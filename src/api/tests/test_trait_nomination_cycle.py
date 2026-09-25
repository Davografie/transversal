"""The registry's nomination graph cannot loop ([[B143]]).

A registry trait nominates what may be put *inside* it, two ways: individual
traits (``possible_subtrait_ids``) and whole trait sets
(``possible_subtraitset_ids``, meaning every trait in the set). Following those
nominations has to stay a path. If it can return to where it started, the
registry is saying a trait may contain itself.

Nothing walks nominations recursively today, so the loop is authoring-only and
harmless *right now* — which is the point of refusing it before container
content gets deep. This is the **nomination** graph and is deliberately not the
same check as ``_would_cycle`` (a setting nested under its own descendant) or a
shortcut trait referencing another trait.

The live registry was measured before this went in: **802 traits, 63 with
``possible_subtrait_ids``, 18 with ``possible_subtraitset_ids``, 858 direct
nominations and 20 set nominations — and 0 cycles, 0 self-nominations.** So the
guard refuses nothing that exists; it only stops the first one being authored.

Live-ArangoDB tests. They build an isolated registry and tear it down, and skip
when ArangoDB is unavailable.
"""

import pytest

from transversal.db.repository import EntityRepository
from transversal.domain import DieType, Trait, TraitSet

try:
    _repo = EntityRepository()
    HAVE_DB = True
except Exception:
    _repo = None
    HAVE_DB = False

pytestmark = pytest.mark.skipif(not HAVE_DB, reason="ArangoDB not available")

U = "test-nomcycle-u"

TS_MAIN = "ts-nomcycle-main"
TS_OTHER = "ts-nomcycle-other"

A, B, C, OUTSIDE = (
    "trait-nomcycle-a", "trait-nomcycle-b",
    "trait-nomcycle-c", "trait-nomcycle-outside",
)

# The chain the fixtures build: A nominates B, B nominates C.
_CHAIN = {"a": A, "b": B, "c": C}


def _cleanup(repo):
    for tid in (A, B, C, OUTSIDE):
        repo.delete_trait(tid)
    for tsid in (TS_MAIN, TS_OTHER):
        repo.delete_traitset(tsid)


def _seed(repo):
    """A nominates B nominates C. OUTSIDE nominates nothing and is in its own set."""
    _cleanup(repo)
    for ts in (
        TraitSet(id=TS_MAIN, name="nomcycle main", universes=[U]),
        TraitSet(id=TS_OTHER, name="nomcycle other", universes=[U]),
    ):
        repo.create_traitset(ts)
    for trait in (
        Trait(id=A, name="A", universes=[U], traitset_id=TS_MAIN,
              default_die_type=DieType.D8, possible_subtrait_ids=[B]),
        Trait(id=B, name="B", universes=[U], traitset_id=TS_MAIN,
              default_die_type=DieType.D6, possible_subtrait_ids=[C]),
        Trait(id=C, name="C", universes=[U], traitset_id=TS_MAIN,
              default_die_type=DieType.D4),
        Trait(id=OUTSIDE, name="Outside", universes=[U], traitset_id=TS_OTHER,
              default_die_type=DieType.D4),
    ):
        repo.create_trait(trait)


def _nominate(repo, trait_id: str, *, ids=None, sets=None):
    """Propose a new nomination list for ``trait_id`` and write it."""
    trait = repo.get_trait(trait_id)
    if ids is not None:
        trait.possible_subtrait_ids = ids
    if sets is not None:
        trait.possible_subtraitset_ids = sets
    return repo.update_trait(trait)


# ── The rule ─────────────────────────────────────────

def test_a_trait_cannot_nominate_itself():
    repo = _repo
    _seed(repo)
    try:
        with pytest.raises(ValueError):
            repo.create_trait(Trait(
                id=OUTSIDE + "-self", name="Self", universes=[U],
                traitset_id=TS_MAIN, possible_subtrait_ids=[OUTSIDE + "-self"],
            ))
        assert repo.get_trait(OUTSIDE + "-self") is None
    finally:
        repo.delete_trait(OUTSIDE + "-self")
        _cleanup(repo)


