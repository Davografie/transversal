"""Tests for the effects engine."""

from transversal.domain import (
    DieType,
    Effect,
    EffectTiming,
    SFX,
)
from transversal.services.effects_applier import EffectRegistry
from transversal.services.effects_engine import (
    EffectsEngine,
    GameEvent,
)


# Set up a test registry with a tracking applier
_test_applied = []
_test_registry = EffectRegistry()


def _tracking_handler(action, eid, universe, ctx):
    _test_applied.append(action)


# Register catch-all handler for testing
_test_registry.register("*", "*", _tracking_handler)


# Replace global for tests
import transversal.services.effects_applier as _applier_mod
_applier_mod.effect_registry = _test_registry


def _reset():
    _test_applied.clear()


def _make_sfx(id, name, trigger, effects=None, limit=""):
    """Helper to create the new SFX model."""
    return SFX(
        id=id, name=name, limit=limit, trigger=trigger,
        effects=effects or [],
    )


def _make_effect(polarity="neutral", timing="immediate", type="modify_roll",
                 action="step_up_die", target="primary", result=None):
    """Helper to create an Effect (polarity arg retained for test-call compat)."""
    return Effect(
        timing=EffectTiming(timing),
        type=type, action=action, target=target, result=result,
    )


class TestRegistry:
    def test_register_and_get(self):
        engine = EffectsEngine()
        sfx = _make_sfx("sfx-test", "Test", "manual")
        engine.register(sfx)
        assert engine.get("sfx-test") is not None
        assert engine.get("sfx-test").name == "Test"

    def test_register_many(self):
        engine = EffectsEngine()
        sfxs = [
            _make_sfx("sfx-a", "A", "manual"),
            _make_sfx("sfx-b", "B", "manual"),
        ]
        engine.register_many(sfxs)
        assert engine.get("sfx-a") is not None
        assert engine.get("sfx-b") is not None

    def test_get_missing(self):
        engine = EffectsEngine()
        assert engine.get("nonexistent") is None


class TestTriggerMatching:
    def test_direct_match(self):
        engine = EffectsEngine()
        sfx = _make_sfx("sfx-test", "Test", "manual")
        event = GameEvent(type="manual", entity_id="e1", universe="earth")
        assert engine._trigger_matches(sfx, event)

    def test_legacy_on_activate_matches_manual(self):
        engine = EffectsEngine()
        sfx = _make_sfx("sfx-test", "Test", "on_activate")
        event = GameEvent(type="manual", entity_id="e1", universe="earth")
        assert engine._trigger_matches(sfx, event)

    def test_no_match(self):
        engine = EffectsEngine()
        sfx = _make_sfx("sfx-test", "Test", "on_success")
        event = GameEvent(type="manual", entity_id="e1", universe="earth")
        assert not engine._trigger_matches(sfx, event)

    def test_complication_trigger_on_roll_with_hitches(self):
        engine = EffectsEngine()
        sfx = _make_sfx("sfx-lucky", "Lucky Break", "on_complication")
        from transversal.domain import DieRoll, SimplifiedResult
        event = GameEvent(
            type="on_roll", entity_id="e1", universe="earth",
            roll_result=SimplifiedResult(
                rolls=[DieRoll(die=DieType.D8, result=1, label="test")],
                highest=1, tier="fail", effect_die=None,
                hitches=[DieRoll(die=DieType.D8, result=1, label="test")],
                botch=True, hitches_count=1,
            ),
        )
        assert engine._trigger_matches(sfx, event)

    def test_botch_trigger(self):
        engine = EffectsEngine()
        sfx = _make_sfx("sfx-insurance", "Catastrophe Insurance", "on_botch")
        from transversal.domain import DieRoll, SimplifiedResult
        event = GameEvent(
            type="on_roll", entity_id="e1", universe="earth",
            roll_result=SimplifiedResult(
                rolls=[DieRoll(die=DieType.D8, result=1, label="test")],
                highest=1, tier="fail", effect_die=None,
                hitches=[DieRoll(die=DieType.D8, result=1, label="test")],
                botch=True, hitches_count=1,
            ),
        )
        assert engine._trigger_matches(sfx, event)


