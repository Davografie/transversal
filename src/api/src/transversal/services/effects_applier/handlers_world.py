"""Handlers world — split out of src/api/src/transversal/services/effects_applier.py."""

import random

from transversal.services.effect_targets import resolve_candidates
from typing import Optional
from transversal.services.effects_applier.datatypes import (
    AppliedEffect,
    PendingChoice,
)
from transversal.services.effects_applier.reverts import (
    _queue_entity_revert,
)
from transversal.services.effects_applier.targeting import (
    _effect_subject,
    _resolve_target,
    _track_subject,
)


def _apply_attune_universe(a, em, universe_fallback: str) -> str:
    """The universe an attune effect grants.

    Prefers the resolved ``projection`` reference — the intended model, where the
    capability is sourced from a *life* and takes its universe. Falls back to the
    authored universe string so content written before the reference existed
    keeps working.
    """
    ref = (getattr(a, "refs", None) or {}).get("projection")
    projection_id = getattr(ref, "value", "") if ref is not None else ""
    if projection_id:
        projection = em.repo.get_projection(projection_id)
        if projection is not None and projection.universe:
            return projection.universe
    return a.result or universe_fallback

def _apply_cancel_scheduled_event(entity, effect, repo, result):
    """Cancel a specific pending timer (target = a scheduled-event id)."""
    subject = _effect_subject(entity, effect, result, repo)
    if subject is None:
        return
    _track_subject(result, entity, subject)
    target = _resolve_target(subject, effect, result, "scheduled_event", repo)
    if target is None:
        return  # pending choice (or no candidate)
    if repo.delete_scheduled_event(target):
        result.applied.append(AppliedEffect(effect, f"ended active effect {target}", target))
    else:
        result.applied.append(AppliedEffect(effect, f"no active effect {target} to end"))

def _apply_create_projection(entity, effect, repo, result):
    """Create + activate a temporary alternate body (disguise) in the current
    universe/location; schedule a restore of the prior body on expiry."""
    from transversal.domain import Projection, TransversalType
    from transversal.services.entity_manager import touch_projection

    subject = _effect_subject(entity, effect, result, repo)
    if subject is None:
        return
    _track_subject(result, entity, subject)

    ctx = effect.context or {}
    name = (effect.target or "").strip() or (ctx.get("name") or "").strip() or "disguise"
    prior = subject.current_projection
    proj = Projection(
        id=_next_projection_id(subject.id, subject.current_universe, repo),
        entity_id=subject.id,
        origin_universe=subject.current_universe,
        universe=subject.current_universe,
        name=name,
        current_location=subject.current_location,
        transversal_type=TransversalType.NATIVE,
    )
    touch_projection(proj)
    result.new_projections.append(proj)
    subject.current_projection = proj.id
    result.applied.append(AppliedEffect(effect, f"disguised as {name} ({proj.id})", proj.id))
    _queue_entity_revert(repo, subject, effect, prior_result=prior)

def _apply_restore_projection(entity, effect, repo, result):
    """Revert a temporary projection: re-activate the prior body at the current
    location and delete the temporary (disguise) body."""
    from transversal.services.entity_manager import touch_projection

    subject = _effect_subject(entity, effect, result, repo)
    if subject is None:
        return
    _track_subject(result, entity, subject)

    prior_id = (effect.result or "").strip()
    if not prior_id:
        return
    prior = repo.get_projection(prior_id)
    if prior is None:
        result.applied.append(AppliedEffect(effect, f"prior body {prior_id} not found"))
        return
    disguise_id = subject.current_projection
    if disguise_id and disguise_id != prior_id:
        disguise = repo.get_projection(disguise_id)
        if disguise is not None:
            result.removed_projections.append(disguise)
    prior.current_location = subject.current_location
    touch_projection(prior)
    result.updated_projections.append(prior)
    subject.current_projection = prior.id
    result.applied.append(AppliedEffect(effect, f"restored body {prior.id}"))

