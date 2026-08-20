"""REST endpoints for directional contest-target bans."""

from fastapi import APIRouter

router = APIRouter(prefix="/api/v1", tags=["targeting-bans"])


@router.get("/entities/{entity_id}/targeting-bans")
async def get_targeting_bans(entity_id: str):
    """Return the active directional bans for an entity."""
    from transversal.main import _get_repo

    entity = _get_repo().get_entity(entity_id)
    bans = []
    if entity is not None:
        bans = [{"target_id": b.target_id} for b in (entity.targeting_bans or [])]
    return {"bans": bans}


@router.post("/scenes/advance")
async def advance_scene():
    """Advance the scene: fire scheduled scene effects and decrement bans."""
    from transversal.main import _get_engine, _get_repo
    from transversal.services.scheduled_events import dispatch_event

    _get_engine().tick_scene()
    changed = dispatch_event(_get_repo(), "scene")

    from transversal.services.scene_state import get_scene_store
    from transversal.services.contest_tracker import get_contest_tracker
    get_scene_store().clear_all()
    get_contest_tracker().clear_all()

    from transversal.api.sse.bus import StreamEvent, event_bus
    from transversal.services.session_manager import session_manager
    for s in session_manager.list_active():
        event_bus.publish(StreamEvent(
            event="scene_change",
            session_id=s.id,
            data={"scene": "advanced", "entities_updated": changed},
        ))
    return {"status": "advanced", "entities_updated": changed}