class TestProcessEvent:
    def test_immediate_effect_fires(self):
        _reset()
        engine = EffectsEngine()
        engine.register(_make_sfx(
            "sfx-test", "Test", "manual",
            effects=[_make_effect("positive", "immediate", "modify_roll", "step_up_die", "primary")],
        ))

        event = GameEvent(type="manual", entity_id="e1", universe="earth")
        result = engine.process_event(event, available_sfx_ids=["sfx-test"], razmerit_balance=10)

        assert len(result) == 1
        assert result[0].action == "step_up_die"
        assert len(_test_applied) >= 1

    def test_cost_deducted(self):
        _reset()
        engine = EffectsEngine()
        engine.register(_make_sfx(
            "sfx-costly", "Costly", "manual",
            effects=[
                _make_effect("negative", "immediate", "transfer_razmerit", "spend", "self", "3"),
                _make_effect("positive", "immediate", "modify_roll", "step_up_die", "primary"),
            ],
        ))

        event = GameEvent(type="manual", entity_id="e1", universe="earth")
        engine.process_event(event, available_sfx_ids=["sfx-costly"], razmerit_balance=10)

        spend_actions = [a for a in _test_applied if a.type == "transfer_razmerit" and a.action == "spend"]
        assert len(spend_actions) == 1
        assert spend_actions[0].result == "3"

    def test_insufficient_razmerit_skips(self):
        _reset()
        engine = EffectsEngine()
        engine.register(_make_sfx(
            "sfx-costly", "Costly", "manual",
            effects=[
                _make_effect("negative", "immediate", "transfer_razmerit", "spend", "self", "5"),
                _make_effect("positive", "immediate", "modify_roll", "step_up_die", "primary"),
            ],
        ))

        event = GameEvent(type="manual", entity_id="e1", universe="earth")
        result = engine.process_event(event, available_sfx_ids=["sfx-costly"], razmerit_balance=2)

        assert len(result) == 0  # skipped due to insufficient razmerit

    def test_unavailable_sfx_skipped(self):
        engine = EffectsEngine()
        engine.register(_make_sfx("sfx-test", "Test", "manual"))
        event = GameEvent(type="manual", entity_id="e1", universe="earth")
        result = engine.process_event(event, available_sfx_ids=[], razmerit_balance=10)
        assert len(result) == 0


class _Repo:
    """Minimal central scheduled-events double."""

    def __init__(self):
        self.events = []

    def get_entity(self, eid):
        from types import SimpleNamespace
        return SimpleNamespace(id=eid, current_universe="earth", current_location=None, current_projection=None)

    def get_traitsetting(self, tsid):
        return None

    def create_scheduled_event(self, e):
        self.events.append(e)
        return e

    def list_all_scheduled_events(self):
        return list(self.events)

    def update_scheduled_event(self, e):
        return e

    def delete_scheduled_event(self, eid):
        self.events = [x for x in self.events if x.id != eid]
        return True


class TestScheduling:
    def _run(self, engine, effects):
        repo = _Repo()
        engine.register(_make_sfx("sfx-x", "X", "manual", effects=effects))
        event = GameEvent(type="manual", entity_id="e1", universe="earth")
        result = engine.process_event_outcome(event, available_sfx_ids=["sfx-x"], razmerit_balance=10, repo=repo)
        return repo, result

    def test_deferred_effect_queued(self):
        _reset()
        engine = EffectsEngine()
        repo, result = self._run(engine, [_make_effect("negative", "end_of_scene", "modify_trait", "step_down", "qi_reserves")])
        assert len(result.applied) == 0  # not immediate
        assert len(repo.events) == 1

    def test_beat_fires_end_of_beat(self):
        _reset()
        engine = EffectsEngine()
        repo, _ = self._run(engine, [_make_effect("negative", "end_of_beat", "modify_trait", "step_down", "target")])
        from transversal.services.scheduled_events import advance_scheduled_events
        before = len(_test_applied)
        assert advance_scheduled_events(repo, "beat") == 1
        assert len(_test_applied) > before
        assert repo.events == []

    def test_after_beats_counts_down(self):
        _reset()
        engine = EffectsEngine()
        repo, _ = self._run(engine, [_make_effect("negative", "after_beats", "modify_trait", "step_down", "target")])
        from transversal.services.scheduled_events import advance_scheduled_events
        advance_scheduled_events(repo, "beat")
        advance_scheduled_events(repo, "beat")
        assert len(repo.events) == 1
        advance_scheduled_events(repo, "beat")
        assert repo.events == []

    def test_scene(self):
        _reset()
        engine = EffectsEngine()
        repo, _ = self._run(engine, [_make_effect("negative", "end_of_scene", "modify_trait", "step_down", "target")])
        from transversal.services.scheduled_events import advance_scheduled_events
        advance_scheduled_events(repo, "beat")  # should NOT fire scene effects
        assert len(repo.events) == 1
        advance_scheduled_events(repo, "scene")
        assert repo.events == []

    def test_session(self):
        _reset()
        engine = EffectsEngine()
        repo, _ = self._run(engine, [_make_effect("negative", "end_of_session", "modify_trait", "step_down", "target")])
        from transversal.services.scheduled_events import advance_scheduled_events
        advance_scheduled_events(repo, "session")
        assert repo.events == []

    def test_mixed_timing_effects(self):
        """An SFX can have both immediate and deferred effects."""
        _reset()
        engine = EffectsEngine()
        repo, result = self._run(engine, [
            _make_effect("negative", "immediate", "transfer_razmerit", "spend", "self", "1"),
            _make_effect("positive", "immediate", "modify_roll", "step_up_die", "highest_trait_die"),
            _make_effect("negative", "end_of_beat", "modify_trait", "step_down", "primary", "after_resolution"),
        ])
        # Two effects fire immediately (spend + step_up_die), one is deferred.
        assert len(result.applied) == 2
        assert len(repo.events) == 1


