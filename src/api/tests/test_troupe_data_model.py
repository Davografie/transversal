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
    repo.delete_player("test-b54-player-new")
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


def test_agency_main_query_and_spotlight_recency_order():
    """`get_agency_main` reads the flag; `list_players_by_spotlight` sorts oldest-first."""
    repo = _repo
    _cleanup(repo)

    repo.create_entity(_char(MAIN_ID))
    repo.create_entity(_char(SC_ID))
    repo.create_player(P_ID, "p-old", role="player")
    repo.create_player("test-b54-player-new", "p-new", role="player")
    repo.claim_entity(P_ID, MAIN_ID)
    repo.set_agency_main(P_ID, MAIN_ID, True)

    assert repo.get_agency_main(P_ID, MAIN_ID) is True
    assert repo.get_agency_main(P_ID, SC_ID) is False

    # Old player has a spotlight stamp; the new player never has → nulls first.
    repo.update_player(P_ID, {
        "last_spotlight_at": "2026-09-01T00:00:00+00:00",
        "last_main_entity_id": MAIN_ID,
    })
    ordered = repo.list_players_by_spotlight()
    ids = [p.id for p in ordered if p.id in (P_ID, "test-b54-player-new")]
    assert ids == ["test-b54-player-new", P_ID]

    _cleanup(repo)


def test_record_control_stamps_only_for_mains():
    """Taking control of a main stamps the player; a non-main does not."""
    from transversal.services.player_manager import PlayerManager

    repo = _repo
    _cleanup(repo)

    repo.create_entity(_char(MAIN_ID))
    repo.create_entity(_char(SC_ID))
    repo.create_player(P_ID, "test-player", role="player")
    repo.claim_entity(P_ID, MAIN_ID)
    repo.claim_entity(P_ID, SC_ID)
    repo.set_agency_main(P_ID, MAIN_ID, True)

    mgr = PlayerManager(repo=repo)

    # Non-main → no stamp.
    assert mgr.record_control(P_ID, SC_ID) is False
    p = repo.get_player(P_ID)
    assert p.last_spotlight_at is None
    assert p.last_main_entity_id is None

    # Main → stamped, actor-keyed on the explicit player id.
    assert mgr.record_control(P_ID, MAIN_ID) is True
    p = repo.get_player(P_ID)
    assert p.last_spotlight_at is not None
    assert p.last_main_entity_id == MAIN_ID

    _cleanup(repo)


def test_active_main_registry_and_support_edges():
    """`record_control` tracks the active main; `list_support_edges` lists support edges."""
    from transversal.services.player_manager import (
        PlayerManager,
        _active_main,
        is_main_active,
    )

    repo = _repo
    _cleanup(repo)
    _active_main.clear()  # isolate from prior tests' module-level registry

    repo.create_entity(_char(MAIN_ID))
    repo.create_entity(_char(SC_ID))
    repo.create_player(P_ID, "test-player", role="player")
    repo.claim_entity(P_ID, MAIN_ID)
    repo.claim_entity(P_ID, SC_ID)
    repo.set_agency_main(P_ID, MAIN_ID, True)
    repo.create_relationship(SC_ID, MAIN_ID, "support")

    mgr = PlayerManager(repo=repo)

    # Nothing is active before a control event.
    assert is_main_active(P_ID, MAIN_ID) is False

    # Taking the main marks it active.
    mgr.record_control(P_ID, MAIN_ID)
    assert is_main_active(P_ID, MAIN_ID) is True

    # Switching to a non-main (support) deactivates the main.
    mgr.record_control(P_ID, SC_ID)
    assert is_main_active(P_ID, MAIN_ID) is False

    # The support edge is listed for the availability query.
    edges = repo.list_support_edges()
    assert any(
        e["_from"] == f"entities/{SC_ID}" and e["_to"] == f"entities/{MAIN_ID}"
        for e in edges
    )

    _cleanup(repo)
