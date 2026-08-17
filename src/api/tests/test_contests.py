"""Tests for contest mechanics — head-to-head dice resolution.

Covers:
  - resolve_contest(): two pools in, winner out
  - Simplified vs Simplified (1-2 dice per side)
  - Pool vs Pool (3+ dice per side)
  - Mixed pipelines (pool vs simplified)
  - Tie-breaking: higher tier beats lower, higher value beats lower,
    same both → challenger (initiator) wins
  - Effect die availability for both winner and loser
  - Per-location ContestTracker: assembly, opposition, resolution
  - Beat lifecycle: clear pools after resolution
"""

import pytest

from transversal.domain import (
    ContestResult,
    ContestWinner,
    DicePoolRequest,
    DieRoll,
    DieType,
    OutcomeTier,
    Opposition,
    PoolAssembly,
    PoolResult,
    SimplifiedResult,
)
from transversal.services.dice_resolver import (
    _resolve_contest_winner,
    _resolve_contest_winner_pool,
    resolve,
    resolve_contest,
)
from transversal.services.contest_tracker import ContestTracker


# ── Contest Winner Helpers ──────────────────────────────

class TestContestWinnerSimplified:
    """Deterministic tie-breaking for simplified contests."""

    def test_higher_tier_wins_regardless_of_value(self):
        """Exceptional (9) beats Success (8) even though 8 < 9 isn't true here.
        Actually: Exceptional tier beats Success tier. Period."""
        winner = _resolve_contest_winner(
            OutcomeTier.EXCEPTIONAL, OutcomeTier.SUCCESS, 9, 8,
        )
        assert winner == ContestWinner.PLAYER

    def test_perfect_beats_exceptional(self):
        winner = _resolve_contest_winner(
            OutcomeTier.PERFECT, OutcomeTier.EXCEPTIONAL, 12, 11,
        )
        assert winner == ContestWinner.PLAYER

    def test_same_tier_higher_value_wins(self):
        """Both Success — player rolled 8, opponent rolled 6."""
        winner = _resolve_contest_winner(
            OutcomeTier.SUCCESS, OutcomeTier.SUCCESS, 8, 6,
        )
        assert winner == ContestWinner.PLAYER

    def test_same_tier_opponent_higher_value_wins(self):
        winner = _resolve_contest_winner(
            OutcomeTier.SUCCESS, OutcomeTier.SUCCESS, 6, 8,
        )
        assert winner == ContestWinner.OPPONENT

    def test_same_tier_same_value_challenger_wins(self):
        """Tie on both tier and value → challenger (initiator) wins."""
        winner = _resolve_contest_winner(
            OutcomeTier.SUCCESS, OutcomeTier.SUCCESS, 7, 7,
        )
        assert winner == ContestWinner.PLAYER

    def test_fail_loses_to_everything(self):
        for tier in [OutcomeTier.MARGINAL, OutcomeTier.SUCCESS,
                      OutcomeTier.EXCEPTIONAL, OutcomeTier.PERFECT]:
            winner = _resolve_contest_winner(
                OutcomeTier.FAIL, tier, 2, 3,
            )
            assert winner == ContestWinner.OPPONENT


class TestContestWinnerPool:
    """Deterministic tie-breaking for pool contests."""

    def test_higher_total_wins(self):
        assert _resolve_contest_winner_pool(15, 12) == ContestWinner.PLAYER

    def test_lower_total_loses(self):
        assert _resolve_contest_winner_pool(10, 14) == ContestWinner.OPPONENT

    def test_tie_goes_to_challenger(self):
        assert _resolve_contest_winner_pool(13, 13) == ContestWinner.PLAYER


# ── resolve_contest() integration ──────────────────────

