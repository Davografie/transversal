"""The nav-dot defaults a location link materialises when it is created.

``_ensure_child_zone`` gives a new child a zone hotspot on its parent; these
tests pin the matching half — the child's own ``parent`` dot position, and the
``portal`` dots a ``transversal`` seeds on both ends.

Why it matters: with no stored position the location viewer has to fall back to a
default, and it both **draws** the dot and **lands** on it. Those two used to
resolve that default differently (the preview guessed the map centre, the travel
guessed the parent dot), so the destination image visibly jumped at the handover.

The numbers below must stay equal to ``NAV_DOT_DEFAULTS`` in
``src/frontend/src/components/LocationViewer.vue`` — if they drift apart, a
location with no stored position is drawn at one spot and landed on at another.

Isolated fixture data, torn down (see ``test_location_scope_db.py`` for the
convention). Skips when ArangoDB is unavailable.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from transversal.api.rest.locations import router as locations_router
from transversal.db.arango import RELATIONSHIPS
from transversal.db.repository import EntityRepository
from transversal.db.repository_mixins.relationships import (
    DEFAULT_PARENT_NAV_POSITION,
    DEFAULT_PORTAL_NAV_POSITION,
)
from transversal.domain import Entity, EntityType

try:
    _repo = EntityRepository()
    HAVE_DB = True
except Exception:
    _repo = None
    HAVE_DB = False

pytestmark = pytest.mark.skipif(not HAVE_DB, reason="ArangoDB not available")

HALL = "test-navpos-hall"            # parent
CELLAR = "test-navpos-cellar"        # its child
PORTAL_A = "test-navpos-portal-a"    # transversal pair, nothing authored
PORTAL_B = "test-navpos-portal-b"
PLACED_A = "test-navpos-placed-a"    # transversal pair, destination authored
PLACED_B = "test-navpos-placed-b"
REST_CHILD = "test-navpos-rest-child"    # linked through the REST endpoint
REST_PARENT = "test-navpos-rest-parent"
LEGACY_A = "test-navpos-legacy-a"        # transversal stored under a non-canonical key
LEGACY_B = "test-navpos-legacy-b"

ALL_IDS = (HALL, CELLAR, PORTAL_A, PORTAL_B, PLACED_A, PLACED_B, REST_CHILD, REST_PARENT,
           LEGACY_A, LEGACY_B)

AUTHORED = {"x": 12, "y": 34}


def _cleanup(repo):
    for lid in ALL_IDS:
        try:
            repo.delete_entity(lid)
        except Exception:
            pass


@pytest.fixture(scope="module")
def nav_data():
    repo = _repo
    _cleanup(repo)  # self-heal an interrupted prior run

    for lid, name in (
        (HALL, "Test Nav Hall"),
        (CELLAR, "Test Nav Cellar"),
        (PORTAL_A, "Test Nav Portal A"),
        (PORTAL_B, "Test Nav Portal B"),
        (PLACED_A, "Test Nav Placed A"),
        (PLACED_B, "Test Nav Placed B"),
    ):
        repo.create_entity(Entity(id=lid, type=EntityType.LOCATION, name=name,
                                  current_universe="test-navpos"))

    # The GM already placed this one's portal dot: seeding must leave it alone.
    placed = repo.get_entity(PLACED_B)
    placed.nav_positions["portal"] = dict(AUTHORED)
    repo.update_entity(placed)

    repo.create_relationship(CELLAR, HALL, "super")              # child -> parent
    repo.create_relationship(PORTAL_A, PORTAL_B, "transversal")  # lateral pair
    repo.create_relationship(PLACED_A, PLACED_B, "transversal")

    yield repo

    for a, b, t in ((CELLAR, HALL, "super"), (HALL, CELLAR, "super"),
                    (PORTAL_A, PORTAL_B, "transversal"), (PORTAL_B, PORTAL_A, "transversal"),
                    (PLACED_A, PLACED_B, "transversal"), (PLACED_B, PLACED_A, "transversal"),
                    (LEGACY_A, LEGACY_B, "transversal"), (LEGACY_B, LEGACY_A, "transversal")):
        try:
            repo.delete_relationship(a, b, t)
        except Exception:
            pass
    _cleanup(repo)


def test_a_new_child_gets_the_parent_dot_position(nav_data):
    """The child stores the dot that leads back up, so arrivals have a target."""
    assert nav_data.get_entity(CELLAR).nav_positions.get("parent") == DEFAULT_PARENT_NAV_POSITION


def test_the_parent_dot_seed_is_the_viewer_default(nav_data):
    """Draw and land must agree — this is the number the hole is framed against."""
    assert DEFAULT_PARENT_NAV_POSITION == {"x": 90, "y": 15}


def test_the_portal_dot_seed_is_the_viewer_default(nav_data):
    assert DEFAULT_PORTAL_NAV_POSITION == {"x": 90, "y": 50}


def test_a_transversal_seeds_a_portal_dot_on_both_ends(nav_data):
    """Both ends carry a dot pointing at the other, so both can be arrived at."""
    assert nav_data.get_entity(PORTAL_A).nav_positions.get("portal") == DEFAULT_PORTAL_NAV_POSITION
    assert nav_data.get_entity(PORTAL_B).nav_positions.get("portal") == DEFAULT_PORTAL_NAV_POSITION


def test_an_authored_position_is_never_overwritten(nav_data):
    """Seeding fills a gap; it does not move a dot the GM placed."""
    assert nav_data.get_entity(PLACED_B).nav_positions.get("portal") == AUTHORED


def test_the_rest_edge_endpoint_seeds_too(nav_data):
    """The UI links locations through this endpoint, not ``create_relationship``.

    ``create_edge`` inserts the edge document directly, so the seeding has to be
    reached from both paths — this is the one the canvas and the GM panels use,
    and the one that would otherwise silently stay unseeded.
    """
    repo = nav_data
    for lid, name in ((REST_CHILD, "Test Nav Rest Child"), (REST_PARENT, "Test Nav Rest Parent")):
        repo.create_entity(Entity(id=lid, type=EntityType.LOCATION, name=name,
                                  current_universe="test-navpos"))

    app = FastAPI()
    app.include_router(locations_router)
    client = TestClient(app)

    r = client.post(f"/api/v1/locations/{REST_CHILD}/edges/{REST_PARENT}", json={"type": "super"})
    assert r.status_code == 200, r.text

    child = repo.get_entity(REST_CHILD)
    assert child.nav_positions.get("parent") == DEFAULT_PARENT_NAV_POSITION


# ── The edge upsert must find an edge by its triple, not by a derived key ──────

def _edges_for(repo, a, b, rel_type="transversal"):
    """Every stored edge for a triple, whatever its ``_key``.

    This is the question the endpoint should be asking. Live data holds **591**
    relationship documents whose key is not the canonical
    ``edge:<from>:<to>:<type>`` form (measured 2026-09-26), so keying a lookup on
    the canonical string answers "no edge here" about an edge that is plainly
    there.
    """
    return list(repo.db.aql.execute(
        f"FOR r IN {RELATIONSHIPS} "
        "FILTER r._from == @f AND r._to == @t AND r.type == @ty "
        "RETURN r",
        bind_vars={"f": f"entities/{a}", "t": f"entities/{b}", "ty": rel_type},
    ))


def _legacy_pair(repo, key="test-navpos-legacy-key"):
    """Two locations joined by a transversal stored under a random key — the
    shape 591 live edges are in, and the precondition of the reported bug.

    Idempotent: the fixture is module-scoped, so each test re-enters this and
    must start from a clean pair rather than a leftover edge from the last one.
    """
    for lid, name in ((LEGACY_A, "Test Nav Legacy A"), (LEGACY_B, "Test Nav Legacy B")):
        if repo.get_entity(lid) is None:
            repo.create_entity(Entity(id=lid, type=EntityType.LOCATION, name=name,
                                      current_universe="test-navpos"))
    for edge in (_edges_for(repo, LEGACY_A, LEGACY_B)
                 + _edges_for(repo, LEGACY_B, LEGACY_A)):
        repo._relationships.delete(edge["_key"])
    repo._relationships.insert({
        "_key": key,
        "_from": f"entities/{LEGACY_A}",
        "_to": f"entities/{LEGACY_B}",
        "type": "transversal",
    })
    return key


def test_toggling_a_legacy_keyed_edge_updates_it_and_does_not_duplicate(nav_data):
    """The reported bug: switching a transversal's mode **created a new gate**.

    ``loc-76217253`` → Yinling Outskirts was switched from inapposite to
    consciousness and grew a second gate beside the original, because the edge
    carried a legacy key (``26763921``) and the endpoint's ``has(canonical_key)``
    test missed it. The mode must land on the edge that is there, and the pair
    must still hold exactly one.
    """
    repo = nav_data
    legacy_key = _legacy_pair(repo)

    app = FastAPI()
    app.include_router(locations_router)
    client = TestClient(app)

    r = client.post(
        f"/api/v1/locations/{LEGACY_A}/edges/{LEGACY_B}",
        json={"type": "transversal", "transversal_type": "consciousness"},
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"status": "updated", "key": legacy_key}

    stored = repo.get_relationship(LEGACY_A, LEGACY_B, "transversal")
    assert stored["_key"] == legacy_key, "the mode must land on the existing edge"
    assert stored.get("transversal_type") == "consciousness"

    # The bug itself: a second gate appeared.
    edges = _edges_for(repo, LEGACY_A, LEGACY_B)
    assert len(edges) == 1, [e["_key"] for e in edges]


def test_a_legacy_edge_is_still_found_when_only_its_reverse_is_canonical(nav_data):
    """A one-way pair: the forward edge is the legacy one, the reverse canonical.

    ``create_edge`` mirrors the mode onto the reverse, so the two directions
    cannot disagree — but it must find the reverse *by triple* to do it, and the
    reverse is not required to share the forward edge's key shape.
    """
    repo = nav_data
    legacy_key = _legacy_pair(repo, key="test-navpos-legacy-key-2")
    repo._relationships.insert({
        "_key": f"edge:{LEGACY_B}:{LEGACY_A}:transversal",
        "_from": f"entities/{LEGACY_B}",
        "_to": f"entities/{LEGACY_A}",
        "type": "transversal",
    })

    app = FastAPI()
    app.include_router(locations_router)
    client = TestClient(app)

    r = client.post(
        f"/api/v1/locations/{LEGACY_A}/edges/{LEGACY_B}",
        json={"type": "transversal", "transversal_type": "consciousness"},
    )
    assert r.status_code == 200, r.text

    reverse = repo.get_relationship(LEGACY_B, LEGACY_A, "transversal")
    assert reverse.get("transversal_type") == "consciousness", "both ends must agree"
    assert len(_edges_for(repo, LEGACY_A, LEGACY_B)) == 1


def test_deleting_a_legacy_keyed_edge_removes_it(nav_data):
    """DELETE had the same defect: a legacy key 404'd on an edge that is there."""
    repo = nav_data
    _legacy_pair(repo, key="test-navpos-legacy-key-3")

    app = FastAPI()
    app.include_router(locations_router)
    client = TestClient(app)

    r = client.delete(f"/api/v1/locations/{LEGACY_A}/edges/{LEGACY_B}?type=transversal")
    assert r.status_code == 200, r.text
    assert repo.get_relationship(LEGACY_A, LEGACY_B, "transversal") is None
    assert _edges_for(repo, LEGACY_A, LEGACY_B) == []
