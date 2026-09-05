"""Tests for the pure repo-first effect applier."""

from transversal.domain import (
    Condition,
    ConditionType,
    DieType,
    Effect,
    EffectTiming,
    Entity,
    EntityType,
    PendingTerm,
    Polarity,
    Projection,
    RatingType,
    TargetRef,
    TraitSetting,
    TraitSetSetting,
    TransversalType,
)
from transversal.services.effects_applier import apply_effects, resolve_choice


class FakeTrait:
    def __init__(self, trait_id, traitset_id, name=None):
        self.id = trait_id
        self.traitset_id = traitset_id
        self.name = name or trait_id
        self.universes = []


class FakeRepo:
    def __init__(self, traits=None, traitsettings=None, entities=None):
        self.traits = {t.id: t for t in (traits or [])}
        self.traitsettings = list(traitsettings or [])
        self.entities = {e.id: e for e in (entities or [])}
        self.scheduled_events = []
        self.projections = []
        self.traitsetsettings = []

    def get_trait(self, trait_id):
        return self.traits.get(trait_id)

    def get_traitset_by_id(self, traitset_id):
        return None

    def get_traitsettings_for_entity(self, entity_id):
        return [ts for ts in self.traitsettings if ts.entity_id == entity_id]

    def get_traitsetsettings_for_entity(self, entity_id):
        return [tss for tss in getattr(self, "traitsetsettings", []) if tss.entity_id == entity_id]

    def get_entity(self, entity_id):
        return self.entities.get(entity_id)

    def get_projection(self, projection_id):
        for p in self.projections:
            if p.id == projection_id:
                return p
        return None

    def get_projections_for_entity(self, entity_id):
        return [p for p in self.projections if p.entity_id == entity_id]

    def get_traitsetting(self, ts_id):
        for ts in self.traitsettings:
            if ts.id == ts_id:
                return ts
        return None

    def create_scheduled_event(self, event):
        self.scheduled_events.append(event)
        return event

    def list_all_scheduled_events(self):
        return list(self.scheduled_events)

    def update_scheduled_event(self, event):
        return event

    def delete_scheduled_event(self, event_id):
        before = len(self.scheduled_events)
        self.scheduled_events = [e for e in self.scheduled_events if e.id != event_id]
        return len(self.scheduled_events) < before


class RandomRepo:
    """Minimal repo for ``random`` target resolution — listing methods only."""

    def __init__(self, locations=None, occupants=None, traits=None, entities=None):
        self._locations = locations or []
        self._occupants = occupants or []
        self._traits = traits or []
        self._entities = entities or []

    def _entity(self, id, entity_type):
        return Entity(id=id, type=entity_type, name=id, current_universe="earth")

    def list_entities_by_type(self, entity_type, universe=None):
        if entity_type == EntityType.LOCATION:
            return [self._entity(l, EntityType.LOCATION) for l in self._locations]
        return []

    def list_entities_by_location(self, location_id):
        return [self._entity(o, EntityType.GMC) for o in self._occupants]

    def list_all_entities(self, universe=None):
        return [self._entity(e, EntityType.GMC) for e in self._entities]

    def get_traits_by_universe(self, universe):
        return self._traits

    def get_trait(self, trait_id):
        for t in self._traits:
            if t.id == trait_id:
                return t
        return None

    def get_traitsettings_for_entity(self, entity_id):
        return []


def _entity(**overrides):
    kwargs = dict(id="char-1", type=EntityType.CHARACTER, name="Test", current_universe="earth")
    kwargs.update(overrides)
    return Entity(**kwargs)


def _effect(type, action, target="", result=None):
    return Effect(timing=EffectTiming.IMMEDIATE, type=type, action=action, target=target, result=result)


def _ts(trait_id, dice, entity_id="char-1", traitset_id="ts-x", **overrides):
    kwargs = dict(
        id=f"{entity_id}:{trait_id}",
        entity_id=entity_id,
        trait_id=trait_id,
        traitset_id=traitset_id,
        dice=dice,
    )
    kwargs.update(overrides)
    return TraitSetting(**kwargs)


# ── Trait gain ───────────────────────────────────────

def test_gain_creates_traitsetting():
    repo = FakeRepo(traits=[FakeTrait("iron-will", "ts-distinctions")])
    entity = _entity()
    result = apply_effects(entity, [_effect("modify_trait", "gain", "iron-will", "d6")], repo)
    assert len(result.new_trait_settings) == 1
    ts = result.new_trait_settings[0]
    assert ts.trait_id == "iron-will"
    assert ts.traitset_id == "ts-distinctions"
    assert ts.dice == [DieType.D6]
    assert ts.polarity == Polarity.POSITIVE
    assert result.applied[0].summary == "gained iron-will at d6"


def test_gain_sets_statement_and_notes_from_context():
    repo = FakeRepo(traits=[FakeTrait("hazard", "ts-complications")])
    entity = _entity()
    effect = Effect(
        timing=EffectTiming.IMMEDIATE, type="modify_trait", action="gain",
        target="hazard", result="d6", negative=True,
        context={"statement": "Crimson Scar", "notes": "Blood-red glowing scars…"},
    )
    result = apply_effects(entity, [effect], repo)
    ts = result.new_trait_settings[0]
    assert ts.polarity == Polarity.NEGATIVE
    assert ts.statement == "Crimson Scar"
    assert ts.notes == "Blood-red glowing scars…"


def test_gain_sets_rating_type_from_context():
    repo = FakeRepo(traits=[FakeTrait("hazard", "ts-complications")])
    entity = _entity()
    effect = Effect(
        timing=EffectTiming.IMMEDIATE, type="modify_trait", action="gain",
        target="hazard", result="d6",
        context={"rating_type": "resource"},
    )
    result = apply_effects(entity, [effect], repo)
    ts = result.new_trait_settings[0]
    assert ts.rating_type == RatingType.RESOURCE


def test_gain_noop_when_present():
    repo = FakeRepo(traitsettings=[_ts("iron-will", [DieType.D6])])
    entity = _entity()
    result = apply_effects(entity, [_effect("modify_trait", "gain", "iron-will", "d8")], repo)
    assert len(result.new_trait_settings) == 0
    assert result.applied[0].summary == "trait iron-will already present"


# ── gain_or_step_up ──────────────────────────────────

def test_gain_or_step_up_creates_when_absent():
    repo = FakeRepo(traits=[FakeTrait("medicine", "ts-skills")])
    entity = _entity()
    result = apply_effects(entity, [_effect("modify_trait", "gain_or_step_up", "medicine", "d4")], repo)
    assert len(result.new_trait_settings) == 1
    assert result.new_trait_settings[0].dice == [DieType.D4]


def test_gain_or_step_up_steps_up_when_present():
    repo = FakeRepo(traitsettings=[_ts("medicine", [DieType.D6])])
    entity = _entity()
    result = apply_effects(entity, [_effect("modify_trait", "gain_or_step_up", "medicine", "d4")], repo)
    assert len(result.updated_trait_settings) == 1
    assert result.updated_trait_settings[0].dice == [DieType.D8]
    assert len(result.new_trait_settings) == 0


def test_gain_or_step_up_caps_at_d12():
    repo = FakeRepo(traitsettings=[_ts("medicine", [DieType.D12])])
    entity = _entity()
    result = apply_effects(entity, [_effect("modify_trait", "gain_or_step_up", "medicine", "d4")], repo)
    assert len(result.updated_trait_settings) == 0
    assert result.applied[0].summary == "medicine already at d12"


# ── step up / down / set ─────────────────────────────

def test_step_up_steps_smallest_die():
    repo = FakeRepo(traitsettings=[_ts("pool", [DieType.D8, DieType.D6])])
    entity = _entity()
    result = apply_effects(entity, [_effect("modify_trait", "step_up", "pool")], repo)
    assert result.updated_trait_settings[0].dice == [DieType.D8, DieType.D8]


def test_add_die_appends_to_rating():
    repo = FakeRepo(traitsettings=[_ts("pool", [DieType.D8])])
    entity = _entity()
    result = apply_effects(entity, [_effect("modify_trait", "add_die", "pool", "d6")], repo)
    assert result.updated_trait_settings[0].dice == [DieType.D8, DieType.D6]


def test_add_die_works_on_challenge_rating():
    repo = FakeRepo(traitsettings=[_ts("pool", [DieType.D8], rating_type=RatingType.CHALLENGE)])
    entity = _entity()
    result = apply_effects(entity, [_effect("modify_trait", "add_die", "pool", "d6")], repo)
    assert result.updated_trait_settings[0].dice == [DieType.D8, DieType.D6]


def test_remove_die_removes_matching_die():
    repo = FakeRepo(traitsettings=[_ts("pool", [DieType.D8, DieType.D6])])
    entity = _entity()
    result = apply_effects(entity, [_effect("modify_trait", "remove_die", "pool", "d6")], repo)
    assert result.updated_trait_settings[0].dice == [DieType.D8]


def test_step_down_empties_at_d4():
    repo = FakeRepo(traitsettings=[_ts("pool", [DieType.D4])])
    entity = _entity()
    result = apply_effects(entity, [_effect("modify_trait", "step_down", "pool")], repo)
    assert len(result.updated_trait_settings) == 1
    assert result.updated_trait_settings[0].dice == []
    assert len(result.removed_trait_settings) == 0
    assert result.applied[0].summary == "stepped down pool"


