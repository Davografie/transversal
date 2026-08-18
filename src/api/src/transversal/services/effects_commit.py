"""Commit applied effects — persist in-memory mutations and broadcast SSE.

This is the "repo-first" half of the effects contract: `apply_effects` mutates
in-memory models and returns the delta; this module persists that delta through
the repository and publishes SSE so the UI live-updates. It does not re-load
entities by id, so the in-memory entity stays authoritative.
"""

from __future__ import annotations

from transversal.api.sse.bus import StreamEvent, event_bus
from transversal.domain import Effect, Entity
from transversal.services.effects_applier import EffectsResult, apply_effects
from transversal.services.session_manager import session_manager
from transversal.services.state_events import fire_state_sfx


def _publish(event: str, data: dict) -> None:
    for s in session_manager.list_active():
        event_bus.publish(StreamEvent(event=event, session_id=s.id, data=data))


def commit_effects(entity: Entity, effects: list[Effect], repo) -> EffectsResult:
    """Apply effects in-memory, then persist and broadcast.

    Returns the EffectsResult so callers can report what was applied. The caller
    is responsible for having loaded a fresh `entity`; this function persists the
    mutated entity plus any produced trait settings and relationship edges.
    """
    old_razmerit = entity.razmerit
    result = apply_effects(entity, effects, repo)

    # Other entities mutated (e.g. razmerit transfer recipient).
    for other in result.entities_to_update:
        repo.update_entity(other)
        _publish("entity_updated", {
            "entity_id": other.id,
            "name": other.name,
            "current_universe": other.current_universe,
            "current_location": other.current_location,
        })

    # The primary entity.
    if result.applied:
        repo.update_entity(entity)
        _publish("entity_updated", {
            "entity_id": entity.id,
            "name": entity.name,
            "current_universe": entity.current_universe,
            "current_location": entity.current_location,
        })
        if entity.razmerit != old_razmerit:
            _publish("razmerit_changed", {
                "entity_id": entity.id,
                "old_balance": old_razmerit,
                "new_balance": entity.razmerit,
                "reason": "effect",
            })

    # Trait settings produced by the applier.
    for ts in result.new_trait_settings:
        repo.create_traitsetting(ts)
        _publish("trait_updated", {"entity_id": ts.entity_id, "trait_id": ts.trait_id})
        fire_state_sfx(ts.entity_id, entity.current_universe, "trait_updated",
                       {"trait_id": ts.trait_id, "traitset_id": ts.traitset_id})
    for ts in result.updated_trait_settings:
        repo.update_traitsetting(ts)
        _publish("trait_updated", {"entity_id": ts.entity_id, "trait_id": ts.trait_id})
        fire_state_sfx(ts.entity_id, entity.current_universe, "trait_updated",
                       {"trait_id": ts.trait_id, "traitset_id": ts.traitset_id})

    # Relationship edges produced by the applier.
    for rel in result.new_relationships:
        repo.create_relationship(
            rel["from"], rel["to"], rel["type"], rel.get("description", ""),
        )
        fire_state_sfx(rel["from"], entity.current_universe, "relationship_created",
                       {"target": rel["to"], "type": rel["type"]})

    return result
