"""Tests for rating parser and resource dice operations on the dice array."""

import pytest

from transversal.domain import DieType, RatingType, TraitSetting, dice_list_to_rating
from transversal.domain.rating import parse_rating
from transversal.services.resource_pool import (
    ResourcePoolError,
    spend_die,
    recover_die,
    step_up,
)


# ── Parser ──────────────────────────────────────────────

class TestParseRating:
    def test_single_die(self):
        assert parse_rating("d10") == [DieType.D10]

    def test_counted_dice(self):
        assert parse_rating("2d8") == [DieType.D8, DieType.D8]

    def test_mixed_pool(self):
        result = parse_rating("4d4+7d6")
        assert result.count(DieType.D4) == 4
        assert result.count(DieType.D6) == 7
        assert len(result) == 11

    def test_mixed_with_spaces(self):
        result = parse_rating("2d4 + d6")
        assert result.count(DieType.D4) == 2
        assert result.count(DieType.D6) == 1

    def test_capacity_mix(self):
        result = parse_rating("8d4+5d6")
        assert result.count(DieType.D4) == 8
        assert result.count(DieType.D6) == 5

    def test_uppercase_d(self):
        assert parse_rating("3D6") == [DieType.D6, DieType.D6, DieType.D6]

    def test_empty_string_raises(self):
        with pytest.raises(ValueError, match="Could not parse"):
            parse_rating("")

    def test_garbage_raises(self):
        with pytest.raises(ValueError, match="Could not parse"):
            parse_rating("not a rating")


# ── dice_list_to_rating ─────────────────────────────────

class TestDiceListToRating:
    def test_single(self):
        assert dice_list_to_rating([DieType.D10]) == "d10"

    def test_counted(self):
        assert dice_list_to_rating([DieType.D8, DieType.D8]) == "2d8"

    def test_mixed(self):
        assert dice_list_to_rating(
            [DieType.D4, DieType.D4, DieType.D4, DieType.D4,
             DieType.D6, DieType.D6, DieType.D6, DieType.D6,
             DieType.D6, DieType.D6, DieType.D6]
        ) == "4d4 + 7d6"

    def test_empty(self):
        assert dice_list_to_rating([]) == "empty"

    def test_sorted_order(self):
        # d4 comes before d8 regardless of input order
        assert dice_list_to_rating([DieType.D8, DieType.D4]) == "d4 + d8"


# ── Spend / Recover ─────────────────────────────────────

class FakeEM:
    def __init__(self):
        self._ts = {}

    def update_traitsetting(self, ts):
        self._ts[ts.id] = ts
        return ts


@pytest.fixture
def em():
    return FakeEM()


@pytest.fixture
def qi_ts():
    return TraitSetting(
        id="kael-1:qi",
        entity_id="kael-1",
        trait_id="trait-qi",
        rating_type=RatingType.RESOURCE,
        dice=[DieType.D4, DieType.D4, DieType.D4, DieType.D4],
    )


class TestSpendDie:
    def test_spend_one(self, em, qi_ts):
        result = spend_die(qi_ts, DieType.D4, em)
        assert len(result.dice) == 3
        assert result.dice.count(DieType.D4) == 3
        assert result.spent_dice.count(DieType.D4) == 1

    def test_spend_all(self, em, qi_ts):
        for _ in range(4):
            qi_ts = spend_die(qi_ts, DieType.D4, em)
        assert len(qi_ts.dice) == 0
        assert len(qi_ts.spent_dice) == 4

    def test_spend_wrong_type_raises(self, em, qi_ts):
        with pytest.raises(ResourcePoolError, match="No d6 die"):
            spend_die(qi_ts, DieType.D6, em)

    def test_spend_from_empty_raises(self, em, qi_ts):
        for _ in range(4):
            qi_ts = spend_die(qi_ts, DieType.D4, em)
        with pytest.raises(ResourcePoolError, match="No d4 die"):
            spend_die(qi_ts, DieType.D4, em)


class TestRecoverDie:
    def test_recover_one(self, em, qi_ts):
        qi_ts = spend_die(qi_ts, DieType.D4, em)
        result = recover_die(qi_ts, DieType.D4, em)
        assert len(result.dice) == 4
        assert result.spent_dice == []

    def test_capacity_is_preserved(self, em, qi_ts):
        # 6d6 pool: spend 2, capacity (dice + spent) stays 6.
        ts = TraitSetting(
            id="x:res", entity_id="x", trait_id="t",
            rating_type=RatingType.RESOURCE,
            dice=[DieType.D6] * 6,
        )
        ts = spend_die(ts, DieType.D6, em)
        ts = spend_die(ts, DieType.D6, em)
        assert len(ts.dice) == 4
        assert len(ts.spent_dice) == 2
        assert len(ts.dice) + len(ts.spent_dice) == 6

    def test_recover_unspent_type_raises(self, em, qi_ts):
        # Recovery is bounded by the ledger: you can't recover a die that
        # was never spent.
        qi_ts = spend_die(qi_ts, DieType.D4, em)
        with pytest.raises(ResourcePoolError, match="No spent d6 die"):
            recover_die(qi_ts, DieType.D6, em)

    def test_recover_with_nothing_spent_raises(self, em, qi_ts):
        with pytest.raises(ResourcePoolError, match="No spent d4 die"):
            recover_die(qi_ts, DieType.D4, em)


class TestStepUp:
    def test_step_up_d4_to_d6(self, em, qi_ts):
        result = step_up(qi_ts, DieType.D4, em)
        assert DieType.D4 in result.dice  # 3 remaining
        assert DieType.D6 in result.dice  # 1 upgraded
        assert result.dice.count(DieType.D4) == 3
        assert result.dice.count(DieType.D6) == 1

    def test_step_up_nonexistent_raises(self, em, qi_ts):
        with pytest.raises(ResourcePoolError, match="No d12 die"):
            step_up(qi_ts, DieType.D12, em)