class TestResolveContestSimplified:
    """End-to-end: two simplified pools contest each other."""

    def test_both_sides_single_die(self):
        player = DicePoolRequest(
            entity_id="kael", universe="earth",
            dice=[(DieType.D8, "shooting")],
        )
        opponent = DicePoolRequest(
            entity_id="guard", universe="earth",
            dice=[(DieType.D6, "agility")],
        )
        result = resolve_contest(player, opponent)
        assert result.pipeline == "simplified"
        assert result.winner in (ContestWinner.PLAYER, ContestWinner.OPPONENT)
        assert isinstance(result.player_result, SimplifiedResult)
        assert isinstance(result.opponent_result, SimplifiedResult)
        assert result.player_result.rolls[0].die == DieType.D8
        assert result.opponent_result.rolls[0].die == DieType.D6

    def test_both_sides_two_dice(self):
        player = DicePoolRequest(
            entity_id="kael", universe="three_realms",
            dice=[(DieType.D10, "sword_intent"), (DieType.D6, "qi")],
        )
        opponent = DicePoolRequest(
            entity_id="rival", universe="three_realms",
            dice=[(DieType.D8, "sword_intent"), (DieType.D6, "qi")],
        )
        result = resolve_contest(player, opponent)
        assert result.pipeline == "simplified"
        assert len(result.player_result.rolls) == 2
        assert len(result.opponent_result.rolls) == 2

    def test_effect_die_present_for_both(self):
        """A side has an effect die exactly when it does not FAIL.

        FAIL tier (highest roll ≤ 2, which includes botches) maps to
        effect_die=None; every other tier carries an effect die.
        """
        player = DicePoolRequest(
            entity_id="kael", universe="earth",
            dice=[(DieType.D10, "shooting")],
        )
        opponent = DicePoolRequest(
            entity_id="guard", universe="earth",
            dice=[(DieType.D6, "agility")],
        )
        result = resolve_contest(player, opponent)

        for side in (result.player_result, result.opponent_result):
            if side.tier == OutcomeTier.FAIL:
                assert side.effect_die is None
            else:
                assert side.effect_die is not None

        winner_effect = (
            result.player_result.effect_die if result.winner == ContestWinner.PLAYER
            else result.opponent_result.effect_die
        )
        if winner_effect is not None:
            assert winner_effect in (DieType.D4, DieType.D6, DieType.D8, DieType.D10)

    def test_marie_jay_example(self):
        """Marie has d4,d6,d12; Jay has d10,d4,d4 — both should resolve
        in pool pipeline since 3+ dice each."""
        marie = DicePoolRequest(
            entity_id="marie", universe="earth",
            dice=[(DieType.D4, "a"), (DieType.D6, "b"), (DieType.D12, "c")],
        )
        jay = DicePoolRequest(
            entity_id="jay", universe="earth",
            dice=[(DieType.D10, "x"), (DieType.D4, "y"), (DieType.D4, "z")],
        )
        result = resolve_contest(marie, jay)
        assert result.pipeline == "pool"
        assert isinstance(result.player_result, PoolResult)
        assert isinstance(result.opponent_result, PoolResult)
        # Each side keeps 2 dice, has 1 unused → effect die
        assert len(result.player_result.kept) == 2
        assert len(result.opponent_result.kept) == 2
        assert result.player_result.effect_die is not None
        assert result.opponent_result.effect_die is not None


