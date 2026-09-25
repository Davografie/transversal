"""Tests for lifepath_discovery service."""

import pytest

from transversal.db.repository import EntityRepository
from transversal.domain import (
    DieType,
    DiscoveryBlock,
    Entity,
    EntityType,
    TraitSetting,
)
from transversal.services.lifepath_discovery import check_discovery


# ── In-memory repository ─────────────────────────────

class InMemoryRepository(EntityRepository):
    """Minimal in-memory repo for discovery tests — no ArangoDB needed."""

    def __init__(self):
        self._entities: dict[str, dict] = {}
        self._traitsettings: dict[str, dict] = {}
        self._relationships: list[dict] = []
        self.db = None  # signals in-memory mode

    # -- entities --
    def get_entity(self, eid: str):
        d = self._entities.get(eid)
        return Entity.model_validate(d) if d else None

    def add_entity(self, entity: Entity) -> None:
        self._entities[entity.id] = entity.model_dump()

    # -- traitsettings --
    def get_traitsettings_for_entity(self, eid: str) -> list[TraitSetting]:
        return [
            TraitSetting.model_validate(d)
            for d in self._traitsettings.values()
            if d["entity_id"] == eid
        ]

    def add_traitsetting(self, ts: TraitSetting) -> None:
        self._traitsettings[ts.id] = ts.model_dump()

    # -- relationships --
    def add_relationship(self, from_id: str, to_id: str) -> None:
        self._relationships.append(
            {"_from": f"entities/{from_id}", "_to": f"entities/{to_id}"}
        )


# ── Helpers ──────────────────────────────────────────

def _entity(eid: str, **kwargs) -> Entity:
    defaults = {
        "id": eid,
        "type": EntityType.CHARACTER,
        "name": f"Test-{eid}",
        "razmerit": 3,
        "current_universe": "earth",
    }
    defaults.update(kwargs)
    return Entity.model_validate(defaults)


def _ts(tsid: str, entity_id: str, trait_id: str, dice: list[DieType] | None = None) -> TraitSetting:
    return TraitSetting(
        id=tsid,
        entity_id=entity_id,
        trait_id=trait_id,
        dice=dice or [],
    )


# ── Fixtures ─────────────────────────────────────────

@pytest.fixture
def repo():
    return InMemoryRepository()


# ── Tests ────────────────────────────────────────────

class TestDiscoveryBlock:
    """All 12 required test cases."""

    # 1. None discovery → True
    def test_none_discovery_returns_true(self, repo):
        assert check_discovery("e1", None, repo) is True

    # 2. Empty discovery (all fields empty) → True
    def test_empty_discovery_returns_true(self, repo):
        assert check_discovery("e1", DiscoveryBlock(), repo) is True

    # 3. at_location matches → True
    def test_at_location_match(self, repo):
        repo.add_entity(_entity("e1", current_location="loc-forest"))
        discovery = DiscoveryBlock(at_location=["loc-forest"])
        assert check_discovery("e1", discovery, repo) is True

    # 4. at_location does not match → False
    def test_at_location_no_match(self, repo):
        repo.add_entity(_entity("e1", current_location="loc-desert"))
        discovery = DiscoveryBlock(at_location=["loc-forest"])
        assert check_discovery("e1", discovery, repo) is False

    # 5. knows_entity matches → True
    def test_knows_entity_match(self, repo):
        repo.add_entity(_entity("e1", known_to=["npc-elder"]))
        discovery = DiscoveryBlock(knows_entity=["npc-elder"])
        assert check_discovery("e1", discovery, repo) is True

    # 6. possesses_trait matches → True
    def test_possesses_trait_match(self, repo):
        repo.add_traitsetting(_ts("ts1", "e1", "trait-swords", [DieType.D8]))
        discovery = DiscoveryBlock(possesses_trait=["trait-swords"])
        assert check_discovery("e1", discovery, repo) is True

    # 7. has_trait_rating: die meets threshold → True
    def test_has_trait_rating_meets_threshold(self, repo):
        repo.add_traitsetting(_ts("ts1", "e1", "trait-swords", [DieType.D10]))
        discovery = DiscoveryBlock(has_trait_rating={"trait-swords": DieType.D8})
        # D10 (max_value=10) >= D8 (max_value=8) → True
        assert check_discovery("e1", discovery, repo) is True

    # 8. has_trait_rating: die below threshold → False
    def test_has_trait_rating_below_threshold(self, repo):
        repo.add_traitsetting(_ts("ts1", "e1", "trait-swords", [DieType.D6]))
        discovery = DiscoveryBlock(has_trait_rating={"trait-swords": DieType.D8})
        # D6 (max_value=6) < D8 (max_value=8) → False
        assert check_discovery("e1", discovery, repo) is False

    # 9. has_relationship matches → True
    def test_has_relationship_match(self, repo):
        repo.add_relationship("e1", "npc-mentor")
        discovery = DiscoveryBlock(has_relationship=["npc-mentor"])
        assert check_discovery("e1", discovery, repo) is True

    # 10. has_relationship does not match → False
    def test_has_relationship_no_match(self, repo):
        discovery = DiscoveryBlock(has_relationship=["npc-mentor"])
        assert check_discovery("e1", discovery, repo) is False

    # 11. Multiple conditions, one matches → True
    def test_multiple_conditions_one_match(self, repo):
        repo.add_entity(_entity("e1", current_location="loc-desert"))
        repo.add_traitsetting(_ts("ts1", "e1", "trait-swords", [DieType.D10]))
        discovery = DiscoveryBlock(
            at_location=["loc-forest"],                      # no match
            possesses_trait=["trait-swords"],                 # MATCH
            has_trait_rating={"trait-swords": DieType.D12},   # no match (D10 < D12)
        )
        assert check_discovery("e1", discovery, repo) is True

    # 12. Multiple conditions, none match → False
    def test_multiple_conditions_none_match(self, repo):
        repo.add_entity(_entity("e1", current_location="loc-desert"))
        repo.add_traitsetting(_ts("ts1", "e1", "trait-bows", [DieType.D6]))
        discovery = DiscoveryBlock(
            at_location=["loc-forest"],                       # no match
            knows_entity=["npc-elder"],                       # no match
            possesses_trait=["trait-swords"],                 # no match (has bows, not swords)
            has_trait_rating={"trait-swords": DieType.D8},    # no match (has bows at D6)
        )
        assert check_discovery("e1", discovery, repo) is False
