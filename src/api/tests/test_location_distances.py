"""Location distances — the point-to-point sibling of the faction ranking.

`get_location_distances_from(origin, targets)` answers "how far is each of these
places" over the **same** graph and weights `factionDistances` ranks by, because
both read `_location_adjacency` — one definition of the metric, so the faction
list and a place-to-place query can never drift apart. The rules pinned here are
therefore the metric's, not a second interpretation of it:

* **Undirected** — `super` is stored child → parent only.
* **`super` and `transversal` both count**, each step costing 1 — except a portal
  that **crosses a universe boundary**, which costs `CROSS_UNIVERSE_WEIGHT`.
* **Unreachable targets are absent**, not scored: the graph is fragmentary, and a
  caller ranking candidates must not read a sentinel as a number.
* The origin itself scores `0` when it is one of the targets.

The fixture is a chain built so each rule is separable: one cross-universe portal,
then two same-universe hops (one `super`, one portal inside a universe), plus an
isolated location.

Live-ArangoDB tests. They build isolated fixtures and tear them down, and skip
when ArangoDB is unavailable.
"""

import pytest

from transversal.db.repository import EntityRepository
from transversal.db.repository_mixins.canvas import CROSS_UNIVERSE_WEIGHT
from transversal.domain import Entity, EntityType

try:
    _repo = EntityRepository()
    HAVE_DB = True
except Exception:
    _repo = None
    HAVE_DB = False

pytestmark = pytest.mark.skipif(not HAVE_DB, reason="ArangoDB not available")

L1, L2, L3, L4, L5 = (
    "test-ldist-l1", "test-ldist-l2", "test-ldist-l3",
    "test-ldist-l4", "test-ldist-l5",
)
_ALL = (L1, L2, L3, L4, L5)

U1, U2 = "test-ldist-u1", "test-ldist-u2"


def _cleanup(repo):
    for eid in _ALL:
        repo.delete_entity(eid, rmtree=True)


def _seed(repo):
    """
    L1 --transversal--> L2   (u1 -> u2: the boundary crossing)
    L2 --super--> L3         (both u2, cost 1)
    L3 --transversal--> L4   (both u2: a portal inside a universe, cost 1)
    L5                       (isolated)

    Deliberately no `super` edge crosses a universe, so the two cost rules stay
    separable — a hierarchy link always costs one step.
    """
    _cleanup(repo)
    for loc, universe in ((L1, U1), (L2, U2), (L3, U2), (L4, U2), (L5, U1)):
        repo.create_entity(Entity(
            id=loc, type=EntityType.LOCATION, name=loc, current_universe=universe,
        ))
    repo.create_relationship(L1, L2, "transversal")
    repo.create_relationship(L2, L3, "super")
    repo.create_relationship(L3, L4, "transversal")


# ── Reads ────────────────────────────────────────────

def test_distances_carry_the_cross_universe_weight_once():
    """From L1: the portal to u2 costs W, then two same-universe steps cost 1 each."""
    repo = _repo
    _seed(repo)
    try:
        found = repo.get_location_distances_from(L1, {L1, L2, L3, L4, L5})
        assert found[L1] == 0
        assert found[L2] == CROSS_UNIVERSE_WEIGHT
        assert found[L3] == CROSS_UNIVERSE_WEIGHT + 1
        assert found[L4] == CROSS_UNIVERSE_WEIGHT + 2
        # L5 is isolated: absent, not scored.
        assert L5 not in found
    finally:
        _cleanup(repo)


def test_distances_walk_undirected_from_either_end():
    """The same chain read backwards: `super` is stored child → parent, and a
    directed walk would not climb it."""
    repo = _repo
    _seed(repo)
    try:
        found = repo.get_location_distances_from(L4, {L1, L2, L3, L4})
        assert found[L4] == 0
        assert found[L3] == 1                      # up the stored-direction `super`
        assert found[L2] == 2
        assert found[L1] == 2 + CROSS_UNIVERSE_WEIGHT
    finally:
        _cleanup(repo)


def test_unreachable_and_empty_targets():
    repo = _repo
    _seed(repo)
    try:
        # An isolated origin reaches nothing — including itself? No: the origin is
        # settled first, so it scores 0 and any other target is absent.
        assert repo.get_location_distances_from(L5, {L1, L5}) == {L5: 0}
        # No targets at all is an empty read, not a graph walk.
        assert repo.get_location_distances_from(L1, set()) == {}
        assert repo.get_location_distances_from(L1, {""}) == {}
    finally:
        _cleanup(repo)
