"""REST endpoints for the manual (concurrent) contest flow.

Dice pool CRUD lives in :mod:`transversal.api.rest.scene_state`.  This
router owns the contest lifecycle: challenge (designate opponent), commit
a side's rolled result (set), give in, and clear.  Resolution is implicit —
when both sides have set, the tracker compares and declares a winner.
"""

import logging

from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

from transversal.domain import CommittedResult, ContestCompare, ContestOutcome, ContestWinner, DieType, OutcomeTier
from transversal.services.contest_tracker import (
    broadcast_pool_change,
    get_contest_tracker,
    start_contest,
)
from transversal.services.scene_state import get_scene_store

logger = logging.getLogger("transversal.contest_pools")

router = APIRouter(prefix="/api/v1/locations", tags=["contest-pools"])


class SetOppositionRequest(BaseModel):
    opponent_id: str
    universe: str = "earth"


class SetRequest(BaseModel):
    total: int
    effect_die: Optional[str] = None
    tier: Optional[str] = None
    pipeline: str = "pool"


class PreventTakenOutRequest(BaseModel):
    effect_die: Optional[str] = None


def _winner_margin(result: ContestOutcome) -> Optional[int]:
    """How far the winning side beat the losing side's committed total by.

    Read off the outcome's own sides rather than the caller's ids: ``challenger``
    and ``defendant`` are the *seats*, so which of them won is ``result.winner``'s
    business. ``None`` when either side never committed (a give-in before rolling),
    because a margin against a total nobody set is not a number worth inventing.
    """
    challenger = result.challenger.total if result.challenger else None
    defendant = result.defendant.total if result.defendant else None
    if challenger is None or defendant is None:
        return None
    if result.winner == ContestWinner.PLAYER:
        return challenger - defendant
    return defendant - challenger


def _committed_effect_die(committed: Optional[CommittedResult]) -> Optional[str]:
    """One side's **own** committed effect die, or None if it never committed.

    The reaction SFX class turns on this number — *"convert your opponent's
    effect die"* — and it is not the same as the contest's shared ``effect_die``
    (the effective complication die the loser takes), which is what the event
    context carried before [[B232]].
    """
    return committed.effect_die.value if committed and committed.effect_die else None


def _broadcast(event: str, location_id: str, entity_id: str, data: dict) -> None:
    """Publish a contest SSE event to all active sessions."""
    from transversal.api.sse.bus import StreamEvent, event_bus
    from transversal.services.session_manager import session_manager

    for s in session_manager.list_active():
        event_bus.publish(StreamEvent(
            event=event,
            session_id=s.id,
            data={"location_id": location_id, "entity_id": entity_id, **data},
        ))


def _to_committed(body: SetRequest) -> CommittedResult:
    return CommittedResult(
        total=body.total,
        effect_die=DieType(body.effect_die) if body.effect_die else DieType.D4,
        tier=OutcomeTier(body.tier) if body.tier else None,
        pipeline=body.pipeline,
    )


# ── Endpoints ─────────────────────────────────────────

@router.post("/{location_id}/pools/{entity_id}/set-opposition")
async def set_opposition(location_id: str, entity_id: str, body: SetOppositionRequest):
    """Challenge: designate an opponent for an entity's contest here.

    ``start_contest`` is the shared choke point — the ``contest/start`` effect
    comes through the same function, so a challenge begun at the table and one
    begun by a rule cannot drift.
    """
    from transversal.main import _get_repo
    from transversal.services.targeting_bans import has_targeting_ban

    challenger = _get_repo().get_entity(entity_id)
    if has_targeting_ban(challenger, body.opponent_id):
        return {"status": "blocked", "reason": "You can't target that entity yet"}

    start_contest(location_id, entity_id, body.opponent_id, body.universe)
    return {
        "entity_id": entity_id,
        "location_id": location_id,
        "opposition_entity_id": body.opponent_id,
    }


