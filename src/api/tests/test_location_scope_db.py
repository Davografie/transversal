"""Integration test for location scope against the live ArangoDB.

The scope is an AQL traversal, and a pure-unit test cannot catch a malformed one:
AQL evaluates ``PRUNE`` **at the start vertex too**, where the traversed edge is
``null`` — so ``PRUNE e.type != 'super'`` prunes the entire walk and the scope
silently comes back empty. That was a real bug in the first cut; this test is
what catches it.

Isolated fixture data, torn down (see ``test_projection_gating_db.py`` for the
convention): a parent location that owns a rule, a child inside it, and a third
location that is unrelated. Skips when ArangoDB is unavailable.
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

HALL = "test-scope-hall"          # the parent, and the place that owns a rule
CELLAR = "test-scope-cellar"      # nested inside the hall
ELSEWHERE = "test-scope-elsewhere"
RULE = "test-scope-rule-sfx"


def _cleanup(repo):
    for lid in (CELLAR, HALL, ELSEWHERE):
        try:
            repo.delete_entity(lid)
        except Exception:
            pass


@pytest.fixture(scope="module")
def scope_data():
    repo = _repo
    _cleanup(repo)  # self-heal an interrupted prior run

    repo.create_entity(Entity(id=HALL, type=EntityType.LOCATION, name="Test Hall",
                              current_universe="test-scope", sfx_ids=[RULE]))
    repo.create_entity(Entity(id=CELLAR, type=EntityType.LOCATION, name="Test Cellar",
                              current_universe="test-scope"))
    repo.create_entity(Entity(id=ELSEWHERE, type=EntityType.LOCATION, name="Test Elsewhere",
                              current_universe="test-scope"))
    repo.create_relationship(CELLAR, HALL, "super")  # child -> parent
    yield repo
    # Both directions: an earlier cut of this test wrote it the wrong way round.
    repo.delete_relationship(CELLAR, HALL, "super")
    repo.delete_relationship(HALL, CELLAR, "super")
    _cleanup(repo)


def test_the_scope_finds_the_place_and_its_ancestors(scope_data):
    """Standing in the cellar still puts you under the hall's rule."""
    repo = scope_data
    ids = [loc.id for loc in repo.list_ancestor_locations_with_sfx(CELLAR)]
    assert HALL in ids, "the walk up the super chain must find the owning place"
    assert CELLAR not in ids, "the cellar owns no rules of its own"


def test_the_place_itself_is_in_scope(scope_data):
    repo = scope_data
    ids = [loc.id for loc in repo.list_ancestor_locations_with_sfx(HALL)]
    assert ids == [HALL]


def test_an_unrelated_location_is_not_in_scope(scope_data):
    repo = scope_data
    assert [loc.id for loc in repo.list_ancestor_locations_with_sfx(ELSEWHERE)] == []


def test_a_place_without_rules_is_not_returned(scope_data):
    """Only places that *own* rules come back — so the common case stays cheap."""
    repo = scope_data
    assert [loc.id for loc in repo.list_ancestor_locations_with_sfx(CELLAR)] == [HALL]
