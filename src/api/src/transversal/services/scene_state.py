"""In-memory scene state: dice pools + difficulty, keyed by location + entity.

Ephemeral by design — it survives a client refresh or a same-user device
switch (the client re-fetches from the still-running server), but it is
intentionally lost on server restart. This is session/beat state, not history.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SceneStateStore:
    """Single source of truth for in-progress dice pools and difficulty.

    Keyed by (location_id, entity_id) — one pool per character per location.
    A player gets cross-device continuity from their stable player→entity
    claim, not from keying the pool by player.
    Dice are plain dicts of the wire shape::

        {"die": "d8", "source_kind": "trait", "source_id": "...",
         "label": "Hacking", "ts_id": "..."}
    """

    _pools: dict[str, dict[str, list[dict]]] = field(default_factory=dict)
    _difficulty: dict[str, int] = field(default_factory=dict)

    # ── Pools ─────────────────────────────────────────

    def save_pool(self, location_id: str, entity_id: str, dice: list[dict]) -> None:
        self._pools.setdefault(location_id, {})[entity_id] = dice

    def get_pool(self, location_id: str, entity_id: str) -> list[dict]:
        return list(self._pools.get(location_id, {}).get(entity_id, []))

    def clear_pool(self, location_id: str, entity_id: str) -> None:
        self._pools.get(location_id, {}).pop(entity_id, None)

    def clear_pools(self, location_id: str) -> None:
        """Clear every pool at a location (end of beat), keep difficulty."""
        self._pools.pop(location_id, None)

    def resync_trait_die(self, entity_id: str, trait_setting_id: str, new_dice: list[str]) -> list[tuple[str, str]]:
        """Update assembled pool dice referencing ``trait_setting_id``.

        A pool die is a live reference to its source trait until it is rolled.
        When the trait setting's rating changes, this re-syncs the still-open
        pool dice to ``new_dice`` — positionally, so a multi-die static trait
        (``[d10, d10]``) maps each new rating onto its matching pool die in
        order.  Returns the (location_id, entity_id) pairs that changed so the
        caller can broadcast.
        """
        new_dice = [d for d in new_dice if _SINGLE_DIE.match(d or "")]
        if not new_dice:
            return []
        touched: list[tuple[str, str]] = []
        for location_id, pools in self._pools.items():
            dice = pools.get(entity_id)
            if not dice:
                continue
            idx = 0
            for d in dice:
                if d.get("ts_id") == trait_setting_id:
                    if idx < len(new_dice) and d.get("die") != new_dice[idx]:
                        d["die"] = new_dice[idx]
                        if (location_id, entity_id) not in touched:
                            touched.append((location_id, entity_id))
                    idx += 1
        return touched

    def list_entities(self, location_id: str) -> list[str]:
        """Return entity ids with a saved pool at a location."""
        return list(self._pools.get(location_id, {}).keys())

    def get_pools_at(self, location_id: str) -> dict[str, list[dict]]:
        """Return {entity_id: dice} for every saved pool at a location."""
        return {
            eid: list(dice)
            for eid, dice in self._pools.get(location_id, {}).items()
        }

    # ── Difficulty ────────────────────────────────────

    def set_difficulty(self, location_id: str, difficulty: int) -> None:
        self._difficulty[location_id] = difficulty

    def get_difficulty(self, location_id: str) -> Optional[int]:
        return self._difficulty.get(location_id)

    # ── Lifecycle ─────────────────────────────────────

    def clear_location(self, location_id: str) -> None:
        self._pools.pop(location_id, None)
        self._difficulty.pop(location_id, None)


_store: Optional[SceneStateStore] = None


def get_scene_store() -> SceneStateStore:
    global _store
    if _store is None:
        _store = SceneStateStore()
    return _store


_SINGLE_DIE = re.compile(r"^d(4|6|8|10|12)$")


def resync_pool_dice_for_trait(entity_id: str, trait_setting_id: str, new_dice: list[str]) -> None:
    """Re-sync assembled pool dice after a trait setting's rating changes.

    Server-authoritative: when a trait steps up/down, the matching dice already
    in a pool must follow.  ``new_dice`` is the full post-change die array (one
    entry per pool die the trait contributes), mapped positionally onto the
    pool dice sharing ``trait_setting_id``.  Broadcasts ``pool_updated`` for
    each touched (location, entity) so clients re-sync.
    """
    store = get_scene_store()
    touched = store.resync_trait_die(entity_id, trait_setting_id, new_dice)
    for location_id, eid in touched:
        from transversal.services.contest_tracker import broadcast_pool_change
        broadcast_pool_change(location_id, eid, dice=store.get_pool(location_id, eid), phase="adding")
