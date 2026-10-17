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
from transversal.services.effect_refs import target_value


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
    name = target_value(effect).strip() or (ctx.get("name") or "").strip() or "disguise"
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
    rel = {"from": entity.id, "to": target, "type": rel_type, "description": description}
    # **Mint the edge here**, not at commit. The key is the only handle on a tie,
    # and `Effect.output` binds it so a later effect can anchor to the relationship
    # ("gain a trait *on the tie*"). Created at commit time it did not exist while
    # the rest of the batch was still resolving, so that reference could never
    # resolve ([[B303]]). The commit paths skip an edge that already carries a key.
    created = None
    if hasattr(repo, "create_relationship"):
        created = repo.create_relationship(rel["from"], rel["to"], rel["type"], rel["description"])
        # Marked whether or not the repo handed the edge back: the flag is what
        # stops the commit creating it a second time, and a repo that returns
        # nothing (a fake, a future writer) must not turn into a duplicate tie.
        rel["created"] = True
    if isinstance(created, dict):
        rel["key"] = created.get("_key", "")
    result.new_relationships.append(rel)
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

def _apply_duplicate_entity(entity, effect, repo, result):
    """Spawn a copy of an entity — the mob from a template ([[B311]]).

    A **plain deep copy**, which is the human's decision: the copy owns its traits
    rather than inheriting the template's, so no rendering rule is needed and no
    provenance edge is required. Everything is remapped — the entity and its
    projection, each copied trait instance (nested ones **parent-first**, so a
    child points at its *new* parent), the set settings, and the `relation` and
    `membership` edges with the instances anchored to those edges.

    The copy is made **here**, not at commit, for the same reason
    `_apply_relationship_create` mints its edge here: the new id has to exist while
    the rest of the batch is still resolving, so `Effect.output` can name "the
    thing I just spawned" for a later effect.

    The acting subject of a GM-bucket press is the **place** the GM is looking at
    (the sheet's scene overview passes it as the subject), so the landing place is
    resolved defensively rather than assumed to be a character's location.
    """
    from transversal.domain import Projection, TransversalType
    from transversal.services.entity_manager import _generate_id, touch_projection

    template_id = (target_value(effect) or "").strip()
    template = repo.get_entity(template_id) if template_id else None
    if template is None:
        result.applied.append(AppliedEffect(
            effect, f"no entity to copy: '{template_id}' does not exist"))
        return

    ctx = effect.context or {}
    name = (ctx.get("name") or "").strip() or template.name
    location = _spawn_location(entity, effect, repo, template)
    new_id = _generate_id(name, template.type)
    new_universe = template.current_universe
    new = template.model_copy(update={
        "id": new_id,
        "name": name,
        "current_universe": new_universe,
        "current_location": location,
        "current_projection": f"{new_id}:{new_universe}",
        # A copy is a new arrival, not a landmark: it inherits none of the
        # template's *place* — so it is not itself a spawn destination, it has no
        # directions, and the map stacks it as an unplaced occupant rather than
        # hiding it under the template's own dot.
        "destination_location": None,
        "map_x": None,
        "map_y": None,
        "starter_location": False,
    })
    repo.create_entity(new)
    proj = Projection(
        id=f"{new_id}:{new_universe}", entity_id=new_id, universe=new_universe,
        origin_universe=new_universe, current_location=location,
        transversal_type=TransversalType.NATIVE,
    )
    touch_projection(proj)
    repo.create_projection(proj)

    traits = _copy_trait_settings(repo, template.id, new)
    sets = _copy_entity_set_settings(repo, template.id, new_id)
    edges = _copy_entity_edges(repo, template.id, new_id)

    # The ownership edge is **optional**, on the human's instruction: absent
    # unless asked for, and never guessed from the template.
    owner_player = (ctx.get("owner_player_id") or "").strip()
    if owner_player and hasattr(repo, "claim_entity"):
        repo.claim_entity(owner_player, new_id, main=False)

    result.new_entities.append(new)
    result.applied.append(AppliedEffect(
        effect,
        f"spawned {new.name} ({new_id}) from {template.name} — "
        f"{traits} trait(s), {sets} set setting(s), {edges} edge(s)",
        new_id,
    ))


