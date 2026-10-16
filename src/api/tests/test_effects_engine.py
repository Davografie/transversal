"""Tests for the effects engine."""

import pytest

from transversal.domain import (
    TargetRef,
    DieType,
    Effect,
    EffectTiming,
    SFX,
)
from transversal.services.campaign_scope import use_campaign
from transversal.services.effects_applier import EffectRegistry
from transversal.services.effects_engine import (
    EffectsEngine,
    GameEvent,
)

#: Armed state is per-campaign (B305). These tests exercise in-request behaviour,
#: and every request names a campaign.
_CAMPAIGN = "tv2-test-effects-engine"


@pytest.fixture(autouse=True)
def _scoped():
    with use_campaign(_CAMPAIGN):
        yield


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


def test_substitute_effect_context_covers_every_field_that_holds_a_token():
    from transversal.services.effects_engine import _substitute_effect_context

    effect = Effect(
        timing=EffectTiming.IMMEDIATE, type="travel", action="move",
        target="{destination}", entity="{traveller}", result="{outcome}",
        refs={"body": TargetRef(value="{body}")},
        # A per-die effect names *whose* die it runs for, and that is a token too.
        # Leaving it literal meant "for each unchosen die of mine" matched nothing
        # (or, worse for a rule that creates a hazard, every unchosen die).
        die_filter={"role": None, "ts_id": "{source}"},
    )
    out = _substitute_effect_context(
        effect, {"destination": "krasnoyarsk", "traveller": "char-9",
                 "outcome": "d10", "body": "char-9:earth", "source": "ts-scar"},
    )
    assert out.target == "krasnoyarsk"
    assert out.entity == "char-9"
    assert out.result == "d10"
    assert out.refs["body"].value == "char-9:earth"
    assert out.die_filter == {"role": None, "ts_id": "ts-scar"}


def test_a_dice_row_is_substituted_element_by_element():
    """A rating row may name a die the way the single `result` field may.

    `context['dice']` is the rating a trait-gain effect creates at ([[B307]]), and
    `{effect_die}` is the die an author most needs there — "gain it at the effect
    die". A list context value passed through untouched, so every element stayed
    literal and the row failed to parse.
    """
    from transversal.services.effects_engine import _substitute_effect_context

    effect = Effect(timing=EffectTiming.IMMEDIATE, type="modify_trait", action="gain",
                    target="trait-x", result="d6",
                    context={"dice": ["d6", "{effect_die}"], "statement": "burnt"})
    out = _substitute_effect_context(effect, {"effect_die": "d10"})
    assert out.context == {"dice": ["d6", "d10"], "statement": "burnt"}
    # Non-string entries pass through, like every other context value.
    mixed = Effect(timing=EffectTiming.IMMEDIATE, type="modify_trait", action="gain",
                   target="trait-x", context={"dice": ["d6", None]})
    assert _substitute_effect_context(mixed, {}).context == {"dice": ["d6", None]}


def test_a_bound_list_valued_name_is_not_reported_unbound_in_the_rating():
    """A `many` name in `result` is *bound* — it just cannot be a string.

    [[B282]]'s guard skips an effect whose flat field names something nothing
    bound, because applying it would point at the literal ``"{name}"``. A
    list-valued binding is a different thing: it is bound, and for an action that
    creates a trait at a whole **rating** it has a consumer (the row). Reporting it
    as unbound is what made "gain this at the rating the source already has"
    impossible to *name* ([[B307]]).
    """
    from transversal.services.effects_engine import _substitute_effect_context
    from transversal.services.target_resolver import Binding

    bindings = {"formation_rating": Binding(
        value="ts-1", values=["ts-1"], element="rating_die", cardinality="many")}
    row = Effect(timing=EffectTiming.IMMEDIATE, type="modify_trait", action="gain",
                 target="formation", result="{formation_rating}")

    unresolved: list[str] = []
    _substitute_effect_context(row, {}, bindings, unresolved)
    assert unresolved == []

    # The control: the same name on an action with no rating to put it in is still
    # refused, so a junk value never reaches a handler as "the first of something".
    unresolved = []
    _substitute_effect_context(
        Effect(timing=EffectTiming.IMMEDIATE, type="modify_dice_limit", action="increase",
               result="{formation_rating}"),
        {}, bindings, unresolved)
    assert unresolved == ["formation_rating"]

    # And a name nothing bound is refused everywhere, the guard's whole point.
    unresolved = []
    _substitute_effect_context(row, {}, {}, unresolved)
    assert unresolved == ["formation_rating"]