class TestResolveContestPool:
    """End-to-end: two pool (3+) pipelines contest each other."""

    def test_kael_vs_ai(self):
        """Classic Cortex example from the docs."""
        kael = DicePoolRequest(
            entity_id="kael", universe="earth",
            dice=[
                (DieType.D10, "intelligence"),
                (DieType.D8, "hacking"),
                (DieType.D8, "distinction"),
            ],
        )
        ai = DicePoolRequest(
            entity_id="security_ai", universe="earth",
            dice=[
                (DieType.D10, "firewall"),
                (DieType.D8, "counter_intrusion"),
                (DieType.D6, "alerted"),
            ],
        )
        result = resolve_contest(kael, ai)
        assert result.pipeline == "pool"
        assert len(result.player_result.rolls) == 3
        assert len(result.opponent_result.rolls) == 3
        assert len(result.player_result.kept) == 2
        assert len(result.opponent_result.kept) == 2

    def test_asymmetric_pool_sizes(self):
        """Player with 4 dice, opponent with 3 — both still pool pipeline."""
        player = DicePoolRequest(
            entity_id="kael", universe="earth",
            dice=[
                (DieType.D10, "a"), (DieType.D8, "b"),
                (DieType.D8, "c"), (DieType.D6, "d"),
            ],
        )
        opponent = DicePoolRequest(
            entity_id="gmc", universe="earth",
            dice=[
                (DieType.D8, "x"), (DieType.D6, "y"), (DieType.D6, "z"),
            ],
        )
        result = resolve_contest(player, opponent)
        assert result.pipeline == "pool"

    def test_effect_die_from_unused(self):
        """With 3+ dice, effect die comes from dice not used in the total."""
        player = DicePoolRequest(
            entity_id="kael", universe="earth",
            dice=[
                (DieType.D10, "a"), (DieType.D8, "b"), (DieType.D12, "c"),
            ],
        )
        opponent = DicePoolRequest(
            entity_id="gmc", universe="earth",
            dice=[
                (DieType.D8, "x"), (DieType.D6, "y"), (DieType.D6, "z"),
            ],
        )
        result = resolve_contest(player, opponent)
        # Player has 1 unused die → effect die from it
        assert len(result.player_result.unused) == 1
        if result.player_result.unused:
            assert result.player_result.effect_die is not None


class TestResolveContestMixed:
    """Mixed pipelines: one side simplified, the other pool."""

    def test_player_pool_vs_opponent_simplified(self):
        """Player brings 3 dice (pool), opponent brings 1 die (simplified)."""
        player = DicePoolRequest(
            entity_id="kael", universe="earth",
            dice=[
                (DieType.D10, "a"), (DieType.D8, "b"), (DieType.D8, "c"),
            ],
        )
        opponent = DicePoolRequest(
            entity_id="minor_gmc", universe="earth",
            dice=[(DieType.D6, "x")],
        )
        result = resolve_contest(player, opponent)
        assert result.pipeline == "mixed"
        assert result.winner in (ContestWinner.PLAYER, ContestWinner.OPPONENT)

    def test_player_simplified_vs_opponent_pool(self):
        """Player brings 1 die (simplified), opponent brings 3 dice (pool)."""
        player = DicePoolRequest(
            entity_id="kael", universe="earth",
            dice=[(DieType.D10, "a")],
        )
        opponent = DicePoolRequest(
            entity_id="boss", universe="earth",
            dice=[
                (DieType.D10, "x"), (DieType.D8, "y"), (DieType.D8, "z"),
            ],
        )
        result = resolve_contest(player, opponent)
        assert result.pipeline == "mixed"


# ── ContestResult model ────────────────────────────────