def test_step_down_targets_traitsetting_instance_by_id():
    # The die→traitsetting drillthrough yields a full instance id, not a registry
    # trait id. step_down must resolve it directly (ts_id) rather than via the
    # owner + trait_id lookup (which would never match "char-1:pool").
    repo = FakeRepo(traitsettings=[_ts("pool", [DieType.D8])])
    entity = _entity()
    effect = _effect("modify_trait", "step_down", "char-1:pool")
    result = apply_effects(entity, [effect], repo)
    assert len(result.updated_trait_settings) == 1
    assert result.updated_trait_settings[0].dice == [DieType.D6]


def test_step_up_targets_traitsetting_instance_by_id():
    repo = FakeRepo(traitsettings=[_ts("pool", [DieType.D6])])
    entity = _entity()
    effect = _effect("modify_trait", "step_up", "char-1:pool")
    result = apply_effects(entity, [effect], repo)
    assert result.updated_trait_settings[0].dice == [DieType.D8]


def test_step_up_multiple_steps():
    repo = FakeRepo(traitsettings=[_ts("pool", [DieType.D6])])
    entity = _entity()
    effect = Effect(timing=EffectTiming.IMMEDIATE, type="modify_trait", action="step_up",
                    target="pool", context={"steps": 2})
    result = apply_effects(entity, [effect], repo)
    assert result.updated_trait_settings[0].dice == [DieType.D10]


def test_step_up_restores_empty_rating():
    repo = FakeRepo(traitsettings=[_ts("pool", [])])
    entity = _entity()
    result = apply_effects(entity, [_effect("modify_trait", "step_up", "pool")], repo)
    assert len(result.updated_trait_settings) == 1
    assert result.updated_trait_settings[0].dice == [DieType.D4]


def test_step_down_multiple_steps_empties():
    repo = FakeRepo(traitsettings=[_ts("pool", [DieType.D6])])
    entity = _entity()
    effect = Effect(timing=EffectTiming.IMMEDIATE, type="modify_trait", action="step_down",
                    target="pool", context={"steps": 2})
    result = apply_effects(entity, [effect], repo)
    assert len(result.updated_trait_settings) == 1
    assert result.updated_trait_settings[0].dice == []
    assert len(result.removed_trait_settings) == 0


def test_reduce_by_effect_die_removes_when_larger():
    repo = FakeRepo(traitsettings=[_ts("scar", [DieType.D6])])
    entity = _entity()
    effect = Effect(timing=EffectTiming.IMMEDIATE, type="modify_trait", action="reduce_by_effect",
                    target="char-1:scar", context={"effect_die": "d8"})
    result = apply_effects(entity, [effect], repo)
    assert len(result.removed_trait_settings) == 1
    assert len(result.updated_trait_settings) == 0


def test_reduce_by_effect_die_steps_down_when_smaller():
    repo = FakeRepo(traitsettings=[_ts("scar", [DieType.D6])])
    entity = _entity()
    effect = Effect(timing=EffectTiming.IMMEDIATE, type="modify_trait", action="reduce_by_effect",
                    target="char-1:scar", context={"effect_die": "d4"})
    result = apply_effects(entity, [effect], repo)
    assert len(result.updated_trait_settings) == 1
    assert result.updated_trait_settings[0].dice == [DieType.D4]
    assert len(result.removed_trait_settings) == 0


def test_set_overrides_dice():
    repo = FakeRepo(traitsettings=[_ts("trait", [DieType.D6])])
    entity = _entity()
    result = apply_effects(entity, [_effect("modify_trait", "set", "trait", "d10")], repo)
    assert result.updated_trait_settings[0].dice == [DieType.D10]


def test_disable_sets_enabled_false():
    repo = FakeRepo(traitsettings=[_ts("trait", [DieType.D6])])
    entity = _entity()
    result = apply_effects(entity, [_effect("modify_trait", "disable", "trait")], repo)
    assert result.updated_trait_settings[0].enabled is False
    assert result.updated_trait_settings[0].dice == [DieType.D6]  # rating untouched


def test_disable_noop_when_already_disabled():
    repo = FakeRepo(traitsettings=[_ts("trait", [DieType.D6], enabled=False)])
    entity = _entity()
    result = apply_effects(entity, [_effect("modify_trait", "disable", "trait")], repo)
    assert result.updated_trait_settings == []


def test_enable_sets_enabled_true():
    repo = FakeRepo(traitsettings=[_ts("trait", [DieType.D6], enabled=False)])
    entity = _entity()
    result = apply_effects(entity, [_effect("modify_trait", "enable", "trait")], repo)
    assert result.updated_trait_settings[0].enabled is True


def test_toggle_flips_enabled():
    repo = FakeRepo(traitsettings=[_ts("trait", [DieType.D6])])
    entity = _entity()
    result = apply_effects(entity, [_effect("modify_trait", "toggle", "trait")], repo)
    assert result.updated_trait_settings[0].enabled is False

    # toggling again flips back
    repo2 = FakeRepo(traitsettings=[_ts("trait", [DieType.D6], enabled=False)])
    result2 = apply_effects(_entity(), [_effect("modify_trait", "toggle", "trait")], repo2)
    assert result2.updated_trait_settings[0].enabled is True


def test_disable_with_duration_schedules_enable_revert():
    from transversal.domain import EffectDuration, Timer, TimerCombine
    repo = FakeRepo(traitsettings=[_ts("trait", [DieType.D6])])
    entity = _entity()
    effect = Effect(
        timing=EffectTiming.IMMEDIATE, type="modify_trait", action="disable", target="trait",
        duration=EffectDuration(timers=[Timer(event="scene", remaining=1)], combine=TimerCombine.FIRST_TO_FIRE),
    )
    result = apply_effects(entity, [effect], repo)
    assert result.updated_trait_settings[0].enabled is False
    assert len(repo.scheduled_events) == 1
    revert = repo.scheduled_events[0]
    assert revert.target_type == "trait_setting"
    assert revert.target_id == "char-1:trait"
    assert revert.effect.action == "enable"


def test_cancel_scheduled_event_deletes_timer():
    from transversal.domain import ScheduledEvent, Timer, TimerCombine
    ev = ScheduledEvent(
        id="se-1", target_type="entity", target_id="char-1",
        effect=Effect(type="modify_trait", action="enable", target="iron-will"),
        timers=[Timer(event="scene", remaining=2)],
        combine=TimerCombine.FIRST_TO_FIRE,
    )
    repo = FakeRepo()
    repo.scheduled_events = [ev]
    result = apply_effects(_entity(), [_effect("entity", "cancel_scheduled_event", "se-1")], repo)
    assert repo.scheduled_events == []
    assert result.applied


def test_cancel_scheduled_event_missing_is_noop():
    repo = FakeRepo()
    repo.scheduled_events = []
    result = apply_effects(_entity(), [_effect("entity", "cancel_scheduled_event", "se-nope")], repo)
    assert result.applied and "no active effect" in result.applied[0].summary


def test_core_handlers_register_disable_enable_toggle():
    """Duration reverts fire via effect_registry — the disable/toggle actions
    must be registered on the global registry, not just _MUTATION_HANDLERS."""
    from types import SimpleNamespace
    import transversal.services.effects_applier as applier
    from transversal.services.effects_applier import EffectRegistry

    original = applier.effect_registry
    applier.effect_registry = EffectRegistry()
    try:
        raz = SimpleNamespace(spend=lambda *a, **k: None, earn=lambda *a, **k: None, transfer=lambda *a, **k: None)
        em = SimpleNamespace(repo=None, create=lambda *a, **k: None)
        applier._register_core_handlers(em, raz)
        for action in ("disable", "enable", "toggle"):
            assert ("modify_trait", action) in applier.effect_registry._handlers
    finally:
        applier.effect_registry = original


def test_attune_targets_the_chosen_entity():
    """Attune resolves ``target`` to the attuned entity (not the wielder)."""
    from types import SimpleNamespace
    import transversal.services.effects_applier as applier
    from transversal.services.effects_applier import EffectRegistry

    class Repo:
        def __init__(self):
            self.entities = {
                "wielder": SimpleNamespace(id="wielder", attunements=[]),
                "target": SimpleNamespace(id="target", attunements=[]),
            }
        def get_entity(self, eid):
            return self.entities.get(eid)
        def update_entity(self, e):
            self.entities[e.id] = e

    repo = Repo()
    original = applier.effect_registry
    applier.effect_registry = EffectRegistry()
    try:
        raz = SimpleNamespace(spend=lambda *a, **k: None, earn=lambda *a, **k: None, transfer=lambda *a, **k: None)
        em = SimpleNamespace(repo=repo, create=lambda *a, **k: None)
        applier._register_core_handlers(em, raz)
        eff = Effect(timing=EffectTiming.IMMEDIATE, type="attune", action="enable", target="target", result="three_realms")
        applier.effect_registry.apply(eff, "wielder", "earth", {})
    finally:
        applier.effect_registry = original

    assert [a.universe for a in repo.entities["target"].attunements] == ["three_realms"]
    assert repo.entities["wielder"].attunements == []


def test_create_projection_activates_new_body_and_schedules_restore():
    from transversal.domain import EffectDuration, Timer, TimerCombine
    prior = Projection(id="char-1:earth", entity_id="char-1", universe="earth", current_location="loc-1")
    repo = FakeRepo()
    repo.projections = [prior]
    entity = _entity(current_projection="char-1:earth", current_universe="earth", current_location="loc-1")
    effect = Effect(
        timing=EffectTiming.IMMEDIATE, type="projection", action="create", target="phantom",
        duration=EffectDuration(timers=[Timer(event="scene", remaining=1)], combine=TimerCombine.FIRST_TO_FIRE),
    )
    result = apply_effects(entity, [effect], repo)
    assert len(result.new_projections) == 1
    disguise = result.new_projections[0]
    assert entity.current_projection == disguise.id
    assert disguise.universe == "earth"
    assert disguise.current_location == "loc-1"
    assert len(repo.scheduled_events) == 1
    revert = repo.scheduled_events[0]
    assert revert.effect.action == "restore"
    assert revert.effect.result == "char-1:earth"


