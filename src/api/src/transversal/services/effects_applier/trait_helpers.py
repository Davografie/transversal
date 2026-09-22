"""Trait helpers — split out of src/api/src/transversal/services/effects_applier.py."""

from __future__ import annotations

from transversal.domain import DieType
from transversal.domain import Effect
from transversal.domain import Entity
from transversal.domain import Polarity
from transversal.domain import RatingType
from transversal.domain import TraitSetting
from typing import Optional
from transversal.services.effects_applier.datatypes import (
    AppliedEffect,
)


def _resolve_traitset_id(trait_id: str, repo) -> str:
    trait = repo.get_trait(trait_id)
    return trait.traitset_id if trait else ""

def _trait_owner(entity: Entity, effect: Effect, repo) -> tuple[str, str]:
    """Return (from_type, owner_id) for the trait targeted by an effect.

    Defaults to the entity; if ``effect.context.relationship`` names a faction,
    target the character↔faction relationship edge instead.
    """
    rel_target = (effect.context or {}).get("relationship")
    if rel_target == "{term_faction}":
        # Shared tables can't hardcode a faction; resolve to the faction the
        # entity is currently in a term with.
        rel_target = entity.pending_term.faction_id if entity.pending_term else ""
    if rel_target:
        rel = repo.get_relationship(entity.id, rel_target, "membership")
        if rel and rel.get("_key"):
            return ("relationship", rel["_key"])
    return ("entity", entity.id)

def _find_traitsetting(owner: tuple[str, str], repo, trait_id: str) -> Optional[TraitSetting]:
    from_type, owner_id = owner
    settings = (
        repo.get_relationship_traitsettings(owner_id)
        if from_type == "relationship"
        else repo.get_traitsettings_for_entity(owner_id)
    )
    for ts in settings:
        if ts.trait_id == trait_id:
            return ts
    return None

def _find_traitsetting_by_target(subject: Entity, effect: Effect, repo, target: str) -> Optional[TraitSetting]:
    """Resolve a trait-mutation target to a TraitSetting.

    Prefers a direct *instance* lookup — the target is a traitsetting id (e.g.
    ``kael-1:trait-martial``) produced by the ``die→traitsetting`` drillthrough.
    Falls back to the legacy registry-trait + owner lookup so an authored trait
    id (``trait-martial``) still resolves to the subject's instance.
    """
    if target:
        getter = getattr(repo, "get_traitsetting", None)
        if getter is not None:
            ts = getter(target)
            if ts is not None:
                return ts
    return _find_traitsetting(_trait_owner(subject, effect, repo), repo, target)

def _allow_duplicates(trait_id: str, repo) -> bool:
    """Whether the trait's set permits more than one instance (default refuse)."""
    traitset_id = _resolve_traitset_id(trait_id, repo)
    get_traitset = getattr(repo, "get_traitset_by_id", None)
    traitset = get_traitset(traitset_id) if traitset_id and get_traitset else None
    return bool(getattr(traitset, "allow_duplicates", False))

def _resolve_new_traitsetting_id(owner: tuple[str, str], trait_id: str, statement: str, repo, *, negative: bool = False) -> str:
    """The key a new instance lands under, honouring the set's duplicate rule.

    A set that allows duplicates distinguishes same-trait instances by their
    statement, so the id and the collision check have to use the same scheme —
    this is the one place that decides it for the gain path (copy/move ask the
    repository directly, because there the statement comes from the *source*
    instance rather than from the effect's context).

    A **negative** instance keeps the ``:complication`` suffix it has always had,
    so the polarity stays visible in the key and a positive instance of the same
    registry trait on the same owner cannot take its place — one live row
    (``gmc-40729203:trait-148427798:complication``) depends on the old shape.
    """
    owner_id = owner[1]
    resolve = getattr(repo, "resolve_traitsetting_id", None)
    base = (resolve(owner_id, trait_id, statement, _allow_duplicates(trait_id, repo))
            if resolve is not None else f"{owner_id}:{trait_id}")
    return f"{base}:complication" if negative else base

def _find_conflicting_traitsetting(subject: Entity, effect: Effect, repo, target: str, statement: str) -> Optional[TraitSetting]:
    """The existing instance a gain of ``target`` would collide with.

    The gain path's twin of ``_find_traitsetting_by_target``: it keeps the
    direct-instance lookup (a target may *be* a traitsetting id) but asks the
    repository's duplicate rule instead of treating "any instance of the trait"
    as a collision. A set that allows duplicates collides only on the same
    statement, which is what makes two portents of one registry trait possible.

    Only entity-anchored traits have this rule — a relationship-anchored trait is
    one instance per edge by construction — so that case keeps the plain lookup.
    """
    if target:
        getter = getattr(repo, "get_traitsetting", None)
        if getter is not None and getter(target) is not None:
            return getter(target)
    owner = _trait_owner(subject, effect, repo)
    if owner[0] != "entity":
        return _find_traitsetting(owner, repo, target)
    conflict = getattr(repo, "find_traitsetting_collision", None)
    if conflict is None:
        # No duplicate rule to consult (a bare repo double) — refuse as before.
        return _find_traitsetting(owner, repo, target)
    return conflict(subject.id, target, statement, _allow_duplicates(target, repo))

