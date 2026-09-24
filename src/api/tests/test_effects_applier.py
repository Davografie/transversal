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
    TargetingBan,
    TraitSetting,
    TraitSetSetting,
    TransversalType,
)
from transversal.services.effects_applier import PendingChoice, apply_effects, resolve_choice
from transversal.services.target_resolver import Binding
from transversal.services.target_spec import TargetSpec


class FakeTrait:
    def __init__(self, trait_id, traitset_id, name=None, universes=None, tags=None):
        self.id = trait_id
        self.traitset_id = traitset_id
        self.name = name or trait_id
        # A trait definition always belongs to at least one universe, and a path
        # that ranges over the registry narrows by exactly that.
        self.universes = list(universes) if universes is not None else ["earth"]
        # The `container` tag is what lets a trait hold others, and the
        # definition-change rule reads it.
        self.tags = list(tags or [])


class FakeTraitSet:
    def __init__(self, ts_id, allow_duplicates=False):
        self.id = ts_id
        self.allow_duplicates = allow_duplicates


class FakeRepo:
    def __init__(self, traits=None, traitsettings=None, entities=None, traitsets=None):
        self.traits = {t.id: t for t in (traits or [])}
        self.traitsettings = list(traitsettings or [])
        self.entities = {e.id: e for e in (entities or [])}
        self.traitsets = {t.id: t for t in (traitsets or [])}
        self.scheduled_events = []
        self.projections = []
        self.traitsetsettings = []

    def get_trait(self, trait_id):
        return self.traits.get(trait_id)

    def get_traitset_by_id(self, traitset_id):
        return self.traitsets.get(traitset_id)

    # Mirrors the real repository's duplicate rules (statement distinguishes
    # duplicates when a set allows them).
    def find_traitsetting_collision(self, entity_id, trait_id, statement="", allow_duplicates=False):
        existing = [ts for ts in self.traitsettings
                    if ts.entity_id == entity_id and ts.trait_id == trait_id]
        if not existing:
            return None
        if not allow_duplicates:
            return existing[0]
        for ts in existing:
            if (ts.statement or "") == (statement or ""):
                return ts
        return None

    def resolve_traitsetting_id(self, entity_id, trait_id, statement="", allow_duplicates=False):
        base = f"{entity_id}:{trait_id}"
        if allow_duplicates and statement:
            import hashlib
            return f"{base}:{hashlib.sha1(statement.encode()).hexdigest()[:8]}"
        return base

    def get_traitsettings_for_entity(self, entity_id):
        return [ts for ts in self.traitsettings if ts.entity_id == entity_id]

    def get_traitsetting(self, ts_id):
        return next((ts for ts in self.traitsettings if ts.id == ts_id), None)

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

    def __init__(self, locations=None, occupants=None, traits=None, entities=None,
                 universes=None):
        self._locations = locations or []
        self._occupants = occupants or []
        self._traits = traits or []
        self._entities = entities or []
        self._universes = universes or []

    def _entity(self, id, entity_type):
        return Entity(id=id, type=entity_type, name=id, current_universe="earth")

    def list_entities_by_type(self, entity_type, universe=None):
        if entity_type == EntityType.LOCATION:
            return [self._entity(l, EntityType.LOCATION) for l in self._locations]
        if entity_type == EntityType.UNIVERSE:
            return [self._entity(u, EntityType.UNIVERSE) for u in self._universes]
        return []

    def get_entity(self, entity_id):
        for kind, ids in ((EntityType.LOCATION, self._locations),
                          (EntityType.GMC, [*self._entities, *self._occupants]),
                          (EntityType.UNIVERSE, self._universes)):
            if entity_id in ids:
                return self._entity(entity_id, kind)
        return None

    def get_all_traits(self):
        return list(self._traits)

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


def _starter_location_spec():
    """A random starter location in Earth — the path the built-in SFX carries.

    ``{random:location}`` + ``universe:earth`` + a starter-location filter used to
    spell this; it composes the same declared scope path with a terminal random
    step, so the applier sees a spec instead of a placeholder.
    """
    from transversal.services.target_scopes import choice_spec

    return choice_spec("location", "universe:earth", mode="random",
                       filter={"starter_location": True})


def _bodies_at(location_id: str):
    """The actor's own bodies inside a place, as a path.

    This is what a `projection` reference's spec says: the same declarations the
    old `location:X` scope resolved (the place, its zones, my bodies there).
    """
    from transversal.services.target_scopes import ACTOR_AT_RUNTIME, selection_spec

    return selection_spec("projection", location_id, ACTOR_AT_RUNTIME, "location")


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


def test_change_trait_points_the_instance_at_another_definition():
    """The instance keeps everything that is its own — owner, dice, rating type,
    polarity, statement, notes, grants — and changes what it *is*. Its trait set
    follows the new definition, because the set is what says where it renders and
    how a `HAS_TRAIT_IN_TRAITSET` condition reads it."""
    repo = FakeRepo(
        traits=[FakeTrait("trait-blade", "ts-weapons"),
                FakeTrait("trait-fire-blade", "ts-elements")],
        traitsettings=[_ts("trait-blade", [DieType.D8], statement="my blade",
                           notes="gm only", polarity=Polarity.POSITIVE)],
    )
    effect = Effect(
        timing=EffectTiming.IMMEDIATE, type="modify_trait", action="change",
        target="trait-blade",
        refs={"trait": TargetRef(value="trait-fire-blade")},
    )
    result = apply_effects(_entity(), [effect], repo)
    assert len(result.updated_trait_settings) == 1
    ts = result.updated_trait_settings[0]
    assert ts.trait_id == "trait-fire-blade"
    assert ts.traitset_id == "ts-elements"
    assert ts.dice == [DieType.D8] and ts.statement == "my blade"
    assert ts.notes == "gm only" and ts.polarity == Polarity.POSITIVE
    assert ts.entity_id == "char-1"
    assert "changed trait-blade into trait-fire-blade" in result.applied[0].summary


def test_change_trait_with_duration_queues_a_change_back_revert():
    """A timed change is a timed revert: the same action pointed back at the
    definition the instance had, scheduled on the timer."""
    from transversal.domain import EffectDuration, Timer, TimerCombine

    repo = FakeRepo(
        traits=[FakeTrait("trait-blade", "ts-weapons"),
                FakeTrait("trait-fire-blade", "ts-elements")],
        traitsettings=[_ts("trait-blade", [DieType.D8], statement="my blade")],
    )
    effect = Effect(
        timing=EffectTiming.IMMEDIATE, type="modify_trait", action="change",
        target="trait-blade",
        refs={"trait": TargetRef(value="trait-fire-blade")},
        duration=EffectDuration(timers=[Timer(event="scene", remaining=1)],
                                combine=TimerCombine.FIRST_TO_FIRE),
    )
    result = apply_effects(_entity(), [effect], repo)
    ts = result.updated_trait_settings[0]
    assert ts.trait_id == "trait-fire-blade" and ts.traitset_id == "ts-elements"

    assert len(repo.scheduled_events) == 1
    event = repo.scheduled_events[0]
    assert event.kind == "revert"
    assert event.target_type == "trait_setting" and event.target_id == ts.id
    assert event.effect.action == "change"
    assert event.effect.result == "trait-blade", "the prior definition was not captured"
    # Addressed to the *instance*: the authored target was a registry trait id, and
    # that stops naming this instance the moment the pointer moves.
    assert event.effect.target == ts.id

    # Applying the queued revert puts the pointer — and the set that follows it —
    # back.
    apply_effects(_entity(), [event.effect], repo)
    assert ts.trait_id == "trait-blade"
    assert ts.traitset_id == "ts-weapons"
    assert ts.dice == [DieType.D8] and ts.statement == "my blade"


def test_change_trait_without_a_duration_is_cancellable():
    """No duration: the undo is a *hold* inside a cancelable (manual) activation,
    so the change can be taken back before it commits — the same booking a step-up
    gets."""
    from transversal.services.scheduled_events import activation_booking

    repo = FakeRepo(
        traits=[FakeTrait("trait-blade", "ts-weapons"),
                FakeTrait("trait-fire-blade", "ts-elements")],
        traitsettings=[_ts("trait-blade", [DieType.D8])],
    )
    effect = Effect(
        timing=EffectTiming.IMMEDIATE, type="modify_trait", action="change",
        target="trait-blade",
        refs={"trait": TargetRef(value="trait-fire-blade")},
    )
    with activation_booking("sfx-ignite", cancelable=True):
        apply_effects(_entity(), [effect], repo)

    assert len(repo.scheduled_events) == 1
    hold = repo.scheduled_events[0]
    assert hold.kind == "hold"
    assert hold.target_id == "char-1:trait-blade"
    assert hold.effect.action == "change" and hold.effect.result == "trait-blade"


def test_change_trait_without_an_instance_refuses():
    repo = FakeRepo(traits=[FakeTrait("trait-fire-blade", "ts-elements")])
    effect = Effect(
        timing=EffectTiming.IMMEDIATE, type="modify_trait", action="change",
        target="trait-nothing",
        refs={"trait": TargetRef(value="trait-fire-blade")},
    )
    result = apply_effects(_entity(), [effect], repo)
    assert result.updated_trait_settings == []
    assert "no trait instance" in result.applied[0].summary


def test_change_trait_without_a_definition_refuses():
    repo = FakeRepo(traitsettings=[_ts("trait-blade", [DieType.D8])])
    effect = Effect(
        timing=EffectTiming.IMMEDIATE, type="modify_trait", action="change",
        target="trait-blade",
        refs={"trait": TargetRef(value="trait-does-not-exist")},
    )
    result = apply_effects(_entity(), [effect], repo)
    assert result.updated_trait_settings == []
    assert "no trait definition to change to" in result.applied[0].summary


def test_change_trait_to_the_same_definition_is_a_no_op():
    repo = FakeRepo(traits=[FakeTrait("trait-blade", "ts-weapons")],
                    traitsettings=[_ts("trait-blade", [DieType.D8])])
    effect = Effect(
        timing=EffectTiming.IMMEDIATE, type="modify_trait", action="change",
        target="trait-blade",
        refs={"trait": TargetRef(value="trait-blade")},
    )
    result = apply_effects(_entity(), [effect], repo)
    assert result.updated_trait_settings == []
    assert "already trait-blade" in result.applied[0].summary


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


