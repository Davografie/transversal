"""Handlers pools — split out of src/api/src/transversal/services/effects_applier.py."""

from transversal.domain import DieType
from transversal.domain import TraitSetSetting
from typing import Optional
from transversal.services.effects_applier.datatypes import (
    AppliedEffect,
)
from transversal.services.effects_applier.reverts import (
    _queue_entity_revert,
)
from transversal.services.effects_applier.targeting import (
    _effect_subject,
    _resolve_target,
    _track_subject,
)


def _find_traitsetsetting(entity_id: str, traitset_id: str, repo) -> Optional[TraitSetSetting]:
    for tss in repo.get_traitsetsettings_for_entity(entity_id):
        if tss.traitset_id == traitset_id and tss.from_type == "entity":
            return tss
    return None

def _apply_set_traitset_limit(entity, effect, repo, result):
    """Override how many traits this entity can hold in a trait set.

    ``result`` is the new limit (integer). Empty result clears the override.
    Duration-driven reverts restore the prior limit (or clear).
    """
    subject = _effect_subject(entity, effect, result, repo)
    if subject is None:
        return
    _track_subject(result, entity, subject)
    target = _resolve_target(subject, effect, result, "traitset", repo)
    if target is None:
        return
    raw = (effect.result or "").strip()
    existing = _find_traitsetsetting(subject.id, target, repo)

    if raw == "":
        if existing is not None and existing.limit is not None:
            existing.limit = None
            result.updated_traitsetsettings.append(existing)
            result.applied.append(AppliedEffect(effect, f"cleared {target} limit override", existing.id))
        return

    try:
        new_limit = max(int(raw), 0)
    except (TypeError, ValueError):
        new_limit = 1

    prior = existing.limit if existing is not None else None
    if existing is None:
        tss = TraitSetSetting(
            id=f"{subject.id}:{target}", entity_id=subject.id, traitset_id=target,
            from_type="entity", limit=new_limit,
        )
        result.new_traitsetsettings.append(tss)
        result.applied.append(AppliedEffect(effect, f"set {target} limit to {new_limit}", tss.id))
        _queue_entity_revert(repo, subject, effect, prior_result="")
    else:
        existing.limit = new_limit
        result.updated_traitsetsettings.append(existing)
        result.applied.append(AppliedEffect(effect, f"set {target} limit to {new_limit}", existing.id))
        _queue_entity_revert(repo, subject, effect, prior_result=str(prior) if prior is not None else "")

def _apply_dice_limit(entity, effect, repo, result):
    """Increase/decrease the dice-pool selection limits (total vs effect dice).

    ``effect.result`` is the delta magnitude (default 1); ``effect.context.limit``
    selects ``total`` (base 2) or ``effect`` (base 1). The delta is applied to
    ``Entity.total_dice_bonus`` / ``Entity.effect_dice_bonus``; a duration on the
    effect schedules the inverse (opposite sign, same magnitude) on expiry.
    """
    subject = _effect_subject(entity, effect, result, repo)
    if subject is None:
        return
    _track_subject(result, entity, subject)

    which = (effect.context or {}).get("limit") or "total"
    raw = (effect.result or "").strip()
    try:
        amount = int(raw)
    except (TypeError, ValueError):
        amount = 1
    delta = amount if effect.action == "increase" else -amount

    if which == "effect":
        subject.effect_dice_bonus = (subject.effect_dice_bonus or 0) + delta
    else:
        subject.total_dice_bonus = (subject.total_dice_bonus or 0) + delta

    result.applied.append(AppliedEffect(effect, f"{effect.action}d {which} dice limit by {amount}"))
    _queue_entity_revert(repo, subject, effect)

def _resolve_pool(target: str, entity, repo) -> tuple[str, str]:
    """Map a resolved pool target id to ``(location_id, owner_id)``.

    Accepts the composite ids the targeting resolver produces
    (``difficulty:<location>``, ``pool:<entity>``) plus a bare entity/location id
    as a fallback (a location id implies the GM difficulty pool).
    """
    t = (target or "").strip()
    if not t:
        return ("", "")
    if t.startswith("difficulty:"):
        loc = t[len("difficulty:"):]
        return (loc, loc)
    if t.startswith("pool:"):
        owner_id = t[len("pool:"):]
        owner = repo.get_entity(owner_id)
        return (owner.current_location if owner else "", owner_id)
    owner = repo.get_entity(t)
    if owner is not None:
        loc = owner.id if owner.type == "location" else owner.current_location
        return (loc or "", owner.id)
    return ("", "")

