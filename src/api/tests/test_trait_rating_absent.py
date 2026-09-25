"""An empty rating is *absent* — no die, and no word standing in for one.

An ``EMPTY`` trait is descriptive (``full name``, ``behaviour``, ``age``) or a
container. It has no rating, and the editor already enforces that on the way in —
switching a trait to EMPTY clears its dice (*"EMPTY traits carry no dice rating —
clear them"*, `useTraitEditor`). The **read** was the half that disagreed, in two
different ways, and both were live:

* **1,261** empty settings still carry a die in storage, so ``rating`` reported it
  as a rating (a meaningless ``d4`` on ``full name``) and ``dieType`` reported it
  too — and where there was none, ``dieType`` fabricated a **d6**;
* **3,423** settings have no dice at all — empty ones and non-empty ones like a
  drained resource — and ``rating`` answered with the literal string
  ``"empty"``, which is what `dice_list_to_rating([])` returns and which stops
  being a sentinel the moment it reaches a client.

The rule now: an empty rating comes back as **null**, and the dice it would have
rated with come back as an **empty array**. Deciding how absence *looks* is the
client's job, and it already does it ("depleted" for a drained resource).

Live-ArangoDB tests for the GraphQL surface, plus unit tests on the shared rule
that both converters use.
"""

import asyncio

import pytest

from transversal.api.graphql.resolvers.converters import _ts_to_gql
from transversal.api.graphql.schema import schema
from transversal.api.graphql.type_defs.traits import _gql_trait_setting, rating_dice
from transversal.db.repository import EntityRepository
from transversal.domain import (
    DieType,
    Entity,
    EntityType,
    Polarity,
    RatingType,
    Trait,
    TraitSet,
    TraitSetting,
)
from transversal.services.entity_manager import EntityManager

try:
    _repo = EntityRepository()
    HAVE_DB = True
except Exception:
    _repo = None
    HAVE_DB = False

pytestmark = pytest.mark.skipif(not HAVE_DB, reason="ArangoDB not available")

U = "test-emptyrating-u"
ENTITY = "test-emptyrating-entity"
TSET = "test-emptyrating-tset"
TRAIT_EMPTY = "test-emptyrating-trait-empty"
TRAIT_STATIC = "test-emptyrating-trait-static"
SETTING_EMPTY = "test-emptyrating-setting-empty"
SETTING_STATIC = "test-emptyrating-setting-static"

_ALL = (ENTITY,)


def _setting(rt, dice, sid="s-1", trait_id=TRAIT_EMPTY) -> TraitSetting:
    return TraitSetting(
        id=sid, entity_id=ENTITY, trait_id=trait_id,
        rating_type=rt, dice=dice, polarity=Polarity.POSITIVE,
    )


def _cleanup(repo):
    for eid in _ALL:
        repo.delete_entity(eid, rmtree=True)
    repo.delete_traitset(TSET)


def _seed(repo):
    """An entity with one EMPTY trait carrying a stray die, and one rated static."""
    _cleanup(repo)
    repo.create_traitset(TraitSet(id=TSET, name="empty-rating set", universes=[U]))
    for tid, name, rt in ((TRAIT_EMPTY, "Full Name", RatingType.EMPTY),
                          (TRAIT_STATIC, "Might", RatingType.STATIC)):
        repo.create_trait(Trait(id=tid, name=name, universes=[U], traitset_id=TSET,
                                default_die_type=DieType.D8, default_rating_type=rt))
    repo.create_entity(Entity(id=ENTITY, type=EntityType.CHARACTER, name="Subject",
                              current_universe=U))
    repo.create_traitsetting(_setting(RatingType.EMPTY, [DieType.D4],
                                      sid=SETTING_EMPTY, trait_id=TRAIT_EMPTY))
    repo.create_traitsetting(_setting(RatingType.STATIC, [DieType.D8],
                                      sid=SETTING_STATIC, trait_id=TRAIT_STATIC))


