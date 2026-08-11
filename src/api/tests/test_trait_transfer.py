"""Tests for trait transfer mutations — teach, gift, and take."""

import pytest

from transversal.db.repository import EntityRepository
from transversal.domain import (
    DieType,
    Entity,
    EntityType,
    Trait,
    TraitSet,
    TraitSetting,
    TransferFlags,
)
from transversal.services.trait_transfer import (
    teach_trait,
    gift_trait,
    take_trait,
    resolve_transfer_flags,
)


# ── Extended In-Memory Repository ──────────────────────

class InMemoryRepository(EntityRepository):
    def __init__(self):
        self._entities: dict[str, dict] = {}
        self._projections: dict[str, dict] = {}
        self._traits: dict[str, dict] = {}
        self._traitsets: dict[str, dict] = {}
        self._traitsettings: dict[str, dict] = {}
        self._relationships: list[dict] = []
        self.db = None

    def _store(self, coll: dict, key: str, doc: dict) -> dict:
        doc["_key"] = key
        coll[key] = doc
        return doc

    # Entities
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

    # Projections
    def create_projection(self, p):
        self._store(self._projections, p.id, p.model_dump())
        return p

    def get_projections_for_entity(self, eid):
        from transversal.domain import Projection
        return [Projection.model_validate(d) for d in self._projections.values() if d["entity_id"] == eid]

    def update_projection(self, p):
        self._projections[p.id] = p.model_dump()
        return p

    # Traits
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

    # Traitsets
    def create_traitset(self, ts: TraitSet) -> TraitSet:
        self._store(self._traitsets, ts.id, ts.model_dump())
        return ts

    def get_traitset_by_id(self, tsid: str):
        d = self._traitsets.get(tsid)
        return TraitSet.model_validate(d) if d else None

    def get_traitsets_by_universe(self, universe: str) -> list[TraitSet]:
        return [TraitSet.model_validate(d) for d in self._traitsets.values() if universe in d["universes"]]

    # TraitSettings
    def create_traitsetting(self, ts: TraitSetting) -> TraitSetting:
        self._store(self._traitsettings, ts.id, ts.model_dump())
        return ts

    def get_traitsetting(self, ts_id: str):
        d = self._traitsettings.get(ts_id)
        return TraitSetting.model_validate(d) if d else None

    def get_traitsettings_for_entity(self, eid: str) -> list[TraitSetting]:
        return [TraitSetting.model_validate(d) for d in self._traitsettings.values() if d["entity_id"] == eid]

    def get_traitsettings_by_traitset(self, eid, tsid) -> list[TraitSetting]:
        return [TraitSetting.model_validate(d) for d in self._traitsettings.values()
                if d["entity_id"] == eid and d["traitset_id"] == tsid]

    def update_traitsetting(self, ts: TraitSetting) -> TraitSetting:
        self._store(self._traitsettings, ts.id, ts.model_dump())
        return ts

    def delete_traitsetting(self, tsid: str) -> bool:
        return self._traitsettings.pop(tsid, None) is not None

    def get_effective_traitsettings(self, eid: str, universe: str) -> list[TraitSetting]:
        universe_trait_ids = {tid for tid, d in self._traits.items() if universe in d["universes"]}
        return [
            TraitSetting.model_validate(d)
            for d in self._traitsettings.values()
            if d["entity_id"] == eid and (d["trait_id"] in universe_trait_ids or d.get("ego", False))
        ]

    # Relationships
    def create_relationship(self, from_id: str, to_id: str, rel_type: str, description: str = "") -> dict:
        rel = {
            "_key": f"{from_id}:{to_id}:{rel_type}",
            "from_entity_id": from_id,
            "to_entity_id": to_id,
            "type": rel_type,
            "description": description,
        }
        self._relationships.append(rel)
        return rel

    def delete_relationship(self, from_id: str, to_id: str, rel_type: str) -> bool:
        key = f"{from_id}:{to_id}:{rel_type}"
        for i, r in enumerate(self._relationships):
            if r["_key"] == key:
                self._relationships.pop(i)
                return True
        return False

    # Assembly
    def assemble_character(self, eid: str):
        entity = self.get_entity(eid)
        if not entity:
            return None
        from transversal.domain import CharacterView
        return CharacterView(
            entity=entity,
            projections={p.universe: p for p in self.get_projections_for_entity(eid)},
            trait_settings=self.get_traitsettings_for_entity(eid),
        )


# ── Fixtures ────────────────────────────────────────────

@pytest.fixture
def repo():
    return InMemoryRepository()


@pytest.fixture
def teacher(repo):
    e = Entity(id="teacher-1", type=EntityType.CHARACTER, name="Kael Drift",
               current_universe="earth", razmerit=5)
    repo.create_entity(e)
    return e