@router.post("/{location_id}/pools/{entity_id}/set")
async def set_result(location_id: str, entity_id: str, body: SetRequest):
    """Commit one side's rolled+picked result.

    Returns a provisional compare or final outcome when both sides have set;
    otherwise a waiting flag.
    """
    ct = get_contest_tracker()
    from transversal.services import contest_history
    # Store the raw result first (no compare): an outcome effect firing below may
    # rewrite the effect die it carries, and the compare flips initiative, so it
    # must run exactly once afterwards on the value the table will see.
    ct.store_committed(location_id, entity_id, _to_committed(body))

    # The total + effect dice are now locked — fire ``on_set``.
    from transversal.services.state_events import fire_state_sfx
    fire_state_sfx(entity_id, "", "on_set", {
        "effect_die": body.effect_die,
        "total": body.total,
    })

    # Fire ``on_result`` with the finalized roll state (dice + roles + tiers),
    # so SFX can inspect which dice were rolled and which were left unchosen.
    from transversal.services.roll_orchestrator import fire_result_sfx
    fire_result_sfx(
        entity_id, "", get_scene_store().get_pool(location_id, entity_id),
        effect_die=body.effect_die, total=body.total,
    )

    # Fire roll-scoped deferred effects armed with ``on_set``/``on_result``.
    from transversal.services.roll_deferral import fire_armed
    roll_context = {
        "effect_die": body.effect_die,
        "total": body.total,
        "tier": body.tier,
        "rolls": get_scene_store().get_pool(location_id, entity_id),
    }
    fire_armed(entity_id, "on_set", "", roll_context)
    fire_armed(entity_id, "on_result", "", roll_context)

    # Fire outcome-gated roll effects: success (any non-fail tier) vs failure.
    if body.tier:
        fire_armed(entity_id, "on_success" if body.tier != "fail" else "on_failure", "", roll_context)

    # An outcome effect may have stepped the effect die / tier while those fired.
    # The committed result already carries the stepped value — compare once, now.
    result = ct.compare_if_ready(location_id, entity_id)

    challenger, defendant = ct.get_contestants(location_id, entity_id)
    challenger_id = challenger.entity_id if challenger else None
    defendant_id = defendant.entity_id if defendant else None

    # Re-read this side's committed result: an outcome effect may have stepped the
    # effect die or the tier, and the table must see what the contest resolves on.
    committed_state = challenger if (challenger and challenger.entity_id == entity_id) else defendant
    committed = committed_state.committed if committed_state is not None else None

    _broadcast("contest_set", location_id, entity_id, {
        "total": committed.total if committed else body.total,
        "effect_die": (committed.effect_die.value if committed and committed.effect_die else body.effect_die),
        "tier": (committed.tier.value if committed and committed.tier else body.tier),
        "pipeline": body.pipeline,
        "challenger_id": challenger_id,
        "defendant_id": defendant_id,
    })

    if isinstance(result, (ContestCompare, ContestOutcome)):
        # The round is complete — freeze it now, after the outcome effects have had
        # their say, so the Blue Book entry records the value the contest resolves
        # on rather than the one the client sent ([[B177]]).
        contest_history.snapshot_round(
            location_id,
            ct,
            get_scene_store(),
            [challenger_id, defendant_id],
            decision="compare" if isinstance(result, ContestCompare) else "resolved",
            pending=result.pending if isinstance(result, ContestCompare) else None,
        )

    if isinstance(result, ContestCompare):
        _broadcast("contest_compare", location_id, entity_id, result.model_dump())
        return result
    if isinstance(result, ContestOutcome):
        winner_id = challenger_id if result.winner == ContestWinner.PLAYER else defendant_id
        loser_id = defendant_id if result.winner == ContestWinner.PLAYER else challenger_id
        universe = challenger.universe if challenger else ""
        from transversal.services.state_events import fire_contest_outcome_sfx
        # Each side's **own** committed effect die, so a reaction can read the
        # other side's ([[B232]]) — the shared ``effect_die`` above is only the
        # effective complication die for the loser.
        fire_contest_outcome_sfx(
            winner_id or "",
            loser_id or "",
            universe,
            effect_die=result.effect_die.value if result.effect_die else None,
            high_stakes=result.high_stakes,
            taken_out=result.taken_out,
            own_effect_dice={
                challenger_id: _committed_effect_die(result.challenger),
                defendant_id: _committed_effect_die(result.defendant),
            },
            # The winner's margin; `fire_contest_outcome_sfx` signs it per side.
            margin=_winner_margin(result),
        )
        # One entry per participant's book, each from its own side ([[B177]]).
        contest_history.record_contest_outcome(location_id, challenger, defendant, result)
        _broadcast("contest_resolved", location_id, entity_id, {
            "winner": result.winner.value,
            "gave_in": result.gave_in.value if result.gave_in else None,
            "challenger": result.challenger.model_dump() if result.challenger else None,
            "defendant": result.defendant.model_dump() if result.defendant else None,
            "challenger_id": challenger_id,
            "defendant_id": defendant_id,
            "high_stakes": result.high_stakes,
            "effect_die": result.effect_die.value if result.effect_die else None,
            "taken_out": result.taken_out,
        })
        return result

    return {"status": "waiting"}


