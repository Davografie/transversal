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


def test_deferred_effects_share_step_output_bindings(monkeypatch):
    import transversal.main as main
    from types import SimpleNamespace
    from transversal.services.target_spec import SelectStep, TargetSpec

    roll_deferral.reset()
    entity = SimpleNamespace(id="e1")
    repo = SimpleNamespace(get_entity=lambda eid: entity)
    monkeypatch.setattr(main, "_get_repo", lambda: repo)

    applied = []
    class FakeRegistry:
        def apply(self, effect, entity_id, universe, context):
            applied.append(effect)
    monkeypatch.setattr("transversal.services.effects_applier.effect_registry", FakeRegistry())

    emit = Effect(
        timing=EffectTiming.ON_RESULT, type="modify_trait", action="set",
        target_spec=TargetSpec(steps=[SelectStep(collection="self", output="complication")]),
    )
    consume = Effect(
        timing=EffectTiming.ON_RESULT, type="modify_trait", action="step_down", target="{complication}",
    )

    roll_deferral.arm_sfx("e1", [emit, consume], source_sfx_id="sfx-heal", duration=_rolls_duration(1))
    fired = roll_deferral.fire_armed("e1", "on_result", "earth", {"total": 5})

    assert [e.target for e in fired] == ["e1", "e1"]
    assert len(applied) == 2
    assert applied[1].target == "e1"


def test_bind_activation_writes_into_armed_scope(monkeypatch):
    roll_deferral.reset()
    applied = []

    class FakeRegistry:
        def apply(self, effect, entity_id, universe, context):
            applied.append(effect)

    monkeypatch.setattr("transversal.services.effects_applier.effect_registry", FakeRegistry())

    consume = Effect(
        timing=EffectTiming.ON_RESULT, type="modify_trait", action="step_down", target="{complication}",
    )
    roll_deferral.arm_sfx("e1", [consume], source_sfx_id="sfx-heal", duration=_rolls_duration(1))

    roll_deferral.bind_activation("e1", "sfx-heal", "complication", "ts-9")

    fired = roll_deferral.fire_armed("e1", "on_result", "earth", {"total": 5})
    assert [e.target for e in fired] == ["ts-9"]
    assert applied[0].target == "ts-9"


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


def test_die_filter_iterates_even_with_a_target_path(monkeypatch):
    """The die filter decides *which* dice; the target path resolves per die.

    Before this, an effect carrying both ran once for the whole roll and its die
    filter was silently ignored.
    """
    import transversal.main as main
    from types import SimpleNamespace
    from transversal.services.target_spec import SelectStep, TargetSpec

    roll_deferral.reset()
    repo = SimpleNamespace(get_entity=lambda eid: SimpleNamespace(id=eid))
    monkeypatch.setattr(main, "_get_repo", lambda: repo)

    applied = []

    class FakeRegistry:
        def apply(self, effect, entity_id, universe, context):
            applied.append(effect)

    monkeypatch.setattr("transversal.services.effects_applier.effect_registry", FakeRegistry())

    effect = Effect(
        timing=EffectTiming.ON_RESULT, type="modify_trait", action="step_down",
        target_spec=TargetSpec(steps=[SelectStep(collection="rolled_dice")]),
        die_filter={"role": None},
    )
    roll_deferral.arm_sfx("e1", [effect], duration=_rolls_duration(1))

    rolls = [
        {"die": "d8", "result": 7, "role": None, "ts_id": "ts-a"},
        {"die": "d8", "result": 5, "role": "total", "ts_id": "ts-b"},
        {"die": "d6", "result": 3, "role": None, "ts_id": "ts-c"},
    ]
    roll_deferral.fire_armed("e1", "on_result", "earth", {"rolls": rolls})

    assert [e.target for e in applied] == ["ts-a", "ts-c"]


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