def test_restore_projection_reactivates_prior_and_removes_disguise():
    prior = Projection(id="char-1:earth", entity_id="char-1", universe="earth", current_location="loc-1")
    disguise = Projection(id="char-1:earth:2", entity_id="char-1", universe="earth", current_location="loc-2")
    repo = FakeRepo()
    repo.projections = [prior, disguise]
    entity = _entity(current_projection="char-1:earth:2", current_universe="earth", current_location="loc-2")
    effect = Effect(timing=EffectTiming.IMMEDIATE, type="projection", action="restore", result="char-1:earth")
    result = apply_effects(entity, [effect], repo)
    assert entity.current_projection == "char-1:earth"
    assert [p.id for p in result.removed_projections] == ["char-1:earth:2"]
    assert prior.current_location == "loc-2"  # prior body imported to current location


def test_set_traitset_limit_creates_override_and_schedules_revert():
    from transversal.domain import EffectDuration, Timer, TimerCombine
    repo = FakeRepo()
    entity = _entity()
    effect = Effect(
        timing=EffectTiming.IMMEDIATE, type="modify_traitset", action="set_limit",
        target="ts-distinctions", result="2",
        duration=EffectDuration(timers=[Timer(event="scene", remaining=1)], combine=TimerCombine.FIRST_TO_FIRE),
    )
    result = apply_effects(entity, [effect], repo)
    assert len(result.new_traitsetsettings) == 1
    tss = result.new_traitsetsettings[0]
    assert tss.limit == 2
    assert tss.traitset_id == "ts-distinctions"
    assert len(repo.scheduled_events) == 1
    assert repo.scheduled_events[0].effect.action == "set_limit"
    assert repo.scheduled_events[0].effect.result == ""  # no prior → clear


def test_set_traitset_limit_updates_and_restores_prior():
    from transversal.domain import EffectDuration, Timer, TimerCombine
    tss = TraitSetSetting(
        id="char-1:ts-distinctions", entity_id="char-1", traitset_id="ts-distinctions",
        from_type="entity", limit=1,
    )
    repo = FakeRepo()
    repo.traitsetsettings = [tss]
    entity = _entity()
    effect = Effect(
        timing=EffectTiming.IMMEDIATE, type="modify_traitset", action="set_limit",
        target="ts-distinctions", result="3",
        duration=EffectDuration(timers=[Timer(event="scene", remaining=1)], combine=TimerCombine.FIRST_TO_FIRE),
    )
    result = apply_effects(entity, [effect], repo)
    assert result.updated_traitsetsettings[0].limit == 3
    assert repo.scheduled_events[0].effect.result == "1"  # prior limit restored


# ── Dice-limit modifiers ────────────────────────────

def test_increase_dice_limit_total_schedules_inverse():
    from transversal.domain import EffectDuration, Timer, TimerCombine
    repo = FakeRepo()
    entity = _entity()
    effect = Effect(
        timing=EffectTiming.IMMEDIATE, type="modify_dice_limit", action="increase",
        result="1", context={"limit": "total"},
        duration=EffectDuration(timers=[Timer(event="scene", remaining=1)], combine=TimerCombine.FIRST_TO_FIRE),
    )
    result = apply_effects(entity, [effect], repo)
    assert entity.total_dice_bonus == 1
    assert entity.effect_dice_bonus == 0
    assert len(result.applied) == 1
    assert len(repo.scheduled_events) == 1
    revert = repo.scheduled_events[0].effect
    assert revert.action == "decrease"
    assert revert.result == "1"
    assert revert.context == {"limit": "total"}


def test_decrease_dice_limit_effect_schedules_inverse():
    from transversal.domain import EffectDuration, Timer, TimerCombine
    repo = FakeRepo()
    entity = _entity()
    effect = Effect(
        timing=EffectTiming.IMMEDIATE, type="modify_dice_limit", action="decrease",
        result="2", context={"limit": "effect"},
        duration=EffectDuration(timers=[Timer(event="beat", remaining=1)], combine=TimerCombine.FIRST_TO_FIRE),
    )
    apply_effects(entity, [effect], repo)
    assert entity.total_dice_bonus == 0
    assert entity.effect_dice_bonus == -2
    revert = repo.scheduled_events[0].effect
    assert revert.action == "increase"
    assert revert.result == "2"
    assert revert.context == {"limit": "effect"}


def test_dice_limit_without_duration_is_permanent():
    repo = FakeRepo()
    entity = _entity()
    effect = Effect(
        timing=EffectTiming.IMMEDIATE, type="modify_dice_limit", action="increase",
        result="1", context={"limit": "total"},
    )
    apply_effects(entity, [effect], repo)
    assert entity.total_dice_bonus == 1
    assert repo.scheduled_events == []  # no duration → no revert


# ── Dice-pool mutation (add_dice) ────────────────────

def test_resolve_pool_targets():
    from transversal.services.effects_applier import _resolve_pool

    entity = _entity(current_location="loc-1")
    repo = FakeRepo(entities=[entity])
    assert _resolve_pool("difficulty:loc-1", entity, repo) == ("loc-1", "loc-1")
    assert _resolve_pool("pool:char-1", entity, repo) == ("loc-1", "char-1")

    loc = Entity(id="loc-1", type=EntityType.LOCATION, name="loc", current_universe="earth")
    repo2 = FakeRepo(entities=[entity, loc])
    assert _resolve_pool("loc-1", entity, repo2) == ("loc-1", "loc-1")  # bare location → difficulty
    assert _resolve_pool("nope", entity, repo2) == ("", "")


def test_add_dice_to_difficulty_pool():
    from transversal.services.scene_state import get_scene_store

    store = get_scene_store()
    store.clear_all()
    store.save_pool("loc-1", "loc-1", [])

    repo = FakeRepo()
    entity = _entity()
    effect = Effect(
        timing=EffectTiming.IMMEDIATE, type="modify_pool", action="add_dice",
        target="difficulty:loc-1", context={"dice": ["d8", "d8"]},
    )
    result = apply_effects(entity, [effect], repo)
    assert len(result.applied) == 1
    pool = store.get_pool("loc-1", "loc-1")
    assert [d["die"] for d in pool] == ["d8", "d8"]
    assert all(d["source_kind"] == "sfx" for d in pool)
    store.clear_all()


def test_add_dice_no_dice_is_noop():
    repo = FakeRepo()
    entity = _entity()
    effect = Effect(
        timing=EffectTiming.IMMEDIATE, type="modify_pool", action="add_dice",
        target="difficulty:loc-1", context={},
    )
    result = apply_effects(entity, [effect], repo)
    assert result.applied[0].summary == "no dice to add"


def test_roll_pool_rolls_difficulty_pool():
    from transversal.services.scene_state import get_scene_store

    store = get_scene_store()
    store.clear_all()
    store.save_pool("loc-1", "loc-1", [
        {"die": "d8", "source_kind": "trait", "source_id": "", "label": "complication", "ts_id": None},
        {"die": "d6", "source_kind": "trait", "source_id": "", "label": "base", "ts_id": None},
    ])

    repo = FakeRepo()
    entity = _entity()
    effect = Effect(
        timing=EffectTiming.IMMEDIATE, type="modify_pool", action="roll",
        refs={"pool": TargetRef(value="difficulty:loc-1")},
    )
    result = apply_effects(entity, [effect], repo)
    assert len(result.applied) == 1
    pool = store.get_pool("loc-1", "loc-1")
    assert len(pool) == 2
    assert all(d.get("result") is not None for d in pool)
    assert all(1 <= d["result"] <= 8 for d in pool)
    store.clear_all()


def test_roll_pool_empty_or_missing_target_is_noop():
    from transversal.services.scene_state import get_scene_store

    store = get_scene_store()
    store.clear_all()
    store.save_pool("loc-1", "loc-1", [])

    repo = FakeRepo()
    entity = _entity()
    # Empty pool → no-op summary.
    empty = Effect(timing=EffectTiming.IMMEDIATE, type="modify_pool", action="roll",
                   refs={"pool": TargetRef(value="difficulty:loc-1")})
    r1 = apply_effects(entity, [empty], repo)
    assert r1.applied[0].summary == "pool loc-1 is empty"
    # Missing target → no-op summary (pool:<entity> with an unknown entity).
    missing = Effect(timing=EffectTiming.IMMEDIATE, type="modify_pool", action="roll",
                     refs={"pool": TargetRef(value="pool:char-1")})
    r2 = apply_effects(entity, [missing], repo)
    assert r2.applied[0].summary == "pool target not found: pool:char-1"
    store.clear_all()


