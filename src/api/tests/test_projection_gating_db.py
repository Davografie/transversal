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
    Attunement,
    AttunementOp,
    AttunementScope,
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


TRAITSET_ALPHA_TWIN = "test-gating-ts-alpha-twin"
ALPHA_TWIN = f"{CHAR_ID}:{UNIVERSE_ALPHA}:2"
TRAIT_ALPHA_TWIN = "test-gating-trait-alpha-twin"

# The set-scoped ego cases (2026-09-13): an ungated set is universal, a set gated
# elsewhere takes its ego traits dark — and its own ``universes`` list is never
# consulted (TRAIT_EGO_DARK declares ALPHA but sits in a GAMMA-gated set).
TRAITSET_EGO_UNIVERSAL = "test-gating-ts-ego-universal"
TRAIT_EGO_UNIVERSAL = "test-gating-trait-ego-universal"
TRAITSET_EGO_DARK = "test-gating-ts-ego-dark"
TRAIT_EGO_DARK = "test-gating-trait-ego-dark"


def _cleanup(repo):
    """Remove the fixture data (idempotent — safe on a partial/absent run)."""
    repo.delete_entity(CHAR_ID)  # cascades projections + trait settings
    for tid in (TRAIT_ALPHA, TRAIT_BETA, TRAIT_GAMMA, TRAIT_EGO,
                TRAIT_EGO_UNIVERSAL, TRAIT_EGO_DARK):
        repo.delete_trait(tid)
    for tsid in (TRAITSET_ALPHA, TRAITSET_BETA, TRAITSET_GAMMA, TRAITSET_EGO,
                 TRAITSET_EGO_UNIVERSAL, TRAITSET_EGO_DARK):
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
    repo.create_traitset(TraitSet(id=TRAITSET_EGO_UNIVERSAL, name="ego universal set", universes=[]))
    repo.create_traitset(TraitSet(id=TRAITSET_EGO_DARK, name="ego gamma set", universes=[UNIVERSE_GAMMA]))

    # Traits.
    repo.create_trait(Trait(id=TRAIT_ALPHA, name="alpha morph", universes=[UNIVERSE_ALPHA], traitset_id=TRAITSET_ALPHA))
    repo.create_trait(Trait(id=TRAIT_BETA, name="beta morph", universes=[UNIVERSE_BETA], traitset_id=TRAITSET_BETA))
    repo.create_trait(Trait(id=TRAIT_GAMMA, name="gamma morph", universes=[UNIVERSE_GAMMA], traitset_id=TRAITSET_GAMMA))
    repo.create_trait(Trait(id=TRAIT_EGO, name="ego distinction", universes=[UNIVERSE_ALPHA], traitset_id=TRAITSET_EGO))
    repo.create_trait(Trait(id=TRAIT_EGO_UNIVERSAL, name="ego everywhere", universes=[UNIVERSE_ALPHA], traitset_id=TRAITSET_EGO_UNIVERSAL))
    repo.create_trait(Trait(id=TRAIT_EGO_DARK, name="ego in a gamma set", universes=[UNIVERSE_ALPHA], traitset_id=TRAITSET_EGO_DARK))

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

    # Trait settings: entity-anchored ego, projection-anchored morphs.
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
        traitset_id=TRAITSET_EGO, dice=[DieType.D8],
    ))
    repo.create_traitsetting(TraitSetting(
        id=f"{CHAR_ID}:ego-universal", entity_id=CHAR_ID, trait_id=TRAIT_EGO_UNIVERSAL,
        traitset_id=TRAITSET_EGO_UNIVERSAL, dice=[DieType.D8],
    ))
    repo.create_traitsetting(TraitSetting(
        id=f"{CHAR_ID}:ego-dark", entity_id=CHAR_ID, trait_id=TRAIT_EGO_DARK,
        traitset_id=TRAITSET_EGO_DARK, dice=[DieType.D8],
    ))

    yield repo

    _cleanup(repo)


@pytest.fixture(scope="module")
def db_repo():
    return _repo


def _has(settings, trait_id):
    return any(ts.trait_id == trait_id for ts in settings)


# ── Gating behaviour (fixture-scoped) ────────────────

