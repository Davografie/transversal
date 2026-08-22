"""Integration tests against the live ArangoDB for projection gating.

These verify the real AQL/DB code paths (effective universes, origin fallback,
projection-anchored trait gating) rather than the in-memory test double. Unlike
a smoke test that pins seeded content, they build their own isolated fixture
data and tear it down, so they never depend on a live entity (e.g. ``kael-1``)
or its mutable state. They skip when ArangoDB is unavailable.
"""

import pytest

from transversal.db.arango import TRAITSETTINGS
from transversal.db.repository import EntityRepository
from transversal.domain import (
    DieType,
    Entity,
    EntityType,
    Projection,
    Trait,
    TraitSet,
    TraitSetting,
    TransversalType,
)
from transversal.services.entity_manager import _origin_universe_from_key

try:
    _repo = EntityRepository()
    HAVE_DB = True
except Exception:
    _repo = None
    HAVE_DB = False

pytestmark = pytest.mark.skipif(not HAVE_DB, reason="ArangoDB not available")


# ── Isolated fixture data ────────────────────────────

CHAR_ID = "test-gating-char"
UNIVERSE_ALPHA = "test-gating-alpha"
UNIVERSE_BETA = "test-gating-beta"
UNIVERSE_GAMMA = "test-gating-gamma"

TRAIT_ALPHA = "test-gating-trait-alpha"
TRAIT_BETA = "test-gating-trait-beta"
TRAIT_GAMMA = "test-gating-trait-gamma"
TRAIT_EGO = "test-gating-trait-ego"

TRAITSET_ALPHA = "test-gating-ts-alpha"
TRAITSET_BETA = "test-gating-ts-beta"
TRAITSET_GAMMA = "test-gating-ts-gamma"
TRAITSET_EGO = "test-gating-ts-ego"


def _cleanup(repo):
    """Remove the fixture data (idempotent — safe on a partial/absent run)."""
    repo.delete_entity(CHAR_ID)  # cascades projections + trait settings
    for tid in (TRAIT_ALPHA, TRAIT_BETA, TRAIT_GAMMA, TRAIT_EGO):
        repo.delete_trait(tid)
    for tsid in (TRAITSET_ALPHA, TRAITSET_BETA, TRAITSET_GAMMA, TRAITSET_EGO):
        repo.delete_traitset(tsid)


@pytest.fixture(scope="module")
def gating_data():
    repo = _repo
    _cleanup(repo)  # self-heal any leftover from an interrupted prior run

    # Trait sets (universe-gated registries).
    repo.create_traitset(TraitSet(id=TRAITSET_ALPHA, name="alpha set", universes=[UNIVERSE_ALPHA]))
    repo.create_traitset(TraitSet(id=TRAITSET_BETA, name="beta set", universes=[UNIVERSE_BETA]))
    repo.create_traitset(TraitSet(id=TRAITSET_GAMMA, name="gamma set", universes=[UNIVERSE_GAMMA]))
    repo.create_traitset(TraitSet(id=TRAITSET_EGO, name="ego set", universes=[UNIVERSE_ALPHA]))

    # Traits.
    repo.create_trait(Trait(id=TRAIT_ALPHA, name="alpha morph", universes=[UNIVERSE_ALPHA], traitset_id=TRAITSET_ALPHA))
    repo.create_trait(Trait(id=TRAIT_BETA, name="beta morph", universes=[UNIVERSE_BETA], traitset_id=TRAITSET_BETA))
    repo.create_trait(Trait(id=TRAIT_GAMMA, name="gamma morph", universes=[UNIVERSE_GAMMA], traitset_id=TRAITSET_GAMMA))
    repo.create_trait(Trait(id=TRAIT_EGO, name="ego distinction", universes=[UNIVERSE_ALPHA], traitset_id=TRAITSET_EGO))

    # Character — active body is the alpha NATIVE projection.
    repo.create_entity(Entity(
        id=CHAR_ID,
        type=EntityType.CHARACTER,
        name="Gating Test Char",
        current_universe=UNIVERSE_ALPHA,
        current_projection=f"{CHAR_ID}:{UNIVERSE_ALPHA}",
    ))

    # Two NATIVE homes (alpha active, gamma second) + one CONSCIOUSNESS body (beta).
    repo.create_projection(Projection(
        id=f"{CHAR_ID}:{UNIVERSE_ALPHA}", entity_id=CHAR_ID,
        origin_universe=UNIVERSE_ALPHA, universe=UNIVERSE_ALPHA,
        transversal_type=TransversalType.NATIVE,
    ))
    repo.create_projection(Projection(
        id=f"{CHAR_ID}:{UNIVERSE_GAMMA}", entity_id=CHAR_ID,
        origin_universe=UNIVERSE_GAMMA, universe=UNIVERSE_GAMMA,
        transversal_type=TransversalType.NATIVE,
    ))
    repo.create_projection(Projection(
        id=f"{CHAR_ID}:{UNIVERSE_BETA}", entity_id=CHAR_ID,
        origin_universe=UNIVERSE_BETA, universe=UNIVERSE_BETA,
        transversal_type=TransversalType.CONSCIOUSNESS,
    ))

    # Trait settings: entity-anchored morph, projection-anchored morphs, ego.
    repo.create_traitsetting(TraitSetting(
        id=f"{CHAR_ID}:alpha", entity_id=CHAR_ID, trait_id=TRAIT_ALPHA,
        traitset_id=TRAITSET_ALPHA, dice=[DieType.D6],
    ))
    repo.create_traitsetting(TraitSetting(
        id=f"{CHAR_ID}:beta", entity_id=CHAR_ID, trait_id=TRAIT_BETA,
        from_type="projection", projection_id=f"{CHAR_ID}:{UNIVERSE_BETA}",
        traitset_id=TRAITSET_BETA, dice=[DieType.D8],
    ))
    repo.create_traitsetting(TraitSetting(
        id=f"{CHAR_ID}:gamma", entity_id=CHAR_ID, trait_id=TRAIT_GAMMA,
        from_type="projection", projection_id=f"{CHAR_ID}:{UNIVERSE_GAMMA}",
        traitset_id=TRAITSET_GAMMA, dice=[DieType.D10],
    ))
    repo.create_traitsetting(TraitSetting(
        id=f"{CHAR_ID}:ego", entity_id=CHAR_ID, trait_id=TRAIT_EGO,
        traitset_id=TRAITSET_EGO, dice=[DieType.D8], ego=True,
    ))

    yield repo

    _cleanup(repo)