def test_add_die_seeds_the_trait_when_missing():
    """A resource trait starts from its first die (Crimson Scars)."""
    repo = FakeRepo(traits=[FakeTrait("hazard", "ts-complications")])
    entity = _entity()
    effect = Effect(
        timing=EffectTiming.IMMEDIATE, type="modify_trait", action="add_die",
        target="hazard", result="d8", negative=True,
        context={"rating_type": "resource", "statement": "Crimson Scar"},
    )
    result = apply_effects(entity, [effect], repo)
    assert len(result.new_trait_settings) == 1
    ts = result.new_trait_settings[0]
    assert ts.trait_id == "hazard"
    assert ts.dice == [DieType.D8]
    assert ts.rating_type == RatingType.RESOURCE
    assert ts.statement == "Crimson Scar"
    assert ts.polarity == Polarity.NEGATIVE
    assert result.applied[0].summary == "gained hazard at d8"


def test_add_die_seeded_trait_is_deleted_on_revert():
    from transversal.domain import EffectDuration, Timer, TimerCombine
    repo = FakeRepo(traits=[FakeTrait("hazard", "ts-complications")])
    entity = _entity()
    effect = Effect(
        timing=EffectTiming.IMMEDIATE, type="modify_trait", action="add_die",
        target="hazard", result="d4",
        duration=EffectDuration(timers=[Timer(event="scene", remaining=1)], combine=TimerCombine.FIRST_TO_FIRE),
    )
    apply_effects(entity, [effect], repo)
    assert len(repo.scheduled_events) == 1
    revert = repo.scheduled_events[0]
    assert revert.effect.action == "remove"
    assert revert.effect.target == "hazard"


def test_add_die_accumulates_into_the_seeded_trait():
    """The second unchosen die appends to the trait the first one seeded.

    Mirrors the armed per-die loop: each die is applied and committed on its
    own, so the next one finds the trait its predecessor created.
    """
    repo = FakeRepo(traits=[FakeTrait("hazard", "ts-complications")])
    entity = _entity()
    first = _effect("modify_trait", "add_die", "hazard", "d4")
    second = _effect("modify_trait", "add_die", "hazard", "d8")
    seeded = apply_effects(entity, [first], repo)
    repo.traitsettings.append(seeded.new_trait_settings[0])   # what commit_effects does
    second_result = apply_effects(entity, [second], repo)
    assert second_result.new_trait_settings == []
    assert repo.traitsettings[0].dice == [DieType.D4, DieType.D8]


def test_add_die_without_a_die_rating_is_skipped():
    """An unresolved variable (a fail tier has no effect die) adds nothing."""
    repo = FakeRepo(traits=[FakeTrait("hazard", "ts-complications")])
    entity = _entity()
    result = apply_effects(entity, [_effect("modify_trait", "add_die", "hazard", "")], repo)
    assert result.new_trait_settings == []
    assert "no die rating" in result.applied[0].summary


# ── Trait copy (teach / gift) ────────────────

def _copy_effect(recipient_id, source_ts_id):
    return Effect(
        timing=EffectTiming.IMMEDIATE, type="modify_trait", action="copy",
        entity=recipient_id, refs={"trait": TargetRef(value=source_ts_id)},
    )


def test_copy_trait_carries_the_instance_to_the_recipient():
    src = _ts("medicine", [DieType.D8], entity_id="char-1", traitset_id="ts-med",
              statement="Field surgery", notes="from the war")
    learner = _entity(id="char-2", name="Dmitri")
    repo = FakeRepo(traits=[FakeTrait("medicine", "ts-med")], traitsettings=[src], entities=[learner])
    result = apply_effects(_entity(), [_copy_effect("char-2", "char-1:medicine")], repo)
    ts = result.new_trait_settings[0]
    assert ts.id == "char-2:medicine"
    assert ts.entity_id == "char-2"
    assert ts.dice == [DieType.D8]
    assert ts.traitset_id == "ts-med"
    assert ts.statement == "Field surgery"
    assert ts.notes == "from the war"
    assert result.applied[0].summary == "copied medicine to char-2"


def test_copy_trait_refuses_when_the_recipient_already_has_it():
    src = _ts("medicine", [DieType.D8], entity_id="char-1")
    owned = _ts("medicine", [DieType.D6], entity_id="char-2")
    learner = _entity(id="char-2", name="Dmitri")
    repo = FakeRepo(traitsettings=[src, owned], entities=[learner])
    result = apply_effects(_entity(), [_copy_effect("char-2", "char-1:medicine")], repo)
    assert result.new_trait_settings == []
    assert "already has medicine" in result.applied[0].summary


def test_copy_trait_allows_a_distinct_statement_when_the_set_allows_duplicates():
    src = _ts("medicine", [DieType.D8], entity_id="char-1",
              statement="Field surgery", traitset_id="ts-med")
    owned = _ts("medicine", [DieType.D6], entity_id="char-2",
                statement="Herbalism", traitset_id="ts-med")
    learner = _entity(id="char-2", name="Dmitri")
    repo = FakeRepo(
        traits=[FakeTrait("medicine", "ts-med")], traitsettings=[src, owned], entities=[learner],
        traitsets=[FakeTraitSet("ts-med", allow_duplicates=True)],
    )
    result = apply_effects(_entity(), [_copy_effect("char-2", "char-1:medicine")], repo)
    ts = result.new_trait_settings[0]
    assert ts.statement == "Field surgery"
    assert ts.id != "char-2:medicine"      # statement-distinguished key


def test_copy_trait_refuses_a_same_statement_duplicate():
    src = _ts("medicine", [DieType.D8], entity_id="char-1",
              statement="Field surgery", traitset_id="ts-med")
    owned = _ts("medicine", [DieType.D6], entity_id="char-2",
                statement="Field surgery", traitset_id="ts-med")
    learner = _entity(id="char-2", name="Dmitri")
    repo = FakeRepo(
        traits=[FakeTrait("medicine", "ts-med")], traitsettings=[src, owned], entities=[learner],
        traitsets=[FakeTraitSet("ts-med", allow_duplicates=True)],
    )
    result = apply_effects(_entity(), [_copy_effect("char-2", "char-1:medicine")], repo)
    assert result.new_trait_settings == []
    assert "already has medicine" in result.applied[0].summary


def test_copy_trait_without_a_resolved_ref_does_nothing():
    learner = _entity(id="char-2", name="Dmitri")
    repo = FakeRepo(entities=[learner])
    result = apply_effects(_entity(), [_copy_effect("char-2", "")], repo)
    assert result.new_trait_settings == []
    assert "no trait instance to copy" in result.applied[0].summary


# ── Gain honours the set's duplicate rule ────────────

def _gain_with_statement(action, trait_id, die, statement):
    return Effect(
        timing=EffectTiming.IMMEDIATE, type="modify_trait", action=action,
        target=trait_id, result=die, context={"statement": statement},
    )


def test_gain_allows_a_distinct_statement_when_the_set_allows_duplicates():
    """The portent model: one registry trait, many instances, keyed by statement."""
    owned = _ts("portent", [DieType.D6], traitset_id="ts-agenda", statement="Portent 3")
    repo = FakeRepo(
        traits=[FakeTrait("portent", "ts-agenda")], traitsettings=[owned],
        traitsets=[FakeTraitSet("ts-agenda", allow_duplicates=True)],
    )
    result = apply_effects(_entity(), [_gain_with_statement("gain", "portent", "d6", "Portent 5")], repo)
    assert len(result.new_trait_settings) == 1
    gained = result.new_trait_settings[0]
    assert gained.statement == "Portent 5"
    assert gained.id != "char-1:portent"      # statement-distinguished key
    assert gained.id != owned.id


def test_gain_refuses_a_same_statement_duplicate_when_the_set_allows_duplicates():
    owned = _ts("portent", [DieType.D6], traitset_id="ts-agenda", statement="Portent 3")
    repo = FakeRepo(
        traits=[FakeTrait("portent", "ts-agenda")], traitsettings=[owned],
        traitsets=[FakeTraitSet("ts-agenda", allow_duplicates=True)],
    )
    result = apply_effects(_entity(), [_gain_with_statement("gain", "portent", "d6", "Portent 3")], repo)
    assert result.new_trait_settings == []
    assert "already present" in result.applied[0].summary


def test_gain_still_refuses_a_distinct_statement_when_duplicates_are_disallowed():
    """The rule is the *set's*, not the statement's: a normal set stays one-per-trait."""
    owned = _ts("medicine", [DieType.D6], traitset_id="ts-x", statement="Herbalism")
    repo = FakeRepo(traits=[FakeTrait("medicine", "ts-x")], traitsettings=[owned])
    result = apply_effects(_entity(), [_gain_with_statement("gain", "medicine", "d6", "Field surgery")], repo)
    assert result.new_trait_settings == []
    assert "already present" in result.applied[0].summary


def test_gain_creates_distinct_ids_for_distinct_statements():
    repo = FakeRepo(
        traits=[FakeTrait("portent", "ts-agenda")],
        traitsets=[FakeTraitSet("ts-agenda", allow_duplicates=True)],
    )
    entity = _entity()
    result = apply_effects(
        entity,
        [_gain_with_statement("gain", "portent", "d6", "Portent 1"),
         _gain_with_statement("gain", "portent", "d6", "Portent 2")],
        repo,
    )
    ids = [ts.id for ts in result.new_trait_settings]
    assert len(ids) == 2
    assert ids[0] != ids[1]


def test_gain_or_step_up_creates_a_second_instance_for_a_distinct_statement():
    """A duplicate-allowing set gets a new instance, not a step-up of the first."""
    owned = _ts("portent", [DieType.D6], traitset_id="ts-agenda", statement="Portent 3")
    repo = FakeRepo(
        traits=[FakeTrait("portent", "ts-agenda")], traitsettings=[owned],
        traitsets=[FakeTraitSet("ts-agenda", allow_duplicates=True)],
    )
    result = apply_effects(
        _entity(), [_gain_with_statement("gain_or_step_up", "portent", "d6", "Portent 5")], repo)
    assert len(result.new_trait_settings) == 1
    assert result.updated_trait_settings == []
    assert owned.dice == [DieType.D6]          # the existing instance was not stepped


