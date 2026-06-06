"""Location navigation REST endpoint."""

from fastapi import APIRouter, HTTPException

from transversal.api.sse.bus import StreamEvent, event_bus
from transversal.db.repository import EntityRepository
from transversal.services.entity_manager import EntityManager

router = APIRouter(prefix="/api/v1", tags=["locations"])


def _repo():
    return EntityRepository()


def _em():
    return EntityManager(repository=_repo())


@router.get("/locations/tree")
async def location_tree():
    """Return the full location hierarchy as a nested tree."""
    return _repo().location_tree()


@router.get("/locations/{location_id}/navigate")
async def navigate(location_id: str):
    """Return navigation options from a location.

    Returns parent (up), children (down), and transversal destinations (lateral).
    """
    result = _repo().navigate_from(location_id)
    if result["location"] is None:
        raise HTTPException(status_code=404, detail=f"Location '{location_id}' not found")
    return result


from pydantic import BaseModel


class MoveRequest(BaseModel):
    location: str
    universe: str | None = None


class EdgeRequest(BaseModel):
    type: str  # "super" or "transversal"


@router.post("/entities/{entity_id}/move")
async def move_entity(entity_id: str, body: MoveRequest):
    """Move an entity to a new location."""
    em = _em()
    repo = _repo()
    entity = em.get(entity_id)
    result = em.move_to(entity, body.location, body.universe)

    # Get the display name of the target location
    loc = repo.get_entity(body.location)
    location_name = loc.name if loc else body.location

    return {
        "entity_id": result.id,
        "name": result.name,
        "location": location_name,
        "location_id": result.current_location,
        "universe": result.current_universe,
    }


# ── Location Edge Management ─────────────────────────


@router.post("/locations/{from_id}/edges/{to_id}")
async def create_edge(from_id: str, to_id: str, body: EdgeRequest):
    """Create a super or transversal edge between two locations."""
    if body.type not in ("super", "transversal"):
        raise HTTPException(status_code=400, detail=f"Invalid edge type: {body.type}")

    repo = _repo()
    edge_key = f"edge:{from_id}:{to_id}:{body.type}"

    if repo._relationships.has(edge_key):
        return {"status": "exists", "key": edge_key}

    repo._relationships.insert({
        "_key": edge_key,
        "_from": f"entities/{from_id}",
        "_to": f"entities/{to_id}",
        "type": body.type,
    })

    # For transversal edges, also create the reverse
    if body.type == "transversal":
        rev_key = f"edge:{to_id}:{from_id}:{body.type}"
        if not repo._relationships.has(rev_key):
            repo._relationships.insert({
                "_key": rev_key,
                "_from": f"entities/{to_id}",
                "_to": f"entities/{from_id}",
                "type": body.type,
            })

    return {"status": "created", "key": edge_key}


@router.delete("/locations/{from_id}/edges/{to_id}")
async def delete_edge(from_id: str, to_id: str, type: str = "super"):
    """Delete a super or transversal edge between two locations."""
    repo = _repo()
    edge_key = f"edge:{from_id}:{to_id}:{type}"

    try:
        repo._relationships.delete(edge_key)
        # For transversal edges, also remove the reverse
        if type == "transversal":
            rev_key = f"edge:{to_id}:{from_id}:{type}"
            try:
                repo._relationships.delete(rev_key)
            except Exception:
                pass
        return {"status": "deleted", "key": edge_key}
    except Exception:
        raise HTTPException(status_code=404, detail=f"Edge '{edge_key}' not found")


# ── Zone Management ──────────────────────────────────

from transversal.domain import Zone


class ZoneUpdate(BaseModel):
    name: str
    x: float
    y: float
    background_image: str | None = None


@router.put("/locations/{location_id}/zones")
async def update_zones(location_id: str, zones: list[ZoneUpdate]):
    """Replace all zones on a location."""
    repo = _repo()
    entity = repo.get_entity(location_id)
    if entity is None:
        raise HTTPException(status_code=404, detail=f"Location '{location_id}' not found")

    entity.zones = [
        Zone(name=z.name, x=z.x, y=z.y, background_image=z.background_image)
        for z in zones
    ]
    repo.update_entity(entity)

    return {"status": "ok", "count": len(entity.zones)}


# ── Entity Map Position ──────────────────────────────

from pydantic import BaseModel as PydanticBaseModel


class MapPosition(PydanticBaseModel):
    map_x: float | None = None
    map_y: float | None = None


@router.patch("/entities/{entity_id}/map-position")
async def update_map_position(entity_id: str, body: MapPosition):
    """Update an entity's map position on the current location."""
    repo = _repo()
    entity = repo.get_entity(entity_id)
    if entity is None:
        raise HTTPException(status_code=404, detail=f"Entity '{entity_id}' not found")

    entity.map_x = body.map_x
    entity.map_y = body.map_y
    repo.update_entity(entity)

    # Broadcast position to all active SSE subscribers
    for session_id in list(event_bus._queues.keys()):
        event_bus.publish(StreamEvent(
            session_id=session_id,
            event="entity_moved",
            data={
                "entity_id": entity_id,
                "map_x": entity.map_x,
                "map_y": entity.map_y,
                "current_location": entity.current_location,
            },
        ))

    return {"status": "ok", "map_x": entity.map_x, "map_y": entity.map_y}
