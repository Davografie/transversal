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
    ScheduledEffect,
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


class TestScheduling:
    def test_deferred_effect_queued(self):
        _reset()
        engine = EffectsEngine()
        engine.register(_make_sfx(
            "sfx-buff", "Buff", "manual",
            effects=[_make_effect("negative", "end_of_scene", "modify_trait", "step_down", "qi_reserves")],
        ))

        event = GameEvent(type="manual", entity_id="e1", universe="earth")
        result = engine.process_event(event, available_sfx_ids=["sfx-buff"], razmerit_balance=10)

        assert len(result) == 0  # not immediate
        assert engine.scheduled_count == 1

    def test_tick_beat_fires_end_of_beat(self):
        _reset()
        engine = EffectsEngine()
        engine.register(_make_sfx(
            "sfx-beat", "BeatEffect", "manual",
            effects=[_make_effect("negative", "end_of_beat", "modify_trait", "step_down", "target")],
        ))

        event = GameEvent(type="manual", entity_id="e1", universe="earth")
        engine.process_event(event, available_sfx_ids=["sfx-beat"], razmerit_balance=10)
        assert engine.scheduled_count == 1

        before = len([a for a in _test_applied if a.type != "transfer_razmerit"])
        fired_scheduled = engine.tick_beat()
        assert len(fired_scheduled) == 1
        after = len([a for a in _test_applied if a.type != "transfer_razmerit"])
        assert after > before
        assert engine.scheduled_count == 0

    def test_after_beats_counts_down(self):
        _reset()
        engine = EffectsEngine()
        engine.register(_make_sfx(
            "sfx-delayed", "Delayed", "manual",
            effects=[_make_effect("negative", "after_beats", "modify_trait", "step_down", "target")],
        ))

        event = GameEvent(type="manual", entity_id="e1", universe="earth")
        engine.process_event(event, available_sfx_ids=["sfx-delayed"], razmerit_balance=10)

        # Tick 2 beats — shouldn't fire yet (default 3)
        engine.tick_beat()
        engine.tick_beat()
        assert engine.scheduled_count == 1

        # Third tick — fires
        engine.tick_beat()
        assert engine.scheduled_count == 0

    def test_tick_scene(self):
        _reset()
        engine = EffectsEngine()
        engine.register(_make_sfx(
            "sfx-scene", "SceneEffect", "manual",
            effects=[_make_effect("negative", "end_of_scene", "modify_trait", "step_down", "target")],
        ))

        event = GameEvent(type="manual", entity_id="e1", universe="earth")
        engine.process_event(event, available_sfx_ids=["sfx-scene"], razmerit_balance=10)
        engine.tick_beat()  # should NOT fire scene effects

        engine.tick_scene()
        assert engine.scheduled_count == 0

    def test_tick_session(self):
        _reset()
        engine = EffectsEngine()
        engine.register(_make_sfx(
            "sfx-session", "SessionEffect", "manual",
            effects=[_make_effect("negative", "end_of_session", "modify_trait", "step_down", "target")],
        ))

        event = GameEvent(type="manual", entity_id="e1", universe="earth")
        engine.process_event(event, available_sfx_ids=["sfx-session"], razmerit_balance=10)

        engine.tick_session()
        assert engine.scheduled_count == 0

    def test_mixed_timing_effects(self):
        """An SFX can have both immediate and deferred effects."""
        _reset()
        engine = EffectsEngine()
        engine.register(_make_sfx(
            "sfx-mixed", "Mixed", "manual",
            effects=[
                _make_effect("negative", "immediate", "transfer_razmerit", "spend", "self", "1"),
                _make_effect("positive", "immediate", "modify_roll", "step_up_die", "highest_trait_die"),
                _make_effect("negative", "end_of_beat", "modify_trait", "step_down", "primary", "after_resolution"),
            ],
        ))

        event = GameEvent(type="manual", entity_id="e1", universe="earth")
        result = engine.process_event(event, available_sfx_ids=["sfx-mixed"], razmerit_balance=5)

        # Two effects fire immediately (spend + step_up_die)
        assert len(result) == 2
        # One effect is deferred
        assert engine.scheduled_count == 1

    def test_schedule_effect_fires_on_tick(self):
        """Life-path deferred effects queue and fire through schedule_effect."""
        _reset()
        engine = EffectsEngine()
        effect = _make_effect("negative", "end_of_beat", "modify_trait", "step_down", "target")

        engine.schedule_effect("e1", "earth", effect)
        assert engine.scheduled_count == 1

        before = len(_test_applied)
        fired = engine.tick_beat()
        assert len(fired) == 1
        assert engine.scheduled_count == 0
        assert len(_test_applied) > before


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
