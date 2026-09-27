"""The trait-set offer — `SFX.offer_traitsets`.

A rule is *offered* to a trait instance in one of two ways: its own trait
definition declares it (`Trait.possible_sfx_ids`, one definition at a time), or
the trait's whole **set** offers it — "every trait in this set may learn it", said
once and read at read time.

The offer is not the gate. An offered rule still has to pass its `acquire_spec`
before a chip appears, and an **implicit** rule is never a chip at all — it is
simply *had* by the instances the offer reaches.

The author's case (2026-09-26): a `Gift` rule meant for every trait in the assets
traitset, authored with an acquire path. The path held — verified live — and no chip
appeared anywhere, because nothing offered it: the assets traitset's 65 traits
declared no SFX at all, and editing 65 definitions by hand is not an answer.
"""

from types import SimpleNamespace as NS

import pytest

from transversal.domain import SFX, TargetSpec
from transversal.services.sfx_owner import (
    get_available_sfx_ids,
    invalidate_sfx_cache,
)

ASSETS = "ts-3"
OTHER = "ts-9"

# `select source` is the owner itself, so it resolves — the common authoring shape.
PASSES = TargetSpec(steps=[{"kind": "select", "collection": "source"}])
# …and a filter that matches nothing is a gate that never holds.
FAILS = TargetSpec(steps=[
    {"kind": "select", "collection": "source"},
    {"kind": "filter", "field": "id", "operator": "==", "value": "nobody"},
])


@pytest.fixture(autouse=True)
def _fresh_caches():
    """The offer index is a process-level cache (dropped on every rule write).

    Tests mutate the world between assertions, so they have to drop it first —
    the same requirement the neighbouring SFX/trait-declaration caches already
    carry.
    """
    invalidate_sfx_cache()
    yield
    invalidate_sfx_cache()


class Repo:
    """Just the reads the offer paths make: the availability walk, and the chip."""

    def __init__(self, traitset_id=ASSETS):
        self.entity = NS(id="e1", sfx_ids=[], current_projection=None, current_location=None)
        self.projection = None
        self.owners = {}
        self.locations = {}
        self.location_parents = {}
        self.nested = {}
        self.edge_traits = {}
        self.traitset_settings = []
        self.sfxs = {}
        self.traits = {
            "trait-sword": NS(traitset_id=traitset_id, possible_sfx_ids=[],
                              default_sfx_ids=[], enabled=True),
        }
        # One instance of that trait, held by `e1`.
        self.setting = NS(id="e1:trait-sword", entity_id="e1", trait_id="trait-sword",
                          sfx_ids=[], enabled=True)
        self.trait_settings = [self.setting]

    # ── availability walk ──
    def get_entity(self, entity_id):
        return self.entity

    def get_projection(self, pid):
        return self.projection

    def get_sfx_owner(self, oid):
        return self.owners.get(oid)

    def get_effective_traitsettings(self, entity_id, universes):
        return list(self.trait_settings)

    def get_effective_traitsetsettings(self, entity_id, universes):
        return list(self.traitset_settings)

    def get_relationship_traitsettings_for_entity(self, entity_id):
        return list(self.edge_traits.get(entity_id, []))

    def get_relationship_traitsettings_for_entities(self, entity_ids):
        return {eid: list(self.edge_traits.get(eid, [])) for eid in entity_ids}

    def list_member_factions_with_sfx(self, entity_id):
        return []

    def list_member_factions_with_sfx_bulk(self, entity_ids):
        return {}

    def get_sub_traitsettings_for_parents(self, parent_ids):
        return {pid: list(self.nested.get(pid, [])) for pid in parent_ids}

    def list_ancestor_locations_with_sfx(self, location_id, max_depth=8):
        return []

    # ── the offer reads ──
    def get_trait(self, trait_id):
        return self.traits.get(trait_id)

    def get_sfx(self, sfx_id):
        return self.sfxs.get(sfx_id)

    def get_all_sfxs(self):
        return list(self.sfxs.values())

    def get_traitsetting(self, ts_id):
        return self.setting if ts_id == self.setting.id else None


def _rule(sfx_id="sfx-gift", offer=None, implicit=False, acquire=None):
    return SFX(id=sfx_id, name=sfx_id, trigger="manual", source_kind="trait_setting",
               offer_traitsets=list(offer or []), implicit=implicit, acquire_spec=acquire)


def _chips(repo, ts_id=None):
    """What the sheet asks for: `acquirableSfxIds` for one trait instance."""
    from transversal.api.graphql.resolvers.queries_sfx import QueriesSfx

    info = NS(context={"entity_manager": NS(repo=repo)})
    return [str(s) for s in QueriesSfx().acquirable_sfx_ids(info, ts_id or repo.setting.id)]


# ── The chip: a set offer is an offer ────────────────────────

def test_a_trait_set_offer_puts_the_chip_on_its_traits():
    repo = Repo(traitset_id=ASSETS)
    repo.sfxs["sfx-gift"] = _rule(offer=[ASSETS])

    assert _chips(repo) == ["sfx-gift"]


def test_a_trait_set_offer_does_not_reach_another_set():
    repo = Repo(traitset_id=OTHER)
    repo.sfxs["sfx-gift"] = _rule(offer=[ASSETS])

    assert _chips(repo) == []


def test_an_implicit_rule_is_never_a_chip():
    """It needs no learning, so offering to take it would offer what the instance
    already has ([[B131]])."""
    repo = Repo()
    repo.sfxs["sfx-gift"] = _rule(offer=[ASSETS], implicit=True)

    assert _chips(repo) == []


def test_the_set_offer_still_obeys_the_acquire_gate():
    """The offer says *who may ever*; the gate says *where it may be taken now*."""
    repo = Repo()
    repo.sfxs["sfx-gift"] = _rule(offer=[ASSETS], acquire=FAILS)

    assert _chips(repo) == []


def test_a_rule_offered_by_both_the_trait_and_its_set_appears_once():
    repo = Repo()
    repo.traits["trait-sword"].possible_sfx_ids = ["sfx-gift"]
    repo.sfxs["sfx-gift"] = _rule(offer=[ASSETS])

    assert _chips(repo) == ["sfx-gift"]


# ── Availability: only an implicit rule is simply *had* ──────

def test_an_implicit_set_offer_reaches_availability():
    repo = Repo()
    repo.sfxs["sfx-gift"] = _rule(offer=[ASSETS], implicit=True)

    assert get_available_sfx_ids("e1", "three_realms", repo) == ["sfx-gift"]


def test_a_non_implicit_set_offer_is_not_availability():
    """It is the learn-chip's business until somebody takes it."""
    repo = Repo()
    repo.sfxs["sfx-gift"] = _rule(offer=[ASSETS])

    assert get_available_sfx_ids("e1", "three_realms", repo) == []


def test_an_implicit_set_offer_elsewhere_does_not_reach():
    repo = Repo(traitset_id=OTHER)
    repo.sfxs["sfx-gift"] = _rule(offer=[ASSETS], implicit=True)

    assert get_available_sfx_ids("e1", "three_realms", repo) == []


def test_the_availability_offer_still_obeys_the_gate():
    repo = Repo()
    repo.sfxs["sfx-gift"] = _rule(offer=[ASSETS], implicit=True, acquire=FAILS)

    assert get_available_sfx_ids("e1", "three_realms", repo) == []
