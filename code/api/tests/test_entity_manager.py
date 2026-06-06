"""Tests for v2 multi-collection entity manager and razmerit service."""

import pytest

from transversal.db.repository import EntityRepository
from transversal.domain import (
    CharacterView,
    DieType,
    Entity,
    EntityType,
    Projection,

    Trait,
    TraitSet,
    TraitSetting,
    TransversalType,
)
from transversal.domain.validation import ValidationError, validate_entity
from transversal.services.entity_manager import (
    EntityManager,
    EntityNotFoundError,
)
from transversal.services.razmerit import (
    InsufficientRazmeritError,
    RazmeritService,
)


# ── In-memory repository ─────────────────────────────

class InMemoryRepository(EntityRepository):
    def __init__(self):
        self._entities: dict[str, dict] = {}
        self._projections: dict[str, dict] = {}
        self._traits: dict[str, dict] = {}
        self._traitsets: dict[str, dict] = {}
        self._traitsettings: dict[str, dict] = {}
        self.db = None

    def _store(self, coll: dict, key: str, doc: dict) -> dict:
        doc["_key"] = key
        coll[key] = doc
        return doc

    # entities
    def create_entity(self, entity: Entity) -> Entity:
        self._store(self._entities, entity.id, entity.model_dump())
        return entity
    def get_entity(self, eid: str):
        d = self._entities.get(eid)
        return Entity.model_validate(d) if d else None
    def update_entity(self, entity: Entity) -> Entity:
        self._entities[entity.id] = entity.model_dump()
        return entity
    def delete_entity(self, eid: str) -> bool:
        return self._entities.pop(eid, None) is not None
    def list_entities_by_type(self, et, universe=None):
        return [Entity.model_validate(d) for d in self._entities.values()
                if d["type"] == et.value and (universe is None or d.get("current_universe") == universe)]

    # projections
    def create_projection(self, p: Projection) -> Projection:
        self._store(self._projections, p.id, p.model_dump())
        return p
    def get_projections_for_entity(self, eid: str) -> list[Projection]:
        return [Projection.model_validate(d) for d in self._projections.values() if d["entity_id"] == eid]
    def update_projection(self, p: Projection) -> Projection:
        self._projections[p.id] = p.model_dump()
        return p

    # traits registry
    def create_trait(self, t: Trait) -> Trait:
        self._store(self._traits, t.id, t.model_dump())
        return t
    def get_trait(self, tid: str):
        d = self._traits.get(tid)
        return Trait.model_validate(d) if d else None
    def get_trait_by_name(self, name, universe):
        for d in self._traits.values():
            if d["name"] == name and d["universe"] == universe:
                return Trait.model_validate(d)
        return None

    def get_traits_by_universe(self, universe: str) -> list[Trait]:
        return [Trait.model_validate(d) for d in self._traits.values() if d["universe"] == universe]

    def get_traitsets_by_universe(self, universe: str) -> list[TraitSet]:
        return [TraitSet.model_validate(d) for d in self._traitsets.values() if d["universe"] == universe]

    # traitsets
    def create_traitset(self, ts: TraitSet) -> TraitSet:
        self._store(self._traitsets, ts.id, ts.model_dump())
        return ts

    # traitsettings
    def create_traitsetting(self, ts: TraitSetting) -> TraitSetting:
        self._store(self._traitsettings, ts.id, ts.model_dump())
        return ts
    def get_traitsettings_for_entity(self, eid: str) -> list[TraitSetting]:
        return [TraitSetting.model_validate(d) for d in self._traitsettings.values() if d["entity_id"] == eid]
    def get_traitsettings_by_traitset(self, eid, tsid) -> list[TraitSetting]:
        return [TraitSetting.model_validate(d) for d in self._traitsettings.values()
                if d["entity_id"] == eid and d["traitset_id"] == tsid]
    def update_traitsetting(self, ts: TraitSetting) -> TraitSetting:
        self._store(self._traitsettings, ts.id, ts.model_dump())
        return ts
    def get_traitsetting(self, ts_id: str) -> TraitSetting | None:
        d = self._traitsettings.get(ts_id)
        return TraitSetting.model_validate(d) if d else None
    def delete_traitsetting(self, tsid: str) -> bool:
        return self._traitsettings.pop(tsid, None) is not None

    # effective traits
    def get_effective_traitsettings(self, eid: str, universe: str) -> list[TraitSetting]:
        universe_trait_ids = {tid for tid, d in self._traits.items() if d["universe"] == universe}
        return [
            TraitSetting.model_validate(d)
            for d in self._traitsettings.values()
            if d["entity_id"] == eid and (d["trait_id"] in universe_trait_ids or d.get("ego", False))
        ]

    # assembly
    def assemble_character(self, eid: str):
        entity = self.get_entity(eid)
        if not entity:
            return None
        return CharacterView(
            entity=entity,
            projections={p.universe: p for p in self.get_projections_for_entity(eid)},
            trait_settings=self.get_traitsettings_for_entity(eid),
        )