def test_cortex_gain_allows_a_distinct_statement_when_the_set_allows_duplicates():
    owned = _ts("portent", [DieType.D6], traitset_id="ts-agenda", statement="Portent 3")
    repo = FakeRepo(
        traits=[FakeTrait("portent", "ts-agenda")], traitsettings=[owned],
        traitsets=[FakeTraitSet("ts-agenda", allow_duplicates=True)],
    )
    result = apply_effects(
        _entity(), [_gain_with_statement("cortex_gain", "portent", "d8", "Portent 5")], repo)
    assert len(result.new_trait_settings) == 1
    assert result.new_trait_settings[0].statement == "Portent 5"
    assert owned.dice == [DieType.D6]          # the existing instance was not replaced


def test_negative_gain_keeps_the_complication_suffix_in_its_key():
    """A live row depends on the shape (`gmc-…:trait-…:complication`)."""
    repo = FakeRepo(traits=[FakeTrait("hazard", "ts-1")])
    negative = Effect(timing=EffectTiming.IMMEDIATE, type="modify_trait", action="gain",
                      target="hazard", result="d6", negative=True)
    result = apply_effects(_entity(), [negative], repo)
    assert result.new_trait_settings[0].id == "char-1:hazard:complication"
    positive = Effect(timing=EffectTiming.IMMEDIATE, type="modify_trait", action="gain",
                      target="hazard", result="d6")
    other = _entity(id="char-2")
    result2 = apply_effects(other, [positive], FakeRepo(traits=[FakeTrait("hazard", "ts-1")]))
    assert result2.new_trait_settings[0].id == "char-2:hazard"


# ── Trait move (steal) ───────────────────────

def _move_effect(recipient_id, source_ts_id):
    return Effect(
        timing=EffectTiming.IMMEDIATE, type="modify_trait", action="move",
        entity=recipient_id, refs={"trait": TargetRef(value=source_ts_id)},
    )


def test_move_trait_re_anchors_the_instance():
    src = _ts("asset", [DieType.D8], entity_id="char-1", traitset_id="ts-assets",
              statement="Family heirloom")
    src.sfx_ids = ["sfx-legacy"]
    thief = _entity(id="char-2", name="Kael")
    repo = FakeRepo(traits=[FakeTrait("asset", "ts-assets")], traitsettings=[src], entities=[thief])
    result = apply_effects(_entity(), [_move_effect("char-2", "char-1:asset")], repo)
    moved = result.new_trait_settings[0]
    assert moved.id == "char-2:asset"
    assert moved.entity_id == "char-2"
    assert moved.statement == "Family heirloom"
    # The same instance changing hands: its grants travel with it.
    assert moved.sfx_ids == ["sfx-legacy"]
    assert result.removed_trait_settings == [src]
    assert result.applied[0].summary == "moved asset from char-1 to char-2"


def test_move_trait_to_its_own_owner_is_a_no_op():
    src = _ts("asset", [DieType.D8], entity_id="char-1", traitset_id="ts-assets")
    repo = FakeRepo(traitsettings=[src])
    result = apply_effects(_entity(), [_move_effect("char-1", "char-1:asset")], repo)
    assert result.new_trait_settings == []
    assert result.removed_trait_settings == []
    assert "already on char-1" in result.applied[0].summary


def test_move_trait_refuses_when_the_recipient_already_has_it():
    src = _ts("asset", [DieType.D8], entity_id="char-1", traitset_id="ts-assets")
    owned = _ts("asset", [DieType.D6], entity_id="char-2", traitset_id="ts-assets")
    thief = _entity(id="char-2", name="Kael")
    repo = FakeRepo(traitsettings=[src, owned], entities=[thief])
    result = apply_effects(_entity(), [_move_effect("char-2", "char-1:asset")], repo)
    assert result.new_trait_settings == []
    assert result.removed_trait_settings == []
    assert "already has asset" in result.applied[0].summary


# ── Provenance + instance carry (B105) ───────
# The teach/gift/take rebuild needs the effect system to say *where a trait came
# from*; a copy that cannot name its giver is not a gift. See
# [[Character Growth#Trait Transfer — removed (2026-09-10)]].

def test_copy_records_the_giver_and_the_instance_it_came_from():
    src = _ts("medicine", [DieType.D8], entity_id="char-1", traitset_id="ts-med",
              statement="Field surgery")
    learner = _entity(id="char-2", name="Dmitri")
    repo = FakeRepo(traits=[FakeTrait("medicine", "ts-med")], traitsettings=[src],
                    entities=[learner])
    result = apply_effects(_entity(), [_copy_effect("char-2", "char-1:medicine")], repo)
    ts = result.new_trait_settings[0]
    assert ts.source_type == "gifted"          # the neutral default
    assert ts.source_entity_id == "char-1"     # who handed it over
    assert ts.source_trait_setting_id == src.id


def test_copy_can_say_a_trait_was_taught_rather_than_gifted():
    src = _ts("medicine", [DieType.D8], entity_id="char-1", traitset_id="ts-med")
    learner = _entity(id="char-2", name="Dmitri")
    repo = FakeRepo(traits=[FakeTrait("medicine", "ts-med")], traitsettings=[src],
                    entities=[learner])
    effect = _copy_effect("char-2", "char-1:medicine")
    effect.context = {"provenance": "taught"}
    result = apply_effects(_entity(), [effect], repo)
    assert result.new_trait_settings[0].source_type == "taught"


def test_copy_carries_the_instances_reach_and_order():
    """Instance config travels with the instance, the anchor does not."""
    src = _ts("medicine", [DieType.D8], entity_id="char-1", traitset_id="ts-med",
              order=3, locations_enabled=["loc-clinic"], locations_disabled=["loc-wilds"],
              tags=["field"])
    learner = _entity(id="char-2", name="Dmitri")
    repo = FakeRepo(traits=[FakeTrait("medicine", "ts-med")], traitsettings=[src],
                    entities=[learner])
    result = apply_effects(_entity(), [_copy_effect("char-2", "char-1:medicine")], repo)
    ts = result.new_trait_settings[0]
    assert ts.order == 3
    assert ts.locations_enabled == ["loc-clinic"]
    assert ts.locations_disabled == ["loc-wilds"]
    assert ts.tags == ["field"]


def test_move_records_that_the_trait_was_taken():
    src = _ts("asset", [DieType.D8], entity_id="char-1", traitset_id="ts-assets")
    thief = _entity(id="char-2", name="Kael")
    repo = FakeRepo(traits=[FakeTrait("asset", "ts-assets")], traitsettings=[src],
                    entities=[thief])
    result = apply_effects(_entity(), [_move_effect("char-2", "char-1:asset")], repo)
    moved = result.new_trait_settings[0]
    assert moved.source_type == "taken"
    assert moved.source_entity_id == "char-1"       # the previous owner
    assert moved.source_trait_setting_id == src.id


# ── Contest start (B105) ─────────────────────

def _contest_effect(opponent_id, **overrides):
    kwargs = dict(timing=EffectTiming.IMMEDIATE, type="contest", action="start",
                  target=opponent_id)
    kwargs.update(overrides)
    return Effect(**kwargs)


def _started(monkeypatch):
    """Capture ``start_contest`` calls without touching the live tracker."""
    from transversal.services import contest_tracker

    calls = []
    monkeypatch.setattr(contest_tracker, "start_contest",
                        lambda loc, eid, opp, uni="": calls.append((loc, eid, opp, uni)))
    return calls


def test_start_contest_opposes_the_subject_and_the_target(monkeypatch):
    calls = _started(monkeypatch)
    opponent = _entity(id="char-2", name="Wei Zhao")
    repo = FakeRepo(entities=[opponent])
    actor = _entity(id="char-1", current_location="loc-arena", current_universe="three_realms")
    result = apply_effects(actor, [_contest_effect("char-2")], repo)
    assert calls == [("loc-arena", "char-1", "char-2", "three_realms")]
    assert "contest with char-2" in result.applied[0].summary


def test_start_contest_refuses_itself(monkeypatch):
    calls = _started(monkeypatch)
    repo = FakeRepo()
    actor = _entity(id="char-1", current_location="loc-arena")
    result = apply_effects(actor, [_contest_effect("char-1")], repo)
    assert calls == []
    assert "cannot contest itself" in result.applied[0].summary


def test_start_contest_needs_a_location(monkeypatch):
    calls = _started(monkeypatch)
    opponent = _entity(id="char-2", name="Wei Zhao")
    repo = FakeRepo(entities=[opponent])
    result = apply_effects(_entity(id="char-1"), [_contest_effect("char-2")], repo)
    assert calls == []
    assert "no location to contest at" in result.applied[0].summary


def test_start_contest_honours_a_targeting_ban(monkeypatch):
    """The give-in ban exists so the loser cannot re-challenge — a rule may not
    route around it."""
    calls = _started(monkeypatch)
    opponent = _entity(id="char-2", name="Wei Zhao")
    repo = FakeRepo(entities=[opponent])
    actor = _entity(id="char-1", current_location="loc-arena")
    actor.targeting_bans = [TargetingBan(target_id="char-2")]
    result = apply_effects(actor, [_contest_effect("char-2")], repo)
    assert calls == []
    assert "cannot target char-2 yet" in result.applied[0].summary


def test_start_contest_refuses_an_unknown_opponent(monkeypatch):
    calls = _started(monkeypatch)
    repo = FakeRepo()
    actor = _entity(id="char-1", current_location="loc-arena")
    result = apply_effects(actor, [_contest_effect("char-nope")], repo)
    assert calls == []
    assert "no entity char-nope to contest" in result.applied[0].summary