@pytest.fixture(scope="module")
def db_repo():
    return _repo


def _has(settings, trait_id):
    return any(ts.trait_id == trait_id for ts in settings)


# ── Gating behaviour (fixture-scoped) ────────────────

def test_effective_universes_include_active_and_native_homes(gating_data):
    repo = gating_data
    char = repo.get_entity(CHAR_ID)
    universes = repo.effective_universes(char)
    assert UNIVERSE_ALPHA in universes      # active body
    assert UNIVERSE_GAMMA in universes      # second NATIVE home (multiversal)
    assert UNIVERSE_BETA not in universes   # consciousness body, not active


def test_projection_anchored_trait_gated_by_origin(gating_data):
    repo = gating_data
    beta = repo.get_effective_traitsettings(CHAR_ID, [UNIVERSE_BETA])
    assert _has(beta, TRAIT_BETA)
    elsewhere = repo.get_effective_traitsettings(CHAR_ID, [UNIVERSE_ALPHA, UNIVERSE_GAMMA])
    assert not _has(elsewhere, TRAIT_BETA)


def test_entity_anchored_trait_gated_by_trait_universe(gating_data):
    repo = gating_data
    alpha = repo.get_effective_traitsettings(CHAR_ID, [UNIVERSE_ALPHA])
    assert _has(alpha, TRAIT_ALPHA)
    beta_only = repo.get_effective_traitsettings(CHAR_ID, [UNIVERSE_BETA])
    assert not _has(beta_only, TRAIT_ALPHA)


def test_ego_trait_always_effective(gating_data):
    repo = gating_data
    for universes in (
        [UNIVERSE_ALPHA],
        [UNIVERSE_BETA],
        [UNIVERSE_GAMMA],
        [UNIVERSE_ALPHA, UNIVERSE_BETA, UNIVERSE_GAMMA],
    ):
        assert _has(repo.get_effective_traitsettings(CHAR_ID, universes), TRAIT_EGO)


def test_fixture_current_projection_valid(gating_data):
    repo = gating_data
    char = repo.get_entity(CHAR_ID)
    assert repo.get_projection(char.current_projection) is not None


# ── Global invariants (whole DB, not tied to seed content) ──

def test_projection_origin_matches_key(db_repo):
    for proj in db_repo.list_all_projections():
        assert proj.origin_universe == _origin_universe_from_key(proj.id)


def test_no_dangling_projection_anchors(db_repo):
    rows = list(db_repo.db.aql.execute(f"""
        FOR ts IN {TRAITSETTINGS}
        FILTER ts.from_type == "projection"
        LET proj = DOCUMENT(ts._from)
        FILTER proj == null
        RETURN ts._key
    """))
    assert rows == []