def test_add_trait_rating_dice_to_difficulty_pool():
    from transversal.services.scene_state import get_scene_store

    store = get_scene_store()
    store.clear_all()
    store.save_pool("loc-1", "loc-1", [])

    ts = _ts("trait-scar", [DieType.D8, DieType.D6])
    repo = FakeRepo(
        traits=[FakeTrait("trait-scar", "ts-complications", name="Scar")],
        traitsettings=[ts],
    )
    entity = _entity(current_location="loc-1")
    effect = Effect(
        timing=EffectTiming.IMMEDIATE, type="modify_pool", action="add_trait_rating",
        refs={
            "trait": TargetRef(value="char-1:trait-scar"),
            "pool": TargetRef(value="difficulty:loc-1"),
        },
    )
    result = apply_effects(entity, [effect], repo)
    assert len(result.applied) == 1
    pool = store.get_pool("loc-1", "loc-1")
    assert [d["die"] for d in pool] == ["d8", "d6"]
    assert all(d["source_kind"] == "trait" for d in pool)
    assert all(d["ts_id"] == "char-1:trait-scar" for d in pool)
    store.clear_all()


def test_add_trait_rating_dice_targets_an_entity_pool():
    from transversal.services.scene_state import get_scene_store

    store = get_scene_store()
    store.clear_all()
    store.save_pool("loc-1", "char-1", [])

    ts = _ts("trait-scar", [DieType.D8])
    repo = FakeRepo(
        traits=[FakeTrait("trait-scar", "ts-complications", name="Scar")],
        traitsettings=[ts],
        entities=[Entity(id="char-1", type=EntityType.CHARACTER, name="hero", current_universe="earth", current_location="loc-1")],
    )
    entity = _entity(current_location="loc-1")
    effect = Effect(
        timing=EffectTiming.IMMEDIATE, type="modify_pool", action="add_trait_rating",
        refs={
            "trait": TargetRef(value="char-1:trait-scar"),
            "pool": TargetRef(value="pool:char-1"),
        },
    )
    result = apply_effects(entity, [effect], repo)
    assert len(result.applied) == 1
    pool = store.get_pool("loc-1", "char-1")
    assert [d["die"] for d in pool] == ["d8"]
    store.clear_all()


def test_effect_conditions_gate_application():
    repo = FakeRepo(traits=[FakeTrait("scar", "ts-complications")])
    entity = _entity()
    effect = Effect(
        timing=EffectTiming.IMMEDIATE, type="modify_trait", action="gain",
        target="scar", result="d4",
        conditions=[Condition(type=ConditionType.CONTEST_OUTCOME, target="player")],
    )
    # No contest_winner in context -> condition fails -> effect skipped.
    assert len(apply_effects(entity, [effect], repo, context={}).applied) == 0
    # Won the contest -> applies.
    assert len(apply_effects(entity, [effect], repo, context={"contest_winner": "player"}).applied) == 1
    # Lost -> skipped.
    assert len(apply_effects(entity, [effect], repo, context={"contest_winner": "opponent"}).applied) == 0


# ── Complications (unified polarity) ─────────────────

def test_gain_negative_sets_negative():
    repo = FakeRepo(traits=[FakeTrait("scar", "ts-complications")])
    entity = _entity()
    effect = Effect(timing=EffectTiming.IMMEDIATE, type="modify_trait", action="gain",
                    target="scar", result="d4", negative=True)
    result = apply_effects(entity, [effect], repo)
    ts = result.new_trait_settings[0]
    assert ts.polarity == Polarity.NEGATIVE
    assert ts.traitset_id == "ts-complications"


def test_gain_or_step_up_negative_creates_when_absent():
    repo = FakeRepo(traits=[FakeTrait("scar", "ts-complications")])
    entity = _entity()
    effect = Effect(timing=EffectTiming.IMMEDIATE, type="modify_trait", action="gain_or_step_up",
                    target="scar", result="d4", negative=True)
    result = apply_effects(entity, [effect], repo)
    assert len(result.new_trait_settings) == 1
    ts = result.new_trait_settings[0]
    assert ts.polarity == Polarity.NEGATIVE
    assert ts.dice == [DieType.D4]


def test_gain_or_step_up_negative_steps_up_when_present():
    repo = FakeRepo(traitsettings=[_ts("scar", [DieType.D4], traitset_id="ts-complications", negative=True)])
    entity = _entity()
    effect = Effect(timing=EffectTiming.IMMEDIATE, type="modify_trait", action="gain_or_step_up",
                    target="scar", result="d4", negative=True)
    result = apply_effects(entity, [effect], repo)
    assert len(result.new_trait_settings) == 0
    assert len(result.updated_trait_settings) == 1
    assert result.updated_trait_settings[0].dice == [DieType.D6]


def test_gain_or_step_up_with_steps_creates_base_plus_steps():
    repo = FakeRepo(traits=[FakeTrait("scar", "ts-complications")])
    entity = _entity()
    effect = Effect(timing=EffectTiming.IMMEDIATE, type="modify_trait", action="gain_or_step_up",
                    target="scar", result="d4", negative=True, context={"steps": 2})
    result = apply_effects(entity, [effect], repo)
    assert len(result.new_trait_settings) == 1
    assert result.new_trait_settings[0].dice == [DieType.D8]


def test_gain_or_step_up_with_steps_steps_up_existing():
    repo = FakeRepo(traitsettings=[_ts("scar", [DieType.D6], traitset_id="ts-complications", negative=True)])
    entity = _entity()
    effect = Effect(timing=EffectTiming.IMMEDIATE, type="modify_trait", action="gain_or_step_up",
                    target="scar", result="d4", negative=True, context={"steps": 2})
    result = apply_effects(entity, [effect], repo)
    assert len(result.new_trait_settings) == 0
    assert len(result.updated_trait_settings) == 1
    assert result.updated_trait_settings[0].dice == [DieType.D10]


# ── Razmerit ─────────────────────────────────────────

def test_earn_razmerit():
    entity = _entity(razmerit=3)
    apply_effects(entity, [_effect("transfer_razmerit", "earn", "self", "5")], FakeRepo())
    assert entity.razmerit == 8


def test_spend_razmerit():
    entity = _entity(razmerit=10)
    apply_effects(entity, [_effect("transfer_razmerit", "spend", "self", "4")], FakeRepo())
    assert entity.razmerit == 6


def test_transfer_razmerit():
    recipient = _entity(id="char-2")
    repo = FakeRepo(entities=[recipient])
    entity = _entity(razmerit=10)
    result = apply_effects(entity, [_effect("transfer_razmerit", "transfer", "char-2", "3")], repo)
    assert entity.razmerit == 7
    assert recipient.razmerit == 3
    assert result.entities_to_update == [recipient]


# ── Rank / flow ──────────────────────────────────────

def test_rank_set_is_passthrough():
    """rank/set was removed — rank is a relationship trait, not an entity field."""
    entity = _entity()
    result = apply_effects(entity, [_effect("rank", "set", "lp-x", "3")], FakeRepo())
    assert len(result.passthrough) == 1


def test_discover_appends():
    entity = _entity(discovered_life_paths=["lp-a"])
    apply_effects(entity, [_effect("life_path", "discover", "lp-b")], FakeRepo())
    assert entity.discovered_life_paths == ["lp-a", "lp-b"]


def test_discover_idempotent():
    entity = _entity(discovered_life_paths=["lp-a"])
    result = apply_effects(entity, [_effect("life_path", "discover", "lp-a")], FakeRepo())
    assert entity.discovered_life_paths == ["lp-a"]
    assert result.applied[0].summary == "life path lp-a already discovered"


# ── Relationships ────────────────────────────────────

def test_relationship_create():
    entity = _entity()
    effect = Effect(
        timing=EffectTiming.IMMEDIATE, type="relationship", action="create",
        target="char-2", result="ally", context={"description": "old friend"},
    )
    result = apply_effects(entity, [effect], FakeRepo())
    assert result.new_relationships == [
        {"from": "char-1", "to": "char-2", "type": "ally", "description": "old friend"}
    ]


# ── Pending choices and passthrough ──────────────────

def test_unresolved_target_becomes_pending():
    entity = _entity()
    result = apply_effects(entity, [_effect("modify_trait", "gain", "{choose_trait}", "d6")], FakeRepo())
    assert len(result.pending_choices) == 1
    assert result.pending_choices[0].kind == "trait"
    assert len(result.new_trait_settings) == 0


def test_empty_required_target_becomes_pending():
    entity = _entity()
    result = apply_effects(entity, [_effect("modify_trait", "gain", "", "d6")], FakeRepo())
    assert len(result.pending_choices) == 1
    assert result.pending_choices[0].kind == "trait"


def test_choose_location_yields_location_kind():
    entity = _entity()
    effect = Effect(
        timing=EffectTiming.IMMEDIATE, type="relationship", action="create",
        target="{choose_location}", result="linked",
    )
    result = apply_effects(entity, [effect], FakeRepo())
    assert len(result.pending_choices) == 1
    assert result.pending_choices[0].kind == "location"


def test_choose_occupant_yields_occupant_kind():
    entity = _entity()
    effect = Effect(
        timing=EffectTiming.IMMEDIATE, type="relationship", action="create",
        target="{choose_occupant}", result="ally",
    )
    result = apply_effects(entity, [effect], FakeRepo())
    assert result.pending_choices[0].kind == "occupant"


def test_choose_rating_die_yields_rating_die_kind():
    entity = _entity()
    effect = Effect(
        timing=EffectTiming.IMMEDIATE, type="modify_trait", action="step_down",
        target="{choose_rating_die}",
    )
    result = apply_effects(entity, [effect], FakeRepo())
    assert result.pending_choices[0].kind == "rating_die"


