"""Tests for the stateless dice resolver."""

import pytest

from transversal.domain import (
    ChallengeResult,
    CommittedResult,
    ContestWinner,
    DicePoolRequest,
    DieRoll,
    DieSpec,
    DieType,
    Opposition,
    OutcomeTier,
    RollKind,
    SimplifiedResult,
    PoolResult,
)
from transversal.services.dice_resolver import (
    _determine_tier,
    _is_botch,
    _resolve_challenge,
    compare_committed,
    compare_totals,
    detect_hitches,
    is_botch,
    pick_effect_die,
    pick_total,
    resolve,
    resolve_contest,
    roll_dice,
)


class TestDetermineTier:
    def test_fail(self):
        assert _determine_tier(1) == OutcomeTier.FAIL
        assert _determine_tier(2) == OutcomeTier.FAIL

    def test_marginal(self):
        assert _determine_tier(3) == OutcomeTier.MARGINAL
        assert _determine_tier(4) == OutcomeTier.MARGINAL
        assert _determine_tier(5) == OutcomeTier.MARGINAL

    def test_success(self):
        assert _determine_tier(6) == OutcomeTier.SUCCESS
        assert _determine_tier(7) == OutcomeTier.SUCCESS
        assert _determine_tier(8) == OutcomeTier.SUCCESS

    def test_exceptional(self):
        assert _determine_tier(9) == OutcomeTier.EXCEPTIONAL
        assert _determine_tier(10) == OutcomeTier.EXCEPTIONAL
        assert _determine_tier(11) == OutcomeTier.EXCEPTIONAL

    def test_perfect(self):
        assert _determine_tier(12) == OutcomeTier.PERFECT

    def test_tier_effect_die(self):
        assert OutcomeTier.FAIL.effect_die is None
        assert OutcomeTier.MARGINAL.effect_die == DieType.D4
        assert OutcomeTier.SUCCESS.effect_die == DieType.D6
        assert OutcomeTier.EXCEPTIONAL.effect_die == DieType.D8
        assert OutcomeTier.PERFECT.effect_die == DieType.D10


class TestBotch:
    def test_not_botch(self):
        from transversal.domain import DieRoll
        rolls = [DieRoll(die=DieType.D8, result=5, label="test")]
        assert not _is_botch(rolls)

    def test_botch_single(self):
        from transversal.domain import DieRoll
        rolls = [DieRoll(die=DieType.D8, result=1, label="test")]
        assert _is_botch(rolls)

    def test_botch_multiple(self):
        from transversal.domain import DieRoll
        rolls = [
            DieRoll(die=DieType.D8, result=1, label="a"),
            DieRoll(die=DieType.D6, result=1, label="b"),
        ]
        assert _is_botch(rolls)

    def test_not_botch_mixed(self):
        from transversal.domain import DieRoll
        rolls = [
            DieRoll(die=DieType.D8, result=1, label="a"),
            DieRoll(die=DieType.D6, result=5, label="b"),
        ]
        assert not _is_botch(rolls)

    def test_botch_empty(self):
        from transversal.domain import DieRoll
        assert not _is_botch([])


class TestChallengeResolution:
    def test_effect_larger_removes(self):
        result = _resolve_challenge(
            effect_die=DieType.D10,
            challenge_die=DieType.D8,
            success=True,
        )
        assert result.outcome == "removed"
        assert result.new_challenge_rating is None

    def test_effect_equal_steps_down(self):
        result = _resolve_challenge(
            effect_die=DieType.D8,
            challenge_die=DieType.D8,
            success=True,
        )
        assert result.outcome == "stepped_down"
        assert result.new_challenge_rating == "d6"

    def test_effect_smaller_steps_down(self):
        result = _resolve_challenge(
            effect_die=DieType.D6,
            challenge_die=DieType.D8,
            success=True,
        )
        assert result.outcome == "stepped_down"
        assert result.new_challenge_rating == "d6"

    def test_failure_steps_up(self):
        result = _resolve_challenge(
            effect_die=DieType.D6,
            challenge_die=DieType.D8,
            success=False,
        )
        assert result.outcome == "stepped_up"
        assert result.new_challenge_rating == "d10"

    def test_d4_cannot_step_down(self):
        result = _resolve_challenge(
            effect_die=DieType.D6,
            challenge_die=DieType.D4,
            success=True,
        )
        assert result.outcome == "removed"

    def test_d12_cannot_step_up(self):
        result = _resolve_challenge(
            effect_die=DieType.D6,
            challenge_die=DieType.D12,
            success=False,
        )
        assert result.outcome == "unchanged"
        assert result.new_challenge_rating == "d12"


