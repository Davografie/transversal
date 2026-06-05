"""SSE stream endpoint — pushes game state changes to connected clients."""

from fastapi import APIRouter, Query, Request
from sse_starlette.sse import EventSourceResponse

from transversal.api.sse.bus import event_bus

router = APIRouter(prefix="/api/v1", tags=["sse"])


@router.get("/stream")
async def stream(
    request: Request,
    session_id: str = Query(...),
    entity_id: str = Query(...),
):
    """SSE endpoint for real-time state push.

    Query params:
        session_id: The session to subscribe to
        entity_id: The entity whose events to receive (filtered server-side)

    Events pushed:
        location_changed, trait_updated, razmerit_changed,
        roll_result, sfx_triggered, beat_end, scene_change
    """
    sub = event_bus.subscribe(session_id)

    async def event_generator():
        try:
            async for sse_message in sub.stream():
                # Check if client disconnected
                if await request.is_disconnected():
                    break
                yield sse_message
        finally:
            sub.close()

    return EventSourceResponse(event_generator())