def test_target_scope_populates_pending_choice_scope():
    entity = _entity()
    effect = Effect(
        timing=EffectTiming.IMMEDIATE, type="modify_trait", action="gain",
        target="{choose_trait}", result="d6", target_scope="earth",
    )
    result = apply_effects(entity, [effect], FakeRepo())
    assert len(result.pending_choices) == 1
    assert result.pending_choices[0].scope == "earth"


def test_travel_random_starter_location_relocates():
    from transversal.domain import Projection, TransversalType

    entity = _entity()
    entity.current_projection = "char-1:earth"
    proj = Projection(
        id="char-1:earth", entity_id="char-1", origin_universe="earth",
        universe="earth", current_location=None, transversal_type=TransversalType.NATIVE,
    )

    class Repo:
        def list_entities_by_type(self, entity_type, universe=None):
            if entity_type == EntityType.LOCATION:
                return [
                    Entity(id="loc-a", type=EntityType.LOCATION, name="A",
                           current_universe="earth", starter_location=True),
                    Entity(id="loc-b", type=EntityType.LOCATION, name="B",
                           current_universe="earth", starter_location=False),
                ]
            return []

        def get_projection(self, pid):
            return proj if pid == proj.id else None

    effect = Effect(
        timing=EffectTiming.IMMEDIATE, type="travel", action="move",
        target="{random:location}", target_scope="universe:earth",
        target_filter={"starter_location": True},
        context={"transversal_type": "inapposite"},
    )
    result = apply_effects(entity, [effect], Repo())
    assert entity.current_location == "loc-a"
    assert entity.current_universe == "earth"
    assert proj.current_location == "loc-a"


def test_set_location_random_starter_relocates():
    from transversal.domain import Projection, TransversalType

    entity = _entity()
    entity.current_projection = "char-1:earth"
    proj = Projection(
        id="char-1:earth", entity_id="char-1", origin_universe="earth",
        universe="earth", current_location=None, transversal_type=TransversalType.NATIVE,
    )
    loc_a = Entity(id="loc-a", type=EntityType.LOCATION, name="A",
                   current_universe="earth", starter_location=True)
    loc_b = Entity(id="loc-b", type=EntityType.LOCATION, name="B",
                   current_universe="earth", starter_location=False)

    class Repo:
        def list_entities_by_type(self, entity_type, universe=None):
            if entity_type == EntityType.LOCATION:
                return [loc_a, loc_b]
            return []

        def get_projection(self, pid):
            return proj if pid == proj.id else None

        def get_entity(self, eid):
            return {"loc-a": loc_a, "loc-b": loc_b}.get(eid)

    effect = Effect(
        timing=EffectTiming.IMMEDIATE, type="location", action="set",
        target="{random:location}", target_scope="universe:earth",
        target_filter={"starter_location": True},
    )
    result = apply_effects(entity, [effect], Repo())
    assert entity.current_location == "loc-a"
    assert entity.current_universe == "earth"
    assert proj.current_location == "loc-a"
    assert proj.universe == "earth"
    assert proj.transversal_type == TransversalType.NATIVE  # untouched


def test_set_location_creates_native_body_when_missing():
    from transversal.domain import Projection, TransversalType

    entity = _entity()
    entity.current_projection = None

    loc_a = Entity(id="loc-a", type=EntityType.LOCATION, name="A",
                   current_universe="earth", starter_location=True)
    loc_b = Entity(id="loc-b", type=EntityType.LOCATION, name="B",
                   current_universe="earth", starter_location=False)

    class Repo:
        def list_entities_by_type(self, entity_type, universe=None):
            if entity_type == EntityType.LOCATION:
                return [loc_a, loc_b]
            return []

        def get_entity(self, eid):
            return {"loc-a": loc_a, "loc-b": loc_b}.get(eid)

        def get_projection(self, pid):
            return None

        def get_projections_for_entity(self, entity_id):
            return []

    effect = Effect(
        timing=EffectTiming.IMMEDIATE, type="location", action="set",
        target="{random:location}", target_scope="universe:earth",
        target_filter={"starter_location": True},
    )
    result = apply_effects(entity, [effect], Repo())
    assert entity.current_location == "loc-a"
    assert entity.current_universe == "earth"
    assert entity.current_projection == "char-1:earth"
    assert len(result.new_projections) == 1
    proj = result.new_projections[0]
    assert proj.id == "char-1:earth"
    assert proj.origin_universe == "earth"
    assert proj.universe == "earth"
    assert proj.current_location == "loc-a"
    assert proj.transversal_type == TransversalType.NATIVE


def test_resolve_choice_returns_reappliable_effect():
    entity = _entity()
    effect = Effect(
        timing=EffectTiming.IMMEDIATE, type="relationship", action="create",
        target="{choose_location}", result="linked",
    )
    result = apply_effects(entity, [effect], FakeRepo())
    resolved = resolve_choice(result.pending_choices[0], "loc-krasnoyarsk")
    assert resolved.target == "loc-krasnoyarsk"
    assert resolved.type == "relationship"
    assert resolved.action == "create"
    assert resolved.result == "linked"


def test_resolve_choice_can_be_reapplied():
    entity = _entity()
    effect = Effect(
        timing=EffectTiming.IMMEDIATE, type="relationship", action="create",
        target="{choose_location}", result="linked",
    )
    result = apply_effects(entity, [effect], FakeRepo())
    assert len(result.pending_choices) == 1
    assert result.new_relationships == []

    resolved = resolve_choice(result.pending_choices[0], "loc-krasnoyarsk")
    reapplied = apply_effects(entity, [resolved], FakeRepo())
    assert reapplied.new_relationships == [
        {"from": "char-1", "to": "loc-krasnoyarsk", "type": "linked", "description": ""}
    ]


# ── Random target mode ───────────────────────────────

def test_random_location_resolves_to_candidate():
    repo = RandomRepo(locations=["loc-earth"])
    entity = _entity()
    effect = Effect(
        timing=EffectTiming.IMMEDIATE, type="relationship", action="create",
        target="{random:location}", result="linked",
    )
    result = apply_effects(entity, [effect], repo)
    assert result.pending_choices == []
    assert result.new_relationships == [
        {"from": "char-1", "to": "loc-earth", "type": "linked", "description": ""}
    ]


def test_random_location_no_candidates_noops():
    repo = RandomRepo(locations=[])
    entity = _entity()
    effect = Effect(
        timing=EffectTiming.IMMEDIATE, type="relationship", action="create",
        target="{random:location}", result="linked",
    )
    result = apply_effects(entity, [effect], repo)
    assert result.pending_choices == []
    assert result.new_relationships == []
    assert result.applied == []


def test_random_occupant_resolves_in_scope():
    repo = RandomRepo(occupants=["dmitry"])
    entity = _entity(current_location="railyard")
    effect = Effect(
        timing=EffectTiming.IMMEDIATE, type="relationship", action="create",
        target="{random:occupant}", result="ally", target_scope="railyard",
    )
    result = apply_effects(entity, [effect], repo)
    assert result.pending_choices == []
    assert result.new_relationships == [
        {"from": "char-1", "to": "dmitry", "type": "ally", "description": ""}
    ]


def test_random_trait_resolves_to_candidate():
    repo = RandomRepo(traits=[FakeTrait("iron-will", "ts-distinctions")])
    entity = _entity()
    effect = Effect(
        timing=EffectTiming.IMMEDIATE, type="modify_trait", action="gain",
        target="{random:trait}", result="d6",
    )
    result = apply_effects(entity, [effect], repo)
    assert result.pending_choices == []
    assert [ts.trait_id for ts in result.new_trait_settings] == ["iron-will"]


def test_resolve_scope_random_universe():
    from transversal.services.effects_applier import _resolve_scope

    class UniverseRepo:
        def list_entities_by_type(self, entity_type, universe=None):
            if entity_type == EntityType.UNIVERSE:
                return [
                    Entity(id="earth", type=EntityType.UNIVERSE, name="Earth", current_universe="earth"),
                    Entity(id="three_realms", type=EntityType.UNIVERSE, name="Three Realms", current_universe="three_realms"),
                ]
            return []

    entity = _entity()
    out = _resolve_scope("universe:{random_universe}", entity, UniverseRepo())
    assert out in ("universe:earth", "universe:three_realms")


def test_random_location_scoped_by_random_universe():
    from transversal.services.effects_applier import _random_candidate

    class Repo:
        def list_entities_by_type(self, entity_type, universe=None):
            if entity_type == EntityType.UNIVERSE:
                return [
                    Entity(id="earth", type=EntityType.UNIVERSE, name="Earth", current_universe="earth"),
                    Entity(id="three_realms", type=EntityType.UNIVERSE, name="Three Realms", current_universe="three_realms"),
                ]
            if entity_type == EntityType.LOCATION:
                locs = {
                    "earth": [Entity(id="l-earth", type=EntityType.LOCATION, name="Earth Loc", current_universe="earth")],
                    "three_realms": [Entity(id="l-realm", type=EntityType.LOCATION, name="Realm Loc", current_universe="three_realms")],
                }
                return locs.get(universe, [])
            return []

    entity = _entity()
    out = _random_candidate("location", "universe:{random_universe}", entity, Repo())
    assert out in ("l-earth", "l-realm")


def test_unknown_effect_is_passthrough():
    entity = _entity()
    result = apply_effects(entity, [_effect("modify_roll", "step_up_die", "highest")], FakeRepo())
    assert len(result.passthrough) == 1
    assert result.passthrough[0].type == "modify_roll"
    assert len(result.applied) == 0


def test_flow_effect_is_passthrough_for_now():
    entity = _entity()
    result = apply_effects(entity, [_effect("life_path", "next_step")], FakeRepo())
    assert len(result.passthrough) == 1


