"""REST endpoints for in-memory scene state (dice pools + difficulty).

Pools are keyed by (location, entity) — one pool per character.  Mutations
broadcast ``pool_updated`` / ``difficulty_set`` server-side so other
clients see authoritative state without having to echo events themselves.
"""

import logging

from fastapi import APIRouter
from pydantic import BaseModel, Field
from typing import Optional

from transversal.api.sse.bus import StreamEvent, event_bus
from transversal.services.scene_state import get_scene_store
from transversal.services.contest_tracker import broadcast_pool_change
from transversal.services.session_manager import session_manager

logger = logging.getLogger("transversal.scene_state")

router = APIRouter(prefix="/api/v1/locations", tags=["scene-state"])


class PoolDieIn(BaseModel):
    die: str  # "d4".."d12"
    source_kind: str = "manual"  # "trait" | "difficulty" | "manual" | extensible
    source_id: str = ""
    label: str = ""
    ts_id: Optional[str] = None
    resource: bool = False  # resource-pool die: rolled separately, highest applies to total
    armed_sfx_ids: list[str] = Field(default_factory=list)  # client-stamped SFX ids arming this die


class SavePoolRequest(BaseModel):
    dice: list[PoolDieIn] = Field(default_factory=list)


class OfferNegativeRequest(BaseModel):
    opponent_id: str
    trait_setting_id: str
    dice: list[str] = Field(default_factory=list)
    label: str = ""


class DifficultyRequest(BaseModel):
    difficulty: int


@router.get("/{location_id}/pools")
async def get_pools(location_id: str):
    """Return every entity's saved dice pool at a location."""
    store = get_scene_store()
    pools = store.get_pools_at(location_id)
    logger.info(f"[init] get_pools loc={location_id} count={len(pools)}")
    return {"location_id": location_id, "pools": pools}


@router.get("/{location_id}/pools/{entity_id}")
async def get_pool(location_id: str, entity_id: str):
    """Return one entity's saved dice pool (empty if none)."""
    store = get_scene_store()
    dice = store.get_pool(location_id, entity_id)
    phase = store.get_phase(location_id, entity_id)
    logger.info(f"[init] get_pool loc={location_id} entity={entity_id} dice={len(dice)}")
    return {"dice": dice, "phase": phase}


@router.put("/{location_id}/pools/{entity_id}")
async def save_pool(location_id: str, entity_id: str, req: SavePoolRequest):
    """Persist (in-memory) an entity's assembled dice pool for a location."""
    dice = [d.model_dump(exclude_unset=True) for d in req.dice]
    # Read the pool *before* the write: the difference between the two is "what
    # changed", which only this moment can know.
    was = get_scene_store().get_pool(location_id, entity_id)
    get_scene_store().save_pool(location_id, entity_id, dice)
    logger.info(f"[init] save_pool loc={location_id} entity={entity_id} dice={len(dice)}")
    broadcast_pool_change(location_id, entity_id, dice=dice, phase="adding")

    # The pool is saved — a rule can now see it as the player built it, with the
    # other side of the contest too when there is one (`on_pool_change`).
    from transversal.services.state_events import fire_pool_change_sfx

    fire_pool_change_sfx(location_id, entity_id, dice, before=was)

    # Fog of war: everyone at this location learns the traits now in the pool.
    from transversal.services.trait_reveal import reveal_pool_traits, trait_setting_ids_from_pool

    if trait_setting_ids_from_pool(dice):
        from transversal.main import _get_repo

        repo = _get_repo()
        # In-memory test repos have no Arango handle; occupant lookup needs one.
        if getattr(repo, "db", None) is not None:
            changed, learner_ids = reveal_pool_traits(repo, location_id, entity_id)
            if changed:
                for s in session_manager.list_active():
                    event_bus.publish(StreamEvent(
                        event="traits_revealed",
                        session_id=s.id,
                        data={
                            "location_id": location_id,
                            "owner_id": entity_id,
                            "learner_ids": learner_ids,
                            "trait_setting_ids": changed,
                        },
                    ))
    return {"saved": True}


