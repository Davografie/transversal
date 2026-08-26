"""Tests for v2 multi-collection entity manager and razmerit service."""

import pytest

from transversal.db.repository import EntityRepository
from transversal.domain import (
    Attunement,
    AttunementScope,
    CharacterView,
    DieType,
    Entity,
    EntityType,
    Projection,
    ScheduledEvent,

    SfxOwner,
    Trait,
    TraitSet,
    TraitSetting,
    TraitSetSetting,
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
        self._traitsetsettings: dict[str, dict] = {}
        self._sfx_owners: dict[str, dict] = {}
        self._scheduled_events: dict[str, dict] = {}
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
    def create_scheduled_event(self, event):
        self._store(self._scheduled_events, event.id, event.model_dump())
        return event
    def list_all_scheduled_events(self):
        return [ScheduledEvent.model_validate(d) for d in self._scheduled_events.values()]
    def list_scheduled_events(self, target_type=None, target_id=None, target_ids=None):
        events = self.list_all_scheduled_events()
        if target_type is not None:
            events = [e for e in events if e.target_type == target_type]
        if target_id is not None:
            events = [e for e in events if e.target_id == target_id]
        if target_ids is not None:
            ids = set(target_ids)
            events = [e for e in events if e.target_id in ids]
        return events
    def update_scheduled_event(self, event):
        self._store(self._scheduled_events, event.id, event.model_dump())
        return event
    def delete_scheduled_event(self, event_id):
        return self._scheduled_events.pop(event_id, None) is not None
    def update_entity(self, entity: Entity) -> Entity:
        self._entities[entity.id] = entity.model_dump()
        return entity
    def delete_entity(self, eid: str) -> bool:
        return self._entities.pop(eid, None) is not None
    def list_entities_by_type(self, et, universe=None):
        return [Entity.model_validate(d) for d in self._entities.values()
                if d["type"] == et.value and (universe is None or d.get("current_universe") == universe)]
    def get_entities_by_ids(self, entity_ids):
        return [Entity.model_validate(self._entities[eid]) for eid in entity_ids if eid in self._entities]

    # projections
    def create_projection(self, p: Projection) -> Projection:
        self._store(self._projections, p.id, p.model_dump())
        return p
    def get_projections_for_entity(self, eid: str) -> list[Projection]:
        return [Projection.model_validate(d) for d in self._projections.values() if d["entity_id"] == eid]
    def get_projection(self, pid: str) -> Projection | None:
        d = self._projections.get(pid)
        return Projection.model_validate(d) if d else None
    def update_projection(self, p: Projection) -> Projection:
        self._store(self._projections, p.id, p.model_dump())
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
            if d["name"] == name and universe in d["universes"]:
                return Trait.model_validate(d)
        return None

    def get_traits_by_universe(self, universe: str) -> list[Trait]:
        return [Trait.model_validate(d) for d in self._traits.values() if universe in d["universes"]]

    def get_traitsets_by_universe(self, universe: str) -> list[TraitSet]:
        return [TraitSet.model_validate(d) for d in self._traitsets.values() if universe in d["universes"]]

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
    def get_relationship_traitsettings_for_entity(self, entity_id: str) -> list[dict]:
        # No relationship edges in the plain in-memory double.
        return []
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

    # traitsetsettings
    def create_traitsetsetting(self, tss: TraitSetSetting) -> TraitSetSetting:
        self._store(self._traitsetsettings, tss.id, tss.model_dump())
        return tss
    def get_traitsetsettings_for_entity(self, eid: str) -> list[TraitSetSetting]:
        return [
            TraitSetSetting.model_validate(d)
            for d in self._traitsetsettings.values()
            if d["entity_id"] == eid
        ]

    # sfx owners
    def get_sfx_owner(self, owner_id: str) -> SfxOwner | None:
        d = self._sfx_owners.get(owner_id)
        return SfxOwner.model_validate(d) if d else None

    # effective traits
    def get_effective_traitsettings(self, eid: str, universes: list[str]) -> list[TraitSetting]:
        universe_trait_ids = {tid for tid, d in self._traits.items() if any(u in d["universes"] for u in universes)}
        return [
            TraitSetting.model_validate(d)
            for d in self._traitsettings.values()
            if d["entity_id"] == eid and (d["trait_id"] in universe_trait_ids or d.get("from_type") == "entity")
        ]

    def get_effective_traitsetsettings(self, eid: str, universes: list[str]) -> list:
        return []

    # assembly
    def assemble_character(self, eid: str):
        entity = self.get_entity(eid)
        if not entity:
            return None
        return CharacterView(
            entity=entity,
            projections=self.get_projections_for_entity(eid),
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

    def test_universe_key_derived_from_name_and_unique(self, em):
        em.create(name="Earth", entity_type=EntityType.UNIVERSE, universe="ignored")
        cyber = em.create(name="Cyberpunk", entity_type=EntityType.UNIVERSE, universe="ignored")
        assert cyber.current_universe == "cyberpunk"

        # A second universe with the same name gets a numbered suffix, never a
        # shared key that would collide in the location tree.
        cyber2 = em.create(name="Cyberpunk", entity_type=EntityType.UNIVERSE, universe="ignored")
        assert cyber2.current_universe == "cyberpunk-2"


class TestProjections:
    def test_add_projection(self, em, kael):
        em.add_projection(kael, "three_realms")
        projs = em.get_projections(kael.id)
        assert len(projs) == 2
        universes = {p.universe for p in projs}
        assert universes == {"earth", "three_realms"}

    def test_duplicate_universe_allowed(self, em, kael):
        em.add_projection(kael, "earth")
        earth_projs = [p for p in em.get_projections(kael.id) if p.universe == "earth"]
        assert len(earth_projs) == 2
        ids = {p.id for p in earth_projs}
        assert f"{kael.id}:earth" in ids
        assert f"{kael.id}:earth:2" in ids

    def test_effective_universes(self, em, repo, kael):
        # base = active projection's universe
        assert repo.effective_universes(kael) == ["earth"]

        # a self attunement adds its universe
        kael.attunements.append(Attunement(universe="three_realms", scope=AttunementScope.SELF))
        repo.update_entity(kael)
        assert repo.effective_universes(kael) == ["earth", "three_realms"]


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
        assert any(p.universe == "earth" for p in cv.projections)
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
        # Earth trait (morph — anchored to the Earth projection)
        earth_t = Trait(id="trait-earth-hacking", name="hacking", universes=["earth"],
                        traitset_id="ts-earth-skills")
        repo.create_trait(earth_t)
        # Ego trait (curiosity — personality, not universe-specific)
        ego_t = Trait(id="trait-ego-curious", name="curious", universes=["earth"],
                      traitset_id="ts-earth-distinctions")
        repo.create_trait(ego_t)

        em.add_traitsetting(TraitSetting(
            id=f"{kael.id}:hacking", entity_id=kael.id, trait_id="trait-earth-hacking",
            traitset_id="ts-earth-skills", dice=[DieType.D10],
            from_type="projection", projection_id=f"{kael.id}:earth",
        ))
        em.add_traitsetting(TraitSetting(
            id=f"{kael.id}:curious", entity_id=kael.id, trait_id="trait-ego-curious",
            traitset_id="ts-earth-distinctions", dice=[DieType.D8],
        ))

        # On Earth: both available
        earth_traits = em.get_effective_traitsettings(kael.id, ["earth"])
        earth_names = {repo.get_trait(ts.trait_id).name for ts in earth_traits}
        assert "hacking" in earth_names
        assert "curious" in earth_names

        # In Three Realms: only curious (ego), not hacking (Earth morph)
        realm_traits = em.get_effective_traitsettings(kael.id, ["three_realms"])
        realm_names = {repo.get_trait(ts.trait_id).name for ts in realm_traits}
        assert "hacking" not in realm_names
        assert "curious" in realm_names


class TestLocation:
    def test_move(self, em, kael):
        em.move_to(kael, "Valley of Ascension", "three_realms")
        updated = em.get(kael.id)
        assert updated.current_location == "Valley of Ascension"
        assert updated.current_universe == "three_realms"

    def test_move_ignores_mismatched_universe(self, em, kael):
        # Destination location is on Earth; a wrong client universe must be ignored.
        loc = em.create(name="Krasnoyarsk", entity_type=EntityType.LOCATION, universe="earth")
        em.move_to(kael, loc.id, "three_realms")
        updated = em.get(kael.id)
        assert updated.current_location == loc.id
        assert updated.current_universe == "earth"

    def test_move_omitted_universe_follows_location(self, em, kael):
        # Universe omitted → derive it from the destination location, not the old one.
        loc = em.create(name="Aviary Peak", entity_type=EntityType.LOCATION, universe="three_realms")
        em.move_to(kael, loc.id)
        updated = em.get(kael.id)
        assert updated.current_location == loc.id
        assert updated.current_universe == "three_realms"
        proj = em.repo.get_projection(f"{kael.id}:earth")
        assert proj.universe == "three_realms"
        assert proj.current_location == loc.id

    def test_travel_consciousness(self, em, kael):
        loc = em.create(name="Aviary Peak", entity_type=EntityType.LOCATION, universe="three_realms")
        result = em.travel(kael.id, loc.id, transversal_type="consciousness", projection_policy="{last_projection}")
        assert result.current_projection == f"{kael.id}:three_realms"
        assert result.current_universe == "three_realms"
        assert result.current_location == loc.id
        proj = em.repo.get_projection(f"{kael.id}:three_realms")
        assert proj is not None
        assert proj.transversal_type == TransversalType.CONSCIOUSNESS
        assert proj.origin_universe == "three_realms"

    def test_travel_inapposite(self, em, kael):
        loc = em.create(name="Aviary Peak", entity_type=EntityType.LOCATION, universe="three_realms")
        result = em.travel(kael.id, loc.id, transversal_type="inapposite")
        # key stays origin-earth even though the body is now in three_realms
        assert result.current_projection == f"{kael.id}:earth"
        proj = em.repo.get_projection(f"{kael.id}:earth")
        assert proj.universe == "three_realms"
        assert proj.origin_universe == "earth"
        assert proj.transversal_type == TransversalType.INAPPOSITE

    def test_travel_effect_self_entity_id_persists(self, em, kael):
        # A travel effect whose ``entity`` is the entity's own id must not be
        # overwritten by the stale primary instance in commit_effects.
        from transversal.domain import Effect, EffectTiming
        from transversal.services.effects_commit import commit_effects

        loc = em.create(name="Aviary Peak", entity_type=EntityType.LOCATION, universe="three_realms")
        effect = Effect(
            timing=EffectTiming.IMMEDIATE,
            type="travel", action="move",
            target=loc.id,
            entity=kael.id,  # self by id, not ""/"self"
            context={"transversal_type": "inapposite"},
        )
        commit_effects(kael, [effect], em.repo)

        updated = em.get(kael.id)
        assert updated.current_location == loc.id
        assert updated.current_universe == "three_realms"


def test_origin_universe_from_key_handles_suffix():
    from transversal.services.entity_manager import _origin_universe_from_key
    assert _origin_universe_from_key("character-1:earth") == "earth"
    assert _origin_universe_from_key("character-1:earth:2") == "earth"
    assert _origin_universe_from_key("x") == ""
