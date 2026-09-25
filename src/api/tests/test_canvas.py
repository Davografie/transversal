"""Integration tests for the relational canvas repository methods.

The canvas is an assembly layer: it takes the **roster read**
(`get_faction_roster`) plus the location tree and shapes them into members,
the pruned ancestor scaffolding, and the edges between them. What is pinned
here is that assembly — assets dropped, ancestors disjoint from member
locations, edges only among the pruned set — not the roster rule itself, which
is `test_faction_roster.py`'s business.

These tests **build their own fixture and tear it down**. They used to hit the
live tree seeded by ``transversal.migrate_conspyramid`` and name specific ids
(``fac-crimson-hollow``, ``gmc-hollow-patriarch``); authoring sessions then
changed that content and four of them went red for a reason that had nothing to
do with the canvas — the patrol gmc had been deleted and the faction had no ties
left, so it correctly returned an empty canvas. Pinning live content is the rot,
so the fixture is local now.

Live-ArangoDB tests. They skip when ArangoDB is unavailable.
"""

import pytest

from transversal.db.repository import EntityRepository
from transversal.domain import DieType, Entity, EntityType, TraitSetting

try:
    _repo = EntityRepository()
    HAVE_DB = True
except Exception:
    _repo = None
    HAVE_DB = False

pytestmark = pytest.mark.skipif(not HAVE_DB, reason="ArangoDB not available")

U = "test-canvas-u"

FACTION_ID = "test-canvas-faction"
# Test Valley > Test Ridge > { Test Cave, Test Bluff, Test Ford }
ROOT, MID, CAVE, BLUFF, FORD = (
    "test-canvas-loc-root", "test-canvas-loc-mid", "test-canvas-loc-cave",
    "test-canvas-loc-bluff", "test-canvas-loc-ford",
)
_LOCATIONS = (ROOT, MID, CAVE, BLUFF, FORD)

# Six members, two standing at each leaf location.
M1, M2, M3, M4, M5, M6 = (
    "test-canvas-m1", "test-canvas-m2", "test-canvas-m3",
    "test-canvas-m4", "test-canvas-m5", "test-canvas-m6",
)
_MEMBERS = (M1, M2, M3, M4, M5, M6)

PATRIARCH = "test-canvas-patriarch"
PEER1, PEER2 = "test-canvas-peer1", "test-canvas-peer2"
_PEOPLE = (PATRIARCH, PEER1, PEER2)

_ALL_IDS = _MEMBERS + _PEOPLE + _LOCATIONS + (FACTION_ID,)
_LEAVES = (CAVE, BLUFF, FORD)

RELATIONS_TRAITSET = "ts-relations-b114"


def _trait_id(repo, name: str) -> str:
    """The registry's own trait by name — resolved, never hard-coded."""
    for trait in repo.get_traits_by_traitset(RELATIONS_TRAITSET):
        if trait.name == name:
            return trait.id
    raise AssertionError(f"no '{name}' trait in the relations trait set")


def _rank(rank: str) -> DieType:
    return {"d4": DieType.D4, "d6": DieType.D6, "d8": DieType.D8,
            "d10": DieType.D10, "d12": DieType.D12}[rank]


def _tie(repo, frm: str, to: str, rel_type: str, *, role=None, rank=None,
         description: str = ""):
    """A relationship edge, optionally carrying the roster's role/rank traits."""
    edge = repo.create_relationship(frm, to, rel_type, description=description)
    if role is not None:
        trait_id = _trait_id(repo, "role")
        repo.create_traitsetting(TraitSetting(
            id=f"{edge['_key']}:{trait_id}",
            entity_id=edge["_key"],
            trait_id=trait_id,
            traitset_id=RELATIONS_TRAITSET,
            from_type="relationship",
            dice=[DieType.D4],
            statement=role,
        ))
    if rank is not None:
        trait_id = _trait_id(repo, "rank")
        repo.create_traitsetting(TraitSetting(
            id=f"{edge['_key']}:{trait_id}",
            entity_id=edge["_key"],
            trait_id=trait_id,
            traitset_id=RELATIONS_TRAITSET,
            from_type="relationship",
            dice=[_rank(rank)],
            statement="",
        ))
    return edge["_key"]


def _cleanup(repo):
    # People first; deleting a location rmtree-walks its own subtree.
    for eid in _ALL_IDS:
        repo.delete_entity(eid, rmtree=True)


