"""Change a Die — one family, two homes for a die.

A die lives in a trait instance's *rating* or in an assembled *pool*, and the
effect's target says which one:

- ``rating:<index>:<ts_id>`` — the index comes **first** because a traitsetting id
  contains colons (``kael:spiritual-power``), so the tail is the only
  unambiguous place to put it;
- ``die:<location>:<owner>:<index>`` — a pool die has no id of its own, so it is
  named by where it sits.

**One rule, two appliers.** :func:`_plan_change` turns a verb into one of three
outcomes — the die resized, the die gone, or N copies of it — and both homes apply
that outcome with their own plumbing (a list of ``DieType`` vs a list of pool
dicts). So "step up" cannot come to mean two different things.

Where a change *lands* is what it means. A rating is a fact about the character,
so the change persists and can carry a duration; the undo restores the whole prior
dice list, recorded here, because counts and the d4 floor mean the naive inverse
of "step up 2" is not "step down 2". A pool is rebuilt every roll, so the change
lasts the roll and its undo only matters inside a manual activation's take-back
window.
"""

from __future__ import annotations

from dataclasses import dataclass

from transversal.domain import DieType
from transversal.domain import Effect
from transversal.domain.dice import step_die
from transversal.services.effects_applier.datatypes import (
    AppliedEffect,
)
from transversal.services.effects_applier.handlers_pools import (
    _parse_die_ref,
)
from transversal.services.effects_applier.reverts import (
    _queue_entity_revert,
    _queue_trait_revert,
)
from transversal.services.effects_applier.trait_helpers import (
    _die_opt,
)

_DIE_STEPS = ("d4", "d6", "d8", "d10", "d12")


@dataclass(frozen=True)
class DieChange:
    """What a verb does to one die — the shape both homes apply.

    ``copies`` is how many dice the result is: 1 for a resize, N+1 for a double or
    a split (the verb's count plus the die it came from), 0 for a removal.
    """
    die: DieType | None
    copies: int = 1
    note: str = ""


def _plan_change(die: DieType | None, verb: str, effect: Effect,
                 count: int) -> tuple[DieChange | None, str]:
    """The one rule: a verb, a die, and the result. ``(None, reason)`` to refuse.

    ``die`` is None for an empty rating — a valid state, where stepping up (or
    setting) *restores* a die rather than failing. Reachable whenever a reference
    outlives the die it named (a binding snapshotted before a change removed it).
    """
    if die is None:
        if verb == "step_up":
            restored = step_die(None, count)
            return DieChange(restored, 1, f"restored {restored.value} to an empty rating"), ""
        if verb == "set":
            new = _die_opt(effect.result)
            if new is None:
                return None, f"not a die rating: {effect.result!r}"
            return DieChange(new, 1, f"set an empty rating to {new.value}"), ""
        return None, f"there is no die to {verb}"
    if verb == "set":
        new = _die_opt(effect.result)
        if new is None:
            return None, f"not a die rating: {effect.result!r}"
        return DieChange(new, 1, f"set {die.value} → {new.value}"), ""
    if verb in ("step_up", "step_down"):
        moved = step_die(die, count if verb == "step_up" else -count)
        if moved is None:
            # A d4 stepped down is gone — the rating keeps its other dice.
            return DieChange(None, 0, f"{die.value} stepped down off the ladder"), ""
        if moved == die:
            return DieChange(die, 1, f"{die.value} is already at the limit"), ""
        return DieChange(moved, 1, f"{die.value} → {moved.value}"), ""
    if verb == "double":
        return DieChange(die, count + 1, f"{die.value} → {count + 1}{die.value}"), ""
    if verb == "split":
        smaller = step_die(die, -1)
        if smaller is None:
            return None, f"a {die.value} is already the smallest die and cannot be split"
        return DieChange(smaller, count + 1, f"{die.value} → {count + 1}{smaller.value}"), ""
    if verb == "remove":
        return DieChange(None, 0, f"removed {die.value}"), ""
    if verb in ("raise_by_effect", "lower_by_effect"):
        # The reference is the *effect die* rather than a number — the same
        # comparison the challenge pipeline reads (`effect_die_beats`), so an
        # effect die that beats a die removes it, and one that does not moves it
        # a single step.
        from transversal.services.dice_resolver import effect_die_beats

        effect_die = _die_opt((effect.context or {}).get("effect_die"))
        if effect_die is None:
            return None, "no effect die to compare"
        beats = effect_die_beats(effect_die, die)
        why = (f"the effect die {effect_die.value} beats {die.value}" if beats
               else f"the effect die {effect_die.value} does not beat {die.value}")
        if verb == "raise_by_effect":
            if beats:
                return DieChange(effect_die, 1, f"set {die.value} → {effect_die.value} ({why})"), ""
            moved = step_die(die, 1)
            if moved == die:
                return DieChange(die, 1, f"{die.value} is already at the limit ({why})"), ""
            return DieChange(moved, 1, f"{die.value} → {moved.value} ({why})"), ""
        if beats:
            return DieChange(None, 0, f"removed {die.value} ({why})"), ""
        moved = step_die(die, -1)
        if moved is None:
            return DieChange(None, 0, f"{die.value} stepped down off the ladder ({why})"), ""
        return DieChange(moved, 1, f"{die.value} → {moved.value} ({why})"), ""
    return None, f"unknown change-die verb {verb!r}"


