"""Tests for directional contest-target bans (`services/targeting_bans.py`)."""

from transversal.domain import Entity, EntityType, TargetingBan
from transversal.services.targeting_bans import (
    active_target_ids,
    apply_targeting_ban,
    clear_taken_out,
    decrement_scene_bans,
    has_targeting_ban,
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
    apply_targeting_ban(entity, "guard", 1)
    assert has_targeting_ban(entity, "guard") is True
    assert has_targeting_ban(entity, "other") is False


def test_apply_refreshes_existing_ban():
    entity = _entity("kael")
    apply_targeting_ban(entity, "guard", 3)
    apply_targeting_ban(entity, "guard", 1)
    assert sum(1 for b in entity.targeting_bans if b.target_id == "guard") == 1
    assert entity.targeting_bans[0].scenes_remaining == 1


def test_decrement_scene_bans_expires_and_counts_down():
    entity = _entity("kael", [
        TargetingBan(target_id="guard", scenes_remaining=2),
        TargetingBan(target_id="fox", scenes_remaining=1),
    ])
    repo = FakeRepo([entity])
    changed = decrement_scene_bans(repo)
    assert changed == 1
    assert {b.target_id for b in entity.targeting_bans} == {"guard"}
    assert entity.targeting_bans[0].scenes_remaining == 1
    assert has_targeting_ban(entity, "fox") is False


def test_active_target_ids_filters_expired():
    entity = _entity("kael", [
        TargetingBan(target_id="guard", scenes_remaining=1),
        TargetingBan(target_id="fox", scenes_remaining=0),
    ])
    assert active_target_ids(entity) == ["guard"]


def test_clear_taken_out():
    taken = Entity(id="kael", type=EntityType.CHARACTER, name="kael", current_universe="earth", taken_out=True)
    not_taken = Entity(id="guard", type=EntityType.CHARACTER, name="guard", current_universe="earth", taken_out=False)
    repo = FakeRepo([taken, not_taken])
    changed = clear_taken_out(repo)
    assert changed == 1
    assert taken.taken_out is False
    assert not_taken.taken_out is False