def _apply_add_dice(entity, effect, repo, result):
    """Add dice to a targeted dice pool (the GM difficulty pool or an entity's).

    ``effect.target`` is a resolved pool id (``difficulty:<loc>`` or
    ``pool:<entity>``); ``effect.context.dice`` is the list of die sizes to add.
    """
    from transversal.services.contest_tracker import broadcast_pool_change
    from transversal.services.scene_state import get_scene_store

    dice = (effect.context or {}).get("dice") or []
    if isinstance(dice, str):
        dice = [d.strip() for d in dice.split(",") if d.strip()]
    if not dice:
        result.applied.append(AppliedEffect(effect, "no dice to add"))
        return

    location_id, owner_id = _resolve_pool(effect.target, entity, repo)
    if not location_id or not owner_id:
        result.applied.append(AppliedEffect(effect, f"pool target not found: {effect.target}"))
        return

    store = get_scene_store()
    pool = store.get_pool(location_id, owner_id)
    for die in dice:
        pool.append({"die": die, "source_kind": "sfx", "source_id": "", "label": die, "ts_id": None})
    store.save_pool(location_id, owner_id, pool)
    broadcast_pool_change(location_id, owner_id, dice=pool, phase="adding")
    result.applied.append(AppliedEffect(effect, f"added {len(dice)} dice to {owner_id} pool"))

def _add_trait_rating_to_pool(ts_id: str, pool_id: str, entity, repo):
    """Add a trait setting's rating dice to a pool; return ``(location_id, owner_id)``.

    Returns ``(None, None)`` when the trait is missing/has no rating, or the pool
    target is unresolvable.
    """
    from transversal.services.contest_tracker import broadcast_pool_change
    from transversal.services.scene_state import get_scene_store

    ts = repo.get_traitsetting(ts_id) if ts_id else None
    if ts is None or not ts.dice:
        return (None, None)
    location_id, owner_id = _resolve_pool(pool_id, entity, repo)
    if not location_id or not owner_id:
        return (None, None)

    trait = repo.get_trait(ts.trait_id)
    label = trait.name if trait else ts.trait_id
    dice = [d.value for d in ts.dice]
    store = get_scene_store()
    pool = store.get_pool(location_id, owner_id)
    for die in dice:
        pool.append({"die": die, "source_kind": "trait", "source_id": ts.id, "label": label, "ts_id": ts.id})
    store.save_pool(location_id, owner_id, pool)
    broadcast_pool_change(location_id, owner_id, dice=pool, phase="adding")
    return (location_id, owner_id)

def _apply_add_trait_rating(entity, effect, repo, result):
    """Add a trait instance's rating dice to a targeted dice pool.

    ``refs["trait"]`` is a resolved ``traitsetting`` id (the complication to
    heal); ``refs["pool"]`` is a resolved pool id (``difficulty:<loc>`` or
    ``pool:<entity>``). Both are authored through the targeting wizard.
    """
    trait_ref = (effect.refs or {}).get("trait")
    pool_ref = (effect.refs or {}).get("pool")
    ts_id = trait_ref.value if trait_ref else ""
    pool_id = pool_ref.value if pool_ref else ""

    ts = repo.get_traitsetting(ts_id) if ts_id else None
    if ts is None:
        result.applied.append(AppliedEffect(effect, f"trait {ts_id or '(unset)'} not found"))
        return
    if not ts.dice:
        result.applied.append(AppliedEffect(effect, f"trait {ts_id} has no rating"))
        return

    loc = _add_trait_rating_to_pool(ts_id, pool_id, entity, repo)
    if loc == (None, None):
        result.applied.append(AppliedEffect(effect, f"pool target not found: {pool_id or '(unset)'}"))
        return
    trait = repo.get_trait(ts.trait_id)
    label = trait.name if trait else ts.trait_id
    result.applied.append(AppliedEffect(effect, f"added {label} rating {[d.value for d in ts.dice]} to pool"))

def _resolve_pool_ref(effect):
    """Return the resolved pool id from ``refs["pool"]`` or the literal ``target``."""
    pool_ref = (effect.refs or {}).get("pool")
    return (pool_ref.value if pool_ref else "") or (effect.target or "")

