"""Location navigation REST endpoint."""

import logging

from fastapi import APIRouter, HTTPException

from transversal.api.sse.bus import StreamEvent, event_bus
from transversal.db.repository import EntityRepository
from transversal.db.repository_mixins.images import pick_role_image
from transversal.db.repository_mixins.trait_settings import trait_visible_to
from transversal.domain import ArrivalKind
from transversal.services.entity_manager import EntityManager, EntityNotFoundError

logger = logging.getLogger("transversal.locations")

from transversal.services.media_utils import ROLE_VARIANT

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


def _trait_entry(repo, ts, location_id: str, viewer: str):
    """One trait as the viewer's payload sees it — or ``None`` if it is hidden.

    Shared by both location-trait reads so the shape and the fog-of-war rule
    cannot drift between them. An inherited trait is returned as the **owner's**
    setting (same id, same ledger), so ``hidden``/``known_to`` are the owner's
    too: a zone cannot un-hide the district's curse.
    """
    owner = repo.get_entity(ts.entity_id)
    hidden = bool(getattr(owner, "hidden", False))
    known_to = [str(k) for k in (ts.known_to or [])]
    if viewer and not trait_visible_to(hidden, known_to, viewer):
        return None
    registry = repo.get_trait(ts.trait_id)
    # Which sheet tab this trait belongs on. It is a property of the trait's **set**,
    # not of the trait or the entity (`TraitSet.sheet_tab`), and it is the same
    # read-through the GraphQL `traitsetTab` field does — the viewer needs it to keep
    # profile traits (a location's "appearance", say) off the map ([[B92]]).
    #
    # The set comes from the *registry trait* (`registry` is already in hand above):
    # a setting does not record one, because a copy could only drift the moment a
    # trait moved between sets.
    set_id = getattr(registry, "traitset_id", "") or ""
    traitset = repo.get_traitset_by_id(set_id)
    return {
        "id": ts.id,
        "trait_id": ts.trait_id,
        "name": getattr(registry, "name", "") or ts.trait_id,
        "traitset_id": set_id,
        "sheet_tab": getattr(getattr(traitset, "sheet_tab", None), "value", None) or "traits",
        "rating_type": ts.rating_type.value,
        "polarity": ts.polarity.value,
        # SFX granted by this trait, so a map chip can tell whether it has any to
        # offer. The definitions are not here: a client reads them from the `sfxs`
        # catalog query, which every surface already uses for names and text.
        "sfx_ids": list(ts.sfx_ids or []),
        "dice": [d.value for d in ts.dice],
        "capacity": [d.value for d in (ts.capacity or [])],
        "statement": ts.statement,
        "owner_location_id": ts.entity_id,
        "owner_name": getattr(owner, "name", "") or ts.entity_id,
        "inherited": ts.entity_id != location_id,
        "hidden": hidden,
        "known_to": known_to,
    }


def _attach_navdot_markers(repo, entries: list[dict]) -> list[dict]:
    """Resolve each trait's ``navdot`` marker image onto its entry ([[B200]]).

    The registry **trait** is the image owner and the **trait setting** is the
    variant — the same read-through the sheet's ``TraitSetting.image(role)`` does,
    which is what lets slice 2's per-instance override reach the map with no change
    here ([[Media Pipeline]] §Traits as image owners). The ladder is the shared
    ``pick_role_image``, so the chip and the sheet cannot disagree about which file
    a role means; its universe rung answers empty for a trait, which is how one
    picture serves every universe the trait belongs to.

    Batched, because a location can hold dozens of traits: one
    ``get_images_for_owners`` for the page rather than one read per chip. An entry
    with no such image simply lacks the keys, and the chip draws as it did before.
    """
    owner_ids = list(dict.fromkeys(e["trait_id"] for e in entries if e.get("trait_id")))
    if not owner_ids:
        return entries
    by_owner = repo.get_images_for_owners(owner_ids)
    for entry in entries:
        image = pick_role_image(by_owner.get(entry["trait_id"], []), "navdot", entry["id"])
        if image is not None:
            # Via the shared map, so a navdot cannot drift from what the entity
            # resolver would serve for the same role.
            entry["navdot_image"] = repo.role_image_url(image, ROLE_VARIANT["navdot"])
            entry["navdot_transparent"] = image.transparent
    return entries


@router.get("/locations/{location_id}/traits")
async def location_traits(location_id: str, viewer: str = ""):
    """Everything the viewer should list for this location ([[B92]]).

    The location's **own** traits of every kind, plus the **challenge pools it
    inherits** from its ancestors — the human's decision (2026-09-25): a doom
    pool is a condition of the place, but a room does not display the district's
    static and resource traits as its own.

    ``viewer`` is the viewing character's entity id; passing it applies the
    fog-of-war rule **server-side** because only the payload knows who is asking
    ([[B92]], the human's decision 2026-09-23): the owner not hidden ⇒ visible to
    all; the owner hidden ⇒ only a viewer its ``known_to`` names. Omit it for the
    whole set with the flags on it (the GM's read).
    """
    repo = _repo()
    traits = []
    for ts in repo.get_location_traits(location_id):
        entry = _trait_entry(repo, ts, location_id, viewer)
        if entry is not None:
            traits.append(entry)
    return {"location_id": location_id, "viewer": viewer or None,
            "traits": _attach_navdot_markers(repo, traits)}