def _spawn_location(subject, effect, repo, template) -> Optional[str]:
    """Where the copy lands: an authored place, else the subject's, else the template's.

    A GM-owned rule runs against the scene and its subject is a **location**, in
    which case the place *is* the subject — that is the "mob where the GM is
    looking" case, and treating it as an entity's ``current_location`` would put
    the mob in the place's *parent* instead.
    """
    ref = (getattr(effect, "refs", None) or {}).get("owner")
    authored = (getattr(ref, "value", "") or "").strip()
    if authored and authored != "self":
        return authored
    if subject is not None:
        if _entity_type_of(subject) == "location":
            return subject.id
        if subject.current_location:
            return subject.current_location
    return template.current_location


def _entity_type_of(entity) -> str:
    """An entity's type as a plain string, enum or not."""
    value = getattr(entity, "type", "")
    return str(getattr(value, "value", value) or "")


def _copy_trait_settings(repo, source_entity_id: str, new) -> int:
    """Copy the entity's own instances, nested children included, remapped.

    Parent-first: a nested instance's key is scoped to its parent
    (`repo.resolve_subtrait_id`), so the parent must exist under its **new** id
    before the child can be keyed. Every new key comes from the repository's own
    resolver with the **source instance's statement** — the rule the gain and copy
    paths already share — because inventing one here would let two readers
    disagree about which instance is which.
    """
    reader = getattr(repo, "get_traitsettings_for_entity", None)
    if reader is None:
        return 0
    copied = 0
    for source in reader(source_entity_id) or []:
        copied += _copy_one_trait(repo, source, new, parent_copy=None)
    return copied


def _copy_one_trait(repo, source, new, parent_copy) -> int:
    from transversal.services.effects_applier.trait_helpers import _allow_duplicates

    entity_id, projection_id, parent_id = new.id, None, None
    from_type = source.from_type
    if parent_copy is not None:
        entity_id = getattr(parent_copy, "entity_id", "") or new.id
        parent_id = getattr(parent_copy, "id", None)
        from_type = "traitsetting"
        resolve_sub = getattr(repo, "resolve_subtrait_id", None)
        new_id = (resolve_sub(parent_id, source.trait_id, source.statement)
                  if resolve_sub is not None else f"{parent_id}:{source.trait_id}")
    else:
        if from_type == "projection":
            projection_id = new.current_projection
        resolve = getattr(repo, "resolve_traitsetting_id", None)
        new_id = (resolve(entity_id, source.trait_id, source.statement,
                          _allow_duplicates(source.trait_id, repo))
                  if resolve is not None else f"{entity_id}:{source.trait_id}")
    created = source.model_copy(update={
        "id": new_id,
        "entity_id": entity_id,
        "from_type": from_type,
        "projection_id": projection_id,
        "parent_traitsetting_id": parent_id,
    })
    repo.create_traitsetting(created)
    count = 1
    get_children = getattr(repo, "get_sub_traitsettings", None)
    for child in (get_children(source.id) if get_children else []) or []:
        count += _copy_one_trait(repo, child, new, parent_copy=created)
    return count


def _copy_entity_set_settings(repo, source_entity_id: str, new_entity_id: str) -> int:
    """Copy the entity's trait-set settings (its `entity → set` overrides)."""
    reader = getattr(repo, "get_traitsetsettings_for_entity", None)
    if reader is None:
        return 0
    copied = 0
    for source in reader(source_entity_id) or []:
        repo.create_traitsetsetting(source.model_copy(update={
            "id": f"{new_entity_id}:{source.traitset_id}",
            "entity_id": new_entity_id,
            "projection_id": None,
        }))
        copied += 1
    return copied