def test_a_two_step_loop_is_refused():
    """B nominating A closes A → B → A, the shape the ticket names."""
    repo = _repo
    _seed(repo)
    try:
        with pytest.raises(ValueError):
            _nominate(repo, B, ids=[A])
        # …and the stored list is untouched.
        assert repo.get_trait(B).possible_subtrait_ids == [C]
    finally:
        _cleanup(repo)


def test_a_longer_loop_is_refused():
    """C nominating A closes A → B → C → A — depth must not matter."""
    repo = _repo
    _seed(repo)
    try:
        with pytest.raises(ValueError):
            _nominate(repo, C, ids=[A])
        assert repo.get_trait(C).possible_subtrait_ids == []
    finally:
        _cleanup(repo)


def test_a_trait_cannot_nominate_its_own_traitset():
    """A set nomination expands to every trait in it — including the nominator."""
    repo = _repo
    _seed(repo)
    try:
        with pytest.raises(ValueError):
            _nominate(repo, A, sets=[TS_MAIN])
        assert repo.get_trait(A).possible_subtraitset_ids == []
    finally:
        _cleanup(repo)


def test_a_loop_through_another_set_is_refused():
    """A nominates the set OUTSIDE is in; OUTSIDE is pointed back at A."""
    repo = _repo
    _seed(repo)
    try:
        # OUTSIDE → A is fine on its own (OUTSIDE is not reachable from A yet).
        _nominate(repo, OUTSIDE, ids=[A])
        # Now A nominating OUTSIDE's whole set closes it through the set.
        with pytest.raises(ValueError):
            _nominate(repo, A, sets=[TS_OTHER])
    finally:
        _cleanup(repo)


def test_the_refusal_names_the_loop():
    """The message is what a caller reports, so it has to read as a cycle."""
    repo = _repo
    _seed(repo)
    try:
        with pytest.raises(ValueError) as exc:
            _nominate(repo, C, ids=[A])
        message = str(exc.value)
        assert "C" in message and "A" in message and "B" in message
    finally:
        _cleanup(repo)


# ── What must still be allowed ───────────────────────

def test_a_plain_chain_is_allowed():
    """A → B → C is the ordinary case; only a *return* is refused."""
    repo = _repo
    _seed(repo)
    try:
        assert repo.nomination_cycle(repo.get_trait(A)) is None
        assert repo.nomination_cycle(repo.get_trait(B)) is None
        assert repo.nomination_cycle(repo.get_trait(C)) is None
    finally:
        _cleanup(repo)


def test_nominating_an_unrelated_trait_is_allowed():
    repo = _repo
    _seed(repo)
    try:
        assert _nominate(repo, C, ids=[OUTSIDE]) is not None
        assert repo.nomination_cycle(repo.get_trait(C)) is None
    finally:
        _cleanup(repo)


def test_a_diamond_is_allowed():
    """Two paths to the same trait is sharing, not a loop."""
    repo = _repo
    _seed(repo)
    try:
        _nominate(repo, B, ids=[C, OUTSIDE])
        assert _nominate(repo, A, ids=[B, C]) is not None
        assert repo.nomination_cycle(repo.get_trait(A)) is None
    finally:
        _cleanup(repo)


def test_a_trait_may_nominate_a_set_it_is_not_in():
    repo = _repo
    _seed(repo)
    try:
        assert _nominate(repo, A, sets=[TS_OTHER]) is not None
        assert repo.nomination_cycle(repo.get_trait(A)) is None
    finally:
        _cleanup(repo)


# ── The live registry is acyclic, so nothing on it is refused ────────

def test_no_live_trait_is_refused_by_the_new_guard():
    """The guard must not turn a pre-existing registry into an un-editable one.

    Every trait in the live registry is re-checked; a cycle anywhere would make
    that trait refuse *any* future edit, so this is the regression that matters.
    """
    repo = _repo
    offenders = [
        t.id for t in repo.get_all_traits() if repo.nomination_cycle(t) is not None
    ]
    assert offenders == []