def test_armed_source_threads_into_effect_context(monkeypatch):
    """Deferred effects carry the resolved source so per-effect source_rating
    conditions evaluate against the trait that owns the SFX (not ``source=None``)."""
    import transversal.main as main
    from types import SimpleNamespace
    from transversal.domain import Condition, ConditionType, DieType

    roll_deferral.reset()
    # The source trait carries the dice the condition reads: an armed effect's own
    # conditions run at fire time, so this double has to answer them honestly.
    ts = SimpleNamespace(id="char-1:cultivation", dice=[DieType.D4])
    repo = SimpleNamespace(
        get_entity=lambda eid: SimpleNamespace(id=eid),
        get_traitsetting=lambda tid: ts if tid == ts.id else None,
    )
    monkeypatch.setattr(main, "_get_repo", lambda: repo)

    seen = {}
    class FakeRegistry:
        def apply(self, effect, entity_id, universe, context):
            seen["context"] = context
    monkeypatch.setattr("transversal.services.effects_applier.effect_registry", FakeRegistry())

    effect = Effect(
        timing=EffectTiming.ON_RESULT, type="modify_dice_limit", action="increase",
        result="1", context={"limit": "total"},
        conditions=[Condition(type=ConditionType.SOURCE_RATING, value="d4", operator="==")],
    )
    roll_deferral.arm_sfx(
        "e1", [effect],
        source_sfx_id="sfx-qi", source_kind="trait_setting", source_id=ts.id,
        duration=_rolls_duration(1),
    )
    fired = roll_deferral.fire_armed("e1", "on_result", "earth", {})

    assert len(fired) == 1
    assert seen["context"].get("_source") is ts
    assert seen["context"].get("_source_element") == "traitsetting"


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


def test_global_scope_honors_roll_budget(monkeypatch):
    """A global entry with a rolls:N duration fires N times then drops (not forever)."""
    roll_deferral.reset()
    applied = []

    class FakeRegistry:
        def apply(self, effect, entity_id, universe, context):
            applied.append((effect, entity_id))
    monkeypatch.setattr("transversal.services.effects_applier.effect_registry", FakeRegistry())

    roll_deferral.arm_passive(
        [_make_effect(timing=EffectTiming.ON_ROLL, result="d8")],
        duration=_rolls_duration(1),
    )

    # First roll fires and exhausts the one-roll budget.
    fired = roll_deferral.fire_armed("e1", "on_roll", "earth", {})
    assert len(fired) == 1
    assert roll_deferral.list_global_armed() == []  # exhausted → dropped

    # A second roll (a different entity) has nothing global left to fire.
    fired2 = roll_deferral.fire_armed("e2", "on_roll", "earth", {})
    assert fired2 == []


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


def test_arm_passive_is_idempotent_per_sfx_id():
    """A global rule arms once, however many times it is activated.

    A per-entity fan-out visits a global-scope SFX once per owning entity; each
    visit re-arming it must refresh the one entry, not stack another copy.
    """
    roll_deferral.reset()

    roll_deferral.arm_passive([_make_effect()], source_sfx_id="sfx-passive")
    roll_deferral.arm_passive([_make_effect()], source_sfx_id="sfx-passive")
    assert len(roll_deferral.list_global_armed()) == 1

    # A different SFX is a different rule.
    roll_deferral.arm_passive([_make_effect()], source_sfx_id="sfx-other")
    assert len(roll_deferral.list_global_armed()) == 2

    # Anonymous rules have no key to dedupe on, so they stay separate.
    roll_deferral.arm_passive([_make_effect()])
    roll_deferral.arm_passive([_make_effect()])
    assert len(roll_deferral.list_global_armed()) == 4

    roll_deferral.reset()


def test_arm_sfx_is_idempotent_per_sfx_id():
    """The entity-local register follows the same rule: armed is a state."""
    roll_deferral.reset()

    roll_deferral.arm_sfx("e1", [_make_effect()], source_sfx_id="sfx-local")
    roll_deferral.arm_sfx("e1", [_make_effect()], source_sfx_id="sfx-local")
    assert len(roll_deferral.list_armed("e1")) == 1

    # Another entity keeps its own copy of the same rule.
    roll_deferral.arm_sfx("e2", [_make_effect()], source_sfx_id="sfx-local")
    assert len(roll_deferral.list_armed("e1")) == 1
    assert len(roll_deferral.list_armed("e2")) == 1

    # Anonymous entries still stack (no key to dedupe on).
    roll_deferral.arm_sfx("e1", [_make_effect()])
    roll_deferral.arm_sfx("e1", [_make_effect()])
    assert len(roll_deferral.list_armed("e1")) == 3

    roll_deferral.reset()


