"""B54 — troupe data model: player domain model, agency ``main`` flag,
``support`` edge, and the GMC ``base difficulty`` trait set.

Live-ArangoDB integration tests. They build isolated fixture data and tear it
down, and skip when ArangoDB is unavailable.
"""

import pytest

from transversal.db.repository import EntityRepository
from transversal.domain import DieType, Entity, EntityType, Player, RatingType

try:
    _repo = EntityRepository()
    HAVE_DB = True
except Exception:
    _repo = None
    HAVE_DB = False

pytestmark = pytest.mark.skipif(not HAVE_DB, reason="ArangoDB not available")


P_ID = "test-b54-player"
MAIN_ID = "test-b54-main"
SC_ID = "test-b54-sc"
_ENTITY_IDS = [MAIN_ID, SC_ID]


def _cleanup(repo):
    repo.delete_player(P_ID)
    for eid in _ENTITY_IDS:
        repo.delete_entity(eid, rmtree=True)


def _char(eid: str) -> Entity:
    return Entity(
        id=eid, type=EntityType.GMC, name=eid, current_universe="earth",
    )


def test_player_domain_round_trip_and_agency_main():
    """A player flags an owned entity as main; the flag round-trips."""
    repo = _repo
    _cleanup(repo)

    repo.create_entity(_char(MAIN_ID))
    repo.create_entity(_char(SC_ID))
    repo.create_player(P_ID, "test-player", role="player")

    assert repo.claim_entity(P_ID, MAIN_ID) is True
    assert repo.claim_entity(P_ID, SC_ID) is True

    # No main flag yet.
    agency = repo.get_agency_edges(P_ID)
    assert {a["entity_id"] for a in agency} == {MAIN_ID, SC_ID}
    assert all(a["main"] is False for a in agency)

    # Flag the main.
    assert repo.set_agency_main(P_ID, MAIN_ID, True) is True
    agency = {a["entity_id"]: a["main"] for a in repo.get_agency_edges(P_ID)}
    assert agency[MAIN_ID] is True
    assert agency[SC_ID] is False

    # Un-flagging an entity with no agency edge is refused.
    assert repo.set_agency_main(P_ID, "no-such-entity", True) is False

    # The domain Player carries the spotlight fields and resolved entity_ids.
    p = repo.get_player(P_ID)
    assert isinstance(p, Player)
    assert sorted(p.entity_ids) == sorted([MAIN_ID, SC_ID])
    assert p.last_spotlight_at is None
    assert p.last_main_entity_id is None

    # Spotlight stamp persists.
    assert repo.update_player(P_ID, {
        "last_spotlight_at": "2026-09-03T00:00:00+00:00",
        "last_main_entity_id": MAIN_ID,
    })
    p = repo.get_player(P_ID)
    assert p.last_spotlight_at == "2026-09-03T00:00:00+00:00"
    assert p.last_main_entity_id == MAIN_ID

    _cleanup(repo)


def test_support_edge_round_trip():
    """An SC links to its main via a directional `support` edge."""
    repo = _repo
    _cleanup(repo)

    repo.create_entity(_char(MAIN_ID))
    repo.create_entity(_char(SC_ID))
    repo.create_relationship(SC_ID, MAIN_ID, "support")

    edge = repo.get_relationship(SC_ID, MAIN_ID, "support")
    assert edge is not None
    assert edge["_from"] == f"entities/{SC_ID}"
    assert edge["_to"] == f"entities/{MAIN_ID}"

    # support is a structural edge, not a personal one — no projection routing.
    assert repo.get_relationship(SC_ID, MAIN_ID, "support")["type"] == "support"

    _cleanup(repo)


def test_gmc_base_difficulty_seed():
    """`ensure_gmc_base_difficulty` seeds the GMC-only trait set + trait."""
    from transversal.services.sfx_owner import ensure_gmc_base_difficulty

    repo = _repo
    ensure_gmc_base_difficulty(repo)

    ts = repo.get_traitset_by_id("ts-gmc-base")
    assert ts is not None
    assert EntityType.GMC in ts.entity_types

    trait = repo.get_trait("trait-base-difficulty")
    assert trait is not None
    assert trait.traitset_id == "ts-gmc-base"
    assert trait.default_rating_type == RatingType.STATIC
    assert trait.default_die_type == DieType.D6

    # Idempotent — a second run must not raise.
    ensure_gmc_base_difficulty(repo)
