"""The trait-set setting is addressable whether or not it has been written (B228).

A trait-set setting is an **override**: ``limit=None`` means *the set's registry
default* and ``sfx_ids=[]`` means *this set carries no rules of its own*. So the
(entity, set) pair is real before anything is stored against it, and the id is a
pure function of the pair — ``{entity_id}:{traitset_id}``, the shape both writers
that have ever minted one already use.

That is what makes the three hops usable by the effect system: a rule may land on
a set-level setting that nothing has created yet, and the write that stores it is
the same act that materializes the row. Before this, the only creator in the whole
application was one effect action, and ``set_sfx_for_owner`` *refused* a set-level
attach whenever the row was absent — so no live row carries an SFX at all.

Live-ArangoDB tests skip when ArangoDB is unavailable.
"""

from types import SimpleNamespace as NS

import pytest

from transversal.services.target_resolver import TargetContext, resolve
from transversal.services.target_spec import (
    FilterStep,
    LiteralStep,
    NavigateStep,
    SelectStep,
    TargetSpec,
)
from transversal.services.traitset_settings import (
    UNSET,
    parse_traitsetsetting_id,
    resolve as resolve_setting,
    resolve_stored_or_default,
    traitsetsetting_id,
    upsert,
)


def spec(*steps):
    return TargetSpec(steps=list(steps))


ENTITY = "gmc-1"
OTHER_ENTITY = "gmc-2"
TRAITSET = "ts-motivations"
OTHER_TRAITSET = "ts-skills"
TRAIT = "trait-duty"
OTHER_TRAIT = "trait-nerve"
RULE = "sfx-test-rule"


class FakeRepo:
    """The minimum the set-setting plumbing reads."""

    def __init__(self):
        self.entities = {
            ENTITY: NS(id=ENTITY, type="gmc"),
            OTHER_ENTITY: NS(id=OTHER_ENTITY, type="gmc"),
        }
        self.traits = {
            TRAIT: NS(id=TRAIT, traitset_id=TRAITSET),
            OTHER_TRAIT: NS(id=OTHER_TRAIT, traitset_id=OTHER_TRAITSET),
        }
        self.traitsets = {
            TRAITSET: NS(id=TRAITSET, name="motivations"),
            OTHER_TRAITSET: NS(id=OTHER_TRAITSET, name="skills"),
        }
        self.settings = {}          # traitsetsettings by id
        self.traitsettings = {
            "gmc-1:trait-duty": NS(id="gmc-1:trait-duty", entity_id=ENTITY,
                                   trait_id=TRAIT, from_type="entity"),
            # Another set's instance, and a nested one: neither is one of the
            # set's own top-level instances.
            "gmc-1:trait-nerve": NS(id="gmc-1:trait-nerve", entity_id=ENTITY,
                                    trait_id=OTHER_TRAIT, from_type="entity"),
            "gmc-1:trait-duty:nested": NS(id="gmc-1:trait-duty:nested",
                                          entity_id=ENTITY, trait_id=TRAIT,
                                          from_type="traitsetting"),
        }

    def get_entity(self, eid):
        return self.entities.get(eid)

    def get_trait(self, tid):
        return self.traits.get(tid)

    def get_traitset_by_id(self, tsid):
        return self.traitsets.get(tsid)

    def get_traits_by_traitset(self, tsid):
        return [t for t in self.traits.values() if t.traitset_id == tsid]

    def get_traitsetting(self, tsid):
        return self.traitsettings.get(tsid)

    def get_traitsetsetting(self, tss_id):
        return self.settings.get(tss_id)

    def create_traitsetsetting(self, tss):
        self.settings[tss.id] = tss
        return tss

    def update_traitsetsetting(self, tss):
        self.settings[tss.id] = tss
        return tss

    def get_traitsetsettings_for_entity(self, eid):
        return [s for s in self.settings.values() if s.entity_id == eid]

    def get_traitsetsettings_for_traitset(self, tsid):
        return [s for s in self.settings.values() if s.traitset_id == tsid]

    def get_traitsettings_for_entity(self, eid):
        return [t for t in self.traitsettings.values() if t.entity_id == eid]

    def get_traitsettings_for_entity_and_traitset(self, eid, tsid):
        """Mirrors the repository's two-step read: the set's traits, then the
        entity's settings among them, nested ones excluded."""
        trait_ids = {t.id for t in self.get_traits_by_traitset(tsid)}
        return [t for t in self.traitsettings.values()
                if t.entity_id == eid and t.trait_id in trait_ids
                and t.from_type != "traitsetting"]