class TestSimplifiedPipeline:
    def test_single_die_success(self):
        request = DicePoolRequest(
            entity_id="test-1",
            universe="earth",
            dice=[(DieType.D8, "shooting")],
        )
        result = resolve(request)
        assert isinstance(result, SimplifiedResult)
        assert result.pipeline == "simplified"
        assert result.highest >= 1
        assert result.highest <= 8
        assert result.rolls[0].die == DieType.D8

    def test_single_die_1_is_botch(self):
        # We can't control randomness, but we can verify structure
        request = DicePoolRequest(
            entity_id="test-1",
            universe="earth",
            dice=[(DieType.D8, "shooting")],
        )
        result = resolve(request)
        assert isinstance(result, SimplifiedResult)
        if result.highest == 1:
            assert result.botch is True
            assert result.tier == OutcomeTier.FAIL
            assert len(result.hitches) >= 1

    def test_two_dice_structure(self):
        request = DicePoolRequest(
            entity_id="test-1",
            universe="three_realms",
            dice=[(DieType.D10, "sword_intent"), (DieType.D6, "qi_reserves")],
        )
        result = resolve(request)
        assert isinstance(result, SimplifiedResult)
        assert len(result.rolls) == 2
        assert result.highest >= 1
        assert result.highest <= 10

    def test_challenge_pool_has_opposition_roll(self):
        request = DicePoolRequest(
            entity_id="test-1",
            universe="three_realms",
            dice=[(DieType.D10, "sword_intent")],
            opposition=Opposition(
                type="challenge",
                challenge_die=DieType.D8,
            ),
        )
        result = resolve(request)
        assert isinstance(result, SimplifiedResult)
        assert result.opposition_roll is not None
        assert result.opposition_roll.die == DieType.D8
        assert result.challenge_result is not None

    def test_simplified_hitches_detected(self):
        request = DicePoolRequest(
            entity_id="test-1",
            universe="earth",
            dice=[(DieType.D4, "unlucky")],
        )
        result = resolve(request)
        assert isinstance(result, SimplifiedResult)
        # Can't assert specific hitch count (random), but structure is correct
        assert result.hitches_count == len(result.hitches)

    def test_simplified_static_difficulty(self):
        request = DicePoolRequest(
            entity_id="test-1",
            universe="earth",
            dice=[(DieType.D8, "shooting")],
            opposition=Opposition(type="static_difficulty", static_difficulty=8),
        )
        result = resolve(request)
        assert isinstance(result, SimplifiedResult)
        assert result.opposition_total == 8


