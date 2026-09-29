"""A set an entity holds has a setting whether or not anything was stored (B244).

[[B243]] made the ``(entity, set)`` pair *addressable* — a path can land on a
setting nothing has written, and the first write creates the row. But the reads
that **enumerate** an entity's settings still scanned documents, so the pair was
walkable and not *listable*: measured on the live world while authoring the Gift
SFX, a rule granted to the assets set reached **261** entities and only **1** of
them had a stored row, so the sheet — which draws a set-level granted rule on
that node — had nothing to draw on for the other 260.

The fix is that the entity-facing reads (``Entity.traitSetSettings`` and the
granted-rule membership test) include a **virtual** setting for every set the
entity holds a trait of, while the *targeting* hop ``entity → traitsetsettings``
stays documents-only: a path asks where an effect may land, a sheet asks what
this entity has.

Live-ArangoDB tests skip when ArangoDB is unavailable.
"""

import pytest

from transversal.services import sfx_owner
from transversal.services.traitset_settings import (
    default_for,
    parse_traitsetsetting_id,
    traitsetsetting_id,
)


# ── The default shape (pure) ─────────────────────────────

class ExplodingRepo:
    """Fails loudly if the default constructor reads anything — it must not."""

    def __getattr__(self, name):  # pragma: no cover - only runs on a regression
        raise AssertionError(f"default_for touched the repo ({name})")


def test_default_for_mints_the_derived_id_without_a_read():
    setting = default_for("gmc-1", "ts-assets")
    assert setting.id == traitsetsetting_id("gmc-1", "ts-assets") == "gmc-1:ts-assets"
    assert setting.entity_id == "gmc-1"
    assert setting.traitset_id == "ts-assets"
    assert setting.from_type == "entity"
    # The honest default: nothing overridden, so no rules and the registry limit.
    assert setting.sfx_ids == []
    assert setting.limit is None


def test_default_for_and_resolve_agree_on_the_same_id():
    """``resolve`` on a missing pair returns exactly what ``default_for`` mints —
    if the two could drift, a merged batch and a single lookup would hand back
    different keys for one setting."""
    repo = ExplodingRepo()
    repo.get_traitsetsetting = lambda _id: None  # the only call resolve makes
    from transversal.services.traitset_settings import resolve

    assert resolve(repo, "gmc-1", "ts-assets").id == default_for("gmc-1", "ts-assets").id


# ── Live ArangoDB ────────────────────────────────────────

try:
    from transversal.db.repository import EntityRepository

    _repo = EntityRepository()
    HAVE_DB = True
except Exception:  # pragma: no cover - the whole class skips
    _repo = None
    HAVE_DB = False


@pytest.fixture(autouse=True)
def _cool_the_rule_caches():
    """Leave with the rule caches cold.

    A test here fills `reach_index` from the **real** registry, and that cache is
    process-global: a later fake-repo test would inherit live owners and take a
    branch its stub cannot serve. Clearing on the way out keeps this module's use
    of the live world from becoming another test's invisible input.
    """
    yield
    sfx_owner.invalidate_sfx_cache()


def _held_pair_without_a_row(repo):
    """A real entity and a set it *holds a trait of* that nothing has overridden.

    The held half matters: a virtual setting is derived from an instance, so a set
    the entity has no trait in must not produce one.
    """
    ids = [e.id for e in repo.list_all_entities()]
    for start in range(0, len(ids), 200):
        held = repo.get_traitset_ids_for_entities(ids[start:start + 200])
        for entity_id, set_ids in held.items():
            for set_id in set_ids:
                if repo.get_traitsetsetting(traitsetsetting_id(entity_id, set_id)) is None:
                    return entity_id, set_id
    return None, None


