"""Trait-setting field plumbing — `order`, and fields the read path must not drop.

Two concerned reads of the same edge:

1. **`order`** — the author's position among siblings. Sub-traits must come back in
   it, and content that does not use it must keep the order it had before the field
   existed (trait set, then trait id). Enforced against a live DB.
2. **the converter round-trip** — `_gql_trait_setting` feeds *every read path* (the
   sheet's trait list, sub-traits, relationship traits), so a field it forgets reads
   as its default everywhere. That is how `enabled` came to report `True` for
   disabled settings on every read while the mutation responses were correct.
"""

import pytest

from transversal.db.repository import EntityRepository
from transversal.domain import (
    DieType,
    Entity,
    EntityType,
    Polarity,
    RatingType,
    TraitSetting,
)

try:
    _repo = EntityRepository()
    HAVE_DB = True
except Exception:
    _repo = None
    HAVE_DB = False

ENTITY_ID = "test-order-entity"
CONTAINER_ID = f"{ENTITY_ID}:trait-test-container"


def _setting(ts_id: str, order=None, statement: str = "") -> TraitSetting:
    return TraitSetting(
        id=ts_id,
        entity_id=ENTITY_ID,
        trait_id="trait-3160510",          # the container-tagged registry trait
        traitset_id="ts-2200695",
        from_type="traitsetting",
        parent_traitsetting_id=CONTAINER_ID,
        rating_type=RatingType.EMPTY,
        dice=[],
        polarity=Polarity.POSITIVE,
        statement=statement,
        order=order,
    )


def _container() -> TraitSetting:
    return TraitSetting(
        id=CONTAINER_ID,
        entity_id=ENTITY_ID,
        trait_id="trait-3160510",
        traitset_id="ts-2200695",
        rating_type=RatingType.EMPTY,
        dice=[],
    )


def _cleanup(repo):
    repo.delete_entity(ENTITY_ID, rmtree=True)


@pytest.mark.skipif(not HAVE_DB, reason="ArangoDB not available")
class TestSubTraitOrdering:
    def test_children_come_back_in_author_order(self):
        """Created out of order; read back ordered."""
        repo = _repo
        _cleanup(repo)
        repo.create_entity(Entity(id=ENTITY_ID, type=EntityType.FACTION,
                                  name="Order Test", current_universe="earth"))
        repo.create_traitsetting(_container())
        for ts_id, order in (("p3", 3), ("p1", 1), ("p2", 2)):
            repo.create_traitsetting(_setting(f"{CONTAINER_ID}:{ts_id}", order, ts_id))

        got = [ts.id.split(":")[-1] for ts in repo.get_sub_traitsettings(CONTAINER_ID)]
        assert got == ["p1", "p2", "p3"]

        # The batch read (what the loader uses) must agree with the single read.
        grouped = repo.get_sub_traitsettings_for_parents([CONTAINER_ID])
        assert [ts.id.split(":")[-1] for ts in grouped[CONTAINER_ID]] == got

        _cleanup(repo)

    def test_unordered_children_keep_the_order_they_had_before_the_field(self):
        """No `order` → trait set, then trait id, then key.

        Siblings sharing one registry trait — exactly the portent case, many
        settings of one generic trait — have no trait-id tier to break the tie, so
        the key is the last tier and the read is a **total** order: repeat reads
        cannot reshuffle. That makes an unordered container merely unspecified
        rather than unstable.
        """
        repo = _repo
        _cleanup(repo)
        repo.create_entity(Entity(id=ENTITY_ID, type=EntityType.FACTION,
                                  name="Order Test", current_universe="earth"))
        repo.create_traitsetting(_container())
        for ts_id in ("zeta", "alpha", "mid"):
            repo.create_traitsetting(_setting(f"{CONTAINER_ID}:{ts_id}", None, ts_id))

        first = [ts.id for ts in repo.get_sub_traitsettings(CONTAINER_ID)]
        second = [ts.id for ts in repo.get_sub_traitsettings(CONTAINER_ID)]
        assert first == second
        assert len(first) == 3

        _cleanup(repo)

    def test_ordered_children_precede_unordered_ones(self):
        repo = _repo
        _cleanup(repo)
        repo.create_entity(Entity(id=ENTITY_ID, type=EntityType.FACTION,
                                  name="Order Test", current_universe="earth"))
        repo.create_traitsetting(_container())
        repo.create_traitsetting(_setting(f"{CONTAINER_ID}:has-order", 2, "has-order"))
        repo.create_traitsetting(_setting(f"{CONTAINER_ID}:no-order", None, "no-order"))

        got = [ts.id.split(":")[-1] for ts in repo.get_sub_traitsettings(CONTAINER_ID)]
        assert got == ["has-order", "no-order"]

        _cleanup(repo)


class TestConverterCarriesFields:
    """`_gql_trait_setting` is the read path — assert it forwards, not defaults."""

    def test_enabled_and_order_survive_the_read_converter(self):
        from transversal.api.graphql.type_defs.traits import _gql_trait_setting

        s = TraitSetting(
            id="ts-1", entity_id="e-1", trait_id="trait-1", traitset_id="tset-1",
            rating_type=RatingType.STATIC, dice=[DieType.D8],
            enabled=False, order=4, statement="a step", notes="gm only",
        )
        gql = _gql_trait_setting(s)
        assert gql.enabled is False, "a disabled setting read as enabled"
        assert gql.order == 4
        assert gql.notes == "gm only"