# ── Relationship-trait targeting ─────────────────────

class RelationshipFakeRepo:
    def __init__(self, edge_key="edge:char-1:fac-1:membership"):
        self.edge_key = edge_key
        self.relationship_traits = []

    def get_trait(self, trait_id):
        return FakeTrait(trait_id, "ts-rel")

    def get_traitset_by_id(self, traitset_id):
        return None

    def get_traitsettings_for_entity(self, entity_id):
        return []

    def get_relationship(self, entity_id, faction_id, rel_type):
        return {"_key": self.edge_key}

    def get_relationship_traitsettings(self, edge_key):
        return self.relationship_traits


def test_gain_relationship_trait():
    entity = _entity()
    effect = Effect(
        timing=EffectTiming.IMMEDIATE,
        type="modify_trait", action="gain_or_step_up",
        target="trait-rel-rank", result="d4",
        context={"relationship": "fac-1"},
    )
    result = apply_effects(entity, [effect], RelationshipFakeRepo())
    assert len(result.new_trait_settings) == 1
    ts = result.new_trait_settings[0]
    assert ts.from_type == "relationship"
    assert ts.entity_id == "edge:char-1:fac-1:membership"
    assert ts.trait_id == "trait-rel-rank"
    assert ts.dice == [DieType.D4]


def test_term_faction_relationship_token():
    """{term_faction} resolves to the current pending term's faction."""
    entity = _entity(pending_term=PendingTerm(faction_id="fac-current", path_id="lp-1", current_table_id="tbl"))
    captured = {}

    class Repo(RelationshipFakeRepo):
        def get_relationship(self, entity_id, faction_id, rel_type):
            captured["faction_id"] = faction_id
            return {"_key": "edge:char-1:fac-current:membership"}

    effect = Effect(
        timing=EffectTiming.IMMEDIATE,
        type="modify_trait", action="gain_or_step_up",
        target="trait-rel-rank", result="d4",
        context={"relationship": "{term_faction}"},
    )
    result = apply_effects(entity, [effect], Repo())
    assert captured["faction_id"] == "fac-current"
    assert len(result.new_trait_settings) == 1


def test_step_down_relationship_trait():
    """Rank demotion: step down a relationship trait (e.g. trait-rel-rank)."""
    repo = RelationshipFakeRepo()
    repo.relationship_traits = [
        TraitSetting(
            id="edge:char-1:fac-1:membership:trait-rel-rank",
            entity_id="edge:char-1:fac-1:membership",
            trait_id="trait-rel-rank",
            traitset_id="ts-rel",
            from_type="relationship",
            dice=[DieType.D8],
        )
    ]
    effect = Effect(
        timing=EffectTiming.IMMEDIATE,
        type="modify_trait", action="step_down",
        target="trait-rel-rank",
        context={"relationship": "fac-1"},
    )
    result = apply_effects(_entity(), [effect], repo)
    assert len(result.updated_trait_settings) == 1
    assert result.updated_trait_settings[0].dice == [DieType.D6]


def test_set_with_duration_queues_prior_value_revert():
    from transversal.domain import EffectDuration, Timer, TimerCombine

    repo = FakeRepo(traitsettings=[_ts("strength", [DieType.D6])])
    effect = Effect(
        timing=EffectTiming.IMMEDIATE, type="modify_trait", action="set",
        target="strength", result="d8",
        duration=EffectDuration(timers=[Timer(event="scene", remaining=1)], combine=TimerCombine.FIRST_TO_FIRE),
    )
    result = apply_effects(_entity(), [effect], repo)
    ts = result.updated_trait_settings[0]
    assert ts.dice == [DieType.D8]
    assert len(repo.scheduled_events) == 1
    se = repo.scheduled_events[0]
    assert se.target_type == "trait_setting"
    assert se.target_id == ts.id
    assert se.effect.type == "modify_trait"
    assert se.effect.action == "set"
    assert se.effect.result == "d6"  # prior value captured


def test_step_up_with_duration_queues_step_down_revert():
    from transversal.domain import EffectDuration, Timer, TimerCombine

    repo = FakeRepo(traitsettings=[_ts("strength", [DieType.D6])])
    effect = Effect(
        timing=EffectTiming.IMMEDIATE, type="modify_trait", action="step_up",
        target="strength",
        duration=EffectDuration(timers=[Timer(event="beat", remaining=3)]),
    )
    result = apply_effects(_entity(), [effect], repo)
    ts = result.updated_trait_settings[0]
    assert ts.dice == [DieType.D8]
    assert len(repo.scheduled_events) == 1
    assert repo.scheduled_events[0].effect.action == "step_down"


def test_gain_with_duration_queues_remove_revert():
    from transversal.domain import EffectDuration, Timer, TimerCombine

    repo = FakeRepo()
    entity = _entity()
    effect = Effect(
        timing=EffectTiming.IMMEDIATE, type="modify_trait", action="gain",
        target="iron-will", result="d6",
        duration=EffectDuration(timers=[Timer(event="scene", remaining=1)], combine=TimerCombine.FIRST_TO_FIRE),
    )
    result = apply_effects(entity, [effect], repo)
    assert len(result.new_trait_settings) == 1
    assert len(repo.scheduled_events) == 1
    se = repo.scheduled_events[0]
    assert se.target_type == "entity"
    assert se.effect.type == "modify_trait"
    assert se.effect.action == "remove"
    assert se.effect.target == "iron-will"


# ── cortex_gain ──────────────────────────────────────

def test_cortex_gain_creates_when_absent():
    repo = FakeRepo(traits=[FakeTrait("complication-x", "ts-complications-a190")])
    entity = _entity()
    result = apply_effects(entity, [_effect("modify_trait", "cortex_gain", "complication-x", "d8")], repo)
    assert len(result.new_trait_settings) == 1
    ts = result.new_trait_settings[0]
    assert ts.trait_id == "complication-x"
    assert ts.dice == [DieType.D8]
    assert ts.polarity == Polarity.POSITIVE
    assert result.applied[0].summary == "gained complication-x at d8"


def test_cortex_gain_negative_flag_creates_negative():
    repo = FakeRepo(traits=[FakeTrait("complication-x", "ts-complications-a190")])
    entity = _entity()
    effect = Effect(
        timing=EffectTiming.IMMEDIATE, type="modify_trait", action="cortex_gain",
        target="complication-x", result="d8", negative=True,
    )
    result = apply_effects(entity, [effect], repo)
    assert len(result.new_trait_settings) == 1
    assert result.new_trait_settings[0].polarity == Polarity.NEGATIVE


def test_cortex_gain_jumps_when_effect_die_higher():
    repo = FakeRepo(traitsettings=[_ts("complication-x", [DieType.D8])])
    entity = _entity()
    result = apply_effects(entity, [_effect("modify_trait", "cortex_gain", "complication-x", "d12")], repo)
    assert len(result.updated_trait_settings) == 1
    assert result.updated_trait_settings[0].dice == [DieType.D12]
    assert "jumped" in result.applied[0].summary


def test_cortex_gain_steps_up_when_effect_die_equal():
    repo = FakeRepo(traitsettings=[_ts("complication-x", [DieType.D8])])
    entity = _entity()
    result = apply_effects(entity, [_effect("modify_trait", "cortex_gain", "complication-x", "d8")], repo)
    assert len(result.updated_trait_settings) == 1
    assert result.updated_trait_settings[0].dice == [DieType.D10]
    assert "stepped up" in result.applied[0].summary


def test_cortex_gain_at_cap_noop():
    repo = FakeRepo(traitsettings=[_ts("complication-x", [DieType.D12])])
    entity = _entity()
    result = apply_effects(entity, [_effect("modify_trait", "cortex_gain", "complication-x", "d12")], repo)
    assert len(result.updated_trait_settings) == 0
    assert "already at d12" in result.applied[0].summary


# ── P3.8: complication stepped beyond d12 → taken out ──

def test_step_up_d12_complication_takes_out():
    repo = FakeRepo(traitsettings=[_ts("scar", [DieType.D12], negative=True)])
    entity = _entity()
    result = apply_effects(entity, [_effect("modify_trait", "step_up", "scar")], repo)
    assert entity.taken_out is True
    assert "taken out" in result.applied[0].summary
    assert len(repo.scheduled_events) == 1
    assert repo.scheduled_events[0].target_type == "entity"
    assert repo.scheduled_events[0].effect.action == "clear_taken_out"


def test_step_up_d12_positive_trait_no_takeout():
    repo = FakeRepo(traitsettings=[_ts("iron-will", [DieType.D12])])
    entity = _entity()
    result = apply_effects(entity, [_effect("modify_trait", "step_up", "iron-will")], repo)
    assert entity.taken_out is False
    assert "already at d12" in result.applied[0].summary


def test_cortex_gain_d12_complication_takes_out():
    repo = FakeRepo(traitsettings=[_ts("scar", [DieType.D12], negative=True)])
    entity = _entity()
    result = apply_effects(entity, [_effect("modify_trait", "cortex_gain", "scar", "d8")], repo)
    assert entity.taken_out is True
    assert "taken out" in result.applied[0].summary


def test_earn_targets_explicit_entity():
    other = _entity(id="char-2", name="Other")
    repo = FakeRepo(entities=[other])
    entity = _entity(razmerit=0)
    effect = Effect(timing=EffectTiming.IMMEDIATE, type="transfer_razmerit", action="earn",
                    target="self", entity="char-2", result="3")
    result = apply_effects(entity, [effect], repo)
    assert other.razmerit == 3
    assert entity.razmerit == 0
    assert other in result.entities_to_update


