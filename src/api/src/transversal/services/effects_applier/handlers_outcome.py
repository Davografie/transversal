"""Outcome handlers (``modify_outcome``) — the roll's own result, changed after it is set.

These are the only effects that act on a result that already exists. Everything
else in the applier mutates entities or trait instances; an outcome effect
adjusts the *roll* — its effect die, or its outcome tier — and that value lives
in the contest tracker's committed result, so the handler writes it back there.

**Why the endpoint compares once, after these fire:** ``_compare`` flips
initiative when the attacker beats the difficulty, so re-running it is not
idempotent. The set endpoint therefore commits the raw result, fires outcome
effects, and only then compares — so the comparison and its ramifications are
computed from the stepped value exactly once (the human's call: *"re-resolve
after"*).
"""

from __future__ import annotations

from transversal.domain import Effect
from transversal.domain import Entity
from transversal.services.effects_applier.datatypes import (
    AppliedEffect,
    EffectsResult,
)


#: The tier ladder, in order — an outcome step moves one rung up. Kept local
#: because ``OutcomeTier`` is a plain ``str`` enum with no ``step_up`` (unlike
#: ``DieType``), and the order is a game rule rather than an accident of
#: declaration.
_TIER_LADDER = ("fail", "marginal", "success", "exceptional", "perfect")


def _step_tier(tier: str | None) -> str | None:
    """One rung up the outcome ladder, saturating at *perfect*."""
    if not tier:
        return None
    try:
        idx = _TIER_LADDER.index(str(tier))
    except ValueError:
        return None
    return _TIER_LADDER[min(idx + 1, len(_TIER_LADDER) - 1)]


def _committed_of(location_id: str, entity_id: str):
    """This side's committed result, or ``None`` when there is no contest."""
    from transversal.services.contest_tracker import get_contest_tracker

    ct = get_contest_tracker()
    challenger, defendant = ct.get_contestants(location_id, entity_id) if location_id else (None, None)
    if challenger is None and defendant is None:
        # No location on the effect (a non-contest roll): find their contest by
        # scanning, so a mook-location roll still resolves its own result.
        for entry in ct.list_all_contests():
            if entity_id in (entry.get("challenger_id"), entry.get("defendant_id")):
                loc = entry.get("location_id") or ""
                challenger, defendant = ct.get_contestants(loc, entity_id)
                location_id = loc
                break
    if challenger is None and defendant is None:
        return None, None, None
    state = challenger if getattr(challenger, "entity_id", None) == entity_id else defendant
    if state is None or state.committed is None:
        return None, None, None
    return ct, location_id, state


def _apply_step_up_effect(entity, effect: Effect, repo, result: EffectsResult) -> None:
    """Step the roll's effect die up one size.

    Targets the **effect die itself** (the human's call): on a pool roll the
    outcome *tier* is not computed server-side, so the die is the value the table
    actually sees. The committed result is rewritten and re-broadcast by the set
    endpoint, which compares once on the stepped value.
    """
    ct, location_id, state = _committed_of(getattr(entity, "current_location", "") or "", entity.id)
    if ct is None:
        result.applied.append(AppliedEffect(effect, "no committed result to step"))
        return
    committed = state.committed
    before = committed.effect_die
    if before is None:
        result.applied.append(AppliedEffect(effect, "the result has no effect die to step"))
        return
    stepped = before.step_up()
    if stepped == before:
        result.applied.append(AppliedEffect(effect, f"the effect die is already {before.value}"))
        return
    ct.refresh_committed(location_id, state.entity_id,
                         committed.model_copy(update={"effect_die": stepped}))
    result.applied.append(AppliedEffect(
        effect, f"stepped the effect die {before.value} → {stepped.value}"))


def _apply_step_up_outcome(entity, effect: Effect, repo, result: EffectsResult) -> None:
    """Step the roll's outcome tier up one rung.

    A pool roll carries no tier server-side (only a simplified side sends one), so
    this steps the **effect die** there instead — the tier's effect die *is* what
    the rung means (`OutcomeTier.effect_die`), so the visible outcome still moves.
    """
    ct, location_id, state = _committed_of(getattr(entity, "current_location", "") or "", entity.id)
    if ct is None:
        result.applied.append(AppliedEffect(effect, "no committed result to step"))
        return
    committed = state.committed
    if committed.tier:
        stepped = _step_tier(committed.tier.value if hasattr(committed.tier, "value") else committed.tier)
        if stepped is None or stepped == (committed.tier.value if hasattr(committed.tier, "value") else committed.tier):
            result.applied.append(AppliedEffect(effect, f"the outcome is already {committed.tier}"))
            return
        from transversal.domain import OutcomeTier
        ct.refresh_committed(location_id, state.entity_id,
                             committed.model_copy(update={"tier": OutcomeTier(stepped)}))
        result.applied.append(AppliedEffect(effect, f"stepped the outcome to {stepped}"))
        return
    before = committed.effect_die
    if before is None:
        result.applied.append(AppliedEffect(effect, "the result has no outcome to step"))
        return
    stepped = before.step_up()
    if stepped == before:
        result.applied.append(AppliedEffect(effect, f"the effect die is already {before.value}"))
        return
    ct.refresh_committed(location_id, state.entity_id,
                         committed.model_copy(update={"effect_die": stepped}))
    result.applied.append(AppliedEffect(
        effect, f"stepped the outcome's effect die {before.value} → {stepped.value}"))
