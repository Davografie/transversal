"""Tests for challenge-pool operations (spend + completion check)."""

import pytest

from transversal.domain import DieType, Polarity, RatingType, TraitSetting
from transversal.services.challenge_pools import (
    ChallengePoolError,
    challenge_capacity,
    check_challenge_completion,
    recover_challenge_die,
    spend_challenge_die,
)


class FakeEM:
    def __init__(self):
        self._ts = {}

    def update_traitsetting(self, ts):
        self._ts[ts.id] = ts
        return ts


@pytest.fixture
def em():
    return FakeEM()


def _doom_ts(**kw):
    base = dict(
        id="loc:doom", entity_id="loc-krasnoyarsk", trait_id="trait-doom",
        traitset_id="ts-location", rating_type=RatingType.CHALLENGE,
        dice=[DieType.D6, DieType.D6, DieType.D8], polarity=Polarity.NEGATIVE,
    )
    base.update(kw)
    return TraitSetting(**base)


def _progress_ts(**kw):
    base = dict(
        id="loc:gate", entity_id="loc-sect", trait_id="trait-gate",
        traitset_id="ts-location", rating_type=RatingType.CHALLENGE,
        dice=[DieType.D6, DieType.D6], capacity=[DieType.D6, DieType.D6, DieType.D6],
        polarity=Polarity.POSITIVE,
    )
    base.update(kw)
    return TraitSetting(**base)


class TestSpendChallengeDie:
    def test_spend_doom_die(self, em):
        ts = _doom_ts()
        result = spend_challenge_die(ts, DieType.D6, em, destination="opposition")
        assert result.resource is False
        assert result.die == DieType.D6
        assert result.ts.dice.count(DieType.D6) == 1
        assert result.ts.dice.count(DieType.D8) == 1

    def test_spend_progress_die_returns_resource_flag(self, em):
        ts = _progress_ts()
        result = spend_challenge_die(ts, DieType.D6, em, destination="pool")
        assert result.resource is True
        assert result.ts.dice == [DieType.D6]

    def test_spend_wrong_type_raises(self, em):
        ts = _doom_ts()
        with pytest.raises(ChallengePoolError, match="No d12 die"):
            spend_challenge_die(ts, DieType.D12, em)

    def test_spend_from_empty_raises(self, em):
        ts = _doom_ts(dice=[])
        with pytest.raises(ChallengePoolError, match="No d6 die"):
            spend_challenge_die(ts, DieType.D6, em)

    def test_spend_non_challenge_raises(self, em):
        ts = TraitSetting(
            id="x:res", entity_id="x", trait_id="t",
            rating_type=RatingType.RESOURCE, dice=[DieType.D6],
        )
        with pytest.raises(ChallengePoolError, match="not challenge-rated"):
            spend_challenge_die(ts, DieType.D6, em)


class TestCheckChallengeCompletion:
    def test_complete_when_dice_match_capacity(self):
        ts = _progress_ts(dice=[DieType.D6, DieType.D6, DieType.D6])
        assert check_challenge_completion(ts) is True

    def test_incomplete_when_below_capacity(self):
        ts = _progress_ts()
        assert check_challenge_completion(ts) is False

    def test_multiset_equality_ignores_order(self):
        ts = _progress_ts(
            dice=[DieType.D6, DieType.D6, DieType.D6],
            capacity=[DieType.D6, DieType.D6, DieType.D6],
        )
        assert check_challenge_completion(ts) is True

    def test_negative_never_completes(self):
        ts = _doom_ts(capacity=[DieType.D6, DieType.D6, DieType.D8])
        # dice == capacity, but negative polarity → no completion
        assert check_challenge_completion(ts) is False

    def test_no_capacity_never_completes(self):
        ts = _progress_ts(capacity=None)
        assert check_challenge_completion(ts) is False

    def test_non_challenge_never_completes(self):
        ts = TraitSetting(
            id="x:res", entity_id="x", trait_id="t",
            rating_type=RatingType.RESOURCE, dice=[DieType.D6],
            capacity=[DieType.D6], polarity=Polarity.POSITIVE,
        )
        assert check_challenge_completion(ts) is False


class TestChallengeCapacity:
    def test_returns_capacity(self):
        ts = _progress_ts()
        assert challenge_capacity(ts) == [DieType.D6, DieType.D6, DieType.D6]

    def test_returns_empty_when_unset(self):
        ts = _doom_ts()
        assert challenge_capacity(ts) == []


class TestRecoverChallengeDie:
    """Refunding a die that was spent into a pool and then pulled back out.

    The mirror of the resource auto-recover: the die never reached a roll, so
    it goes straight back into ``dice`` (a challenge pool keeps no ledger).
    """

    def test_refund_restores_the_spent_die(self, em):
        ts = _doom_ts()
        spent = spend_challenge_die(ts, DieType.D6, em, destination="opposition")
        assert spent.ts.dice.count(DieType.D6) == 1

        back = recover_challenge_die(spent.ts, DieType.D6, em)
        assert back.dice.count(DieType.D6) == 2
        assert back.dice.count(DieType.D8) == 1
        assert len(back.dice) == 3

    def test_refund_works_for_a_positive_progress_pool(self, em):
        ts = _progress_ts()
        spent = spend_challenge_die(ts, DieType.D6, em, destination="pool")
        assert spent.resource is True
        back = recover_challenge_die(spent.ts, DieType.D6, em)
        assert back.dice.count(DieType.D6) == 2

    def test_refund_does_not_re_fire_completion(self, em):
        """A refund restores the pre-spend state; completion is not re-checked."""
        ts = _progress_ts(dice=[DieType.D6, DieType.D6, DieType.D6],
                          capacity=[DieType.D6, DieType.D6, DieType.D6])
        assert check_challenge_completion(ts) is True
        spent = spend_challenge_die(ts, DieType.D6, em, destination="pool")
        assert check_challenge_completion(spent.ts) is False
        back = recover_challenge_die(spent.ts, DieType.D6, em)
        # Back to capacity — and the caller is responsible for not re-firing.
        assert check_challenge_completion(back) is True
        assert [d for d in back.dice].count(DieType.D6) == 3

    def test_refund_rejects_a_non_challenge_trait(self, em):
        ts = TraitSetting(
            id="x:res", entity_id="x", trait_id="t",
            rating_type=RatingType.RESOURCE, dice=[DieType.D6],
            capacity=[DieType.D6], polarity=Polarity.POSITIVE,
        )
        with pytest.raises(ChallengePoolError):
            recover_challenge_die(ts, DieType.D6, em)

    def test_refund_persists_through_the_em(self, em):
        ts = _doom_ts()
        spent = spend_challenge_die(ts, DieType.D8, em, destination="opposition")
        recover_challenge_die(spent.ts, DieType.D8, em)
        assert em._ts["loc:doom"].dice.count(DieType.D8) == 1