# ── Fog-of-war learning trigger + context substitution ──

def test_on_trait_learn_trigger_matches_trait_learned():
    engine = EffectsEngine()
    sfx = _make_sfx("sfx-learn", "Learn", "on_trait_learn")
    event = GameEvent(type="trait_learned", entity_id="char-1", universe="earth")
    assert engine._trigger_matches(sfx, event)


def test_on_trait_learn_trigger_ignores_other_events():
    engine = EffectsEngine()
    sfx = _make_sfx("sfx-learn", "Learn", "on_trait_learn")
    event = GameEvent(type="trait_updated", entity_id="char-1", universe="earth")
    assert not engine._trigger_matches(sfx, event)


def test_batch4_triggers_match_their_fire_events():
    """on_set / on_beat / on_scene fire directly with those event types."""
    engine = EffectsEngine()
    for trigger in ("on_set", "on_beat", "on_scene"):
        sfx = _make_sfx(f"sfx-{trigger}", trigger, trigger)
        event = GameEvent(type=trigger, entity_id="char-1", universe="earth")
        assert engine._trigger_matches(sfx, event), trigger
        # They must not fire for unrelated events.
        other = GameEvent(type="manual", entity_id="char-1", universe="earth")
        assert not engine._trigger_matches(sfx, other), trigger


def test_substitute_effect_context_across_fields():
    from transversal.services.effects_engine import _substitute_effect_context

    effect = Effect(
        timing=EffectTiming.IMMEDIATE, type="modify_trait", action="reveal",
        target="{trait_id}", entity="{owner}", result="{learner}",
        context={"learner": "{learner}"},
    )
    ctx = {"trait_id": "hidden", "owner": "char-2", "learner": "char-1"}
    out = _substitute_effect_context(effect, ctx)
    assert out.target == "hidden"
    assert out.entity == "char-2"
    assert out.result == "char-1"
    assert out.context == {"learner": "char-1"}


def test_substitute_effect_context_covers_scopes():
    from transversal.services.effects_engine import _substitute_effect_context

    effect = Effect(
        timing=EffectTiming.IMMEDIATE, type="travel", action="move",
        result="{choose_location}",
        target_scope="universe:{target_universe}",
        entity_scope="location:{target_location}",
    )
    out = _substitute_effect_context(
        effect, {"target_universe": "three_realms", "target_location": "krasnoyarsk"}
    )
    assert out.target_scope == "universe:three_realms"
    assert out.entity_scope == "location:krasnoyarsk"


def test_substitute_effect_context_leaves_choose_placeholder():
    from transversal.services.effects_engine import _substitute_effect_context

    effect = Effect(
        timing=EffectTiming.IMMEDIATE, type="modify_trait", action="gain",
        target="{choose_trait}", result="d6",
    )
    out = _substitute_effect_context(effect, {"trait_id": "x"})
    assert out.target == "{choose_trait}"
    assert out.result == "d6"


def test_substitute_effect_context_uses_bindings():
    from transversal.services.effects_engine import _substitute_effect_context
    from transversal.services.target_resolver import Binding

    effect = Effect(timing=EffectTiming.IMMEDIATE, type="modify_trait", action="step_down", target="{complication}")
    out = _substitute_effect_context(effect, {}, {"complication": Binding(value="gmc-1:injury", element="traitsetting")})
    assert out.target == "gmc-1:injury"


def test_bindings_override_context():
    from transversal.services.effects_engine import _substitute_effect_context
    from transversal.services.target_resolver import Binding

    effect = Effect(timing=EffectTiming.IMMEDIATE, type="x", action="y", target="{v}")
    out = _substitute_effect_context(effect, {"v": "context"}, {"v": Binding(value="binding", element="string")})
    assert out.target == "binding"


