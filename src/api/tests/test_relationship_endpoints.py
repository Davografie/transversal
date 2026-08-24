"""DB-backed tests for relationship endpoints (entity vs projection targets).

These exercise the real ``EntityRepository`` ArangoDB code paths for
entity→entity and entity→projection relationship edges, plus the edge-key
lookup used to resolve ego/morph for relationship trait settings.
"""

import pytest

from transversal.db.repository import EntityRepository
from transversal.domain import Entity, EntityType, Projection, TransversalType

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