class TestPoolPipeline:
    def test_pool_routes_correctly(self):
        request = DicePoolRequest(
            entity_id="test-1",
            universe="three_realms",
            dice=[
                (DieType.D10, "intelligence"),
                (DieType.D8, "hacking"),
                (DieType.D8, "distinction"),
            ],
        )
        result = resolve(request)
        assert isinstance(result, PoolResult)
        assert result.pipeline == "pool"
        assert len(result.rolls) == 3
        assert len(result.kept) == 2
        assert result.total == sum(r.result for r in result.kept)

    def test_forced_pool_pipeline_on_two_dice(self):
        """A GM difficulty roll with only two dice still keeps-and-sums."""
        request = DicePoolRequest(
            entity_id="gm",
            universe="earth",
            dice=[
                (DieType.D8, "difficulty"),
                (DieType.D8, "difficulty"),
            ],
            pipeline="pool",
        )
        result = resolve(request)
        assert isinstance(result, PoolResult)
        assert result.pipeline == "pool"
        assert len(result.kept) == 2
        assert result.total == sum(r.result for r in result.kept)

    def test_difficulty_hitches_do_not_apply(self):
        """GM difficulty rolls suppress hitch/botch semantics (1s are dice)."""
        request = DicePoolRequest(
            entity_id="gm",
            universe="earth",
            dice=[
                (DieType.D4, "difficulty"),
                (DieType.D4, "difficulty"),
            ],
            pipeline="pool",
            hitches_apply=False,
        )
        result = resolve(request)
        assert result.hitches == []
        assert result.botch is False
        assert result.hitches_count == 0

    def test_pool_effect_die_skips_hitches(self, monkeypatch):
        """A rolled-1 die (hitch) can't be auto-selected as the effect die."""
        from transversal.services import dice_resolver as dr

        rolls = iter([6, 7, 1])  # d8=6, d10=7, d12=1 → the d12 is a hitch
        monkeypatch.setattr(
            dr, "_roll_die",
            lambda spec: DieRoll(**spec.model_dump(), result=next(rolls)),
        )
        request = DicePoolRequest(
            entity_id="test-1",
            universe="three_realms",
            dice=[
                (DieType.D8, "hacking"),
                (DieType.D10, "intelligence"),
                (DieType.D12, "distinction"),
            ],
        )
        result = resolve(request)
        assert isinstance(result, PoolResult)
        # The d12 rolled a 1, so no non-hitch unused die remains → d4 fallback.
        assert result.effect_die == DieType.D4


class TestCompareCommitted:
    def test_pool_higher_total_wins(self):
        challenger = CommittedResult(total=15, effect_die=DieType.D8, pipeline="pool")
        defendant = CommittedResult(total=10, effect_die=DieType.D6, pipeline="pool")
        assert compare_committed(challenger, defendant) == ContestWinner.PLAYER

    def test_pool_tie_favors_challenger(self):
        challenger = CommittedResult(total=12, pipeline="pool")
        defendant = CommittedResult(total=12, pipeline="pool")
        assert compare_committed(challenger, defendant) == ContestWinner.PLAYER

    def test_simplified_higher_tier_wins(self):
        challenger = CommittedResult(total=8, tier=OutcomeTier.SUCCESS, pipeline="simplified")
        defendant = CommittedResult(total=9, tier=OutcomeTier.MARGINAL, pipeline="simplified")
        assert compare_committed(challenger, defendant) == ContestWinner.PLAYER

    def test_mixed_pool_vs_simplified(self):
        challenger = CommittedResult(total=7, pipeline="pool")
        defendant = CommittedResult(total=9, tier=OutcomeTier.SUCCESS, pipeline="simplified")
        assert compare_committed(challenger, defendant) == ContestWinner.OPPONENT

    def test_pool_effect_die_from_unused(self):
        request = DicePoolRequest(
            entity_id="test-1",
            universe="three_realms",
            dice=[
                (DieType.D10, "intelligence"),
                (DieType.D8, "hacking"),
                (DieType.D12, "distinction"),
            ],
        )
        result = resolve(request)
        assert isinstance(result, PoolResult)
        assert len(result.unused) == 1
        if result.unused:
            assert result.effect_die is not None

    def test_pool_no_unused_defaults_effect(self):
        request = DicePoolRequest(
            entity_id="test-1",
            universe="three_realms",
            dice=[
                (DieType.D10, "intelligence"),
                (DieType.D8, "hacking"),
            ],
        )
        # 2 dice should use simplified, but test pool directly by passing 3
        request_3 = DicePoolRequest(
            entity_id="test-1",
            universe="three_realms",
            dice=[
                (DieType.D10, "a"),
                (DieType.D8, "b"),
                (DieType.D6, "c"),
            ],
        )
        result = resolve(request_3)
        assert isinstance(result, PoolResult)

    def test_pool_with_opposition(self):
        request = DicePoolRequest(
            entity_id="test-1",
            universe="three_realms",
            dice=[
                (DieType.D10, "intelligence"),
                (DieType.D8, "hacking"),
                (DieType.D8, "distinction"),
            ],
            opposition=Opposition(
                type="gmc",
                dice=[(DieType.D8, "firewall"), (DieType.D6, "alerted")],
            ),
        )
        result = resolve(request)
        assert isinstance(result, PoolResult)
        assert result.opposition_total is not None

    def test_pool_with_challenge(self):
        request = DicePoolRequest(
            entity_id="test-1",
            universe="three_realms",
            dice=[
                (DieType.D10, "intelligence"),
                (DieType.D8, "hacking"),
                (DieType.D8, "distinction"),
            ],
            opposition=Opposition(
                type="challenge",
                challenge_die=DieType.D8,
            ),
        )
        result = resolve(request)
        assert isinstance(result, PoolResult)
        assert result.challenge_result is not None


