"""Integration tests for deletion cascades (orphan prevention).

These verify, against live ArangoDB, that every repository delete path removes
its dependents — projections, trait settings, trait-set settings, relationship
edges, scheduled-event timers, images, and owned roll tables — rather than
leaving them orphaned. They build isolated fixture data and tear it down, so
they never depend on a live entity or its mutable state. They skip when ArangoDB
is unavailable.
"""

import pytest

from transversal.db.repository import EntityRepository
from transversal.domain import (
    DieType,
    Effect,
    Entity,
    MediaImage,
    EntityType,
    ImageType,
    LifePath,
    Projection,
    RatingType,
    RollTable,
    SFX,
    SfxOwner,
    ScheduledEvent,
    Trait,
    TraitSet,
    TraitSetSetting,
    TraitSetting,
    TransversalType,
)

try:
    _repo = EntityRepository()
    HAVE_DB = True
except Exception:
    _repo = None
    HAVE_DB = False

pytestmark = pytest.mark.skipif(not HAVE_DB, reason="ArangoDB not available")


# ── Fixture id namespace ──────────────────────────────

# rmtree / B49
PARENT = "test-cascade-parent"
CHILD = "test-cascade-child"
OCCUPANT = "test-cascade-occupant"
OTHER = "test-cascade-other"
PROJ1 = "test-cascade-proj1"
TRAIT1 = "test-cascade-trait1"
TRAITSET1 = "test-cascade-ts1"

# entity → trait-set settings
E2 = "test-cascade-e2"
TRAITSET2 = "test-cascade-ts2"
TSS2 = "test-cascade-tss2"

# projection cascade
E3 = "test-cascade-e3"
E3B = "test-cascade-e3b"
PROJ3 = "test-cascade-proj3"
TRAIT3 = "test-cascade-trait3"
TRAITSET3 = "test-cascade-ts3"
PTS3 = "test-cascade-pts3"
PTSS3 = "test-cascade-ptss3"
IMG3 = "test-cascade-img3"

# relationship cascade
E4A = "test-cascade-e4a"
E4B = "test-cascade-e4b"
TRAIT4 = "test-cascade-trait4"
TRAITSET4 = "test-cascade-ts4"
RTS4 = "test-cascade-rts4"

# traitset cascade
E5 = "test-cascade-e5"
TRAIT5 = "test-cascade-trait5"
TRAITSET5 = "test-cascade-ts5"
TSS5 = "test-cascade-tss5"

# life path cascade
LP6 = "test-cascade-lp6"
RT6 = "test-cascade-rt6"

# SFX reference integrity
SFX7 = "test-cascade-sfx"
E7 = "test-cascade-sfx-entity"
PROJ7 = "test-cascade-sfx-proj"
TRAIT7 = "test-cascade-sfx-trait"
TRAITSET7 = "test-cascade-sfx-traitset"
TS7 = "test-cascade-sfx-tsetting"
TSS7 = "test-cascade-sfx-tss"
OWNER7 = "test-cascade-sfx-owner"

_ENTITY_IDS = [PARENT, CHILD, OCCUPANT, OTHER, E2, E3, E3B, E4A, E4B, E5, E7]
_TRAIT_IDS = [TRAIT1, TRAIT3, TRAIT4, TRAIT5, TRAIT7]
_TRAITSET_IDS = [TRAITSET1, TRAITSET2, TRAITSET3, TRAITSET4, TRAITSET5, TRAITSET7]
_LP_IDS = [LP6]
_RT_IDS = [RT6]
_SFX_IDS = [SFX7]
_OWNER_IDS = [OWNER7]


def _cleanup(repo):
    """Remove all fixture data (idempotent — safe on a partial/absent run)."""
    for eid in _ENTITY_IDS:
        repo.delete_entity(eid, rmtree=True)
    for pid in (PROJ1, PROJ3, PROJ7):
        repo.delete_projection(pid)
    for tid in _TRAIT_IDS:
        repo.delete_trait(tid)
    for tsid in _TRAITSET_IDS:
        repo.delete_traitset(tsid)
    for lpid in _LP_IDS:
        repo.delete_lifepath(lpid)
    for rtid in _RT_IDS:
        repo.delete_roll_table(rtid)
    for sid in _SFX_IDS:
        repo.delete_sfx(sid)
    for oid in _OWNER_IDS:
        repo.delete_sfx_owner(oid)


def _char(eid: str, location: str | None = None) -> Entity:
    return Entity(
        id=eid,
        type=EntityType.CHARACTER,
        name=eid,
        current_universe="earth",
        current_location=location,
    )