def test_effective_universes_are_the_active_body_only(gating_data):
    """A second NATIVE home does not go live on its own.

    ``transversal_type`` is provenance, never a gate for trait availability —
    another body's traits arrive only through a deliberate, costed effect. See
    [[Active Projections Design Log]].
    """
    repo = gating_data
    char = repo.get_entity(CHAR_ID)
    universes = repo.effective_universes(char)
    assert UNIVERSE_ALPHA in universes      # active body
    assert UNIVERSE_GAMMA not in universes  # second NATIVE home — not auto-live
    assert UNIVERSE_BETA not in universes   # consciousness body, not active


def test_attunement_is_how_another_universe_goes_live(gating_data):
    """The deliberate path: an attunement makes another universe available."""
    repo = gating_data
    char = repo.get_entity(CHAR_ID)
    attuned = char.model_copy(update={
        "attunements": [Attunement(universe=UNIVERSE_GAMMA, scope=AttunementScope.SELF)],
    })
    universes = repo.effective_universes(attuned)
    assert UNIVERSE_ALPHA in universes
    assert UNIVERSE_GAMMA in universes      # live via the effect, not the body type


def test_active_projections_default_to_the_current_body(gating_data):
    repo = gating_data
    char = repo.get_entity(CHAR_ID)
    assert repo.active_projections(char) == [f"{CHAR_ID}:{UNIVERSE_ALPHA}"]
    assert repo.effective_universes(char) == [UNIVERSE_ALPHA]


def test_suppression_cuts_a_specific_body_out(gating_data):
    """A `remove` grant naming a body takes it out of the active set."""
    repo = gating_data
    char = repo.get_entity(CHAR_ID)
    suppressed = char.model_copy(update={
        "attunements": [Attunement(
            op=AttunementOp.REMOVE,
            projection_id=f"{CHAR_ID}:{UNIVERSE_ALPHA}",
            scope=AttunementScope.SELF,
        )],
    })
    assert repo.active_projections(suppressed) == []
    assert repo.effective_universes(suppressed) == []   # ego traits only


def test_swap_is_add_plus_suppress(gating_data):
    """Swap = attune another body + suppress the current one (two effects)."""
    repo = gating_data
    char = repo.get_entity(CHAR_ID)
    swapped = char.model_copy(update={
        "attunements": [
            Attunement(op=AttunementOp.ADD, universe=UNIVERSE_GAMMA,
                       scope=AttunementScope.SELF),
            Attunement(op=AttunementOp.REMOVE, projection_id=f"{CHAR_ID}:{UNIVERSE_ALPHA}",
                       scope=AttunementScope.SELF),
        ],
    })
    assert repo.active_projections(swapped) == [f"{CHAR_ID}:{UNIVERSE_GAMMA}"]
    assert repo.effective_universes(swapped) == [UNIVERSE_GAMMA]


def test_effective_traitsettings_are_projection_native(gating_data):
    """Two bodies in ONE universe do not share availability.

    The projection-native gate: only the body that is in the active set counts, so a
    second body in the same universe stays dark. Universe-based gating cannot tell
    them apart — that is exactly the case this method exists for (see
    [[Active Projections Design Log]]).
    """
    repo = gating_data
    alpha_body = f"{CHAR_ID}:{UNIVERSE_ALPHA}"
    repo.create_traitset(TraitSet(id=TRAITSET_ALPHA_TWIN, name="alpha twin set",
                                  universes=[UNIVERSE_ALPHA]))
    repo.create_trait(Trait(id=TRAIT_ALPHA_TWIN, name="alpha twin morph",
                            universes=[UNIVERSE_ALPHA], traitset_id=TRAITSET_ALPHA_TWIN))
    repo.create_projection(Projection(
        id=ALPHA_TWIN, entity_id=CHAR_ID, origin_universe=UNIVERSE_ALPHA,
        universe=UNIVERSE_ALPHA, transversal_type=TransversalType.NATIVE,
    ))
    repo.create_traitsetting(TraitSetting(
        id=f"{CHAR_ID}:alpha-twin", entity_id=CHAR_ID, trait_id=TRAIT_ALPHA_TWIN,
        from_type="projection", projection_id=ALPHA_TWIN,
        traitset_id=TRAITSET_ALPHA_TWIN, dice=[DieType.D6],
    ))
    try:
        live = repo.get_effective_traitsettings_for_projections(
            CHAR_ID, [alpha_body], [UNIVERSE_ALPHA])
        assert _has(live, TRAIT_ALPHA)           # the live body's morph trait
        assert not _has(live, TRAIT_ALPHA_TWIN)  # same universe, but not live
        assert _has(live, TRAIT_EGO)             # ego, in a set gated to this universe

        # The universe-scoped question is the coarser one — it cannot separate them.
        by_universe = repo.get_effective_traitsettings(CHAR_ID, [UNIVERSE_ALPHA])
        assert _has(by_universe, TRAIT_ALPHA_TWIN)
    finally:
        repo.delete_projection(ALPHA_TWIN)
        repo.delete_trait(TRAIT_ALPHA_TWIN)
        repo.delete_traitset(TRAITSET_ALPHA_TWIN)