def test_die_filter_substitution_keeps_a_null_predicate_null():
    """"Not chosen" is expressed as a `null`, so the substitution must pass
    non-strings through rather than stringifying them into a value no die has."""
    from transversal.services.effects_engine import _substitute_effect_context

    effect = Effect(timing=EffectTiming.IMMEDIATE, type="modify_trait", action="gain",
                    target="trait-x", die_filter={"role": None, "ts_id": "{source}"})
    out = _substitute_effect_context(effect, {"source": "ts-scar"})
    assert out.die_filter == {"role": None, "ts_id": "ts-scar"}
    # And the substitution is what makes the per-die select match the right die.
    from transversal.services.roll_deferral import _die_matches

    assert _die_matches({"ts_id": "ts-scar", "role": None}, out.die_filter)
    assert not _die_matches({"ts_id": "ts-other", "role": None}, out.die_filter)


def test_substitute_effect_context_leaves_an_unmatched_token():
    from transversal.services.effects_engine import _substitute_effect_context

    effect = Effect(
        timing=EffectTiming.IMMEDIATE, type="modify_trait", action="gain",
        target="{source_trait}", result="d6",
    )
    out = _substitute_effect_context(effect, {"trait_id": "x"})
    assert out.target == "{source_trait}"
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


# ── B282 — an unbound ``{token}`` must not run against the literal string ──

def test_substitute_effect_context_reports_the_names_it_could_not_fill():
    """The accumulator a caller uses to refuse the effect ([[B282]]).

    Only the fields that **name something or carry a value into an id** count: a
    reference's value is one, while ``context`` (a policy keyword lives there) and
    ``die_filter`` (a selector, which fails closed) are deliberately exempt.
    """
    from transversal.services.effects_engine import _substitute_effect_context

    effect = Effect(
        timing=EffectTiming.IMMEDIATE, type="modify_trait", action="gain",
        target="{picked}", entity="{owner}", result="{effect_die}",
        refs={"recipient": TargetRef(value="{giver}")},
        context={"projection": "{last_projection}"},
        die_filter={"ts_id": "{trait_setting}"},
    )
    unresolved: list[str] = []
    out = _substitute_effect_context(effect, {"owner": "char-2"}, unresolved=unresolved)

    assert set(unresolved) == {"effect_die", "picked", "giver"}
    assert out.entity == "char-2"          # the bound name still resolves
    assert out.target == "{picked}"        # the returned effect is unchanged
    assert "{last_projection}" not in unresolved
    assert "{trait_setting}" not in unresolved


def test_the_path_form_is_not_reported_as_an_unbound_token():
    """``select variable picked`` already resolves to zero targets on its own — it
    must not be mistaken for a flat ``{picked}`` ([[B282]])."""
    from transversal.services.effects_engine import _substitute_effect_context
    from transversal.services.target_spec import SelectStep, TargetSpec

    effect = Effect(
        timing=EffectTiming.IMMEDIATE, type="modify_trait", action="gain",
        target_spec=TargetSpec(steps=[SelectStep(collection="variable", variable="picked")]),
    )
    unresolved: list[str] = []
    _substitute_effect_context(effect, {}, unresolved=unresolved)
    assert unresolved == []


def test_an_unbound_flat_token_skips_the_effect_and_records_why():
    """An effect naming a value nothing bound applies **zero** times, and says so
    on the outcome — never against the literal ``"{picked}"`` as if it were an id."""
    _reset()
    engine = EffectsEngine()
    engine.register(_make_sfx("sfx-picked", "Picked", "manual", effects=[
        Effect(timing=EffectTiming.IMMEDIATE, type="modify_trait", action="gain",
               target="{picked}", result="d6"),
    ]))
    event = GameEvent(type="manual", entity_id="char-1", universe="earth")
    outcome = engine.process_event_outcome(event, ["sfx-picked"], 0)

    assert _test_applied == []
    assert outcome.applied == []
    notes = [n for n in outcome.notes if n.get("action") == "gain"]
    assert notes, outcome.notes
    assert "{picked}" in notes[0]["note"]


