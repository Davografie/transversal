"""The faction roster read — what makes an entity a member, and its inverse.

One definition of "roster entry" backs the canvas, the GraphQL roster fields, the
effect-targeting scope and `list_faction_members`:

- a ``membership`` edge, **or** a ``relation`` tie carrying a ``role``/``rank``
  trait (the authored shape, converged onto ``membership`` by
  ``migrate_faction_membership``);
- **member → faction only** — the reverse is the organisation's own view of
  someone (Azure Dawn's "outer sect disciple"), which is a posture, not a slot.

Live-ArangoDB tests. They build isolated fixtures and tear them down, and skip
when ArangoDB is unavailable.
"""

import pytest

from transversal.db.repository import EntityRepository
from transversal.domain import DieType, Entity, EntityType, TraitSetting
from transversal.services.target_scopes import resolve_candidates

try:
    _repo = EntityRepository()
    HAVE_DB = True
except Exception:
    _repo = None
    HAVE_DB = False

pytestmark = pytest.mark.skipif(not HAVE_DB, reason="ArangoDB not available")

FACTION_ID = "test-roster-faction"
FACTION_B_ID = "test-roster-faction-b"
GMC_ID = "test-roster-gmc"
GMC_B_ID = "test-roster-gmc-b"
CHAR_ID = "test-roster-char"
ASSET_ID = "test-roster-asset"
LONER_ID = "test-roster-loner"
RELATIONS_TRAITSET = "ts-relations-b114"
_ALL_IDS = (FACTION_ID, FACTION_B_ID, GMC_ID, GMC_B_ID, CHAR_ID, ASSET_ID, LONER_ID)


def _cleanup(repo):
    for eid in _ALL_IDS:
        repo.delete_entity(eid, rmtree=True)


def _trait_id(repo, name: str) -> str:
    for trait in repo.get_traits_by_traitset(RELATIONS_TRAITSET):
        if trait.name == name:
            return trait.id
    raise AssertionError(f"no '{name}' trait in the relations trait set")


def _seed(repo):
    _cleanup(repo)
    repo.create_entity(Entity(id=FACTION_ID, type=EntityType.FACTION,
                              name="Test Roster Sect", current_universe="earth"))
    repo.create_entity(Entity(id=FACTION_B_ID, type=EntityType.FACTION,
                              name="Test Roster Family", current_universe="earth"))
    for eid, etype in (
        (GMC_ID, EntityType.GMC),
        (GMC_B_ID, EntityType.GMC),
        (CHAR_ID, EntityType.CHARACTER),
        (ASSET_ID, EntityType.ASSET),
        (LONER_ID, EntityType.GMC),
    ):
        repo.create_entity(Entity(id=eid, type=etype, name=eid, current_universe="earth"))


def _tie(repo, frm, to, rel_type, trait_name=None, statement=""):
    """A relationship edge, optionally carrying a roster/posture trait."""
    edge = repo.create_relationship(frm, to, rel_type)
    if trait_name:
        trait_id = _trait_id(repo, trait_name)
        repo.create_traitsetting(TraitSetting(
            id=f"{edge['_key']}:{trait_id}",
            entity_id=edge["_key"],
            trait_id=trait_id,
            from_type="relationship",
            dice=[DieType.D4],
            statement=statement,
        ))
    return edge["_key"]


def test_roster_reads_role_and_rank_from_either_edge_shape():
    repo = _repo
    _seed(repo)
    role_trait = _trait_id(repo, "role")

    _tie(repo, GMC_ID, FACTION_ID, "membership")
    _tie(repo, CHAR_ID, FACTION_ID, "relation", "role", statement="disciple")
    _tie(repo, ASSET_ID, FACTION_ID, "relation", "rank", statement="")
    # Not roster entries: a statement-only posture tie, and a faction→member view.
    _tie(repo, GMC_B_ID, FACTION_ID, "relation", "statement", statement="owes a debt")
    _tie(repo, FACTION_ID, LONER_ID, "relation", "role", statement="outer disciple")
    # An empty statement still marks a roster slot; the role falls back to the trait.
    _tie(repo, GMC_B_ID, FACTION_B_ID, "relation", "role", statement="")

    by_id = {m["id"]: m for m in repo.get_faction_roster(FACTION_ID)}
    assert set(by_id) == {GMC_ID, CHAR_ID, ASSET_ID}
    assert by_id[GMC_ID]["role"] is None
    assert by_id[CHAR_ID]["role"] == "disciple"
    assert by_id[CHAR_ID]["type"] == "character"
    assert by_id[ASSET_ID]["rank"] == "d4"
    assert by_id[ASSET_ID]["type"] == "asset"
    assert [m["role"] for m in repo.get_faction_roster(FACTION_B_ID)] == [role_trait]

    # The canvas renders people and places, so it drops assets — the roster keeps them.
    assert {m["id"] for m in repo.canvas_faction(FACTION_ID)["members"]} == {GMC_ID, CHAR_ID}
    # `list_faction_members` is the same read, filtered to people.
    assert {e.id for e in repo.list_faction_members(FACTION_ID)} == {GMC_ID, CHAR_ID}

    _cleanup(repo)


def test_entity_factions_is_the_inverse_and_respects_direction():
    repo = _repo
    _seed(repo)

    _tie(repo, GMC_ID, FACTION_ID, "membership")
    _tie(repo, CHAR_ID, FACTION_ID, "relation", "role", statement="disciple")
    _tie(repo, GMC_B_ID, FACTION_ID, "relation", "statement", statement="a grudge")
    _tie(repo, FACTION_ID, LONER_ID, "relation", "role", statement="outer disciple")

    assert repo.get_entity_factions(GMC_ID) == [FACTION_ID]
    assert repo.get_entity_factions(CHAR_ID) == [FACTION_ID]
    assert repo.get_entity_factions(GMC_B_ID) == []   # posture only
    assert repo.get_entity_factions(LONER_ID) == []   # the org's view of them
    assert repo.get_entity_factions(FACTION_ID) == []

    _cleanup(repo)


def test_actor_faction_scope_resolves_the_actors_own_org():
    repo = _repo
    _seed(repo)
    # A member of two orgs, so narrowing has something to narrow.
    _tie(repo, GMC_ID, FACTION_ID, "membership")
    _tie(repo, GMC_ID, FACTION_B_ID, "relation", "role", statement="advisor")

    member = repo.get_entity(GMC_ID)
    resolved = resolve_candidates("entity", "actor_faction:", member, repo)
    assert sorted(c.id for c in resolved) == sorted([FACTION_ID, FACTION_B_ID])
    assert {c.name for c in resolved} == {"Test Roster Sect", "Test Roster Family"}

    # A value narrows to one org by id. (The old flat form also accepted a
    # case-insensitive fragment of the name; a path filters on a field, so the
    # fragment spelling is gone — the value in a scope is an id.)
    assert [c.id for c in resolve_candidates("entity", f"actor_faction:{FACTION_ID}", member, repo)] == [FACTION_ID]
    assert resolve_candidates("entity", "actor_faction:FAMILY", member, repo) == []

    # An entity with no roster has no actor faction — not an error.
    assert resolve_candidates("entity", "actor_faction:", repo.get_entity(GMC_B_ID), repo) == []

    _cleanup(repo)