@router.get("/locations/{location_id}/challenge-traits")
async def location_challenge_traits(location_id: str, viewer: str = ""):
    """This location's doom/progress pools, **including what its zones inherit** ([[B191]]).

    The pools-only read: it is what the dice side addresses when a challenge die
    is spent, and an inherited pool is returned as the *owner's own* trait
    setting — same id and dice ledger — so nothing here is a copy and a die spent
    against it spends the one pool. [[B92]]'s viewer wants
    ``/locations/{id}/traits`` instead, which adds the location's own
    non-challenge traits; this one stays challenge-only.
    """
    repo = _repo()
    traits = []
    for ts in repo.get_location_challenge_traits(location_id):
        entry = _trait_entry(repo, ts, location_id, viewer)
        if entry is not None:
            traits.append(entry)
    return {"location_id": location_id, "viewer": viewer or None,
            "traits": _attach_navdot_markers(repo, traits)}


@router.get("/locations/{location_id}/navigate")
async def navigate(location_id: str, entity_id: str | None = None):
    """Return navigation options from a location.

    Returns parent (up), children (down), and transversal destinations (lateral).

    Pass ``entity_id`` to also get that character's **guided route**: when it
    carries a ``destination_location`` — written by the effects system's "set
    destination" action, which an SFX grants in the fiction — the response adds
    ``destination`` (the objective) and ``next_hop`` (the neighbouring location
    that is the first step toward it). The viewer lights that single navdot; see
    [[Location Viewer]]. ``next_hop`` is null when the character is already there
    or nothing connects the two, and ``destination`` is absent when the character
    has no directions at all.

    The hop is measured **from the location being viewed**, not from the
    character's own ``current_location``, so every location shows its own next
    step — which is what "each location highlights the next hop" means.
    """
    logger.info(f"[init] navigate loc={location_id}")
    repo = _repo()
    result = repo.navigate_from(location_id)
    if result["location"] is None:
        raise HTTPException(status_code=404, detail=f"Location '{location_id}' not found")

    # Resolve navdot images from entity_images (role="navdot") in one query.
    def _eid(entity: dict) -> str | None:
        return (entity or {}).get("_key") or (entity or {}).get("id")

    nav_targets = [
        *result.get("occupants", []),
        *result.get("children", []),
        *result.get("transversal", []),
    ]
    parent = result.get("parent")
    if parent:
        nav_targets.append(parent)
    nav_target_ids = [eid for eid in (_eid(e) for e in nav_targets) if eid]
    # An occupant resolves through the body standing *there*, not the entity's
    # active one: a body left behind when the consciousness travelled away is the
    # one on the map, and it must wear its own face ([[B137]] S1). Children, the
    # parent and portal destinations are places, not bodies, so they are untouched.
    bodies = {
        o["id"]: o["body_id"]
        for o in result.get("occupants", [])
        if o.get("body_id")
    }
    navdot_images = repo.get_navdot_images(nav_target_ids, bodies=bodies)
    navdot_transparent = repo.get_navdot_transparency(nav_target_ids, bodies=bodies)

    for occ in result.get("occupants", []):
        nav = navdot_images.get(_eid(occ))
        if nav:
            occ["image"] = nav
            occ["image_transparent"] = navdot_transparent.get(_eid(occ), False)

    for child in result.get("children", []):
        nav = navdot_images.get(_eid(child))
        if nav:
            child["navdot_image"] = nav
            child["navdot_image_transparent"] = navdot_transparent.get(_eid(child), False)

    for trans in result.get("transversal", []):
        nav = navdot_images.get(_eid(trans))
        if nav:
            trans["navdot_image"] = nav
            trans["navdot_image_transparent"] = navdot_transparent.get(_eid(trans), False)

    if parent:
        nav = navdot_images.get(_eid(parent))
        if nav:
            parent["navdot_image"] = nav
            parent["navdot_image_transparent"] = navdot_transparent.get(_eid(parent), False)

    # Zones carry their own ``location_id`` — the authoritative link, written
    # when the ``super`` edge is created (repository ``_ensure_child_zone``) —
    # and it is served verbatim. Identity is never resolved by comparing
    # display names: they are editable labels, so a rename must not retarget
    # or orphan a zone.

    # The guided route (optional, per-character — the destination lives on the
    # entity). ``next_hop`` is present-but-null rather than absent when there is
    # no way through, so the viewer can tell "no directions" from "directions
    # with no route" — though authoring is supposed to refuse the latter.
    if entity_id:
        subject = repo.get_entity(entity_id)
        destination_id = subject.destination_location if subject else None
        if destination_id:
            dest = repo.get_entity(destination_id)
            result["destination"] = {
                "location_id": destination_id,
                "name": dest.name if dest else destination_id,
            }
            result["next_hop"] = repo.get_route_next_hop(location_id, destination_id)

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
    # How they got there. Omitted → "move"; navigation sends "hierarchy" when
    # entering/leaving a sub-location, so a rule can tell the two apart.
    arrival_kind: str | None = None
    # Consciousness travel only: which body the mind arrives in. Omitted →
    # "{last_projection}", the behaviour every existing caller already got.
    # "{closest_projection}" takes the body nearest the destination instead (the
    # Blue Book's click-a-place-to-go-there gesture). An unknown value is treated
    # as a literal projection id by the travel handler, so nothing here has to
    # police the vocabulary.
    projection_policy: str | None = None
    # Re-entering a point already in the entity's history: move, but write no
    # historical record. The Blue Book uses this so a reader can *set* where the
    # next leg belongs without an untravelled leg entering the record ([[B173]]).
    seek: bool = False


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
    result = em.move_to(entity, body.location, body.universe,
                        arrival_kind=ArrivalKind.parse(body.arrival_kind, ArrivalKind.MOVE))

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
    """Transfer an entity's consciousness to a projection at the target location.

    Failures are mapped instead of left to become a bare 500. The Blue Book's
    click-a-place gesture reports the reason to the reader, and "Internal Server
    Error" is not one — while a missing destination is a routine case there, since
    a Blue Book entry outlives the location it names.
    """
    em = _em()
    repo = _repo()
    try:
        result = em.travel(
            entity_id, body.location,
            transversal_type="consciousness",
            projection_policy=body.projection_policy or "{last_projection}",
            seek=body.seek,
        )
    except EntityNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        # `travel` raises this only for input it cannot resolve — an unknown
        # destination location, or a projection id that no longer exists.
        raise HTTPException(status_code=400, detail=str(exc)) from exc

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
    """Create or update a super or transversal edge between two locations.

    A ``super`` edge is a parent link (child → parent), so one that would close
    a loop is refused before anything is written: a location cannot be its own
    parent, nor be re-parented under something already inside its own subtree.
    Such an edge detaches the whole branch from the tree root and it simply
    disappears from the location tree — the state Yinling Creek was found in on
    2026-09-11. The GM tree refuses the drop client-side too (``56a0ab5``); this
    is the same rule where the data is written, so no other caller gets past it.
    """
    if body.type not in ("super", "transversal"):
        raise HTTPException(status_code=400, detail=f"Invalid edge type: {body.type}")

    repo = _repo()
    refusal = repo.validate_relationship(from_id, to_id, body.type)
    if refusal:
        raise HTTPException(status_code=400, detail=refusal)

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

    # Materialise the nav-dot defaults the new link needs, so the viewer has a
    # stored dot to draw *and* land on. This endpoint inserts edge documents
    # directly and so does not go through `create_relationship` — both paths call
    # the same helper.
    repo.ensure_location_link_defaults(from_id, to_id, body.type)

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
        projection_policy = "{last_projection}" if travel_type == "consciousness" else None
        updated = _em().travel(body.entity_id, to_id, transversal_type=travel_type, projection_policy=projection_policy)
        return {
            "status": "moved", "applied": [], "pendingChoices": [],
            "entity_id": updated.id, "name": updated.name,
            "location_id": updated.current_location, "universe": updated.current_universe,
        }

    result = commit_effects(entity, effects, repo, arrival_kind=ArrivalKind.TRANSVERSAL)
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
    # The label is derived from the linked child; a zone is always a link.
    location_id: str
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
        Zone(location_id=z.location_id, x=z.x, y=z.y, background_image=z.background_image)
        for z in zones
    ]
    repo.update_entity(entity)

    return {"status": "ok", "count": len(entity.zones)}


