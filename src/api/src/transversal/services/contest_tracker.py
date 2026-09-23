"""Per-location contest state tracker.

Dice pools live in :mod:`transversal.services.scene_state` (the single
source of truth for pools).  This tracker owns only the *contest*
metadata — who is opposing whom, whether a side has pushed this beat, and
razmerit spent.  Resolution reads dice from the shared scene store.
"""

from __future__ import annotations

import logging

from dataclasses import dataclass, field
from typing import Optional

from transversal.domain import (
    CommittedResult,
    ContestCompare,
    ContestOutcome,
    ContestResult,
    ContestWinner,
    DicePoolRequest,
    DieType,
    RollKind,
)
from transversal.services.dice_resolver import resolve_contest

logger = logging.getLogger("transversal.contest_tracker")


def _effect_rank(die: Optional[DieType]) -> int:
    if die is None:
        return 0
    return list(DieType).index(die)


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
    initiative: Optional[str] = None  # entity_id holding the current difficulty to beat
    pending_decision: Optional[str] = None  # entity_id that must give in or push
    high_stakes: bool = False
    pushed_this_loop: bool = False
    razmerit_spent: int = 0
    committed: Optional[CommittedResult] = None
    gave_in: bool = False
    # Whether this roll is a **test** or a **contest**. Not derivable from the
    # state after the fact — a pool that later gets opposed was still rolled as a
    # test — so the commit path records it where the flow is known: `set-opposition`
    # / `/set` mean a contest, `/resolve` means a test. Defaults to TEST, which is
    # what a state created by a pool save is.
    kind: RollKind = RollKind.TEST


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
        later commit a result or give in.  A challenge always starts a fresh
        contest: any committed result or give-in from a prior contest is
        cleared on both sides so it can't leak into the new one.
        """
        state = self.get_or_create(location_id, entity_id, universe)
        state.opposition_entity_id = opponent_id
        # Declaring a challenge is what makes this side's roll a contest.
        state.kind = RollKind.CONTEST
        state.committed = None
        state.gave_in = False
        state.initiative = None
        state.pending_decision = None
        state.high_stakes = False
        state.pushed_this_loop = False

        opponent = self.get_or_create(location_id, opponent_id, universe)
        opponent.committed = None
        opponent.gave_in = False
        opponent.initiative = None
        opponent.pending_decision = None
        opponent.high_stakes = False
        opponent.pushed_this_loop = False
        # Both sides are in the same contest, so both records say so — neither
        # side's `kind` may depend on which one was challenged.
        opponent.kind = RollKind.CONTEST
        return state

    def set_pushed(self, location_id: str, entity_id: str) -> None:
        """Mark that the entity has pushed this beat."""
        state = self._contests.get(location_id, {}).get(entity_id)
        if state:
            state.pushed_this_loop = True

    def set_stakes(self, location_id: str, entity_id: str, high_stakes: bool) -> bool:
        """Set the contest's stakes (low by default). Returns False if no contest."""
        challenger, defendant = self.get_contestants(location_id, entity_id)
        if challenger is None or defendant is None:
            return False
        challenger.high_stakes = high_stakes
        defendant.high_stakes = high_stakes
        return True

    def clear_pool(self, location_id: str, entity_id: str) -> None:
        """Remove contest metadata for an entity at a location."""
        loc = self._contests.get(location_id)
        if loc and entity_id in loc:
            del loc[entity_id]

    def clear_location(self, location_id: str) -> None:
        """Remove all contest metadata at a location (scene end)."""
        self._contests.pop(location_id, None)

    def clear_all(self) -> None:
        """Remove all contest metadata everywhere (scene end)."""
        self._contests.clear()

    # ── Metadata queries ───────────────────────────────

    def get_contests_at(self, location_id: str) -> dict[str, ContestState]:
        """Return all contest states at a location."""
        return dict(self._contests.get(location_id, {}))

    def list_all_contests(self) -> list[dict]:
        """Return one entry per active contest across all locations.

        A contest is identified by its challenger's ``opposition_entity_id``.
        Multi-party-ready: ``parties`` holds every competitor (today always
        two — resolution remains 1v1 — but the shape doesn't assume a pair).
        """
        result: list[dict] = []
        for location_id, states in self._contests.items():
            for entity_id, state in states.items():
                opponent = state.opposition_entity_id
                if not opponent:
                    continue
                defendant = states.get(opponent)
                result.append({
                    "location_id": location_id,
                    "challenger_id": entity_id,
                    "defendant_id": opponent,
                    "parties": [entity_id, opponent],
                    "pending": state.pending_decision,
                    "high_stakes": state.high_stakes,
                    "challenger_committed": state.committed is not None,
                    "defendant_committed": bool(defendant and defendant.committed is not None),
                })
        return result

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

        # Read the sides' dice-limit bonuses (base 0 when the entity/repo is
        # unavailable, e.g. in isolated unit tests).
        challenger_bonus = (0, 0)
        defendant_bonus = (0, 0)
        try:
            from transversal.main import _get_repo
            repo = _get_repo()
            ce = repo.get_entity(challenger.entity_id)
            de = repo.get_entity(defendant.entity_id)
            if ce is not None:
                challenger_bonus = (ce.total_dice_bonus or 0, ce.effect_dice_bonus or 0)
            if de is not None:
                defendant_bonus = (de.total_dice_bonus or 0, de.effect_dice_bonus or 0)
        except Exception:  # noqa: BLE001 - bonuses are best-effort at resolution
            pass

        challenger_req = DicePoolRequest(
            entity_id=challenger.entity_id,
            universe=challenger.universe,
            dice=challenger_dice,
            razmerit_spent=challenger.razmerit_spent,
            total_dice_bonus=challenger_bonus[0],
            effect_dice_bonus=challenger_bonus[1],
        )
        defendant_req = DicePoolRequest(
            entity_id=defendant.entity_id,
            universe=defendant.universe,
            dice=defendant_dice,
            razmerit_spent=defendant.razmerit_spent,
            total_dice_bonus=defendant_bonus[0],
            effect_dice_bonus=defendant_bonus[1],
        )

        result = resolve_contest(challenger_req, defendant_req)
        result.pushed = challenger.pushed_this_loop
        return result

    # ── Manual (concurrent) contest flow ────────────────

    def refresh_committed(
        self,
        location_id: str,
        entity_id: str,
        committed: CommittedResult,
    ) -> None:
        """Replace a side's committed result with an effect's adjusted one.

        ``CommittedResult`` says further *trait* changes do not touch it, and that
        stands. This is the one deliberate exception: an outcome effect (Step Up
        Effect) changes the roll's own effect die, and the comparison must be made
        on the value the table will see — one number per roll, not two.
        """
        state = self._contests.get(location_id, {}).get(entity_id)
        if state is not None:
            state.committed = committed

    def mark_kind(self, location_id: str, entity_id: str, kind: RollKind) -> None:
        """Record whether this roll is being resolved as a test or a contest.

        Called from the two commit endpoints, each of which knows the answer and
        neither of which could be derived from the other: `/set` commits a
        contest, `/resolve` commits a test. A state that does not exist yet is
        created, because "this was a test" is itself worth recording.
        """
        state = self._contests.get(location_id, {}).get(entity_id)
        if state is None:
            state = self.get_or_create(location_id, entity_id, "")
        state.kind = kind

    def store_committed(
        self,
        location_id: str,
        entity_id: str,
        committed: CommittedResult,
    ) -> bool:
        """Record one side's committed result **without** comparing.

        Split out so the set endpoint can store the raw result, let outcome
        effects rewrite it, and compare once afterwards. Returns whether a
        contest state existed to write to.
        """
        challenger, defendant = self.get_contestants(location_id, entity_id)
        if challenger is None or defendant is None:
            logger.info(f"[contest] store_committed no-contestants loc={location_id} entity={entity_id}")
            return False
        if entity_id == challenger.entity_id:
            challenger.committed = committed
        else:
            defendant.committed = committed
        # Committing *here* is what makes it a contest: this endpoint is reachable
        # only through the tracker's contest path (`/resolve` is the test path).
        if entity_id == challenger.entity_id:
            challenger.kind = RollKind.CONTEST
        else:
            defendant.kind = RollKind.CONTEST
        logger.info(
            f"[contest] store_committed loc={location_id} entity={entity_id} total={committed.total} "
            f"challenger_committed={challenger.committed is not None} defendant_committed={defendant.committed is not None}"
        )
        return True

    def set_result(
        self,
        location_id: str,
        entity_id: str,
        committed: CommittedResult,
    ) -> ContestOutcome | ContestCompare | None:
        """Commit one side's rolled+picked result, then compare if both are in.

        Returns:
          - ``ContestOutcome`` when both sides have committed and the
            attacker failed to beat the difficulty (the contest is over).
          - ``ContestCompare`` when the attacker beat the difficulty and the
            now-losing side must give in or push.
          - ``None`` while still waiting for the other side.
        """
        if not self.store_committed(location_id, entity_id, committed):
            return None
        return self.compare_if_ready(location_id, entity_id)

    def compare_if_ready(
        self,
        location_id: str,
        entity_id: str,
    ) -> ContestOutcome | ContestCompare | None:
        """Compare the two committed results, if both sides have set.

        Its own step because a compare is **not idempotent** — it flips
        initiative when the attacker beats the difficulty — so the set endpoint
        commits, lets outcome effects change the roll, and compares exactly once
        here, on the final value.
        """
        challenger, defendant = self.get_contestants(location_id, entity_id)
        if challenger is None or defendant is None:
            return None
        if challenger.committed is not None and defendant.committed is not None:
            return self._compare(challenger, defendant)
        return None

    def _set_initiative(
        self, challenger: ContestState, defendant: ContestState, holder_id: str
    ) -> None:
        challenger.initiative = holder_id
        defendant.initiative = holder_id

    def _compare(
        self, challenger: ContestState, defendant: ContestState
    ) -> ContestOutcome | ContestCompare:
        """Compare two committed results against the initiative model.

        The side holding initiative set the current difficulty; the other
        side (the attacker) must *strictly* beat it.  Ties go to the holder.
        """
        holder_id = challenger.initiative or challenger.entity_id  # round 1: challenger
        holder = challenger if holder_id == challenger.entity_id else defendant
        attacker = defendant if holder is challenger else challenger

        assert attacker.committed is not None
        assert holder.committed is not None
        attacker_total = attacker.committed.total
        holder_total = holder.committed.total

        if attacker_total > holder_total:
            # Attacker beat the difficulty: initiative flips, holder must decide.
            self._set_initiative(challenger, defendant, attacker.entity_id)
            pending = holder.entity_id
            challenger.pending_decision = pending
            defendant.pending_decision = pending
            logger.info(f"[contest] compare beat loc={challenger.location_id} pending={pending}")
            return ContestCompare(
                pending=pending,
                initiative=attacker.entity_id,
                challenger_id=challenger.entity_id,
                defendant_id=defendant.entity_id,
                challenger=challenger.committed,
                defendant=defendant.committed,
                margin=attacker_total - holder_total,
            )

        winner = ContestWinner.PLAYER if holder is challenger else ContestWinner.OPPONENT
        winner_state = challenger if winner == ContestWinner.PLAYER else defendant
        loser_state = defendant if winner == ContestWinner.PLAYER else challenger
        effect_die, taken_out = self._resolve_ramifications(
            winner_state, loser_state, challenger.high_stakes
        )
        challenger.pending_decision = None
        defendant.pending_decision = None
        logger.info(f"[contest] compare resolved loc={challenger.location_id} winner={winner.value}")
        return ContestOutcome(
            winner=winner,
            challenger=challenger.committed,
            defendant=defendant.committed,
            gave_in=None,
            pushed=challenger.pushed_this_loop,
            high_stakes=challenger.high_stakes,
            effect_die=effect_die,
            taken_out=taken_out,
        )

    def _resolve_ramifications(
        self, winner_state: ContestState, loser_state: ContestState, high_stakes: bool
    ) -> tuple[Optional[DieType], bool]:
        """Compute the effective complication die for the loser.

        Low stakes: winner's effect applies, stepped down one if it is not
        strictly larger than the loser's.  High stakes: winner's effect
        applies; if strictly larger, the loser is taken out.
        """
        winner_effect = winner_state.committed.effect_die if winner_state.committed else None
        loser_effect = loser_state.committed.effect_die if loser_state.committed else None
        winner_rank = _effect_rank(winner_effect)
        loser_rank = _effect_rank(loser_effect)

        if high_stakes:
            return winner_effect, winner_rank > loser_rank
        if winner_rank > loser_rank:
            return winner_effect, False
        return (winner_effect.step_down() if winner_effect else None), False

    def give_in(self, location_id: str, entity_id: str) -> Optional[ContestOutcome]:
        """Concede the contest — the other side wins.

        Post-compare, only the side that is pending may give in.  Before a
        compare (declining to oppose), the initiator must have committed.
        """
        challenger, defendant = self.get_contestants(location_id, entity_id)
        if challenger is None or defendant is None:
            logger.info(f"[contest] give_in no-contestants loc={location_id} entity={entity_id}")
            return None

        pending = challenger.pending_decision
        if pending is not None:
            if entity_id != pending:
                logger.info(f"[contest] give_in blocked (not pending) loc={location_id} entity={entity_id}")
                return None
        elif challenger.committed is None:
            logger.info(f"[contest] give_in blocked (initiator not committed) loc={location_id} entity={entity_id}")
            return None

        gave_in = ContestWinner.PLAYER if entity_id == challenger.entity_id else ContestWinner.OPPONENT
        outcome = self._give_in_outcome(challenger, defendant, gave_in)
        logger.info(f"[contest] give_in resolved loc={location_id} entity={entity_id} winner={outcome.winner.value}")
        return outcome

    def _give_in_outcome(
        self,
        challenger: ContestState,
        defendant: ContestState,
        gave_in: ContestWinner,
    ) -> ContestOutcome:
        if gave_in == ContestWinner.PLAYER:
            challenger.gave_in = True
            winner = ContestWinner.OPPONENT
            winner_state, loser_state = defendant, challenger
        else:
            defendant.gave_in = True
            winner = ContestWinner.PLAYER
            winner_state, loser_state = challenger, defendant
        challenger.pending_decision = None
        defendant.pending_decision = None
        # Conceding still applies a complication at the winner's effect die
        # (house rule): step down for low stakes when the winner's effect is
        # not strictly larger than the conceder's. Giving in never takes out.
        effect_die, _ = self._resolve_ramifications(
            winner_state, loser_state, challenger.high_stakes
        )
        return ContestOutcome(
            winner=winner,
            challenger=challenger.committed,
            defendant=defendant.committed,
            gave_in=gave_in,
            pushed=challenger.pushed_this_loop,
            high_stakes=challenger.high_stakes,
            effect_die=effect_die,
            taken_out=False,
        )

    def push(self, location_id: str, entity_id: str) -> Optional[dict]:
        """Start a push (continue): the pending side rebuilds and rerolls.

        Free (no razmerit).  Contests go back and forth until one side gives
        in or fails to beat the difficulty, so the pending side may push every
        round it is pending.  Clears the pusher's committed result so they can
        assemble and set a new one; the other side's committed result remains
        the difficulty to beat.
        """
        challenger, defendant = self.get_contestants(location_id, entity_id)
        if challenger is None or defendant is None:
            return None
        pending = challenger.pending_decision
        if pending is None or entity_id != pending:
            logger.info(f"[contest] push blocked (not pending) loc={location_id} entity={entity_id}")
            return None
        state = challenger if entity_id == challenger.entity_id else defendant
        state.committed = None
        challenger.pending_decision = None
        defendant.pending_decision = None
        logger.info(f"[contest] push started loc={location_id} entity={entity_id}")
        return {"status": "pushed", "entity_id": entity_id}

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
        if state.pushed_this_loop:
            return None  # already pushed this contest

        scene_store.save_pool(location_id, entity_id, list(new_dice))
        state.pushed_this_loop = True
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
    actor_id: Optional[str] = None,
) -> None:
    """Publish a pool_updated SSE event to all active sessions.

    ``dice`` is the DieSpec wire shape (list of dicts).  When omitted, the
    current pool is read from the shared scene store.  ``actor_id`` identifies
    who caused the change (defaults to the pool owner — i.e. self-initiated);
    it differs when one entity modifies another's pool (offer-negative).

    Payload matches the frontend's pool_updated handler:
      { player_id, entity_id, actor_id, dice, phase, location_id }
    """
    from transversal.api.sse.bus import StreamEvent, event_bus
    from transversal.services.scene_state import get_scene_store
    from transversal.services.session_manager import session_manager

    if dice is None:
        dice = get_scene_store().get_pool(location_id, entity_id)

    # Persist the lifecycle phase so a client re-fetch (tab switch / refresh)
    # can restore the committed result rather than the picking screen.
    get_scene_store().set_phase(location_id, entity_id, phase)

    actor = actor_id or entity_id
    wire_dice = [d if isinstance(d, dict) else {"die": str(d)} for d in dice]

    for s in session_manager.list_active():
        event_bus.publish(StreamEvent(
            event="pool_updated",
            session_id=s.id,
            data={
                "player_id": actor,
                "entity_id": entity_id,
                "actor_id": actor,
                "dice": wire_dice,
                "phase": phase,
                "location_id": location_id,
            },
        ))
