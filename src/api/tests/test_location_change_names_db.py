"""The ``location_changed`` payload names both ends of a move.

The GM's move toast reads ``name`` (who moved) and ``to_name`` (where to)
straight off this event. Without them a client can only print ids: the entity
has just *left* the location whose peers it would look up, and the destination
may be somewhere that client has never been.

``move_to`` already resolves the destination to read its universe, so ``to_name``
costs nothing there; ``name`` is free everywhere. ``_publish_to_sessions`` is
patched because it fans out over active sessions, and a test has none.

Isolated fixture data, torn down (see ``test_location_scope_db.py``). Skips when
ArangoDB is unavailable.
"""

import pytest

from transversal.db.repository import EntityRepository
from transversal.domain import Entity, EntityType
from transversal.services import entity_manager as em_module
from transversal.services.entity_manager import EntityManager

try:
    _repo = EntityRepository()
    HAVE_DB = True
except Exception:
    _repo = None
    HAVE_DB = False

pytestmark = pytest.mark.skipif(not HAVE_DB, reason="ArangoDB not available")

HALL = "test-movenames-hall"
CELLAR = "test-movenames-cellar"
WANDERER = "test-movenames-wanderer"


def _cleanup(repo):
    for eid in (WANDERER, CELLAR, HALL):
        try:
            repo.delete_entity(eid)
        except Exception:
            pass


@pytest.fixture
def moved(monkeypatch):
    """Move a character from the hall to the cellar; return what was published."""
    repo = _repo
    _cleanup(repo)  # self-heal an interrupted prior run

    repo.create_entity(Entity(id=HALL, type=EntityType.LOCATION, name="Test Move Hall",
                              current_universe="test-movenames"))
    repo.create_entity(Entity(id=CELLAR, type=EntityType.LOCATION, name="Test Move Cellar",
                              current_universe="test-movenames"))
    repo.create_entity(Entity(id=WANDERER, type=EntityType.CHARACTER, name="Test Wanderer",
                              current_universe="test-movenames", current_location=HALL))

    events = []
    monkeypatch.setattr(em_module, "_publish_to_sessions", lambda evt: events.append(evt))

    EntityManager(repository=repo).move_to(repo.get_entity(WANDERER), CELLAR)

    yield events
    _cleanup(repo)


def _payload(events):
    found = [e for e in events if e.event == "location_changed"]
    assert found, "a move must publish location_changed"
    return found[-1].data


def test_the_event_names_the_entity_that_moved(moved):
    assert _payload(moved)["name"] == "Test Wanderer"


def test_the_event_names_the_destination_place(moved):
    assert _payload(moved)["to_name"] == "Test Move Cellar"


def test_the_ids_are_still_there(moved):
    """The names ride alongside the ids; nothing that keyed off them changed."""
    payload = _payload(moved)
    assert payload["entity_id"] == WANDERER
    assert payload["to"] == CELLAR