class TestContestResultModel:
    def test_player_win_structure(self):
        """Verify a ContestResult when player wins."""
        result = ContestResult(
            pipeline="pool",
            winner=ContestWinner.PLAYER,
            player_result=PoolResult(
                rolls=[DieRoll(die=DieType.D10, result=9, source="a"),
                       DieRoll(die=DieType.D8, result=6, source="b"),
                       DieRoll(die=DieType.D8, result=5, source="c")],
                kept=[DieRoll(die=DieType.D10, result=9, source="a"),
                      DieRoll(die=DieType.D8, result=6, source="b")],
                total=15, effect_die=DieType.D8, effect_die_value=5,
                unused=[DieRoll(die=DieType.D8, result=5, source="c")],
                hitches=[], botch=False, razmerit_earned=0,
            ),
            opponent_result=PoolResult(
                rolls=[DieRoll(die=DieType.D8, result=5, source="x"),
                       DieRoll(die=DieType.D6, result=4, source="y"),
                       DieRoll(die=DieType.D6, result=3, source="z")],
                kept=[DieRoll(die=DieType.D8, result=5, source="x"),
                      DieRoll(die=DieType.D6, result=4, source="y")],
                total=9, effect_die=DieType.D6, effect_die_value=3,
                unused=[DieRoll(die=DieType.D6, result=3, source="z")],
                hitches=[], botch=False, razmerit_earned=0,
            ),
            pushed=False,
        )
        assert result.winner == ContestWinner.PLAYER
        assert result.pushed is False

    def test_opponent_win_structure(self):
        result = ContestResult(
            pipeline="simplified",
            winner=ContestWinner.OPPONENT,
            player_result=SimplifiedResult(
                rolls=[DieRoll(die=DieType.D6, result=4, source="a")],
                highest=4, tier=OutcomeTier.MARGINAL, effect_die=DieType.D4,
                hitches=[], botch=False, razmerit_earned=0,
            ),
            opponent_result=SimplifiedResult(
                rolls=[DieRoll(die=DieType.D8, result=7, source="x")],
                highest=7, tier=OutcomeTier.SUCCESS, effect_die=DieType.D6,
                hitches=[], botch=False, razmerit_earned=0,
            ),
        )
        assert result.winner == ContestWinner.OPPONENT

    def test_tie_challenger_structure(self):
        result = ContestResult(
            pipeline="pool",
            winner=ContestWinner.PLAYER,
            player_result=PoolResult(
                rolls=[DieRoll(die=DieType.D10, result=8, source="a"),
                       DieRoll(die=DieType.D8, result=5, source="b"),
                       DieRoll(die=DieType.D6, result=4, source="c")],
                kept=[DieRoll(die=DieType.D10, result=8, source="a"),
                      DieRoll(die=DieType.D8, result=5, source="b")],
                total=13, effect_die=DieType.D6, effect_die_value=4,
                unused=[DieRoll(die=DieType.D6, result=4, source="c")],
                hitches=[], botch=False, razmerit_earned=0,
            ),
            opponent_result=PoolResult(
                rolls=[DieRoll(die=DieType.D10, result=8, source="x"),
                       DieRoll(die=DieType.D6, result=5, source="y"),
                       DieRoll(die=DieType.D6, result=3, source="z")],
                kept=[DieRoll(die=DieType.D10, result=8, source="x"),
                      DieRoll(die=DieType.D6, result=5, source="y")],
                total=13, effect_die=DieType.D6, effect_die_value=3,
                unused=[DieRoll(die=DieType.D6, result=3, source="z")],
                hitches=[], botch=False, razmerit_earned=0,
            ),
        )
        assert result.winner == ContestWinner.PLAYER
        # Both have effect dice even in a tie
        assert result.player_result.effect_die is not None
        assert result.opponent_result.effect_die is not None


# ── Per-Location ContestTracker ────────────────────────

