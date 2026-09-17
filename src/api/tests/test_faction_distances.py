"""Faction distance — the weighted, undirected location-graph read (B134).

The read ranks factions by how far their controlled ground is from a location,
which is what a distance-sorted faction list needs ([[Tickets#B107]]/[[Tickets#B134]]).

The rules pinned here, all the author's calls (2026-09-16):

* **Undirected** — `super` is stored child → parent only, so following stored
  direction would reach a small fraction of the graph.
* **`super` and `transversal` both count**, costing 1 — except a portal that
  **crosses a universe boundary**, which costs `CROSS_UNIVERSE_WEIGHT`.
* **The control tie's die is ignored** (a d10 "sect seat" is *how much*, not *how
  far*), and **direction matters** — only `faction → location` is a claim.
* A faction that controls nothing, or whose ground is unreachable, gets a null
  distance and sorts last.

The fixture is a chain built to make each rule separable: two same-universe hops,
one cross-universe portal, then one more same-universe hop.

Live-ArangoDB tests. They build isolated fixtures and tear them down, and skip
when ArangoDB is unavailable.
"""

import pytest

from transversal.db.repository import EntityRepository
from transversal.db.repository_mixins.canvas import CROSS_UNIVERSE_WEIGHT
from transversal.domain import DieType, Entity, EntityType, TraitSetting

try:
    _repo = EntityRepository()
    HAVE_DB = True
except Exception:
    _repo = None
    HAVE_DB = False

pytestmark = pytest.mark.skipif(not HAVE_DB, reason="ArangoDB not available")

RELATIONS_TRAITSET = "ts-relations-b114"

F1, F2, F3, F4, F5 = (
    "test-fdist-f1", "test-fdist-f2", "test-fdist-f3",
    "test-fdist-f4", "test-fdist-f5",
)
L1, L2, L3, L4, L5, L6 = (
    "test-fdist-l1", "test-fdist-l2", "test-fdist-l3",
    "test-fdist-l4", "test-fdist-l5", "test-fdist-l6",
)
_FACTIONS = (F1, F2, F3, F4, F5)
_LOCATIONS = (L1, L2, L3, L4, L5, L6)
_ALL = _FACTIONS + _LOCATIONS

U1, U2 = "test-fdist-u1", "test-fdist-u2"


def _cleanup(repo):
    for eid in _ALL:
        repo.delete_entity(eid, rmtree=True)


def _control_trait_id(repo) -> str:
    """The registry's own `control` trait — resolved, so the fixture cannot drift."""
    for trait in repo.get_traits_by_traitset(RELATIONS_TRAITSET):
        if trait.name == "control":
            return trait.id
    raise AssertionError("no 'control' trait in the relations trait set")


def _control(repo, faction_id: str, location_id: str, trait_id: str, die=DieType.D10):
    """A claim on ground: a `faction → location` tie carrying a `control` setting."""
    edge = repo.create_relationship(faction_id, location_id, "relation")
    repo.create_traitsetting(TraitSetting(
        id=f"{edge['_key']}:{trait_id}",
        entity_id=edge["_key"],
        trait_id=trait_id,
        traitset_id=RELATIONS_TRAITSET,
        from_type="relationship",
        dice=[die],
        statement="seat",
    ))


def _seed(repo):
    """
    L2 --super--> L1        (both u1, cost 1)
    L2 --transversal--> L3  (u1 -> u2: the boundary crossing)
    L4 --super--> L3        (both u2, cost 1)
    L1 --transversal--> L6  (both u1: a portal inside a universe, cost 1)
    L5                      (isolated: its controller is unreachable)

    Deliberately no `super` edge crosses a universe: a hierarchy link is not a
    portal, so this fixture keeps the two cost rules separable.
    """
    _cleanup(repo)
    for loc, universe in ((L1, U1), (L2, U1), (L3, U2), (L4, U2), (L5, U1), (L6, U1)):
        repo.create_entity(Entity(
            id=loc, type=EntityType.LOCATION, name=loc, current_universe=universe,
        ))
    for faction in _FACTIONS:
        repo.create_entity(Entity(
            id=faction, type=EntityType.FACTION, name=faction, current_universe=U1,
        ))

    repo.create_relationship(L2, L1, "super")
    repo.create_relationship(L2, L3, "transversal")
    repo.create_relationship(L4, L3, "super")
    repo.create_relationship(L1, L6, "transversal")

    trait_id = _control_trait_id(repo)
    _control(repo, F1, L1, trait_id)   # from L1: 0
    _control(repo, F4, L4, trait_id)   # from L1: 1 + W + 1
    _control(repo, F3, L5, trait_id)   # isolated: unreachable from L1
    # F2 controls nothing at all.
    # F5's claim runs the *wrong way* — a location's posture toward a faction.
    edge = repo.create_relationship(L2, F5, "relation")
    repo.create_traitsetting(TraitSetting(
        id=f"{edge['_key']}:{trait_id}", entity_id=edge["_key"], trait_id=trait_id,
        traitset_id=RELATIONS_TRAITSET, from_type="relationship",
        dice=[DieType.D10], statement="not a claim",
    ))


