"""Tests for condition evaluation."""

from transversal.domain import (
    Condition,
    ConditionType,
    DieType,
    Entity,
    EntityType,
    TraitSetting,
)
from transversal.services.conditions import (
    CONDITION_TYPES,
    evaluate_condition,
    evaluate_conditions,
    static_conditions,
)


class FakeRepo:
    def __init__(self, traitsettings=None, related=None, entities=None):
        self.traitsettings = list(traitsettings or [])
        self.related = list(related or [])
        self.entities = {e.id: e for e in (entities or [])}

    def get_traitsettings_for_entity(self, entity_id):
        return [ts for ts in self.traitsettings if ts.entity_id == entity_id]

    def get_related_entities(self, entity_id):
        return self.related

    def get_entity(self, entity_id):
        return self.entities.get(entity_id)


def _entity(**overrides):
    kwargs = dict(id="char-1", type=EntityType.CHARACTER, name="Kael", current_universe="earth")
    kwargs.update(overrides)
    return Entity(**kwargs)


def _ts(trait_id, entity_id="char-1"):
    return TraitSetting(
        id=f"{entity_id}:{trait_id}", entity_id=entity_id, trait_id=trait_id,
        traitset_id="ts-x", dice=[DieType.D6],
    )


def test_always_true():
    assert evaluate_condition(_entity(), Condition(type=ConditionType.ALWAYS), FakeRepo())


def test_narrative_true():
    assert evaluate_condition(
        _entity(),
        Condition(type=ConditionType.NARRATIVE, narrative="Must be wielding a firearm"),
        FakeRepo(),
    )


def test_at_location():
    assert evaluate_condition(_entity(current_location="loc-x"), Condition(type=ConditionType.AT_LOCATION, target="loc-x"), FakeRepo())
    assert not evaluate_condition(_entity(current_location="loc-y"), Condition(type=ConditionType.AT_LOCATION, target="loc-x"), FakeRepo())


def test_has_trait():
    repo = FakeRepo(traitsettings=[_ts("iron-will")])
    assert evaluate_condition(_entity(), Condition(type=ConditionType.HAS_TRAIT, target="iron-will"), repo)
    assert not evaluate_condition(_entity(), Condition(type=ConditionType.HAS_TRAIT, target="medicine"), repo)


def test_has_effective_trait():
    enabled_ts = TraitSetting(
        id="char-1:iron-will", entity_id="char-1", trait_id="iron-will",
        traitset_id="ts-x", dice=[DieType.D6], enabled=True,
    )
    disabled_ts = TraitSetting(
        id="char-1:scar", entity_id="char-1", trait_id="scar",
        traitset_id="ts-x", dice=[DieType.D6], enabled=False,
    )
    repo = FakeRepo(traitsettings=[enabled_ts, disabled_ts])

    # Possession is true regardless of enabled.
    assert evaluate_condition(_entity(), Condition(type=ConditionType.HAS_TRAIT, target="scar"), repo)
    # Effective requires enabled.
    assert evaluate_condition(_entity(), Condition(type=ConditionType.HAS_EFFECTIVE_TRAIT, target="iron-will"), repo)
    assert not evaluate_condition(_entity(), Condition(type=ConditionType.HAS_EFFECTIVE_TRAIT, target="scar"), repo)
    assert not evaluate_condition(_entity(), Condition(type=ConditionType.HAS_EFFECTIVE_TRAIT, target="medicine"), repo)


def test_has_trait_in_traitset():
    repo = FakeRepo(traitsettings=[_ts("iron-will")])  # _ts uses traitset_id "ts-x"
    assert evaluate_condition(_entity(), Condition(type=ConditionType.HAS_TRAIT_IN_TRAITSET, target="ts-x"), repo)
    assert not evaluate_condition(_entity(), Condition(type=ConditionType.HAS_TRAIT_IN_TRAITSET, target="ts-y"), repo)


def test_trait_rating_reached():
    repo = FakeRepo(traitsettings=[_ts("iron-will")])  # d6
    assert evaluate_condition(_entity(), Condition(type=ConditionType.TRAIT_RATING, target="iron-will", value="d6"), repo)
    assert not evaluate_condition(_entity(), Condition(type=ConditionType.TRAIT_RATING, target="iron-will", value="d8"), repo)


def test_has_relationship():
    repo = FakeRepo(related=[{"id": "char-2"}])
    assert evaluate_condition(_entity(), Condition(type=ConditionType.HAS_RELATIONSHIP, target="char-2"), repo)
    assert not evaluate_condition(_entity(), Condition(type=ConditionType.HAS_RELATIONSHIP, target="char-3"), repo)