def test_start_contest_creates_the_state_on_both_sides():
    """The real tracker, not a stand-in: a contest exists for *both* entities
    afterwards, and both are marked as contests rather than tests."""
    from transversal.domain import RollKind
    from transversal.services.contest_tracker import get_contest_tracker

    ct = get_contest_tracker()
    ct.clear_all()
    try:
        opponent = _entity(id="char-2", name="Wei Zhao")
        repo = FakeRepo(entities=[opponent])
        actor = _entity(id="char-1", current_location="loc-arena")
        result = apply_effects(actor, [_contest_effect("char-2")], repo)
        assert result.applied
        challenger, defendant = ct.get_contestants("loc-arena", "char-1")
        assert {challenger.entity_id, defendant.entity_id} == {"char-1", "char-2"}
        assert challenger.opposition_entity_id == "char-2"
        assert challenger.kind == RollKind.CONTEST
        assert defendant.kind == RollKind.CONTEST
    finally:
        ct.clear_all()


def test_start_contest_is_registered_on_the_engine_registry():
    """The engine dispatches through ``effect_registry``, so a handler only in
    ``_MUTATION_HANDLERS`` would never fire on a real trigger."""
    from types import SimpleNamespace
    import transversal.services.effects_applier as applier
    from transversal.services.effects_applier import EffectRegistry

    original = applier.effect_registry
    applier.effect_registry = EffectRegistry()
    try:
        raz = SimpleNamespace(spend=lambda *a, **k: None, earn=lambda *a, **k: None,
                              transfer=lambda *a, **k: None)
        em = SimpleNamespace(repo=None, create=lambda *a, **k: None)
        applier._register_core_handlers(em, raz)
        assert ("contest", "start") in applier.effect_registry._handlers
    finally:
        applier.effect_registry = original


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


def test_ending_a_timer_applies_its_revert_and_removes_it(monkeypatch):
    """`end_active_effect` ends the effect *now*: the row's stored undo is applied.

    (It used to delete the row without applying — quietly making a temporary change
    permanent, the opposite of what the label promises.)
    """
    import transversal.services.effects_applier as applier
    from transversal.domain import ScheduledEvent, Timer, TimerCombine
    ev = ScheduledEvent(
        id="se-1", target_type="entity", target_id="char-1",
        effect=Effect(type="modify_trait", action="enable", target="iron-will"),
        timers=[Timer(event="scene", remaining=2)],
        combine=TimerCombine.FIRST_TO_FIRE,
    )
    repo = FakeRepo(entities=[_entity()])
    repo.scheduled_events = [ev]
    fired = []
    monkeypatch.setattr(applier.effect_registry, "apply",
                        lambda eff, eid, u, ctx: fired.append((eff.type, eff.action)))
    result = apply_effects(_entity(), [_effect("entity", "cancel_scheduled_event", "se-1")], repo)
    assert fired == [("modify_trait", "enable")]
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


def test_dice_limit_source_rating_condition_threads_source():
    """Per-effect ``source_rating`` conditions gate on the resolved source."""
    repo = FakeRepo()
    effect = Effect(
        timing=EffectTiming.IMMEDIATE, type="modify_dice_limit", action="increase",
        result="1", context={"limit": "total"},
        conditions=[Condition(type=ConditionType.SOURCE_RATING, value="d4", operator="==")],
    )

    # Matching source → applies.
    entity = _entity()
    source = _ts("cultivation-stage", [DieType.D4])
    result = apply_effects(entity, [effect], repo, source=source, source_element="traitsetting")
    assert entity.total_dice_bonus == 1
    assert len(result.applied) == 1

    # No source threaded → skipped (guards against the source not reaching the applier).
    entity2 = _entity()
    result2 = apply_effects(entity2, [effect], repo)
    assert entity2.total_dice_bonus == 0
    assert result2.applied == []

    # Non-matching source rating → skipped.
    entity3 = _entity()
    source_d6 = _ts("cultivation-stage", [DieType.D6])
    result3 = apply_effects(entity3, [effect], repo, source=source_d6, source_element="traitsetting")
    assert entity3.total_dice_bonus == 0
    assert result3.applied == []


def test_dice_limit_pool_ref_targets_the_pool_owner():
    """A pool ref moves the limits on that pool's owner, not the acting entity."""
    repo = FakeRepo(entities=[_entity(id="char-2", name="Other")])
    actor = _entity()
    effect = Effect(
        timing=EffectTiming.IMMEDIATE, type="modify_dice_limit", action="increase",
        result="2", context={"limit": "total"},
        refs={"pool": TargetRef(value="pool:char-2")},
    )
    result = apply_effects(actor, [effect], repo)
    owner = repo.get_entity("char-2")
    assert owner.total_dice_bonus == 2
    assert actor.total_dice_bonus == 0
    assert owner in result.entities_to_update
    assert result.applied[0].summary == "increased total dice limit by 2 for char-2"


def test_dice_limit_pool_ref_on_the_actor_applies_in_place():
    """A pool ref naming the actor needs no redirect (and the owner has no location)."""
    actor = _entity()  # current_location defaults to None
    repo = FakeRepo(entities=[actor])
    effect = Effect(
        timing=EffectTiming.IMMEDIATE, type="modify_dice_limit", action="increase",
        result="1", context={"limit": "effect"},
        refs={"pool": TargetRef(value="pool:char-1")},
    )
    result = apply_effects(actor, [effect], repo)
    assert actor.effect_dice_bonus == 1
    assert result.applied[0].summary == "increased effect dice limit by 1 for char-1"


def test_dice_limit_without_pool_ref_falls_back_to_subject():
    """No ref → the pre-existing subject behaviour stays (stored effects keep working)."""
    repo = FakeRepo()
    entity = _entity()
    effect = Effect(
        timing=EffectTiming.IMMEDIATE, type="modify_dice_limit", action="increase",
        result="1", context={"limit": "total"},
    )
    apply_effects(entity, [effect], repo)
    assert entity.total_dice_bonus == 1


def test_dice_limit_unresolvable_pool_ref_falls_back_to_subject():
    """A pool ref that names no entity falls back rather than erroring."""
    repo = FakeRepo()
    entity = _entity()
    effect = Effect(
        timing=EffectTiming.IMMEDIATE, type="modify_dice_limit", action="increase",
        result="1", context={"limit": "total"},
        refs={"pool": TargetRef(value="pool:no-such-entity")},
    )
    apply_effects(entity, [effect], repo)
    assert entity.total_dice_bonus == 1


def test_dice_limit_pool_ref_schedules_the_revert_on_the_owner():
    """The inverse lands on the owner too, so expiry undoes that entity's bonus."""
    from transversal.domain import EffectDuration, Timer, TimerCombine
    repo = FakeRepo(entities=[_entity(id="char-2", name="Other")])
    actor = _entity()
    effect = Effect(
        timing=EffectTiming.IMMEDIATE, type="modify_dice_limit", action="increase",
        result="1", context={"limit": "total"},
        refs={"pool": TargetRef(value="pool:char-2")},
        duration=EffectDuration(timers=[Timer(event="scene", remaining=1)], combine=TimerCombine.FIRST_TO_FIRE),
    )
    apply_effects(actor, [effect], repo)
    event = repo.scheduled_events[0]
    assert event.target_type == "entity"
    assert event.target_id == "char-2"
    assert event.effect.action == "decrease"


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


def test_resolve_pool_rolls_and_sets_difficulty():
    from transversal.services.scene_state import get_scene_store

    store = get_scene_store()
    store.clear_all()
    store.save_pool("loc-1", "loc-1", [
        {"die": "d8", "source_kind": "trait", "source_id": "", "label": "complication", "ts_id": None},
        {"die": "d8", "source_kind": "trait", "source_id": "", "label": "base", "ts_id": None},
        {"die": "d6", "source_kind": "trait", "source_id": "", "label": "base", "ts_id": None},
    ])

    repo = FakeRepo()
    entity = _entity()
    effect = Effect(
        timing=EffectTiming.IMMEDIATE, type="modify_pool", action="resolve",
        refs={"pool": TargetRef(value="difficulty:loc-1")},
    )
    result = apply_effects(entity, [effect], repo)
    assert len(result.applied) == 1
    assert result.applied[0].summary.startswith("resolved loc-1 pool")

    pool = store.get_pool("loc-1", "loc-1")
    results = sorted([d["result"] for d in pool], reverse=True)
    assert store.get_difficulty("loc-1") == sum(results[:2])
    # The two highest dice are marked as the total so the client renders them.
    total_roles = [d for d in pool if d.get("role") == "total"]
    assert len(total_roles) == 2
    assert {d["result"] for d in total_roles} == set(results[:2])
    # The pool is committed (resolved), not left in the picking phase.
    assert store.get_phase("loc-1", "loc-1") == "resolved"
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

        def get_entity(self, eid):
            return entity if eid == entity.id else None

    effect = Effect(
        timing=EffectTiming.IMMEDIATE, type="travel", action="move",
        target_spec=_starter_location_spec(),
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
        target_spec=_starter_location_spec(),
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
        target_spec=_starter_location_spec(),
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
        timing=EffectTiming.IMMEDIATE, type="travel", action="move",
        target="loc-krasnoyarsk", entity="char-1",
        context={"transversal_type": "consciousness", "projection": "{choose_projection}"},
    )
    choice = PendingChoice(effect=effect, kind="projection", field="context.projection")
    resolved = resolve_choice(choice, "char-1:earth")
    assert resolved.context["projection"] == "char-1:earth"
    assert resolved.type == "travel" and resolved.action == "move"


def test_resolve_choice_can_be_reapplied():
    """The chosen body is what the re-applied effect arrives in."""
    entity = _entity()
    repo = TravelRepo(
        entities=[entity, _loc("peak", "earth")],
        projections=[_proj("char-1:earth", "char-1", "earth", location="peak")],
    )
    effect = Effect(
        timing=EffectTiming.IMMEDIATE, type="travel", action="move",
        target="peak",
        context={"transversal_type": "consciousness", "projection": "{choose_projection}"},
    )
    pending = apply_effects(entity, [effect], repo)
    assert len(pending.pending_choices) == 1
    assert pending.pending_choices[0].field == "context.projection"

    resolved = resolve_choice(pending.pending_choices[0], "char-1:earth")
    apply_effects(entity, [resolved], repo)
    assert entity.current_projection == "char-1:earth"
    assert entity.current_location == "peak"