def _location(eid: str) -> Entity:
    return Entity(
        id=eid,
        type=EntityType.LOCATION,
        name=eid,
        current_universe="earth",
    )


def _event(target_id: str) -> ScheduledEvent:
    return ScheduledEvent(
        id=f"ev-{target_id}",
        target_type="entity",
        target_id=target_id,
        effect=Effect(type="entity", action="targeting_ban"),
    )


# ── Tests ─────────────────────────────────────────────

def test_rmtree_prune_cascades_occupants():
    """B49: deleting a location with rmtree=True cleans its occupants fully."""
    repo = _repo
    _cleanup(repo)

    repo.create_traitset(TraitSet(id=TRAITSET1, name="t1", universes=["earth"]))
    repo.create_trait(Trait(id=TRAIT1, name="trait1", universes=["earth"], traitset_id=TRAITSET1))

    repo.create_entity(_location(PARENT))
    repo.create_entity(_location(CHILD))
    repo.create_relationship(CHILD, PARENT, "super")  # child → parent super edge
    repo.create_entity(_char(OCCUPANT, location=CHILD))
    repo.create_entity(_char(OTHER))
    repo.create_projection(Projection(
        id=PROJ1, entity_id=OCCUPANT, origin_universe="earth", universe="earth",
        transversal_type=TransversalType.NATIVE,
    ))
    repo.create_traitsetting(TraitSetting(
        id="test-cascade-ts-occ", entity_id=OCCUPANT, trait_id=TRAIT1,
         rating_type=RatingType.STATIC, dice=[DieType.D8],
    ))
    repo.create_scheduled_event(_event(OCCUPANT))
    repo.create_relationship(OCCUPANT, OTHER, "associate")

    repo.delete_entity(PARENT, rmtree=True)

    assert repo.get_entity(PARENT) is None
    assert repo.get_entity(CHILD) is None
    assert repo.get_entity(OCCUPANT) is None
    assert repo.get_entity(OTHER) is not None  # not an occupant — survives
    assert repo.get_projection(PROJ1) is None
    assert repo.get_traitsetting("test-cascade-ts-occ") is None
    assert repo.get_relationship(OCCUPANT, OTHER, "associate") is None
    assert OCCUPANT not in {e.target_id for e in repo.list_all_scheduled_events()}

    _cleanup(repo)


def test_entity_delete_cleans_traitset_settings():
    """Deleting an entity removes its trait-set settings (entity↔traitset edges)."""
    repo = _repo
    _cleanup(repo)

    repo.create_traitset(TraitSet(id=TRAITSET2, name="t2", universes=["earth"]))
    repo.create_entity(_char(E2))
    repo.create_traitsetsetting(TraitSetSetting(
        id=TSS2, entity_id=E2, traitset_id=TRAITSET2, from_type="entity",
    ))

    repo.delete_entity(E2)

    assert repo.get_traitsetsetting(TSS2) is None

    _cleanup(repo)


def test_delete_projection_cascades_dependents():
    """Deleting a projection removes its edges, settings, and images."""
    repo = _repo
    _cleanup(repo)

    repo.create_traitset(TraitSet(id=TRAITSET3, name="t3", universes=["earth"]))
    repo.create_trait(Trait(id=TRAIT3, name="trait3", universes=["earth"], traitset_id=TRAITSET3))
    repo.create_entity(_char(E3))
    repo.create_entity(_char(E3B))
    repo.create_projection(Projection(
        id=PROJ3, entity_id=E3, origin_universe="earth", universe="earth",
        transversal_type=TransversalType.NATIVE,
    ))
    repo.create_traitsetting(TraitSetting(
        id=PTS3, entity_id=E3, trait_id=TRAIT3,
        from_type="projection", projection_id=PROJ3,
        rating_type=RatingType.STATIC, dice=[DieType.D8],
    ))
    repo.create_traitsetsetting(TraitSetSetting(
        id=PTSS3, entity_id=E3, traitset_id=TRAITSET3, from_type="projection", projection_id=PROJ3,
    ))
    repo.create_image(MediaImage(
        id=IMG3, entity_id=E3, projection_id=PROJ3, universe="earth", image_type=ImageType.IMAGEN,
    ))
    repo.create_relationship(PROJ3, E3B, "morph", from_projection=True)

    repo.delete_projection(PROJ3)

    assert repo.get_projection(PROJ3) is None
    assert repo.get_traitsetting(PTS3) is None
    assert repo.get_traitsetsetting(PTSS3) is None
    assert repo.get_image(IMG3) is None
    assert repo.get_relationship(PROJ3, E3B, "morph", from_projection=True) is None
    assert repo.get_entity(E3) is not None  # the soul survives

    _cleanup(repo)


