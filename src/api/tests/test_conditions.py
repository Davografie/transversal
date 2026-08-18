"""Tests for condition evaluation."""

from transversal.domain import (
    Condition,
    ConditionType,
    DieType,
    Entity,
    EntityType,
    TraitSetting,
)
from transversal.services.conditions import evaluate_condition, evaluate_conditions


class FakeRepo:
    def __init__(self, traitsettings=None, related=None):
        self.traitsettings = list(traitsettings or [])
        self.related = list(related or [])

    def get_traitsettings_for_entity(self, entity_id):
        return [ts for ts in self.traitsettings if ts.entity_id == entity_id]

    def get_related_entities(self, entity_id):
        return self.related


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