@pytest.mark.skipif(not HAVE_DB, reason="ArangoDB not available")
class TestAgainstLiveArango:
    def test_the_sheet_read_includes_a_held_pair_that_was_never_stored(self):
        repo = _repo
        entity_id, set_id = _held_pair_without_a_row(repo)
        assert entity_id is not None, "every held pair has a stored row — nothing to test"

        rows = repo.get_traitsetsettings_for_entities([entity_id])[entity_id]
        virtual = [r for r in rows if r.traitset_id == set_id]
        assert virtual, "a held-but-unoverridden set produced no setting"
        node = virtual[0]
        assert node.id == traitsetsetting_id(entity_id, set_id)
        assert node.entity_id == entity_id and node.from_type == "entity"
        assert node.sfx_ids == [] and node.limit is None

        # …and the singular form used by the sheet's read path answers too.
        assert repo.get_traitsetsetting(node.id) is None

    def test_the_sheet_read_does_not_invent_a_pair_the_entity_does_not_hold(self):
        repo = _repo
        entity_id, _ = _held_pair_without_a_row(repo)
        assert entity_id is not None
        held = set(repo.get_traitset_ids_for_entities([entity_id])[entity_id])
        unheld = next((t.id for t in repo.get_all_traitsets() if t.id not in held), None)
        assert unheld is not None, "the entity holds every set in the registry"
        got = {r.traitset_id for r in repo.get_traitsetsettings_for_entities([entity_id])[entity_id]}
        assert unheld not in got

    def test_the_effective_read_includes_the_held_pair_and_gates_on_universe(self):
        repo = _repo
        entity_id, set_id = _held_pair_without_a_row(repo)
        assert entity_id is not None
        entity = repo.get_entity(entity_id)

        got = {t.traitset_id for t in repo.get_effective_traitsetsettings(
            entity_id, [entity.current_universe])}
        assert set_id in got, "the availability read did not see the held pair"

        # A set declared for universes keeps the gate: a universe it is not in
        # yields no derived pair either.
        gated = [s for s in repo.get_traitset_ids_for_entities([entity_id])[entity_id]
                 if (repo.get_traitset_by_id(s).universes or [])]
        if gated:
            elsewhere = {t.traitset_id for t in repo.get_effective_traitsetsettings(
                entity_id, ["__no_such_universe__"])}
            assert not (set(gated) & elsewhere), "a gated set leaked through the universe filter"

    def test_the_targeting_hop_stays_documents_only(self):
        """``entity → traitsetsettings`` is the *path* read, and [[B243]] drew that
        boundary deliberately — effects must not be handed a row per held set."""
        repo = _repo
        entity_id, set_id = _held_pair_without_a_row(repo)
        assert entity_id is not None
        stored = {s.traitset_id for s in repo.get_traitsetsettings_for_entity(entity_id)}
        assert set_id not in stored, "the targeting hop started enumerating virtual pairs"

    def test_a_granted_rule_on_a_held_pair_is_available_with_no_row(self):
        """The whole point, against whatever rule is actually declaring reach: a
        granted owner whose pair was never stored is still *available* to its
        entity, because availability membership-tests the derived pair."""
        repo = _repo
        for sfx in repo.get_all_sfxs():
            if not (getattr(sfx, "reach", None) or []):
                continue
            for owner_id in sfx_owner.reach_owner_ids(repo, sfx, "granted"):
                pair = parse_traitsetsetting_id(owner_id)
                if pair is None or repo.get_traitsetsetting(owner_id) is not None:
                    continue
                entity_id, set_id = pair
                entity = repo.get_entity(entity_id)
                if entity is None:
                    continue
                # It is only virtual because the entity holds the set.
                if set_id not in repo.get_traitset_ids_for_entities([entity_id])[entity_id]:
                    continue
                available = sfx_owner.get_available_sfx_ids(
                    entity_id, entity.current_universe, repo)
                assert sfx.id in available, (
                    f"'{sfx.id}' is granted to {owner_id} but is not available to "
                    f"{entity_id} — the held pair did not reach the membership test"
                )
                return
        pytest.skip("no granted rule reaches an un-overridden (entity, set) pair")