def _seed(repo):
    _cleanup(repo)

    repo.create_entity(Entity(id=FACTION_ID, type=EntityType.FACTION,
                              name="Test Hollow Sect", current_universe=U))
    for loc, name in ((ROOT, "Test Valley"), (MID, "Test Ridge"),
                      (CAVE, "Test Cave"), (BLUFF, "Test Bluff"),
                      (FORD, "Test Ford")):
        repo.create_entity(Entity(id=loc, type=EntityType.LOCATION,
                                  name=name, current_universe=U))
    # super edges point child → parent.
    for child, parent in ((MID, ROOT), (CAVE, MID), (BLUFF, MID), (FORD, MID)):
        repo.create_relationship(child, parent, "super")

    for i, (member, loc) in enumerate(zip(_MEMBERS, (CAVE, CAVE, BLUFF, BLUFF, FORD, FORD))):
        repo.create_entity(Entity(
            id=member, type=EntityType.CHARACTER if i % 2 == 0 else EntityType.GMC,
            name=f"Member {i + 1}", current_universe=U, current_location=loc,
        ))
        _tie(repo, member, FACTION_ID, "membership",
             role=f"rank {i + 1}", rank=("d4", "d6", "d8", "d10", "d12", "d6")[i])

    # A labelled chain between two members, which the canvas annotates.
    _tie(repo, M1, M2, "relation", description="commands")

    # The GMC web: the patriarch plus two peers, each standing somewhere.
    repo.create_entity(Entity(id=PATRIARCH, type=EntityType.GMC,
                              name="The Hollow Patriarch", current_universe=U,
                              current_location=CAVE))
    repo.create_entity(Entity(id=PEER1, type=EntityType.GMC, name="Peer One",
                              current_universe=U, current_location=BLUFF))
    repo.create_entity(Entity(id=PEER2, type=EntityType.CHARACTER, name="Peer Two",
                              current_universe=U, current_location=FORD))
    _tie(repo, PATRIARCH, PEER1, "relation", description="advises")
    _tie(repo, PEER2, PATRIARCH, "relation", description="owes")


# ── Neighborhood ─────────────────────────────────────

def test_neighborhood_shape():
    repo = _repo
    _seed(repo)
    try:
        nb = repo.canvas_neighborhood(MID)
        assert nb["location"] is not None
        assert isinstance(nb["children"], list)
        assert isinstance(nb["transversal"], list)
        assert isinstance(nb["occupants"], list)
        # Canvas additions
        assert isinstance(nb["faction_memberships"], dict)
        assert isinstance(nb["occupant_relations"], list)
    finally:
        _cleanup(repo)


# ── Faction canvas ───────────────────────────────────

def test_faction_members_have_rank_role():
    repo = _repo
    _seed(repo)
    try:
        fc = repo.canvas_faction(FACTION_ID)
        assert fc["faction"] is not None
        assert fc["faction"]["name"] == "Test Hollow Sect"
        assert len(fc["members"]) == 6
        for m in fc["members"]:
            assert m["rank"] in ("d4", "d6", "d8", "d10", "d12")
            assert m["role"]
            assert m["location_id"]
        # Command chain relations carry a description (edge label).
        assert any(r["description"] == "commands" for r in fc["relations"])
    finally:
        _cleanup(repo)


def test_faction_ancestors_are_disjoint_scaffolding():
    repo = _repo
    _seed(repo)
    try:
        fc = repo.canvas_faction(FACTION_ID)
        member_locs = {l["id"] for l in fc["locations"]}
        ancestor_locs = {l["id"] for l in fc["ancestors"]}
        assert member_locs == set(_LEAVES)
        assert not (member_locs & ancestor_locs)
        # The pruned tree keeps the middle rung and the root as scaffolding.
        assert {l["name"] for l in fc["ancestors"]} == {"Test Ridge", "Test Valley"}
    finally:
        _cleanup(repo)


def test_faction_location_edges_connect_members_to_ancestors():
    repo = _repo
    _seed(repo)
    try:
        fc = repo.canvas_faction(FACTION_ID)
        edges = fc["location_edges"]
        assert edges
        member_ids = {l["id"] for l in fc["locations"]}
        child_ids = {e["child"] for e in edges}
        parent_ids = {e["parent"] for e in edges}
        # Member locations are leaves: every member is a child, none is a parent.
        for mid in member_ids:
            assert mid in child_ids
            assert mid not in parent_ids
        # Every ancestor location participates in the tree (as parent or child).
        ancestor_ids = {l["id"] for l in fc["ancestors"]}
        assert ancestor_ids <= (child_ids | parent_ids)
    finally:
        _cleanup(repo)


def test_the_roster_read_is_the_only_member_definition():
    """The canvas drops assets; `list_faction_members` is the same read, filtered."""
    repo = _repo
    _seed(repo)
    try:
        fc = repo.canvas_faction(FACTION_ID)
        assert {m["id"] for m in fc["members"]} == set(_MEMBERS)
        assert {e.id for e in repo.list_faction_members(FACTION_ID)} == set(_MEMBERS)
    finally:
        _cleanup(repo)


# ── GMC web ──────────────────────────────────────────

def test_gmc_web_resolves_other_locations():
    repo = _repo
    _seed(repo)
    try:
        gw = repo.canvas_gmc_web(PATRIARCH)
        assert gw["gmc"]["name"] == "The Hollow Patriarch"
        assert gw["location"]["name"] == "Test Cave"
        assert len(gw["relations"]) == 2
        for r in gw["relations"]:
            assert r["other_name"]
            assert r["other_location_id"]
            assert r["other_location_name"]
    finally:
        _cleanup(repo)


def test_unknown_ids_return_none():
    repo = _repo
    try:
        assert repo.canvas_faction("nonexistent")["faction"] is None
        assert repo.canvas_gmc_web("nonexistent")["gmc"] is None
        assert repo.canvas_neighborhood("nonexistent")["location"] is None
    finally:
        _cleanup(repo)
