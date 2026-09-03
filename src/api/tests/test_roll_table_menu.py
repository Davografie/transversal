"""Tests for the roll-table-as-menu pick flow (B58)."""

import pytest

from transversal.domain import (
    DieType,
    Effect,
    EffectTiming,
    Entity,
    EntityType,
    RollTable,
    RollTableEntry,
    RollTableScheme,
    TraitSetting,
)
from transversal.services.roll_table_menu import (
    entry_razmerit_cost,
    pick_roll_table_entry,
    resolve_support_cast_table_id,
)


class FakeTrait:
    def __init__(self, trait_id, traitset_id):
        self.id = trait_id
        self.traitset_id = traitset_id


class MenuRepo:
    def __init__(self, table):
        self.table = table
        self.traits = {"iron-will": FakeTrait("iron-will", "ts-distinctions")}
        self.traitsettings = []
        self.created_traitsettings = []
        self.updated_traitsettings = []
        self.updated_entities = []
        self.created_relationships = []

    def get_roll_table(self, table_id):
        return self.table if self.table.id == table_id else None

    def get_trait(self, trait_id):
        return self.traits.get(trait_id)

    def get_traitset_by_id(self, traitset_id):
        return None

    def get_traitsettings_for_entity(self, entity_id):
        return [ts for ts in self.traitsettings if ts.entity_id == entity_id]

    def get_entity(self, entity_id):
        return None

    def update_entity(self, entity):
        self.updated_entities.append(entity.id)

    def create_traitsetting(self, ts):
        self.created_traitsettings.append(ts)

    def update_traitsetting(self, ts):
        self.updated_traitsettings.append(ts)

    def create_relationship(self, from_id, to_id, rel_type, description=""):
        self.created_relationships.append((from_id, to_id, rel_type, description))


def _entity(**overrides):
    kwargs = dict(id="char-1", type=EntityType.CHARACTER, name="Test", current_universe="earth", razmerit=5)
    kwargs.update(overrides)
    return Entity(**kwargs)


def _spend(amount):
    return Effect(timing=EffectTiming.IMMEDIATE, type="transfer_razmerit", action="spend", result=str(amount))


def _gain(trait_id="iron-will", die="d6"):
    return Effect(timing=EffectTiming.IMMEDIATE, type="modify_trait", action="gain", target=trait_id, result=die)


def _table(cost_effects=(), effects=()):
    return RollTable(
        id="rt-menu",
        name="Support options",
        scheme=RollTableScheme.INDEX,
        entries=[
            RollTableEntry(
                label="Ancient lineage",
                description="d8 distinction",
                cost_effects=list(cost_effects),
                effects=list(effects),
            ),
        ],
    )


def test_entry_razmerit_cost_sums_spend_effects():
    entry = RollTableEntry(
        cost_effects=[_spend(5), Effect(timing=EffectTiming.IMMEDIATE, type="transfer_razmerit", action="earn", result="2")],
    )
    assert entry_razmerit_cost(entry) == 5


def test_pick_pays_cost_then_gains():
    repo = MenuRepo(_table(cost_effects=[_spend(2)], effects=[_gain()]))
    entity = _entity(razmerit=5)

    result, structured, label, cost = pick_roll_table_entry(repo, entity, "rt-menu", 1)

    assert label == "Ancient lineage"
    assert cost == 2
    assert entity.razmerit == 3
    assert structured == []
    assert repo.created_traitsettings and repo.created_traitsettings[0].trait_id == "iron-will"


def test_pick_rejects_unaffordable():
    repo = MenuRepo(_table(cost_effects=[_spend(6)], effects=[_gain()]))
    entity = _entity(razmerit=5)

    with pytest.raises(ValueError, match="insufficient razmerit"):
        pick_roll_table_entry(repo, entity, "rt-menu", 1)
    # Nothing applied when unaffordable.
    assert entity.razmerit == 5
    assert repo.created_traitsettings == []


def test_resolve_support_cast_table_id_universe_scoped_with_fallback():
    class ResolverRepo:
        def __init__(self, ids):
            self.ids = set(ids)

        def get_roll_table(self, table_id):
            return RollTable(id=table_id, name=table_id) if table_id in self.ids else None

    repo = ResolverRepo({"rt-emberline-support-cast", "rt-support-cast"})
    assert resolve_support_cast_table_id(repo, "emberline") == "rt-emberline-support-cast"
    assert resolve_support_cast_table_id(repo, "three_realms") == "rt-support-cast"
    assert resolve_support_cast_table_id(repo, "") == "rt-support-cast"

    empty = ResolverRepo(set())
    assert resolve_support_cast_table_id(empty, "emberline") is None
