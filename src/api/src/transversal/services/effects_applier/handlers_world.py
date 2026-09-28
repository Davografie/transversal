"""Handlers world — split out of src/api/src/transversal/services/effects_applier.py."""

from __future__ import annotations

import random

from transversal.services.target_scopes import resolve_candidates
from typing import Optional
from transversal.services.effects_applier.datatypes import (
    AppliedEffect,
    PendingChoice,
)
from transversal.services.effects_applier.handlers_traits import (
    _resolve_learners,
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

def _apply_attune_projection(a, em) -> Optional[str]:
    """The body a grant names, from the resolved ``projection`` reference.

    The reference is the intended form for *both* halves: for an attunement it is
    the life the capability is sourced from, and for a suppression it is the body
    being cut off — resolved at read-time by its path (see decision 4 in
    [[Active Projections Design Log]]), so "the body that is current" means it when
    the effect runs and not when it was authored.

    Falls back to the authored id so a directly-named body keeps working.
    """
    ref = (getattr(a, "refs", None) or {}).get("projection")
    projection_id = getattr(ref, "value", "") if ref is not None else ""
    return projection_id or (a.result or "").strip() or None


def _apply_cancel_scheduled_event(entity, effect, repo, result):
    """End a pending row now (target = a scheduled-event id).

    Ending means the effect stops: a revert/hold row's undo is applied instead of
    waiting for its timer, and a deferred forward row is dropped before it fires.
    (It used to delete without applying — which quietly made a temporary change
    permanent, the opposite of what the label promises.)
    """
    subject = _effect_subject(entity, effect, result, repo)
    if subject is None:
        return
    _track_subject(result, entity, subject)
    target = _resolve_target(subject, effect, result, repo)
    if target is None:
        return  # pending choice (or no candidate)
    getter = getattr(repo, "get_scheduled_event", None)
    event = getter(target) if getter else None
    if event is None and hasattr(repo, "list_all_scheduled_events"):
        event = next((e for e in repo.list_all_scheduled_events() if e.id == target), None)
    if event is None:
        result.applied.append(AppliedEffect(effect, f"no active effect {target} to end"))
        return
    from transversal.services.scheduled_events import end_event

    applied = end_event(repo, event)
    result.applied.append(
        AppliedEffect(effect, f"ended active effect {target}" if applied else f"dropped pending effect {target}", target)
    )

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
    target = _resolve_target(entity, effect, result, repo)
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

    location_id = _resolve_target(subject, effect, result, repo)
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

def _body_pool(effect, subject, dest_universe: str, repo) -> list:
    """The bodies a travel effect may reuse, in scope order.

    The author narrows the pool with the ``projection`` **reference's path** — the
    same declarations the old ``target_scope`` spelled (``location:X → its subtree
    → the actor's projections``), so "reuse the body I have *here*" is a path like
    any other. With no path the pool is the actor's bodies in the destination
    universe, which is what a transversal means by "a body I already have there".
    """
    from transversal.services.target_resolver import TargetContext, resolved_id, resolve

    ref = (effect.refs or {}).get("projection")
    if ref is not None and ref.spec is not None and ref.spec.steps:
        resolution = resolve(ref.spec, TargetContext(subject=subject, repo=repo))
        return [rid for value in resolution.values if (rid := resolved_id(value))]
    scope = f"universe:{dest_universe}" if dest_universe else None
    return [c.id for c in resolve_candidates("projection", scope, subject, repo)]


def _apply_travel(entity, effect, repo, result):
    """Cross a universal boundary, honoring subject/location/mechanism/body/universe.

    Subject = ``effect.entity``. Destination location = ``effect.target`` (a spec
    resolves it to a concrete id before this runs). Universe = the destination
    location's universe. Mechanism = ``context.transversal_type``. Body policy =
    ``context.projection``, whose pool is the ``projection`` reference's **path**
    (or the destination universe when the reference names no path).

    Inapposite always uses the active body (it travels). Consciousness picks a
    body via ``{last_projection}`` / ``{random_projection}`` / ``{choose_projection}``
    (reuse an existing body in the destination universe, falling back to a fresh
    body when there is none) or ``{new_projection}`` (always spawn).
    ``{closest_projection}`` is the one policy that is *place*-driven rather than
    *universe*-driven: it takes the body nearest the destination by the weighted
    location graph, moves that body to the destination, and arrives in it — so the
    entity lands where it asked to go, on the nearest body it had.
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
        target = (effect.target or "").strip()
        if target and not target.startswith("{"):
            loc = repo.get_entity(target)
            if loc and loc.current_universe:
                return loc.current_universe
        return subject.current_universe

    # ── Inapposite — the active body itself travels. ──
    if travel_type != "consciousness":
        location_id = _resolve_target(subject, effect, result, repo)
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
        location_id = _resolve_target(subject, effect, result, repo)
        if location_id is None:
            return
        _spawn_body(dest_universe, location_id, TransversalType.CONSCIOUSNESS)

    def _closest_body():
        """The subject's body nearest the destination, by the location-graph metric.

        The pool is **every** placed body the subject has, not the destination
        universe's — that is the scope the *reuse* policies want, and it answers
        the wrong question here. The metric already prices a universe boundary at
        ``CROSS_UNIVERSE_WEIGHT``, so a body on the near side beats a far one on
        distance rather than by being the only candidate, and a body in another
        universe is still the right answer when it is the closest thing the
        entity has.

        A body with no location cannot be ranked, and one whose location is
        unreachable from the destination is not a candidate at all (the read omits
        unreachable targets). Either way this returns None and the caller falls
        back to a fresh body at the destination, so a transversal never silently
        does nothing. Ties break on body id, so the pick is deterministic.
        """
        location_id = _resolve_target(subject, effect, result, repo)
        if location_id is None:
            return None  # a pending choice was recorded instead
        bodies = [p for p in repo.get_projections_for_entity(subject.id) if p.current_location]
        distances = repo.get_location_distances_from(
            location_id, {p.current_location for p in bodies}
        )
        ranked = [
            (distances[p.current_location], p)
            for p in bodies if p.current_location in distances
        ]
        if not ranked:
            return None
        _distance, proj = min(ranked, key=lambda pair: (pair[0], pair[1].id))
        # The body comes to the location. A consciousness transversal is the mind
        # moving into a body, and ``_arrive_in_body`` aligns the entity with
        # wherever that body sits — so the body is placed first, and the mind then
        # lands on the spot that was asked for rather than wherever the nearest
        # body happened to be.
        proj.current_location = location_id
        proj.universe = dest_universe
        # ``NATIVE`` means *home*: it is what ``is_transversal`` counts, and what
        # makes a universe live for the entity. A body back in its origin universe
        # is native again; one standing in a foreign universe is there by
        # consciousness, exactly as the inapposite branch labels its own crossing.
        proj.transversal_type = (
            TransversalType.NATIVE
            if dest_universe == proj.origin_universe
            else TransversalType.CONSCIOUSNESS
        )
        return proj

    # A literal projection id is a resolved ``{choose_projection}``.
    if projection_policy not in ("{last_projection}", "{new_projection}", "{random_projection}", "{choose_projection}", "{closest_projection}"):
        proj = repo.get_projection(projection_policy)
        if proj is not None:
            _arrive_in_body(proj)
            return
        projection_policy = "{new_projection}"

    if projection_policy == "{closest_projection}":
        proj = _closest_body()
        if proj is not None:
            _arrive_in_body(proj)
            return
        projection_policy = "{new_projection}"  # no ranked body → spawn at the destination

    if projection_policy in ("{last_projection}", "{random_projection}", "{choose_projection}"):
        body_ids = _body_pool(effect, subject, dest_universe, repo)
        if body_ids:
            if projection_policy == "{choose_projection}":
                # The destination universe stays as the picker's narrowing hint: a
                # body outside it would be a transversal in its own right.
                result.pending_choices.append(PendingChoice(
                    effect=effect, kind="projection",
                    scope=f"universe:{dest_universe}" if dest_universe else None,
                    field="context.projection",
                ))
                return
            if projection_policy == "{last_projection}":
                projs = [p for p in (repo.get_projection(pid) for pid in body_ids) if p is not None]
                projs.sort(key=lambda p: p.last_used_at or "", reverse=True)
                proj = projs[0] if projs else None
            else:
                proj = repo.get_projection(random.choice(body_ids))
            if proj is not None:
                _arrive_in_body(proj)
                return
        projection_policy = "{new_projection}"  # no existing body → spawn a fresh one

    _spawn_new()


def _apply_set_destination(entity, effect, repo, result):
    """Grant an entity directions to a place ([[Guided Route]]).

    Only the destination **id** is written: the viewer derives the name and the
    next hop from the graph, so a renamed location or an edited graph cannot leave
    a stale label or a stale route behind. The subject is the entity who is being
    told the way — the target machinery fans out, so a party-wide brief is one
    effect over several subjects.
    """
    subject = _effect_subject(entity, effect, result, repo)
    if subject is None:
        return
    _track_subject(result, entity, subject)

    location_id = _resolve_target(subject, effect, result, repo)
    if location_id is None:
        return  # pending choice recorded

    prior = getattr(subject, "destination_location", None) or ""
    subject.destination_location = location_id
    result.applied.append(AppliedEffect(effect, f"directions to {location_id}"))
    _queue_entity_revert(repo, subject, effect, prior_result=prior)


def _apply_clear_destination(entity, effect, repo, result):
    """The undo of directions — an expiry, or a decided activation taken back.

    ``effect.result`` carries the pre-apply destination (the action declares
    ``inverse_captures_prior``), so this **restores** what the guidance replaced
    rather than always emptying it: re-pointing someone at a new place and then
    ending that guidance leaves the old objective standing, which is what an
    expiry of the *second* rule ought to mean.
    """
    subject = _effect_subject(entity, effect, result, repo)
    if subject is None:
        return
    _track_subject(result, entity, subject)

    prior = (effect.result or "").strip() or None
    subject.destination_location = prior
    result.applied.append(
        AppliedEffect(effect, f"directions restored to {prior}" if prior else "directions cleared")
    )


def _apply_learn(entity, effect, repo, result):
    """The learner learns the effect's target ([[B121]]).

    A **union**, never a replace: the id joins ``known_to`` only if it is not
    already there, so a rule that fires twice — or a second rule that teaches
    something adjacent — cannot wipe the list. That is the whole reason this is
    an action rather than a field write: `known_to` is monotonic knowledge, and
    the GM assuming a hidden occupant must not forget what that occupant already
    knew.

    **Two questions, so two declarations:** *who learns* is the ``learner``
    reference — a targeting path, so "everyone with him" is sayable — and *which
    entity they learn about* is the target. An empty learner means the entity the
    effect lands on (the subject), which is the only reading this had before the
    reference existed. A path fans out before it reaches here, so "every occupant
    of my location" arrives as one call per entity and the membership check does
    the dedupe. An entity is never made known to itself.
    """
    subject = _effect_subject(entity, effect, result, repo)
    if subject is None:
        return
    _track_subject(result, entity, subject)

    target = _resolve_target(subject, effect, result, repo)
    if not target:
        result.applied.append(AppliedEffect(effect, "no one named to learn"))
        return

    # The learner may be someone other than the subject, so each one is tracked
    # for persistence — `commit_effects` writes the primary entity plus every
    # entity in `entities_to_update`, and nothing else.
    for learner_id in _resolve_learners(entity, effect, repo, result, default=[subject.id]):
        learner = subject if learner_id == subject.id else (
            repo.get_entity(learner_id) if repo is not None else None)
        if learner is None:
            result.applied.append(AppliedEffect(effect, f"no entity {learner_id} to learn it"))
            continue
        _track_subject(result, entity, learner)
        if learner.id == target:
            result.applied.append(AppliedEffect(
                effect, f"{learner.name or learner.id} already knows itself"))
            continue
        known = list(getattr(learner, "known_to", None) or [])
        if target in known:
            result.applied.append(AppliedEffect(
                effect, f"{learner.name or learner.id} already knows {target}"))
            continue
        learner.known_to = [*known, target]
        result.applied.append(AppliedEffect(
            effect, f"{learner.name or learner.id} learns {target}"))
