"""Per-location contest pool tracker.

Dice pools are assembled per location/scene so players can build a contest
in one location, navigate elsewhere, and return to continue assembling.
Each (location_id, entity_id) pair has one active PoolAssembly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from transversal.domain import (
    ContestResult,
    DicePoolRequest,
    DieType,
    PoolAssembly,
)
from transversal.services.dice_resolver import resolve_contest


@dataclass
class ContestTracker:
    """Tracks dice pool assemblies per location.

    Thread-safe for a single session.  Not persisted across server restarts
    — pools are beat-scoped and ephemeral by design.
    """

    _assemblies: dict[str, dict[str, PoolAssembly]] = field(default_factory=dict)
    #                  location_id → {entity_id → PoolAssembly}

    # ── Assembly management ─────────────────────────────

    def get_or_create(
        self, location_id: str, entity_id: str, universe: str
    ) -> PoolAssembly:
        """Return the existing assembly for (location, entity) or create one."""
        if location_id not in self._assemblies:
            self._assemblies[location_id] = {}
        loc = self._assemblies[location_id]
        if entity_id not in loc:
            loc[entity_id] = PoolAssembly(
                entity_id=entity_id,
                location_id=location_id,
                universe=universe,
            )
        return loc[entity_id]

    def get(self, location_id: str, entity_id: str) -> Optional[PoolAssembly]:
        """Return the assembly if it exists, None otherwise."""
        return self._assemblies.get(location_id, {}).get(entity_id)

    def add_die(
        self, location_id: str, entity_id: str, die: DieType, source: str, universe: str
    ) -> PoolAssembly:
        """Add a die to an entity's pool at a location."""
        pa = self.get_or_create(location_id, entity_id, universe)
        pa.dice.append((die, source))
        return pa

    def remove_die(
        self, location_id: str, entity_id: str, index: int
    ) -> PoolAssembly:
        """Remove a die by index from an entity's pool."""
        pa = self._assemblies.get(location_id, {}).get(entity_id)
        if pa is None:
            raise KeyError(f"No pool assembly for entity '{entity_id}' at location '{location_id}'")
        if 0 <= index < len(pa.dice):
            pa.dice.pop(index)
        return pa

    def clear_pool(self, location_id: str, entity_id: str) -> None:
        """Reset an entity's pool at a location (end of beat)."""
        loc = self._assemblies.get(location_id)
        if loc and entity_id in loc:
            del loc[entity_id]

    def clear_location(self, location_id: str) -> None:
        """Reset all pools at a location (scene end)."""
        self._assemblies.pop(location_id, None)

    def set_opposition(
        self, location_id: str, entity_id: str, opponent_id: str, universe: str
    ) -> PoolAssembly:
        """Designate an opponent for the entity's pool at this location."""
        pa = self.get_or_create(location_id, entity_id, universe)
        pa.opposition_entity_id = opponent_id
        return pa

    def set_pushed(self, location_id: str, entity_id: str) -> None:
        """Mark that the entity has pushed this beat."""
        loc = self._assemblies.get(location_id, {})
        pa = loc.get(entity_id)
        if pa:
            pa.pushed_this_beat = True

    # ── Assembly queries ────────────────────────────────

    def get_pools_at(self, location_id: str) -> dict[str, PoolAssembly]:
        """Return all pool assemblies at a location."""
        return dict(self._assemblies.get(location_id, {}))

    def get_opposition_pools(
        self, location_id: str, entity_id: str
    ) -> tuple[Optional[PoolAssembly], Optional[PoolAssembly]]:
        """Return (entity_pool, opponent_pool) for a potential contest."""
        entity_pool = self.get(location_id, entity_id)
        if entity_pool is None or entity_pool.opposition_entity_id is None:
            return (entity_pool, None)
        opponent_pool = self.get(location_id, entity_pool.opposition_entity_id)
        return (entity_pool, opponent_pool)

    def get_contestants(
        self, location_id: str, entity_id: str
    ) -> tuple[Optional[PoolAssembly], Optional[PoolAssembly]]:
        """Return (challenger_pool, defendant_pool) for the contest that
        ``entity_id`` is involved in, regardless of which side it is.

        The challenger (initiator) is the entity whose pool carries
        ``opposition_entity_id``; the defendant is that target. If
        ``entity_id`` is the defendant, we look up who challenged them.
        """
        pools = self._assemblies.get(location_id, {})
        entity_pool = pools.get(entity_id)
        if entity_pool is None:
            return (None, None)

        if entity_pool.opposition_entity_id:
            challenger = entity_pool
            defendant = pools.get(entity_pool.opposition_entity_id)
        else:
            challenger = next(
                (pa for pa in pools.values() if pa.opposition_entity_id == entity_id),
                None,
            )
            defendant = entity_pool
        return (challenger, defendant)

    def can_resolve(self, location_id: str, entity_id: str) -> bool:
        """Check if both sides have dice assembled for a contest."""
        challenger, defendant = self.get_contestants(location_id, entity_id)
        if challenger is None or defendant is None:
            return False
        return len(challenger.dice) > 0 and len(defendant.dice) > 0

    # ── Resolution ──────────────────────────────────────

    def resolve(
        self, location_id: str, entity_id: str
    ) -> Optional[ContestResult]:
        """Resolve a contest between a challenger and its defendant.

        ``entity_id`` may be either side; ties favor the challenger
        (initiator) regardless of which side triggered the resolve.

        Returns None if either side hasn't assembled a pool yet.
        """
        challenger, defendant = self.get_contestants(location_id, entity_id)
        if challenger is None or defendant is None:
            return None
        if not challenger.dice or not defendant.dice:
            return None

        challenger_req = DicePoolRequest(
            entity_id=challenger.entity_id,
            universe=challenger.universe,
            dice=list(challenger.dice),
            razmerit_spent=challenger.razmerit_spent,
        )
        defendant_req = DicePoolRequest(
            entity_id=defendant.entity_id,
            universe=defendant.universe,
            dice=list(defendant.dice),
            razmerit_spent=defendant.razmerit_spent,
        )

        result = resolve_contest(challenger_req, defendant_req)
        result.pushed = challenger.pushed_this_beat

        return result

    def push_contest(
        self, location_id: str, entity_id: str,
        new_dice: list[tuple[DieType, str]],
    ) -> Optional[ContestResult]:
        """Push after a failed/tied contest: reassemble and reroll.

        Only one push per beat.  Costs 1 razmerit (enforced by caller via
        the effects engine — the tracker only checks availability).

        Args:
            location_id: Where the contest is happening.
            entity_id: The pushing entity.
            new_dice: The reassembled dice pool (can differ from original).
        """
        entity_pool, opponent_pool = self.get_opposition_pools(location_id, entity_id)
        if entity_pool is None or opponent_pool is None:
            return None
        if entity_pool.pushed_this_beat:
            return None  # already pushed this beat

        # Update the entity's pool with new dice
        entity_pool.dice = list(new_dice)
        entity_pool.pushed_this_beat = True

        return self.resolve(location_id, entity_id)