def test_delete_relationship_cascades_traitsettings():
    """Deleting a relationship removes trait settings anchored to its edge."""
    repo = _repo
    _cleanup(repo)

    repo.create_traitset(TraitSet(id=TRAITSET4, name="t4", universes=["earth"]))
    repo.create_trait(Trait(id=TRAIT4, name="trait4", universes=["earth"], traitset_id=TRAITSET4))
    repo.create_entity(_char(E4A))
    repo.create_entity(_char(E4B))
    edge = repo.create_relationship(E4A, E4B, "relation")
    repo.create_traitsetting(TraitSetting(
        id=RTS4, entity_id=edge["_key"], trait_id=TRAIT4,
        from_type="relationship", rating_type=RatingType.STATIC, dice=[DieType.D8],
    ))

    repo.delete_relationship(E4A, E4B, "relation")

    assert repo.get_relationship(E4A, E4B, "relation") is None
    assert repo.get_traitsetting(RTS4) is None

    _cleanup(repo)


def test_delete_traitset_cascades_traitset_settings():
    """Deleting a trait set removes its entity↔traitset settings."""
    repo = _repo
    _cleanup(repo)

    repo.create_traitset(TraitSet(id=TRAITSET5, name="t5", universes=["earth"]))
    repo.create_trait(Trait(id=TRAIT5, name="trait5", universes=["earth"], traitset_id=TRAITSET5))
    repo.create_entity(_char(E5))
    repo.create_traitsetsetting(TraitSetSetting(
        id=TSS5, entity_id=E5, traitset_id=TRAITSET5, from_type="entity",
    ))

    repo.delete_traitset(TRAITSET5)

    assert repo.get_traitsetsetting(TSS5) is None
    assert repo.get_trait(TRAIT5) is None

    _cleanup(repo)


def test_delete_lifepath_cascades_roll_tables():
    """Deleting a life path removes the roll tables it owns."""
    repo = _repo
    _cleanup(repo)

    repo.create_lifepath(LifePath(id=LP6, name="lp6", universe="earth"))
    repo.create_roll_table(RollTable(id=RT6, name="rt6", universe="earth", life_path=LP6))

    repo.delete_lifepath(LP6)

    assert repo.get_lifepath(LP6) is None
    assert repo.get_roll_table(RT6) is None

    _cleanup(repo)


def test_delete_sfx_strips_owner_references():
    """Deleting an SFX removes its id from every owner surface."""
    repo = _repo
    _cleanup(repo)

    repo.create_sfx(SFX(id=SFX7, name="sfx7", trigger="manual"))
    repo.create_traitset(TraitSet(id=TRAITSET7, name="ts7", universes=["earth"]))
    repo.create_trait(Trait(
        id=TRAIT7, name="trait7", universes=["earth"], traitset_id=TRAITSET7,
        default_sfx_ids=[SFX7], possible_sfx_ids=[SFX7],
    ))
    repo.create_entity(Entity(
        id=E7, type=EntityType.CHARACTER, name=E7, current_universe="earth",
        sfx_ids=[SFX7],
    ))
    repo.create_projection(Projection(
        id=PROJ7, entity_id=E7, origin_universe="earth", universe="earth",
        transversal_type=TransversalType.NATIVE, sfx_ids=[SFX7],
    ))
    repo.create_traitsetting(TraitSetting(
        id=TS7, entity_id=E7, trait_id=TRAIT7,
        rating_type=RatingType.STATIC, dice=[DieType.D8], sfx_ids=[SFX7],
    ))
    repo.create_traitsetsetting(TraitSetSetting(
        id=TSS7, entity_id=E7, traitset_id=TRAITSET7, from_type="entity", sfx_ids=[SFX7],
    ))
    repo.create_sfx_owner(SfxOwner(id=OWNER7, sfx_ids=[SFX7]))

    repo.delete_sfx(SFX7)

    assert repo.get_sfx(SFX7) is None
    assert SFX7 not in repo.get_entity(E7).sfx_ids
    assert SFX7 not in repo.get_projection(PROJ7).sfx_ids
    assert SFX7 not in repo.get_trait(TRAIT7).default_sfx_ids
    assert SFX7 not in repo.get_trait(TRAIT7).possible_sfx_ids
    assert SFX7 not in repo.get_traitsetting(TS7).sfx_ids
    assert SFX7 not in repo.get_traitsetsetting(TSS7).sfx_ids
    assert SFX7 not in repo.get_sfx_owner(OWNER7).sfx_ids

    _cleanup(repo)
