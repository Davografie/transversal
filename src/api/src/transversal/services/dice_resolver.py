"""Stateless dice resolver.

Implements both resolution pipelines:
  - Simplified (1-2 dice): take highest, map to outcome tier
  - Dice Pool (3+ dice): keep two highest, add, compare

The resolver is pure — it takes a pool spec and returns a result.
It does not mutate state, apply effects, or touch the database.
"""

import random
import secrets
from typing import Optional

from transversal.domain import (
    ChallengeResult,
    ContestResult,
    ContestWinner,
    DicePoolRequest,
    DieRoll,
    DieSpec,
    DieType,
    Opposition,
    OutcomeTier,
    PoolResult,
    RollKind,
    RollResult,
    SimplifiedResult,
)


def _roll_die(spec: DieSpec) -> DieRoll:
    """Roll a single die using cryptographically secure randomness."""
    return DieRoll(**spec.model_dump(), result=secrets.randbelow(spec.die.max_value) + 1)


def _determine_tier(highest: int) -> OutcomeTier:
    """Map the highest die result to an outcome tier."""
    if highest <= 2:
        return OutcomeTier.FAIL
    elif highest <= 5:
        return OutcomeTier.MARGINAL
    elif highest <= 8:
        return OutcomeTier.SUCCESS
    elif highest <= 11:
        return OutcomeTier.EXCEPTIONAL
    else:
        return OutcomeTier.PERFECT


def _is_botch(rolls: list[DieRoll]) -> bool:
    """A botch occurs when ALL dice show 1."""
    return len(rolls) > 0 and all(r.result == 1 for r in rolls)


def _resolve_challenge(
    effect_die: Optional[DieType],
    challenge_die: DieType,
    success: bool,
) -> ChallengeResult:
    """Compare effect die to challenge die and determine outcome."""
    if not success:
        # Failure: challenge die steps up
        new_die = challenge_die.step_up()
        return ChallengeResult(
            targeted_die=challenge_die,
            effect_die=effect_die,
            outcome="stepped_up" if new_die != challenge_die else "unchanged",
            new_challenge_rating=new_die.value,
        )

    if effect_die is None:
        return ChallengeResult(
            targeted_die=challenge_die,
            effect_die=None,
            outcome="unchanged",
            new_challenge_rating=challenge_die.value,
        )

    # Compare effect die to challenge die
    effect_order = list(DieType)
    challenge_order = list(DieType)

    effect_idx = effect_order.index(effect_die)
    challenge_idx = challenge_order.index(challenge_die)

    if effect_idx > challenge_idx:
        # Effect die is larger → remove challenge die
        return ChallengeResult(
            targeted_die=challenge_die,
            effect_die=effect_die,
            outcome="removed",
            new_challenge_rating=None,
        )
    else:
        # Effect die is equal or smaller → step down challenge die
        new_die = challenge_die.step_down()
        return ChallengeResult(
            targeted_die=challenge_die,
            effect_die=effect_die,
            outcome="stepped_down" if new_die != challenge_die else "unchanged",
            new_challenge_rating=new_die.value,
        )


