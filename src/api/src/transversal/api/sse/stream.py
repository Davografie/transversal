"""SSE stream endpoint — pushes game state changes to connected clients."""

import logging

from fastapi import APIRouter, HTTPException, Query, Request
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
        session_id: The session to subscribe to, **in the caller's campaign**
        entity_id: The entity whose events to receive (filtered client-side)
        player_id: The acting player (for presence tracking)

    The subscription is bound to the caller's campaign ([[B305]]). It used to accept
    any ``session_id`` at all — the parameter was never checked against anything — so
    an admitted player could watch another campaign's stream by naming its id. Because
    a fork preserves every ``_key``, the ids are guessable-shaped and the events are
    indistinguishable from the caller's own, which is what made this a cross-tenant
    read rather than a curiosity. An unknown session, or one belonging to another
    campaign, is a **404**: the same answer for both, so the endpoint does not confirm
    that someone else's session exists.
    """
    from transversal.services.campaign_scope import current_campaign
    from transversal.services.presence import mark_offline, mark_online
    from transversal.services.session_manager import session_manager
    from transversal.services.state_events import broadcast_presence_changed

    campaign = current_campaign()
    if not campaign or session_manager.get(session_id) is None:
        logger.info(
            "SSE refused — session=%s is not in this campaign (campaign=%r)",
            session_id,
            campaign,
        )
        raise HTTPException(status_code=404, detail="no such session in this campaign")

    logger.info(
        "SSE client connecting — session=%s campaign=%s entity=%s player=%s",
        session_id,
        campaign,
        entity_id,
        player_id,
    )
    sub = event_bus.subscribe(session_id, campaign)
    if player_id and mark_online(player_id):
        broadcast_presence_changed()

    async def event_generator():
        try:
            async for sse_message in sub.stream():
                # Check if client disconnected
                if await request.is_disconnected():
                    logger.info("SSE client disconnected — session=%s", session_id)
                    break
                yield sse_message
        finally:
            sub.close()
            if player_id:
                mark_offline(player_id)
            logger.info("SSE subscription closed — session=%s", session_id)

    return EventSourceResponse(event_generator())
