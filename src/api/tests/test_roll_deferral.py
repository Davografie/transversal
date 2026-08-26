"""Tests for roll-scoped SFX deferral (the "rolls" temporal spine)."""

from transversal.domain import (
    Effect,
    EffectDuration,
    EffectTiming,
    Timer,
    TimerCombine,
)
from transversal.services import roll_deferral


def _make_effect(timing=EffectTiming.ON_RESULT, target="hazard", result=None, die_filter=None):
    return Effect(
        timing=timing,
        type="modify_trait",
        action="gain",
        target=target,
        result=result,
        die_filter=die_filter or {},
    )


def _rolls_duration(n):
    return EffectDuration(
        timers=[Timer(event="rolls", remaining=n)],
        combine=TimerCombine.FIRST_TO_FIRE,
    )


def test_arm_and_fire_one_shot(monkeypatch):
    roll_deferral.reset()
    applied = []

    class FakeRegistry:
        def apply(self, effect, entity_id, universe, context):
            applied.append((effect, entity_id, universe, context))

    monkeypatch.setattr("transversal.services.effects_applier.effect_registry", FakeRegistry())

    roll_deferral.arm_sfx("e1", [_make_effect()])
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

    roll_deferral.arm_sfx("e1", [_make_effect()], duration=_rolls_duration(2))

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

    roll_deferral.arm_sfx("e1", [_make_effect(timing=EffectTiming.ON_RESULT)])

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

    roll_deferral.arm_sfx("e1", [_make_effect(result="{effect_die}")])

    roll_deferral.fire_armed("e1", "on_result", "earth", {"effect_die": "d8"})

    assert len(applied) == 1
    assert applied[0].result == "d8"


def test_clear_armed():
    roll_deferral.reset()
    roll_deferral.arm_sfx("e1", [_make_effect()])
    assert len(roll_deferral.list_armed("e1")) == 1
    roll_deferral.clear_armed("e1")
    assert roll_deferral.list_armed("e1") == []


def test_rolls_budget_defaults_to_one():
    assert roll_deferral._rolls_budget(None) == 1
    assert roll_deferral._rolls_budget(_rolls_duration(4)) == 4
    # A non-rolls duration (e.g. scene) has no roll budget → one-shot.
    scene = EffectDuration(timers=[Timer(event="scene", remaining=1)], combine=TimerCombine.FIRST_TO_FIRE)
    assert roll_deferral._rolls_budget(scene) == 1


def test_die_filter_iterates_matching_dice(monkeypatch):
    roll_deferral.reset()
    applied = []

    class FakeRegistry:
        def apply(self, effect, entity_id, universe, context):
            applied.append(effect)

    monkeypatch.setattr("transversal.services.effects_applier.effect_registry", FakeRegistry())

    roll_deferral.arm_sfx("e1", [
        _make_effect(result="{triggered_die_effect_die}", die_filter={"role": None}),
    ])

    rolls = [
        {"die": "d8", "result": 7, "role": None, "tier": "success", "effect_die": "d6", "ts_id": "ts-x"},
        {"die": "d8", "result": 5, "role": "total", "tier": "marginal", "effect_die": "d4", "ts_id": "ts-x"},
        {"die": "d6", "result": 3, "role": None, "tier": "marginal", "effect_die": "d4", "ts_id": "ts-y"},
    ]
    fired = roll_deferral.fire_armed("e1", "on_result", "earth", {"rolls": rolls})

    # Two unchosen dice match; each yields a hazard at its own tier's effect die.
    assert [e.result for e in fired] == ["d6", "d4"]
    assert len(applied) == 2
    assert roll_deferral.list_armed("e1") == []


def test_die_filter_scope_by_ts_id(monkeypatch):
    roll_deferral.reset()
    applied = []

    class FakeRegistry:
        def apply(self, effect, entity_id, universe, context):
            applied.append(effect)

    monkeypatch.setattr("transversal.services.effects_applier.effect_registry", FakeRegistry())

    roll_deferral.arm_sfx("e1", [
        _make_effect(result="{triggered_die_tier}", die_filter={"role": None, "ts_id": "ts-crimson"}),
    ])

    rolls = [
        {"die": "d8", "result": 7, "role": None, "tier": "success", "effect_die": "d6", "ts_id": "ts-crimson"},
        {"die": "d6", "result": 3, "role": None, "tier": "marginal", "effect_die": "d4", "ts_id": "ts-other"},
    ]
    fired = roll_deferral.fire_armed("e1", "on_result", "earth", {"rolls": rolls})

    # Only the ts-crimson unchosen die matches.
    assert [e.result for e in fired] == ["success"]


def test_die_filter_no_match_consumes_budget(monkeypatch):
    roll_deferral.reset()
    applied = []

    class FakeRegistry:
        def apply(self, effect, entity_id, universe, context):
            applied.append(effect)

    monkeypatch.setattr("transversal.services.effects_applier.effect_registry", FakeRegistry())

    roll_deferral.arm_sfx("e1", [
        _make_effect(die_filter={"role": None}),
    ])

    rolls = [{"die": "d8", "result": 5, "role": "total", "tier": "marginal", "effect_die": "d4", "ts_id": "ts-x"}]
    fired = roll_deferral.fire_armed("e1", "on_result", "earth", {"rolls": rolls})

    assert fired == []
    assert applied == []
    assert roll_deferral.list_armed("e1") == []  # one-shot consumed even without a match


def test_die_matches_equality_predicates():
    assert roll_deferral._die_matches({"role": None, "ts_id": "a"}, {"role": None})
    assert not roll_deferral._die_matches({"role": "total"}, {"role": None})
    assert roll_deferral._die_matches({"role": None, "ts_id": "a"}, {"role": None, "ts_id": "a"})
    assert not roll_deferral._die_matches({"role": None, "ts_id": "a"}, {"ts_id": "b"})


def test_source_sfx_id_matches_armed_dice(monkeypatch):
    roll_deferral.reset()
    applied = []

    class FakeRegistry:
        def apply(self, effect, entity_id, universe, context):
            applied.append(effect)

    monkeypatch.setattr("transversal.services.effects_applier.effect_registry", FakeRegistry())

    roll_deferral.arm_sfx("e1", [
        _make_effect(result="{triggered_die_effect_die}", die_filter={"role": None}),
    ], source_sfx_id="sfx-crimson")

    rolls = [
        {"die": "d8", "result": 7, "role": None, "tier": "success", "effect_die": "d6", "armed_sfx_ids": ["sfx-crimson"]},
        {"die": "d6", "result": 3, "role": None, "tier": "marginal", "effect_die": "d4", "armed_sfx_ids": []},
        {"die": "d8", "result": 5, "role": "total", "tier": "marginal", "effect_die": "d4", "armed_sfx_ids": ["sfx-crimson"]},
    ]
    fired = roll_deferral.fire_armed("e1", "on_result", "earth", {"rolls": rolls})

    # Only the unchosen die the client stamped with sfx-crimson matches.
    assert [e.result for e in fired] == ["d6"]
