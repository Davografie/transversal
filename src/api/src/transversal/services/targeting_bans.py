"""Directional contest-target bans.

A conceder gains a temporary ban preventing them from re-challenging the
entity they gave in to.  Bans live on the entity document (``targeting_bans``)
and count down one per scene.  This module is deliberately small and
effect-friendly: :func:`apply_targeting_ban` is the mutation the effect
handler calls, and :func:`decrement_scene_bans` is the scene-advance expiry.
"""

from __future__ import annotations

from typing import Optional

from transversal.domain import Entity, TargetingBan


def active_target_ids(entity: Optional[Entity]) -> list[str]:
    """Return the ids the entity currently cannot target."""
    if entity is None:
        return []
    return [b.target_id for b in (entity.targeting_bans or []) if b.scenes_remaining > 0]


def has_targeting_ban(entity: Optional[Entity], target_id: str) -> bool:
    """True if ``entity`` currently has an active ban against ``target_id``."""
    if entity is None:
        return False
    return any(
        b.target_id == target_id and b.scenes_remaining > 0
        for b in (entity.targeting_bans or [])
    )


def apply_targeting_ban(entity: Entity, target_id: str, scenes: int = 1) -> None:
    """Add (or refresh) a directional ban on ``entity`` toward ``target_id``."""
    entity.targeting_bans = [
        b for b in (entity.targeting_bans or []) if b.target_id != target_id
    ]
    entity.targeting_bans.append(TargetingBan(target_id=target_id, scenes_remaining=max(1, scenes)))


def decrement_scene_bans(repo) -> int:
    """Advance every entity's targeting bans by one scene.

    Removes bans that expire and decrements the rest.  Returns the number of
    entities whose bans changed.
    """
    changed_entities = 0
    for entity in repo.list_all_entities():
        if not entity.targeting_bans:
            continue
        kept: list[TargetingBan] = []
        changed = False
        for ban in entity.targeting_bans:
            if ban.scenes_remaining <= 1:
                changed = True  # expires this scene
            else:
                ban.scenes_remaining -= 1
                kept.append(ban)
                changed = True
        if changed:
            entity.targeting_bans = kept
            repo.update_entity(entity)
            changed_entities += 1
    return changed_entities


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