def test_phase_condition_reads_trigger_context():
    repo = FakeRepo()
    cond = Condition(type=ConditionType.PHASE, target="adding")
    assert evaluate_condition(_entity(), cond, repo, context={"phase": "adding"})
    assert not evaluate_condition(_entity(), cond, repo, context={"phase": "rolling"})
    # No phase in context -> fails.
    assert not evaluate_condition(_entity(), cond, repo)


def test_contest_outcome_condition():
    repo = FakeRepo()
    win = Condition(type=ConditionType.CONTEST_OUTCOME, target="player")
    loss = Condition(type=ConditionType.CONTEST_OUTCOME, target="opponent")
    assert evaluate_condition(_entity(), win, repo, context={"contest_winner": "player"})
    assert not evaluate_condition(_entity(), win, repo, context={"contest_winner": "opponent"})
    assert evaluate_condition(_entity(), loss, repo, context={"contest_winner": "opponent"})
    # No outcome in context -> fails.
    assert not evaluate_condition(_entity(), win, repo)


def test_roll_tier_condition():
    repo = FakeRepo()
    success = Condition(type=ConditionType.ROLL_TIER, operator=">=", value="success")
    assert evaluate_condition(_entity(), success, repo, context={"tier": "success"})
    assert evaluate_condition(_entity(), success, repo, context={"tier": "exceptional"})
    assert not evaluate_condition(_entity(), success, repo, context={"tier": "marginal"})
    assert not evaluate_condition(_entity(), success, repo, context={"tier": "fail"})
    # No tier in context -> fails.
    assert not evaluate_condition(_entity(), success, repo)


def test_test_outcome_condition_is_binary():
    repo = FakeRepo()
    success = Condition(type=ConditionType.TEST_OUTCOME, target="success")
    fail = Condition(type=ConditionType.TEST_OUTCOME, target="fail")
    # marginal counts as a success (any non-fail tier).
    assert evaluate_condition(_entity(), success, repo, context={"tier": "marginal"})
    assert evaluate_condition(_entity(), success, repo, context={"tier": "success"})
    assert evaluate_condition(_entity(), success, repo, context={"tier": "perfect"})
    assert not evaluate_condition(_entity(), success, repo, context={"tier": "fail"})
    assert evaluate_condition(_entity(), fail, repo, context={"tier": "fail"})
    assert not evaluate_condition(_entity(), fail, repo, context={"tier": "success"})
    # No tier in context -> not success, not fail.
    assert not evaluate_condition(_entity(), success, repo)
    assert not evaluate_condition(_entity(), fail, repo)


def test_all_must_pass():
    repo = FakeRepo(traitsettings=[_ts("iron-will")])
    conditions = [
        Condition(type=ConditionType.HAS_TRAIT, target="iron-will"),
        Condition(type=ConditionType.AT_LOCATION, target="loc-x"),
    ]
    assert evaluate_conditions(_entity(current_location="loc-x"), conditions, repo)
    assert not evaluate_conditions(_entity(current_location="loc-y"), conditions, repo)


def test_empty_conditions_true():
    assert evaluate_conditions(_entity(), [], FakeRepo())


def test_unplaced():
    assert evaluate_condition(_entity(), Condition(type=ConditionType.UNPLACED), FakeRepo())
    assert not evaluate_condition(
        _entity(current_location="loc-x"), Condition(type=ConditionType.UNPLACED), FakeRepo()
    )


def test_in_universe():
    assert evaluate_condition(
        _entity(current_universe="earth"), Condition(type=ConditionType.IN_UNIVERSE, target="earth"), FakeRepo()
    )
    assert not evaluate_condition(
        _entity(current_universe="three_realms"), Condition(type=ConditionType.IN_UNIVERSE, target="earth"), FakeRepo()
    )


def test_has_razmerit():
    # Default comparator is ">=".
    assert evaluate_condition(_entity(razmerit=5), Condition(type=ConditionType.HAS_RAZMERIT, value="3"), FakeRepo())
    assert not evaluate_condition(_entity(razmerit=2), Condition(type=ConditionType.HAS_RAZMERIT, value="3"), FakeRepo())
    assert evaluate_condition(_entity(razmerit=3), Condition(type=ConditionType.HAS_RAZMERIT, value="3", operator="=="), FakeRepo())
    assert not evaluate_condition(_entity(razmerit=4), Condition(type=ConditionType.HAS_RAZMERIT, value="3", operator="=="), FakeRepo())
    assert evaluate_condition(_entity(razmerit=1), Condition(type=ConditionType.HAS_RAZMERIT, value="3", operator="<"), FakeRepo())
    assert evaluate_condition(_entity(razmerit=3), Condition(type=ConditionType.HAS_RAZMERIT, value="3", operator="<="), FakeRepo())
    assert evaluate_condition(_entity(razmerit=4), Condition(type=ConditionType.HAS_RAZMERIT, value="3", operator=">"), FakeRepo())
    assert evaluate_condition(_entity(razmerit=2), Condition(type=ConditionType.HAS_RAZMERIT, value="3", operator="!="), FakeRepo())
    # Non-integer value fails safe.
    assert not evaluate_condition(_entity(razmerit=5), Condition(type=ConditionType.HAS_RAZMERIT, value="abc"), FakeRepo())