def test_the_same_effect_applies_once_the_name_is_bound():
    """The other half: the *same* authored effect runs where the name exists."""
    _reset()
    engine = EffectsEngine()
    engine.register(_make_sfx("sfx-picked", "Picked", "manual", effects=[
        Effect(timing=EffectTiming.IMMEDIATE, type="modify_trait", action="gain",
               target="{picked}", result="d6"),
    ]))
    event = GameEvent(type="manual", entity_id="char-1", universe="earth",
                      context={"picked": "trait-x"})
    outcome = engine.process_event_outcome(event, ["sfx-picked"], 0)

    assert [e.action for e in _test_applied] == ["gain"]
    assert [e.target for e in outcome.applied] == ["trait-x"]


def test_a_context_policy_token_does_not_skip_the_effect():
    """``{last_projection}`` is a *keyword* the travel handler reads, not a bound
    name — the exemption that keeps banish/transverse firing ([[B282]])."""
    _reset()
    engine = EffectsEngine()
    engine.register(_make_sfx("sfx-banish", "Banish", "manual", effects=[
        Effect(timing=EffectTiming.IMMEDIATE, type="travel", action="move",
               target="loc-1", context={"projection": "{last_projection}"}),
    ]))
    event = GameEvent(type="manual", entity_id="char-1", universe="earth")
    outcome = engine.process_event_outcome(event, ["sfx-banish"], 0)

    assert [e.action for e in _test_applied] == ["move"]
    assert len(outcome.applied) == 1


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
    from transversal.services.target_scopes import choice_spec

    _reset()
    engine = EffectsEngine()
    blocking = _make_effect("either", "immediate", "modify_pool", "add_trait_rating", "")
    blocking.target_spec = choice_spec("trait", "traitset:ts-x")
    engine.register(_make_sfx(
        "sfx-seq", "Seq", "manual",
        effects=[
            _make_effect("positive", "immediate", "modify_roll", "step_up_die", "primary"),
            blocking,
            _make_effect("either", "immediate", "modify_pool", "resolve", "difficulty:loc-1"),
        ],
    ))

    event = GameEvent(type="manual", entity_id="e1", universe="earth")
    outcome = engine.process_event_outcome(event, available_sfx_ids=["sfx-seq"], razmerit_balance=10)

    # Effect 1 applied; effect 2 stopped at its choose step (a structured choice
    # carrying the pool); effect 3 waits for the answer.
    assert [a.action for a in outcome.applied] == ["step_up_die"]
    assert len(outcome.structured) == 1
    assert outcome.structured[0].field == "target"
    assert len(outcome.structured[0].continuation) == 1
    assert outcome.structured[0].continuation[0].action == "resolve"


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
        target="krasnoyarsk",
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

            entry = roll_deferral.armed_entry_for("gmc-1", "sfx-curse")
            assert entry.scope == "listener_spec"
            assert entry.source_sfx_id == "sfx-curse"
        finally:
            roll_deferral.reset()


def test_resuming_a_subject_choice_also_resolves_the_effects_refs():
    """Gift's shape: `entitySpec = select occupants → choose 1` **and**
    `refs.trait = select source`.

    The choice is raised for the subject before the refs are walked — the effect has
    to stay whole for the answer to re-resolve it — so the resume path must finish
    the job. It resolved the subject and left the ref as a *path*, and the handler
    reads `refs.trait.value`: the recipient arrived, the trait did not, and the move
    silently did nothing.
    """
    from types import SimpleNamespace as NS

    from transversal.domain import Effect, TargetRef
    from transversal.services.effects_engine.refs import resolve_effect_spec_choices
    from transversal.services.target_spec import (
        ChooseStep, SelectStep, TargetSpec,
    )

    class _Repo:
        def __init__(self):
            self.here = NS(id="e1", current_location="loc-1")
            self.target = NS(id="e2", current_location="loc-1")
            self.ts = NS(id="ts-1", trait_id="trait-1", entity_id="e1")

        def get_entity(self, eid):
            return {"e1": self.here, "e2": self.target}.get(eid)

        def get_traitsetting(self, tid):
            return self.ts if tid == "ts-1" else None

        def list_entities_by_location(self, _loc):
            return [self.here, self.target]

    repo = _Repo()
    effect = Effect(
        type="modify_trait", action="move",
        entity_spec=TargetSpec(steps=[
            SelectStep(collection="occupants"), ChooseStep(count=1)]),
        refs={"trait": TargetRef(value="", spec=TargetSpec(steps=[
            SelectStep(collection="source")]))},
    )

    applied, pending = resolve_effect_spec_choices(
        effect, "entity", {1: ["e2"]}, repo.here, repo,
        source_kind="trait_setting", source_id="ts-1", source_sfx_id="sfx-x")

    assert pending == []
    assert len(applied) == 1
    resolved = applied[0]
    assert resolved.entity == "e2", "the chosen recipient"
    assert resolved.entity_spec is None
    assert resolved.refs["trait"].value == "ts-1", "…and the trait to move, not a path"
    assert resolved.refs["trait"].spec is None


