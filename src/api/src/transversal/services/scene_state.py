"""In-memory scene state: dice pools + difficulty, keyed by location + entity.

Ephemeral by design — it survives a client refresh or a same-user device
switch (the client re-fetches from the still-running server), but it is
intentionally lost on server restart. This is session/beat state, not history.
"""

from __future__ import annotations

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
