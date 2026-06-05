"""Tests for the effects engine."""

from transversal.domain import (
    DieType,
    EffectAction,
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


class TestRegistry:
    def test_register_and_get(self):
        engine = EffectsEngine()
        sfx = SFX(id="sfx-test", name="Test", trigger="on_activate", cost=1)
        engine.register(sfx)
        assert engine.get("sfx-test") is not None
        assert engine.get("sfx-test").name == "Test"

    def test_register_many(self):
        engine = EffectsEngine()
        sfxs = [
            SFX(id="sfx-a", name="A", trigger="on_activate", cost=0),
            SFX(id="sfx-b", name="B", trigger="on_activate", cost=1),
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
        sfx = SFX(id="sfx-test", name="Test", trigger="on_activate", cost=0)
        event = GameEvent(type="on_activate", entity_id="e1", universe="earth")
        assert engine._trigger_matches(sfx, event)

    def test_no_match(self):
        engine = EffectsEngine()
        sfx = SFX(id="sfx-test", name="Test", trigger="on_success", cost=0)
        event = GameEvent(type="on_activate", entity_id="e1", universe="earth")
        assert not engine._trigger_matches(sfx, event)

    def test_complication_trigger_on_roll_with_hitches(self):
        engine = EffectsEngine()
        sfx = SFX(id="sfx-lucky", name="Lucky Break", trigger="on_complication", cost=1)
        from transversal.domain import DieRoll, SimplifiedResult
        event = GameEvent(
            type="on_roll", entity_id="e1", universe="earth",
            roll_result=SimplifiedResult(
                rolls=[DieRoll(die=DieType.D8, result=1, source="test")],
                highest=1, tier="fail", effect_die=None,
                hitches=[DieRoll(die=DieType.D8, result=1, source="test")],
                botch=True, razmerit_earned=1,
            ),
        )
        assert engine._trigger_matches(sfx, event)

    def test_botch_trigger(self):
        engine = EffectsEngine()
        sfx = SFX(id="sfx-insurance", name="Catastrophe Insurance", trigger="on_botch", cost=2)
        from transversal.domain import DieRoll, SimplifiedResult
        event = GameEvent(
            type="on_roll", entity_id="e1", universe="earth",
            roll_result=SimplifiedResult(
                rolls=[DieRoll(die=DieType.D8, result=1, source="test")],
                highest=1, tier="fail", effect_die=None,
                hitches=[DieRoll(die=DieType.D8, result=1, source="test")],
                botch=True, razmerit_earned=1,
            ),
        )
        assert engine._trigger_matches(sfx, event)


class TestProcessEvent:
    def test_immediate_effect_fires(self):
        _reset()
        engine = EffectsEngine()
        engine.register(SFX(
            id="sfx-test", name="Test", trigger="on_activate", timing=EffectTiming.IMMEDIATE,
            cost=0,
            effects=[EffectAction(type="modify_roll", action="step_up_die", target="primary")],
        ))

        event = GameEvent(type="on_activate", entity_id="e1", universe="earth")
        result = engine.process_event(event, available_sfx_ids=["sfx-test"], razmerit_balance=10)

        assert len(result) == 1
        assert result[0].action == "step_up_die"
        # Tracking handler should have been called (cost spend + effect)
        assert len(_test_applied) >= 1

    def test_cost_deducted(self):
        _reset()
        engine = EffectsEngine()
        engine.register(SFX(
            id="sfx-costly", name="Costly", trigger="on_activate", timing=EffectTiming.IMMEDIATE,
            cost=3,
            effects=[EffectAction(type="modify_roll", action="step_up_die", target="primary")],
        ))

        event = GameEvent(type="on_activate", entity_id="e1", universe="earth")
        engine.process_event(event, available_sfx_ids=["sfx-costly"], razmerit_balance=10)

        # Check that transfer_razmerit action was applied
        spend_actions = [a for a in _test_applied if a.type == "transfer_razmerit"]
        assert len(spend_actions) == 1
        assert spend_actions[0].result == "3"

    def test_insufficient_razmerit_skips(self):
        _reset()
        engine = EffectsEngine()
        engine.register(SFX(
            id="sfx-costly", name="Costly", trigger="on_activate", timing=EffectTiming.IMMEDIATE,
            cost=5,
            effects=[EffectAction(type="modify_roll", action="step_up_die", target="primary")],
        ))

        event = GameEvent(type="on_activate", entity_id="e1", universe="earth")
        result = engine.process_event(event, available_sfx_ids=["sfx-costly"], razmerit_balance=2)

        assert len(result) == 0  # skipped due to cost

    def test_unavailable_sfx_skipped(self):
        engine = EffectsEngine()
        engine.register(SFX(id="sfx-test", name="Test", trigger="on_activate", cost=0))
        event = GameEvent(type="on_activate", entity_id="e1", universe="earth")
        result = engine.process_event(event, available_sfx_ids=[], razmerit_balance=10)
        assert len(result) == 0


class TestScheduling:
    def test_deferred_effect_queued(self):
        _reset()
        engine = EffectsEngine()
        engine.register(SFX(
            id="sfx-buff", name="Buff", trigger="on_activate", timing=EffectTiming.END_OF_SCENE,
            cost=0,
            effects=[EffectAction(type="modify_trait", action="step_down", target="qi_reserves")],
        ))

        event = GameEvent(type="on_activate", entity_id="e1", universe="earth")
        result = engine.process_event(event, available_sfx_ids=["sfx-buff"], razmerit_balance=10)

        assert len(result) == 0  # not immediate
        assert engine.scheduled_count == 1

    def test_tick_beat_fires_end_of_beat(self):
        _reset()
        engine = EffectsEngine()
        engine.register(SFX(
            id="sfx-beat", name="BeatEffect", trigger="on_activate", timing=EffectTiming.END_OF_BEAT,
            cost=0,
            effects=[EffectAction(type="modify_trait", action="step_down", target="target")],
        ))

        event = GameEvent(type="on_activate", entity_id="e1", universe="earth")
        engine.process_event(event, available_sfx_ids=["sfx-beat"], razmerit_balance=10)
        assert engine.scheduled_count == 1

        # Count non-spend actions
        before = len([a for a in _test_applied if a.type != "transfer_razmerit"])
        fired_scheduled = engine.tick_beat()
        assert len(fired_scheduled) == 1
        after = len([a for a in _test_applied if a.type != "transfer_razmerit"])
        assert after > before
        assert engine.scheduled_count == 0

    def test_after_beats_counts_down(self):
        _reset()
        engine = EffectsEngine()
        engine.register(SFX(
            id="sfx-delayed", name="Delayed", trigger="on_activate", timing=EffectTiming.AFTER_BEATS,
            cost=0,
            effects=[EffectAction(type="modify_trait", action="step_down", target="target")],
        ))

        event = GameEvent(type="on_activate", entity_id="e1", universe="earth")
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
        engine.register(SFX(
            id="sfx-scene", name="SceneEffect", trigger="on_activate", timing=EffectTiming.END_OF_SCENE,
            cost=0,
            effects=[EffectAction(type="modify_trait", action="step_down", target="target")],
        ))

        event = GameEvent(type="on_activate", entity_id="e1", universe="earth")
        engine.process_event(event, available_sfx_ids=["sfx-scene"], razmerit_balance=10)
        engine.tick_beat()  # should NOT fire scene effects

        engine.tick_scene()
        assert engine.scheduled_count == 0

    def test_tick_session(self):
        _reset()
        engine = EffectsEngine()
        engine.register(SFX(
            id="sfx-session", name="SessionEffect", trigger="on_activate",
            timing=EffectTiming.END_OF_SESSION, cost=0,
            effects=[EffectAction(type="modify_trait", action="step_down", target="target")],
        ))

        event = GameEvent(type="on_activate", entity_id="e1", universe="earth")
        engine.process_event(event, available_sfx_ids=["sfx-session"], razmerit_balance=10)

        engine.tick_session()
        assert engine.scheduled_count == 0