# ── Random target mode ───────────────────────────────

def test_unknown_effect_is_passthrough():
    # An action with no mutation handler passes through to resolver context.
    # (`reroll_die` used to be the example here; it now mutates the scene store, so
    # the example is an outcome action that has no applier of its own.)
    entity = _entity()
    result = apply_effects(entity, [_effect("modify_outcome", "reroll_highest", "")], FakeRepo())
    assert len(result.passthrough) == 1
    assert result.passthrough[0].type == "modify_outcome"
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

    def list_all_projections(self):
        return list(self.projections.values())


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
        target="",
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
        target="yinling",
        refs={"projection": TargetRef(spec=_bodies_at("valley"))},
        context={"transversal_type": "consciousness", "projection": "{last_projection}"},
    )
    result = apply_effects(entity, [effect], repo)
    # only char-1:earth is in the Valley path, even though :2 is more recent
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
        target="yinling",
        refs={"projection": TargetRef(spec=_bodies_at("valley"))},
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
        target="peak",
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

# ── {choose:*} in scope ─────────────────────────────

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


def test_attune_honours_the_authored_scope():
    """An authored scope decides who the attunement reaches.

    ``self`` (the default) attunes only the carrier; ``domain`` radiates to
    everyone in the carrier's location subtree. Before this the scope came only
    from the *event* context, so an authored scope was silently ignored and every
    attunement was self-scoped.
    """
    from types import SimpleNamespace
    import transversal.services.effects_applier as applier
    from transversal.services.effects_applier import EffectRegistry
    from transversal.domain import AttunementScope

    class Repo:
        def __init__(self):
            self.entities = {"shrine": SimpleNamespace(id="shrine", attunements=[])}
            self.updated = []

        def get_entity(self, eid):
            return self.entities.get(eid)

        def update_entity(self, e):
            self.updated.append(e)
            self.entities[e.id] = e

    repo = Repo()
    original = applier.effect_registry
    applier.effect_registry = EffectRegistry()
    try:
        raz = SimpleNamespace(spend=lambda *a, **k: None, earn=lambda *a, **k: None, transfer=lambda *a, **k: None)
        em = SimpleNamespace(repo=repo, create=lambda *a, **k: None)
        applier._register_core_handlers(em, raz)

        domain = Effect(timing=EffectTiming.IMMEDIATE, type="attune", action="enable",
                        target="shrine", result="three_realms", context={"scope": "domain"})
        applier.effect_registry.apply(domain, "shrine", "earth", {})

        default = Effect(timing=EffectTiming.IMMEDIATE, type="attune", action="enable",
                         target="shrine", result="emberline")
        applier.effect_registry.apply(default, "shrine", "earth", {})
    finally:
        applier.effect_registry = original

    attunements = {a.universe: a.scope for a in repo.entities["shrine"].attunements}
    assert attunements["three_realms"] == AttunementScope.DOMAIN
    assert attunements["emberline"] == AttunementScope.SELF


def test_attune_takes_its_universe_from_the_resolved_projection():
    """A projection reference supersedes the authored universe string.

    The author's model: a capability comes from a *life*, so the universe is read
    off the projection the reference resolved to. Content written before the
    reference existed keeps working through the fallback.
    """
    from types import SimpleNamespace
    import transversal.services.effects_applier as applier
    from transversal.services.effects_applier import EffectRegistry
    from transversal.domain import TargetRef

    class Repo:
        def __init__(self):
            self.entities = {"wielder": SimpleNamespace(id="wielder", attunements=[])}
            self.projections = {
                "wielder:dreamlands": SimpleNamespace(id="wielder:dreamlands", universe="the-dreamlands"),
            }

        def get_entity(self, eid):
            return self.entities.get(eid)

        def get_projection(self, pid):
            return self.projections.get(pid)

        def update_entity(self, e):
            self.entities[e.id] = e

    repo = Repo()
    original = applier.effect_registry
    applier.effect_registry = EffectRegistry()
    try:
        raz = SimpleNamespace(spend=lambda *a, **k: None, earn=lambda *a, **k: None, transfer=lambda *a, **k: None)
        em = SimpleNamespace(repo=repo, create=lambda *a, **k: None)
        applier._register_core_handlers(em, raz)

        effect = Effect(
            timing=EffectTiming.IMMEDIATE, type="attune", action="enable", target="wielder",
            result="three_realms",  # the fallback, superseded below
            refs={"projection": TargetRef(name="projection", value="wielder:dreamlands")},
        )
        applier.effect_registry.apply(effect, "wielder", "earth", {})

        # A reference that resolves to nothing keeps the authored fallback.
        fallback = Effect(
            timing=EffectTiming.IMMEDIATE, type="attune", action="enable", target="wielder",
            result="three_realms",
            refs={"projection": TargetRef(name="projection", value="")},
        )
        applier.effect_registry.apply(fallback, "wielder", "earth", {})
    finally:
        applier.effect_registry = original

    attuned = {a.universe for a in repo.entities["wielder"].attunements}
    assert attuned == {"the-dreamlands", "three_realms"}


def test_publishing_an_output_binds_the_produced_trait():
    """A gain the author named binds its result into the activation scope — what
    a later effect's `select variable {beast}` resolves against."""
    from transversal.domain import DieType, TraitSetting
    from transversal.services.effects_applier.datatypes import BINDINGS_CONTEXT_KEY, EffectsResult
    from transversal.services.effects_applier.registry import publish_effect_output

    effect = Effect(timing=EffectTiming.IMMEDIATE, type="modify_trait", action="gain",
                    target="trait-beast", output="beast")
    ts = TraitSetting(id="char-1:beast", entity_id="char-1", trait_id="trait-beast",
                      traitset_id="ts-x", dice=[DieType.D6])
    ctx: dict = {}

    publish_effect_output(effect, EffectsResult(new_trait_settings=[ts]), ctx)

    binding = ctx[BINDINGS_CONTEXT_KEY]["beast"]
    assert (binding.value, binding.element, binding.cardinality) == (
        "char-1:beast", "traitsetting", "one")


def test_a_named_result_is_selectable_by_a_later_step():
    from transversal.domain import DieType, TraitSetting
    from transversal.services.target_resolver import Binding, TargetContext, resolve
    from transversal.services.target_spec import TargetSpec

    ts = TraitSetting(id="char-1:beast", entity_id="char-1", trait_id="trait-beast",
                      traitset_id="ts-x", dice=[DieType.D6])
    repo = FakeRepo(traitsettings=[ts])
    spec = TargetSpec(steps=[{"kind": "select", "collection": "variable", "variable": "beast"}])
    context = TargetContext(repo=repo, bindings={
        "beast": Binding(value="char-1:beast", values=["char-1:beast"],
                         element="traitsetting", cardinality="one"),
    })

    resolution = resolve(spec, context)

    assert [getattr(v, "id", v) for v in resolution.values] == ["char-1:beast"]
    assert not resolution.errors


# ── Play as Rating ───────────────────────────────────

def _play_effect(ts_id, die):
    return Effect(timing=EffectTiming.IMMEDIATE, type="modify_roll",
                  action="play_as_rating", target=ts_id, result=die)


def _play_repo(**overrides):
    ts = _ts("distinction", [DieType.D8], traitset_id="ts-dist")
    return FakeRepo(traits=[FakeTrait("distinction", "ts-dist")],
                    traitsettings=[ts], **overrides), ts


def test_play_as_rating_temporarily_sets_the_trait_rating():
    """The rating *is* the played size, so a pooled die added later reads it too."""
    from transversal.services.scene_state import get_scene_store

    store = get_scene_store()
    store.clear_all()
    repo, ts = _play_repo()
    result = apply_effects(_entity(), [_play_effect(ts.id, "d4")], repo)
    assert [d.value for d in ts.dice] == ["d4"]
    assert result.updated_trait_settings == [ts]
    assert "plays as d4" in result.applied[0].summary
    store.clear_all()


def test_play_as_rating_matches_every_die_the_trait_contributes():
    """A 2d8 trait plays as 2d4 — a multi-die rating is not half-played."""
    from transversal.services.scene_state import get_scene_store

    store = get_scene_store()
    store.clear_all()
    ts = _ts("technique", [DieType.D8, DieType.D8], traitset_id="ts-tech")
    repo = FakeRepo(traits=[FakeTrait("technique", "ts-tech")], traitsettings=[ts])
    apply_effects(_entity(), [_play_effect(ts.id, "d6")], repo)
    assert [d.value for d in ts.dice] == ["d6", "d6"]
    store.clear_all()


def test_play_as_rating_pulls_the_open_pool_dice_to_the_new_size():
    """The rolled pool follows its trait — `resync_pool_dice_for_trait`."""
    from transversal.services.scene_state import get_scene_store

    store = get_scene_store()
    store.clear_all()
    repo, ts = _play_repo()
    store.save_pool("loc-1", "char-1", [
        {"die": "d8", "source_kind": "trait", "source_id": ts.id, "label": "Distinction", "ts_id": ts.id},
    ])
    apply_effects(_entity(current_location="loc-1"), [_play_effect(ts.id, "d4")], repo)
    assert [d["die"] for d in store.get_pool("loc-1", "char-1")] == ["d4"]
    store.clear_all()


def test_play_as_rating_restores_the_prior_rating_on_expiry():
    """The inverse is `restore_die`: it restores the whole prior list, and the pool
    follows back."""
    from transversal.services.scene_state import get_scene_store

    store = get_scene_store()
    store.clear_all()
    repo, ts = _play_repo()
    store.save_pool("loc-1", "char-1", [
        {"die": "d8", "source_kind": "trait", "source_id": ts.id, "label": "Distinction", "ts_id": ts.id},
    ])
    apply_effects(_entity(current_location="loc-1"), [_play_effect(ts.id, "d4")], repo)
    assert [d.value for d in ts.dice] == ["d4"]

    revert = Effect(timing=EffectTiming.IMMEDIATE, type="modify_roll", action="restore_die",
                    target=f"rating:0:{ts.id}", context={"prior_dice": ["d8"]})
    apply_effects(_entity(current_location="loc-1"), [revert], repo)
    assert [d.value for d in ts.dice] == ["d8"]
    assert [d["die"] for d in store.get_pool("loc-1", "char-1")] == ["d8"]
    store.clear_all()


