"""REST endpoint for publishing session events — enables shared dice pools and roll results."""

from fastapi import APIRouter
from pydantic import BaseModel

from transversal.api.sse.bus import StreamEvent, event_bus

router = APIRouter(prefix="/api/v1/sessions", tags=["session-events"])


class SessionEventRequest(BaseModel):
    event: str
    data: dict = {}


@router.post("/{session_id}/publish")
async def publish_event(session_id: str, req: SessionEventRequest) -> dict:
    """Publish an event to all subscribers of a session.

    Used by clients to share dice pools, roll results, and other
    real-time state that doesn't need server-side persistence.
    """
    event_bus.publish(StreamEvent(
        event=req.event,
        session_id=session_id,
        data=req.data,
    ))
    return {"published": True}