# Singleton for the session
_contest_tracker: Optional[ContestTracker] = None


def get_contest_tracker() -> ContestTracker:
    global _contest_tracker
    if _contest_tracker is None:
        _contest_tracker = ContestTracker()
    return _contest_tracker


# ── SSE Broadcasting ──────────────────────────────────

def _pool_to_dict(pa: PoolAssembly) -> dict:
    """Serialize a PoolAssembly for SSE broadcast."""
    return {
        "entity_id": pa.entity_id,
        "location_id": pa.location_id,
        "universe": pa.universe,
        "dice": [{"die": d.value, "source": s} for d, s in pa.dice],
        "opposition_entity_id": pa.opposition_entity_id,
        "pushed_this_beat": pa.pushed_this_beat,
        "razmerit_spent": pa.razmerit_spent,
    }


def broadcast_pool_change(location_id: str, entity_id: str) -> None:
    """Publish a pool_updated SSE event to all active sessions.

    Call this after any mutation to the contest tracker so clients can
    update their pool-dice display near character avatars.

    Payload format matches the frontend's existing pool_updated handler:
      { player_id, entity_id, dice, phase, location_id }
    """
    from transversal.api.sse.bus import StreamEvent, event_bus
    from transversal.services.session_manager import session_manager

    tracker = get_contest_tracker()
    pa = tracker.get(location_id, entity_id)

    if pa and pa.dice:
        dice = [d.value for d, _ in pa.dice]
    else:
        dice = []

    for s in session_manager.list_active():
        event_bus.publish(StreamEvent(
            event="pool_updated",
            session_id=s.id,
            data={
                "player_id": entity_id,
                "entity_id": entity_id,
                "dice": dice,
                "phase": "adding",
                "location_id": location_id,
            },
        ))