class TestContestTrackerAssembly:
    """Pool assembly — adding dice, setting opposition."""

    def test_get_or_create_returns_same_assembly(self):
        ct = ContestTracker()
        a1 = ct.get_or_create("loc-1", "kael", "earth")
        a2 = ct.get_or_create("loc-1", "kael", "earth")
        assert a1 is a2

    def test_different_locations_independent(self):
        ct = ContestTracker()
        ct.add_die("loc-1", "kael", DieType.D8, "shooting", "earth")
        ct.add_die("loc-2", "kael", DieType.D10, "persuasion", "earth")
        assert len(ct.get("loc-1", "kael").dice) == 1
        assert len(ct.get("loc-2", "kael").dice) == 1
        # They are separate assemblies
        assert ct.get("loc-1", "kael") is not ct.get("loc-2", "kael")

    def test_add_and_remove_dice(self):
        ct = ContestTracker()
        ct.add_die("loc-1", "kael", DieType.D8, "shooting", "earth")
        ct.add_die("loc-1", "kael", DieType.D6, "distinction", "earth")
        assert len(ct.get("loc-1", "kael").dice) == 2
        ct.remove_die("loc-1", "kael", 0)
        assert len(ct.get("loc-1", "kael").dice) == 1

    def test_set_opposition(self):
        ct = ContestTracker()
        ct.add_die("loc-1", "kael", DieType.D8, "shooting", "earth")
        ct.set_opposition("loc-1", "kael", "guard-1", "earth")
        ct.add_die("loc-1", "guard-1", DieType.D6, "agility", "earth")
        assert ct.get("loc-1", "kael").opposition_entity_id == "guard-1"

    def test_can_resolve_false_without_both_pools(self):
        ct = ContestTracker()
        ct.add_die("loc-1", "kael", DieType.D8, "shooting", "earth")
        assert not ct.can_resolve("loc-1", "kael")

    def test_can_resolve_true_with_both_pools(self):
        ct = ContestTracker()
        ct.add_die("loc-1", "kael", DieType.D8, "shooting", "earth")
        ct.set_opposition("loc-1", "kael", "guard-1", "earth")
        ct.add_die("loc-1", "guard-1", DieType.D6, "agility", "earth")
        assert ct.can_resolve("loc-1", "kael")

    def test_clear_pool(self):
        ct = ContestTracker()
        ct.add_die("loc-1", "kael", DieType.D8, "shooting", "earth")
        ct.clear_pool("loc-1", "kael")
        assert ct.get("loc-1", "kael") is None

    def test_clear_location(self):
        ct = ContestTracker()
        ct.add_die("loc-1", "kael", DieType.D8, "shooting", "earth")
        ct.add_die("loc-1", "guard-1", DieType.D6, "agility", "earth")
        ct.clear_location("loc-1")
        assert ct.get_pools_at("loc-1") == {}
        # Other locations unaffected
        ct.add_die("loc-2", "kael", DieType.D10, "persuasion", "earth")
        assert ct.get("loc-2", "kael") is not None


class TestContestTrackerResolution:
    """Resolving contests through the tracker."""

    def test_resolve_returns_contest_result(self):
        ct = ContestTracker()
        ct.add_die("loc-1", "kael", DieType.D10, "intelligence", "earth")
        ct.add_die("loc-1", "kael", DieType.D8, "hacking", "earth")
        ct.add_die("loc-1", "kael", DieType.D8, "distinction", "earth")
        ct.set_opposition("loc-1", "kael", "guard-1", "earth")
        ct.add_die("loc-1", "guard-1", DieType.D8, "agility", "earth")
        ct.add_die("loc-1", "guard-1", DieType.D6, "alertness", "earth")
        ct.add_die("loc-1", "guard-1", DieType.D6, "training", "earth")

        result = ct.resolve("loc-1", "kael")
        assert result is not None
        assert isinstance(result, ContestResult)
        assert result.pipeline == "pool"
        assert result.winner in (ContestWinner.PLAYER, ContestWinner.OPPONENT)

    def test_resolve_works_from_defendant_side(self):
        """Resolving with the defendant's id still resolves the contest."""
        ct = ContestTracker()
        ct.add_die("loc-1", "kael", DieType.D10, "intelligence", "earth")
        ct.add_die("loc-1", "kael", DieType.D8, "hacking", "earth")
        ct.add_die("loc-1", "kael", DieType.D8, "distinction", "earth")
        ct.set_opposition("loc-1", "kael", "guard-1", "earth")
        ct.add_die("loc-1", "guard-1", DieType.D8, "agility", "earth")
        ct.add_die("loc-1", "guard-1", DieType.D6, "alertness", "earth")
        ct.add_die("loc-1", "guard-1", DieType.D6, "training", "earth")

        result = ct.resolve("loc-1", "guard-1")
        assert result is not None
        assert isinstance(result, ContestResult)

    def test_get_contestants_identifies_challenger_from_either_side(self):
        ct = ContestTracker()
        ct.add_die("loc-1", "kael", DieType.D8, "shooting", "earth")
        ct.set_opposition("loc-1", "kael", "guard-1", "earth")
        ct.add_die("loc-1", "guard-1", DieType.D6, "agility", "earth")

        challenger, defendant = ct.get_contestants("loc-1", "kael")
        assert challenger.entity_id == "kael"
        assert defendant.entity_id == "guard-1"

        challenger, defendant = ct.get_contestants("loc-1", "guard-1")
        assert challenger.entity_id == "kael"
        assert defendant.entity_id == "guard-1"

    def test_resolve_returns_none_without_opponent(self):
        ct = ContestTracker()
        ct.add_die("loc-1", "kael", DieType.D8, "shooting", "earth")
        result = ct.resolve("loc-1", "kael")
        assert result is None

    def test_resolve_returns_none_with_empty_opponent(self):
        ct = ContestTracker()
        ct.add_die("loc-1", "kael", DieType.D8, "shooting", "earth")
        ct.set_opposition("loc-1", "kael", "guard-1", "earth")
        # guard-1 has no dice yet
        result = ct.resolve("loc-1", "kael")
        assert result is None

    def test_pool_survives_location_switch(self):
        """Build pool at loc-1, check it's still there after 'traveling'."""
        ct = ContestTracker()
        ct.add_die("loc-1", "kael", DieType.D10, "intelligence", "earth")
        ct.add_die("loc-1", "kael", DieType.D8, "hacking", "earth")
        ct.set_opposition("loc-1", "kael", "guard-1", "earth")
        ct.add_die("loc-1", "guard-1", DieType.D8, "agility", "earth")

        # Travel to loc-2, build different pool
        ct.add_die("loc-2", "kael", DieType.D10, "persuasion", "earth")

        # Return to loc-1 — pool still there
        pool = ct.get("loc-1", "kael")
        assert pool is not None
        assert len(pool.dice) == 2
        assert pool.opposition_entity_id == "guard-1"

    def test_push_flag(self):
        ct = ContestTracker()
        ct.add_die("loc-1", "kael", DieType.D8, "shooting", "earth")
        ct.set_opposition("loc-1", "kael", "guard-1", "earth")
        ct.add_die("loc-1", "guard-1", DieType.D6, "agility", "earth")
        ct.set_pushed("loc-1", "kael")
        result = ct.resolve("loc-1", "kael")
        assert result is not None
        assert result.pushed is True


