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

    roll_deferral.arm_sfx("e1", [_make_effect()], duration=_rolls_duration(1))
    assert len(roll_deferral.list_armed("e1")) == 1

    fired = roll_deferral.fire_armed("e1", "on_result", "earth", {"total": 5})

    assert len(fired) == 1
    assert len(applied) == 1
    assert roll_deferral.list_armed("e1") == []


def test_deferred_effects_share_output_bindings(monkeypatch):
    from transversal.domain import EffectOutput
    roll_deferral.reset()
    applied = []

    class FakeRegistry:
        def apply(self, effect, entity_id, universe, context):
            applied.append(effect)

    monkeypatch.setattr("transversal.services.effects_applier.effect_registry", FakeRegistry())

    emit = Effect(
        timing=EffectTiming.ON_RESULT, type="modify_trait", action="set", target="ts-1",
        outputs=[EffectOutput(name="complication", field="target")],
    )
    consume = Effect(
        timing=EffectTiming.ON_RESULT, type="modify_trait", action="step_down", target="{complication}",
    )

    roll_deferral.arm_sfx("e1", [emit, consume], duration=_rolls_duration(1))
    fired = roll_deferral.fire_armed("e1", "on_result", "earth", {"total": 5})

    assert [e.target for e in fired] == ["ts-1", "ts-1"]
    assert len(applied) == 2
    assert applied[1].target == "ts-1"


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


def test_none_duration_is_indefinite(monkeypatch):
    roll_deferral.reset()
    applied = []

    class FakeRegistry:
        def apply(self, effect, entity_id, universe, context):
            applied.append(effect)

    monkeypatch.setattr("transversal.services.effects_applier.effect_registry", FakeRegistry())

    roll_deferral.arm_sfx("e1", [_make_effect()], duration=None)

    roll_deferral.fire_armed("e1", "on_result", "earth", {})
    roll_deferral.fire_armed("e1", "on_result", "earth", {})
    assert len(applied) == 2
    assert len(roll_deferral.list_armed("e1")) == 1  # never expires


def test_nonmatching_timing_is_kept(monkeypatch):
    roll_deferral.reset()
    applied = []

    class FakeRegistry:
        def apply(self, effect, entity_id, universe, context):
            applied.append(effect)

    monkeypatch.setattr("transversal.services.effects_applier.effect_registry", FakeRegistry())

    roll_deferral.arm_sfx("e1", [_make_effect(timing=EffectTiming.ON_RESULT)], duration=_rolls_duration(1))

    # An on_set event must not fire (nor consume) an on_result-armed effect.
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

    roll_deferral.arm_sfx("e1", [_make_effect(result="{effect_die}")], duration=_rolls_duration(1))

    roll_deferral.fire_armed("e1", "on_result", "earth", {"effect_die": "d8"})

    assert len(applied) == 1
    assert applied[0].result == "d8"


def test_expire_armed_removes_matching_boundary():
    roll_deferral.reset()
    beat = EffectDuration(timers=[Timer(event="beat", remaining=1)], combine=TimerCombine.FIRST_TO_FIRE)
    roll_deferral.arm_sfx("e1", [_make_effect()], duration=beat)
    roll_deferral.arm_sfx("e1", [_make_effect()], duration=_rolls_duration(1))
    assert len(roll_deferral.list_armed("e1")) == 2

    roll_deferral.expire_armed("e1", "beat")
    # The beat-bound SFX is dropped; the rolls-bound one remains.
    assert len(roll_deferral.list_armed("e1")) == 1


def test_clear_armed():
    roll_deferral.reset()
    roll_deferral.arm_sfx("e1", [_make_effect()])
    assert len(roll_deferral.list_armed("e1")) == 1
    roll_deferral.clear_armed("e1")
    assert roll_deferral.list_armed("e1") == []


def test_split_duration():
    assert roll_deferral._split_duration(None) == (None, [])
    assert roll_deferral._split_duration(_rolls_duration(4)) == (4, [])
    scene = EffectDuration(timers=[Timer(event="scene", remaining=1)], combine=TimerCombine.FIRST_TO_FIRE)
    assert roll_deferral._split_duration(scene) == (None, ["scene"])
    mixed = EffectDuration(
        timers=[Timer(event="rolls", remaining=2), Timer(event="beat", remaining=1)],
        combine=TimerCombine.FIRST_TO_FIRE,
    )
    assert roll_deferral._split_duration(mixed) == (2, ["beat"])


def test_die_filter_iterates_matching_dice(monkeypatch):
    roll_deferral.reset()
    applied = []

    class FakeRegistry:
        def apply(self, effect, entity_id, universe, context):
            applied.append(effect)

    monkeypatch.setattr("transversal.services.effects_applier.effect_registry", FakeRegistry())

    roll_deferral.arm_sfx("e1", [
        _make_effect(result="{triggered_die_effect_die}", die_filter={"role": None}),
    ], duration=_rolls_duration(1))

    rolls = [
        {"die": "d8", "result": 7, "role": None, "tier": "success", "effect_die": "d6", "ts_id": "ts-x"},
        {"die": "d8", "result": 5, "role": "total", "tier": "marginal", "effect_die": "d4", "ts_id": "ts-x"},
        {"die": "d6", "result": 3, "role": None, "tier": "marginal", "effect_die": "d4", "ts_id": "ts-y"},
    ]
    fired = roll_deferral.fire_armed("e1", "on_result", "earth", {"rolls": rolls})

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
    ], duration=_rolls_duration(1))

    rolls = [
        {"die": "d8", "result": 7, "role": None, "tier": "success", "effect_die": "d6", "ts_id": "ts-crimson"},
        {"die": "d6", "result": 3, "role": None, "tier": "marginal", "effect_die": "d4", "ts_id": "ts-other"},
    ]
    fired = roll_deferral.fire_armed("e1", "on_result", "earth", {"rolls": rolls})

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
    ], duration=_rolls_duration(1))

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
    ], source_sfx_id="sfx-crimson", duration=_rolls_duration(1))

    rolls = [
        {"die": "d8", "result": 7, "role": None, "tier": "success", "effect_die": "d6", "armed_sfx_ids": ["sfx-crimson"]},
        {"die": "d6", "result": 3, "role": None, "tier": "marginal", "effect_die": "d4", "armed_sfx_ids": []},
        {"die": "d8", "result": 5, "role": "total", "tier": "marginal", "effect_die": "d4", "armed_sfx_ids": ["sfx-crimson"]},
    ]
    fired = roll_deferral.fire_armed("e1", "on_result", "earth", {"rolls": rolls})

    assert [e.result for e in fired] == ["d6"]