def test_rearming_refreshes_the_roll_budget(monkeypatch):
    """Re-arming replaces the entry, so its ``rolls`` budget restarts."""
    roll_deferral.reset()
    applied = []

    class FakeRegistry:
        def apply(self, effect, entity_id, universe, context):
            applied.append(effect)

    monkeypatch.setattr("transversal.services.effects_applier.effect_registry", FakeRegistry())

    roll_deferral.arm_passive(
        [_make_effect(timing=EffectTiming.ON_ROLL)],
        source_sfx_id="sfx-passive", duration=_rolls_duration(1),
    )
    roll_deferral.fire_armed("e1", "on_roll", "earth", {})
    assert roll_deferral.list_global_armed() == []  # one-roll budget spent

    # Re-arming the same rule restores the budget instead of stacking a copy.
    roll_deferral.arm_passive(
        [_make_effect(timing=EffectTiming.ON_ROLL)],
        source_sfx_id="sfx-passive", duration=_rolls_duration(1),
    )
    assert len(roll_deferral.list_global_armed()) == 1
    fired = roll_deferral.fire_armed("e1", "on_roll", "earth", {})
    assert len(fired) == 1  # fires once, not twice

    roll_deferral.reset()


def test_die_scoped_entity_spec_reads_that_die(monkeypatch):
    """A per-die effect's ``entity_spec`` reads *that* die, not the whole roll.

    The live `sfx-crimson-scars` shape: for each unchosen die, grant a hazard to
    the location of the pool owner of that die. Two unchosen dice must mean two
    hazards — a path read against the whole roll would instead resolve the first
    die's owner twice.
    """
    import transversal.main as main
    from types import SimpleNamespace
    from transversal.services.target_spec import TargetSpec

    roll_deferral.reset()
    world = {
        "roller": SimpleNamespace(id="roller", name="Roller", current_location="loc-kael"),
        "kael": SimpleNamespace(id="kael", name="Kael", current_location="loc-kael"),
        "neya": SimpleNamespace(id="neya", name="Neya", current_location="loc-neya"),
        "loc-kael": SimpleNamespace(id="loc-kael", name="Rusted Gate", current_location=""),
        "loc-neya": SimpleNamespace(id="loc-neya", name="Salt Flats", current_location=""),
    }
    repo = SimpleNamespace(get_entity=lambda eid: world.get(eid))
    monkeypatch.setattr(main, "_get_repo", lambda: repo)

    applied = []

    class FakeRegistry:
        def apply(self, effect, entity_id, universe, context):
            applied.append(effect)

    monkeypatch.setattr("transversal.services.effects_applier.effect_registry", FakeRegistry())

    roll_deferral.arm_sfx("roller", [
        Effect(
            timing=EffectTiming.ON_RESULT, type="modify_trait", action="gain",
            target="trait-hazard", result="d6", die_filter={"role": None},
            entity_spec=TargetSpec.model_validate({"steps": [
                {"kind": "select", "collection": "rolled_dice"},
                {"kind": "navigate", "edge": "owner"},
                {"kind": "navigate", "edge": "location"},
            ]}),
        ),
    ], duration=_rolls_duration(1))

    rolls = [
        {"die": "d8", "result": 7, "role": None, "ts_id": "ts-crimson", "owner_id": "kael"},
        {"die": "d8", "result": 5, "role": None, "ts_id": "ts-crimson", "owner_id": "neya"},
        {"die": "d6", "result": 3, "role": "total", "ts_id": "ts-other", "owner_id": "kael"},
    ]
    fired = roll_deferral.fire_armed("roller", "on_result", "earth", {"rolls": rolls})

    assert [e.entity for e in fired] == ["loc-kael", "loc-neya"]
    assert len(applied) == 2


