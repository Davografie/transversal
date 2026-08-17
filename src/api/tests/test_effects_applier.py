"""Tests for the pure repo-first effect applier."""

from transversal.domain import (
    DieType,
    Effect,
    EffectTiming,
    Entity,
    EntityType,
    TraitSetting,
)
from transversal.services.effects_applier import apply_effects, resolve_choice


class FakeTrait:
    def __init__(self, trait_id, traitset_id):
        self.id = trait_id
        self.traitset_id = traitset_id


class FakeRepo:
    def __init__(self, traits=None, traitsettings=None, entities=None):
        self.traits = {t.id: t for t in (traits or [])}
        self.traitsettings = list(traitsettings or [])
        self.entities = {e.id: e for e in (entities or [])}

    def get_trait(self, trait_id):
        return self.traits.get(trait_id)

    def get_traitsettings_for_entity(self, entity_id):
        return [ts for ts in self.traitsettings if ts.entity_id == entity_id]

    def get_entity(self, entity_id):
        return self.entities.get(entity_id)


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
    assert ts.negative is False
    assert result.applied[0].summary == "gained iron-will at d6"


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


def test_step_down_floors_at_d4():
    repo = FakeRepo(traitsettings=[_ts("pool", [DieType.D4])])
    entity = _entity()
    result = apply_effects(entity, [_effect("modify_trait", "step_down", "pool")], repo)
    assert len(result.updated_trait_settings) == 0
    assert result.applied[0].summary == "pool already at d4"


def test_set_overrides_dice():
    repo = FakeRepo(traitsettings=[_ts("trait", [DieType.D6])])
    entity = _entity()
    result = apply_effects(entity, [_effect("modify_trait", "set", "trait", "d10")], repo)
    assert result.updated_trait_settings[0].dice == [DieType.D10]


# ── Complications ────────────────────────────────────

def test_gain_complication_sets_negative():
    repo = FakeRepo(traits=[FakeTrait("scar", "ts-complications")])
    entity = _entity()
    result = apply_effects(entity, [_effect("modify_trait", "gain_complication", "scar", "d4")], repo)
    ts = result.new_trait_settings[0]
    assert ts.negative is True
    assert ts.traitset_id == "ts-complications"


def test_gain_or_step_up_complication_creates_when_absent():
    repo = FakeRepo(traits=[FakeTrait("scar", "ts-complications")])
    entity = _entity()
    result = apply_effects(entity, [_effect("modify_trait", "gain_or_step_up_complication", "scar", "d4")], repo)
    assert len(result.new_trait_settings) == 1
    ts = result.new_trait_settings[0]
    assert ts.negative is True
    assert ts.dice == [DieType.D4]


def test_gain_or_step_up_complication_steps_up_when_present():
    repo = FakeRepo(traitsettings=[_ts("scar", [DieType.D4], traitset_id="ts-complications", negative=True)])
    entity = _entity()
    result = apply_effects(entity, [_effect("modify_trait", "gain_or_step_up_complication", "scar", "d4")], repo)
    assert len(result.new_trait_settings) == 0
    assert len(result.updated_trait_settings) == 1
    assert result.updated_trait_settings[0].dice == [DieType.D6]


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