def ctx(repo, subject=ENTITY):
    return TargetContext(subject=repo.get_entity(subject), repo=repo)


# ── The derived id ───────────────────────────────────────

def test_the_id_is_the_pair():
    assert traitsetsetting_id(ENTITY, TRAITSET) == f"{ENTITY}:{TRAITSET}"


def test_the_id_round_trips():
    assert parse_traitsetsetting_id(traitsetsetting_id(ENTITY, TRAITSET)) == (ENTITY, TRAITSET)


def test_a_non_pair_is_not_parsed():
    assert parse_traitsetsetting_id("") is None
    assert parse_traitsetsetting_id("gmc-1") is None
    assert parse_traitsetsetting_id("a:b:c") is None


# ── Resolution: stored, default, or nothing ──────────────

def test_an_absent_setting_resolves_to_the_default_it_would_have():
    """Not an invention: this is what every reader already computes for a missing
    row, so returning it as an object changes no answer and makes the pair nameable."""
    setting = resolve_setting(FakeRepo(), ENTITY, TRAITSET)
    assert setting.id == f"{ENTITY}:{TRAITSET}"
    assert setting.entity_id == ENTITY and setting.traitset_id == TRAITSET
    assert setting.limit is None and setting.sfx_ids == []


def test_a_stored_setting_resolves_to_itself():
    repo = FakeRepo()
    repo.settings[f"{ENTITY}:{TRAITSET}"] = NS(
        id=f"{ENTITY}:{TRAITSET}", entity_id=ENTITY, traitset_id=TRAITSET,
        from_type="entity", sfx_ids=[RULE], limit=4)
    setting = resolve_setting(repo, ENTITY, TRAITSET)
    assert setting.limit == 4 and setting.sfx_ids == [RULE]


def test_a_pair_is_defaulted_only_when_both_ends_exist():
    """A target invented for a typo is worse than an unresolved one: validation and
    the picker would both report a name for something the world does not have."""
    repo = FakeRepo()
    assert resolve_stored_or_default(repo, f"{ENTITY}:{TRAITSET}") is not None
    assert resolve_stored_or_default(repo, "gmc-nope:ts-motivations") is None
    assert resolve_stored_or_default(repo, f"{ENTITY}:ts-nope") is None
    assert resolve_stored_or_default(repo, "not-a-pair") is None


def test_a_trait_instances_id_is_not_mistaken_for_a_setting():
    """`{entity}:{trait}` has the same shape as `{entity}:{traitset}`, so the shape
    alone cannot tell them apart — the second half has to resolve as a trait set."""
    repo = FakeRepo()
    assert parse_traitsetsetting_id("gmc-1:trait-duty") == ("gmc-1", "trait-duty")
    assert resolve_stored_or_default(repo, "gmc-1:trait-duty") is None


# ── Write: the first write creates the row ───────────────

def test_upsert_creates_the_row_on_first_write():
    repo = FakeRepo()
    assert repo.get_traitsetsetting(f"{ENTITY}:{TRAITSET}") is None
    setting = upsert(repo, ENTITY, TRAITSET, sfx_ids=[RULE])
    assert setting.id == f"{ENTITY}:{TRAITSET}"
    assert repo.get_traitsetsetting(setting.id).sfx_ids == [RULE]


def test_upsert_leaves_omitted_fields_alone():
    repo = FakeRepo()
    upsert(repo, ENTITY, TRAITSET, limit=3)
    upsert(repo, ENTITY, TRAITSET, sfx_ids=[RULE])
    setting = resolve_setting(repo, ENTITY, TRAITSET)
    assert setting.limit == 3 and setting.sfx_ids == [RULE]