def test_effect_wire_dict_is_a_valid_effect_input():
    """A structured choice's effect is echoed straight back as an `EffectInput`.

    Every key the wire dict emits must therefore be one the input accepts, and the
    two shapes must not drift apart. This is the check that was missing: `owner_spec`
    and `result_spec` were added to `Effect` and never to the camel-case map, so the
    echoed object carried `owner_spec` / `result_spec` / `branches`, GraphQL rejected
    the **whole** `resolveEffectTargets` mutation, and answering a structured choice
    did nothing at all — visible only in the browser console, as
    "Field 'owner_spec' is not defined by type 'EffectInput'".
    """
    from transversal.api.graphql.type_defs.effects import EffectInput
    from transversal.domain import (
        Condition, ConditionType, Effect, EffectBranch, TargetRef,
    )
    from transversal.services.effects_engine.wire import effect_to_wire_dict
    from transversal.services.target_spec import SelectStep, TargetSpec

    def spec():
        return TargetSpec(steps=[SelectStep(collection="source")])

    effect = Effect(
        timing="immediate", type="modify_trait", action="move",
        die_filter={"x": 1}, target_spec=spec(), entity_spec=spec(),
        owner_spec=spec(), result_spec=spec(),
        refs={"trait": TargetRef(value="", spec=spec())},
        branches=[EffectBranch(id="a", label="A", effects=[])],
        conditions=[Condition(type=ConditionType.ALWAYS)],
    )
    wire = effect_to_wire_dict(effect)

    accepted = {f.python_name for f in EffectInput.__strawberry_definition__.fields}
    # The wire dict speaks camelCase where Strawberry renames; map back to compare.
    camel = {"dieFilter": "die_filter", "targetSpec": "target_spec",
             "entitySpec": "entity_spec", "ownerSpec": "owner_spec",
             "resultSpec": "result_spec"}
    unknown = [k for k in wire if camel.get(k, k) not in accepted]
    assert unknown == [], f"the wire dict carries keys EffectInput rejects: {unknown}"

    # …and the two shapes stay together, so the *next* field added cannot slip past.
    missing = set(Effect.model_fields) - accepted
    assert missing == set(), f"Effect fields with no EffectInput counterpart: {sorted(missing)}"


def test_a_rule_authors_no_duration_by_default():
    """The 1-roll default is gone, and its absence means what it says.

    It used to default to one roll, which the editor round-tripped and wrote into
    storage — 42 of 46 live rules carried a value nobody had chosen and could not
    see, and `sfx-gift` showed "Duration 1 roll" in the Active rail for a rule whose
    effects are both immediate, where the duration does nothing at all.

    Its only reader is the arming of roll-timing effects, and there `None` means
    **no roll limit** — the honest reading of "the author set nothing", and what the
    panel now says out loud.
    """
    from transversal.domain import SFX
    from transversal.services.roll_deferral import _split_duration

    assert SFX(id="x", name="X", trigger="manual").duration is None
    assert _split_duration(None) == (None, []), "no duration must not invent a budget"

    # …and an authored one still reads as written.
    from transversal.domain import EffectDuration, Timer

    authored = EffectDuration(timers=[Timer(event="rolls", remaining=2)])
    assert _split_duration(authored) == (2, [])