class SetStakesRequest(BaseModel):
    high_stakes: bool = False


@router.post("/{location_id}/pools/{entity_id}/stakes")
async def set_stakes(location_id: str, entity_id: str, body: SetStakesRequest):
    """Set whether the contest is high stakes (default low)."""
    ct = get_contest_tracker()
    if not ct.set_stakes(location_id, entity_id, body.high_stakes):
        return {"status": "no_contest"}
    _broadcast("contest_stakes", location_id, entity_id, {"high_stakes": body.high_stakes})
    return {"status": "ok", "high_stakes": body.high_stakes}


@router.post("/{location_id}/pools/{entity_id}/give-in")
async def give_in(location_id: str, entity_id: str):
    """Concede the contest — the other side wins.

    Gated: the initiator must have committed a result first.
    """
    ct = get_contest_tracker()
    from transversal.services import contest_history
    challenger, defendant = ct.get_contestants(location_id, entity_id)
    logger.info(
        f"[contest] give_in loc={location_id} entity={entity_id} "
        f"challenger={challenger.entity_id if challenger else None} defendant={defendant.entity_id if defendant else None}"
    )
    if challenger is None or defendant is None:
        logger.info(f"[contest] give_in -> no_contest loc={location_id} entity={entity_id}")
        return {"status": "no_contest"}
    if challenger.committed is None:
        logger.info(f"[contest] give_in -> not_ready (initiator not committed) loc={location_id} entity={entity_id}")
        return {"status": "not_ready", "reason": "Initiator has not set a result yet"}

    outcome = ct.give_in(location_id, entity_id)
    if outcome is None:
        logger.info(f"[contest] give_in -> no_contest (tracker) loc={location_id} entity={entity_id}")
        return {"status": "no_contest"}
    logger.info(f"[contest] give_in -> resolved winner={outcome.winner.value} loc={location_id} entity={entity_id}")

    # Fire automatic SFX for the conceding side (give-in → +1 razmerit + ban).
    from transversal.services.state_events import fire_state_sfx
    opponent_id = defendant.entity_id if entity_id == challenger.entity_id else challenger.entity_id
    fire_state_sfx(entity_id, "", "on_give_in", {"gave_in": True, "contest_entity_opponent": opponent_id})

    challenger, defendant = ct.get_contestants(location_id, entity_id)
    challenger_id = challenger.entity_id if challenger else None
    defendant_id = defendant.entity_id if defendant else None

    # A give-in before any compare leaves the initiator's committed roll
    # unsnapshotted (no compare ran), so freeze whatever is committed now; a
    # side already recorded for this round is skipped ([[B177]]).
    contest_history.snapshot_round(
        location_id,
        ct,
        get_scene_store(),
        [challenger_id, defendant_id],
        decision="gave_in",
    )
    contest_history.record_contest_outcome(location_id, challenger, defendant, outcome)

    _broadcast("contest_give_in", location_id, entity_id, {
        "gave_in": outcome.gave_in.value if outcome.gave_in else None,
        "winner": outcome.winner.value,
        "challenger_id": challenger_id,
        "defendant_id": defendant_id,
    })
    _broadcast("contest_resolved", location_id, entity_id, {
        "winner": outcome.winner.value,
        "gave_in": outcome.gave_in.value if outcome.gave_in else None,
        "challenger": outcome.challenger.model_dump() if outcome.challenger else None,
        "defendant": outcome.defendant.model_dump() if outcome.defendant else None,
        "challenger_id": challenger_id,
        "defendant_id": defendant_id,
        "high_stakes": outcome.high_stakes,
        "effect_die": outcome.effect_die.value if outcome.effect_die else None,
        "taken_out": outcome.taken_out,
    })
    return outcome


@router.post("/{location_id}/pools/{entity_id}/prevent-taken-out")
async def prevent_taken_out(location_id: str, entity_id: str, req: PreventTakenOutRequest):
    """Prevent a pending high-stakes takeout by spending 1 razmerit."""
    from transversal.services.state_events import prevent_taken_out as _prevent

    result = _prevent(entity_id, effect_die=req.effect_die)
    if result.get("prevented"):
        _broadcast("contest_prevent_taken_out", location_id, entity_id, {"entity_id": entity_id})
    return result


