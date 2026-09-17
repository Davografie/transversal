"""The inverse agency read — one entity, several holders, one defined answer.

``get_agency_for_entity`` answers "who holds agency over this entity" and feeds
``Entity.agency`` on the GM panel. **One entity can have several holders** —
measured live 2026-09-16: 42 agency edges over 33 entities, four entities held
more than once, and one character held by **seven** player records (one human's
per-device identities). The read used to ``LIMIT 1`` with no ordering, so which
holder came back was plan order: stable in practice, unspecified in principle,
and the panel's "Agency: <name>" could name any of the seven.

It is now ordered — a ``main`` claim first, then player id ascending — which is
what these tests pin: not just *an* answer, but the *same* answer, and the one
the ``main`` flag makes meaningful.

Live-ArangoDB tests. They build isolated fixtures and tear them down, and skip
when ArangoDB is unavailable.
"""

import pytest

from transversal.api.graphql.resolvers.converters import _entity_to_gql
from transversal.db.repository import EntityRepository
from transversal.domain import Entity, EntityType
from transversal.services.entity_manager import EntityManager

try:
    _repo = EntityRepository()
    HAVE_DB = True
except Exception:
    _repo = None
    HAVE_DB = False

pytestmark = pytest.mark.skipif(not HAVE_DB, reason="ArangoDB not available")

ENTITY_ID = "test-agency-entity"
P_A = "test-agency-player-a"
P_B = "test-agency-player-b"
P_C = "test-agency-player-c"
_NAMES = {P_A: "Anna", P_B: "Bram", P_C: "Cleo"}
_PLAYERS = (P_A, P_B, P_C)


def _cleanup(repo):
    for pid in _PLAYERS:
        repo.delete_player(pid)
    repo.delete_entity(ENTITY_ID, rmtree=True)


def _entity() -> Entity:
    return Entity(
        id=ENTITY_ID, type=EntityType.GMC, name="Held", current_universe="earth",
    )


def _seed(repo):
    """One entity, three players, all three holding agency — none flagged main.

    ``main=False`` on every claim is deliberate: B117 auto-designates a player's
    first claim as their main, which would otherwise make the "no main" case
    impossible to construct.
    """
    _cleanup(repo)
    repo.create_entity(_entity())
    for pid, name in _NAMES.items():
        repo.create_player(pid, name, role="player")
    for pid in _PLAYERS:
        repo.claim_entity(pid, ENTITY_ID, main=False)


def _info(repo):
    return type("Info", (), {"context": {"entity_manager": EntityManager(repo)}})()


def test_an_unheld_entity_reads_none():
    repo = _repo
    _cleanup(repo)
    repo.create_entity(_entity())

    assert repo.get_agency_for_entity(ENTITY_ID) is None

    _cleanup(repo)


def test_a_single_main_holder_is_the_answer():
    """The main wins even when it is neither first-inserted nor lowest-keyed."""
    repo = _repo
    _seed(repo)

    assert repo.set_agency_main(P_B, ENTITY_ID, True) is True

    agency = repo.get_agency_for_entity(ENTITY_ID)
    assert agency == {"player_id": P_B, "main": True}

    _cleanup(repo)


def test_several_mains_resolve_deterministically_by_player_id():
    repo = _repo
    _seed(repo)

    assert repo.set_agency_main(P_A, ENTITY_ID, True) is True
    assert repo.set_agency_main(P_C, ENTITY_ID, True) is True

    assert repo.get_agency_for_entity(ENTITY_ID) == {"player_id": P_A, "main": True}

    _cleanup(repo)


def test_no_main_holder_still_resolves_by_player_id():
    repo = _repo
    _seed(repo)

    assert repo.get_agency_for_entity(ENTITY_ID) == {"player_id": P_A, "main": False}

    _cleanup(repo)


def test_the_resolver_names_the_holder():
    """``Entity.agency`` reads through the ordered lookup and names the player."""
    repo = _repo
    _seed(repo)
    repo.set_agency_main(P_B, ENTITY_ID, True)

    ref = _entity_to_gql(_entity()).agency(_info(repo))

    assert ref is not None
    assert ref.player_id == P_B
    assert ref.player_name == "Bram"
    assert ref.main is True

    _cleanup(repo)


def test_the_resolver_is_null_for_an_unheld_entity():
    repo = _repo
    _cleanup(repo)
    repo.create_entity(_entity())

    assert _entity_to_gql(_entity()).agency(_info(repo)) is None

    _cleanup(repo)
