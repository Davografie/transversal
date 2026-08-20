"""Directional contest-target bans.

A conceder gains a temporary ban preventing them from re-challenging the
entity they gave in to.  Bans live on the entity document (``targeting_bans``)
as plain membership markers; their expiry is driven by a scheduled event
(``entity/remove_targeting_ban``) via the unified scheduled-events system.
"""

from __future__ import annotations

from typing import Optional

from transversal.domain import Entity, TargetingBan


def active_target_ids(entity: Optional[Entity]) -> list[str]:
    """Return the ids the entity currently cannot target."""
    if entity is None:
        return []
    return [b.target_id for b in (entity.targeting_bans or [])]


def has_targeting_ban(entity: Optional[Entity], target_id: str) -> bool:
    """True if ``entity`` currently has an active ban against ``target_id``."""
    if entity is None:
        return False
    return any(b.target_id == target_id for b in (entity.targeting_bans or []))


def apply_targeting_ban(entity: Entity, target_id: str) -> None:
    """Add (or refresh) a directional ban on ``entity`` toward ``target_id``."""
    entity.targeting_bans = [
        b for b in (entity.targeting_bans or []) if b.target_id != target_id
    ]
    entity.targeting_bans.append(TargetingBan(target_id=target_id))


def remove_targeting_ban(entity: Entity, target_id: str) -> None:
    """Remove the directional ban on ``entity`` toward ``target_id`` (idempotent)."""
    entity.targeting_bans = [
        b for b in (entity.targeting_bans or []) if b.target_id != target_id
    ]


def clear_taken_out(repo) -> int:
    """Clear the scene-scoped taken-out state from every entity.

    Returns the number of entities that were taken out.
    """
    changed = 0
    for entity in repo.list_all_entities():
        if entity.taken_out:
            entity.taken_out = False
            repo.update_entity(entity)
            changed += 1
    return changed