def test_die_context_exposes_ts_id(monkeypatch):
    roll_deferral.reset()
    applied = []

    class FakeRegistry:
        def apply(self, effect, entity_id, universe, context):
            applied.append(effect)

    monkeypatch.setattr("transversal.services.effects_applier.effect_registry", FakeRegistry())

    roll_deferral.arm_sfx("e1", [
        _make_effect(timing=EffectTiming.ON_ROLL, result="{triggered_die_ts_id}", die_filter={"role": None}),
    ], duration=_rolls_duration(1))

    rolls = [{"die": "d8", "result": 7, "role": None, "ts_id": "ts-crimson"}]
    fired = roll_deferral.fire_armed("e1", "on_roll", "earth", {"rolls": rolls})

    assert [e.result for e in fired] == ["ts-crimson"]


def test_passive_rule_applies_to_every_entity(monkeypatch):
    roll_deferral.reset()
    applied = []

    class FakeRegistry:
        def apply(self, effect, entity_id, universe, context):
            applied.append((effect, entity_id))

    monkeypatch.setattr("transversal.services.effects_applier.effect_registry", FakeRegistry())

    roll_deferral.arm_passive([
        _make_effect(timing=EffectTiming.ON_ROLL, result="{triggered_die_ts_id}", die_filter={"role": None}),
    ])

    rolls = [{"die": "d8", "result": 7, "role": None, "ts_id": "ts-a"}]
    fired = roll_deferral.fire_armed("e1", "on_roll", "earth", {"rolls": rolls})
    assert [e.result for e in fired] == ["ts-a"]

    # The same passive rule fires for a second entity that never armed anything.
    fired2 = roll_deferral.fire_armed("e2", "on_roll", "earth", {"rolls": rolls})
    assert [e.result for e in fired2] == ["ts-a"]
    assert roll_deferral.list_global_armed() != []  # never consumed


def test_expire_global_drops_matching_boundary():
    roll_deferral.reset()
    beat = EffectDuration(timers=[Timer(event="beat", remaining=1)], combine=TimerCombine.FIRST_TO_FIRE)
    roll_deferral.arm_passive([_make_effect(timing=EffectTiming.ON_ROLL)], duration=beat)
    assert len(roll_deferral.list_global_armed()) == 1
    roll_deferral.expire_global("beat")
    assert roll_deferral.list_global_armed() == []


def test_clear_global_armed():
    roll_deferral.reset()
    roll_deferral.arm_passive([_make_effect(timing=EffectTiming.ON_ROLL)])
    assert len(roll_deferral.list_global_armed()) == 1
    roll_deferral.clear_global_armed()
    assert roll_deferral.list_global_armed() == []


def test_one_trick_resolves_spec_and_fans_out(monkeypatch):
    import transversal.main as main
    from types import SimpleNamespace
    from transversal.services.target_spec import FilterStep, NavigateStep, SelectStep, TargetSpec

    roll_deferral.reset()

    ts_martial = SimpleNamespace(id="char-1:martial", trait_id="martial", entity_id="char-1")
    ts_qi = SimpleNamespace(id="char-1:qi", trait_id="qi", entity_id="char-1")
    entity = SimpleNamespace(id="char-1")
    repo = SimpleNamespace(
        get_entity=lambda eid: entity,
        get_traitsetting=lambda tsid: {"char-1:martial": ts_martial, "char-1:qi": ts_qi}.get(tsid),
    )
    monkeypatch.setattr(main, "_get_repo", lambda: repo)

    applied = []
    class FakeRegistry:
        def apply(self, effect, entity_id, universe, context):
            applied.append(effect)
    monkeypatch.setattr("transversal.services.effects_applier.effect_registry", FakeRegistry())

    spec = TargetSpec(steps=[
        SelectStep(collection="rolled_dice"),
        FilterStep(field="source_kind", value="trait"),
        NavigateStep(edge="traitsetting", dedup=True),
    ])
    effect = Effect(
        timing=EffectTiming.ON_ROLL, type="modify_trait", action="step_down",
        target_spec=spec,
    )
    roll_deferral.arm_passive([effect])

    rolls = [
        {"ts_id": "char-1:martial", "source_kind": "trait", "result": 7},
        {"ts_id": "char-1:qi", "source_kind": "trait", "result": 3},
        {"ts_id": "char-1:martial", "source_kind": "trait", "result": 5},  # dup — deduped
        {"ts_id": "char-1:other", "source_kind": "manual", "result": 6},   # filtered out
    ]
    fired = roll_deferral.fire_armed("char-1", "on_roll", "earth", {"rolls": rolls})

    # One apply per *deduped* traitsetting, in roll order.
    assert [e.target for e in applied] == ["char-1:martial", "char-1:qi"]
    assert len(applied) == 2
