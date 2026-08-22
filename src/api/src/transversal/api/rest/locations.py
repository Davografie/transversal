"""Location navigation REST endpoint."""

import logging

from fastapi import APIRouter, HTTPException

from transversal.api.sse.bus import StreamEvent, event_bus
from transversal.db.repository import EntityRepository
from transversal.services.entity_manager import EntityManager

logger = logging.getLogger("transversal.locations")

router = APIRouter(prefix="/api/v1", tags=["locations"])


def _repo():
    return EntityRepository()


def _em():
    return EntityManager(repository=_repo())


@router.get("/locations/tree")
async def location_tree():
    """Return the full location hierarchy as a nested tree."""
    logger.info("[init] location_tree")
    return _repo().location_tree()


@router.get("/locations/graph")
async def location_graph():
    """Return the full location hierarchy plus transversal edges for the canvas."""
    return _repo().location_graph()


@router.get("/locations/{location_id}/navigate")
async def navigate(location_id: str):
    """Return navigation options from a location.

    Returns parent (up), children (down), and transversal destinations (lateral).
    """
    logger.info(f"[init] navigate loc={location_id}")
    result = _repo().navigate_from(location_id)
    if result["location"] is None:
        raise HTTPException(status_code=404, detail=f"Location '{location_id}' not found")

    # Resolve navdot images from entity_images (role="navdot")
    from transversal.db.repository import EntityRepository
    from transversal.domain import ImageType
    repo = EntityRepository()

    def _resolve_navdot(entity: dict) -> str | None:
        eid = (entity or {}).get("_key") or (entity or {}).get("id")
        if not eid:
            return None
        images = repo.get_entity_images(eid)
        for img in images:
            if "navdot" in img.roles:
                if img.image_type == ImageType.ANIMATED:
                    return f"/media/animated/{img.entity_id}/{img.universe}/{img.filename}.{img.extension}"
                else:
                    return f"/media/imagen/{img.entity_id}/{img.universe}/{img.filename}_Large.{img.extension}"
        return None

    for occ in result.get("occupants", []):
        nav = _resolve_navdot(occ)
        if nav:
            occ["image"] = nav

    for child in result.get("children", []):
        nav = _resolve_navdot(child)
        if nav:
            child["navdot_image"] = nav

    for trans in result.get("transversal", []):
        nav = _resolve_navdot(trans)
        if nav:
            trans["navdot_image"] = nav

    parent = result.get("parent")
    if parent:
        nav = _resolve_navdot(parent)
        if nav:
            parent["navdot_image"] = nav

    # Populate zone location_id by matching children to zones by name
    children = result.get("children", [])
    zones = result.get("location", {}).get("zones", [])
    for child in children:
        child_name = child.get("name", "")
        child_key = child.get("_key", "")
        if child_name and child_key:
            for zone in zones:
                if zone.get("name") == child_name and not zone.get("location_id"):
                    zone["location_id"] = child_key

    return result


# ── Relational Canvas ───────────────────────────────

@router.get("/locations/canvas")
async def locations_canvas(
    root: str = "all",
    depth: int = -1,
    focus: str | None = None,
    faction: str | None = None,
):
    """Return a scoped location graph for the unified relational canvas.

    ``root`` is ``all``, ``universe:<id>``, or ``location:<id>``.  ``depth``
    limits how many location levels below the root are included (-1 = all).
    ``focus`` marks a location as the focal node (its occupants are included
    up front); ``faction`` filters occupants to that faction's members.
    """
    return _repo().location_canvas(root=root, depth=depth, focus=focus, faction=faction)


@router.get("/locations/{location_id}/canvas")
async def location_canvas(location_id: str):
    """Return a location's neighborhood for the relational canvas."""
    result = _repo().canvas_neighborhood(location_id)
    if result["location"] is None:
        raise HTTPException(status_code=404, detail=f"Location '{location_id}' not found")
    return result


@router.get("/factions/{faction_id}/canvas")
async def faction_canvas(faction_id: str):
    """Return a faction's conspyramid data for the relational canvas."""
    result = _repo().canvas_faction(faction_id)
    if result["faction"] is None:
        raise HTTPException(status_code=404, detail=f"Faction '{faction_id}' not found")
    return result


@router.get("/gmcs/{gmc_id}/web")
async def gmc_web(gmc_id: str):
    """Return a GMC's relational web for the relational canvas."""
    result = _repo().canvas_gmc_web(gmc_id)
    if result["gmc"] is None:
        raise HTTPException(status_code=404, detail=f"GMC '{gmc_id}' not found")
    return result


from pydantic import BaseModel


class MoveRequest(BaseModel):
    location: str
    universe: str | None = None


class EdgeRequest(BaseModel):
    type: str  # "super" or "transversal"
    transversal_type: str | None = None  # "consciousness" | "inapposite" (transversal edges only)
    effects: list[dict] | None = None  # portal effects (travel SFX), frontend wire shape


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