def _resync_pool(ts: TraitSetting) -> None:
    """Let an assembled pool follow its trait's new rating.

    One home for the call, because a rating change and its undo must both do it —
    a pool that follows the forward change but not the restore would show a
    temporary size against a trait that reads its own. Tolerates a double without
    an owning entity (there is then no pool to follow).
    """
    entity_id = getattr(ts, "entity_id", "")
    if not entity_id:
        return
    from transversal.services.scene_state import resync_pool_dice_for_trait
    resync_pool_dice_for_trait(entity_id, ts.id, [d.value for d in (ts.dice or [])])

def _step_up(ts: TraitSetting) -> bool:
    """Step up the smallest die, capped at d12. Restores an empty rating to d4."""
    if not ts.dice:
        ts.dice = [DieType.D4]
        return True
    smallest = min(ts.dice, key=lambda d: d.max_value)
    if smallest == DieType.D12:
        return False
    ts.dice[ts.dice.index(smallest)] = smallest.step_up()
    return True

def _step_down_one(ts: TraitSetting) -> str:
    """Step down the smallest die. Returns ``"stepped" | "empty"``.

    A d4 die steps down to no die (empty rating) — the trait *persists* with an
    empty rating rather than being deleted, so a temporary step-down can revert.
    """
    if not ts.dice:
        return "empty"
    smallest = min(ts.dice, key=lambda d: d.max_value)
    if smallest == DieType.D4:
        ts.dice.remove(smallest)
        return "stepped"
    ts.dice[ts.dice.index(smallest)] = smallest.step_down()
    return "stepped"

def _steps(effect: Effect) -> int:
    """Read the optional step magnitude from an effect's context (default 1)."""
    raw = (effect.context or {}).get("steps")
    try:
        return max(int(raw), 1)
    except (TypeError, ValueError):
        return 1

def _has_steps(effect: Effect) -> bool:
    """True when ``steps`` was explicitly provided in the effect's context."""
    return "steps" in (effect.context or {})

def _step_up_trait(entity: Entity, ts: TraitSetting, target: str, effect: Effect, result, repo, steps: int = 1) -> bool:
    """Step up a trait setting up to ``steps`` times.

    Returns True when the rating changed (caller persists + reverts). A negative
    trait pushed beyond d12 takes the entity out (once) and leaves the trait at
    d12.
    """
    applied = 0
    for _ in range(steps):
        if _step_up(ts):
            applied += 1
        else:
            break  # empty dice or already at d12

    if applied < steps:
        if ts.polarity == Polarity.NEGATIVE:
            entity.taken_out = True
            result.applied.append(AppliedEffect(effect, f"{target} stepped beyond d12 — taken out"))
            from transversal.domain import Effect as _Effect, EffectTiming as _ET, Timer as _Timer, TimerCombine as _TC
            from transversal.services.scheduled_events import schedule_event
            schedule_event(
                repo, "entity", entity.id,
                _Effect(timing=_ET.IMMEDIATE, type="entity", action="clear_taken_out", target="self"),
                [_Timer(event="scene", remaining=1)],
                _TC.FIRST_TO_FIRE,
            )
        elif applied == 0:
            result.applied.append(AppliedEffect(effect, f"{target} already at d12"))
    return applied > 0

def _die(result: Optional[str]) -> DieType:
    return DieType(str(result).lower()) if result else DieType.D4

def _die_opt(result: Optional[str]) -> Optional[DieType]:
    """Parse a die rating, or ``None`` when the value is not one.

    Used where an unreadable rating must *skip* rather than default: a
    substituted roll variable is empty when the die's tier has no effect die
    (a fail), and a token that never substituted is not a die either.
    """
    raw = str(result or "").strip().lower()
    if not raw:
        return None
    try:
        return DieType(raw)
    except ValueError:
        return None

def _ctx(effect: Effect, key: str) -> str:
    """Read a string context value (empty when absent)."""
    return str((effect.context or {}).get(key) or "")

def _rating_type(effect: Effect) -> RatingType:
    """Rating type authored on a trait-gain effect (default STATIC)."""
    raw = _ctx(effect, "rating_type").lower() or "static"
    try:
        return RatingType(raw)
    except ValueError:
        return RatingType.STATIC

def _new_traitsetting(owner: tuple[str, str], trait_id: str, die: DieType, repo, *, negative: bool = False, statement: str = "", notes: str = "", rating_type: RatingType = RatingType.STATIC) -> TraitSetting:
    from transversal.services.polarity import default_polarity

    from_type, owner_id = owner
    traitset_id = _resolve_traitset_id(trait_id, repo)
    trait = repo.get_trait(trait_id)
    get_traitset = getattr(repo, "get_traitset_by_id", None)
    traitset = get_traitset(traitset_id) if traitset_id and get_traitset else None
    polarity = Polarity.NEGATIVE if negative else default_polarity(trait, traitset)
    if not traitset_id and polarity == Polarity.NEGATIVE:
        traitset_id = "ts-complications-a190"
    projection_id = None
    if from_type == "entity" and trait is not None and not getattr(trait, "default_ego", False):
        # Morph-by-default — anchor the grant to the entity's active projection.
        get_entity = getattr(repo, "get_entity", None)
        entity = get_entity(owner_id) if get_entity else None
        if entity is not None and entity.current_projection:
            from_type = "projection"
            projection_id = entity.current_projection
    return TraitSetting(
        id=_resolve_new_traitsetting_id(owner, trait_id, statement, repo,
                                       negative=polarity == Polarity.NEGATIVE),
        entity_id=owner_id,
        trait_id=trait_id,
        traitset_id=traitset_id,
        from_type=from_type,
        projection_id=projection_id,
        dice=[die],
        rating_type=rating_type,
        polarity=polarity,
        statement=statement,
        notes=notes,
        source_type="effect",
    )
