"""Commit applied effects — persist in-memory mutations and broadcast SSE.

This is the "repo-first" half of the effects contract: `apply_effects` mutates
in-memory models and returns the delta; this module persists that delta through
the repository and publishes SSE so the UI live-updates. It does not re-load
entities by id, so the in-memory entity stays authoritative.
"""

from __future__ import annotations

from transversal.api.sse.bus import StreamEvent, event_bus
from transversal.domain import ArrivalKind, Effect, Entity, dice_list_to_rating
from transversal.services.effects_applier import EffectsResult, apply_effects
from transversal.services.effects_applier.datatypes import EFFECT_NOTES_CONTEXT_KEY
from transversal.services.scene_state import resync_pool_dice_for_trait
from transversal.services.session_manager import session_manager


def _publish(event: str, data: dict) -> None:
    for s in session_manager.list_active():
        event_bus.publish(StreamEvent(event=event, session_id=s.id, data=data))


def _publish_trait_changed(ts, universe: str) -> None:
    """Publish an enriched trait_updated + re-sync any assembled pool dice."""
    new_rating = dice_list_to_rating(ts.dice)
    new_dice = [d.value for d in ts.dice]
    _publish("trait_updated", {
        "entity_id": ts.entity_id,
        "trait_id": ts.trait_id,
        "trait_setting_id": ts.id,
        "new_rating": new_rating,
        "new_dice": new_dice,
    })
    resync_pool_dice_for_trait(ts.entity_id, ts.id, new_dice)
    from transversal.services.scheduled_events import dispatch_event
    # The *instance*, not just the registry trait: several settings can share one
    # generic trait — an agenda's steps all instantiate "grim portent" — so a
    # `trait` alone cannot tell step 3 from step 5. The SSE payload above always
    # carried it; the effects context dropped it.
    dispatch_event(None, "trait_updated", entity_id=ts.entity_id, universe=universe,
                   context={"trait": ts.trait_id, "trait_setting": ts.id})


def _publish_trait_removed(ts, universe: str) -> None:
    """Tell clients a trait instance is gone ([[B74]]).

    A removal had **no** broadcast at all, so a sheet that was already open kept
    rendering the trait an effect had taken away until something else forced a
    refetch — the visible half of "the sheet live-updates when an SFX changes
    traits". The event is the same one the client already handles (`trait_updated`
    → refetch the sheet, and re-sync that die), with the dice emptied: the trait's
    identity is what the client keys on, and `new_dice: []` clears the assembled
    pool's die for it.

    Deliberately **not** dispatched to the effects engine: a rule that reacts to
    "this trait changed" would be handed an instance that no longer exists. If a
    rule ever needs the removal moment, it wants its own event, not this one.
    """
    _publish("trait_updated", {
        "entity_id": ts.entity_id,
        "trait_id": ts.trait_id,
        "trait_setting_id": ts.id,
        "new_rating": None,
        "new_dice": [],
        "removed": True,
    })
    resync_pool_dice_for_trait(ts.entity_id, ts.id, [])


