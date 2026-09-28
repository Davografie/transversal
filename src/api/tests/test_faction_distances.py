"""Faction distance — the weighted, undirected location-graph read (B134).

The read ranks factions by how far their nearest **presence** is from a location,
which is what a distance-sorted faction list needs ([[Tickets#B107]]/[[Tickets#B134]]).

The rules pinned here, all the author's calls (2026-09-16, presence widened
2026-09-26):

* **Undirected** — `super` is stored child → parent only, so following stored
  direction would reach a small fraction of the graph.
* **`super` and `transversal` both count**, costing 1 — except a portal that
  **crosses a universe boundary**, which costs `CROSS_UNIVERSE_WEIGHT`.
* **A tie's die is ignored** (a d10 "sect seat" is *how much*, not *how far*), and
  **direction matters** — only `faction → location` is presence.
* **Presence is two things**: an authored `faction → location` tie
  (`holds_ground`) — *any* tie, not only one carrying a `control` setting — or a
  member of the faction standing there (`has_people`). Assets are not ears, and at
  equal distance authored ground sorts first.
* A faction present nowhere reachable gets a null distance and sorts last.

The fixture is a chain built to make each rule separable: two same-universe hops,
one cross-universe portal, then one more same-universe hop.

Live-ArangoDB tests. They build isolated fixtures and tear them down, and skip
when ArangoDB is unavailable.
"""

import pytest

from transversal.db.repository import EntityRepository
from transversal.db.repository_mixins.canvas import (
    CROSS_UNIVERSE_WEIGHT,
    PRESENCE_GROUND,
    PRESENCE_PEOPLE,
)
from transversal.domain import DieType, Entity, EntityType, Projection, TraitSetting

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

# Presence members are created **per test**, never in the shared seed: F2 has to
# keep meaning "present nowhere" for the null-distance assertions.
GMC1, GMC2, ASSET1 = "test-fdist-gmc1", "test-fdist-gmc2", "test-fdist-asset1"

_ALL = _FACTIONS + _LOCATIONS + (GMC1, GMC2, ASSET1)

U1, U2 = "test-fdist-u1", "test-fdist-u2"
BODY1 = f"{GMC1}:{U1}"                # a parked body of GMC1 (B137 body-present rule)


def _cleanup(repo):
    try:
        repo.delete_projection(BODY1)
    except Exception:
        pass
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
         from_type="relationship",
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


# ── Presence, widened (author, 2026-09-26) ────────────────────────────────────
#
# The read used to answer "how far is this faction's *controlled* ground". The
# author widened it to *presence*: any authored faction → location tie, or a
# member of the faction standing at the place. The measured case for it: only 1
# of 81 live factions held any `control` ground, against 21 covered by presence,
# and the derived half costs nothing to maintain (94 memberships, every member
# carries a location).


def _member(repo, member_id, faction_id, *, kind=EntityType.GMC, at=None):
    """A member of `faction_id`, optionally standing somewhere."""
    repo.create_entity(Entity(
        id=member_id, type=kind, name=member_id,
        current_universe=U1, current_location=at,
    ))
    repo.create_relationship(member_id, faction_id, "membership")


def _tie(repo, faction_id, location_id, *, trait=None):
    """An authored ``faction → location`` tie; no trait setting unless asked."""
    edge = repo.create_relationship(faction_id, location_id, "relation")
    if trait:
        repo.create_traitsetting(TraitSetting(
            id=f"{edge['_key']}:{trait}", entity_id=edge["_key"], trait_id=trait,
            from_type="relationship", dice=[DieType.D6], statement="tie",
        ))
    return edge


def test_any_authored_tie_is_presence_not_only_a_control_one():
    """A plain faction → location tie states that the faction is here.

    This is the widening: the tie used to be invisible unless it carried a
    ``control`` setting, which hid 7 of the 12 live ties."""
    repo = _repo
    _seed(repo)
    _tie(repo, F2, L2)                       # deliberately carries no trait at all

    d = _dists(repo, L1)[F2]
    assert d["distance"] == 1
    assert d["presence"] == PRESENCE_GROUND
    assert d["nearest_location_id"] == L2
    assert d["nearest_location_name"] == L2   # the fixture names locations by id

    _cleanup(repo)