def _resolve_simplified(request: DicePoolRequest) -> SimplifiedResult:
    """Resolve a simplified pipeline roll (1-2 dice)."""
    rolls = [_roll_die(spec) for spec in request.dice]
    highest = max(r.result for r in rolls)
    tier = _determine_tier(highest)
    hitches = [r for r in rolls if r.result == 1]
    botch = _is_botch(rolls)
    razmerit_earned = len(hitches)  # 1 razmerit per hitch

    # Opposition roll (GMC, challenge, or static difficulty)
    opposition_roll = None
    opposition_rolls: list[DieRoll] = []
    opposition_total: Optional[int] = None
    challenge_result = None

    if request.opposition:
        if request.opposition.type == "gmc":
            # Simplified GMC contest: roll GMC's dice, take highest
            opp_rolls = [_roll_die(spec) for spec in request.opposition.dice]
            opposition_rolls = opp_rolls
            if opp_rolls:
                opposition_roll = max(opp_rolls, key=lambda r: r.result)

        elif request.opposition.type == "challenge" and request.opposition.challenge_die:
            opp_die = _roll_die(DieSpec(die=request.opposition.challenge_die, source_kind="challenge", label="challenge"))
            opposition_roll = opp_die
            opposition_rolls = [opp_die]

            # The player's highest must beat the challenge roll's result
            diff = highest - opp_die.result

            if diff <= 0:
                success = False
                tier = OutcomeTier.FAIL
            else:
                success = True
                if diff <= 2:
                    tier = OutcomeTier.MARGINAL
                elif diff <= 5:
                    tier = OutcomeTier.SUCCESS
                elif diff <= 8:
                    tier = OutcomeTier.EXCEPTIONAL
                else:
                    tier = OutcomeTier.PERFECT

            challenge_result = _resolve_challenge(
                effect_die=tier.effect_die,
                challenge_die=request.opposition.challenge_die,
                success=success,
            )
            razmerit_earned = len(hitches)

        elif request.opposition.type == "static_difficulty" and request.opposition.static_difficulty is not None:
            opposition_total = request.opposition.static_difficulty

    return SimplifiedResult(
        kind=request.kind,
        rolls=rolls,
        highest=highest,
        tier=tier,
        effect_die=tier.effect_die,
        hitches=hitches,
        botch=botch,
        opposition_roll=opposition_roll,
        opposition_total=opposition_total,
        challenge_result=challenge_result,
        razmerit_earned=razmerit_earned,
    )


def _resolve_pool(request: DicePoolRequest) -> PoolResult:
    """Resolve a dice pool pipeline roll (3+ dice, Cortex Prime)."""
    rolls = [_roll_die(spec) for spec in request.dice]
    hitches = [r for r in rolls if r.result == 1]
    botch = _is_botch(rolls)
    razmerit_earned = len(hitches)

    # Sort by result descending; keep two highest
    sorted_rolls = sorted(rolls, key=lambda r: r.result, reverse=True)
    kept = sorted_rolls[:2]
    total = sum(r.result for r in kept)
    unused = sorted_rolls[2:]

    # Effect die: choose from unused dice, preferring largest die type
    if unused:
        # Pick the largest die type from unused as effect die
        effect_roll = max(unused, key=lambda r: r.die.max_value)
        effect_die = effect_roll.die
        effect_die_value = effect_roll.result
    else:
        effect_die = DieType.D4  # default
        effect_die_value = None

    # Opposition
    opposition_rolls: list[DieRoll] = []
    opposition_total: Optional[int] = None
    challenge_result = None

    if request.opposition:
        if request.opposition.type == "gmc":
            opp_rolls = [_roll_die(spec) for spec in request.opposition.dice]
            opposition_rolls = opp_rolls
            opp_sorted = sorted(opp_rolls, key=lambda r: r.result, reverse=True)
            if len(opp_sorted) >= 2:
                opposition_total = sum(r.result for r in opp_sorted[:2])
            elif opp_sorted:
                opposition_total = opp_sorted[0].result

        elif request.opposition.type == "challenge" and request.opposition.challenge_die:
            opp_die = _roll_die(DieSpec(die=request.opposition.challenge_die, source_kind="challenge", label="challenge"))
            opposition_rolls = [opp_die]
            opposition_total = opp_die.result

            success = total > opposition_total
            challenge_result = _resolve_challenge(
                effect_die=effect_die,
                challenge_die=request.opposition.challenge_die,
                success=success,
            )

        elif request.opposition.type == "static_difficulty" and request.opposition.static_difficulty is not None:
            opposition_total = request.opposition.static_difficulty

    return PoolResult(
        kind=request.kind,
        rolls=rolls,
        kept=kept,
        total=total,
        effect_die=effect_die,
        effect_die_value=effect_die_value,
        unused=unused,
        hitches=hitches,
        botch=botch,
        opposition_rolls=opposition_rolls,
        opposition_total=opposition_total,
        challenge_result=challenge_result,
        razmerit_earned=razmerit_earned,
    )