def test_a_choice_event_says_where_the_question_came_from(monkeypatch):
    """The client puts a choice table where it was **raised**, so the event must say.

    The author's rule: a manual press on a sheet asks on the sheet, a roll asks in the
    roller, and an automatic rule (a state change or a timer nobody pressed) asks in a
    floating panel because there is no obvious place its reader is looking. `origin` is
    set per emission site, so nothing has to be inferred at the far end.

    A follow-up inherits it client-side rather than server-side: the client is the one
    that knows where it is still rendering, and `resolveEffectTargets` / `resolveSfxLoop`
    accept the origin back for exactly that reason.
    """
    from types import SimpleNamespace

    from transversal.api.sse import bus as bus_mod
    from transversal.domain import Effect
    from transversal.services import roll_orchestrator as ro
    from transversal.services import session_manager as sm_mod
    from transversal.services.effects_engine.events import StructuredChoice

    captured = []
    monkeypatch.setattr(bus_mod, "event_bus", SimpleNamespace(publish=captured.append), raising=False)
    monkeypatch.setattr(sm_mod, "session_manager",
                        SimpleNamespace(list_active=lambda: [SimpleNamespace(id="s1")]), raising=False)

    choice = StructuredChoice(element="entity", candidates=[], count=1, field="entity",
                              effect=Effect(type="modify_trait", action="move"))

    ro._emit_pending_choices("e1", "earth", [], [choice])
    assert captured, "an event must be published"
    assert captured[0].event == "sfx_choice_required"
    assert captured[0].data["choices"][0]["origin"] == "roll", "the default is a roll"

    for origin in ("sheet", "auto"):
        captured.clear()
        ro._emit_pending_choices("e1", "earth", [], [choice], origin=origin)
        assert captured[0].data["choices"][0]["origin"] == origin


def test_a_multi_select_ref_fans_out_to_one_effect_per_pick():
    """The author's case: a Learner path of `select occupants → choose 2`, answered
    with two people, must teach **both**.

    `choose` reports its `count` on the pending choice (that is what the wizard's
    multi-select reads), and answering with several ids must fan the reference out
    the same way a multi-value path does — one effect per pick, each carrying one
    concrete learner. A resume that collapsed the picks to the first would look
    like it worked and only ever teach one person.
    """
    from types import SimpleNamespace as NS

    from transversal.domain import Effect, TargetRef
    from transversal.services.effects_engine.refs import resolve_effect_spec_choices
    from transversal.services.target_spec import (
        ChooseStep, SelectStep, TargetSpec,
    )

    class _Repo:
        def __init__(self):
            self.here = NS(id="e1", current_location="loc-1")
            self.a = NS(id="e2", current_location="loc-1")
            self.b = NS(id="e3", current_location="loc-1")

        def get_entity(self, eid):
            return {"e1": self.here, "e2": self.a, "e3": self.b}.get(eid)

        def list_entities_by_location(self, _loc):
            return [self.here, self.a, self.b]

    repo = _Repo()
    effect = Effect(
        type="entity", action="learn", target="gmc-hidden",
        refs={"learner": TargetRef(value="", spec=TargetSpec(steps=[
            SelectStep(collection="occupants"), ChooseStep(count=2)]))},
    )

    applied, pending = resolve_effect_spec_choices(
        effect, "refs.learner", {1: ["e2", "e3"]}, repo.here, repo,
        source_kind="entity", source_id="e1", source_sfx_id="sfx-reveal-entity")

    assert pending == []
    assert sorted(e.refs["learner"].value for e in applied) == ["e2", "e3"], \
        "one effect per pick, each with a concrete learner"
    assert all(e.refs["learner"].spec is None for e in applied), \
        "…and no path left for the handler to read instead"


def test_a_multi_select_subject_fans_out_to_one_effect_per_pick():
    """The other half of the author's ask: once a multi-choose *asks*, the answer
    must reach **everyone** picked — one effect per selection, each with a concrete
    subject. Before, the silent shortcut answered with the first candidate and the
    rest were lost; now the fan-out is what carries them."""
    from types import SimpleNamespace as NS

    from transversal.domain import Effect
    from transversal.services.effects_engine.refs import resolve_effect_spec_choices
    from transversal.services.target_spec import (
        ChooseStep, SelectStep, TargetSpec,
    )

    class _Repo:
        def __init__(self):
            self.here = NS(id="e1", current_location="loc-1")
            self.a = NS(id="e2", current_location="loc-1")
            self.b = NS(id="e3", current_location="loc-1")

        def get_entity(self, eid):
            return {"e1": self.here, "e2": self.a, "e3": self.b}.get(eid)

        def list_entities_by_location(self, _loc):
            return [self.here, self.a, self.b]

    repo = _Repo()
    effect = Effect(
        type="modify_trait", action="move",
        entity_spec=TargetSpec(steps=[
            SelectStep(collection="occupants"), ChooseStep(count=None)]),
    )

    applied, pending = resolve_effect_spec_choices(
        effect, "entity", {1: ["e2", "e3"]}, repo.here, repo)

    assert pending == []
    assert sorted(e.entity for e in applied) == ["e2", "e3"], \
        "one effect per pick, each with a concrete subject"
    assert all(e.entity_spec is None for e in applied)