class TestDieType:
    def test_step_up(self):
        assert DieType.D4.step_up() == DieType.D6
        assert DieType.D6.step_up() == DieType.D8
        assert DieType.D12.step_up() == DieType.D12  # cap

    def test_step_down(self):
        assert DieType.D12.step_down() == DieType.D10
        assert DieType.D6.step_down() == DieType.D4
        assert DieType.D4.step_down() == DieType.D4  # floor

    def test_max_value(self):
        assert DieType.D4.max_value == 4
        assert DieType.D6.max_value == 6
        assert DieType.D12.max_value == 12


class TestRollKind:
    def test_request_defaults_to_test(self):
        request = DicePoolRequest(
            entity_id="test-1",
            universe="earth",
            dice=[(DieType.D8, "shooting")],
        )
        assert request.kind == RollKind.TEST

    def test_resolve_defaults_to_test(self):
        request = DicePoolRequest(
            entity_id="test-1",
            universe="earth",
            dice=[(DieType.D8, "shooting")],
        )
        result = resolve(request)
        assert result.kind == RollKind.TEST

    def test_resolve_carries_explicit_kind(self):
        request = DicePoolRequest(
            entity_id="test-1",
            universe="earth",
            dice=[(DieType.D8, "shooting")],
            kind=RollKind.ROLL_TABLE,
        )
        result = resolve(request)
        assert result.kind == RollKind.ROLL_TABLE

    def test_contest_forces_contest_kind(self):
        player = DicePoolRequest(
            entity_id="kael", universe="earth",
            dice=[
                (DieType.D8, "shooting"),
                (DieType.D6, "distinction"),
                (DieType.D6, "asset"),
            ],
        )
        opponent = DicePoolRequest(
            entity_id="guard", universe="earth",
            dice=[
                (DieType.D8, "agility"),
                (DieType.D6, "awareness"),
                (DieType.D4, "wary"),
            ],
        )
        result = resolve_contest(player, opponent)
        assert result.kind == RollKind.CONTEST
        assert result.player_result.kind == RollKind.CONTEST
        assert result.opponent_result.kind == RollKind.CONTEST


class TestStructuredDieSource:
    """A rolled die carries its structured source (a DieSpec + result)."""

    def test_pool_roll_preserves_source(self):
        request = DicePoolRequest(
            entity_id="test-1",
            universe="earth",
            dice=[
                DieSpec(die=DieType.D10, source_kind="trait", source_id="ts-hacking", label="Hacking", ts_id="ts-hacking"),
                DieSpec(die=DieType.D8, source_kind="difficulty", label="2d6"),
                DieSpec(die=DieType.D6, source_kind="manual", label="d6"),
            ],
        )
        result = resolve(request)
        assert isinstance(result, PoolResult)
        by_source_id = {r.source_id: r for r in result.rolls}
        hacking = by_source_id["ts-hacking"]
        assert hacking.source_kind == "trait"
        assert hacking.label == "Hacking"
        assert hacking.ts_id == "ts-hacking"
        assert hacking.die == DieType.D10
        assert isinstance(hacking.result, int)