def _apply_relationship_create(entity, effect, repo, result):
    target = _resolve_target(entity, effect, result, "entity", repo)
    if target is None:
        return
    rel_type = effect.result or ""
    description = effect.context.get("description", "") if effect.context else ""
    result.new_relationships.append({
        "from": entity.id,
        "to": target,
        "type": rel_type,
        "description": description,
    })
    result.applied.append(AppliedEffect(effect, f"relationship {rel_type} → {target}"))

def _next_projection_id(entity_id: str, universe: str, repo) -> str:
    """Generate a unique projection key (first body keeps the legacy key)."""
    base = f"{entity_id}:{universe}"
    existing = {p.id for p in repo.get_projections_for_entity(entity_id)}
    if base not in existing:
        return base
    n = 2
    while f"{base}:{n}" in existing:
        n += 1
    return f"{base}:{n}"

def _scope_universe(scope: Optional[str]) -> Optional[str]:
    """Return a literal universe from a ``universe:X`` scope, else None."""
    from transversal.services.effect_targets import parse_scope
    if not scope:
        return None
    prefix, value = parse_scope(scope)
    if prefix == "universe" and value and not value.startswith("{"):
        return value
    return None

def _apply_set_location(entity, effect, repo, result):
    """Place an entity at a location without crossing a universal boundary.

    Sets the entity's ``current_location`` (and its active body's location).
    The destination location's universe, when known, is authoritative — matching
    the REST ``move`` endpoint. Unlike ``travel``, no body/transversal policy
    applies: the active body simply relocates.

    If the subject has no active body, a fresh native body is created — mirroring
    ``EntityManager.move_to`` — so an unplaced character is never left bodiless.
    """
    from transversal.domain import Projection, TransversalType
    from transversal.services.entity_manager import touch_projection

    subject = _effect_subject(entity, effect, result, repo)
    if subject is None:
        return
    _track_subject(result, entity, subject)

    location_id = _resolve_target(subject, effect, result, "location", repo)
    if location_id is None:
        return  # pending choice recorded

    loc = repo.get_entity(location_id)
    dest_universe = loc.current_universe if loc is not None and loc.current_universe else subject.current_universe

    subject.current_location = location_id
    subject.current_universe = dest_universe

    proj = repo.get_projection(subject.current_projection) if subject.current_projection else None
    if proj is not None:
        proj.current_location = location_id
        proj.universe = dest_universe
        touch_projection(proj)
        result.updated_projections.append(proj)
    else:
        proj = Projection(
            id=_next_projection_id(subject.id, dest_universe, repo),
            entity_id=subject.id,
            origin_universe=dest_universe,
            universe=dest_universe,
            current_location=location_id,
            transversal_type=TransversalType.NATIVE,
        )
        touch_projection(proj)
        result.new_projections.append(proj)
        subject.current_projection = proj.id

    result.applied.append(AppliedEffect(effect, f"placed at {location_id}"))