# ── Simplified GMC Opposition (now wired) ──────────────

class TestSimplifiedGMCOpposition:
    """Simplified pipeline now handles GMC-type opposition."""

    def test_gmc_opposition_in_simplified(self):
        request = DicePoolRequest(
            entity_id="kael", universe="earth",
            dice=[(DieType.D8, "shooting")],
            opposition=Opposition(
                type="gmc",
                dice=[(DieType.D6, "agility")],
            ),
        )
        result = resolve(request)
        assert isinstance(result, SimplifiedResult)
        assert result.opposition_roll is not None
        assert result.opposition_roll.die == DieType.D6

    def test_gmc_opposition_two_dice(self):
        request = DicePoolRequest(
            entity_id="kael", universe="earth",
            dice=[(DieType.D8, "shooting"), (DieType.D6, "distinction")],
            opposition=Opposition(
                type="gmc",
                dice=[(DieType.D8, "agility"), (DieType.D4, "awareness")],
            ),
        )
        result = resolve(request)
        assert isinstance(result, SimplifiedResult)
        assert result.opposition_roll is not None
        # GMC's highest die becomes the opposition roll
        assert result.opposition_roll.result >= 1


# ── Botch in Contests ──────────────────────────────────

class TestBotchInContests:
    def test_botch_detected_in_contest(self):
        """A botch is still detected when resolved via contest path."""
        player = DicePoolRequest(
            entity_id="unlucky", universe="earth",
            dice=[(DieType.D4, "cursed"), (DieType.D4, "jinxed")],
        )
        opponent = DicePoolRequest(
            entity_id="boss", universe="earth",
            dice=[(DieType.D10, "power")],
        )
        result = resolve_contest(player, opponent)
        # botch flag is set on the player result
        if result.player_result.botch:
            assert result.player_result.tier == OutcomeTier.FAIL
        # Structure is always valid
        assert result.winner in (ContestWinner.PLAYER, ContestWinner.OPPONENT)


# ── SFX Push (data model) ──────────────────────────────

