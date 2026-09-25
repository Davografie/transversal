"""Membership writes — endpoint validation and a non-destructive upsert.

The roster edge is `membership` (member → faction). Two integrity rules are
asserted here:

1. a malformed membership is **refused** rather than written (self-edge, a `_to`
   that is not a faction, a `_from` that cannot hold membership);
2. re-writing an existing edge **keeps the edge and its trait settings** — the
   GraphQL mutation used to delete-then-create, and because relationship trait
   settings anchor to the edge key, that silently wiped a member's rank and role.

Live-ArangoDB tests. They build isolated fixtures and tear them down, and skip
when ArangoDB is unavailable.
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

FACTION_ID = "test-mem-faction"
FACTION_B_ID = "test-mem-faction-b"
GMC_ID = "test-mem-gmc"
CHAR_ID = "test-mem-char"
ASSET_ID = "test-mem-asset"
RELATIONS_TRAITSET = "ts-relations-b114"


def _role_trait_id(repo) -> str:
    """The registry's own `role` trait — resolved, so the fixture cannot drift."""
    for trait in repo.get_traits_by_traitset(RELATIONS_TRAITSET):
        if trait.name == "role":
            return trait.id
    raise AssertionError("no 'role' trait in the relations trait set")


_ALL_IDS = (FACTION_ID, FACTION_B_ID, GMC_ID, CHAR_ID, ASSET_ID)


def _cleanup(repo):
    for eid in _ALL_IDS:
        repo.delete_entity(eid, rmtree=True)


def _entity(eid: str, etype: EntityType) -> Entity:
    return Entity(id=eid, type=etype, name=eid, current_universe="earth")


def _seed(repo):
    _cleanup(repo)
    repo.create_entity(_entity(FACTION_ID, EntityType.FACTION))
    repo.create_entity(_entity(FACTION_B_ID, EntityType.FACTION))
    repo.create_entity(_entity(GMC_ID, EntityType.GMC))
    repo.create_entity(_entity(CHAR_ID, EntityType.CHARACTER))
    repo.create_entity(_entity(ASSET_ID, EntityType.ASSET))


def test_membership_endpoints_are_validated():
    repo = _repo
    _seed(repo)

    # A member may be a person-like entity or an owned thing.
    assert repo.validate_relationship(GMC_ID, FACTION_ID, "membership") is None
    assert repo.validate_relationship(CHAR_ID, FACTION_ID, "membership") is None
    assert repo.validate_relationship(ASSET_ID, FACTION_ID, "membership") is None

    # Refusals, each naming the reason.
    assert "itself" in repo.validate_relationship(FACTION_ID, FACTION_ID, "membership")
    assert "not a faction" in repo.validate_relationship(GMC_ID, CHAR_ID, "membership")
    member_refusal = repo.validate_relationship(FACTION_ID, FACTION_B_ID, "membership")
    assert member_refusal is not None and "membership is held by" in member_refusal
    assert "not found" in repo.validate_relationship("no-such-entity", FACTION_ID, "membership")
    assert "not found" in repo.validate_relationship(GMC_ID, "no-such-entity", "membership")

    # Every other type is unconstrained — nested orgs are a `relation`.
    assert repo.validate_relationship(FACTION_ID, FACTION_B_ID, "relation") is None

    _cleanup(repo)


def test_upsert_keeps_the_edge_and_its_role_trait():
    """The regression: a second write must not orphan rank/role."""
    repo = _repo
    _seed(repo)

    edge = repo.upsert_relationship(GMC_ID, FACTION_ID, "membership", description="sworn in")
    edge_key = edge["_key"]

    role_trait = _role_trait_id(repo)
    repo.create_traitsetting(TraitSetting(
        id=f"{edge_key}:{role_trait}",
        entity_id=edge_key,
        trait_id=role_trait,
        from_type="relationship",
        dice=[DieType.D4],
        statement="sect disciple",
    ))

    again = repo.upsert_relationship(GMC_ID, FACTION_ID, "membership", description="renewed")

    assert again["_key"] == edge_key, "the edge was replaced instead of updated"
    assert again["description"] == "renewed"
    traits = repo.get_relationship_traitsettings(edge_key)
    assert [t.trait_id for t in traits] == [role_trait]
    assert traits[0].statement == "sect disciple"

    _cleanup(repo)


def test_upsert_creates_once_and_is_idempotent():
    repo = _repo
    _seed(repo)

    first = repo.upsert_relationship(GMC_ID, FACTION_ID, "membership")
    second = repo.upsert_relationship(GMC_ID, FACTION_ID, "membership")
    assert first["_key"] == second["_key"]

    # One edge, not two: a duplicate roster entry would double-count the member.
    count = list(repo.db.aql.execute(
        "FOR r IN relationships FILTER r._from == @f AND r._to == @t AND r.type == 'membership' "
        "COLLECT WITH COUNT INTO n RETURN n",
        bind_vars={"f": f"entities/{GMC_ID}", "t": f"entities/{FACTION_ID}"},
    ))
    assert count == [1]

    _cleanup(repo)


def test_roster_promotion_promotes_members_only_and_keeps_the_role():
    """The convergence rule: member→faction with a role promotes; the reverse does not."""
    from transversal import migrate_faction_membership as mig

    repo = _repo
    _seed(repo)

    def _tie(frm, to, trait_name, statement):
        trait_id = next(
            t.id for t in repo.get_traits_by_traitset(RELATIONS_TRAITSET) if t.name == trait_name
        )
        edge = repo.create_relationship(frm, to, "relation")
        repo.create_traitsetting(TraitSetting(
            id=f"{edge['_key']}:{trait_id}",
            entity_id=edge["_key"],
            trait_id=trait_id,
            from_type="relationship",
            dice=[DieType.D4],
            statement=statement,
        ))
        return edge["_key"]

    member_side = _tie(GMC_ID, FACTION_ID, "role", "sect disciple")
    faction_side = _tie(FACTION_ID, CHAR_ID, "role", "outer sect disciple")
    # A posture tie carries no roster trait, so it is not a roster entry — and an
    # empty-statement `role` tie still is one, because the trait is the marker.
    _tie(GMC_ID, FACTION_B_ID, "statement", "they will not touch my family")
    empty_role_tie = _tie(CHAR_ID, FACTION_B_ID, "role", "")

    candidates = mig.find_candidates(repo)
    assert sorted(c["edge"] for c in candidates) == sorted([member_side, empty_role_tie]), candidates

    assert mig.promote(repo, candidates) == 2
    assert repo.get_relationship_by_key(member_side)["type"] == "membership"
    assert repo.get_relationship_by_key(empty_role_tie)["type"] == "membership"
    assert repo.get_relationship_by_key(faction_side)["type"] == "relation"
    traits = repo.get_relationship_traitsettings(member_side)
    assert [t.statement for t in traits] == ["sect disciple"]

    # Idempotent: nothing left to promote.
    assert mig.find_candidates(repo) == []

    _cleanup(repo)