class TraitPositionsUpdate(BaseModel):
    # Keyed by trait-setting id: {"<ts-id>": {"x": 30, "y": 55}}. The whole map is
    # replaced, like the zone list above; an absent id keeps meaning "not placed
    # yet", which is what leaves that chip in the viewer's auto-stack.
    trait_positions: dict


@router.put("/locations/{location_id}/trait-positions")
async def update_trait_positions(location_id: str, body: TraitPositionsUpdate):
    """Replace a location's trait-chip positions ([[B92]], [[Location Trait Chips]]).

    Placement is per **location**, deliberately, not per trait setting: an inherited
    trait's chip sits where *this* place wants it, and nothing is written onto the
    owner — the same reasoning that puts ``nav_positions`` here. Values are
    image-space percentages exactly like a nav dot's, so a chip pans and zooms with
    the scene.
    """
    repo = _repo()
    entity = repo.get_entity(location_id)
    if entity is None:
        raise HTTPException(status_code=404, detail=f"Location '{location_id}' not found")

    entity.trait_positions = {
        str(k): {"x": float(v.get("x", 50.0)), "y": float(v.get("y", 50.0))}
        for k, v in (body.trait_positions or {}).items()
    }
    repo.update_entity(entity)

    return {"status": "ok", "count": len(entity.trait_positions)}


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