def test_play_as_rating_without_a_target_does_nothing():
    repo, _ = _play_repo()
    result = apply_effects(_entity(), [_play_effect("", "d4")], repo)
    assert result.applied[0].summary == "no trait instance (unset)"


def test_play_as_rating_declares_a_traitsetting_path_not_an_implicit_target():
    """The old `implicit_target={source_trait}` was never bound by any firing path,
    so the effect silently did nothing; the path is now the only way to name the
    trait (the rule's own source is `select source`)."""
    from transversal.services.effects_registry import get_action_meta
    meta = get_action_meta("play_as_rating")
    assert meta is not None
    assert meta.implicit_target is None
    assert meta.path_element == ("traitsetting",)
    assert meta.inverse == ("modify_roll", "restore_die")


# ── Invert Polarity ──────────────────────────────────

def test_invert_polarity_flips_a_complication_to_an_asset():
    """The author's call: flipping the flag is enough — the instance keeps its id,
    its traitset and its grants, and only `polarity` moves."""
    ts = _ts("hazard", [DieType.D6], traitset_id="ts-1", polarity=Polarity.NEGATIVE)
    repo = FakeRepo(traits=[FakeTrait("hazard", "ts-1")], traitsettings=[ts])
    effect = Effect(timing=EffectTiming.IMMEDIATE, type="modify_trait",
                    action="invert_polarity", target="char-1:hazard")
    result = apply_effects(_entity(), [effect], repo)
    assert ts.polarity == Polarity.POSITIVE
    assert result.updated_trait_settings == [ts]
    assert "negative → positive" in result.applied[0].summary


def test_invert_polarity_flips_back():
    """Two values, so the inverse of a flip is the same flip."""
    ts = _ts("hazard", [DieType.D6], traitset_id="ts-1", polarity=Polarity.POSITIVE)
    repo = FakeRepo(traits=[FakeTrait("hazard", "ts-1")], traitsettings=[ts])
    effect = Effect(timing=EffectTiming.IMMEDIATE, type="modify_trait",
                    action="invert_polarity", target="char-1:hazard")
    apply_effects(_entity(), [effect], repo)
    assert ts.polarity == Polarity.NEGATIVE


def test_invert_polarity_keeps_the_instances_identity():
    """Explicitly *not* a re-home: the id, traitset and dice are untouched, which is
    why a definition change is a separate Change Trait."""
    ts = _ts("hazard", [DieType.D8], traitset_id="ts-1", polarity=Polarity.NEGATIVE,
             statement="Twisted ankle")
    ts.sfx_ids = ["sfx-legacy"]
    before = (ts.id, ts.traitset_id, [d.value for d in ts.dice], ts.statement)
    repo = FakeRepo(traits=[FakeTrait("hazard", "ts-1")], traitsettings=[ts])
    effect = Effect(timing=EffectTiming.IMMEDIATE, type="modify_trait",
                    action="invert_polarity", target="char-1:hazard")
    apply_effects(_entity(), [effect], repo)
    assert (ts.id, ts.traitset_id, [d.value for d in ts.dice], ts.statement) == before
    assert ts.sfx_ids == ["sfx-legacy"]


def test_invert_polarity_without_an_instance_says_so():
    repo = FakeRepo()
    effect = Effect(timing=EffectTiming.IMMEDIATE, type="modify_trait",
                    action="invert_polarity", target="char-1:nope")
    result = apply_effects(_entity(), [effect], repo)
    assert "no trait instance" in result.applied[0].summary


def test_invert_polarity_replaced_convert_complication():
    from transversal.services.effects_registry import get_action_meta
    assert get_action_meta("convert_complication").retired is True
    meta = get_action_meta("invert_polarity")
    assert meta.retired is False
    assert meta.path_element == ("traitsetting",)
    assert meta.inverse == ("modify_trait", "invert_polarity")


# ── Anchoring a trait to a relationship edge (B153) ───

class TypedRelationshipRepo(RelationshipFakeRepo):
    """Only serves an edge of the requested type — the hardcoded-type bug cannot
    hide behind a permissive double."""

    def __init__(self, edges):
        super().__init__()
        self.edges = edges            # {(to_id, type): key}

    def get_relationship(self, entity_id, other_id, rel_type):
        key = self.edges.get((other_id, rel_type))
        return {"_key": key} if key else None


def _rel_effect(action="gain", **context):
    return Effect(timing=EffectTiming.IMMEDIATE, type="modify_trait", action=action,
                  target="trait-rel-rank", result="d4", context=context)


def test_a_trait_can_anchor_to_a_non_membership_edge():
    """`relation` edges are the majority of live relationship-anchored traits
    (264 vs 43 membership), so the type has to be readable rather than assumed."""
    repo = TypedRelationshipRepo({("fac-1", "relation"): "edge:char-1:fac-1:relation"})
    effect = _rel_effect(relationship="fac-1", relationship_type="relation")
    result = apply_effects(_entity(), [effect], repo)
    ts = result.new_trait_settings[0]
    assert ts.from_type == "relationship"
    assert ts.entity_id == "edge:char-1:fac-1:relation"


def test_membership_stays_the_default():
    repo = TypedRelationshipRepo({("fac-1", "membership"): "edge:char-1:fac-1:membership"})
    effect = _rel_effect(relationship="fac-1")   # no relationship_type
    result = apply_effects(_entity(), [effect], repo)
    assert result.new_trait_settings[0].entity_id == "edge:char-1:fac-1:membership"


def test_a_missing_edge_is_an_error_not_an_entity_trait():
    """The bug: a `relationship` naming an edge that does not exist fell through to
    the entity, so the die landed on the character and nothing said so."""
    repo = TypedRelationshipRepo({})
    effect = _rel_effect(relationship="fac-1", relationship_type="relation")
    result = apply_effects(_entity(), [effect], repo)
    assert result.new_trait_settings == []
    assert "no relationship to fac-1 (relation)" in result.applied[0].summary
    assert "create it first" in result.applied[0].summary


def test_a_wrong_type_is_reported_with_the_type_asked_for():
    """Asking for membership when only a relation exists is the *same* silent-miss
    class, so it reports too."""
    repo = TypedRelationshipRepo({("fac-1", "relation"): "edge:char-1:fac-1:relation"})
    effect = _rel_effect(relationship="fac-1", relationship_type="membership")
    result = apply_effects(_entity(), [effect], repo)
    assert result.new_trait_settings == []
    assert "(membership)" in result.applied[0].summary


def test_gain_or_step_up_and_cortex_gain_report_the_missing_edge_too():
    repo = TypedRelationshipRepo({})
    effect = _rel_effect(action="gain_or_step_up", relationship="fac-1")
    assert "no relationship to fac-1" in apply_effects(_entity(), [effect], repo).applied[0].summary
    effect2 = _rel_effect(action="cortex_gain", relationship="fac-1")
    assert "no relationship to fac-1" in apply_effects(_entity(), [effect2], repo).applied[0].summary


def test_the_relationship_anchor_is_its_own_verb():
    """A tie is a different *owner*, so it is a different verb.

    `Gain Trait` used to carry "Relationship with" + "Relationship type" beside its
    entity targeting — two context fields that asked for an entity id in a text
    box and anchored the trait somewhere other than the field you were reading.
    The anchor is a **path** now, declared by the verb that means it, and `Gain
    Trait` no longer offers it at all.
    """
    from transversal.services.effects_registry import get_action_meta

    names = [f.name for f in get_action_meta("gain_trait").context_fields]
    assert "relationship" not in names and "relationship_type" not in names

    tie = get_action_meta("gain_relationship_trait")
    assert tie.owner_elements == ("relationship",)
    assert tie.effect_action == "gain_relationship"

    facet = get_action_meta("gain_subtrait")
    assert facet.owner_elements == ("traitsetting",)
    assert facet.effect_action == "gain_subtrait"
    # The agenda fields belong to the verb that creates a nested instance.
    facet_fields = [f.name for f in facet.context_fields]
    assert "order" in facet_fields and "enabled" in facet_fields


# ── Gain: "create only if missing" ───────────────────

def _gain_if_not_exists(trait="medicine", statement=""):
    return Effect(timing=EffectTiming.IMMEDIATE, type="modify_trait", action="gain",
                  target=trait, result="d8", output="it",
                  context={"if_not_exists": "true", "statement": statement})


def test_gain_if_not_exists_creates_when_absent():
    repo = FakeRepo(traits=[FakeTrait("medicine", "ts-x")])
    result = apply_effects(_entity(), [_gain_if_not_exists()], repo)
    assert len(result.new_trait_settings) == 1
    assert result.found_trait_settings == []
    assert "gained medicine" in result.applied[0].summary


def test_gain_if_not_exists_found_an_existing_instance():
    """The point of the flag: nothing is written, and the step still names the
    instance that is there — so a later step can act on whichever case happened."""
    owned = _ts("medicine", [DieType.D6], traitset_id="ts-x")
    repo = FakeRepo(traits=[FakeTrait("medicine", "ts-x")], traitsettings=[owned])
    result = apply_effects(_entity(), [_gain_if_not_exists()], repo)
    assert result.new_trait_settings == []
    assert result.found_trait_settings == [owned]
    assert "already present — using it" in result.applied[0].summary


def test_gain_without_the_flag_still_refuses_silently():
    """Default unchanged: no flag, no output binding — nothing moves for existing
    content."""
    owned = _ts("medicine", [DieType.D6], traitset_id="ts-x")
    repo = FakeRepo(traits=[FakeTrait("medicine", "ts-x")], traitsettings=[owned])
    plain = Effect(timing=EffectTiming.IMMEDIATE, type="modify_trait", action="gain",
                   target="medicine", result="d8")
    result = apply_effects(_entity(), [plain], repo)
    assert result.new_trait_settings == [] and result.found_trait_settings == []