class TestDecomposedCallables:
    """The P2.10d G5 granular callables drive resolution step by step."""

    @staticmethod
    def _r(die, result):
        return DieRoll(die=die, result=result)

    def test_roll_dice_returns_one_roll_per_spec(self):
        specs = [
            DieSpec(die=DieType.D8, label="a"),
            DieSpec(die=DieType.D6, label="b"),
        ]
        rolls = roll_dice(specs)
        assert len(rolls) == 2
        for r in rolls:
            assert 1 <= r.result <= r.die.max_value

    def test_detect_hitches(self):
        rolls = [self._r(DieType.D8, 1), self._r(DieType.D6, 5), self._r(DieType.D4, 1)]
        hitches = detect_hitches(rolls)
        assert len(hitches) == 2
        assert all(r.result == 1 for r in hitches)

    def test_is_botch(self):
        assert is_botch([self._r(DieType.D8, 1), self._r(DieType.D6, 1)])
        assert not is_botch([self._r(DieType.D8, 1), self._r(DieType.D6, 5)])
        assert not is_botch([])

    def test_pick_total(self):
        rolls = [self._r(DieType.D8, 5), self._r(DieType.D6, 3), self._r(DieType.D8, 8)]
        assert pick_total(rolls, [0, 2]) == 13

    def test_pick_effect_die_prefers_largest_type(self):
        rolls = [
            self._r(DieType.D8, 6),   # kept in total
            self._r(DieType.D8, 5),   # kept in total
            self._r(DieType.D6, 6),   # leftover d6
            self._r(DieType.D8, 2),   # leftover d8
        ]
        effect = pick_effect_die(rolls, [0, 1])
        assert effect.die == DieType.D8
        assert effect.result == 2

    def test_pick_effect_die_excludes_hitches(self):
        rolls = [
            self._r(DieType.D8, 6),
            self._r(DieType.D8, 5),
            self._r(DieType.D8, 1),   # leftover hitch (ineligible)
            self._r(DieType.D6, 4),   # leftover d6
        ]
        effect = pick_effect_die(rolls, [0, 1])
        assert effect.die == DieType.D6

    def test_pick_effect_die_none_when_no_leftovers(self):
        rolls = [self._r(DieType.D8, 6), self._r(DieType.D8, 5)]
        assert pick_effect_die(rolls, [0, 1]) is None

    def test_compare_totals(self):
        assert compare_totals(15, 12) == ContestWinner.PLAYER
        assert compare_totals(10, 14) == ContestWinner.OPPONENT
        assert compare_totals(13, 13) == ContestWinner.PLAYER  # tie → initiator


class TestResourceDice:
    """Resource dice roll separately; only the highest applies to the total."""

    def _patch_rolls(self, monkeypatch, results):
        from transversal.services import dice_resolver
        it = iter(results)
        monkeypatch.setattr(
            dice_resolver,
            "_roll_die",
            lambda spec: DieRoll(**spec.model_dump(), result=next(it)),
        )

    def test_resource_highest_added_to_total(self, monkeypatch):
        self._patch_rolls(monkeypatch, [5, 3, 7, 2])  # main 5+3, resource 7 (kept) & 2
        request = DicePoolRequest(
            entity_id="e", universe="earth",
            dice=[
                DieSpec(die=DieType.D8, label="main1"),
                DieSpec(die=DieType.D6, label="main2"),
                DieSpec(die=DieType.D6, label="res1", resource=True),
                DieSpec(die=DieType.D4, label="res2", resource=True),
            ],
        )
        result = resolve(request)
        assert isinstance(result, PoolResult)
        assert result.total == 5 + 3 + 7
        assert len(result.resource_rolls) == 2
        assert result.resource_kept.result == 7
        # kept/effect come from main dice only
        assert len(result.kept) == 2
        assert all(not r.resource for r in result.kept)
        assert all(not r.resource for r in result.unused)

    def test_resource_forces_pool_pipeline(self, monkeypatch):
        # 2 dice total, but one is a resource — must resolve as a pool.
        self._patch_rolls(monkeypatch, [4, 6])
        request = DicePoolRequest(
            entity_id="e", universe="earth",
            dice=[
                DieSpec(die=DieType.D8, label="main"),
                DieSpec(die=DieType.D6, label="res", resource=True),
            ],
        )
        result = resolve(request)
        assert isinstance(result, PoolResult)
        assert result.total == 4 + 6
        assert result.resource_kept.result == 6