def test_a_member_standing_somewhere_makes_their_faction_present():
    """The informant case, which is the point: nobody authored a tie, but the
    faction has ears in L2, so it becomes visible to the GM."""
    repo = _repo
    _seed(repo)
    _member(repo, GMC1, F2, at=L2)

    d = _dists(repo, L1)[F2]
    assert d["distance"] == 1
    assert d["presence"] == PRESENCE_PEOPLE
    assert d["nearest_location_id"] == L2

    _cleanup(repo)


def test_a_member_at_this_very_location_scores_zero():
    repo = _repo
    _seed(repo)
    _member(repo, GMC1, F2, at=L1)

    assert _dists(repo, L1)[F2]["distance"] == 0

    _cleanup(repo)


def test_an_asset_member_is_not_ears():
    """A parked asset is owned by the faction, not present for it."""
    repo = _repo
    _seed(repo)
    _member(repo, ASSET1, F2, kind=EntityType.ASSET, at=L2)

    assert _dists(repo, L1)[F2]["distance"] is None

    _cleanup(repo)


def test_authored_ground_outranks_people_at_the_same_place():
    repo = _repo
    _seed(repo)
    _tie(repo, F2, L2)
    _member(repo, GMC1, F2, at=L2)

    assert _dists(repo, L1)[F2]["presence"] == PRESENCE_GROUND

    _cleanup(repo)


def test_a_member_is_present_where_their_body_stands():
    """Body-present, the occupant read's own rule ([[B137]] S1).

    GMC1's entity location is L5 — an isolated place — but its body stands at L2,
    and the body is what is on the map. An entity-location reading would answer
    null here."""
    repo = _repo
    _seed(repo)
    repo.create_entity(Entity(
        id=GMC1, type=EntityType.GMC, name=GMC1,
        current_universe=U1, current_location=L5,
    ))
    repo.create_relationship(GMC1, F2, "membership")
    repo.create_projection(Projection(
        id=BODY1, entity_id=GMC1, origin_universe=U1, universe=U1,
        current_location=L2,
    ))

    d = _dists(repo, L1)[F2]
    assert d["nearest_location_id"] == L2, "the body's place, not the entity's"
    assert d["presence"] == PRESENCE_PEOPLE
    assert d["distance"] is not None, "L5 is isolated; only the body makes this reachable"

    _cleanup(repo)


def test_the_nearest_presence_is_the_one_reported():
    repo = _repo
    _seed(repo)
    _member(repo, GMC1, F2, at=L2)   # one hop from L1
    _member(repo, GMC2, F2, at=L4)   # behind the universe boundary

    d = _dists(repo, L1)[F2]
    assert d["distance"] == 1
    assert d["nearest_location_id"] == L2

    _cleanup(repo)


def test_ground_sorts_before_people_at_equal_distance():
    """One ranking, with the tie broken toward the stronger statement."""
    repo = _repo
    _seed(repo)
    _tie(repo, F2, L2)                 # ground, one hop from L1
    _member(repo, GMC1, F3, at=L6)     # people, one hop the other way

    rows = [
        r for r in repo.get_faction_distances_for_location(L1)
        if r["faction_id"] in (F2, F3)
    ]
    assert [r["distance"] for r in rows] == [1, 1]
    assert [r["presence"] for r in rows] == [PRESENCE_GROUND, PRESENCE_PEOPLE]

    _cleanup(repo)


def test_the_graphql_resolver_exposes_presence_and_the_place():
    from transversal.api.graphql.resolvers.queries_entities import QueriesEntities
    from transversal.services.entity_manager import EntityManager

    repo = _repo
    _seed(repo)
    _member(repo, GMC1, F2, at=L2)
    info = type("Info", (), {"context": {"entity_manager": EntityManager(repo)}})()

    refs = QueriesEntities().faction_distances(info, L1)
    f2 = next(r for r in refs if r.faction_id == F2)

    assert f2.presence == PRESENCE_PEOPLE
    assert f2.nearest_location_name == L2
    assert f2.distance == 1

    _cleanup(repo)