@pytest.fixture
def student(repo):
    e = Entity(id="student-1", type=EntityType.CHARACTER, name="Elena",
               current_universe="earth", razmerit=0)
    repo.create_entity(e)
    return e


@pytest.fixture
def giver(repo):
    e = Entity(id="giver-1", type=EntityType.CHARACTER, name="Giver",
               current_universe="earth", razmerit=5)
    repo.create_entity(e)
    return e


@pytest.fixture
def recipient(repo):
    e = Entity(id="recipient-1", type=EntityType.CHARACTER, name="Recipient",
               current_universe="earth", razmerit=0)
    repo.create_entity(e)
    return e


@pytest.fixture
def taker(repo):
    e = Entity(id="taker-1", type=EntityType.CHARACTER, name="Thief",
               current_universe="earth", razmerit=5)
    repo.create_entity(e)
    return e


@pytest.fixture
def victim(repo):
    e = Entity(id="victim-1", type=EntityType.CHARACTER, name="Target",
               current_universe="earth", razmerit=2)
    repo.create_entity(e)
    return e


@pytest.fixture
def teachable_trait_and_set(repo):
    """A trait and traitset with teachable flag."""
    ts = TraitSet(
        id="ts-earth-skills", name="skills", universes=["earth"],
        transfer_flags=TransferFlags(teachable=True, giftable=True, takable=True),
    )
    repo.create_traitset(ts)
    trait = Trait(
        id="trait-earth-hacking", name="hacking", universes=["earth"],
        traitset_id="ts-earth-skills", default_die_type=DieType.D6,
    )
    repo.create_trait(trait)
    return trait, ts


@pytest.fixture
def non_teachable_trait_and_set(repo):
    """A trait and traitset with NO transfer flags (all false)."""
    ts = TraitSet(
        id="ts-earth-locked", name="locked_skills", universes=["earth"],
    )
    repo.create_traitset(ts)
    trait = Trait(
        id="trait-earth-secret", name="secret_tech", universes=["earth"],
        traitset_id="ts-earth-locked", default_die_type=DieType.D8,
    )
    repo.create_trait(trait)
    return trait, ts


@pytest.fixture
def trait_with_override(repo):
    """Trait whose own flags override the traitset."""
    ts = TraitSet(
        id="ts-earth-override", name="override_set", universes=["earth"],
        transfer_flags=TransferFlags(teachable=False),
    )
    repo.create_traitset(ts)
    trait = Trait(
        id="trait-earth-override", name="override_trait", universes=["earth"],
        traitset_id="ts-earth-override", default_die_type=DieType.D6,
        transfer_flags=TransferFlags(teachable=True),
    )
    repo.create_trait(trait)
    return trait, ts


# ── Tests ───────────────────────────────────────────────

class TestTeachTrait:
    def test_teacher_d10_student_gets_d6(self, repo, teacher, student, teachable_trait_and_set):
        trait, _ts = teachable_trait_and_set
        # Create teacher's TraitSetting at d10
        teacher_ts = TraitSetting(
            id=f"{teacher.id}:{trait.id}",
            entity_id=teacher.id,
            trait_id=trait.id,
            traitset_id=trait.traitset_id,
            dice=[DieType.D10],
        )
        repo.create_traitsetting(teacher_ts)

        result = teach_trait(teacher.id, student.id, teacher_ts.id, repo)

        student_ts = result["student_trait_setting"]
        assert student_ts.entity_id == student.id
        assert student_ts.dice == [DieType.D6]
        assert student_ts.source_type == "taught"
        assert student_ts.source_entity_id == teacher.id
        assert student_ts.source_trait_setting_id == teacher_ts.id
        assert result["razmerit_cost"] == 1

    def test_teacher_d6_student_gets_d4(self, repo, teacher, student, teachable_trait_and_set):
        trait, _ts = teachable_trait_and_set
        teacher_ts = TraitSetting(
            id=f"{teacher.id}:{trait.id}",
            entity_id=teacher.id,
            trait_id=trait.id,
            traitset_id=trait.traitset_id,
            dice=[DieType.D6],
        )
        repo.create_traitsetting(teacher_ts)

        result = teach_trait(teacher.id, student.id, teacher_ts.id, repo)

        student_ts = result["student_trait_setting"]
        assert student_ts.dice == [DieType.D4]

    def test_non_teachable_raises(self, repo, teacher, student, non_teachable_trait_and_set):
        trait, _ts = non_teachable_trait_and_set
        teacher_ts = TraitSetting(
            id=f"{teacher.id}:{trait.id}",
            entity_id=teacher.id,
            trait_id=trait.id,
            traitset_id=trait.traitset_id,
            dice=[DieType.D10],
        )
        repo.create_traitsetting(teacher_ts)

        with pytest.raises(ValueError, match="not teachable"):
            teach_trait(teacher.id, student.id, teacher_ts.id, repo)


