"""Per-location contest state tracker.

Dice pools live in :mod:`transversal.services.scene_state` (the single
source of truth for pools).  This tracker owns only the *contest*
metadata — who is opposing whom, whether a side has pushed this beat, and
razmerit spent.  Resolution reads dice from the shared scene store.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from transversal.domain import (
    CommittedResult,
    ContestOutcome,
    ContestResult,
    ContestWinner,
    DicePoolRequest,
)
from transversal.services.dice_resolver import compare_committed, resolve_contest


@dataclass
class ContestState:
    """Contest metadata for one entity at one location.

    The actual dice are stored in the scene store under the same
    ``(location_id, entity_id)`` key.  ``committed`` is this side's frozen
    result once they roll + pick and press Set.
    """

    entity_id: str
    location_id: str
    universe: str
    opposition_entity_id: Optional[str] = None
    pushed_this_beat: bool = False
    razmerit_spent: int = 0
    committed: Optional[CommittedResult] = None
    gave_in: bool = False


@dataclass
class ContestTracker:
    """Tracks contest metadata per location.

    Thread-safe for a single session.  Not persisted across server restarts
    — contests are beat-scoped and ephemeral by design.
    """

    _contests: dict[str, dict[str, ContestState]] = field(default_factory=dict)
    #                  location_id → {entity_id → ContestState}

    # ── Metadata management ────────────────────────────

    def get_or_create(
        self, location_id: str, entity_id: str, universe: str
    ) -> ContestState:
        """Return the existing contest state for (location, entity) or create one."""
        if location_id not in self._contests:
            self._contests[location_id] = {}
        loc = self._contests[location_id]
        if entity_id not in loc:
            loc[entity_id] = ContestState(
                entity_id=entity_id,
                location_id=location_id,
                universe=universe,
            )
        return loc[entity_id]

    def get(self, location_id: str, entity_id: str) -> Optional[ContestState]:
        """Return the contest state if it exists, None otherwise."""
        return self._contests.get(location_id, {}).get(entity_id)

    def set_opposition(
        self, location_id: str, entity_id: str, opponent_id: str, universe: str
    ) -> ContestState:
        """Designate an opponent for the entity at this location (the challenge).

        Ensures the defendant has a contest state too, so either side can
        later commit a result or give in.
        """
        state = self.get_or_create(location_id, entity_id, universe)
        state.opposition_entity_id = opponent_id
        self.get_or_create(location_id, opponent_id, universe)
        return state

    def set_pushed(self, location_id: str, entity_id: str) -> None:
        """Mark that the entity has pushed this beat."""
        state = self._contests.get(location_id, {}).get(entity_id)
        if state:
            state.pushed_this_beat = True

    def clear_pool(self, location_id: str, entity_id: str) -> None:
        """Remove contest metadata for an entity at a location."""
        loc = self._contests.get(location_id)
        if loc and entity_id in loc:
            del loc[entity_id]

    def clear_location(self, location_id: str) -> None:
        """Remove all contest metadata at a location (scene end)."""
        self._contests.pop(location_id, None)

    # ── Metadata queries ───────────────────────────────

    def get_contests_at(self, location_id: str) -> dict[str, ContestState]:
        """Return all contest states at a location."""
        return dict(self._contests.get(location_id, {}))

    def get_contestants(
        self, location_id: str, entity_id: str
    ) -> tuple[Optional[ContestState], Optional[ContestState]]:
        """Return (challenger, defendant) for the contest that ``entity_id``
        is involved in, regardless of which side it is.

        The challenger (initiator) is the entity whose contest state
        carries ``opposition_entity_id``; the defendant is that target.
        If ``entity_id`` is the defendant, we look up who challenged them.
        """
        states = self._contests.get(location_id, {})
        entity_state = states.get(entity_id)

        # ``entity_id`` is the challenger.
        if entity_state is not None and entity_state.opposition_entity_id:
            opp_id = entity_state.opposition_entity_id
            defendant = states.get(opp_id) or ContestState(
                entity_id=opp_id,
                location_id=location_id,
                universe=entity_state.universe,
            )
            return (entity_state, defendant)

        # ``entity_id`` is (or may be) the defendant — find its challenger.
        challenger = next(
            (s for s in states.values() if s.opposition_entity_id == entity_id),
            None,
        )
        if challenger is None:
            if entity_state is not None:
                return (entity_state, None)
            return (None, None)

        defendant = entity_state or ContestState(
            entity_id=entity_id,
            location_id=location_id,
            universe=challenger.universe,
        )
        return (challenger, defendant)

    def can_resolve(
        self, location_id: str, entity_id: str, scene_store
    ) -> bool:
        """Check if both sides have dice assembled for a contest."""
        challenger, defendant = self.get_contestants(location_id, entity_id)
        if challenger is None or defendant is None:
            return False
        return bool(
            scene_store.get_pool(location_id, challenger.entity_id)
            and scene_store.get_pool(location_id, defendant.entity_id)
        )

    # ── Resolution ──────────────────────────────────────

    def resolve(
        self, location_id: str, entity_id: str, scene_store
    ) -> Optional[ContestResult]:
        """Resolve a contest between a challenger and its defendant.

        ``entity_id`` may be either side; ties favor the challenger
        (initiator) regardless of which side triggered the resolve.

        Dice are read from ``scene_store``.  Returns None if either side
        hasn't assembled a pool yet.
        """
        challenger, defendant = self.get_contestants(location_id, entity_id)
        if challenger is None or defendant is None:
            return None

        challenger_dice = scene_store.get_pool(location_id, challenger.entity_id)
        defendant_dice = scene_store.get_pool(location_id, defendant.entity_id)
        if not challenger_dice or not defendant_dice:
            return None

        challenger_req = DicePoolRequest(
            entity_id=challenger.entity_id,
            universe=challenger.universe,
            dice=challenger_dice,
            razmerit_spent=challenger.razmerit_spent,
        )
        defendant_req = DicePoolRequest(
            entity_id=defendant.entity_id,
            universe=defendant.universe,
            dice=defendant_dice,
            razmerit_spent=defendant.razmerit_spent,
        )

        result = resolve_contest(challenger_req, defendant_req)
        result.pushed = challenger.pushed_this_beat
        return result

    # ── Manual (concurrent) contest flow ────────────────

    def set_result(
        self,
        location_id: str,
        entity_id: str,
        committed: CommittedResult,
    ) -> Optional[ContestOutcome]:
        """Commit one side's rolled+picked result.

        When both sides have committed, returns the outcome; otherwise None
        (waiting for the other side).  The committed result is frozen.
        """
        challenger, defendant = self.get_contestants(location_id, entity_id)
        if challenger is None or defendant is None:
            return None

        if entity_id == challenger.entity_id:
            challenger.committed = committed
        else:
            defendant.committed = committed

        if challenger.committed is not None and defendant.committed is not None:
            return self._outcome(challenger, defendant, gave_in=None)
        return None

    def give_in(self, location_id: str, entity_id: str) -> Optional[ContestOutcome]:
        """Concede the contest — the other side wins."""
        challenger, defendant = self.get_contestants(location_id, entity_id)
        if challenger is None or defendant is None:
            return None
        if entity_id == challenger.entity_id:
            return self._outcome(challenger, defendant, gave_in=ContestWinner.PLAYER)
        return self._outcome(challenger, defendant, gave_in=ContestWinner.OPPONENT)

    def _outcome(
        self,
        challenger: ContestState,
        defendant: ContestState,
        gave_in: Optional[ContestWinner],
    ) -> ContestOutcome:
        if gave_in == ContestWinner.PLAYER:
            challenger.gave_in = True
            winner = ContestWinner.OPPONENT
        elif gave_in == ContestWinner.OPPONENT:
            defendant.gave_in = True
            winner = ContestWinner.PLAYER
        else:
            winner = compare_committed(challenger.committed, defendant.committed)  # type: ignore[arg-type]

        stakes = defendant.committed.effect_die if defendant.committed else None
        return ContestOutcome(
            winner=winner,
            challenger=challenger.committed,
            defendant=defendant.committed,
            stakes=stakes,
            gave_in=gave_in,
            pushed=challenger.pushed_this_beat,
        )

    def push_contest(
        self, location_id: str, entity_id: str, scene_store, new_dice: list[dict]
    ) -> Optional[ContestResult]:
        """Push after a failed/tied contest: reassemble and reroll.

        Only one push per beat.  Costs 1 razmerit (enforced by caller via
        the effects engine — the tracker only checks availability).

        Args:
            location_id: Where the contest is happening.
            entity_id: The pushing entity.
            scene_store: The shared pool store.
            new_dice: The reassembled dice pool (DieSpec wire dicts).
        """
        state = self.get(location_id, entity_id)
        if state is None:
            return None
        if state.pushed_this_beat:
            return None  # already pushed this beat

        scene_store.save_pool(location_id, entity_id, list(new_dice))
        state.pushed_this_beat = True
        return self.resolve(location_id, entity_id, scene_store)


# Singleton for the session
_contest_tracker: Optional[ContestTracker] = None


def get_contest_tracker() -> ContestTracker:
    global _contest_tracker
    if _contest_tracker is None:
        _contest_tracker = ContestTracker()
    return _contest_tracker


# ── SSE Broadcasting ──────────────────────────────────

def broadcast_pool_change(
    location_id: str,
    entity_id: str,
    dice: Optional[list[dict]] = None,
    phase: str = "adding",
) -> None:
    """Publish a pool_updated SSE event to all active sessions.

    ``dice`` is the DieSpec wire shape (list of dicts).  When omitted, the
    current pool is read from the shared scene store.

    Payload matches the frontend's pool_updated handler:
      { player_id, entity_id, dice, phase, location_id }
    """
    from transversal.api.sse.bus import StreamEvent, event_bus
    from transversal.services.scene_state import get_scene_store
    from transversal.services.session_manager import session_manager

    if dice is None:
        dice = get_scene_store().get_pool(location_id, entity_id)

    wire_dice = [d if isinstance(d, dict) else {"die": str(d)} for d in dice]

    for s in session_manager.list_active():
        event_bus.publish(StreamEvent(
            event="pool_updated",
            session_id=s.id,
            data={
                "player_id": entity_id,
                "entity_id": entity_id,
                "dice": wire_dice,
                "phase": phase,
                "location_id": location_id,
            },
        ))
