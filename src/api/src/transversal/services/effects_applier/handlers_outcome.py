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


def _apply_start_contest(entity, effect: Effect, repo, result: EffectsResult) -> None:
    """Put the subject and the effect's target into a contest (B105).

    The **challenger is the subject** — the entity the effect was applied to,
    which the ``entity``/``entity_spec`` machinery may have fanned out to someone
    other than the actor — and the **opponent is the target**. This is the same
    shape the ``contest_win`` conditions read back (the challenger is the side
    carrying ``opposition_entity_id``), so a rule that starts a contest can react
    to its own result.

    Both gates the REST challenge route applies are honoured here too: a
    **targeting ban** (the give-in ban exists precisely so the loser cannot
    re-challenge, and an SFX may not route around it) and the need for a
    **location** (a contest is per-location state; an entity with nowhere to be
    has no contest to be in). Every refusal is reported as an applied-effect
    note rather than raised — an unplaceable challenge should not abort the rest
    of a rule's effects.
    """
    from transversal.services.effects_applier.targeting import _effect_subject, _resolve_target, _track_subject
    from transversal.services.targeting_bans import has_targeting_ban

    subject = _effect_subject(entity, effect, result, repo)
    if subject is None:
        return
    _track_subject(result, entity, subject)

    opponent_id = _resolve_target(subject, effect, result, repo)
    if not opponent_id:
        result.applied.append(AppliedEffect(effect, "no opponent named for the contest"))
        return
    if opponent_id == subject.id:
        result.applied.append(AppliedEffect(effect, "an entity cannot contest itself"))
        return
    if has_targeting_ban(subject, opponent_id):
        result.applied.append(AppliedEffect(
            effect, f"{subject.name or subject.id} cannot target {opponent_id} yet"))
        return
    if repo.get_entity(opponent_id) is None:
        result.applied.append(AppliedEffect(effect, f"no entity {opponent_id} to contest"))
        return
    location_id = subject.current_location or ""
    if not location_id:
        result.applied.append(AppliedEffect(
            effect, f"{subject.name or subject.id} has no location to contest at"))
        return

    from transversal.services.contest_tracker import start_contest

    start_contest(location_id, subject.id, opponent_id, subject.current_universe or "")
    result.applied.append(AppliedEffect(
        effect, f"contest with {opponent_id} at {location_id}"))