def test_projection_anchored_trait_gated_by_origin(gating_data):
    repo = gating_data
    beta = repo.get_effective_traitsettings(CHAR_ID, [UNIVERSE_BETA])
    assert _has(beta, TRAIT_BETA)
    elsewhere = repo.get_effective_traitsettings(CHAR_ID, [UNIVERSE_ALPHA, UNIVERSE_GAMMA])
    assert not _has(elsewhere, TRAIT_BETA)


def test_ego_traits_follow_the_set_not_the_trait(gating_data):
    """The 2026-09-13 decision: *the traits not universe gated, the traitset gated*.

    An ego trait's own ``universes`` list is never consulted. Its **set's** is: an
    ungated set is universal, and a set gated elsewhere takes its ego traits dark
    with it — ``TRAIT_EGO_DARK`` declares ALPHA itself but sits in a GAMMA-gated
    set, so it is dark in ALPHA and live in GAMMA. This replaces the old
    "entity-anchored traits are always effective" invariant, which the human
    overruled.
    """
    repo = gating_data
    # TRAIT_EGO — set gated to ALPHA: live there, dark elsewhere.
    assert _has(repo.get_effective_traitsettings(CHAR_ID, [UNIVERSE_ALPHA]), TRAIT_EGO)
    for universes in ([UNIVERSE_BETA], [UNIVERSE_GAMMA], [UNIVERSE_BETA, UNIVERSE_GAMMA]):
        assert not _has(repo.get_effective_traitsettings(CHAR_ID, universes), TRAIT_EGO)

    # TRAIT_EGO_DARK — its OWN list says ALPHA, its SET says GAMMA: the set wins, so
    # it is dark in ALPHA and live in GAMMA. That is the whole decision in one pair.
    assert not _has(repo.get_effective_traitsettings(CHAR_ID, [UNIVERSE_ALPHA]), TRAIT_EGO_DARK)
    assert not _has(repo.get_effective_traitsettings(CHAR_ID, [UNIVERSE_BETA]), TRAIT_EGO_DARK)
    assert _has(repo.get_effective_traitsettings(CHAR_ID, [UNIVERSE_GAMMA]), TRAIT_EGO_DARK)

    # An ungated set is universal, whatever the trait declares.
    for universes in ([UNIVERSE_ALPHA], [UNIVERSE_BETA], [UNIVERSE_GAMMA]):
        assert _has(repo.get_effective_traitsettings(CHAR_ID, universes), TRAIT_EGO_UNIVERSAL)


def test_ego_set_gate_on_the_projection_native_path(gating_data):
    """The same rule on the body-scoped question the sheet actually asks."""
    repo = gating_data
    at_alpha = repo.get_effective_traitsettings_for_projections(
        CHAR_ID, [f"{CHAR_ID}:{UNIVERSE_ALPHA}"], [UNIVERSE_ALPHA])
    assert _has(at_alpha, TRAIT_EGO)
    assert not _has(at_alpha, TRAIT_EGO_DARK)      # set gated to gamma → dark
    assert _has(at_alpha, TRAIT_EGO_UNIVERSAL)     # ungated set → live

    at_gamma = repo.get_effective_traitsettings_for_projections(
        CHAR_ID, [f"{CHAR_ID}:{UNIVERSE_GAMMA}"], [UNIVERSE_GAMMA])
    assert _has(at_gamma, TRAIT_EGO_DARK)
    assert not _has(at_gamma, TRAIT_EGO)           # and the alpha set is dark here


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
