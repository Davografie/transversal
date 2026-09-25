"""Integration tests for the repository batch methods, against live ArangoDB.

The in-memory test double *reimplements* every method in Python, so it never runs
the real AQL — a bug in a ``FILTER … IN @ids`` query cannot be caught by it. These
tests execute the actual queries and assert the batch methods **agree with their
single-entity counterparts**, which is the invariant that matters: the two must
return the same rows for the same input.

They build isolated fixture data and tear it down, so they never depend on a live
entity or its mutable state. They skip when ArangoDB is unavailable.
"""

import pytest

from transversal.db.repository import EntityRepository
from transversal.domain import (
    DieType,
    Entity,
    EntityType,
    Projection,
    SheetTab,
    Trait,
    TraitSet,
    TraitSetSetting,
    TraitSetting,
    TransversalType,
)

try:
    _repo = EntityRepository()
    HAVE_DB = True
except Exception:
    _repo = None
    HAVE_DB = False

pytestmark = pytest.mark.skipif(not HAVE_DB, reason="ArangoDB not available")


# ── Fixture id namespace ──────────────────────────────

ENTITY_A = "test-batch-a"
ENTITY_B = "test-batch-b"
PROJ_A = f"{ENTITY_A}:earth"
PROJ_B = f"{ENTITY_B}:earth"
TRAITSET = "test-batch-ts"
TRAIT_1 = "test-batch-trait-1"
TRAIT_2 = "test-batch-trait-2"
TRAIT_SUB = "test-batch-trait-sub"
TS_A1 = f"{ENTITY_A}:{TRAIT_1}"
TS_A_SUB = f"{TS_A1}:{TRAIT_SUB}"          # sub-trait: anchored to the parent setting
TS_B2 = f"{ENTITY_B}:{TRAIT_2}"
TSS_A = f"{ENTITY_A}:{TRAITSET}"
REL_TYPE = "relation"
REL_TS = "test-batch-rel-ts"


def _cleanup(repo):
    """Remove the fixture data (idempotent — safe on a partial/absent run)."""
    repo.delete_entity(ENTITY_A)  # cascades projections, settings, edges
    repo.delete_entity(ENTITY_B)
    for tid in (TRAIT_1, TRAIT_2, TRAIT_SUB):
        repo.delete_trait(tid)
    repo.delete_traitset(TRAITSET)


@pytest.fixture(scope="module")
def batch_data():
    repo = _repo
    _cleanup(repo)  # self-heal any leftover from an interrupted prior run

    repo.create_traitset(TraitSet(id=TRAITSET, name="batch set", universes=["earth"]))
    repo.create_trait(Trait(id=TRAIT_1, name="Batch One", universes=["earth"], traitset_id=TRAITSET))
    repo.create_trait(Trait(id=TRAIT_2, name="Batch Two", universes=["earth"], traitset_id=TRAITSET))
    repo.create_trait(Trait(id=TRAIT_SUB, name="Batch Sub", universes=["earth"], traitset_id=TRAITSET))

    for eid in (ENTITY_A, ENTITY_B):
        repo.create_entity(Entity(
            id=eid, type=EntityType.CHARACTER, name=f"Batch {eid}",
            current_universe="earth", current_projection=f"{eid}:earth",
        ))
        repo.create_projection(Projection(
            id=f"{eid}:earth", entity_id=eid, origin_universe="earth",
            universe="earth", transversal_type=TransversalType.NATIVE,
        ))

    repo.create_traitsetting(TraitSetting(
        id=TS_A1, entity_id=ENTITY_A, trait_id=TRAIT_1,
        dice=[DieType.D6],
    ))
    repo.create_traitsetting(TraitSetting(
        id=TS_B2, entity_id=ENTITY_B, trait_id=TRAIT_2,
        dice=[DieType.D8],
    ))
    # Sub-trait — from_type='traitsetting', anchored to the parent setting.
    repo.create_traitsetting(TraitSetting(
        id=TS_A_SUB, entity_id=ENTITY_A, trait_id=TRAIT_SUB,
        from_type="traitsetting", parent_traitsetting_id=TS_A1, dice=[DieType.D4],
    ))
    repo.create_traitsetsetting(TraitSetSetting(
        id=TSS_A, entity_id=ENTITY_A, traitset_id=TRAITSET, from_type="entity", limit=3,
    ))

    # A real relationship edge A → B carrying a relationship-anchored trait setting.
    repo.create_relationship(ENTITY_A, ENTITY_B, REL_TYPE)
    edge = repo.get_relationship(ENTITY_A, ENTITY_B, REL_TYPE)
    if edge is not None:
        repo.create_traitsetting(TraitSetting(
            id=REL_TS, entity_id=edge["_key"], trait_id=TRAIT_2,
             from_type="relationship", dice=[DieType.D6],
        ))

    yield repo

    _cleanup(repo)