def _count(effect: Effect) -> int:
    """How many steps / extra dice this change asks for (context ``count``)."""
    try:
        return max(int((effect.context or {}).get("count") or 1), 1)
    except (TypeError, ValueError):
        return 1


def _parse_rating_ref(target: str) -> tuple[int, str] | None:
    """``rating:<index>:<ts_id>`` → ``(index, ts_id)``, or None if it isn't one.

    The index is split off the *front* because a traitsetting id contains colons
    (``kael:spiritual-power``) — the mirror of the pool's positional reference.
    """
    parts = (target or "").strip().split(":", 2)
    if len(parts) != 3 or parts[0] != "rating":
        return None
    try:
        return int(parts[1]), parts[2]
    except ValueError:
        return None


def _highest_trait_die(pool: list[dict]) -> int | None:
    """Index of the highest-rated die that came from a trait (the default target).

    ``highest_trait_die`` is a *strategy keyword*, not a thing: it has to be given
    a meaning, and this is the plain reading of its name. A specific die is named
    with a targeting path instead.
    """
    best, best_i = -1, None
    for i, die in enumerate(pool):
        if not die.get("ts_id") and not die.get("source_id"):
            continue
        try:
            rating = _DIE_STEPS.index((die.get("die") or "").strip())
        except ValueError:
            continue
        if rating > best:
            best, best_i = rating, i
    return best_i


# ── The two homes ──────────────────────────────────────────────

def _apply_rating_change(entity, effect: Effect, repo, result, index: int,
                         ts_id: str, verb: str) -> None:
    """Change one die of a trait instance's rating — a fact about the character."""
    ts = repo.get_traitsetting(ts_id) if repo else None
    if ts is None:
        result.applied.append(AppliedEffect(effect, f"no trait instance {ts_id}"))
        return
    dice = list(ts.dice or [])
    if not dice and index == 0:
        # An empty rating is a legal trait; step up/set restore a die. The ref can
        # still arrive (a binding taken before the dice were removed).
        change, reason = _plan_change(None, verb, effect, _count(effect))
        if change is None:
            result.applied.append(AppliedEffect(effect, reason))
            return
        ts.dice = [change.die]
        result.updated_trait_settings.append(ts)
        result.applied.append(AppliedEffect(effect, f"{change.note} in {ts_id}", ts.id))
        _queue_trait_revert(repo, ts, effect, context_extra={"prior_dice": []})
        return
    if index < 0 or index >= len(dice):
        result.applied.append(AppliedEffect(
            effect, f"no die {index} in {ts_id}'s rating ({len(dice)} dice)"))
        return
    change, reason = _plan_change(dice[index], verb, effect, _count(effect))
    if change is None:
        result.applied.append(AppliedEffect(effect, reason))
        return
    before = [d.value for d in dice]
    if change.copies == 0:
        dice.pop(index)
    elif change.copies > 1:
        dice[index:index + 1] = [change.die] * change.copies
    else:
        dice[index] = change.die
    ts.dice = dice
    result.updated_trait_settings.append(ts)
    result.applied.append(AppliedEffect(effect, f"{change.note} in {ts_id}'s rating", ts.id))
    # The undo restores the whole list: with counts and the d4 floor, the inverse
    # of a change is not a change back. An empty list is a legal value.
    _queue_trait_revert(repo, ts, effect, context_extra={"prior_dice": before})


