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
    CommittedResult,
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
    result = secrets.randbelow(spec.die.max_value) + 1
    return DieRoll(**spec.model_dump(), result=result, tier=determine_tier(result))


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


def determine_tier(highest: int) -> OutcomeTier:
    """Public alias for the simplified-pipeline tier mapping."""
    return _determine_tier(highest)


def _is_botch(rolls: list[DieRoll]) -> bool:
    """A botch occurs when ALL dice show 1."""
    return len(rolls) > 0 and all(r.result == 1 for r in rolls)


# ── Decomposed resolution callables (P2.10d G5) ──────
#
# The only step that should be automatic is rolling. Everything else — hitch
# detection, total selection, effect-die selection, comparison — is exposed as
# a pure callable so the MCP (and the client) can drive resolution step by
# step instead of relying on the monolithic ``resolve()``.


def roll_dice(specs: list[DieSpec]) -> list[DieRoll]:
    """Roll every die in a pool, returning one ``DieRoll`` per die."""
    return [_roll_die(spec) for spec in specs]


def detect_hitches(rolls: list[DieRoll]) -> list[DieRoll]:
    """Return the dice that rolled a 1 (hitches)."""
    return [r for r in rolls if r.result == 1]


def is_botch(rolls: list[DieRoll]) -> bool:
    """A botch occurs when every die rolled a 1."""
    return _is_botch(rolls)


def pick_total(rolls: list[DieRoll], indices: list[int]) -> int:
    """Sum the results of the dice at ``indices`` (the chosen total)."""
    return sum(rolls[i].result for i in indices)


def pick_effect_die(
    rolls: list[DieRoll],
    total_indices: list[int],
    hitches_apply: bool = True,
) -> Optional[DieRoll]:
    """Choose the effect die from dice not used in the total.

    Prefers the largest die type among eligible leftovers; hitches are
    ineligible. Ties in die type prefer the higher rolled result (matching the
    auto-resolve ordering). Returns the chosen roll, or ``None`` when nothing
    remains — callers fall back to ``d4``.
    """
    used = set(total_indices)
    candidates = [r for i, r in enumerate(rolls) if i not in used]
    if hitches_apply:
        candidates = [r for r in candidates if r.result != 1]
    if not candidates:
        return None
    candidates = sorted(candidates, key=lambda r: r.result, reverse=True)
    return max(candidates, key=lambda r: r.die.max_value)


def _pick_effect_dice(
    rolls: list[DieRoll],
    total_indices: list[int],
    count: int,
    hitches_apply: bool = True,
) -> list[DieRoll]:
    """Choose up to ``count`` effect dice from dice not used in the total.

    Prefers the largest die type; ties prefer the higher rolled result (matching
    ``pick_effect_die``). Returns at most ``count`` rolls in preference order.
    """
    if count <= 0:
        return []
    used = set(total_indices)
    candidates = [r for i, r in enumerate(rolls) if i not in used]
    if hitches_apply:
        candidates = [r for r in candidates if r.result != 1]
    if not candidates:
        return []
    candidates = sorted(candidates, key=lambda r: (r.die.max_value, r.result), reverse=True)
    return candidates[:count]


def compare_totals(player_total: int, opponent_total: int) -> ContestWinner:
    """Higher total wins a contest; a tie favors the challenger (PLAYER)."""
    if player_total > opponent_total:
        return ContestWinner.PLAYER
    if opponent_total > player_total:
        return ContestWinner.OPPONENT
    return ContestWinner.PLAYER


def effect_die_beats(effect_die: DieType, target_die: DieType) -> bool:
    """True when the effect die is strictly larger than the target die.

    The single definition of the effect-die comparison, shared by the challenge
    pipeline (which steps a challenge die *down*) and the two comparison effect
    actions — ``reduce_by_effect`` (removes when it beats) and
    ``increase_by_effect`` (sets when it beats).
    """
    order = list(DieType)
    return order.index(effect_die) > order.index(target_die)


def compare_effect_die(effect_die: DieType, target_die: DieType) -> str:
    """The shared effect-die-vs-target-die rule.

    Returns ``"remove"`` when the effect die is strictly larger, else
    ``"step_down"``. Used by challenge resolution and the ``reduce_by_effect``
    effect action so both apply the same comparison.
    """
    return "remove" if effect_die_beats(effect_die, target_die) else "step_down"


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

    # Compare effect die to challenge die (shared helper).
    if compare_effect_die(effect_die, challenge_die) == "remove":
        # Effect die is larger → remove challenge die
        return ChallengeResult(
            targeted_die=challenge_die,
            effect_die=effect_die,
            outcome="removed",
            new_challenge_rating=None,
        )
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
    rolls = roll_dice(request.dice)
    highest = max(r.result for r in rolls)
    tier = _determine_tier(highest)
    hitches = detect_hitches(rolls) if request.hitches_apply else []
    botch = is_botch(rolls) if request.hitches_apply else False
    hitches_count = len(hitches)  # buyable count; no auto-earn

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
            hitches_count = len(hitches)

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
        hitches_count=hitches_count,
    )