def test_the_found_instance_is_what_the_output_name_binds():
    """`publish_effect_output` reads the found list too, which is the junction that
    makes 'name the trait, however it got here' work."""
    from transversal.services.effects_applier.registry import publish_effect_output
    from transversal.services.target_resolver import Binding
    from transversal.services.target_spec import TargetSpec

    owned = _ts("medicine", [DieType.D6], traitset_id="ts-x")
    repo = FakeRepo(traits=[FakeTrait("medicine", "ts-x")], traitsettings=[owned])
    effect = _gain_if_not_exists()
    result = apply_effects(_entity(), [effect], repo)
    ctx = {}
    publish_effect_output(effect, result, ctx)
    bindings = ctx.get("_bindings") or {}
    bound = bindings.get("it")
    assert bound is not None, ctx
    assert (bound.value if isinstance(bound, Binding) else bound) == owned.id


def test_gain_if_not_exists_is_authorable_only_on_gain_trait():
    from transversal.services.effects_registry import get_action_meta
    names = [f.name for f in get_action_meta("gain_trait").context_fields]
    assert "if_not_exists" in names
    # Not on the step-up variants: a "don't touch it" flag would contradict them.
    for aid in ("gain_or_step_up_trait", "cortex_gain_trait"):
        assert "if_not_exists" not in [f.name for f in get_action_meta(aid).context_fields]


# ── Reroll Die ───────────────────────────────────────

def _pool_with(dice):
    """Put dice in the scene store and return (store, effect target for index 0)."""
    from transversal.services.scene_state import get_scene_store

    store = get_scene_store()
    store.clear_all()
    store.save_pool("loc-1", "char-1", list(dice))
    return store


def _pool_die(ts_id="ts-hinder", die="d8", result=None):
    return {"die": die, "source_kind": "trait", "source_id": ts_id,
            "label": "Hinder", "ts_id": ts_id, "result": result}


def _reroll_effect(result=""):
    eff = Effect(timing=EffectTiming.IMMEDIATE, type="modify_roll", action="reroll_die",
                 target="die:loc-1:char-1:0")
    eff.result = result or None
    return eff


def test_reroll_die_rolls_the_targeted_die_again():
    store = _pool_with([_pool_die(result=3)])
    repo = FakeRepo(entities=[_entity(current_location="loc-1")])
    result = apply_effects(_entity(current_location="loc-1"), [_reroll_effect()], repo)
    entry = store.get_pool("loc-1", "char-1")[0]
    assert 1 <= entry["result"] <= 8          # a d8 came back
    assert entry["tier"] in ("fail", "marginal", "success", "exceptional", "perfect")
    assert "rerolled" in result.applied[0].summary
    store.clear_all()


def test_reroll_die_touches_only_the_targeted_die():
    """The author's brief: only the targeted dice re-roll."""
    store = _pool_with([_pool_die(result=3), _pool_die(ts_id="other", die="d6", result=6)])
    repo = FakeRepo(entities=[_entity(current_location="loc-1")])
    apply_effects(_entity(current_location="loc-1"), [_reroll_effect()], repo)
    pool = store.get_pool("loc-1", "char-1")
    assert pool[1]["result"] == 6              # untouched
    assert pool[0]["die"] == "d8"              # size unchanged — this rerolls a result
    store.clear_all()


def test_reroll_die_stays_in_the_picking_phase():
    """It fires while the results are on screen, so it does not send the pool back
    to assembly."""
    from transversal.services.scene_state import get_scene_store

    store = _pool_with([_pool_die(result=3)])
    store.set_phase("loc-1", "char-1", "picking")
    repo = FakeRepo(entities=[_entity(current_location="loc-1")])
    apply_effects(_entity(current_location="loc-1"), [_reroll_effect()], repo)
    assert store.get_phase("loc-1", "char-1") == "picking"
    store.clear_all()


def test_reroll_die_restores_the_prior_result_when_it_is_the_revert():
    """The inverse is this action carrying the prior result."""
    store = _pool_with([_pool_die(result=7)])
    repo = FakeRepo(entities=[_entity(current_location="loc-1")])
    apply_effects(_entity(current_location="loc-1"), [_reroll_effect(result="2")], repo)
    assert store.get_pool("loc-1", "char-1")[0]["result"] == 2
    store.clear_all()


def test_reroll_die_refuses_a_rating_die():
    """A rating die has no result to reroll, and says so rather than doing nothing."""
    repo = FakeRepo()
    eff = Effect(timing=EffectTiming.IMMEDIATE, type="modify_roll", action="reroll_die",
                 target="rating:0:char-1:medicine")
    result = apply_effects(_entity(), [eff], repo)
    assert "needs a pool die" in result.applied[0].summary


def test_reroll_die_is_pool_only_and_has_an_inverse():
    from transversal.services.effects_registry import get_action_meta, get_inverse
    meta = get_action_meta("reroll_die")
    assert meta.path_element == ("die",)
    assert meta.supports_duration is False   # a pool is rebuilt every roll
    assert meta.inverse == ("modify_roll", "reroll_die")
    assert get_inverse("modify_roll", "reroll_die") == (("modify_roll", "reroll_die"), True)


# ── Enable Trait / Set Polarity (B127's remaining vocabulary) ───

def test_enable_trait_is_a_first_class_action():
    """The handler existed as `disable`'s duration-revert and had no name of its
    own, so a rule could not enable a disabled trait directly (the portent agenda)."""
    from transversal.services.effects_registry import get_action_meta
    meta = get_action_meta("enable_trait")
    assert meta is not None and meta.retired is False
    assert (meta.effect_type, meta.effect_action) == ("modify_trait", "enable")
    assert meta.inverse == ("modify_trait", "disable")


def test_enabling_a_disabled_trait_works():
    ts = _ts("portent", [DieType.D6], traitset_id="ts-agenda", enabled=False)
    repo = FakeRepo(traits=[FakeTrait("portent", "ts-agenda")], traitsettings=[ts])
    effect = Effect(timing=EffectTiming.IMMEDIATE, type="modify_trait",
                    action="enable", target="char-1:portent")
    result = apply_effects(_entity(), [effect], repo)
    assert ts.enabled is True
    assert "enabled" in result.applied[0].summary


def test_set_polarity_sets_the_value_it_is_given():
    ts = _ts("hazard", [DieType.D6], traitset_id="ts-1", polarity=Polarity.POSITIVE)
    repo = FakeRepo(traits=[FakeTrait("hazard", "ts-1")], traitsettings=[ts])
    effect = Effect(timing=EffectTiming.IMMEDIATE, type="modify_trait",
                    action="set_polarity", target="char-1:hazard",
                    context={"polarity": "negative"})
    result = apply_effects(_entity(), [effect], repo)
    assert ts.polarity == Polarity.NEGATIVE
    assert "positive → negative" in result.applied[0].summary


def test_set_polarity_is_idempotent_unlike_a_flip():
    """The difference that justifies its own action: firing twice lands the same
    place, where Invert Polarity would return."""
    ts = _ts("hazard", [DieType.D6], traitset_id="ts-1", polarity=Polarity.NEGATIVE)
    repo = FakeRepo(traits=[FakeTrait("hazard", "ts-1")], traitsettings=[ts])
    effect = Effect(timing=EffectTiming.IMMEDIATE, type="modify_trait",
                    action="set_polarity", target="char-1:hazard",
                    context={"polarity": "negative"})
    for _ in range(2):
        result = apply_effects(_entity(), [effect], repo)
    assert ts.polarity == Polarity.NEGATIVE
    assert "already negative" in result.applied[0].summary


def test_reroll_highest_is_retired_in_favour_of_a_path():
    from transversal.services.effects_registry import get_action_meta
    assert get_action_meta("reroll_highest").retired is True
    assert get_action_meta("reroll_die").retired is False


# ── Learning (fog of war, B121) ──────────────

def test_learn_unions_into_known_to_without_clobbering():
    """A GM assuming a hidden occupant must not wipe what it already knew, so the
    action unions rather than writes."""
    from transversal.domain import EntityType
    actor = _entity(id="gmc-1", type=EntityType.GMC, current_location="loc-1")
    actor.known_to = ["char-old"]
    other = _entity(id="char-2", name="Bystander")
    repo = FakeRepo(entities=[other])
    result = apply_effects(actor, [_effect("entity", "learn", "char-2")], repo)
    assert actor.known_to == ["char-old", "char-2"]
    assert "learns char-2" in result.applied[0].summary


def test_learning_someone_already_known_changes_nothing():
    actor = _entity(id="gmc-1", current_location="loc-1")
    actor.known_to = ["char-2"]
    repo = FakeRepo(entities=[_entity(id="char-2")])
    result = apply_effects(actor, [_effect("entity", "learn", "char-2")], repo)
    assert actor.known_to == ["char-2"]
    assert "already knows char-2" in result.applied[0].summary


def test_an_entity_is_not_made_known_to_itself():
    actor = _entity(id="gmc-1", current_location="loc-1")
    result = apply_effects(actor, [_effect("entity", "learn", "gmc-1")], FakeRepo())
    assert actor.known_to == []
    assert "already knows itself" in result.applied[0].summary


def test_learn_is_registered_on_the_engine_registry():
    """The engine dispatches through ``effect_registry`` — a handler only in
    ``_MUTATION_HANDLERS`` would never fire on a real trigger."""
    from types import SimpleNamespace
    import transversal.services.effects_applier as applier
    from transversal.services.effects_applier import EffectRegistry

    original = applier.effect_registry
    applier.effect_registry = EffectRegistry()
    try:
        raz = SimpleNamespace(spend=lambda *a, **k: None, earn=lambda *a, **k: None,
                              transfer=lambda *a, **k: None)
        em = SimpleNamespace(repo=None, create=lambda *a, **k: None)
        applier._register_core_handlers(em, raz)
        assert ("entity", "learn") in applier.effect_registry._handlers
    finally:
        applier.effect_registry = original


