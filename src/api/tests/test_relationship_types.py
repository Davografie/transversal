"""Relationship edge-type taxonomy — structural set + personal `relation` collapse.

Live-ArangoDB tests for the personal-type collapse (associate/gifted/suspects/
hostile_to → relation) and the structural-edge leak fix. Skip when ArangoDB is
unavailable.
"""

import pytest

from transversal.db.repository import EntityRepository
from transversal.domain import (
    Entity,
    EntityType,
    PERSONAL_RELATIONSHIP_TYPE,
    STRUCTURAL_RELATIONSHIP_TYPES,
    is_structural_relationship_type,
)

try:
    _repo = EntityRepository()
    HAVE_DB = True
except Exception:
    _repo = None
    HAVE_DB = False

pytestmark = pytest.mark.skipif(not HAVE_DB, reason="ArangoDB not available")


A_ID = "test-reltype-a"
B_ID = "test-reltype-b"
C_ID = "test-reltype-c"
_ENTITY_IDS = [A_ID, B_ID, C_ID]


def _cleanup(repo):
    for eid in _ENTITY_IDS:
        repo.delete_entity(eid, rmtree=True)


def _char(eid: str) -> Entity:
    return Entity(id=eid, type=EntityType.GMC, name=eid, current_universe="earth")


def test_structural_relationship_types_set():
    """The structural set is closed and the helper distinguishes personal edges."""
    assert STRUCTURAL_RELATIONSHIP_TYPES == frozenset({
        "super", "membership", "agency", "transversal", "commands", "support",
    })
    assert is_structural_relationship_type("support") is True
    assert is_structural_relationship_type("commands") is True
    assert is_structural_relationship_type("relation") is False
    assert is_structural_relationship_type("associate") is False
    assert PERSONAL_RELATIONSHIP_TYPE == "relation"


def test_collapse_legacy_personal_relationship_types():
    """associate/gifted/suspects fold onto `relation`; idempotent; dedups."""
    repo = _repo
    _cleanup(repo)

    repo.create_entity(_char(A_ID))
    repo.create_entity(_char(B_ID))
    repo.create_entity(_char(C_ID))

    repo.create_relationship(A_ID, B_ID, "associate", description="friends")
    repo.create_relationship(B_ID, A_ID, "gifted", description="Gifted trait X")
    repo.create_relationship(C_ID, A_ID, "suspects", description="Suspects theft")

    # The collapse is a global backfill, so it also folds any pre-existing legacy
    # edges in the shared DB; assert on our fixtures, not an exact global count.
    assert repo.collapse_legacy_personal_relationship_types() >= 3

    # Legacy types are gone.
    assert repo.get_relationship(A_ID, B_ID, "associate") is None
    assert repo.get_relationship(B_ID, A_ID, "gifted") is None
    assert repo.get_relationship(C_ID, A_ID, "suspects") is None

    # Descriptions survive the fold.
    rel_ab = repo.get_relationship(A_ID, B_ID, "relation")
    assert rel_ab is not None and rel_ab["description"] == "friends"
    rel_ba = repo.get_relationship(B_ID, A_ID, "relation")
    assert rel_ba is not None and rel_ba["description"] == "Gifted trait X"
    assert repo.get_relationship(C_ID, A_ID, "relation") is not None

    # Idempotent.
    assert repo.collapse_legacy_personal_relationship_types() == 0

    _cleanup(repo)


def test_collapse_dedups_existing_relation():
    """A legacy edge is dropped (not duplicated) when a `relation` already exists."""
    repo = _repo
    _cleanup(repo)

    repo.create_entity(_char(A_ID))
    repo.create_entity(_char(B_ID))
    repo.create_relationship(A_ID, B_ID, "relation", description="existing")
    repo.create_relationship(A_ID, B_ID, "associate", description="legacy")

    repo.collapse_legacy_personal_relationship_types()

    rel = repo.get_relationship(A_ID, B_ID, "relation")
    assert rel is not None and rel["description"] == "existing"

    rows = list(repo.db.aql.execute(
        "FOR r IN relationships "
        "FILTER r.type == 'relation' AND r._from == @f AND r._to == @t "
        "RETURN r",
        bind_vars={"f": f"entities/{A_ID}", "t": f"entities/{B_ID}"},
    ))
    assert len(rows) == 1

    _cleanup(repo)


def test_canvas_gmc_web_excludes_structural_edges():
    """`commands`/`support` edges no longer leak into the personal-relations list."""
    repo = _repo
    _cleanup(repo)

    repo.create_entity(_char(A_ID))
    repo.create_entity(_char(B_ID))
    repo.create_relationship(A_ID, B_ID, "commands")          # structural — must not leak
    repo.create_relationship(A_ID, B_ID, "relation", description="rival")

    web = repo.canvas_gmc_web(A_ID)
    types = {r["type"] for r in web["relations"]}
    assert types == {"relation"}

    _cleanup(repo)