def commit_effects(entity: Entity, effects: list[Effect], repo, context: dict | None = None, source=None, source_element: str | None = None, arrival_kind: str | None = None) -> EffectsResult:
    """Apply effects in-memory, then persist and broadcast.

    Returns the EffectsResult so callers can report what was applied. The caller
    is responsible for having loaded a fresh `entity`; this function persists the
    mutated entity plus any produced trait settings and relationship edges.

    ``arrival_kind`` only matters when the effects *move* the entity: it labels
    how they arrived (see :class:`ArrivalKind`). Defaults to ``effect`` — an
    effect moved them — which a caller that knows better (a portal, say) overrides.
    """
    old_razmerit = entity.razmerit
    old_location = entity.current_location
    old_universe = entity.current_universe
    old_total_bonus = entity.total_dice_bonus
    old_effect_bonus = entity.effect_dice_bonus
    old_hitch_threshold = entity.hitch_threshold
    result = apply_effects(entity, effects, repo, context, source=source, source_element=source_element)

    # What each effect did, or why it did nothing, onto the activation's sink when
    # there is one ([[B236]]). Every refusal already carries a reason on
    # ``AppliedEffect.summary``; without this it died here, one layer below the wire.
    notes = context.get(EFFECT_NOTES_CONTEXT_KEY) if isinstance(context, dict) else None
    if notes is not None:
        for record in result.applied:
            applied_effect = getattr(record, "effect", None)
            notes.append({
                "type": getattr(applied_effect, "type", ""),
                "action": getattr(applied_effect, "action", ""),
                "target": getattr(applied_effect, "target", ""),
                "note": getattr(record, "summary", ""),
            })

    # Other entities mutated (e.g. razmerit transfer recipient).
    for other in result.entities_to_update:
        repo.update_entity(other)
        _publish("entity_updated", {
            "entity_id": other.id,
            "name": other.name,
            "current_universe": other.current_universe,
            "current_location": other.current_location,
            "taken_out": other.taken_out,
        })

    # The primary entity.
    if result.applied:
        repo.update_entity(entity)
        _publish("entity_updated", {
            "entity_id": entity.id,
            "name": entity.name,
            "current_universe": entity.current_universe,
            "current_location": entity.current_location,
            "taken_out": entity.taken_out,
        })
        if entity.razmerit != old_razmerit:
            _publish("razmerit_changed", {
                "entity_id": entity.id,
                "old_balance": old_razmerit,
                "new_balance": entity.razmerit,
                "reason": "effect",
            })

    # How the pool *reads* changed — the selection limits, or which faces hitch —
    # so tell the roller to re-read rather than keep drawing the old rules
    # ([[B231]] rides this same event: a widened hitch range is a drawing change).
    if (entity.total_dice_bonus != old_total_bonus
            or entity.effect_dice_bonus != old_effect_bonus
            or entity.hitch_threshold != old_hitch_threshold):
        _publish("dice_limits_changed", {
            "entity_id": entity.id,
            "total_dice_bonus": entity.total_dice_bonus,
            "effect_dice_bonus": entity.effect_dice_bonus,
            "hitch_threshold": entity.hitch_threshold,
        })

    # Projections produced/updated by travel effects.
    for proj in result.new_projections:
        repo.create_projection(proj)
        from transversal.services.state_events import fire_projection_created
        fire_projection_created(proj.entity_id, proj.universe, proj.id)
    for proj in result.updated_projections:
        repo.update_projection(proj)
    for proj in result.removed_projections:
        repo.delete_projection(proj.id)

    if entity.current_location != old_location or entity.current_universe != old_universe:
        kind = str(getattr(arrival_kind, "value", arrival_kind) or ArrivalKind.EFFECT.value)
        _publish("location_changed", {
            "entity_id": entity.id,
            "name": entity.name,
            "from": old_location or "",
            "to": entity.current_location or "",
            "universe": entity.current_universe,
            "arrival_kind": kind,
        })
        from transversal.services.scheduled_events import dispatch_event
        dispatch_event(repo, "location_changed", entity_id=entity.id, universe=entity.current_universe,
                       context={"from_location": old_location, "to_location": entity.current_location,
                                "universe": entity.current_universe, "arrival_kind": kind})

    # Trait settings produced by the applier.
    for ts in result.new_trait_settings:
        repo.create_traitsetting(ts)
        _publish_trait_changed(ts, entity.current_universe)
    for ts in result.updated_trait_settings:
        repo.update_traitsetting(ts)
        _publish_trait_changed(ts, entity.current_universe)
    for ts in result.removed_trait_settings:
        repo.delete_traitsetting(ts.id)
        _publish_trait_removed(ts, entity.current_universe)

    # Trait-set settings (limit overrides) produced by the applier.
    for tss in result.new_traitsetsettings:
        repo.create_traitsetsetting(tss)
    for tss in result.updated_traitsetsettings:
        repo.update_traitsetsetting(tss)

    # Fog-of-war reveals: persist known_to changes and tell viewers to refetch.
    if result.revealed:
        revealed_ids = []
        for ts, learner_id in result.revealed:
            repo.update_traitsetting(ts)
            revealed_ids.append(ts.id)
        _publish("traits_revealed", {
            "owner_id": result.revealed[0][0].entity_id,
            "learner_ids": [learner_id for _, learner_id in result.revealed],
            "trait_setting_ids": revealed_ids,
        })
        from transversal.services.trait_reveal import fire_on_trait_learn
        for ts, learner_id in result.revealed:
            fire_on_trait_learn(ts.entity_id, learner_id, ts.trait_id, ts.id)

    # Relationship edges produced by the applier.
    for rel in result.new_relationships:
        repo.create_relationship(
            rel["from"], rel["to"], rel["type"], rel.get("description", ""),
        )
        from transversal.services.scheduled_events import dispatch_event
        dispatch_event(None, "relationship_created", entity_id=rel["from"], universe=entity.current_universe,
                       context={"target_entity": rel["to"], "relationship_type": rel["type"]})

    return result
