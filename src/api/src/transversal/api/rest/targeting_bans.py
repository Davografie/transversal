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
        bans = [
            {"target_id": b.target_id, "scenes_remaining": b.scenes_remaining}
            for b in (entity.targeting_bans or [])
            if b.scenes_remaining > 0
        ]
    return {"bans": bans}


@router.post("/scenes/advance")
async def advance_scene():
    """Advance the scene: fire scheduled scene effects and decrement bans."""
    from transversal.main import _get_engine, _get_repo
    from transversal.services.targeting_bans import decrement_scene_bans

    _get_engine().tick_scene()
    changed = decrement_scene_bans(_get_repo())
    return {"status": "advanced", "entities_updated": changed}
