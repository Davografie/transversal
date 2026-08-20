"""Tests for directional contest-target bans (`services/targeting_bans.py`)."""

from transversal.domain import Entity, EntityType, TargetingBan
from transversal.services.targeting_bans import (
    active_target_ids,
    apply_targeting_ban,
    clear_taken_out,
    has_targeting_ban,
    remove_targeting_ban,
)


def _entity(entity_id, bans=None):
    return Entity(
        id=entity_id,
        type=EntityType.CHARACTER,
        name=entity_id,
        current_universe="earth",
        targeting_bans=bans or [],
    )


class FakeRepo:
    def __init__(self, entities):
        self.entities = list(entities)
        self.updated = []

    def list_all_entities(self):
        return list(self.entities)

    def update_entity(self, entity):
        self.updated.append(entity.id)
        for i, existing in enumerate(self.entities):
            if existing.id == entity.id:
                self.entities[i] = entity
                return


def test_apply_and_has():
    entity = _entity("kael")
    apply_targeting_ban(entity, "guard")
    assert has_targeting_ban(entity, "guard") is True
    assert has_targeting_ban(entity, "other") is False


def test_apply_refreshes_existing_ban():
    entity = _entity("kael")
    apply_targeting_ban(entity, "guard")
    apply_targeting_ban(entity, "guard")
    assert sum(1 for b in entity.targeting_bans if b.target_id == "guard") == 1


def test_remove_targeting_ban():
    entity = _entity("kael", [TargetingBan(target_id="guard"), TargetingBan(target_id="fox")])
    remove_targeting_ban(entity, "guard")
    assert has_targeting_ban(entity, "guard") is False
    assert has_targeting_ban(entity, "fox") is True


def test_active_target_ids():
    entity = _entity("kael", [TargetingBan(target_id="guard"), TargetingBan(target_id="fox")])
    assert active_target_ids(entity) == ["guard", "fox"]


def test_clear_taken_out():
    taken = Entity(id="kael", type=EntityType.CHARACTER, name="kael", current_universe="earth", taken_out=True)
    not_taken = Entity(id="guard", type=EntityType.CHARACTER, name="guard", current_universe="earth", taken_out=False)
    repo = FakeRepo([taken, not_taken])
    changed = clear_taken_out(repo)
    assert changed == 1
    assert taken.taken_out is False
    assert not_taken.taken_out is False