def test_substitute_effect_context_skips_many_bindings():
    from transversal.services.effects_engine import _substitute_effect_context
    from transversal.services.target_resolver import Binding

    effect = Effect(timing=EffectTiming.IMMEDIATE, type="x", action="y", target="{friends}")
    out = _substitute_effect_context(effect, {}, {
        "friends": Binding(value="a", values=["a", "b"], element="entity", cardinality="many"),
    })
    assert out.target == "{friends}"  # many binding is not stringified into a string field


def test_resolve_effect_spec_choices_resolves_all_refs():
    from types import SimpleNamespace as NS
    from transversal.domain import TargetRef
    from transversal.services.effects_engine import resolve_effect_spec_choices
    from transversal.services.target_spec import ChooseStep, SelectStep, TargetSpec

    class Repo:
        def __init__(self):
            self.entities = {
                "kael": NS(id="kael", current_location="loc-1", current_universe="earth"),
                "gmc-1": NS(id="gmc-1", current_location="loc-1", current_universe="earth"),
            }
        def get_entity(self, eid):
            return self.entities.get(eid)
        def list_entities_by_location(self, lid):
            return [e for e in self.entities.values() if e.current_location == lid]

    repo = Repo()
    entity = repo.entities["kael"]
    effect = Effect(
        timing=EffectTiming.IMMEDIATE, type="modify_pool", action="add_trait_rating",
        refs={
            "trait": TargetRef(spec=TargetSpec(steps=[SelectStep(collection="occupants"), ChooseStep(count=1)])),
            "pool": TargetRef(spec=TargetSpec(steps=[SelectStep(collection="self")])),
        },
    )
    resolved, pending = resolve_effect_spec_choices(effect, "refs.trait", {1: ["gmc-1"]}, entity, repo)
    assert pending == []
    assert resolved[0].refs["trait"].value == "gmc-1"
    assert resolved[0].refs["pool"].value == "kael"


def test_sequential_execution_defers_effects_after_choose():
    """An effect that blocks on a choose must gate every later immediate effect."""
    _reset()
    engine = EffectsEngine()
    engine.register(_make_sfx(
        "sfx-seq", "Seq", "manual",
        effects=[
            _make_effect("positive", "immediate", "modify_roll", "step_up_die", "primary"),
            _make_effect("either", "immediate", "modify_pool", "add_trait_rating", "{choose_trait}"),
            _make_effect("either", "immediate", "modify_pool", "resolve", "difficulty:loc-1"),
        ],
    ))

    event = GameEvent(type="manual", entity_id="e1", universe="earth")
    outcome = engine.process_event_outcome(event, available_sfx_ids=["sfx-seq"], razmerit_balance=10)

    # Effect 1 applied; effect 2 blocked; effect 3 deferred to the continuation.
    assert [a.action for a in outcome.applied] == ["step_up_die"]
    assert len(outcome.pending) == 1
    assert len(outcome.pending[0].continuation) == 1
    assert outcome.pending[0].continuation[0].action == "resolve"
    assert "resolve" not in [a.action for a in outcome.applied]


def test_on_trait_offered_trigger_matches_trait_offered():
    engine = EffectsEngine()
    sfx = _make_sfx("sfx-offer", "Offer", "on_trait_offered")
    event = GameEvent(type="trait_offered", entity_id="char-1", universe="earth")
    assert engine._trigger_matches(sfx, event)


def test_on_trait_offered_trigger_ignores_other_events():
    engine = EffectsEngine()
    sfx = _make_sfx("sfx-offer", "Offer", "on_trait_offered")
    event = GameEvent(type="trait_learned", entity_id="char-1", universe="earth")
    assert not engine._trigger_matches(sfx, event)


def test_sfx_triggered_emitted_when_effect_applies(monkeypatch):
    from transversal.services import effects_engine as ee

    engine = EffectsEngine()
    sfx = _make_sfx(
        "sfx-x", "X", "manual",
        effects=[_make_effect(timing="immediate", type="transfer_razmerit", action="earn", target="self", result="1")],
    )
    engine.register(sfx)

    emitted = []
    monkeypatch.setattr(ee, "_emit_sfx_triggered", lambda entity_id, s: emitted.append((entity_id, s.id)))

    event = GameEvent(type="manual", entity_id="char-1", universe="earth")
    outcome = engine.process_event_outcome(event, ["sfx-x"], 0)

    assert len(outcome.applied) == 1
    assert emitted == [("char-1", "sfx-x")]