def test_upsert_clears_the_limit_when_asked_explicitly():
    """`None` already means "no override", so it must not be confused with the
    unset sentinel that means "leave it"."""
    repo = FakeRepo()
    upsert(repo, ENTITY, TRAITSET, limit=3)
    assert resolve_setting(repo, ENTITY, TRAITSET).limit == 3
    upsert(repo, ENTITY, TRAITSET, limit=None)
    assert resolve_setting(repo, ENTITY, TRAITSET).limit is None
    assert UNSET is not None


# ── The three hops ───────────────────────────────────────

def test_an_instance_reaches_the_setting_governing_its_set():
    """`trait instance → the set-level setting for its set`, and it resolves with
    **no row stored** — the hop that lets a rule land on an un-overridden set."""
    repo = FakeRepo()
    got = resolve(
        spec(SelectStep(collection="self_traitsettings"), NavigateStep(edge="traitsetsetting")),
        ctx(repo),
    ).values
    # One landing per instance, each on *its own* set's setting — the two top-level
    # instances reach two different sets, and the nested one rides its parent's.
    assert {v.id for v in got} == {f"{ENTITY}:{TRAITSET}", f"{ENTITY}:{OTHER_TRAITSET}"}
    assert all(v.limit is None and v.sfx_ids == [] for v in got)


def test_an_instance_of_an_unknown_trait_reaches_nothing():
    repo = FakeRepo()
    repo.traitsettings = {
        "gmc-1:trait-duty": NS(id="gmc-1:trait-duty", entity_id=ENTITY,
                               trait_id="trait-gone", from_type="entity")}
    assert resolve(
        spec(SelectStep(collection="self_traitsettings"), NavigateStep(edge="traitsetsetting")),
        ctx(repo),
    ).values == []


def test_an_entity_reaches_its_stored_set_settings():
    repo = FakeRepo()
    assert resolve(spec(SelectStep(collection="self"), NavigateStep(edge="traitsetsettings")),
                   ctx(repo)).values == []
    upsert(repo, ENTITY, TRAITSET, sfx_ids=[RULE])
    upsert(repo, OTHER_ENTITY, TRAITSET)
    got = resolve(spec(SelectStep(collection="self"), NavigateStep(edge="traitsetsettings")),
                  ctx(repo)).values
    assert [v.id for v in got] == [f"{ENTITY}:{TRAITSET}"]


def test_a_traitset_reaches_its_stored_settings_across_entities():
    repo = FakeRepo()
    upsert(repo, ENTITY, TRAITSET)
    upsert(repo, OTHER_ENTITY, TRAITSET)
    upsert(repo, ENTITY, OTHER_TRAITSET)
    got = resolve(
        spec(LiteralStep(element="traitset", value=TRAITSET),
             NavigateStep(edge="traitsetsettings")),
        ctx(repo),
    ).values
    assert sorted(v.id for v in got) == [f"{ENTITY}:{TRAITSET}", f"{OTHER_ENTITY}:{TRAITSET}"]


def test_a_set_setting_can_be_named_as_a_literal_before_it_exists():
    """The `select source`/literal route: the derived id resolves for a real pair."""
    repo = FakeRepo()
    got = resolve(spec(LiteralStep(element="traitsetsetting", value=f"{ENTITY}:{TRAITSET}")),
                  ctx(repo)).values
    assert [v.id for v in got] == [f"{ENTITY}:{TRAITSET}"]
    assert resolve(spec(LiteralStep(element="traitsetsetting", value=f"{ENTITY}:ts-nope")),
                   ctx(repo)).values == []


def test_the_sfx_list_is_filterable():
    """The field a set-level setting exists to hold, now matchable — a reach
    selector can ask for "the sets that already carry this rule"."""
    repo = FakeRepo()
    upsert(repo, ENTITY, TRAITSET, sfx_ids=[RULE])
    upsert(repo, ENTITY, OTHER_TRAITSET)
    got = resolve(
        spec(SelectStep(collection="self_traitsetsettings"),
             FilterStep(field="sfx_ids", operator="contains", value=RULE)),
        ctx(repo),
    ).values
    assert [v.id for v in got] == [f"{ENTITY}:{TRAITSET}"]