def _dists(repo, location_id):
    """Distances keyed by faction id, restricted to the fixture's factions."""
    return {
        r["faction_id"]: r
        for r in repo.get_faction_distances_for_location(location_id)
        if r["faction_id"] in _FACTIONS
    }


def test_a_faction_controlling_the_place_scores_zero():
    repo = _repo
    _seed(repo)

    assert _dists(repo, L1)[F1]["distance"] == 0
    assert _dists(repo, L1)[F1]["nearest_location_id"] == L1

    _cleanup(repo)


def test_a_same_universe_step_costs_one():
    """L1 and L2 are a `super` edge apart, in one universe."""
    repo = _repo
    _seed(repo)

    assert _dists(repo, L1)[F4]["distance"] == 2 + CROSS_UNIVERSE_WEIGHT  # L1->L2->L3->L4
    assert _dists(repo, L2)[F1]["distance"] == 1

    _cleanup(repo)


def test_a_cross_universe_portal_costs_the_penalty():
    """The whole point of the weighting: reaching L4 is two same-universe hops
    plus one boundary crossing, not three hops."""
    repo = _repo
    _seed(repo)

    d = _dists(repo, L1)
    assert d[F4]["distance"] == CROSS_UNIVERSE_WEIGHT + 2
    assert d[F4]["distance"] > 3, "the boundary must cost more than a plain step"

    _cleanup(repo)


def test_traversal_is_undirected():
    """L4 -> L3 and L3 -> L2 are stored child -> parent; L6's portal is stored
    L6 -> L1. Walking only stored direction would make F1 unreachable from L6."""
    repo = _repo
    _seed(repo)

    assert _dists(repo, L6)[F1]["distance"] == 1
    assert _dists(repo, L4)[F1]["distance"] == CROSS_UNIVERSE_WEIGHT + 2

    _cleanup(repo)


def test_unreachable_and_uncontrolling_factions_are_null():
    repo = _repo
    _seed(repo)

    d = _dists(repo, L1)
    assert d[F3]["distance"] is None, "the controller of an isolated place is unreachable"
    assert d[F3]["nearest_location_id"] is None
    assert d[F2]["distance"] is None, "a faction that controls nothing has no distance"

    _cleanup(repo)


def test_a_reverse_direction_tie_is_not_a_claim():
    """F5's `control` setting sits on a `location → faction` tie, which is the
    location's posture — not a claim on ground, so it must not score."""
    repo = _repo
    _seed(repo)

    assert _dists(repo, L2)[F5]["distance"] is None
    assert _dists(repo, L1)[F5]["distance"] is None

    _cleanup(repo)


def test_the_list_is_sorted_near_first_and_covers_every_faction():
    repo = _repo
    _seed(repo)

    rows = repo.get_faction_distances_for_location(L1)
    ids = [r["faction_id"] for r in rows]
    assert len(ids) == len(set(ids))
    assert F1 in ids and F2 in ids, "every faction is returned, not only controlling ones"

    # reachable first, ascending; then the nulls
    finite = [r["distance"] for r in rows if r["distance"] is not None]
    assert finite == sorted(finite)
    seen_null = False
    for r in rows:
        if r["distance"] is None:
            seen_null = True
        else:
            assert not seen_null, "a reachable faction sorted after an unreachable one"

    _cleanup(repo)


def test_the_graphql_resolver_exposes_the_read():
    from transversal.api.graphql.resolvers.queries_entities import QueriesEntities
    from transversal.services.entity_manager import EntityManager

    repo = _repo
    _seed(repo)
    info = type("Info", (), {"context": {"entity_manager": EntityManager(repo)}})()

    refs = QueriesEntities().faction_distances(info, L1)
    f1 = next(r for r in refs if r.faction_id == F1)

    assert f1.distance == 0
    assert f1.nearest_location_id == L1
    assert f1.name == F1

    _cleanup(repo)
