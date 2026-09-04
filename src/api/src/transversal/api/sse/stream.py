"""SSE stream endpoint — pushes game state changes to connected clients."""

import logging

from fastapi import APIRouter, Query, Request
from sse_starlette.sse import EventSourceResponse

from transversal.api.sse.bus import event_bus

logger = logging.getLogger("transversal.sse")
router = APIRouter(prefix="/api/v1", tags=["sse"])


@router.get("/stream")
async def stream(
    request: Request,
    session_id: str = Query(...),
    entity_id: str = Query(...),
    player_id: str = Query(""),
):
    """SSE endpoint for real-time state push.

    Query params:
        session_id: The session to subscribe to
        entity_id: The entity whose events to receive (filtered server-side)
        player_id: The acting player (for presence tracking)
    """
    from transversal.services.presence import mark_offline, mark_online
    from transversal.services.state_events import broadcast_presence_changed

    logger.info(f"SSE client connecting — session={session_id} entity={entity_id} player={player_id}")
    sub = event_bus.subscribe(session_id)
    if player_id and mark_online(player_id):
        broadcast_presence_changed()

    async def event_generator():
        try:
            async for sse_message in sub.stream():
                # Check if client disconnected
                if await request.is_disconnected():
                    logger.info(f"SSE client disconnected — session={session_id}")
                    break
                yield sse_message
        finally:
            sub.close()
            if player_id:
                mark_offline(player_id)
            logger.info(f"SSE subscription closed — session={session_id}")

    return EventSourceResponse(event_generator())
