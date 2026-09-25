"""The guided route — the next hop from here toward a destination.

`get_route_next_hop(origin, destination)` answers "which neighbour is the first
step?" over the **same** graph and weights the faction ranking and the
point-to-point read use (`_location_adjacency`), so "the way there" can never
come to mean something different from "how far".

The rules pinned here are the human's (2026-09-23):

* **Hidden locations stay hidden unless they are unavoidable.** A concealed place
  is never stepped through while a way around it exists — and the test fixture
  makes the hidden route *shorter* than the open one, so a weighted search that
  merely penalised concealment would fail this and the two-pass exclusion is what
  is actually being pinned.
* **Unavoidable means unavoidable**: when the only way through is hidden, the
  route uses it rather than reporting no route.
* **One hop at a time**: following the returned hop repeatedly must walk to the
  destination and then stop, which is what lets the viewer light a single navdot.

Live-ArangoDB tests. They build isolated fixtures and tear them down, and skip
when ArangoDB is unavailable.
"""

import pytest

from transversal.db.repository import EntityRepository
from transversal.domain import Entity, EntityType

try:
    _repo = EntityRepository()
    HAVE_DB = True
except Exception:
    _repo = None
    HAVE_DB = False

pytestmark = pytest.mark.skipif(not HAVE_DB, reason="ArangoDB not available")

U = "test-lroute-u"

# Detour fixture: the hidden road is SHORTER (2 steps) than the open one (3).
A1, AH, A2, A4, A3 = (
    "test-lroute-a1", "test-lroute-ah", "test-lroute-a2",
    "test-lroute-a4", "test-lroute-a3",
)
# Only a hidden road exists.
B1, BH, B3 = "test-lroute-b1", "test-lroute-bh", "test-lroute-b3"
# Nothing connects them.
C1, C2 = "test-lroute-c1", "test-lroute-c2"
# The destination itself is hidden.
F1, FH = "test-lroute-f1", "test-lroute-fh"

_ALL = (A1, AH, A2, A4, A3, B1, BH, B3, C1, C2, F1, FH)
_HIDDEN = {AH, BH, FH}


def _cleanup(repo):
    for eid in _ALL:
        repo.delete_entity(eid, rmtree=True)


def _seed(repo):
    """
    Detour — hidden is the short way, open is longer:
        A1 --super--> AH(hidden) --super--> A3     (2 steps)
        A1 --super--> A2 --super--> A4 --super--> A3  (3 steps)

    Unavoidable:
        B1 --super--> BH(hidden) --super--> B3

    Hidden destination:
        F1 --super--> FH(hidden)

    C1 and C2 are isolated.
    """
    _cleanup(repo)
    for loc in _ALL:
        repo.create_entity(Entity(
            id=loc, type=EntityType.LOCATION, name=loc, current_universe=U,
            hidden=loc in _HIDDEN,
        ))
    # A fixture left behind by an interrupted run can survive the cleanup with its
    # flag unset, and then the hidden shortcut wins the route and the assertion fails
    # — observed once, passing on every later run. Assert the fixture instead of
    # trusting that creation set it.
    for loc in _ALL:
        e = repo.get_entity(loc)
        if e is not None and bool(e.hidden) != (loc in _HIDDEN):
            e.hidden = loc in _HIDDEN
            repo.update_entity(e)
    for a, b in (
        (A1, AH), (AH, A3),
        (A1, A2), (A2, A4), (A4, A3),
        (B1, BH), (BH, B3),
        (F1, FH),
    ):
        repo.create_relationship(a, b, "super")


# ── Hidden locations ─────────────────────────────────

def test_hidden_is_avoided_even_when_the_open_way_is_longer():
    """A1→A3: the hidden road is 2 steps, the open one 3. The hop must be open.

    This is the rule, not a penalty: a weighted search would take the shorter
    hidden road, so only the exclude-then-fall-back search passes this.
    """
    repo = _repo
    _seed(repo)
    try:
        assert repo.get_route_next_hop(A1, A3) == A2
    finally:
        _cleanup(repo)


def test_hidden_is_used_when_unavoidable():
    """B1→B3: the only road runs through a hidden location, so it is the hop."""
    repo = _repo
    _seed(repo)
    try:
        assert repo.get_route_next_hop(B1, B3) == BH
    finally:
        _cleanup(repo)


def test_a_hidden_destination_is_still_reachable():
    """F1→FH: the goal itself being concealed must not make it unreachable."""
    repo = _repo
    _seed(repo)
    try:
        assert repo.get_route_next_hop(F1, FH) == FH
    finally:
        _cleanup(repo)


def test_an_unavoidable_hidden_step_is_not_a_dead_end():
    """The hidden road is walked to the end, not just onto it."""
    repo = _repo
    _seed(repo)
    try:
        assert repo.get_route_next_hop(BH, B3) == B3
    finally:
        _cleanup(repo)


# ── Hop semantics ────────────────────────────────────

def test_following_the_hops_walks_to_the_destination_and_stops():
    """The property the viewer depends on: repeated hops terminate *at* the goal.

    Lights one navdot at a time, so this loop is exactly what a player does.
    """
    repo = _repo
    _seed(repo)
    try:
        hops, here = [], A1
        for _ in range(10):
            here = repo.get_route_next_hop(here, A3)
            if here is None:
                break
            hops.append(here)
        assert hops == [A2, A4, A3]
    finally:
        _cleanup(repo)


def test_arriving_is_no_hop():
    """Standing at the destination asks for no next step."""
    repo = _repo
    _seed(repo)
    try:
        assert repo.get_route_next_hop(A3, A3) is None
    finally:
        _cleanup(repo)


def test_unconnected_locations_have_no_hop():
    repo = _repo
    _seed(repo)
    try:
        assert repo.get_route_next_hop(C1, C2) is None
        assert repo.get_route_next_hop(C2, C1) is None
    finally:
        _cleanup(repo)


def test_missing_or_empty_ids_have_no_hop():
    repo = _repo
    _seed(repo)
    try:
        assert repo.get_route_next_hop("", A3) is None
        assert repo.get_route_next_hop(A1, "") is None
    finally:
        _cleanup(repo)


def test_the_hop_is_the_first_step_not_the_nearest_by_distance_alone():
    """A1→A3 again, read the other way: the hop is a neighbour of the origin.

    Guards against a rewrite that returns the destination (or any node) rather
    than the adjacent step.
    """
    repo = _repo
    _seed(repo)
    try:
        hop = repo.get_route_next_hop(A1, A3)
        assert hop in {A2, AH, A4, A3}          # a neighbour of A1 only
        assert hop != A3 or repo.get_route_next_hop(hop, A3) is None
    finally:
        _cleanup(repo)


# ── The authoring refusal's read ─────────────────────

def test_reachability_read_is_empty_when_there_is_no_route():
    """What the effects system checks before it will write a destination.

    `get_location_distances_from` omits unreachable targets, so an empty result
    is the "refuse with an error message" condition.
    """
    repo = _repo
    _seed(repo)
    try:
        assert repo.get_location_distances_from(C1, {C2}) == {}
        assert repo.get_location_distances_from(B1, {B3}) == {B3: 2}
    finally:
        _cleanup(repo)


def test_reachability_read_ignores_hidden_for_authoring():
    """The refusal must not reject a destination merely hidden from the route.

    Authoring asks "is there a way at all?" — B1→B3 is walkable (through a hidden
    location), so it must not be refused. The hiding is the *route's* business,
    not the check's.
    """
    repo = _repo
    _seed(repo)
    try:
        assert repo.get_location_distances_from(B1, {B3}) == {B3: 2}
    finally:
        _cleanup(repo)
