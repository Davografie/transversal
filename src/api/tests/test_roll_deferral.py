"""Tests for roll-scoped effect deferral (the "rolls" temporal spine)."""

from transversal.domain import (
    Effect,
    EffectDuration,
    EffectTiming,
    Timer,
    TimerCombine,
)
from transversal.services import roll_deferral


def _make_effect(timing=EffectTiming.ON_RESULT, target="hazard", result=None, duration=None):
    return Effect(
        timing=timing,
        type="modify_trait",
        action="gain",
        target=target,
        result=result,
        duration=duration,
    )


def test_arm_and_fire_one_shot(monkeypatch):
    roll_deferral.reset()
    applied = []

    class FakeRegistry:
        def apply(self, effect, entity_id, universe, context):
            applied.append((effect, entity_id, universe, context))

    monkeypatch.setattr("transversal.services.effects_applier.effect_registry", FakeRegistry())

    eff = _make_effect()
    roll_deferral.arm_effect("e1", eff)
    assert len(roll_deferral.list_armed("e1")) == 1

    fired = roll_deferral.fire_armed("e1", "on_result", "earth", {"total": 5})

    assert len(fired) == 1
    assert len(applied) == 1
    # one-shot (no rolls duration) is consumed after firing
    assert roll_deferral.list_armed("e1") == []


def test_rolls_budget_fires_n_times(monkeypatch):
    roll_deferral.reset()
    applied = []

    class FakeRegistry:
        def apply(self, effect, entity_id, universe, context):
            applied.append(effect)

    monkeypatch.setattr("transversal.services.effects_applier.effect_registry", FakeRegistry())

    duration = EffectDuration(
        timers=[Timer(event="rolls", remaining=2)],
        combine=TimerCombine.FIRST_TO_FIRE,
    )
    eff = _make_effect(duration=duration)
    roll_deferral.arm_effect("e1", eff)

    roll_deferral.fire_armed("e1", "on_result", "earth", {})
    assert len(applied) == 1
    assert len(roll_deferral.list_armed("e1")) == 1  # still one shot left

    roll_deferral.fire_armed("e1", "on_result", "earth", {})
    assert len(applied) == 2
    assert roll_deferral.list_armed("e1") == []  # budget exhausted


def test_nonmatching_timing_is_kept(monkeypatch):
    roll_deferral.reset()
    applied = []

    class FakeRegistry:
        def apply(self, effect, entity_id, universe, context):
            applied.append(effect)

    monkeypatch.setattr("transversal.services.effects_applier.effect_registry", FakeRegistry())

    eff = _make_effect(timing=EffectTiming.ON_RESULT)
    roll_deferral.arm_effect("e1", eff)

    # An on_set event must not fire an on_result-armed effect.
    roll_deferral.fire_armed("e1", "on_set", "earth", {})
    assert applied == []
    assert len(roll_deferral.list_armed("e1")) == 1


def test_substitutes_roll_context_at_fire_time(monkeypatch):
    roll_deferral.reset()
    applied = []

    class FakeRegistry:
        def apply(self, effect, entity_id, universe, context):
            applied.append(effect)

    monkeypatch.setattr("transversal.services.effects_applier.effect_registry", FakeRegistry())

    eff = _make_effect(result="{effect_die}")
    roll_deferral.arm_effect("e1", eff)

    roll_deferral.fire_armed("e1", "on_result", "earth", {"effect_die": "d8"})

    assert len(applied) == 1
    assert applied[0].result == "d8"


def test_clear_armed(monkeypatch):
    roll_deferral.reset()
    roll_deferral.arm_effect("e1", _make_effect())
    assert len(roll_deferral.list_armed("e1")) == 1
    roll_deferral.clear_armed("e1")
    assert roll_deferral.list_armed("e1") == []


def test_rolls_budget_defaults_to_one():
    assert roll_deferral._rolls_budget(_make_effect()) == 1
    duration = EffectDuration(
        timers=[Timer(event="rolls", remaining=4)],
        combine=TimerCombine.FIRST_TO_FIRE,
    )
    assert roll_deferral._rolls_budget(_make_effect(duration=duration)) == 4
