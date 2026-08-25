"""DB-backed tests for relationship endpoints (entity vs projection targets).

These exercise the real ``EntityRepository`` ArangoDB code paths for
entity→entity and entity→projection relationship edges, plus the edge-key
lookup used to resolve ego/morph for relationship trait settings.
"""

import pytest

from transversal.db.repository import EntityRepository
from transversal.domain import DieType, Entity, EntityType, Projection, TraitSetting, TransversalType

try:
    _repo = EntityRepository()
    HAVE_DB = True
except Exception:
    _repo = None
    HAVE_DB = False

pytestmark = pytest.mark.skipif(not HAVE_DB, reason="ArangoDB not available")


A_ID = "test-rel-endpoint-a"
B_ID = "test-rel-endpoint-b"
PROJ_ID = f"{B_ID}:earth"


def _cleanup(repo):
    repo.delete_entity(A_ID)  # removes edges where A is _from
    repo.delete_entity(B_ID)  # cascades B's projection


@pytest.fixture(scope="module")
def data():
    repo = _repo
    _cleanup(repo)

    repo.create_entity(Entity(id=A_ID, type=EntityType.CHARACTER, name="A", current_universe="earth"))
    repo.create_entity(Entity(id=B_ID, type=EntityType.CHARACTER, name="B", current_universe="earth"))
    repo.create_projection(Projection(
        id=PROJ_ID, entity_id=B_ID,
        origin_universe="earth", universe="earth",
        transversal_type=TransversalType.NATIVE,
    ))
    yield repo
    _cleanup(repo)


def test_entity_target_is_default(data):
    edge = data.create_relationship(A_ID, B_ID, "relation", description="entity target")
    doc = data.get_relationship_by_key(edge["_key"])
    assert doc["_to"] == f"entities/{B_ID}"
    assert doc["_from"] == f"entities/{A_ID}"


def test_projection_target(data):
    edge = data.create_relationship(A_ID, PROJ_ID, "relation", to_projection=True)
    doc = data.get_relationship_by_key(edge["_key"])
    assert doc["_to"] == f"projections/{PROJ_ID}"
    assert doc["_from"] == f"entities/{A_ID}"


def test_get_relationship_by_key(data):
    edge = data.create_relationship(A_ID, PROJ_ID, "relation", to_projection=True)
    fetched = data.get_relationship_by_key(edge["_key"])
    assert fetched is not None
    assert fetched["_key"] == edge["_key"]
    assert fetched["_to"] == f"projections/{PROJ_ID}"


def test_relationship_traitsettings_for_entity_readback(data):
    repo = data
    # Entity-target edge + trait.
    e1 = repo.create_relationship(A_ID, B_ID, "relation")
    ts1 = repo.create_traitsetting(TraitSetting(
        id=f"{e1['_key']}:trust", entity_id=e1["_key"], trait_id="trait-relation-trust",
        traitset_id="ts-relations-b114", from_type="relationship", dice=[DieType.D6],
    ))
    # Projection-target edge + trait.
    e2 = repo.create_relationship(A_ID, PROJ_ID, "relation", to_projection=True)
    ts2 = repo.create_traitsetting(TraitSetting(
        id=f"{e2['_key']}:fear", entity_id=e2["_key"], trait_id="trait-relation-fear",
        traitset_id="ts-relations-b114", from_type="relationship", dice=[DieType.D6],
    ))

    try:
        got = {g["setting"].trait_id: g for g in repo.get_relationship_traitsettings_for_entity(A_ID)}
        assert set(got) == {"trait-relation-trust", "trait-relation-fear"}

        # Entity-target contact is the other entity.
        assert got["trait-relation-trust"]["contact_id"] == B_ID
        assert got["trait-relation-trust"]["contact_name"] == "B"
        assert got["trait-relation-trust"]["contact_type"] == "character"
        assert got["trait-relation-trust"]["edge_type"] == "relation"

        # Projection-target contact resolves to its owning entity.
        assert got["trait-relation-fear"]["contact_id"] == B_ID
        assert got["trait-relation-fear"]["contact_name"] == "B"

        # The other entity also sees both (its contact is A).
        got_b = repo.get_relationship_traitsettings_for_entity(B_ID)
        assert {g["setting"].trait_id for g in got_b} == {"trait-relation-trust", "trait-relation-fear"}
        assert all(g["contact_id"] == A_ID for g in got_b)
    finally:
        repo.delete_traitsetting(ts1.id)
        repo.delete_traitsetting(ts2.id)
        repo._relationships.delete(e1["_key"])
        repo._relationships.delete(e2["_key"])