def resolve(request: DicePoolRequest) -> RollResult:
    """Route to the correct pipeline based on pool size.

    Pool size is determined AFTER all modifiers (SFX, razmerit spends).
    The caller must assemble the final dice list before calling resolve().
    """
    pool_size = len(request.dice)

    if pool_size <= 2:
        return _resolve_simplified(request)
    else:
        return _resolve_pool(request)


# ── Contest Resolution ──────────────────────────────────


def _resolve_contest_winner(
    player_tier: OutcomeTier,
    opponent_tier: OutcomeTier,
    player_highest: int,
    opponent_highest: int,
) -> ContestWinner:
    """Determine the winner of a simplified contest.

    Priority:
      1. Higher outcome tier wins
      2. Same tier → higher die value wins
      3. Same tier + same value → challenger (initiator) wins
    """
    tier_order = list(OutcomeTier)
    player_tier_idx = tier_order.index(player_tier)
    opponent_tier_idx = tier_order.index(opponent_tier)

    if player_tier_idx > opponent_tier_idx:
        return ContestWinner.PLAYER
    elif opponent_tier_idx > player_tier_idx:
        return ContestWinner.OPPONENT
    elif player_highest > opponent_highest:
        return ContestWinner.PLAYER
    elif opponent_highest > player_highest:
        return ContestWinner.OPPONENT
    else:
        return ContestWinner.PLAYER  # tie favors the initiator


def _resolve_contest_winner_pool(
    player_total: int,
    opponent_total: int,
) -> ContestWinner:
    """Determine the winner of a dice pool contest.

    Higher total wins. Tie goes to the challenger (initiator).
    """
    if player_total > opponent_total:
        return ContestWinner.PLAYER
    elif opponent_total > player_total:
        return ContestWinner.OPPONENT
    else:
        return ContestWinner.PLAYER  # tie favors the initiator


def resolve_contest(
    player: DicePoolRequest,
    opponent: DicePoolRequest,
) -> ContestResult:
    """Resolve a head-to-head contest between two sides.

    Each side is resolved through their own pipeline (determined by their
    pool size).  The resolver then compares the two results and declares
    a winner per Cortex Prime rules:

      - Simplified vs Simplified: compare outcome tiers
      - Pool vs Pool: compare totals
      - Mixed: the pool side uses its total; the simplified side's
        highest die is treated as a single-die total for comparison

    Ties favor the challenger (initiator, the first argument).
    """
    player_result = resolve(player.model_copy(update={"kind": RollKind.CONTEST}))
    opponent_result = resolve(opponent.model_copy(update={"kind": RollKind.CONTEST}))

    # Determine which pipelines were used
    player_is_pool = isinstance(player_result, PoolResult)
    opponent_is_pool = isinstance(opponent_result, PoolResult)

    if player_is_pool and opponent_is_pool:
        # Both pool → compare totals
        winner = _resolve_contest_winner_pool(
            player_result.total,
            opponent_result.total,
        )
        pipeline = "pool"

    elif not player_is_pool and not opponent_is_pool:
        # Both simplified → compare tiers + values
        winner = _resolve_contest_winner(
            player_result.tier,
            opponent_result.tier,
            player_result.highest,
            opponent_result.highest,
        )
        pipeline = "simplified"

    elif player_is_pool:
        # Player is pool, opponent is simplified
        # Compare player's total to opponent's highest die
        opp_total = opponent_result.highest
        winner = _resolve_contest_winner_pool(player_result.total, opp_total)
        pipeline = "mixed"

    else:
        # Player is simplified, opponent is pool
        player_total = player_result.highest
        winner = _resolve_contest_winner_pool(
            player_total,
            opponent_result.total,
        )
        pipeline = "mixed"

    return ContestResult(
        pipeline=pipeline,
        kind=RollKind.CONTEST,
        winner=winner,
        stakes=opponent_result.effect_die,
        player_result=player_result,
        opponent_result=opponent_result,
    )
