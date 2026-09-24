"""The location-edge cycle guard — a `super` edge cannot close a loop ([[B122]]).

A `super` edge is the location tree's parent link, stored child → parent. Drop a
location on itself, or anywhere inside its own subtree, and the new parent link
makes the pair each other's ancestor: nothing in the loop has a parent-free root
any more, so the whole branch stops being reachable from the tree and silently
disappears from it. That is how **Yinling Creek was lost** (found detached
2026-09-11, repaired by hand). The GM tree has refused the drop client-side since
``56a0ab5``; the endpoint that actually writes the edge did not.

What is pinned here:

* the endpoint refuses a self-edge and a subtree edge with a 400 and **writes
  nothing** — not the edge, and not the nav-dot defaults a created link gets;
* `validate_relationship` is the rule, and it is the *rule* under test, not the
  endpoint's willingness to call it;
* legitimate re-parenting still works, including re-posting an edge that already
  exists (the client does this) and a move that merely looks similar — a child
  moved to its own grandparent;
* `transversal` is untouched: a portal is a lateral link, not a parent, so the
  cycle rule is not applied to it.

Live-ArangoDB tests. The endpoint tests drive the real route over a real
repository, so the refusal is exercised where the write would have happened.
They build isolated fixtures and tear them down, and skip when ArangoDB is
unavailable.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import transversal.api.rest.locations as locations_module
from transversal.api.rest.locations import router as locations_router
from transversal.db.repository import EntityRepository
from transversal.domain import Entity, EntityType

try:
    _repo = EntityRepository()
    HAVE_DB = True
except Exception:
    _repo = None
    HAVE_DB = False

pytestmark = pytest.mark.skipif(not HAVE_DB, reason="ArangoDB not available")

U = "test-edgeguard-u"

# A three-level chain: L1 > L2 > L3. L4 is outside it, an unrelated root.
L1, L2, L3, L4 = (
    "test-edgeguard-l1", "test-edgeguard-l2",
    "test-edgeguard-l3", "test-edgeguard-l4",
)
_ALL = (L1, L2, L3, L4)


def _cleanup(repo):
    for eid in _ALL:
        repo.delete_entity(eid, rmtree=True)


def _seed(repo):
    """L1 > L2 > L3 (L2's parent is L1, L3's parent is L2). L4 is a lone root."""
    _cleanup(repo)
    for loc in _ALL:
        repo.create_entity(Entity(
            id=loc, type=EntityType.LOCATION, name=loc, current_universe=U,
        ))
    for child, parent in ((L2, L1), (L3, L2)):
        repo.create_relationship(child, parent, "super")


def _post(repo, frm, to, edge_type="super", monkeypatch=None):
    """POST the edge route against a real repository; return the response."""
    monkeypatch.setattr(locations_module, "_repo", lambda: repo)
    app = FastAPI()
    app.include_router(locations_router)
    return TestClient(app).post(
        f"/api/v1/locations/{frm}/edges/{to}", json={"type": edge_type}
    )


def _has_edge(repo, frm, to, edge_type="super") -> bool:
    return repo._relationships.has(f"edge:{frm}:{to}:{edge_type}")


# ── The rule ─────────────────────────────────────────

def test_a_location_cannot_be_its_own_parent():
    repo = _repo
    _seed(repo)
    try:
        assert repo.validate_relationship(L1, L1, "super")
    finally:
        _cleanup(repo)


def test_a_location_cannot_be_re_parented_under_its_own_child():
    repo = _repo
    _seed(repo)
    try:
        assert repo.validate_relationship(L1, L2, "super")  # L1 under L2
    finally:
        _cleanup(repo)


def test_a_location_cannot_be_re_parented_under_its_own_grandchild():
    """The subtree case proper: the loop is two links away, not one."""
    repo = _repo
    _seed(repo)
    try:
        assert repo.validate_relationship(L1, L3, "super")  # L1 under L3
    finally:
        _cleanup(repo)


def test_the_refusal_names_the_two_locations():
    """The message is what a GraphQL caller reports, so it has to be readable."""
    repo = _repo
    _seed(repo)
    try:
        refusal = repo.validate_relationship(L1, L3, "super")
        assert L1 in refusal and L3 in refusal
    finally:
        _cleanup(repo)


# ── What must still be allowed ───────────────────────

def test_re_parenting_to_an_unrelated_location_is_allowed():
    repo = _repo
    _seed(repo)
    try:
        assert repo.validate_relationship(L2, L4, "super") is None
    finally:
        _cleanup(repo)


def test_moving_a_child_up_to_its_own_grandparent_is_allowed():
    """L3 under L1 shortens the chain; it does not close it."""
    repo = _repo
    _seed(repo)
    try:
        assert repo.validate_relationship(L3, L1, "super") is None
    finally:
        _cleanup(repo)


def test_re_posting_the_edge_that_already_exists_is_allowed():
    """The client re-POSTs on every drop; an existing parent link is not a loop."""
    repo = _repo
    _seed(repo)
    try:
        assert repo.validate_relationship(L2, L1, "super") is None
    finally:
        _cleanup(repo)


def test_a_transversal_edge_is_not_held_to_the_tree_rule():
    """A portal is lateral; the parent-edge rule is not its business."""
    repo = _repo
    _seed(repo)
    try:
        assert repo.validate_relationship(L1, L1, "transversal") is None
        assert repo.validate_relationship(L1, L3, "transversal") is None
    finally:
        _cleanup(repo)


# ── The endpoint ─────────────────────────────────────

def test_the_endpoint_refuses_a_self_edge_and_writes_nothing(monkeypatch):
    repo = _repo
    _seed(repo)
    try:
        r = _post(repo, L1, L1, monkeypatch=monkeypatch)
        assert r.status_code == 400, r.text
        assert not _has_edge(repo, L1, L1)
        # A created link also seeds nav-dot defaults; a refusal must not.
        assert not repo.get_entity(L1).nav_positions.get("parent")
    finally:
        _cleanup(repo)


def test_the_endpoint_refuses_a_subtree_edge_and_writes_nothing(monkeypatch):
    repo = _repo
    _seed(repo)
    try:
        r = _post(repo, L1, L3, monkeypatch=monkeypatch)
        assert r.status_code == 400, r.text
        assert not _has_edge(repo, L1, L3)
        assert not repo.get_entity(L1).nav_positions.get("parent")
    finally:
        _cleanup(repo)


def test_the_endpoint_still_accepts_a_legitimate_re_parent(monkeypatch):
    repo = _repo
    _seed(repo)
    try:
        r = _post(repo, L2, L4, monkeypatch=monkeypatch)
        assert r.status_code == 200, r.text
        assert _has_edge(repo, L2, L4)
    finally:
        _cleanup(repo)


def test_the_endpoint_still_accepts_a_portal(monkeypatch):
    repo = _repo
    _seed(repo)
    try:
        r = _post(repo, L1, L4, edge_type="transversal", monkeypatch=monkeypatch)
        assert r.status_code == 200, r.text
        assert _has_edge(repo, L1, L4, "transversal")
    finally:
        _cleanup(repo)


def test_the_endpoint_still_rejects_an_unknown_edge_type(monkeypatch):
    """The guard went in ahead of the type check's behaviour, not instead of it."""
    repo = _repo
    _seed(repo)
    try:
        r = _post(repo, L1, L4, edge_type="morph", monkeypatch=monkeypatch)
        assert r.status_code == 400, r.text
    finally:
        _cleanup(repo)