def _ids(rows):
    return sorted(r.id for r in rows)


# ── Batch ≡ single ────────────────────────────────────

def test_projections_batch_matches_single(batch_data):
    repo = batch_data
    grouped = repo.get_projections_for_entities([ENTITY_A, ENTITY_B])
    assert _ids(grouped[ENTITY_A]) == _ids(repo.get_projections_for_entity(ENTITY_A))
    assert _ids(grouped[ENTITY_B]) == _ids(repo.get_projections_for_entity(ENTITY_B))


def test_projections_batch_returns_a_key_for_every_id(batch_data):
    repo = batch_data
    grouped = repo.get_projections_for_entities([ENTITY_A, ENTITY_B, "test-batch-missing"])
    assert set(grouped) == {ENTITY_A, ENTITY_B, "test-batch-missing"}
    assert grouped["test-batch-missing"] == []


def test_traitsettings_batch_matches_single(batch_data):
    repo = batch_data
    grouped = repo.get_traitsettings_for_entities([ENTITY_A, ENTITY_B])
    assert _ids(grouped[ENTITY_A]) == _ids(repo.get_traitsettings_for_entity(ENTITY_A))
    assert _ids(grouped[ENTITY_B]) == _ids(repo.get_traitsettings_for_entity(ENTITY_B))
    # Sub-traits are excluded from the top-level list on both paths.
    assert TS_A_SUB not in _ids(grouped[ENTITY_A])


def test_traitsetsettings_batch_matches_single(batch_data):
    repo = batch_data
    grouped = repo.get_traitsetsettings_for_entities([ENTITY_A, ENTITY_B])
    assert _ids(grouped[ENTITY_A]) == _ids(repo.get_traitsetsettings_for_entity(ENTITY_A))
    assert _ids(grouped[ENTITY_A]) == [TSS_A]


def test_sub_traitsettings_batch_matches_single(batch_data):
    repo = batch_data
    grouped = repo.get_sub_traitsettings_for_parents([TS_A1, TS_B2])
    assert _ids(grouped[TS_A1]) == _ids(repo.get_sub_traitsettings(TS_A1))
    assert _ids(grouped[TS_A1]) == [TS_A_SUB]
    assert grouped[TS_B2] == []


def test_relationship_traitsettings_batch_matches_single(batch_data):
    repo = batch_data
    grouped = repo.get_relationship_traitsettings_for_entities([ENTITY_A, ENTITY_B])

    def shape(rows):
        return sorted((r["setting"].id, r["contact_id"], r["edge_type"]) for r in rows)

    assert shape(grouped[ENTITY_A]) == shape(repo.get_relationship_traitsettings_for_entity(ENTITY_A))
    assert shape(grouped[ENTITY_A]) == [(REL_TS, ENTITY_B, REL_TYPE)]
    # Only outgoing edges count — B holds nothing about A.
    assert grouped[ENTITY_B] == []


def test_batch_methods_accept_and_return_empty(batch_data):
    """Empty input must not issue a query or invent keys."""
    repo = batch_data
    assert repo.get_projections_for_entities([]) == {}
    assert repo.get_traitsettings_for_entities([]) == {}
    assert repo.get_traitsetsettings_for_entities([]) == {}
    assert repo.get_sub_traitsettings_for_parents([]) == {}
    assert repo.get_relationship_traitsettings_for_entities([]) == {}