@router.post("/entities/{entity_id}/consciousness-travel")
async def consciousness_travel(entity_id: str, body: MoveRequest):
    """Transfer an entity's consciousness to a projection at the target location."""
    em = _em()
    repo = _repo()
    result = em.consciousness_travel(entity_id, body.location)

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
    """Create or update a super or transversal edge between two locations."""
    if body.type not in ("super", "transversal"):
        raise HTTPException(status_code=400, detail=f"Invalid edge type: {body.type}")

    repo = _repo()
    edge_key = f"edge:{from_id}:{to_id}:{body.type}"
    patch = {}
    if body.transversal_type is not None:
        patch["transversal_type"] = body.transversal_type
    if body.effects is not None:
        patch["effects"] = body.effects

    if repo._relationships.has(edge_key):
        # Upsert the provided fields on an existing edge (both directions).
        if patch:
            repo._relationships.update({"_key": edge_key, **patch})
            rev_key = f"edge:{to_id}:{from_id}:{body.type}"
            if repo._relationships.has(rev_key):
                repo._relationships.update({"_key": rev_key, **patch})
            return {"status": "updated", "key": edge_key}
        return {"status": "exists", "key": edge_key}

    edge_doc = {
        "_key": edge_key,
        "_from": f"entities/{from_id}",
        "_to": f"entities/{to_id}",
        "type": body.type,
        **patch,
    }
    repo._relationships.insert(edge_doc)

    # For transversal edges, also create the reverse
    if body.type == "transversal":
        rev_key = f"edge:{to_id}:{from_id}:{body.type}"
        if not repo._relationships.has(rev_key):
            rev_doc = {
                "_key": rev_key,
                "_from": f"entities/{to_id}",
                "_to": f"entities/{from_id}",
                "type": body.type,
                **patch,
            }
            repo._relationships.insert(rev_doc)

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


# ── Portal firing ────────────────────────────────────

def _effect_from_wire(d: dict):
    """Convert a frontend effect dict (camelCase) to a domain Effect."""
    from transversal.domain import Effect, EffectDuration, EffectTiming, Timer, TimerCombine

    def _enum(cls, value, default):
        if value is None:
            return default
        if isinstance(value, str):
            try:
                return cls[value]  # member name ("IMMEDIATE", "FIRST_TO_FIRE")
            except KeyError:
                try:
                    return cls(value)  # value ("immediate", "first_to_fire")
                except ValueError:
                    return default
        return value

    duration = None
    if d.get("duration"):
        dur = d["duration"]
        duration = EffectDuration(
            timers=[Timer(event=t.get("event") or "scene", remaining=t.get("remaining", 0))
                    for t in (dur.get("timers") or [])],
            combine=_enum(TimerCombine, dur.get("combine"), TimerCombine.FIRST_TO_FIRE),
        )

    return Effect(
        timing=_enum(EffectTiming, d.get("timing"), EffectTiming.IMMEDIATE),
        type=d.get("type", ""),
        action=d.get("action", ""),
        target=d.get("target", ""),
        entity=d.get("entity", ""),
        result=d.get("result"),
        target_scope=d.get("targetScope"),
        entity_scope=d.get("entityScope"),
        negative=bool(d.get("negative", False)),
        context=d.get("context") or {},
        duration=duration,
    )


class PortalFireRequest(BaseModel):
    entity_id: str


@router.post("/locations/{from_id}/portal/{to_id}/fire")
async def fire_portal(from_id: str, to_id: str, body: PortalFireRequest):
    """Fire a transversal portal: apply its travel effects to the traversing entity.

    With no configured effects, falls back to the legacy ``transversal_type``
    (consciousness → consciousness-travel, else inapposite move).
    """
    from transversal.services.effects_commit import commit_effects

    repo = _repo()
    edge_key = f"edge:{from_id}:{to_id}:transversal"
    edge = repo._relationships.get(edge_key)
    if edge is None:
        raise HTTPException(status_code=404, detail=f"Portal '{edge_key}' not found")

    entity = repo.get_entity(body.entity_id)
    if entity is None:
        raise HTTPException(status_code=404, detail=f"Entity '{body.entity_id}' not found")

    effects = [_effect_from_wire(e) for e in (edge.get("effects") or [])]

    if not effects:
        travel_type = edge.get("transversal_type") or "inapposite"
        em = _em()
        if travel_type == "consciousness":
            updated = em.consciousness_travel(body.entity_id, to_id)
        else:
            updated = em.inapposite_travel(body.entity_id, to_id)
        return {
            "status": "moved", "applied": [], "pendingChoices": [],
            "entity_id": updated.id, "name": updated.name,
            "location_id": updated.current_location, "universe": updated.current_universe,
        }

    result = commit_effects(entity, effects, repo)
    return {
        "status": "applied" if result.applied else "pending",
        "applied": [a.summary for a in result.applied],
        "pendingChoices": [
            {"index": i, "kind": c.kind, "scope": c.scope, "field": c.field,
             "effect": c.effect.model_dump()}
            for i, c in enumerate(result.pending_choices)
        ],
        "entity_id": entity.id, "name": entity.name,
        "location_id": entity.current_location, "universe": entity.current_universe,
    }


# ── Zone Management ──────────────────────────────────

from transversal.domain import Zone


class ZoneUpdate(BaseModel):
    name: str
    x: float
    y: float
    background_image: str | None = None
    location_id: str | None = None


@router.put("/locations/{location_id}/zones")
async def update_zones(location_id: str, zones: list[ZoneUpdate]):
    """Replace all zones on a location."""
    repo = _repo()
    entity = repo.get_entity(location_id)
    if entity is None:
        raise HTTPException(status_code=404, detail=f"Location '{location_id}' not found")

    entity.zones = [
        Zone(name=z.name, x=z.x, y=z.y, background_image=z.background_image, location_id=z.location_id)
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