def _copy_entity_edges(repo, source_entity_id: str, new_entity_id: str) -> int:
    """Copy the entity's `relation` and `membership` edges, and their instances.

    Membership is copied on the human's instruction — the old mutation copied only
    `relation` edges. `_to` is deliberately left alone: the far end is a *shared*
    thing (a faction, a contact), so a spawned mob's tie points at the same
    faction the template's did, which is the point of copying it. The instances
    anchored to a copied edge follow it, keyed to the **new** edge.
    """
    reader = getattr(repo, "list_relationships_for_entity", None)
    if reader is None:
        return 0
    copied = 0
    for edge in reader(source_entity_id) or []:
        rel_type = edge.get("type") or ""
        if rel_type not in ("relation", "membership"):
            continue
        # The reader hands back the edge's own key and its *resolved* contact, not
        # the raw `_to` — `id` is the anchor a relationship-anchored instance
        # points at, and the far end must be a real id to write a new edge with.
        to_id = edge.get("contact_id") or ""
        source_key = edge.get("id") or ""
        if not to_id:
            continue
        created = repo.create_relationship(new_entity_id, to_id, rel_type,
                                           edge.get("description") or "")
        copied += 1
        new_key = created.get("_key", "") if isinstance(created, dict) else ""
        if not new_key or not source_key:
            continue
        get_edge_traits = getattr(repo, "get_relationship_traitsettings", None)
        for source in (get_edge_traits(source_key) if get_edge_traits else []) or []:
            from transversal.services.effects_applier.trait_helpers import _allow_duplicates
            resolve = getattr(repo, "resolve_traitsetting_id", None)
            new_id = (resolve(new_key, source.trait_id, source.statement,
                              _allow_duplicates(source.trait_id, repo))
                      if resolve is not None else f"{new_key}:{source.trait_id}")
            repo.create_traitsetting(source.model_copy(update={
                "id": new_id,
                "entity_id": new_key,
                "projection_id": None,
                "parent_traitsetting_id": None,
            }))
    return copied


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
    # A ref a resolver has **already settled** is still a scope: `resolve_refs`
    # clears the spec and writes the value, so reading only the spec lost the
    # author's narrowing and quietly fell back to "any body in the destination
    # universe" — reusing the most recent body *outside* the scope asked for. The
    # value is taken only when the repository knows it as a body, so a literal like
    # `self` still falls through to the universe pool ([[B261]]).
    if ref is not None and ref.value:
        get_projection = getattr(repo, "get_projection", None)
        if get_projection is not None and get_projection(ref.value) is not None:
            return [ref.value]
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
        target = target_value(effect).strip()
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

    def _place_body(proj, location_id: str) -> None:
        """Move a body to the destination and relabel its crossing.

        ``_arrive_in_body`` sets the entity's location from the **body's**, so a body
        that is not moved first lands the traveller wherever that body already sat —
        and an unplaced body lands them **nowhere** (``current_location = None``,
        while the response still reports a location name). ``{closest_projection}``
        always did this; the reuse and literal policies did not, which is why a
        consciousness transversal arrived nobody (mcp-architect, 2026-09-24).

        ``NATIVE`` means *home*: it is what ``is_transversal`` counts, and what makes
        a universe live for the entity. A body back in its origin universe is native
        again; one standing in a foreign universe is there by consciousness, exactly
        as the inapposite branch labels its own crossing.
        """
        proj.current_location = location_id
        proj.universe = dest_universe
        proj.transversal_type = (
            TransversalType.NATIVE
            if dest_universe == proj.origin_universe
            else TransversalType.CONSCIOUSNESS
        )

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
        _place_body(proj, location_id)
        return proj

    # A literal projection id is a resolved ``{choose_projection}``.
    if projection_policy not in ("{last_projection}", "{new_projection}", "{random_projection}", "{choose_projection}", "{closest_projection}"):
        proj = repo.get_projection(projection_policy)
        # **An unplaced body is not a place.** Arriving in one leaves the entity with
        # no location at all while the response still names a destination, so a body
        # that is nowhere falls through to a fresh one — the same fallback
        # `_closest_body` takes when it cannot rank a body (mcp-architect,
        # 2026-09-24).
        if proj is not None and proj.current_location:
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
            if proj is not None and proj.current_location:
                # A **placed** body is where you land: a reuse policy means "go where
                # your body already is", and the destination has only chosen the
                # universe — the contract the suite pins. What it must not do is
                # arrive in a body that is **nowhere**: that left the entity with
                # `current_location = None` while the response still reported a
                # destination (mcp-architect, 2026-09-24), so an unplaced body falls
                # through to a fresh one below.
                _arrive_in_body(proj)
                return
        projection_policy = "{new_projection}"  # no usable body → spawn at the destination

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
    """Someone learns about the effect's target ([[B121]]).

    **`known_to` is an audience, not a memory.** The author, 2026-09-27: *"If entity
    A has entity B in its known_to, that means that entity B knows entity A, not
    necessarily that entity A knows entity B."* So the id is written on the entity
    being **learned about**, naming who now knows it — the same direction the trait
    field has always had, and the same direction the persistent index on
    ``known_to[*]`` is for. The earlier reading (the learner's own list, "what I
    know") was the other way round and is corrected here.

    A **union**, never a replace: the id joins ``known_to`` only if it is not
    already there, so a rule that fires twice — or a second rule that teaches
    something adjacent — cannot wipe the list. That is the whole reason this is
    an action rather than a field write: knowledge is monotonic, and the GM
    assuming a hidden occupant must not forget who already knew them.

    **Two questions, so two declarations:** *who learns* is the ``learner``
    reference — a targeting path, so "everyone with him" is sayable — and *which
    entity they learn about* is the target. An empty learner means the entity the
    effect lands on (the subject). A path fans out before it reaches here, so
    "every occupant of my location" arrives as one call per person and the
    membership check does the dedupe. An entity is never made known to itself.
    """
    subject = _effect_subject(entity, effect, result, repo)
    if subject is None:
        return
    _track_subject(result, entity, subject)

    learned_id = _resolve_target(subject, effect, result, repo)
    if not learned_id:
        result.applied.append(AppliedEffect(effect, "no entity named to learn about"))
        return
    learned = subject if learned_id == subject.id else (
        repo.get_entity(learned_id) if repo is not None else None)
    if learned is None:
        result.applied.append(AppliedEffect(effect, f"no entity {learned_id} to learn about"))
        return
    # It is the *learned-about* entity that is written, so it is the one that has
    # to be tracked: `commit_effects` persists the primary entity plus everything
    # in `entities_to_update`, and nothing else. An untracked write here would be
    # mutated in memory and silently never saved.
    _track_subject(result, entity, learned)
    learned_label = learned.name or learned.id

    for learner_id in _resolve_learners(entity, effect, repo, result, default=[subject.id]):
        # The subject is already in hand and need not be in the repo — the default
        # learner is usually the acting entity, which a test's fake repo may not hold.
        learner = subject if learner_id == subject.id else (
            repo.get_entity(learner_id) if repo is not None else None)
        if learner is None:
            result.applied.append(AppliedEffect(effect, f"no entity {learner_id} to learn it"))
            continue
        learner_label = learner.name or learner.id
        if learner_id == learned.id:
            result.applied.append(AppliedEffect(
                effect, f"{learner_label} already knows itself"))
            continue
        known = list(getattr(learned, "known_to", None) or [])
        if learner_id in known:
            result.applied.append(AppliedEffect(
                effect, f"{learner_label} already knows {learned_label}"))
            continue
        learned.known_to = [*known, learner_id]
        result.applied.append(AppliedEffect(
            effect, f"{learner_label} learns {learned_label}"))