# ── allow_duplicates helpers (B116-adjacent, live AQL) ─

def test_traitsettings_for_entity_and_trait(batch_data):
    repo = batch_data
    assert _ids(repo.get_traitsettings_for_entity_and_trait(ENTITY_A, TRAIT_1)) == [TS_A1]
    assert repo.get_traitsettings_for_entity_and_trait(ENTITY_A, TRAIT_2) == []


def test_collision_and_id_resolution(batch_data):
    repo = batch_data
    # A already holds TRAIT_1 → a default (no-duplicates) add collides.
    assert repo.find_traitsetting_collision(ENTITY_A, TRAIT_1) is not None
    assert repo.find_traitsetting_collision(ENTITY_A, TRAIT_2) is None

    # With duplicates allowed, only a same-statement instance collides.
    repo.create_traitsetting(TraitSetting(
        id=f"{ENTITY_A}:{TRAIT_2}", entity_id=ENTITY_A, trait_id=TRAIT_2,
         statement="fencing", dice=[DieType.D6],
    ))
    assert repo.find_traitsetting_collision(
        ENTITY_A, TRAIT_2, statement="archery", allow_duplicates=True) is None
    assert repo.find_traitsetting_collision(
        ENTITY_A, TRAIT_2, statement="fencing", allow_duplicates=True) is not None

    base = repo.resolve_traitsetting_id(ENTITY_A, TRAIT_1)
    assert base == f"{ENTITY_A}:{TRAIT_1}"
    dup = repo.resolve_traitsetting_id(
        ENTITY_A, TRAIT_1, statement="archery", allow_duplicates=True)
    assert dup.startswith(f"{ENTITY_A}:{TRAIT_1}:") and dup != base


# ── Tag pool aggregation ─────────────────────────────────────────
#
# The editor wants the distinct tags a universe uses, not every trait that
# carries one. The AQL must agree with the obvious Python fold.

TAG_UNIVERSE = "test-tag-universe"
TAG_TS = "test-tag-ts"
TAG_TRAITS = ("test-tag-trait-1", "test-tag-trait-2", "test-tag-trait-3")


def _tag_cleanup(repo):
    for tid in TAG_TRAITS:
        repo.delete_trait(tid)
    repo.delete_traitset(TAG_TS)


@pytest.fixture(scope="module")
def tag_data():
    repo = _repo
    _tag_cleanup(repo)  # self-heal any leftover from an interrupted prior run

    repo.create_traitset(TraitSet(id=TAG_TS, name="tag set", universes=[TAG_UNIVERSE]))
    repo.create_trait(Trait(id=TAG_TRAITS[0], name="Tagged One", universes=[TAG_UNIVERSE],
                            traitset_id=TAG_TS, tags=["alpha", "beta"]))
    repo.create_trait(Trait(id=TAG_TRAITS[1], name="Tagged Two", universes=[TAG_UNIVERSE],
                            traitset_id=TAG_TS, tags=["beta", "gamma"]))
    # A trait with no tags and one with an empty string — neither contributes.
    repo.create_trait(Trait(id=TAG_TRAITS[2], name="Untagged", universes=[TAG_UNIVERSE],
                            traitset_id=TAG_TS, tags=[""]))
    yield repo
    _tag_cleanup(repo)


def test_trait_tags_by_universe_agrees_with_folding_the_traits(tag_data):
    """The AQL aggregation is exactly the Python fold: distinct, sorted, no
    empties — the invariant the two must share."""
    repo = tag_data
    expected = sorted({t for tr in repo.get_traits_by_universe(TAG_UNIVERSE)
                       for t in (tr.tags or []) if t})
    assert repo.get_trait_tags_by_universe(TAG_UNIVERSE) == expected
    assert expected == ["alpha", "beta", "gamma"]