@router.post("/{location_id}/pools/{entity_id}/push")
async def push(location_id: str, entity_id: str):
    """Start a push: the pending side rebuilds and rerolls (free, once)."""
    ct = get_contest_tracker()
    result = ct.push(location_id, entity_id)
    if result is None:
        return {"status": "not_allowed"}
    from transversal.services.state_events import fire_state_sfx
    fire_state_sfx(entity_id, "", "on_push", {"pushed": True})
    _broadcast("contest_push", location_id, entity_id, {
        "entity_id": entity_id,
        "status": "pushed",
    })
    return result


@router.get("/{location_id}/pools/{entity_id}/contest")
async def get_contest(location_id: str, entity_id: str):
    """Return the current contest state for an entity (perspective re-sync)."""
    ct = get_contest_tracker()
    challenger, defendant = ct.get_contestants(location_id, entity_id)
    logger.info(
        f"[contest] get_contest loc={location_id} entity={entity_id} "
        f"challenger={challenger.entity_id if challenger else None} defendant={defendant.entity_id if defendant else None}"
    )
    if challenger is None or defendant is None:
        logger.info(f"[contest] get_contest -> no_contest loc={location_id} entity={entity_id}")
        return {"status": "no_contest"}
    logger.info(
        f"[contest] get_contest -> active challenger_committed={challenger.committed is not None} "
        f"defendant_committed={defendant.committed is not None}"
    )
    return {
        "status": "active",
        "challenger_id": challenger.entity_id,
        "defendant_id": defendant.entity_id,
        "challenger_result": challenger.committed.model_dump() if challenger.committed else None,
        "defendant_result": defendant.committed.model_dump() if defendant.committed else None,
        "initiative": challenger.initiative,
        "pending": challenger.pending_decision,
        "high_stakes": challenger.high_stakes,
        "challenger_pushed": challenger.pushed_this_loop,
        "defendant_pushed": defendant.pushed_this_loop,
    }


@router.post("/{location_id}/pools/{entity_id}/clear")
async def clear_pool(location_id: str, entity_id: str):
    """Reset an entity's contest + pool at a location (end of beat)."""
    ct = get_contest_tracker()
    get_scene_store().clear_pool(location_id, entity_id)
    ct.clear_pool(location_id, entity_id)
    broadcast_pool_change(location_id, entity_id, dice=[], phase="adding")
    return {"status": "cleared"}


@router.post("/{location_id}/pools/{entity_id}/cancel")
async def cancel_contest(location_id: str, entity_id: str):
    """Cancel a contest the caller started, before they have rolled ([[B118]]).

    A contest is *shared* state, so the initiator cannot simply walk away from
    one: clearing only their own side would leave the opponent holding a
    challenge to nothing, and the pair would still show up as an active contest.
    So both sides' contest metadata goes, while only the canceller's pool is
    cleared — the opponent may have dice assembled that are not theirs to lose.
    Each side is told, because the opponent's screen is showing this contest.

    Only the initiator may cancel it, and only while they have nothing rolled:
    once a side has committed, the contest is a thing to resolve, and give-in is
    how a side leaves that one.
    """
    ct = get_contest_tracker()
    store = get_scene_store()
    challenger, defendant = ct.get_contestants(location_id, entity_id)
    if challenger is None or defendant is None:
        return {"status": "no_contest"}
    if challenger.entity_id != entity_id:
        return {"status": "not_allowed", "reason": "Only the challenger can cancel"}
    if challenger.committed is not None or store.get_pool(location_id, entity_id):
        return {"status": "not_allowed", "reason": "You have already rolled"}

    opponent_id = defendant.entity_id
    store.clear_pool(location_id, entity_id)
    ct.clear_pool(location_id, challenger.entity_id)
    ct.clear_pool(location_id, defendant.entity_id)
    broadcast_pool_change(location_id, entity_id, dice=[], phase="adding")
    for eid in (entity_id, opponent_id):
        _broadcast("contest_cancelled", location_id, eid, {
            "entity_id": entity_id,
            "opponent_id": opponent_id,
        })
    return {"status": "cancelled"}


@router.get("/{location_id}/pools/{entity_id}/pending-effects")
async def pending_effects(location_id: str, entity_id: str):
    """Name the effects that would fire on give-in / prevent-take-out ([[B14]]).

    A read, not a decision: the SFX owner answers which authored rules carry the
    two triggers for this entity, so the buttons can say what they will do.
    """
    from transversal.services.contest_history import pending_contest_effects
    return pending_contest_effects(entity_id)