def _gql(query: str, variables: dict, repo):
    """Execute against the schema over a real repository, with the context the
    app builds — `loaders` included, since the entity's trait-setting list reads
    through a DataLoader."""
    from transversal.api.graphql.loaders import build_loaders

    em = EntityManager(repository=repo)
    result = asyncio.run(schema.execute(
        query, variable_values=variables,
        context_value={"entity_manager": em, "loaders": build_loaders(em)},
    ))
    assert result.errors is None, result.errors
    return result.data


# ── The rule ─────────────────────────────────────────

def test_an_empty_setting_rates_with_no_dice():
    assert rating_dice(_setting(RatingType.EMPTY, [DieType.D4])) == []


def test_a_rated_setting_keeps_its_dice():
    assert rating_dice(_setting(RatingType.STATIC, [DieType.D8])) == [DieType.D8]
    assert rating_dice(_setting(RatingType.CHALLENGE, [DieType.D6, DieType.D6])) == [DieType.D6, DieType.D6]


def test_an_empty_rating_is_null_not_a_die():
    gql = _gql_trait_setting(_setting(RatingType.EMPTY, [DieType.D4]))
    assert gql.rating() is None
    assert gql.dice == []


def test_an_empty_rating_is_null_not_the_word_empty():
    """The `dice_list_to_rating([])` sentinel must not reach a client as a value."""
    gql = _gql_trait_setting(_setting(RatingType.EMPTY, []))
    assert gql.rating() is None
    assert gql.rating() != "empty"


def test_an_empty_rating_does_not_fabricate_a_die_type():
    """`dieType` used to answer D6 for a trait that has no rating at all."""
    assert _gql_trait_setting(_setting(RatingType.EMPTY, [DieType.D4])).die_type() is None
    assert _gql_trait_setting(_setting(RatingType.EMPTY, [])).die_type() is None


def test_a_non_empty_setting_with_no_dice_is_null_not_the_word_empty():
    """A drained resource has nothing to report, and "empty" is not a rating."""
    gql = _gql_trait_setting(_setting(RatingType.RESOURCE, []))
    assert gql.rating() is None
    assert gql.die_type() is None


def test_a_rated_setting_still_reports_normally():
    gql = _gql_trait_setting(_setting(RatingType.STATIC, [DieType.D8]))
    assert gql.rating() == "d8"
    assert gql.die_type() == DieType.D8


def test_both_converters_apply_the_same_rule():
    """The pair that drifted before (`enabled`, `capacity`) must not drift here."""
    setting = _setting(RatingType.EMPTY, [DieType.D4])
    assert _gql_trait_setting(setting).dice == []
    assert _ts_to_gql(setting).dice == []
    rated = _setting(RatingType.STATIC, [DieType.D8])
    assert _gql_trait_setting(rated).dice == _ts_to_gql(rated).dice == [DieType.D8]


# ── Through GraphQL, over a real repository ──────────

def test_the_query_returns_null_and_an_empty_array():
    repo = _repo
    _seed(repo)
    try:
        data = _gql("""
            query($id: ID!) {
                entity(id: $id) { traitSettings { id rating dieType dice ratingType } }
            }
        """, {"id": ENTITY}, repo)
        by_id = {s["id"]: s for s in data["entity"]["traitSettings"]}
        empty = by_id[SETTING_EMPTY]
        assert empty["ratingType"] == "EMPTY"
        assert empty["rating"] is None
        assert empty["dieType"] is None
        assert empty["dice"] == []
    finally:
        _cleanup(repo)


def test_the_query_still_rates_a_rated_trait():
    """The guard must not flatten the ordinary case."""
    repo = _repo
    _seed(repo)
    try:
        data = _gql("""
            query($id: ID!) {
                entity(id: $id) { traitSettings { id rating dieType dice } }
            }
        """, {"id": ENTITY}, repo)
        by_id = {s["id"]: s for s in data["entity"]["traitSettings"]}
        rated = by_id[SETTING_STATIC]
        assert rated["rating"] == "d8"
        assert rated["dieType"] == "D8"
        assert rated["dice"] == ["D8"]
    finally:
        _cleanup(repo)