def test_taking_control_fires_the_assumed_trigger(monkeypatch):
    """The GM-assumes-an-occupant moment is `record_control(stamp=False)`; the
    trigger reports it for *both* audiences and the rule's conditions narrow it."""
    from transversal.services import player_manager as pm
    from transversal.services.player_manager import PlayerManager

    fired = []
    monkeypatch.setattr(pm, "_current_body", {})
    from transversal.services import state_events
    monkeypatch.setattr(state_events, "fire_state_sfx",
                        lambda eid, uni, ev, ctx=None: fired.append((eid, ev)))

    manager = PlayerManager.__new__(PlayerManager)
    manager._repo = None
    manager.record_control("player-1", "gmc-1", stamp=False)

    assert fired == [("gmc-1", "assumed")]


# ── Granting a rule (the lost-update trap) ───

class _FreshReadRepo(FakeRepo):
    """`get_entity` hands back a **new** object on every read, like the real
    repository does.

    This is what made a grant to the committed entity vanish: the owner helper
    read its own copy, wrote the rule through it, and then `commit_effects` saved
    *its* copy — taken before the grant — over the top. The action reported
    success and the rule was gone.
    """

    def get_entity(self, entity_id):
        found = self.entities.get(entity_id)
        return found.model_copy(deep=True) if found is not None else None

    def update_entity(self, entity):
        self.entities[entity.id] = entity.model_copy(deep=True)
        return entity


def test_a_rule_granted_to_the_committed_entity_survives_the_commit():
    from transversal.services.effects_commit import commit_effects

    target = _entity(id="char-2", name="Dmitri")
    repo = _FreshReadRepo(entities=[target])
    effect = Effect(timing=EffectTiming.IMMEDIATE, type="sfx", action="grant",
                    target="sfx-teleport-to-main")

    result = commit_effects(target, [effect], repo)

    assert result.applied and "granted" in result.applied[0].summary
    assert "sfx-teleport-to-main" in repo.entities["char-2"].sfx_ids


def test_a_rule_granted_to_someone_else_is_persisted_too():
    """The other direction: the recipient is not the primary, so it travels via
    `entities_to_update` and must land as well."""
    from transversal.services.effects_commit import commit_effects

    actor = _entity(id="char-1", name="Tester")
    learner = _entity(id="char-2", name="Dmitri")
    repo = _FreshReadRepo(entities=[actor, learner])
    effect = Effect(timing=EffectTiming.IMMEDIATE, type="sfx", action="grant",
                    entity="char-2", target="sfx-teleport-to-main")

    result = commit_effects(actor, [effect], repo)

    assert result.applied and "granted" in result.applied[0].summary
    assert "sfx-teleport-to-main" in repo.entities["char-2"].sfx_ids


# ── Naming a die by path (B98's effect half) ───
#
# "create the hazard at that die's effect die": a result_spec's aggregate over a
# die-typed field arrives as the *size*, and a size on the ladder is the die.

def test_a_spec_value_that_is_a_die_size_names_that_die():
    from transversal.domain import DieType
    from transversal.services.effects_applier.entry import _die_from_spec_value

    for size, name in ((4, "d4"), (6, "d6"), (8, "d8"), (10, "d10"), (12, "d12")):
        assert _die_from_spec_value(size) == name
    assert _die_from_spec_value(DieType.D10) == "d10"
    assert _die_from_spec_value({"rating": "d6"}) == "d6"
    assert _die_from_spec_value("d8") == "d8"
    # Anything not on the ladder names no die, so a wrong path cannot invent one.
    assert _die_from_spec_value(3) is None
    assert _die_from_spec_value(None) is None


def test_a_result_spec_reads_the_unchosen_source_dies_effect_die():
    """The whole route, with the roll in context: filter to *my* die that was not
    chosen, then read the die it left."""
    from transversal.services.effects_applier.datatypes import (
        BINDINGS_CONTEXT_KEY,
        SOURCE_CONTEXT_KEY,
        SOURCE_ELEMENT_CONTEXT_KEY,
    )
    from transversal.services.effects_applier.entry import resolve_effect_result

    class Repo:
        def get_entity(self, eid):
            return _entity(id=eid, current_location="loc-1")

    dice = [
        {"ts_id": "ts-scar", "role": None, "result": 3, "rating": "d6", "effect_die": "d8"},
        {"ts_id": "ts-scar", "role": "total", "result": 5, "rating": "d8", "effect_die": "d6"},
    ]
    effect = Effect(
        timing=EffectTiming.ON_RESULT, type="modify_trait", action="gain",
        target="trait-scar", result="d6",
        result_spec=TargetSpec.model_validate({"steps": [
            {"kind": "select", "collection": "rolled_dice"},
            {"kind": "filter", "field": "ts_id", "operator": "==", "value": "{trait_setting}"},
            {"kind": "filter", "field": "role", "operator": "==", "value": None},
            {"kind": "aggregate", "fn": "max", "field": "effect_die"},
        ]}),
    )
    context = {
        "rolls": dice,
        BINDINGS_CONTEXT_KEY: {
            "trait_setting": Binding(value="ts-scar", values=["ts-scar"],
                                     element="traitsetting", cardinality="one"),
        },
        SOURCE_CONTEXT_KEY: _ts("scar", [DieType.D8]),
        SOURCE_ELEMENT_CONTEXT_KEY: "traitsetting",
    }
    out = resolve_effect_result(effect, "char-2", Repo(), context)
    assert out.result == "d8"      # the unchosen die's effect die
    assert out.result_spec is None

    # No unchosen die of mine in the roll: the result is cleared rather than left
    # standing, so nothing is invented (the handler reports "no die rating").
    chosen_only = dict(context, rolls=[dict(dice[0], role="effect"), dice[1]])
    cleared = resolve_effect_result(effect, "char-2", Repo(), chosen_only)
    assert cleared.result is None


def test_a_polarity_revert_restores_the_prior_value():
    """A duration's undo arrives in `result` (the inverse captures the prior), and
    reading only the context made the revert re-apply the polarity it was undoing —
    so the trait kept the temporary value for good."""
    ts = _ts("hazard", [DieType.D6], traitset_id="ts-1", polarity=Polarity.POSITIVE)
    repo = FakeRepo(traits=[FakeTrait("hazard", "ts-1")], traitsettings=[ts])
    forward = Effect(timing=EffectTiming.IMMEDIATE, type="modify_trait",
                     action="set_polarity", target="char-1:hazard",
                     context={"polarity": "negative"})
    apply_effects(_entity(), [forward], repo)
    assert ts.polarity == Polarity.NEGATIVE

    # The revert `build_revert` produces: same action, the prior in `result`.
    revert = Effect(timing=EffectTiming.IMMEDIATE, type="modify_trait",
                    action="set_polarity", target="char-1:hazard", result="positive",
                    context={"polarity": "negative"})
    result = apply_effects(_entity(), [revert], repo)
    assert ts.polarity == Polarity.POSITIVE
    assert "negative → positive" in result.applied[0].summary


# ── Rating type (B100) ───────────────────────

def _rating_type_effect(value, ts_id="char-1:technique"):
    return Effect(timing=EffectTiming.IMMEDIATE, type="modify_trait",
                  action="set_rating_type", target=ts_id, result=value)


def test_change_rating_type_sets_what_the_author_named():
    ts = _ts("technique", [DieType.D4], traitset_id="ts-1",
             rating_type=RatingType.CHALLENGE)
    repo = FakeRepo(traits=[FakeTrait("technique", "ts-1")], traitsettings=[ts])
    result = apply_effects(_entity(), [_rating_type_effect("static")], repo)
    assert ts.rating_type == RatingType.STATIC
    assert "challenge → static" in result.applied[0].summary


def test_change_rating_type_is_idempotent():
    ts = _ts("technique", [DieType.D4], traitset_id="ts-1", rating_type=RatingType.RESOURCE)
    repo = FakeRepo(traits=[FakeTrait("technique", "ts-1")], traitsettings=[ts])
    for _ in range(2):
        result = apply_effects(_entity(), [_rating_type_effect("resource")], repo)
    assert ts.rating_type == RatingType.RESOURCE
    assert "already a resource trait" in result.applied[0].summary


def test_a_rating_type_revert_restores_the_prior_type():
    """The reason the value lives in `result`, not the context: a duration's undo
    arrives there, so restoring needs no second mechanism."""
    ts = _ts("technique", [DieType.D4], traitset_id="ts-1", rating_type=RatingType.CHALLENGE)
    repo = FakeRepo(traits=[FakeTrait("technique", "ts-1")], traitsettings=[ts])
    apply_effects(_entity(), [_rating_type_effect("static")], repo)
    assert ts.rating_type == RatingType.STATIC

    revert = _rating_type_effect("challenge")
    apply_effects(_entity(), [revert], repo)
    assert ts.rating_type == RatingType.CHALLENGE


def test_an_unknown_rating_type_is_refused_not_guessed():
    ts = _ts("technique", [DieType.D4], traitset_id="ts-1", rating_type=RatingType.STATIC)
    repo = FakeRepo(traits=[FakeTrait("technique", "ts-1")], traitsettings=[ts])
    result = apply_effects(_entity(), [_rating_type_effect("legendary")], repo)
    assert ts.rating_type == RatingType.STATIC
    assert "not a rating type" in result.applied[0].summary


def test_a_missing_trait_reports_rather_than_creating_one():
    repo = FakeRepo()
    result = apply_effects(_entity(), [_rating_type_effect("static", "char-1:absent")], repo)
    assert result.updated_trait_settings == []
    assert "no trait instance" in result.applied[0].summary


def test_change_rating_type_is_registered_on_the_engine_registry():
    """A duration fires its inverse through ``effect_registry``, so the action has
    to be there and not only in ``_MUTATION_HANDLERS``."""
    from types import SimpleNamespace
    import transversal.services.effects_applier as applier
    from transversal.services.effects_applier import EffectRegistry

    original = applier.effect_registry
    applier.effect_registry = EffectRegistry()
    try:
        raz = SimpleNamespace(spend=lambda *a, **k: None, earn=lambda *a, **k: None,
                              transfer=lambda *a, **k: None)
        em = SimpleNamespace(repo=None, create=lambda *a, **k: None)
        applier._register_core_handlers(em, raz)
        assert ("modify_trait", "set_rating_type") in applier.effect_registry._handlers
    finally:
        applier.effect_registry = original