class TestGiftTrait:
    def test_entity_id_changes(self, repo, giver, recipient, teachable_trait_and_set):
        trait, _ts = teachable_trait_and_set
        giver_ts = TraitSetting(
            id=f"{giver.id}:{trait.id}",
            entity_id=giver.id,
            trait_id=trait.id,
            traitset_id=trait.traitset_id,
            dice=[DieType.D10],
        )
        repo.create_traitsetting(giver_ts)

        result = gift_trait(giver.id, recipient.id, giver_ts.id, repo)

        transferred = result["transferred_trait"]
        assert transferred.entity_id == recipient.id
        assert transferred.id == f"{recipient.id}:{trait.id}"
        assert transferred.source_type == "gifted"
        assert transferred.source_entity_id == giver.id
        assert result["relationship_created"] is not None

    def test_non_giftable_raises(self, repo, giver, recipient, non_teachable_trait_and_set):
        trait, _ts = non_teachable_trait_and_set
        giver_ts = TraitSetting(
            id=f"{giver.id}:{trait.id}",
            entity_id=giver.id,
            trait_id=trait.id,
            traitset_id=trait.traitset_id,
            dice=[DieType.D8],
        )
        repo.create_traitsetting(giver_ts)

        with pytest.raises(ValueError, match="not giftable"):
            gift_trait(giver.id, recipient.id, giver_ts.id, repo)


class TestTakeTrait:
    def test_contested_success_transfers(self, repo, taker, victim, teachable_trait_and_set):
        trait, _ts = teachable_trait_and_set

        # Give taker strong combat trait for contest
        taker_combat = TraitSetting(
            id=f"{taker.id}:combat",
            entity_id=taker.id,
            trait_id="trait-earth-combat",
            traitset_id=trait.traitset_id,
            dice=[DieType.D12, DieType.D12, DieType.D12],
        )
        repo.create_traitsetting(taker_combat)
        # Register the combat trait
        combat_trait = Trait(
            id="trait-earth-combat", name="combat", universes=["earth"],
            traitset_id="ts-earth-skills", default_die_type=DieType.D8,
        )
        repo.create_trait(combat_trait)

        # Victim has a weak trait
        victim_ts = TraitSetting(
            id=f"{victim.id}:{trait.id}",
            entity_id=victim.id,
            trait_id=trait.id,
            traitset_id=trait.traitset_id,
            dice=[DieType.D4],
        )
        repo.create_traitsetting(victim_ts)

        result = take_trait(taker.id, victim.id, victim_ts.id, "combat", repo)

        # With d12 dice pool vs d4, taker should almost always win
        if result["success"]:
            transferred = result["transferred_trait"]
            assert transferred.entity_id == taker.id
            assert transferred.source_type == "taken"
            assert transferred.source_entity_id == victim.id
            assert transferred.stolen is True
        else:
            # If by some miracle the victim wins, there should be a suspects relationship
            assert result["transferred_trait"] is None

    def test_non_takable_raises(self, repo, taker, victim, non_teachable_trait_and_set):
        trait, _ts = non_teachable_trait_and_set
        victim_ts = TraitSetting(
            id=f"{victim.id}:{trait.id}",
            entity_id=victim.id,
            trait_id=trait.id,
            traitset_id=trait.traitset_id,
            dice=[DieType.D8],
        )
        repo.create_traitsetting(victim_ts)

        with pytest.raises(ValueError, match="not takable"):
            take_trait(taker.id, victim.id, victim_ts.id, "stealth", repo)


class TestResolveTransferFlags:
    def test_trait_override_of_traitset(self, repo, teacher, trait_with_override):
        trait, _ts = trait_with_override
        ts_setting = TraitSetting(
            id=f"{teacher.id}:{trait.id}",
            entity_id=teacher.id,
            trait_id=trait.id,
            traitset_id=trait.traitset_id,
            dice=[DieType.D6],
        )
        repo.create_traitsetting(ts_setting)

        flags = resolve_transfer_flags(ts_setting, repo)
        # trait has teachable=True, traitset has teachable=False
        assert flags.teachable is True

    def test_inherit_from_traitset(self, repo, teacher, teachable_trait_and_set):
        trait, _ts = teachable_trait_and_set
        ts_setting = TraitSetting(
            id=f"{teacher.id}:{trait.id}",
            entity_id=teacher.id,
            trait_id=trait.id,
            traitset_id=trait.traitset_id,
            dice=[DieType.D6],
        )
        repo.create_traitsetting(ts_setting)

        flags = resolve_transfer_flags(ts_setting, repo)
        # trait has no transfer_flags, so inherit from traitset
        assert flags.teachable is True
        assert flags.giftable is True
        assert flags.takable is True