def _apply_pool_change(entity, effect: Effect, repo, result, target: str, verb: str) -> None:
    """Change a die in an assembled pool — transient, rebuilt every roll."""
    from transversal.services.contest_tracker import broadcast_pool_change
    from transversal.services.scene_state import get_scene_store

    ref = _parse_die_ref(target)
    if ref is not None:
        location_id, owner_id, index = ref
    elif (target or "").strip() == "highest_trait_die":
        location_id = getattr(entity, "current_location", "") or ""
        owner_id = getattr(entity, "id", "") or ""
        index = _highest_trait_die(get_scene_store().get_pool(location_id, owner_id)) if location_id else None
        if index is None:
            result.applied.append(AppliedEffect(effect, "no trait die to change"))
            return
    else:
        result.applied.append(AppliedEffect(effect, f"die target not resolved: {target!r}"))
        return

    store = get_scene_store()
    pool = store.get_pool(location_id, owner_id)
    if index < 0 or index >= len(pool):
        result.applied.append(AppliedEffect(
            effect, f"no die at {target} (pool has {len(pool)})"))
        return

    before = pool[index].get("die") or ""
    die = _die_opt(before)
    if die is None:
        result.applied.append(AppliedEffect(effect, f"not a die in the pool: {before!r}"))
        return
    change, reason = _plan_change(die, verb, effect, _count(effect))
    if change is None:
        result.applied.append(AppliedEffect(effect, reason))
        return

    template = pool[index]
    if change.copies == 0:
        rebuilt = pool[:index] + pool[index + 1:]
    else:
        rebuilt = (pool[:index]
                   + [{**template, "die": change.die.value}] * change.copies
                   + pool[index + 1:])
    store.save_pool(location_id, owner_id, rebuilt)
    broadcast_pool_change(location_id, owner_id, dice=rebuilt, phase="adding")
    result.applied.append(AppliedEffect(effect, f"{change.note} in {owner_id}'s pool"))
    # Booked against the pool's *owner*, not the actor: a cross-entity change (the
    # opponent's die, reached by a path) must not dissolve on the actor's roll.
    owner = _owner_entity(repo, owner_id)
    if owner is not None:
        _queue_entity_revert(repo, owner, effect, context_extra={"prior_rating": before})


def _owner_entity(repo, owner_id: str):
    getter = getattr(repo, "get_entity", None) if repo else None
    return getter(owner_id) if getter else None


def _apply_change(entity, effect: Effect, repo, result, verb: str) -> None:
    """Dispatch a change-die effect to whichever home the target names."""
    target = (effect.target or "").strip()
    rating = _parse_rating_ref(target)
    if rating is not None:
        index, ts_id = rating
        _apply_rating_change(entity, effect, repo, result, index, ts_id, verb)
        return
    _apply_pool_change(entity, effect, repo, result, target, verb)


def _apply_restore_die(entity, effect: Effect, repo, result) -> None:
    """Undo a change, from what the forward handler recorded.

    A rating restores its **whole** prior list (one change can add, remove or
    resize several dice); a pool die restores its prior size. Recorded rather than
    recomputed, because the inverse of a counted change is not that change
    reversed — and because the dice may have shifted since.
    """
    context = effect.context or {}
    rating = _parse_rating_ref(effect.target or "")
    if rating is not None and "prior_dice" in context:
        _, ts_id = rating
        ts = repo.get_traitsetting(ts_id) if repo else None
        if ts is None:
            result.applied.append(AppliedEffect(effect, f"no trait instance {ts_id} to restore"))
            return
        ts.dice = [DieType(d) for d in (context.get("prior_dice") or [])]
        result.updated_trait_settings.append(ts)
        result.applied.append(AppliedEffect(effect, f"restored {ts_id}'s rating", ts.id))
        return

    prior = context.get("prior_rating")
    if prior is None:
        result.applied.append(AppliedEffect(effect, "nothing recorded to restore"))
        return
    from transversal.services.contest_tracker import broadcast_pool_change
    from transversal.services.scene_state import get_scene_store

    ref = _parse_die_ref(effect.target or "")
    if ref is None:
        result.applied.append(AppliedEffect(effect, f"die target not resolved: {effect.target!r}"))
        return
    location_id, owner_id, index = ref
    store = get_scene_store()
    pool = store.get_pool(location_id, owner_id)
    if index < 0 or index >= len(pool):
        result.applied.append(AppliedEffect(effect, f"no die at {effect.target} to restore"))
        return
    pool[index] = {**pool[index], "die": prior}
    store.save_pool(location_id, owner_id, pool)
    broadcast_pool_change(location_id, owner_id, dice=pool, phase="adding")
    result.applied.append(AppliedEffect(effect, f"restored {prior} in {owner_id}'s pool"))


# ── One wrapper per verb (the registry's dispatch keys) ────────

def _apply_change_set(entity, effect, repo, result):
    _apply_change(entity, effect, repo, result, "set")


def _apply_change_step_up(entity, effect, repo, result):
    _apply_change(entity, effect, repo, result, "step_up")


def _apply_change_step_down(entity, effect, repo, result):
    _apply_change(entity, effect, repo, result, "step_down")


def _apply_change_double(entity, effect, repo, result):
    _apply_change(entity, effect, repo, result, "double")


def _apply_change_split(entity, effect, repo, result):
    _apply_change(entity, effect, repo, result, "split")


def _apply_change_remove(entity, effect, repo, result):
    _apply_change(entity, effect, repo, result, "remove")
