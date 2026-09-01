"""DB-backed tests for sub-trait plumbing (traitsetting-anchored trait settings).

Sub-traits reuse the ``traitsettings`` edge collection with
``from_type='traitsetting'`` and ``_from → traitsettings/{parent}``. These tests
exercise the anchor write/read paths, flat-list exclusion, and cascade cleanup.
"""

import pytest

from transversal.db.repository import EntityRepository
from transversal.domain import (
    DieType,
    Entity,
    EntityType,
    Trait,
    TraitSet,
    TraitSetting,
)

try:
    _repo = EntityRepository()
    HAVE_DB = True
except Exception:
    _repo = None
    HAVE_DB = False

pytestmark = pytest.mark.skipif(not HAVE_DB, reason="ArangoDB not available")


ENTITY_ID = "test-sub-entity"
PARENT_TSET = "ts-sub-parent"
CHILD_TSET = "ts-sub-child"
PARENT_TRAIT = "trait-sub-parent"
CHILD_TRAIT = "trait-sub-child"
GRANDCHILD_TRAIT = "trait-sub-grandchild"


def _seed_registry(repo):
    for tset in [
        TraitSet(id=PARENT_TSET, name="parent set", universes=["earth"],
                 entity_types=[EntityType.CHARACTER]),
        TraitSet(id=CHILD_TSET, name="sub set", universes=["earth"],
                 entity_types=[EntityType.SUBTRAIT]),
    ]:
        if not repo.get_traitset_by_id(tset.id):
            repo.create_traitset(tset)

    for trait in [
        Trait(id=PARENT_TRAIT, name="Parent", universes=["earth"],
              traitset_id=PARENT_TSET, default_die_type=DieType.D8,
              possible_subtrait_ids=[CHILD_TRAIT]),
        Trait(id=CHILD_TRAIT, name="Child", universes=["earth"],
              traitset_id=CHILD_TSET, default_die_type=DieType.D6,
              possible_subtrait_ids=[GRANDCHILD_TRAIT]),
        Trait(id=GRANDCHILD_TRAIT, name="Grandchild", universes=["earth"],
              traitset_id=CHILD_TSET, default_die_type=DieType.D4),
    ]:
        if not repo.get_trait(trait.id):
            repo.create_trait(trait)


def _cleanup(repo):
    repo.delete_entity(ENTITY_ID)
    for tid in (PARENT_TRAIT, CHILD_TRAIT, GRANDCHILD_TRAIT):
        repo.delete_trait(tid)
    for tsid in (PARENT_TSET, CHILD_TSET):
        repo.delete_traitset(tsid)


@pytest.fixture(scope="module")
def repo():
    _cleanup(_repo)
    _seed_registry(_repo)
    _repo.create_entity(Entity(
        id=ENTITY_ID, type=EntityType.CHARACTER, name="Sub", current_universe="earth",
    ))
    yield _repo
    _cleanup(_repo)


def _parent_setting(repo) -> TraitSetting:
    ts = TraitSetting(
        id=f"{ENTITY_ID}:{PARENT_TRAIT}",
        entity_id=ENTITY_ID,
        trait_id=PARENT_TRAIT,
        traitset_id=PARENT_TSET,
        from_type="entity",
        dice=[DieType.D8],
    )
    return repo.create_traitsetting(ts)


def test_sub_trait_anchor_and_readback(repo):
    parent = _parent_setting(repo)
    sub = repo.create_traitsetting(TraitSetting(
        id=f"{parent.id}:{CHILD_TRAIT}",
        entity_id=ENTITY_ID,
        trait_id=CHILD_TRAIT,
        traitset_id=CHILD_TSET,
        from_type="traitsetting",
        parent_traitsetting_id=parent.id,
        dice=[DieType.D6],
    ))

    try:
        # Anchor points at the parent's document in the same edge collection.
        doc = repo._traitsettings.get(sub.id)
        assert doc["_from"] == f"traitsettings/{parent.id}"
        assert doc["_to"] == f"traits/{CHILD_TRAIT}"
        assert doc["parent_traitsetting_id"] == parent.id
        assert doc["entity_id"] == ENTITY_ID

        # Nested read returns the sub-trait under its parent.
        nested = repo.get_sub_traitsettings(parent.id)
        assert [s.id for s in nested] == [sub.id]

        # Flat entity enumeration excludes sub-traits (they live nested).
        flat_ids = [s.id for s in repo.get_traitsettings_for_entity(ENTITY_ID)]
        assert sub.id not in flat_ids
        assert parent.id in flat_ids
    finally:
        repo.delete_traitsetting(sub.id)
        repo.delete_traitsetting(parent.id)


def test_recursive_cascade_on_parent_delete(repo):
    parent = _parent_setting(repo)
    sub = repo.create_traitsetting(TraitSetting(
        id=f"{parent.id}:{CHILD_TRAIT}",
        entity_id=ENTITY_ID,
        trait_id=CHILD_TRAIT,
        traitset_id=CHILD_TSET,
        from_type="traitsetting",
        parent_traitsetting_id=parent.id,
        dice=[DieType.D6],
    ))
    grand = repo.create_traitsetting(TraitSetting(
        id=f"{sub.id}:{GRANDCHILD_TRAIT}",
        entity_id=ENTITY_ID,
        trait_id=GRANDCHILD_TRAIT,
        traitset_id=CHILD_TSET,
        from_type="traitsetting",
        parent_traitsetting_id=sub.id,
        dice=[DieType.D4],
    ))

    # Deleting the parent removes the whole nested chain.
    repo.delete_traitsetting(parent.id)
    assert repo.get_traitsetting(parent.id) is None
    assert repo.get_traitsetting(sub.id) is None
    assert repo.get_traitsetting(grand.id) is None


