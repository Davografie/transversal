"""REST endpoints for the manual (concurrent) contest flow.

Dice pool CRUD lives in :mod:`transversal.api.rest.scene_state`.  This
router owns the contest lifecycle: challenge (designate opponent), commit
a side's rolled result (set), give in, and clear.  Resolution is implicit —
when both sides have set, the tracker compares and declares a winner.
"""

from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

from transversal.domain import CommittedResult, DieType, OutcomeTier
from transversal.services.contest_tracker import (
    broadcast_pool_change,
    get_contest_tracker,
)
from transversal.services.scene_state import get_scene_store

router = APIRouter(prefix="/api/v1/locations", tags=["contest-pools"])


class SetOppositionRequest(BaseModel):
    opponent_id: str
    universe: str = "earth"


class SetRequest(BaseModel):
    total: int
    effect_die: Optional[str] = None
    tier: Optional[str] = None
    pipeline: str = "pool"


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
        effect_die=DieType(body.effect_die) if body.effect_die else None,
        tier=OutcomeTier(body.tier) if body.tier else None,
        pipeline=body.pipeline,
    )


# ── Endpoints ─────────────────────────────────────────

@router.post("/{location_id}/pools/{entity_id}/set-opposition")
async def set_opposition(location_id: str, entity_id: str, body: SetOppositionRequest):
    """Challenge: designate an opponent for an entity's contest here."""
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

    Returns the outcome when both sides have set; otherwise a waiting flag.
    """
    ct = get_contest_tracker()
    outcome = ct.set_result(location_id, entity_id, _to_committed(body))

    _broadcast("contest_set", location_id, entity_id, {
        "total": body.total,
        "effect_die": body.effect_die,
        "tier": body.tier,
        "pipeline": body.pipeline,
    })

    if outcome is not None:
        _broadcast("contest_resolved", location_id, entity_id, {
            "winner": outcome.winner.value,
            "stakes": outcome.stakes.value if outcome.stakes else None,
            "gave_in": outcome.gave_in.value if outcome.gave_in else None,
            "challenger": outcome.challenger.model_dump() if outcome.challenger else None,
            "defendant": outcome.defendant.model_dump() if outcome.defendant else None,
        })
        return outcome

    return {"status": "waiting"}


@router.post("/{location_id}/pools/{entity_id}/give-in")
async def give_in(location_id: str, entity_id: str):
    """Concede the contest — the other side wins."""
    ct = get_contest_tracker()
    outcome = ct.give_in(location_id, entity_id)
    if outcome is None:
        return {"status": "no_contest"}

    _broadcast("contest_give_in", location_id, entity_id, {
        "gave_in": outcome.gave_in.value if outcome.gave_in else None,
        "winner": outcome.winner.value,
    })
    _broadcast("contest_resolved", location_id, entity_id, {
        "winner": outcome.winner.value,
        "stakes": outcome.stakes.value if outcome.stakes else None,
        "gave_in": outcome.gave_in.value if outcome.gave_in else None,
        "challenger": outcome.challenger.model_dump() if outcome.challenger else None,
        "defendant": outcome.defendant.model_dump() if outcome.defendant else None,
    })
    return outcome


@router.post("/{location_id}/pools/{entity_id}/clear")
async def clear_pool(location_id: str, entity_id: str):
    """Reset an entity's contest + pool at a location (end of beat)."""
    ct = get_contest_tracker()
    get_scene_store().clear_pool(location_id, entity_id)
    ct.clear_pool(location_id, entity_id)
    broadcast_pool_change(location_id, entity_id, dice=[], phase="adding")
    return {"status": "cleared"}