def test_entity_type():
    assert evaluate_condition(_entity(type=EntityType.CHARACTER), Condition(type=ConditionType.ENTITY_TYPE, target="character"), FakeRepo())
    assert not evaluate_condition(_entity(type=EntityType.GMC), Condition(type=ConditionType.ENTITY_TYPE, target="character"), FakeRepo())
    # Variable subject resolves against context.
    buyer = _entity(id="char-2", type=EntityType.CHARACTER, current_universe="earth")
    repo = FakeRepo(entities=[buyer])
    cond = Condition(type=ConditionType.ENTITY_TYPE, subject="{buying_entity}", target="character")
    assert evaluate_condition(_entity(), cond, repo, context={"buying_entity": "char-2"})
    assert not evaluate_condition(_entity(), cond, repo, context={})


def test_static_conditions_excludes_variable_refs():
    conds = [
        Condition(type=ConditionType.ENTITY_TYPE, target="character"),
        Condition(type=ConditionType.ENTITY_TYPE, subject="{buying_entity}", target="character"),
        Condition(type=ConditionType.IN_UNIVERSE, target="earth"),
    ]
    static = static_conditions(conds)
    assert [c.type for c in static] == [ConditionType.ENTITY_TYPE, ConditionType.IN_UNIVERSE]


def test_subject_variable_resolves_to_other_entity():
    buyer = _entity(id="char-2", current_universe="earth")
    repo = FakeRepo(entities=[buyer])
    cond = Condition(type=ConditionType.IN_UNIVERSE, subject="{buying_entity}", target="earth")
    assert evaluate_condition(_entity(), cond, repo, context={"buying_entity": "char-2"})
    # Unresolved subject → condition fails (safe default).
    assert not evaluate_condition(_entity(), cond, repo, context={})


def test_subject_literal_id():
    other = _entity(id="char-2", current_location="loc-x")
    repo = FakeRepo(entities=[other])
    cond = Condition(type=ConditionType.AT_LOCATION, subject="char-2", target="loc-x")
    assert evaluate_condition(_entity(), cond, repo)


def test_target_variable_resolves():
    repo = FakeRepo(traitsettings=[_ts("iron-will")])
    cond = Condition(type=ConditionType.HAS_TRAIT, target="{trait}")
    assert evaluate_condition(_entity(), cond, repo, context={"trait": "iron-will"})


def test_blank_subject_with_no_default_fails():
    # The hitch menu passes no default entity, so a blank subject can't resolve.
    assert not evaluate_condition(None, Condition(type=ConditionType.UNPLACED), FakeRepo())


def test_condition_types_registry_declares_editor_metadata():
    by_value = {c.value: c for c in CONDITION_TYPES}
    assert "UNPLACED" in by_value
    assert "IN_UNIVERSE" in by_value
    assert by_value["UNPLACED"].needs_target is False
    assert by_value["IN_UNIVERSE"].needs_target is True
    assert by_value["IN_UNIVERSE"].target_placeholder == "universe key"
    assert all(c.label for c in CONDITION_TYPES)


def test_condition_types_declare_picker_target_kinds():
    by_value = {c.value: c for c in CONDITION_TYPES}
    assert by_value["IN_UNIVERSE"].target_kind == "universe"
    assert by_value["AT_LOCATION"].target_kind == "location"
    assert by_value["HAS_TRAIT"].target_kind == "trait"
    assert by_value["HAS_TRAIT_IN_TRAITSET"].target_kind == "traitset"
    assert by_value["TRAIT_RATING"].target_kind == "trait"
    assert by_value["HAS_RELATIONSHIP"].target_kind == "entity"
    assert by_value["ALWAYS"].target_kind == ""


def test_condition_types_declare_value_kind_and_operators():
    by_value = {c.value: c for c in CONDITION_TYPES}
    assert by_value["TRAIT_RATING"].value_kind == "die"
    assert by_value["HAS_RAZMERIT"].value_kind == "number"
    assert by_value["HAS_RAZMERIT"].operators == ("<", "<=", "==", "!=", ">=", ">")
    assert by_value["HAS_RAZMERIT"].needs_target is False
    assert by_value["ENTITY_TYPE"].target_options == ("character", "gmc", "asset")
    assert by_value["ENTITY_TYPE"].needs_target is True