# ── …and back down: a setting reaches the instances it governs ──

def test_a_set_setting_reaches_the_instances_it_governs():
    """`traitset_setting → trait_setting` — what makes a rule attached **once** to a
    set behave like one attached to each of its traits (the `sfx-gift` path)."""
    repo = FakeRepo()
    got = resolve(
        spec(LiteralStep(element="traitsetsetting", value=f"{ENTITY}:{TRAITSET}"),
             NavigateStep(edge="traitsettings")),
        ctx(repo),
    ).values
    assert [v.id for v in got] == [f"{ENTITY}:{TRAIT}"]


def test_the_governed_instances_are_that_set_only_and_never_nested():
    """Another set's instance is not this set's, and a nested sub-trait rides its
    parent — the same exclusion `entity → traitsettings` makes."""
    repo = FakeRepo()
    got = resolve(
        spec(LiteralStep(element="traitsetsetting", value=f"{ENTITY}:{OTHER_TRAITSET}"),
             NavigateStep(edge="traitsettings")),
        ctx(repo),
    ).values
    assert [v.id for v in got] == [f"{ENTITY}:{OTHER_TRAIT}"]


def test_the_gift_path_walks_a_set_setting_source_to_its_traits():
    """The shape the Gift SFX needs end to end: `select source → navigate
    traitsettings`, with the source resolved stored-or-default, so a rule attached
    to a set nobody had overridden still walks down to what the set holds."""
    repo = FakeRepo()
    context = TargetContext(subject=repo.get_entity(ENTITY), repo=repo,
                            source=resolve_setting(repo, ENTITY, TRAITSET),
                            source_element="traitsetsetting")
    got = resolve(
        spec(SelectStep(collection="source"), NavigateStep(edge="traitsettings")),
        context,
    ).values
    assert [v.id for v in got] == [f"{ENTITY}:{TRAIT}"]


def test_a_set_setting_reaches_the_entity_it_sits_on():
    """A rule carried by a *set* has no actor of its own — the setting records one.

    This is the hop that lets such a rule name the character it is acting for, and
    so the first step of *bind the world I am in*: without it
    ``select source → navigate entity`` is a trace error, which is what the author
    hit while giving `sfx-gift` a bound universe.
    """
    repo = FakeRepo()
    got = resolve(
        spec(LiteralStep(element="traitsetsetting", value=f"{ENTITY}:{TRAITSET}"),
             NavigateStep(edge="entity")),
        ctx(repo),
    ).values
    assert [v.id for v in got] == [ENTITY]


# ── Live ArangoDB ────────────────────────────────────────

try:
    from transversal.db.repository import EntityRepository
    from transversal.domain import EntityType

    _repo = EntityRepository()
    HAVE_DB = True
except Exception:  # pragma: no cover - the whole class skips
    _repo = None
    HAVE_DB = False


def _pair_without_a_row(repo):
    """A real (GMC, set-it-could-hold) pair that nothing has overridden."""
    sets = [t for t in repo.get_all_traitsets() if EntityType.GMC in t.entity_types]
    for e in repo.list_all_entities():
        if e.type is not EntityType.GMC:
            continue
        for t in sets:
            if repo.get_traitsetsetting(traitsetsetting_id(e.id, t.id)) is None:
                return e, t
    return None, None