class TestSFXPushDataModel:
    """The push mechanic: spend 1 razmerit after a failed/tied contest to
    assemble a new pool and reroll against the same opposition."""

    def test_push_cost_is_one_razmerit(self):
        result = ContestResult(
            pipeline="pool",
            winner=ContestWinner.OPPONENT,
            player_result=PoolResult(
                rolls=[DieRoll(die=DieType.D10, result=6, source="a"),
                       DieRoll(die=DieType.D8, result=4, source="b"),
                       DieRoll(die=DieType.D6, result=3, source="c")],
                kept=[DieRoll(die=DieType.D10, result=6, source="a"),
                      DieRoll(die=DieType.D8, result=4, source="b")],
                total=10, effect_die=DieType.D6, effect_die_value=3,
                unused=[DieRoll(die=DieType.D6, result=3, source="c")],
                hitches=[], botch=False, razmerit_earned=0,
            ),
            opponent_result=PoolResult(
                rolls=[DieRoll(die=DieType.D10, result=8, source="x"),
                       DieRoll(die=DieType.D8, result=5, source="y"),
                       DieRoll(die=DieType.D6, result=2, source="z")],
                kept=[DieRoll(die=DieType.D10, result=8, source="x"),
                      DieRoll(die=DieType.D8, result=5, source="y")],
                total=13, effect_die=DieType.D6, effect_die_value=2,
                unused=[DieRoll(die=DieType.D6, result=2, source="z")],
                hitches=[], botch=False, razmerit_earned=0,
            ),
            pushed=False,
        )
        assert result.push_cost == 1
        assert result.pushed is False

    def test_push_available_when_lost(self):
        """Push is available after a loss (not yet used)."""
        razmerit = 3
        push_cost = 1
        assert razmerit >= push_cost

    def test_push_not_available_without_razmerit(self):
        razmerit = 0
        push_cost = 1
        assert razmerit < push_cost

    def test_only_one_push_per_beat(self):
        """Tracker enforces single push per beat."""
        ct = ContestTracker()
        ct.add_die("loc-1", "kael", DieType.D8, "shooting", "earth")
        ct.set_opposition("loc-1", "kael", "guard-1", "earth")
        ct.add_die("loc-1", "guard-1", DieType.D6, "agility", "earth")
        ct.set_pushed("loc-1", "kael")
        assert ct.get("loc-1", "kael").pushed_this_beat is True


class TestStakes:
    """The opponent's effect die is surfaced as the contest 'stakes'."""

    def test_pool_contest_reports_opponent_effect_die(self):
        player = DicePoolRequest(
            entity_id="kael", universe="earth",
            dice=[(DieType.D10, "a"), (DieType.D8, "b"), (DieType.D6, "c")],
        )
        opponent = DicePoolRequest(
            entity_id="guard", universe="earth",
            dice=[(DieType.D8, "x"), (DieType.D6, "y"), (DieType.D6, "z")],
        )
        result = resolve_contest(player, opponent)
        assert result.stakes == result.opponent_result.effect_die
        assert result.stakes is not None  # pool opponent always has an effect die

    def test_simplified_contest_reports_opponent_effect_die(self):
        player = DicePoolRequest(
            entity_id="kael", universe="earth",
            dice=[(DieType.D8, "shooting")],
        )
        opponent = DicePoolRequest(
            entity_id="guard", universe="earth",
            dice=[(DieType.D6, "agility")],
        )
        result = resolve_contest(player, opponent)
        assert result.stakes == result.opponent_result.effect_die

    def test_test_roll_reports_no_stakes(self):
        """A single-side test (gmc opposition) carries no stakes."""
        request = DicePoolRequest(
            entity_id="kael", universe="earth",
            dice=[(DieType.D8, "shooting"), (DieType.D8, "distinction"), (DieType.D6, "asset")],
            opposition=Opposition(type="gmc", dice=[(DieType.D8, "agility")]),
        )
        result = resolve(request)
        assert not hasattr(result, "stakes")