def test_process_event_defers_choose_projection_in_context():
    engine = EffectsEngine()
    effect = Effect(
        timing=EffectTiming.IMMEDIATE, type="travel", action="move",
        target="krasnoyarsk", target_scope="universe:earth",
        context={"transversal_type": "consciousness", "projection": "{choose_projection}"},
    )
    sfx = _make_sfx("sfx-portal", "Portal", "manual", effects=[effect])
    engine.register(sfx)

    event = GameEvent(type="manual", entity_id="char-1", universe="earth")
    outcome = engine.process_event_outcome(event, ["sfx-portal"], 0)

    assert len(outcome.applied) == 0
    assert len(outcome.pending) == 1
    assert outcome.pending[0].effect.context["projection"] == "{choose_projection}"


def test_roll_timing_effect_is_armed_not_applied():
    from transversal.services import roll_deferral

    roll_deferral.reset()
    try:
        engine = EffectsEngine()
        sfx = _make_sfx(
            "sfx-arm", "Arm", "manual",
            effects=[Effect(
                timing=EffectTiming.ON_RESULT,
                type="modify_trait", action="gain", target="hazard",
            )],
        )
        engine.register(sfx)

        event = GameEvent(type="manual", entity_id="char-1", universe="earth")
        outcome = engine.process_event_outcome(event, ["sfx-arm"], 10)

        # Roll-timing effects are armed, not applied immediately.
        assert outcome.applied == []
        assert [e.target for e in roll_deferral.list_armed("char-1")] == ["hazard"]
    finally:
        roll_deferral.reset()


class TestListenerSpec:
    """`arming_scope: listener_spec` — the rule listens to whoever its path names.

    The curse case: a rule armed by one entity that watches another's rolls.
    """

    class _Repo:
        def __init__(self):
            from transversal.domain import Entity, EntityType
            self.entities = {
                "char-1": Entity(id="char-1", type=EntityType.CHARACTER, name="Caster",
                                 current_universe="earth"),
                "gmc-1": Entity(id="gmc-1", type=EntityType.GMC, name="Bound",
                                current_universe="earth"),
            }

        def get_entity(self, eid):
            return self.entities.get(eid)

        def list_all_entities(self):
            return list(self.entities.values())

        def list_entities_by_type(self, etype):
            return [e for e in self.entities.values() if e.type == etype]

        def list_entities_by_location(self, loc_id):
            return []

        def get_traitsettings_for_entity(self, eid):
            return []

    def _path(self, value="gmc"):
        from transversal.services.target_spec import TargetSpec
        return TargetSpec(steps=[
            {"kind": "select", "collection": "entities"},
            {"kind": "filter", "field": "type", "operator": "==", "value": value},
        ])

    def _arm(self, repo, listener_spec):
        from transversal.services import roll_deferral
        from transversal.services.target_spec import TargetSpec

        engine = EffectsEngine()
        sfx = _make_sfx(
            "sfx-curse", "Curse", "manual",
            effects=[Effect(timing=EffectTiming.ON_RESULT, type="modify_trait",
                            action="step_down", target="rating")],
        )
        sfx.source_kind = None
        sfx.arming_scope = "listener_spec"
        sfx.listener_spec = listener_spec
        engine.register(sfx)
        event = GameEvent(type="manual", entity_id="char-1", universe="earth")
        engine.process_event_outcome(event, ["sfx-curse"], 10, repo=repo)
        return roll_deferral

    def test_it_arms_the_entities_the_path_names_not_the_activator(self):
        from transversal.services import roll_deferral
        roll_deferral.reset()
        try:
            repo = self._Repo()

            deferral = self._arm(repo, self._path("gmc"))

            assert [e.target for e in deferral.list_armed("gmc-1")] == ["rating"]
            assert deferral.list_armed("char-1") == [], "the caster is not listening"
        finally:
            roll_deferral.reset()

    def test_an_empty_set_arms_nobody_rather_than_falling_back_to_the_activator(self):
        from transversal.services import roll_deferral
        roll_deferral.reset()
        try:
            repo = self._Repo()

            deferral = self._arm(repo, self._path("asset"))  # nobody in the repo is one

            assert deferral.list_armed("char-1") == []
            assert deferral.list_armed("gmc-1") == []
        finally:
            roll_deferral.reset()

    def test_the_armed_entry_records_how_it_got_there(self):
        from transversal.services import roll_deferral
        roll_deferral.reset()
        try:
            repo = self._Repo()

            self._arm(repo, self._path("gmc"))

            entry = roll_deferral._armed["gmc-1"][0]
            assert entry.scope == "listener_spec"
            assert entry.source_sfx_id == "sfx-curse"
        finally:
            roll_deferral.reset()