def _resolve_pool(request: DicePoolRequest) -> PoolResult:
    """Resolve a dice pool pipeline roll (3+ dice, Cortex Prime).

    Resource dice are rolled as a separate pool: only the highest result is
    added to the total.  Main dice keep the standard keep-two/effect model.
    """
    main_specs = [d for d in request.dice if not d.resource]
    resource_specs = [d for d in request.dice if d.resource]

    main_rolls = roll_dice(main_specs)
    resource_rolls = roll_dice(resource_specs)
    # Only the highest non-hitch resource die applies — a rolled 1 is a hitch
    # and doesn't count toward the total (the same rule as every other die).
    eligible_resource = (
        [r for r in resource_rolls if r.result != 1]
        if request.hitches_apply else resource_rolls
    )
    resource_kept = max(eligible_resource, key=lambda r: r.result) if eligible_resource else None

    # Hitch/botch detection sees every rolled die (main + resource).
    all_rolls = main_rolls + resource_rolls
    hitches = detect_hitches(all_rolls) if request.hitches_apply else []
    botch = is_botch(all_rolls) if request.hitches_apply else False
    hitches_count = len(hitches)

    # Keep the highest MAIN dice for the total (base 2 + bonus); the rest unused.
    keep_count = min(len(main_rolls), 2 + max(0, request.total_dice_bonus))
    order = sorted(range(len(main_rolls)), key=lambda i: main_rolls[i].result, reverse=True)
    kept_indices = order[:keep_count]
    kept = [main_rolls[i] for i in kept_indices]
    total = pick_total(main_rolls, kept_indices) + (resource_kept.result if resource_kept else 0)
    unused = [main_rolls[i] for i in order[keep_count:]]

    # Effect dice: choose from unused MAIN dice (resource dice are ineligible).
    # Base 1 + bonus; the primary (highest) stays the single ``effect_die``.
    effect_count = 1 + max(0, request.effect_dice_bonus)
    effect_rolls = _pick_effect_dice(main_rolls, kept_indices, effect_count, request.hitches_apply)
    primary_effect = effect_rolls[0] if effect_rolls else None
    effect_die = primary_effect.die if primary_effect else DieType.D4
    effect_die_value = primary_effect.result if primary_effect else None

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
        rolls=all_rolls,
        kept=kept,
        total=total,
        resource_rolls=resource_rolls,
        resource_kept=resource_kept,
        effect_die=effect_die,
        effect_die_value=effect_die_value,
        effect_dice=list(effect_rolls),
        unused=unused,
        hitches=hitches,
        botch=botch,
        opposition_rolls=opposition_rolls,
        opposition_total=opposition_total,
        challenge_result=challenge_result,
        hitches_count=hitches_count,
    )


def resolve(request: DicePoolRequest) -> RollResult:
    """Route to the correct pipeline based on pool size.

    Pool size is determined AFTER all modifiers (SFX, razmerit spends).
    The caller must assemble the final dice list before calling resolve().

    A ``pipeline`` hint overrides the size heuristic — used by the GM's
    difficulty roll, which must keep-and-sum even when the opposition pool
    is only two dice.
    """
    if request.pipeline == "pool":
        return _resolve_pool(request)
    if request.pipeline == "simplified":
        return _resolve_simplified(request)

    pool_size = len(request.dice)
    has_resource = any(d.resource for d in request.dice)

    # Resource dice only make sense in a keep-and-sum context — force the
    # pool pipeline so the highest resource die can be added to the total.
    if pool_size <= 2 and not has_resource:
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
    return compare_totals(player_total, opponent_total)


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
        player_result=player_result,
        opponent_result=opponent_result,
    )


def compare_committed(
    challenger: CommittedResult,
    defendant: CommittedResult,
) -> ContestWinner:
    """Compare two committed contest results and declare a winner.

    No dice are rolled — both sides already rolled and picked on their own
    clients.  Ties favor the challenger (initiator).
    """
    challenger_pool = challenger.pipeline == "pool"
    defendant_pool = defendant.pipeline == "pool"

    if challenger_pool and defendant_pool:
        return _resolve_contest_winner_pool(challenger.total, defendant.total)
    if not challenger_pool and not defendant_pool:
        return _resolve_contest_winner(
            challenger.tier or OutcomeTier.FAIL,
            defendant.tier or OutcomeTier.FAIL,
            challenger.total,
            defendant.total,
        )
    # Mixed: the simplified side's highest is already stored in ``total``.
    return _resolve_contest_winner_pool(challenger.total, defendant.total)
