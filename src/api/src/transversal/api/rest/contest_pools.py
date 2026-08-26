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
    """Challenge: designate an opponent for an entity's contest here."""
    from transversal.main import _get_repo
    from transversal.services.targeting_bans import has_targeting_ban

    challenger = _get_repo().get_entity(entity_id)
    if has_targeting_ban(challenger, body.opponent_id):
        return {"status": "blocked", "reason": "You can't target that entity yet"}

    ct = get_contest_tracker()
    ct.set_opposition(location_id, entity_id, body.opponent_id, body.universe)
    broadcast_pool_change(location_id, entity_id)
    _broadcast("contest_challenged", location_id, entity_id, {
        "challenger_id": entity_id,
        "opponent_id": body.opponent_id,
    })
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
    result = ct.set_result(location_id, entity_id, _to_committed(body))

    # The total + effect dice are now locked — fire ``on_set``.
    from transversal.services.state_events import fire_state_sfx
    fire_state_sfx(entity_id, "", "on_set", {
        "effect_die": body.effect_die,
        "total": body.total,
    })

    challenger, defendant = ct.get_contestants(location_id, entity_id)
    challenger_id = challenger.entity_id if challenger else None
    defendant_id = defendant.entity_id if defendant else None

    _broadcast("contest_set", location_id, entity_id, {
        "total": body.total,
        "effect_die": body.effect_die,
        "tier": body.tier,
        "pipeline": body.pipeline,
        "challenger_id": challenger_id,
        "defendant_id": defendant_id,
    })

    if isinstance(result, ContestCompare):
        _broadcast("contest_compare", location_id, entity_id, result.model_dump())
        return result
    if isinstance(result, ContestOutcome):
        winner_id = challenger_id if result.winner == ContestWinner.PLAYER else defendant_id
        loser_id = defendant_id if result.winner == ContestWinner.PLAYER else challenger_id
        universe = challenger.universe if challenger else ""
        from transversal.services.state_events import fire_contest_outcome_sfx
        fire_contest_outcome_sfx(
            winner_id or "",
            loser_id or "",
            universe,
            effect_die=result.effect_die.value if result.effect_die else None,
            high_stakes=result.high_stakes,
            taken_out=result.taken_out,
        )
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
