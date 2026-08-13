"""Tests for relationship trait settings (ratings on relationships)."""

import pytest

from tests.test_entity_manager import InMemoryRepository
from transversal.domain import (
    DieType,
    Entity,
    EntityType,
    RatingType,
    Trait,
    TraitSet,
    TraitSetting,
)
from transversal.services.entity_manager import EntityManager


# ── Extended InMemoryRepository with relationships ──────

class ExtendedInMemoryRepository(InMemoryRepository):
    """Adds relationship and relationship-traitsetting support."""

    def __init__(self):
        super().__init__()
        self._relationships: dict[str, dict] = {}

    # ── Relationships ─────────────────────────────────

    def create_relationship(
        self, from_id: str, to_id: str, rel_type: str, description: str = ""
    ) -> dict:
        edge_key = f"edge:{from_id}:{to_id}:{rel_type}"
        edge = {
            "_key": edge_key,
            "_from": f"entities/{from_id}",
            "_to": f"entities/{to_id}",
            "type": rel_type,
        }
        if description:
            edge["description"] = description
        self._relationships[edge_key] = edge
        return edge

    def get_relationship(
        self, from_id: str, to_id: str, rel_type: str
    ) -> dict | None:
        edge_key = f"edge:{from_id}:{to_id}:{rel_type}"
        return self._relationships.get(edge_key)

    # ── Relationship TraitSettings ────────────────────

    def get_relationship_traitsettings(self, edge_key: str) -> list[TraitSetting]:
        """Get trait settings attached to a relationship edge."""
        return [
            TraitSetting.model_validate(d)
            for d in self._traitsettings.values()
            if d["entity_id"] == edge_key and d.get("from_type") == "relationship"
        ]

    def get_relationship_traits_for_entities(
        self, entity_id_a: str, entity_id_b: str
    ) -> list[TraitSetting]:
        """Get all trait settings on relationships between two entities."""
        results: list[TraitSetting] = []
        for rel_type in ["relation", "associate", "gifted", "suspects", "hostile_to"]:
            for frm, to in [(entity_id_a, entity_id_b), (entity_id_b, entity_id_a)]:
                edge_key = f"edge:{frm}:{to}:{rel_type}"
                rel = self.get_relationship(frm, to, rel_type)
                if rel:
                    results.extend(self.get_relationship_traitsettings(edge_key))
        return results

    # ── TraitSet lookup (used by seed) ────────────────

    def get_traitset_by_id(self, traitset_id: str) -> TraitSet | None:
        d = self._traitsets.get(traitset_id)
        return TraitSet.model_validate(d) if d else None


# ── Fixtures ──────────────────────────────────────────

@pytest.fixture
def repo():
    return ExtendedInMemoryRepository()


@pytest.fixture
def em(repo):
    return EntityManager(repository=repo)


@pytest.fixture
def kael(em):
    return em.create(
        name="Kael Drift", entity_type=EntityType.CHARACTER, universe="earth", razmerit=3
    )


@pytest.fixture
def mira(em):
    return em.create(
        name="Mira Voss", entity_type=EntityType.CHARACTER, universe="earth", razmerit=2
    )


# ── Tests ─────────────────────────────────────────────

class TestTraitSettingFromType:
    """Tests for the from_type field on TraitSetting."""

    def test_default_from_type_is_entity(self):
        """from_type defaults to 'entity'."""
        ts = TraitSetting(
            id="ts-test-1",
            entity_id="char-1",
            trait_id="trait-x",
            traitset_id="ts-skills",
        )
        assert ts.from_type == "entity"

    def test_explicit_relationship_from_type(self):
        """from_type can be explicitly set to 'relationship'."""
        ts = TraitSetting(
            id="ts-test-2",
            entity_id="edge:kael-1:mira-1:relation",
            trait_id="trait-relation-trust",
            traitset_id="ts-relations",
            from_type="relationship",
        )
        assert ts.from_type == "relationship"
        assert ts.entity_id == "edge:kael-1:mira-1:relation"