def test_gain_targets_explicit_entity():
    other = _entity(id="char-2", name="Other")
    repo = FakeRepo(traits=[FakeTrait("scar", "ts-complications")], entities=[other])
    entity = _entity()
    effect = Effect(timing=EffectTiming.IMMEDIATE, type="modify_trait", action="gain",
                    target="scar", entity="char-2", result="d6", negative=True)
    result = apply_effects(entity, [effect], repo)
    assert len(result.new_trait_settings) == 1
    assert result.new_trait_settings[0].entity_id == "char-2"


def test_choose_entity_pending_choice_marks_field():
    repo = FakeRepo()
    entity = _entity()
    effect = Effect(timing=EffectTiming.IMMEDIATE, type="transfer_razmerit", action="earn",
                    target="self", entity="{choose_entity}", result="1")
    result = apply_effects(entity, [effect], repo)
    assert len(result.pending_choices) == 1
    assert result.pending_choices[0].kind == "entity"
    assert result.pending_choices[0].field == "entity"


def test_choose_entity_pending_choice_uses_entity_scope():
    repo = FakeRepo()
    entity = _entity()
    effect = Effect(timing=EffectTiming.IMMEDIATE, type="transfer_razmerit", action="earn",
                    target="self", entity="{choose_entity}", entity_scope="subtree:loc-x", result="1")
    result = apply_effects(entity, [effect], repo)
    assert result.pending_choices[0].scope == "subtree:loc-x"


# ── Fog-of-war reveal ────────────────────────────────

def test_reveal_adds_learner_to_known_to():
    owner = _entity(id="char-2")
    ts = _ts("hidden-trait", [DieType.D8], entity_id="char-2", traitset_id="ts-x", known_to=[])
    repo = FakeRepo(traits=[FakeTrait("hidden-trait", "ts-x")], traitsettings=[ts], entities=[owner])
    entity = _entity()  # char-1, the learner

    effect = Effect(
        timing=EffectTiming.IMMEDIATE, type="modify_trait", action="reveal",
        target="hidden-trait", entity="char-2",
    )
    result = apply_effects(entity, [effect], repo)

    assert ts.known_to == ["char-1"]
    assert len(result.revealed) == 1
    assert result.revealed[0][0] is ts
    assert result.revealed[0][1] == "char-1"
    assert result.applied[0].summary == "revealed hidden-trait to char-1"


def test_reveal_is_idempotent():
    owner = _entity(id="char-2")
    ts = _ts("hidden-trait", [DieType.D8], entity_id="char-2", traitset_id="ts-x", known_to=["char-1"])
    repo = FakeRepo(traits=[FakeTrait("hidden-trait", "ts-x")], traitsettings=[ts], entities=[owner])
    entity = _entity()

    effect = Effect(
        timing=EffectTiming.IMMEDIATE, type="modify_trait", action="reveal",
        target="hidden-trait", entity="char-2",
    )
    result = apply_effects(entity, [effect], repo)

    assert ts.known_to == ["char-1"]
    assert result.revealed == []
    assert result.applied[0].summary == "char-1 already knows hidden-trait"


# ── Travel (portal) ─────────────────────────────────

class TravelRepo:
    """Minimal repo for travel effects — entities + projections."""

    def __init__(self, entities=None, projections=None):
        self.entities = {e.id: e for e in (entities or [])}
        self.projections = {p.id: p for p in (projections or [])}

    def get_entity(self, eid):
        return self.entities.get(eid)

    def get_projection(self, pid):
        return self.projections.get(pid)

    def get_projections_for_entity(self, eid):
        return [p for p in self.projections.values() if p.entity_id == eid]

    def create_projection(self, p):
        self.projections[p.id] = p
        return p

    def update_projection(self, p):
        self.projections[p.id] = p
        return p

    def list_entities_by_type(self, et, universe=None):
        return []

    def list_entities_by_location(self, lid):
        return []

    def list_entities_by_locations(self, ids):
        return []

    def list_all_entities(self, universe=None):
        return []

    def get_traits_by_universe(self, u):
        return []

    def get_traits_by_traitset(self, t):
        return []

    def list_lifepaths_by_universe(self, u):
        return []

    def list_roll_tables(self):
        return []

    def list_location_descendants(self, lid):
        return []

    def get_entities_by_ids(self, ids):
        return [self.entities[i] for i in ids if i in self.entities]

    def list_faction_members(self, f):
        return []


def _proj(id, entity_id, universe, origin_universe=None, location=None, transversal_type=None):
    from transversal.domain import Projection, TransversalType
    return Projection(
        id=id, entity_id=entity_id, universe=universe,
        origin_universe=origin_universe or universe,
        current_location=location,
        transversal_type=transversal_type or TransversalType.NATIVE,
    )


def _loc(id, universe):
    return Entity(id=id, type=EntityType.LOCATION, name=id, current_universe=universe)


def test_travel_new_projection_spawns_body():
    from transversal.domain import TransversalType
    entity = _entity()
    repo = TravelRepo(
        entities=[entity, _loc("krasnoyarsk", "earth")],
        projections=[_proj("char-1:earth", "char-1", "earth")],
    )
    effect = Effect(
        timing=EffectTiming.IMMEDIATE, type="travel", action="move",
        target="krasnoyarsk", target_scope="universe:earth",
        context={"transversal_type": "consciousness", "projection": "{new_projection}"},
    )
    result = apply_effects(entity, [effect], repo)
    assert len(result.new_projections) == 1
    newp = result.new_projections[0]
    assert newp.id == "char-1:earth:2"
    assert newp.transversal_type == TransversalType.CONSCIOUSNESS
    assert entity.current_projection == "char-1:earth:2"
    assert entity.current_location == "krasnoyarsk"
    assert entity.current_universe == "earth"


def test_travel_random_projection_reuses_body():
    entity = _entity()
    proj = _proj("char-1:earth", "char-1", "earth", location="railyard")
    repo = TravelRepo(entities=[entity], projections=[proj])
    effect = Effect(
        timing=EffectTiming.IMMEDIATE, type="travel", action="move",
        target="", target_scope="universe:earth",
        context={"transversal_type": "consciousness", "projection": "{random_projection}"},
    )
    result = apply_effects(entity, [effect], repo)
    assert entity.current_projection == "char-1:earth"
    assert entity.current_location == "railyard"
    assert entity.current_universe == "earth"


def test_travel_inapposite_relocates_active_body():
    from transversal.domain import TransversalType
    entity = _entity(current_projection="char-1:earth", current_location="railyard")
    proj = _proj("char-1:earth", "char-1", "earth", location="railyard")
    repo = TravelRepo(entities=[entity, _loc("peak", "three_realms")], projections=[proj])
    effect = Effect(
        timing=EffectTiming.IMMEDIATE, type="travel", action="move",
        target="peak", target_scope="universe:three_realms",
        context={"transversal_type": "inapposite"},
    )
    result = apply_effects(entity, [effect], repo)
    assert len(result.updated_projections) == 1
    assert result.updated_projections[0].universe == "three_realms"
    assert result.updated_projections[0].transversal_type == TransversalType.INAPPOSITE
    assert entity.current_location == "peak"
    assert entity.current_universe == "three_realms"


def test_travel_choose_projection_pends():
    entity = _entity()
    repo = TravelRepo(entities=[entity], projections=[_proj("char-1:earth", "char-1", "earth")])
    effect = Effect(
        timing=EffectTiming.IMMEDIATE, type="travel", action="move",
        target="", target_scope="universe:earth",
        context={"transversal_type": "consciousness", "projection": "{choose_projection}"},
    )
    result = apply_effects(entity, [effect], repo)
    assert len(result.pending_choices) == 1
    assert result.pending_choices[0].kind == "projection"
    assert result.pending_choices[0].field == "context.projection"


def test_travel_random_projection_falls_back_to_new():
    entity = _entity()
    repo = TravelRepo(
        entities=[entity, _loc("peak", "three_realms")],
        projections=[_proj("char-1:earth", "char-1", "earth")],
    )
    effect = Effect(
        timing=EffectTiming.IMMEDIATE, type="travel", action="move",
        target="peak", target_scope="universe:three_realms",
        context={"transversal_type": "consciousness", "projection": "{random_projection}"},
    )
    result = apply_effects(entity, [effect], repo)
    assert len(result.new_projections) == 1
    assert entity.current_projection == "char-1:three_realms"
    assert entity.current_location == "peak"
    assert entity.current_universe == "three_realms"


def test_travel_choose_projection_falls_back_to_new():
    entity = _entity()
    repo = TravelRepo(
        entities=[entity, _loc("peak", "three_realms")],
        projections=[_proj("char-1:earth", "char-1", "earth")],
    )
    effect = Effect(
        timing=EffectTiming.IMMEDIATE, type="travel", action="move",
        target="peak", target_scope="universe:three_realms",
        context={"transversal_type": "consciousness", "projection": "{choose_projection}"},
    )
    result = apply_effects(entity, [effect], repo)
    assert result.pending_choices == []  # no bodies to choose → spawn instead
    assert len(result.new_projections) == 1
    assert entity.current_projection == "char-1:three_realms"


