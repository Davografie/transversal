"""Read-only smoke tests against the live ArangoDB for projection gating.

These verify the real AQL/DB code paths (effective universes, origin fallback,
projection-anchored trait gating) rather than the in-memory test double. They
skip when ArangoDB is unavailable so the in-memory suite still runs standalone.
"""

import pytest

from transversal.db.arango import TRAITSETTINGS
from transversal.db.repository import EntityRepository

try:
    _repo = EntityRepository()
    HAVE_DB = True
except Exception:
    _repo = None
    HAVE_DB = False

pytestmark = pytest.mark.skipif(not HAVE_DB, reason="ArangoDB not available")


@pytest.fixture(scope="module")
def db_repo():
    return _repo


def test_projections_have_origin_universe(db_repo):
    for proj in db_repo.list_all_projections():
        assert proj.origin_universe == proj.id.rsplit(":", 1)[-1]


def test_kael_effective_universes_include_active(db_repo):
    kael = db_repo.get_entity("kael-1")
    if kael is None:
        pytest.skip("kael-1 not seeded")
    universes = db_repo.effective_universes(kael)
    assert "three_realms" in universes


def test_kael_artifact_in_effective(db_repo):
    kael = db_repo.get_entity("kael-1")
    if kael is None:
        pytest.skip("kael-1 not seeded")
    settings = db_repo.get_effective_traitsettings(
        "kael-1", db_repo.effective_universes(kael)
    )
    assert any(ts.trait_id == "trait-artifact-b72a" for ts in settings)


def test_kael_current_projection_valid(db_repo):
    kael = db_repo.get_entity("kael-1")
    if kael is None:
        pytest.skip("kael-1 not seeded")
    if kael.current_projection:
        assert db_repo.get_projection(kael.current_projection) is not None


def test_no_dangling_projection_anchors(db_repo):
    rows = list(db_repo.db.aql.execute(f"""
        FOR ts IN {TRAITSETTINGS}
        FILTER ts.from_type == "projection"
        LET proj = DOCUMENT(ts._from)
        FILTER proj == null
        RETURN ts._key
    """))
    assert rows == []