@router.post("/{location_id}/pools/{entity_id}/offer-negative")
async def offer_negative(location_id: str, entity_id: str, req: OfferNegativeRequest):
    """Offer a negative trait to an opponent's pool during a contest.

    Toggle: if the trait is already in the opponent's pool, remove it.  On offer,
    reveal the trait to everyone at the location and — when the opponent hadn't
    learned it yet — fire ``on_trait_offered`` so a table SFX can reward the
    offering entity.
    """
    store = get_scene_store()
    opponent_pool = store.get_pool(location_id, req.opponent_id)

    if any(d.get("ts_id") == req.trait_setting_id for d in opponent_pool):
        filtered = [d for d in opponent_pool if d.get("ts_id") != req.trait_setting_id]
        store.save_pool(location_id, req.opponent_id, filtered)
        broadcast_pool_change(location_id, req.opponent_id, dice=filtered, phase="adding", actor_id=entity_id)
        return {"offered": False, "removed": True, "newly_revealed": False}

    added = [
        {"die": die, "source_kind": "trait", "source_id": req.trait_setting_id,
         "label": req.label or die, "ts_id": req.trait_setting_id}
        for die in req.dice
    ]
    new_pool = opponent_pool + added
    store.save_pool(location_id, req.opponent_id, new_pool)
    broadcast_pool_change(location_id, req.opponent_id, dice=new_pool, phase="adding", actor_id=entity_id)

    from transversal.main import _get_repo
    from transversal.services.trait_reveal import reveal_trait_to

    repo = _get_repo()
    ts = repo.get_traitsetting(req.trait_setting_id)
    newly_revealed = False
    if ts is not None:
        was_known = req.opponent_id in ts.known_to
        for occupant in repo.list_entities_by_location(location_id):
            reveal_trait_to(ts, occupant.id)
        repo.update_traitsetting(ts)
        newly_revealed = not was_known

    if newly_revealed and ts is not None:
        from transversal.services.state_events import fire_state_sfx
        fire_state_sfx(entity_id, "", "on_trait_offered", {
            "trait": ts.trait_id,
            "trait_setting": ts.id,
            "owner": ts.entity_id,
            "opponent": req.opponent_id,
            "newly_revealed": "true",
        })

    return {"offered": True, "removed": False, "newly_revealed": newly_revealed}


@router.delete("/{location_id}/pools/{entity_id}")
async def clear_pool(location_id: str, entity_id: str):
    get_scene_store().clear_pool(location_id, entity_id)
    broadcast_pool_change(location_id, entity_id, dice=[], phase="adding")
    return {"cleared": True}


@router.put("/{location_id}/difficulty")
async def set_difficulty(location_id: str, req: DifficultyRequest):
    """Persist (in-memory) the current test difficulty for a location."""
    get_scene_store().set_difficulty(location_id, req.difficulty)

    for s in session_manager.list_active():
        event_bus.publish(StreamEvent(
            event="difficulty_set",
            session_id=s.id,
            data={"difficulty": req.difficulty, "location_id": location_id},
        ))
    return {"saved": True}


@router.get("/{location_id}/difficulty")
async def get_difficulty(location_id: str):
    """Return the current test difficulty for a location (null if unset)."""
    difficulty = get_scene_store().get_difficulty(location_id)
    logger.info(f"[init] get_difficulty loc={location_id} difficulty={difficulty}")
    return {"difficulty": difficulty}


@router.post("/{location_id}/next-beat")
async def next_beat(location_id: str):
    """End the beat: clear every pool and the difficulty at the location."""
    store = get_scene_store()
    cleared = store.list_entities(location_id)
    store.clear_pools(location_id)
    store.clear_difficulty(location_id)

    from transversal.services.contest_tracker import get_contest_tracker
    get_contest_tracker().clear_location(location_id)

    from transversal.main import _get_repo
    from transversal.services.scheduled_events import dispatch_event
    repo = _get_repo()
    if getattr(repo, "db", None) is not None:
        dispatch_event(repo, "beat")

    for s in session_manager.list_active():
        event_bus.publish(StreamEvent(
            event="beat_end",
            session_id=s.id,
            data={"location_id": location_id, "cleared_entities": cleared},
        ))
    return {"cleared": len(cleared)}