def test_trait_tags_by_universe_is_empty_for_an_unknown_universe(tag_data):
    assert tag_data.get_trait_tags_by_universe("no-such-universe") == []


# ── Trait-set sheet tab ──────────────────────────────────────────
#
# The sheet routes a trait by its *set's* designation, not by the trait's
# rating type. Sets written before the field existed must read as "traits",
# and a designated set must persist.

TAB_TS = "test-sheet-tab-ts"
TAB_UNIVERSE = "test-sheet-tab-universe"


def test_traitset_sheet_tab_defaults_to_traits_and_round_trips():
    repo = _repo
    repo.delete_traitset(TAB_TS)  # self-heal from an interrupted prior run
    try:
        repo.create_traitset(TraitSet(id=TAB_TS, name="sheet tab", universes=[TAB_UNIVERSE]))

        # The default — what every pre-existing set reads as.
        fresh = repo.get_traitset_by_id(TAB_TS)
        assert fresh.sheet_tab == SheetTab.TRAITS
        assert TraitSet(id=TAB_TS, name="x", universes=[TAB_UNIVERSE]).sheet_tab == SheetTab.TRAITS

        # A designated set persists its choice.
        fresh.sheet_tab = SheetTab.PROFILE
        repo.update_traitset(fresh)
        assert repo.get_traitset_by_id(TAB_TS).sheet_tab == SheetTab.PROFILE
    finally:
        repo.delete_traitset(TAB_TS)


# ── Sub-trait cycle guard ────────────────────────────────────────
#
# A sub-trait chain must stay a path. Nothing else refuses re-parenting a
# setting under its own descendant, and a loop would make every ancestor walk
# (the ego resolver among them) spin or lie.

CYCLE_TS = "test-cycle-ts"
CYCLE_UNIVERSE = "test-cycle-universe"
CYCLE_ENTITY = "test-cycle-entity"
CYCLE_TRAITS = ("test-cycle-a", "test-cycle-b")
CYCLE_S1, CYCLE_S2 = "test-cycle-s1", "test-cycle-s2"


def _cycle_cleanup(repo):
    for sid in (CYCLE_S2, CYCLE_S1):
        repo.delete_traitsetting(sid)
    for tid in CYCLE_TRAITS:
        repo.delete_trait(tid)
    repo.delete_traitset(CYCLE_TS)


def test_re_parenting_a_sub_trait_under_its_own_descendant_is_refused():
    repo = _repo
    _cycle_cleanup(repo)
    try:
        repo.create_traitset(TraitSet(id=CYCLE_TS, name="cycle", universes=[CYCLE_UNIVERSE]))
        repo.create_trait(Trait(id=CYCLE_TRAITS[0], name="Cycle A",
                                universes=[CYCLE_UNIVERSE], traitset_id=CYCLE_TS))
        repo.create_trait(Trait(id=CYCLE_TRAITS[1], name="Cycle B",
                                universes=[CYCLE_UNIVERSE], traitset_id=CYCLE_TS))
        repo.create_traitsetting(TraitSetting(
            id=CYCLE_S1, entity_id=CYCLE_ENTITY, trait_id=CYCLE_TRAITS[0],
             dice=[DieType.D6]))
        repo.create_traitsetting(TraitSetting(
            id=CYCLE_S2, entity_id=CYCLE_ENTITY, trait_id=CYCLE_TRAITS[1],
             from_type="traitsetting",
            parent_traitsetting_id=CYCLE_S1, dice=[DieType.D6]))

        # An ordinary child is not a cycle.
        assert repo._would_cycle(repo.get_traitsetting(CYCLE_S2)) is False

        # Re-parenting the root under its own child would loop → refused.
        root = repo.get_traitsetting(CYCLE_S1)
        root.from_type = "traitsetting"
        root.parent_traitsetting_id = CYCLE_S2
        assert repo._would_cycle(root) is True
        with pytest.raises(ValueError):
            repo.update_traitsetting(root)
    finally:
        _cycle_cleanup(repo)