def test_entity_cascade_removes_sub_traits(repo):
    parent = _parent_setting(repo)
    sub = repo.create_traitsetting(TraitSetting(
        id=f"{parent.id}:{CHILD_TRAIT}",
        entity_id=ENTITY_ID,
        trait_id=CHILD_TRAIT,
        traitset_id=CHILD_TSET,
        from_type="traitsetting",
        parent_traitsetting_id=parent.id,
        dice=[DieType.D6],
    ))

    # Recreate the entity afterwards so the module-scoped fixture can clean up.
    repo.delete_entity(ENTITY_ID)
    assert repo.get_traitsetting(parent.id) is None
    assert repo.get_traitsetting(sub.id) is None

    repo.create_entity(Entity(
        id=ENTITY_ID, type=EntityType.CHARACTER, name="Sub", current_universe="earth",
    ))


def test_trait_definition_delete_cascades_subtree():
    repo = _repo
    E = "test-sub-del-entity"
    P_TS = "ts-sub-del-parent"
    C_TS = "ts-sub-del-child"
    P = "trait-sub-del-parent"
    C = "trait-sub-del-child"
    G = "trait-sub-del-grand"
    repo.delete_entity(E)
    for ts in [
        TraitSet(id=P_TS, name="p", universes=["earth"], entity_types=[EntityType.CHARACTER]),
        TraitSet(id=C_TS, name="c", universes=["earth"], entity_types=[EntityType.SUBTRAIT]),
    ]:
        if not repo.get_traitset_by_id(ts.id):
            repo.create_traitset(ts)
    for t in [
        Trait(id=P, name="P", universes=["earth"], traitset_id=P_TS, default_die_type=DieType.D8),
        Trait(id=C, name="C", universes=["earth"], traitset_id=C_TS, default_die_type=DieType.D6),
        Trait(id=G, name="G", universes=["earth"], traitset_id=C_TS, default_die_type=DieType.D4),
    ]:
        if not repo.get_trait(t.id):
            repo.create_trait(t)
    repo.create_entity(Entity(id=E, type=EntityType.CHARACTER, name="E", current_universe="earth"))
    try:
        parent = repo.create_traitsetting(TraitSetting(
            id=f"{E}:{P}", entity_id=E, trait_id=P, traitset_id=P_TS,
            from_type="entity", dice=[DieType.D8],
        ))
        sub = repo.create_traitsetting(TraitSetting(
            id=f"{parent.id}:{C}", entity_id=E, trait_id=C, traitset_id=C_TS,
            from_type="traitsetting", parent_traitsetting_id=parent.id, dice=[DieType.D6],
        ))
        grand = repo.create_traitsetting(TraitSetting(
            id=f"{sub.id}:{G}", entity_id=E, trait_id=G, traitset_id=C_TS,
            from_type="traitsetting", parent_traitsetting_id=sub.id, dice=[DieType.D4],
        ))

        # Deleting the child trait *definition* must remove its setting and the
        # grandchild nested under it.
        repo.delete_trait(C)
        assert repo.get_traitsetting(sub.id) is None
        assert repo.get_traitsetting(grand.id) is None
        # The parent setting (a different trait) survives.
        assert repo.get_traitsetting(parent.id) is not None
    finally:
        repo.delete_entity(E)
        for t in (P, C, G):
            repo.delete_trait(t)
        for tsid in (P_TS, C_TS):
            repo.delete_traitset(tsid)


def test_entity_delete_cascades_relationship_subtraits(repo):
    A = "test-sub-rel-a"
    B = "test-sub-rel-b"
    for e in (A, B):
        repo.delete_entity(e)
    repo.create_entity(Entity(id=A, type=EntityType.CHARACTER, name="A", current_universe="earth"))
    repo.create_entity(Entity(id=B, type=EntityType.CHARACTER, name="B", current_universe="earth"))
    try:
        edge = repo.create_relationship(A, B, "relation")
        rel_ts = repo.create_traitsetting(TraitSetting(
            id=f"{edge['_key']}:trust", entity_id=edge["_key"], trait_id="trait-rel-trust",
            traitset_id="ts-relations-b114", from_type="relationship", dice=[DieType.D6],
        ))
        sub = repo.create_traitsetting(TraitSetting(
            id=f"{rel_ts.id}:{CHILD_TRAIT}", entity_id=rel_ts.entity_id, trait_id=CHILD_TRAIT,
            traitset_id=CHILD_TSET, from_type="traitsetting",
            parent_traitsetting_id=rel_ts.id, dice=[DieType.D6],
        ))

        # Deleting the from-entity must remove the relationship setting and the
        # sub-trait nested under it (sub-trait entity_id is the edge key).
        repo.delete_entity(A)
        assert repo.get_traitsetting(rel_ts.id) is None
        assert repo.get_traitsetting(sub.id) is None
    finally:
        repo.delete_entity(A)
        repo.delete_entity(B)