@pytest.mark.skipif(not HAVE_DB, reason="ArangoDB not available")
class TestAgainstLiveArango:
    def test_a_live_pair_resolves_before_it_exists_and_materializes_on_write(self):
        repo = _repo
        entity, traitset = _pair_without_a_row(repo)
        assert entity is not None, "no un-overridden (GMC, set) pair to test with"
        setting_id = traitsetsetting_id(entity.id, traitset.id)

        # 1. Addressable with no document, and the default is the honest one.
        before = resolve_setting(repo, entity.id, traitset.id)
        assert before.id == setting_id
        assert before.limit is None and before.sfx_ids == []
        assert resolve_stored_or_default(repo, setting_id) is not None

        # 2. The hop from a live instance, with nothing stored.
        trait = next((t for t in repo.get_traits_by_traitset(traitset.id)), None)
        assert trait is not None, "the chosen set has no traits to hang the hop on"
        assert _hop_from_instance(repo, entity, trait, traitset) == [setting_id]

        # 3. The first write is what creates the row, and it cleans up completely.
        try:
            upsert(repo, entity.id, traitset.id, sfx_ids=["sfx-probe"], limit=2)
            stored = repo.get_traitsetsetting(setting_id)
            assert stored is not None
            assert stored.sfx_ids == ["sfx-probe"] and stored.limit == 2
            assert setting_id in [
                s.id for s in repo.get_traitsetsettings_for_traitset(traitset.id)]
            assert _hop_from_instance(repo, entity, trait, traitset) == [setting_id]
        finally:
            repo.delete_traitsetsetting(setting_id)
        assert repo.get_traitsetsetting(setting_id) is None

    def test_a_live_set_setting_walks_down_to_the_instances_it_governs(self):
        """The requested hop against the real registry. An instance no longer
        records its set ([[B209]]), so the set is read through the trait — which
        makes this the only check that the two reads agree."""
        repo = _repo
        pair = next(
            ((s.entity_id, s.traitset_id) for s in repo.list_all_traitsetsettings()
             if repo.get_traitsettings_for_entity_and_traitset(s.entity_id, s.traitset_id)),
            None,
        )
        if pair is None:
            pytest.skip("no live set setting has instances to walk down to")
        entity_id, traitset_id = pair
        got = resolve(
            spec(LiteralStep(element="traitsetsetting",
                             value=traitsetsetting_id(entity_id, traitset_id)),
                 NavigateStep(edge="traitsettings")),
            ctx(repo, entity_id),
        ).values
        assert got, "a live set setting walked down to nothing"
        in_set = {t.id for t in repo.get_traits_by_traitset(traitset_id)}
        assert all(s.trait_id in in_set for s in got)
        assert all(s.from_type != "traitsetting" for s in got)
        assert all(s.entity_id == entity_id for s in got)

    def test_a_set_level_source_can_bind_the_world_and_filter_the_registry_by_it(self):
        """The author's shape, against the live registry: take the actor from the
        setting, bind the world that actor is in, then keep only the traits that
        world offers.

        The assertion is the *content*, not the count: every trait returned must
        declare the universe that was bound. A path that had narrowed by the
        author's world instead would sail through a count check and fail this one.
        """
        repo = _repo
        entity, traitset = _pair_without_a_row(repo)
        assert entity is not None, "no un-overridden (GMC, set) pair to test with"
        context = TargetContext(
            subject=entity, repo=repo,
            source=resolve_setting(repo, entity.id, traitset.id),
            source_element="traitsetsetting",
        )
        got = resolve(
            spec(SelectStep(collection="source"),
                 NavigateStep(edge="entity"),
                 NavigateStep(edge="universe", output="world"),
                 SelectStep(collection="traits"),
                 FilterStep(field="universes", operator="contains", value="{world}")),
            context,
        )
        assert not got.errors, got.errors
        binding = context.bindings.get("world")
        assert binding is not None, "the world hop bound nothing"
        world = getattr(binding, "value", binding)
        assert world == entity.current_universe
        assert got.values, f"the filter narrowed every trait away for {world!r}"
        assert len(got.values) < len(repo.get_all_traits()), "the filter narrowed nothing"
        for trait in got.values:
            assert world in (trait.universes or []), (
                f"'{trait.name}' does not declare {world!r}")


def _hop_from_instance(repo, entity, trait, traitset) -> list[str]:
    """Run `entity's instance of a trait in <set> → its set-level setting` live."""
    ts = NS(id=f"{entity.id}:{trait.id}", entity_id=entity.id, trait_id=trait.id,
            from_type="entity")
    from transversal.services.target_resolver import _traitsetting_traitsetsetting

    return [s.id for s in _traitsetting_traitsetsetting(ts, ctx(repo, entity.id))]