def test_travel_last_projection_reuses_body():
    entity = _entity()
    repo = TravelRepo(
        entities=[entity],
        projections=[_proj("char-1:earth", "char-1", "earth", location="railyard")],
    )
    effect = Effect(
        timing=EffectTiming.IMMEDIATE, type="travel", action="move",
        target="", target_scope="universe:earth",
        context={"transversal_type": "consciousness", "projection": "{last_projection}"},
    )
    result = apply_effects(entity, [effect], repo)
    assert result.new_projections == []
    assert entity.current_projection == "char-1:earth"
    assert entity.current_location == "railyard"


def test_travel_last_projection_picks_most_recent():
    entity = _entity()
    repo = TravelRepo(
        entities=[entity],
        projections=[
            _proj("char-1:earth", "char-1", "earth", location="railyard"),
            _proj("char-1:earth:2", "char-1", "earth", location="peak"),
        ],
    )
    repo.get_projection("char-1:earth").last_used_at = "2026-08-21T10:00:00+00:00"
    repo.get_projection("char-1:earth:2").last_used_at = "2026-08-22T10:00:00+00:00"
    effect = Effect(
        timing=EffectTiming.IMMEDIATE, type="travel", action="move",
        target="", target_scope="universe:earth",
        context={"transversal_type": "consciousness", "projection": "{last_projection}"},
    )
    result = apply_effects(entity, [effect], repo)
    assert entity.current_projection == "char-1:earth:2"
    assert entity.current_location == "peak"


def test_travel_reuse_scoped_to_location():
    entity = _entity()
    repo = TravelRepo(
        entities=[entity, _loc("valley", "earth"), _loc("yinling", "earth")],
        projections=[
            _proj("char-1:earth", "char-1", "earth", location="valley"),
            _proj("char-1:earth:2", "char-1", "earth", location="elsewhere"),
        ],
    )
    repo.get_projection("char-1:earth").last_used_at = "2026-08-21T10:00:00+00:00"
    repo.get_projection("char-1:earth:2").last_used_at = "2026-08-22T10:00:00+00:00"  # more recent, but outside scope
    effect = Effect(
        timing=EffectTiming.IMMEDIATE, type="travel", action="move",
        target="yinling", target_scope="location:valley",
        context={"transversal_type": "consciousness", "projection": "{last_projection}"},
    )
    result = apply_effects(entity, [effect], repo)
    # only char-1:earth is in the Valley scope, even though :2 is more recent
    assert entity.current_projection == "char-1:earth"
    assert entity.current_location == "valley"


def test_travel_reuse_fallback_spawns_at_specific_target():
    entity = _entity()
    repo = TravelRepo(
        entities=[entity, _loc("valley", "earth"), _loc("yinling", "earth")],
        projections=[_proj("char-1:earth", "char-1", "earth", location="elsewhere")],
    )
    effect = Effect(
        timing=EffectTiming.IMMEDIATE, type="travel", action="move",
        target="yinling", target_scope="location:valley",
        context={"transversal_type": "consciousness", "projection": "{last_projection}"},
    )
    result = apply_effects(entity, [effect], repo)
    assert len(result.new_projections) == 1
    assert result.new_projections[0].current_location == "yinling"
    assert entity.current_projection == result.new_projections[0].id
    assert entity.current_location == "yinling"


def test_travel_last_projection_falls_back_to_new():
    entity = _entity()
    repo = TravelRepo(
        entities=[entity, _loc("peak", "three_realms")],
        projections=[_proj("char-1:earth", "char-1", "earth")],
    )
    effect = Effect(
        timing=EffectTiming.IMMEDIATE, type="travel", action="move",
        target="peak", target_scope="universe:three_realms",
        context={"transversal_type": "consciousness", "projection": "{last_projection}"},
    )
    result = apply_effects(entity, [effect], repo)
    assert len(result.new_projections) == 1
    assert entity.current_projection == "char-1:three_realms"


def test_travel_projection_scoped_to_location_universe():
    entity = _entity()
    repo = TravelRepo(
        entities=[entity, _loc("peak", "three_realms")],
        projections=[
            _proj("char-1:earth", "char-1", "earth"),
            _proj("char-1:three_realms", "char-1", "three_realms", location="peak"),
        ],
    )
    effect = Effect(
        timing=EffectTiming.IMMEDIATE, type="travel", action="move",
        target="peak",  # location scope → destination universe = three_realms
        context={"transversal_type": "consciousness", "projection": "{random_projection}"},
    )
    result = apply_effects(entity, [effect], repo)
    assert entity.current_projection == "char-1:three_realms"


def test_travel_resolved_choose_projection_arrives_in_body():
    entity = _entity()
    repo = TravelRepo(
        entities=[entity],
        projections=[
            _proj("char-1:earth", "char-1", "earth", location="railyard"),
            _proj("char-1:three_realms", "char-1", "three_realms", location="peak"),
        ],
    )
    effect = Effect(
        timing=EffectTiming.IMMEDIATE, type="travel", action="move",
        target="", target_scope="universe:three_realms",
        context={"transversal_type": "consciousness", "projection": "char-1:three_realms"},
    )
    result = apply_effects(entity, [effect], repo)
    assert entity.current_projection == "char-1:three_realms"
    assert entity.current_location == "peak"


# ── choose-placeholder discovery ───────────────────

def test_find_choose_placeholder_target():
    from transversal.services.effects_applier import find_choose_placeholder
    eff = Effect(
        timing=EffectTiming.IMMEDIATE, type="travel", action="move",
        target="{choose_location}", target_scope="universe:earth",
    )
    assert find_choose_placeholder(eff) == ("location", "target", "universe:earth")


def test_find_choose_placeholder_context_projection():
    from transversal.services.effects_applier import find_choose_placeholder
    eff = Effect(
        timing=EffectTiming.IMMEDIATE, type="travel", action="move",
        target="krasnoyarsk", target_scope="universe:earth",
        context={"transversal_type": "consciousness", "projection": "{choose_projection}"},
    )
    assert find_choose_placeholder(eff) == ("projection", "context.projection", "universe:earth")


def test_find_choose_placeholder_none():
    from transversal.services.effects_applier import find_choose_placeholder
    eff = Effect(
        timing=EffectTiming.IMMEDIATE, type="travel", action="move",
        target="krasnoyarsk", context={"projection": "active"},
    )
    assert find_choose_placeholder(eff) is None


# ── {choose:*} in scope ─────────────────────────────

def test_scope_choice_detected_for_choose_universe():
    from transversal.services.effects_applier import _scope_choice
    eff = Effect(
        timing=EffectTiming.IMMEDIATE, type="travel", action="move",
        target="{choose_location}", target_scope="universe:{choose_universe}",
    )
    choice = _scope_choice(eff)
    assert choice is not None
    assert choice.kind == "universe"
    assert choice.field == "target_scope"


def test_find_choose_placeholder_scope_first():
    from transversal.services.effects_applier import find_choose_placeholder
    eff = Effect(
        timing=EffectTiming.IMMEDIATE, type="travel", action="move",
        target="{choose_location}", target_scope="universe:{choose_universe}",
    )
    assert find_choose_placeholder(eff) == ("universe", "target_scope", None)


def test_resolve_scope_choose_substitutes():
    from transversal.services.effects_applier import _resolve_scope_choose
    assert _resolve_scope_choose("universe:{choose_universe}", "earth") == "universe:earth"
    assert _resolve_scope_choose("{choose_universe}", "earth") == "earth"


def test_apply_effects_defers_scope_choice():
    eff = Effect(
        timing=EffectTiming.IMMEDIATE, type="travel", action="move",
        target="{choose_location}", target_scope="universe:{choose_universe}",
    )
    entity = _entity()
    result = apply_effects(entity, [eff], TravelRepo(entities=[entity]))
    assert len(result.pending_choices) == 1
    assert result.pending_choices[0].kind == "universe"
    assert result.pending_choices[0].field == "target_scope"
    assert result.applied == []


def test_two_step_scope_then_location():
    from transversal.services.effects_applier import resolve_choice
    eff = Effect(
        timing=EffectTiming.IMMEDIATE, type="travel", action="move",
        target="{choose_location}", target_scope="universe:{choose_universe}",
        context={"transversal_type": "inapposite"},
    )
    entity = _entity()
    repo = TravelRepo(entities=[entity])

    r1 = apply_effects(entity, [eff], repo)
    assert len(r1.pending_choices) == 1
    assert r1.pending_choices[0].field == "target_scope"

    eff2 = resolve_choice(r1.pending_choices[0], "earth")
    assert eff2.target_scope == "universe:earth"

    r2 = apply_effects(entity, [eff2], repo)
    assert len(r2.pending_choices) == 1
    assert r2.pending_choices[0].field == "target"
    assert r2.pending_choices[0].kind == "location"
    assert r2.pending_choices[0].scope == "universe:earth"


def test_entity_spec_resolves_subject_to_location():
    from transversal.services.target_spec import NavigateStep, SelectStep, TargetSpec

    location = _entity(id="loc-1", type=EntityType.LOCATION, current_location="loc-1")
    entity = _entity(id="char-1", current_location="loc-1")
    ts = _ts("martial", [DieType.D8], entity_id="loc-1")
    repo = FakeRepo(entities=[entity, location], traitsettings=[ts])

    effect = Effect(
        timing=EffectTiming.IMMEDIATE, type="modify_trait", action="step_down",
        target="loc-1:martial",
        entity_spec=TargetSpec(steps=[SelectStep(collection="self"), NavigateStep(edge="location")]),
    )
    result = apply_effects(entity, [effect], repo)
    assert len(result.updated_trait_settings) == 1
    assert result.updated_trait_settings[0].id == "loc-1:martial"