def test_armed_effect_runs_its_own_condition_at_the_roll(monkeypatch):
    """A roll-timing effect's *own* gate is evaluated when the dice land.

    Arming happens at the trigger, where there may be no roll to read at all, so
    a roll-state gate cannot live on the SFX — it belongs to the effect, and the
    effect is only applied if the path it names still matches this roll. The
    condition's named output ("the d4 traits") then drives the effect's own
    targeting path, which fans out once per trait it names — both dice from one
    trait count once.
    """
    import transversal.main as main
    from types import SimpleNamespace
    from transversal.domain import Condition, ConditionType
    from transversal.services.target_spec import (
        EvaluateStep, FilterStep, NavigateStep, SelectStep, TargetSpec,
    )

    roll_deferral.reset()
    roller = SimpleNamespace(id="e1", razmerit=0)
    traits = {
        "ts-a": SimpleNamespace(id="ts-a", entity_id="e1", rating="d4"),
        "ts-b": SimpleNamespace(id="ts-b", entity_id="e1", rating="d4"),
        "ts-c": SimpleNamespace(id="ts-c", entity_id="e1", rating="d8"),
    }

    class Repo:
        def get_entity(self, eid):
            return roller if eid == "e1" else None

        def get_traitsetting(self, tid):
            return traits.get(tid)

    monkeypatch.setattr(main, "_get_repo", lambda: Repo())

    applied = []

    class FakeRegistry:
        def apply(self, effect, entity_id, universe, context):
            applied.append(effect)

    monkeypatch.setattr("transversal.services.effects_applier.effect_registry", FakeRegistry())

    condition = Condition(type=ConditionType.TARGET_PATH, spec=TargetSpec(steps=[
        SelectStep(collection="rolled_dice"),
        FilterStep(field="rating", operator="==", value="d4"),
        NavigateStep(edge="traitsetting", dedup=True),
        FilterStep(field="rating", operator="==", value="d4", output="d4_traits"),
        EvaluateStep(field="count", operator=">=", value=1),
    ]))
    effect = Effect(
        timing=EffectTiming.ON_ROLL, type="transfer_razmerit", action="earn",
        target="self", result="1", conditions=[condition],
        target_spec=TargetSpec(steps=[SelectStep(collection="variable", variable="d4_traits")]),
    )
    roll_deferral.arm_sfx("e1", [effect])
    rolls = [
        {"rating": "d4", "ts_id": "ts-a", "role": None},
        {"rating": "d4", "ts_id": "ts-a", "role": None},  # the same trait twice
        {"rating": "d4", "ts_id": "ts-b", "role": None},
        {"rating": "d8", "ts_id": "ts-c", "role": None},
    ]

    fired = roll_deferral.fire_armed("e1", "on_roll", "earth", {"rolls": rolls})

    assert [e.target for e in fired] == ["ts-a", "ts-b"]
    assert [e.target for e in applied] == ["ts-a", "ts-b"]


def test_armed_effect_own_condition_withholds_it_when_it_does_not_match(monkeypatch):
    """No d4 trait in the roll → the gate fails and nothing is applied."""
    import transversal.main as main
    from types import SimpleNamespace
    from transversal.domain import Condition, ConditionType
    from transversal.services.target_spec import (
        EvaluateStep, FilterStep, SelectStep, TargetSpec,
    )

    roll_deferral.reset()
    roller = SimpleNamespace(id="e1", razmerit=0)
    monkeypatch.setattr(main, "_get_repo", lambda: SimpleNamespace(
        get_entity=lambda eid: roller if eid == "e1" else None))

    applied = []

    class FakeRegistry:
        def apply(self, effect, entity_id, universe, context):
            applied.append(effect)

    monkeypatch.setattr("transversal.services.effects_applier.effect_registry", FakeRegistry())

    condition = Condition(type=ConditionType.TARGET_PATH, spec=TargetSpec(steps=[
        SelectStep(collection="rolled_dice"),
        FilterStep(field="rating", operator="==", value="d4"),
        EvaluateStep(field="count", operator=">=", value=1),
    ]))
    roll_deferral.arm_sfx("e1", [Effect(
        timing=EffectTiming.ON_ROLL, type="transfer_razmerit", action="earn",
        target="self", result="1", conditions=[condition],
    )])
    rolls = [{"rating": "d8", "ts_id": "ts-c", "role": None}]

    fired = roll_deferral.fire_armed("e1", "on_roll", "earth", {"rolls": rolls})

    assert fired == []
    assert applied == []