# ── Fixtures ─────────────────────────────────────────

@pytest.fixture
def repo():
    return InMemoryRepository()

@pytest.fixture
def em(repo):
    return EntityManager(repository=repo)

@pytest.fixture
def raz(repo):
    return RazmeritService(repository=repo)

@pytest.fixture
def kael(em):
    return em.create(name="Kael Drift", entity_type=EntityType.CHARACTER, universe="earth", razmerit=3)

@pytest.fixture
def hacking_trait(repo):
    t = Trait(id="trait-earth-hacking", name="hacking", universe="earth",
              traitset_id="ts-earth-skills", default_die_type=DieType.D6)
    repo.create_trait(t)
    ts = TraitSet(id="ts-earth-skills", name="skills", universe="earth")
    repo.create_traitset(ts)
    return t


# ── Tests ────────────────────────────────────────────

class TestEntityCreation:
    def test_create(self, kael):
        assert kael.name == "Kael Drift"
        assert kael.type == EntityType.CHARACTER
        assert kael.razmerit == 3
        assert kael.current_universe == "earth"

    def test_initial_projection_created(self, em, kael):
        projs = em.get_projections(kael.id)
        assert len(projs) == 1
        assert projs[0].universe == "earth"

    def test_validation_rejects_negative_razmerit(self):
        with pytest.raises(ValidationError):
            validate_entity(Entity(id="x", type=EntityType.CHARACTER, name="x",
                                   razmerit=-5, current_universe="earth"))


class TestProjections:
    def test_add_projection(self, em, kael):
        em.add_projection(kael, "three_realms")
        projs = em.get_projections(kael.id)
        assert len(projs) == 2
        universes = {p.universe for p in projs}
        assert universes == {"earth", "three_realms"}

    def test_duplicate_rejected(self, em, kael):
        with pytest.raises(ValueError, match="already has"):
            em.add_projection(kael, "earth")