def _apply_travel(entity, effect, repo, result):
    """Cross a universal boundary, honoring subject/location/mechanism/body/universe.

    Subject = ``effect.entity``. Destination location = ``effect.target`` (literal,
    ``{choose_location}``, or ``{random:location}``). Universe = ``effect.target_scope``
    (``universe:X``) or, for a location scope, the target location's universe.
    Mechanism = ``context.transversal_type``. Body policy = ``context.projection``.

    Inapposite always uses the active body (it travels). Consciousness picks a
    body via ``{last_projection}`` / ``{random_projection}`` / ``{choose_projection}``
    (reuse an existing body in the destination universe, falling back to a fresh
    body when there is none) or ``{new_projection}`` (always spawn).
    """
    from transversal.domain import Projection, TransversalType
    from transversal.services.entity_manager import touch_projection

    subject = _effect_subject(entity, effect, result, repo)
    if subject is None:
        return
    _track_subject(result, entity, subject)

    ctx = effect.context or {}
    travel_type = ctx.get("transversal_type") or "inapposite"
    projection_policy = (ctx.get("projection") or "active").strip()

    def _spawn_body(dest_universe: str, location_id: str, trans_type: TransversalType) -> None:
        proj = Projection(
            id=_next_projection_id(subject.id, dest_universe, repo),
            entity_id=subject.id,
            origin_universe=dest_universe,
            universe=dest_universe,
            current_location=location_id,
            transversal_type=trans_type,
        )
        touch_projection(proj)
        result.new_projections.append(proj)
        subject.current_projection = proj.id
        subject.current_universe = dest_universe
        subject.current_location = location_id
        result.applied.append(AppliedEffect(effect, f"spawned body {proj.id}"))

    def _dest_universe() -> str:
        uni = _scope_universe(effect.target_scope)
        if uni:
            return uni
        target = (effect.target or "").strip()
        if target and not target.startswith("{"):
            loc = repo.get_entity(target)
            if loc and loc.current_universe:
                return loc.current_universe
        return subject.current_universe

    # ── Inapposite — the active body itself travels. ──
    if travel_type != "consciousness":
        location_id = _resolve_target(subject, effect, result, "location", repo)
        if location_id is None:
            return  # pending choice recorded
        dest_universe = _dest_universe()
        proj = repo.get_projection(subject.current_projection) if subject.current_projection else None
        if proj is None:
            _spawn_body(dest_universe, location_id, TransversalType.NATIVE)
        else:
            proj.universe = dest_universe
            proj.current_location = location_id
            proj.transversal_type = (
                TransversalType.NATIVE if dest_universe == proj.origin_universe else TransversalType.INAPPOSITE
            )
            touch_projection(proj)
            result.updated_projections.append(proj)
            subject.current_projection = proj.id
            subject.current_universe = dest_universe
            subject.current_location = location_id
            result.applied.append(AppliedEffect(effect, f"relocated to {location_id}"))
        return

    # ── Consciousness — pick/reuse/spawn a body in the destination universe. ──
    if projection_policy == "active":
        projection_policy = "{last_projection}"  # legacy alias

    dest_universe = _dest_universe()

    def _arrive_in_body(proj) -> None:
        touch_projection(proj)
        result.updated_projections.append(proj)
        subject.current_projection = proj.id
        subject.current_universe = proj.universe
        subject.current_location = proj.current_location
        result.applied.append(AppliedEffect(effect, f"arrived in body {proj.id}"))

    def _spawn_new() -> None:
        location_id = _resolve_target(subject, effect, result, "location", repo)
        if location_id is None:
            return
        _spawn_body(dest_universe, location_id, TransversalType.CONSCIOUSNESS)

    # A literal projection id is a resolved ``{choose_projection}``.
    if projection_policy not in ("{last_projection}", "{new_projection}", "{random_projection}", "{choose_projection}"):
        proj = repo.get_projection(projection_policy)
        if proj is not None:
            _arrive_in_body(proj)
            return
        projection_policy = "{new_projection}"

    if projection_policy in ("{last_projection}", "{random_projection}", "{choose_projection}"):
        scope = effect.target_scope or (f"universe:{dest_universe}" if dest_universe else None)
        candidates = resolve_candidates("projection", scope, subject, repo)
        if candidates:
            if projection_policy == "{choose_projection}":
                result.pending_choices.append(PendingChoice(
                    effect=effect, kind="projection",
                    scope=scope,
                    field="context.projection",
                ))
                return
            if projection_policy == "{last_projection}":
                projs = [repo.get_projection(c.id) for c in candidates]
                projs = [p for p in projs if p is not None]
                projs.sort(key=lambda p: p.last_used_at or "", reverse=True)
                proj = projs[0] if projs else None
            else:
                proj = repo.get_projection(random.choice([c.id for c in candidates]))
            if proj is not None:
                _arrive_in_body(proj)
                return
        projection_policy = "{new_projection}"  # no existing body → spawn a fresh one

    _spawn_new()