def _roll_stored_pool(location_id: str, owner_id: str):
    """Roll a stored pool in place; return the enriched dice, or None if empty.

    Mirrors the REST ``difficulty-roll`` (no hitches reported): rolls every die,
    saves the enriched result, and broadcasts ``pool_updated`` phase="rolled".
    """
    from transversal.services.contest_tracker import broadcast_pool_change
    from transversal.services.scene_state import get_scene_store
    from transversal.services.dice_resolver import roll_dice
    from transversal.domain import DieSpec

    store = get_scene_store()
    dice = store.get_pool(location_id, owner_id)
    if not dice:
        return None

    specs = [
        DieSpec(
            die=DieType(d["die"]),
            source_kind=d.get("source_kind", "manual"),
            source_id=d.get("source_id", ""),
            label=d.get("label", ""),
            ts_id=d.get("ts_id"),
            resource=d.get("resource", False),
        )
        for d in dice
    ]
    rolls = roll_dice(specs)
    enriched = [
        {**d, "result": r.result, "hitch": r.result == 1, "role": None, "bought": False,
         "tier": r.tier.value if r.tier else None,
         "effect_die": r.tier.effect_die.value if r.tier and r.tier.effect_die else None}
        for d, r in zip(dice, rolls)
    ]
    store.save_pool(location_id, owner_id, enriched)
    broadcast_pool_change(location_id, owner_id, dice=enriched, phase="rolled")
    return enriched

def _apply_roll_pool(entity, effect, repo, result):
    """Roll a target dice pool in place and broadcast the result.

    The pool is resolved from ``refs["pool"]`` (or ``effect.target``); every die
    is rolled and the enriched result is broadcast — no difficulty is set.
    """
    pool_id = _resolve_pool_ref(effect)
    location_id, owner_id = _resolve_pool(pool_id, entity, repo)
    if not location_id or not owner_id:
        result.applied.append(AppliedEffect(effect, f"pool target not found: {pool_id or '(unset)'}"))
        return

    enriched = _roll_stored_pool(location_id, owner_id)
    if enriched is None:
        result.applied.append(AppliedEffect(effect, f"pool {owner_id} is empty"))
        return
    result.applied.append(AppliedEffect(effect, f"rolled {owner_id} pool ({len(enriched)} dice)"))

def _apply_resolve_pool(entity, effect, repo, result):
    """Auto-resolve a target dice pool: roll it, auto-pick the total, set difficulty.

    Rolls the pool (see ``_apply_roll_pool``), then sums the two highest dice
    (the standard keep-2 opposition total) and sets the location's difficulty,
    broadcasting ``difficulty_set`` — the GM's manual total-pick step is gone.
    """
    pool_id = _resolve_pool_ref(effect)
    location_id, owner_id = _resolve_pool(pool_id, entity, repo)
    if not location_id or not owner_id:
        result.applied.append(AppliedEffect(effect, f"pool target not found: {pool_id or '(unset)'}"))
        return

    enriched = _roll_stored_pool(location_id, owner_id)
    if enriched is None:
        result.applied.append(AppliedEffect(effect, f"pool {owner_id} is empty"))
        return

    # Auto-select the two highest as the total (the keep-2 opposition total),
    # marking their role so the difficulty tab renders the resolved selection
    # rather than empty slots.
    order = sorted(range(len(enriched)), key=lambda i: (enriched[i].get("result") or 0), reverse=True)
    for i in order[:2]:
        enriched[i]["role"] = "total"
    total = sum((enriched[i].get("result") or 0) for i in order[:2])

    from transversal.services.scene_state import get_scene_store
    from transversal.services.contest_tracker import broadcast_pool_change
    from transversal.api.sse.bus import StreamEvent, event_bus
    from transversal.services.session_manager import session_manager

    store = get_scene_store()
    store.save_pool(location_id, owner_id, enriched)
    broadcast_pool_change(location_id, owner_id, dice=enriched, phase="resolved")

    store.set_difficulty(location_id, total)
    for s in session_manager.list_active():
        event_bus.publish(StreamEvent(
            event="difficulty_set",
            session_id=s.id,
            data={"difficulty": total, "location_id": location_id},
        ))

    result.applied.append(AppliedEffect(effect, f"resolved {owner_id} pool → difficulty {total}"))