class TestTraitSettings:
    def test_add_traitsetting(self, em, kael, hacking_trait):
        ts = TraitSetting(
            id=f"{kael.id}:hacking",
            entity_id=kael.id, trait_id=hacking_trait.id,
            traitset_id="ts-earth-skills",
            dice=[DieType.D10],
        )
        em.add_traitsetting(ts)
        settings = em.get_traitsettings(kael.id)
        assert len(settings) == 1
        assert settings[0].dice == [DieType.D10]

    def test_step_up(self, em, kael, hacking_trait):
        ts = TraitSetting(
            id=f"{kael.id}:hacking", entity_id=kael.id, trait_id=hacking_trait.id,
            traitset_id="ts-earth-skills",
            dice=[DieType.D10],
        )
        em.add_traitsetting(ts)
        updated = em.step_up_trait(ts)
        assert updated.dice == [DieType.D12]

    def test_filter_by_traitset(self, em, kael, hacking_trait):
        ts1 = TraitSetting(id=f"{kael.id}:hacking", entity_id=kael.id, trait_id=hacking_trait.id,
                           traitset_id="ts-earth-skills", dice=[DieType.D10])
        ts2 = TraitSetting(id=f"{kael.id}:stealth", entity_id=kael.id, trait_id="trait-earth-stealth",
                           traitset_id="ts-earth-skills", dice=[DieType.D6])
        em.add_traitsetting(ts1)
        em.add_traitsetting(ts2)
        result = em.get_traitsettings_by_set(kael.id, "ts-earth-skills")
        assert len(result) == 2

    def test_character_view(self, em, kael, hacking_trait):
        ts = TraitSetting(id=f"{kael.id}:hacking", entity_id=kael.id, trait_id=hacking_trait.id,
                          traitset_id="ts-earth-skills", dice=[DieType.D10])
        em.add_traitsetting(ts)
        cv = em.get_character(kael.id)
        assert cv.entity.name == "Kael Drift"
        assert "earth" in cv.projections
        assert len(cv.trait_settings) == 1
        assert cv.trait_settings[0].dice == [DieType.D10]


class TestRazmerit:
    def test_spend(self, raz, kael):
        r = raz.spend(kael.id, 2, "sfx")
        assert r.from_balance == 1
        assert raz.repo.get_entity(kael.id).razmerit == 1

    def test_earn(self, raz, kael):
        r = raz.earn(kael.id, 2, "hitch")
        assert r.to_balance == 5

    def test_transfer(self, em, raz, kael):
        target = em.create(name="Elder Yun", entity_type=EntityType.GMC, universe="earth", razmerit=5)
        r = raz.transfer(target.id, kael.id, 3)
        assert r.from_balance == 2
        assert r.to_balance == 6

    def test_insufficient(self, raz, kael):
        with pytest.raises(InsufficientRazmeritError):
            raz.spend(kael.id, 10)

    def test_negative_razmerit_rejected(self):
        with pytest.raises(ValidationError):
            e = Entity(id="x", type=EntityType.CHARACTER, name="x", razmerit=-1, current_universe="earth")
            validate_entity(e)


class TestEgoTraits:
    def test_ego_persists_across_universes(self, em, repo, kael):
        # Earth trait
        earth_t = Trait(id="trait-earth-hacking", name="hacking", universe="earth",
                        traitset_id="ts-earth-skills")
        repo.create_trait(earth_t)
        # Ego trait (curiosity — personality, not universe-specific)
        ego_t = Trait(id="trait-ego-curious", name="curious", universe="earth",
                      traitset_id="ts-earth-distinctions")
        repo.create_trait(ego_t)

        em.add_traitsetting(TraitSetting(
            id=f"{kael.id}:hacking", entity_id=kael.id, trait_id="trait-earth-hacking",
            traitset_id="ts-earth-skills", dice=[DieType.D10],
        ))
        em.add_traitsetting(TraitSetting(
            id=f"{kael.id}:curious", entity_id=kael.id, trait_id="trait-ego-curious",
            traitset_id="ts-earth-distinctions", dice=[DieType.D8],
            ego=True,
        ))

        # On Earth: both available
        earth_traits = em.get_effective_traitsettings(kael.id, "earth")
        earth_names = {repo.get_trait(ts.trait_id).name for ts in earth_traits}
        assert "hacking" in earth_names
        assert "curious" in earth_names

        # In Three Realms: only curious (ego), not hacking (Earth morph)
        realm_traits = em.get_effective_traitsettings(kael.id, "three_realms")
        realm_names = {repo.get_trait(ts.trait_id).name for ts in realm_traits}
        assert "hacking" not in realm_names
        assert "curious" in realm_names


class TestLocation:
    def test_move(self, em, kael):
        em.move_to(kael, "Valley of Ascension", "three_realms")
        updated = em.get(kael.id)
        assert updated.current_location == "Valley of Ascension"
        assert updated.current_universe == "three_realms"