class TestRelationshipTraitSettings:
    """Tests for attaching trait settings to relationship edges."""

    def test_create_relationship_traitsetting(self, repo, kael, mira):
        """Creating a TraitSetting with from_type='relationship' stores it correctly."""
        # Create a relationship edge
        repo.create_relationship(kael.id, mira.id, "relation", "allies")

        edge_key = f"edge:{kael.id}:{mira.id}:relation"

        ts = TraitSetting(
            id="ts-rel-trust-1",
            entity_id=edge_key,
            trait_id="trait-relation-trust",
            traitset_id="ts-relations",
            from_type="relationship",
            rating_type=RatingType.STATIC,
            dice=[DieType.D8],
            statement="I trust Mira with my life",
        )
        repo.create_traitsetting(ts)

        # Verify it's retrievable via get_relationship_traitsettings
        results = repo.get_relationship_traitsettings(edge_key)
        assert len(results) == 1
        assert results[0].id == "ts-rel-trust-1"
        assert results[0].trait_id == "trait-relation-trust"
        assert results[0].dice == [DieType.D8]
        assert results[0].from_type == "relationship"

    def test_entity_traitsetting_not_in_relationship_results(self, repo, kael):
        """Entity-scoped traitsettings do not appear in relationship queries."""
        # Create a normal entity traitsetting
        ts = TraitSetting(
            id="ts-entity-1",
            entity_id=kael.id,
            trait_id="trait-earth-strength",
            traitset_id="ts-earth-attributes",
            dice=[DieType.D6],
        )
        repo.create_traitsetting(ts)

        # Querying for relationship traitsettings with an edge_key shouldn't find it
        results = repo.get_relationship_traitsettings("edge:a:b:relation")
        assert len(results) == 0

    def test_get_relationship_traits_for_entities_both_directions(self, repo, kael, mira):
        """Relationship traits are found regardless of edge direction."""
        # Relationship from kael → mira
        repo.create_relationship(kael.id, mira.id, "relation")

        edge_km = f"edge:{kael.id}:{mira.id}:relation"

        ts = TraitSetting(
            id="ts-trust-km",
            entity_id=edge_km,
            trait_id="trait-relation-trust",
            traitset_id="ts-relations",
            from_type="relationship",
            dice=[DieType.D6],
        )
        repo.create_traitsetting(ts)

        # Should find it querying either order
        results_a = repo.get_relationship_traits_for_entities(kael.id, mira.id)
        assert len(results_a) == 1
        assert results_a[0].id == "ts-trust-km"

        results_b = repo.get_relationship_traits_for_entities(mira.id, kael.id)
        assert len(results_b) == 1
        assert results_b[0].id == "ts-trust-km"

    def test_get_relationship_traits_finds_multiple_traits(self, repo, kael, mira):
        """Multiple traits on a relationship edge are all found."""
        repo.create_relationship(kael.id, mira.id, "relation")
        edge_key = f"edge:{kael.id}:{mira.id}:relation"

        ts1 = TraitSetting(
            id="ts-trust-1", entity_id=edge_key,
            trait_id="trait-relation-trust", traitset_id="ts-relations",
            from_type="relationship", dice=[DieType.D8],
        )
        ts2 = TraitSetting(
            id="ts-debt-1", entity_id=edge_key,
            trait_id="trait-relation-debt", traitset_id="ts-relations",
            from_type="relationship", dice=[DieType.D6, DieType.D6],
        )
        repo.create_traitsetting(ts1)
        repo.create_traitsetting(ts2)

        results = repo.get_relationship_traitsettings(edge_key)
        assert len(results) == 2
        trait_ids = {r.trait_id for r in results}
        assert trait_ids == {"trait-relation-trust", "trait-relation-debt"}

    def test_no_traits_for_nonexistent_relationship(self, repo):
        """Querying with entities that have no relationship returns empty."""
        results = repo.get_relationship_traits_for_entities("nonex-a", "nonex-b")
        assert results == []


class TestSeedRelationsTraitset:
    """Tests for the seed_relations_traitset function."""

    def test_seed_creates_traitset(self, repo):
        from transversal.db.seed import seed_relations_traitset

        seed_relations_traitset(repo)

        ts = repo.get_traitset_by_id("ts-relations")
        assert ts is not None
        assert ts.name == "Relations"
        assert "earth" in ts.universes
        assert "three_realms" in ts.universes

    def test_seed_creates_traits(self, repo):
        from transversal.db.seed import seed_relations_traitset

        seed_relations_traitset(repo)

        expected_traits = [
            "trait-relation-trust",
            "trait-relation-debt",
            "trait-relation-rivalry",
            "trait-relation-loyalty",
            "trait-relation-fear",
            "trait-relation-love",
            "trait-relation-duty",
            "trait-rel-rank",
            "trait-rel-tenure",
        ]
        for tid in expected_traits:
            trait = repo.get_trait(tid)
            assert trait is not None, f"Trait {tid} should exist"
            assert trait.traitset_id == "ts-relations"
            assert "earth" in trait.universes
            assert "three_realms" in trait.universes

    def test_seed_is_idempotent(self, repo):
        from transversal.db.seed import seed_relations_traitset

        seed_relations_traitset(repo)
        first_ts = repo.get_traitset_by_id("ts-relations")

        seed_relations_traitset(repo)
        second_ts = repo.get_traitset_by_id("ts-relations")

        assert first_ts is not None
        assert second_ts is not None
        # Should not have created duplicates
        all_traits = [d for d in repo._traits.values() if d["traitset_id"] == "ts-relations"]
        assert len(all_traits) == 9  # the 7 relation traits + rank + tenure


class TestEntityManagerStub:
    """Tests for the EntityManager.get_relationship_trait_settings stub."""

    def test_stub_returns_relationship_traits(self, em, repo, kael, mira):
        """The EntityManager stub delegates to repo."""
        repo.create_relationship(kael.id, mira.id, "relation")
        edge_key = f"edge:{kael.id}:{mira.id}:relation"

        ts = TraitSetting(
            id="ts-trust-stub",
            entity_id=edge_key,
            trait_id="trait-relation-trust",
            traitset_id="ts-relations",
            from_type="relationship",
            dice=[DieType.D10],
        )
        repo.create_traitsetting(ts)

        results = em.get_relationship_trait_settings(kael.id, mira.id)
        assert len(results) == 1
        assert results[0].id == "ts-trust-stub"
        assert results[0].dice == [DieType.D10]