def test_cascade_cleanup_removes_projection_target_edges():
    repo = _repo
    A = "test-cascade-a"
    B = "test-cascade-b"
    PROJ = f"{B}:earth"
    # Self-heal any leftover from an interrupted prior run.
    repo.delete_entity(A)
    repo.delete_entity(B)
    repo.create_entity(Entity(id=A, type=EntityType.CHARACTER, name="A", current_universe="earth"))
    repo.create_entity(Entity(id=B, type=EntityType.CHARACTER, name="B", current_universe="earth"))
    repo.create_projection(Projection(
        id=PROJ, entity_id=B, origin_universe="earth", universe="earth",
        transversal_type=TransversalType.NATIVE,
    ))
    try:
        edge = repo.create_relationship(A, PROJ, "relation", to_projection=True)
        ts = repo.create_traitsetting(TraitSetting(
            id=f"{edge['_key']}:trust", entity_id=edge["_key"], trait_id="trait-relation-trust",
            traitset_id="ts-relations-b114", from_type="relationship", dice=[DieType.D6],
        ))

        # Deleting the *target* must remove the incoming projection edge + its trait.
        repo.delete_entity(B)
        assert repo.get_relationship_by_key(edge["_key"]) is None
        assert repo.get_traitsetting(ts.id) is None
    finally:
        repo.delete_entity(A)
        repo.delete_entity(B)


def test_is_transversal_derivation():
    repo = _repo
    A = "test-transversal-a"   # one native projection → not multiversal
    B = "test-transversal-b"   # two native projections → multiversal
    F = "test-transversal-f"   # faction with two active universes → multiversal
    for eid in (A, B, F):
        repo.delete_entity(eid)
    try:
        repo.create_entity(Entity(id=A, type=EntityType.CHARACTER, name="A", current_universe="earth"))
        repo.create_projection(Projection(
            id=f"{A}:earth", entity_id=A, origin_universe="earth", universe="earth",
            transversal_type=TransversalType.NATIVE,
        ))

        repo.create_entity(Entity(id=B, type=EntityType.CHARACTER, name="B", current_universe="earth"))
        repo.create_projection(Projection(
            id=f"{B}:earth", entity_id=B, origin_universe="earth", universe="earth",
            transversal_type=TransversalType.NATIVE,
        ))
        repo.create_projection(Projection(
            id=f"{B}:emberline", entity_id=B, origin_universe="emberline", universe="emberline",
            transversal_type=TransversalType.NATIVE,
        ))

        repo.create_entity(Entity(
            id=F, type=EntityType.FACTION, name="F", current_universe="earth",
            active_universes=["earth", "emberline"],
        ))

        assert repo.is_transversal(repo.get_entity(A)) is False
        assert repo.is_transversal(repo.get_entity(B)) is True
        assert repo.is_transversal(repo.get_entity(F)) is True
    finally:
        for eid in (A, B, F):
            repo.delete_entity(eid)


def test_p2p_relationship_visible_from_both_sides():
    repo = _repo
    A = "test-p2p-a"
    B = "test-p2p-b"
    APROJ = f"{A}:earth"
    BPROJ = f"{B}:earth"
    for eid in (A, B):
        repo.delete_entity(eid)
    repo.create_entity(Entity(id=A, type=EntityType.CHARACTER, name="A", current_universe="earth"))
    repo.create_entity(Entity(id=B, type=EntityType.CHARACTER, name="B", current_universe="earth"))
    repo.create_projection(Projection(
        id=APROJ, entity_id=A, origin_universe="earth", universe="earth",
        transversal_type=TransversalType.NATIVE,
    ))
    repo.create_projection(Projection(
        id=BPROJ, entity_id=B, origin_universe="earth", universe="earth",
        transversal_type=TransversalType.NATIVE,
    ))
    try:
        edge = repo.create_relationship(APROJ, BPROJ, "relation", from_projection=True, to_projection=True)
        repo.create_traitsetting(TraitSetting(
            id=f"{edge['_key']}:trust", entity_id=edge["_key"], trait_id="trait-relation-trust",
            traitset_id="ts-relations-b114", from_type="relationship", dice=[DieType.D6],
        ))

        # The from-side (A) must see the trait, with B as its contact.
        a_got = repo.get_relationship_traitsettings_for_entity(A)
        a_trust = [g for g in a_got if g["setting"].trait_id == "trait-relation-trust"]
        assert len(a_trust) == 1
        assert a_trust[0]["contact_id"] == B

        # The to-side (B) must see it too, with A as its contact.
        b_got = repo.get_relationship_traitsettings_for_entity(B)
        b_trust = [g for g in b_got if g["setting"].trait_id == "trait-relation-trust"]
        assert len(b_trust) == 1
        assert b_trust[0]["contact_id"] == A
    finally:
        repo.delete_entity(A)
        repo.delete_entity(B)
