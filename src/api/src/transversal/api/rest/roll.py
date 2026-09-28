"""REST endpoints: stateful dice-pool resolution (P2.10d G5).

Every roll is now a pool: the pool is assembled and saved (unrolled), then a
roll endpoint reads the stored pool, sets ``result`` + ``hitch`` on each die,
saves it back, and returns the enriched dice. Selection flags ``role`` via
``/select``. Only rolling is automatic.

  - ``/locations/{loc}/pools/{entity}/cortex-roll``     3+ dice, hitches apply
  - ``/locations/{loc}/pools/{entity}/simplified-roll`` 1-2 dice, deterministic
  - ``/locations/{loc}/pools/{entity}/difficulty-roll`` GM difficulty (no hitches)
  - ``/locations/{loc}/pools/{entity}/select``           flag result/effect dice

The difficulty pool uses the location id as its ``entity`` key (unified pool
concept — the location is its own "entity" for that pool).

``/roll`` is retained as the legacy monolithic resolve for compatibility.
"""

from types import SimpleNamespace
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from transversal.domain import DieSpec, DieType, DicePoolRequest, RollResult
from transversal.services.contest_tracker import broadcast_pool_change, get_contest_tracker
from transversal.services.dice_resolver import (
    determine_tier,
    is_botch,
    resolve as resolve_dice,
    roll_dice as roll_pool_dice,
)
from transversal.services.roll_orchestrator import fire_roll_sfx
from transversal.services.scene_state import get_scene_store

router = APIRouter(prefix="/api/v1", tags=["dice"])


class SelectRequest(BaseModel):
    """Flag which dice are the result/effect dice after a roll."""

    total_indices: list[int] = Field(default_factory=list)
    effect_index: Optional[int] = None


class MarkBoughtRequest(BaseModel):
    """Mark selected rolled dice as bought (consumed by the GM hitch menu)."""

    indices: list[int] = Field(default_factory=list)


def _dice_to_specs(dice: list[dict]) -> list[DieSpec]:
    return [
        DieSpec(
            die=DieType(d["die"]),
            source_kind=d.get("source_kind", "manual"),
            source_id=d.get("source_id", ""),
            label=d.get("label", ""),
            ts_id=d.get("ts_id"),
            resource=d.get("resource", False),
        )
        for d in dice
    ]


def _hitch_threshold(entity_id: str) -> int:
    """How wide this entity's hitch range is — the highest face that hitches.

    Read from the entity rather than sent by the client: the roller is a *view* of
    the rules, not their author, and a client-computed threshold would drift from
    the resolver's ([[B231]]). A difficulty pool's "entity" is a location, so there
    is nothing to ask and the base rule applies — which is moot anyway, since
    ``difficulty_roll`` turns hitches off entirely.
    """
    from transversal.main import _get_repo

    entity = _get_repo().get_entity(entity_id)
    if entity is None:
        return 1
    return max(1, int(getattr(entity, "hitch_threshold", 1) or 1))


def _roll_stored_pool(location_id: str, entity_id: str, hitches_apply: bool) -> tuple[list[dict], list[dict], bool]:
    """Roll the stored pool in place, setting ``result`` + ``hitch`` per die.

    Returns ``(enriched_dice, hitches, botch)`` and saves the enriched dice back.
    """
    store = get_scene_store()
    dice = store.get_pool(location_id, entity_id)
    threshold = _hitch_threshold(entity_id)
    rolls = roll_pool_dice(_dice_to_specs(dice))
    enriched = [
        {**d, "result": r.result, "hitch": r.result <= threshold, "role": None, "bought": False,
         "tier": r.tier.value if r.tier else None,
         "effect_die": r.tier.effect_die.value if r.tier and r.tier.effect_die else None}
        for d, r in zip(dice, rolls)
    ]
    store.save_pool(location_id, entity_id, enriched)
    hitches = [d for d in enriched if d.get("hitch")] if hitches_apply else []
    botch = is_botch(rolls) if hitches_apply and rolls else False
    return enriched, hitches, botch


def _fire_entity_roll_sfx(entity_id: str, rolls: list[dict], hitches: list[dict], botch: bool) -> None:
    """Fire roll SFX for a real entity roll (not the difficulty pool)."""
    from transversal.main import _get_engine, _get_repo

    repo = _get_repo()
    entity = repo.get_entity(entity_id)
    if entity is None:
        return
    fire_roll_sfx(
        _get_engine(), repo, entity_id, entity.current_universe,
        SimpleNamespace(rolls=rolls, hitches=hitches, botch=botch),
    )


@router.post("/roll", response_model=RollResult)
async def roll_dice(request: DicePoolRequest) -> RollResult:
    """Legacy monolithic resolve — kept for compatibility/tests."""
    result = resolve_dice(request)
    from transversal.main import _get_engine, _get_repo

    fire_roll_sfx(_get_engine(), _get_repo(), request.entity_id, request.universe, result)
    return result


@router.post("/locations/{location_id}/pools/{entity_id}/cortex-roll")
async def cortex_roll(location_id: str, entity_id: str):
    """Roll a 3+ dice pool; return rolls + hitches only (client picks)."""
    enriched, hitches, botch = _roll_stored_pool(location_id, entity_id, hitches_apply=True)
    _fire_entity_roll_sfx(entity_id, enriched, hitches, botch)
    broadcast_pool_change(location_id, entity_id, dice=enriched, phase="rolled")
    return {
        "pipeline": "pool",
        "rolls": enriched,
        "hitches": hitches,
        "botch": botch,
        "opposition_total": get_scene_store().get_difficulty(location_id),
    }


class ManualRollRequest(BaseModel):
    """Faces the table rolled physically, one per stored pool die ([[B17]])."""

    results: list[Optional[int]]
    hitches: bool = True


@router.post("/locations/{location_id}/pools/{entity_id}/manual-roll")
async def manual_roll(location_id: str, entity_id: str, req: ManualRollRequest):
    """Enrich the stored pool with faces the *player* rolled ([[B17]]).

    Same contract as ``cortex-roll`` — the pool comes back with ``result``,
    ``hitch``, ``tier`` and ``effect_die`` per die — so picking, resolution and
    contests cannot tell the two apart. The difference is where the numbers come
    from: physical dice, typed or scrolled into the roller, instead of a server
    roll. Every value is checked against its own die's size, so a d6 can never
    show a 9.
    """
    store = get_scene_store()
    dice = store.get_pool(location_id, entity_id)
    if not dice:
        raise HTTPException(status_code=400, detail="There is no pool to record results for")
    if len(req.results) != len(dice):
        raise HTTPException(
            status_code=400,
            detail=f"That pool has {len(dice)} dice, but {len(req.results)} results arrived",
        )

    threshold = _hitch_threshold(entity_id)
    enriched = []
    for d, value in zip(dice, req.results):
        try:
            size = int(str(d.get("die", "")).lstrip("dD"))
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Unknown die {d.get('die')!r}")
        if value is None or not (1 <= int(value) <= size):
            raise HTTPException(
                status_code=400,
                detail=f"A {d.get('die')} cannot show {value!r} (1–{size})",
            )
        face = int(value)
        tier = determine_tier(face)
        enriched.append({
            **d,
            "result": face,
            "hitch": face <= threshold,
            "role": None,
            "bought": False,
            "tier": tier.value if tier else None,
            "effect_die": tier.effect_die.value if tier and tier.effect_die else None,
        })

    store.save_pool(location_id, entity_id, enriched)
    # Mirrors `_roll_stored_pool`: a difficulty determination has no hitches, so
    # its caller turns them off. A botch is every die showing **1** — not "every
    # die hitches", which a widened hitch range would make a different question
    # ([[B231]]).
    hitches = [d for d in enriched if d.get("hitch")] if req.hitches else []
    botch = bool(req.hitches) and all(d["result"] == 1 for d in enriched)
    _fire_entity_roll_sfx(entity_id, enriched, hitches, botch)
    broadcast_pool_change(location_id, entity_id, dice=enriched, phase="rolled")
    return {
        "pipeline": "pool",
        "rolls": enriched,
        "hitches": hitches,
        "botch": botch,
        "opposition_total": store.get_difficulty(location_id),
    }


@router.post("/locations/{location_id}/pools/{entity_id}/simplified-roll")
async def simplified_roll(location_id: str, entity_id: str):
    """Roll 1-2 dice; derive highest/tier/effect deterministically."""
    enriched, hitches, botch = _roll_stored_pool(location_id, entity_id, hitches_apply=True)
    highest = max((d["result"] for d in enriched if d.get("result") is not None), default=0)
    tier = determine_tier(highest)
    _fire_entity_roll_sfx(entity_id, enriched, hitches, botch)
    broadcast_pool_change(location_id, entity_id, dice=enriched, phase="rolled")
    return {
        "pipeline": "simplified",
        "rolls": enriched,
        "hitches": hitches,
        "botch": botch,
        "highest": highest,
        "tier": tier.value,
        "effect_die": tier.effect_die.value if tier.effect_die else None,
        "opposition_total": get_scene_store().get_difficulty(location_id),
    }


@router.post("/locations/{location_id}/pools/{entity_id}/difficulty-roll")
async def difficulty_roll(location_id: str, entity_id: str):
    """Roll GM difficulty dice (no hitches); the client picks the total."""
    enriched, _, _ = _roll_stored_pool(location_id, entity_id, hitches_apply=False)
    broadcast_pool_change(location_id, entity_id, dice=enriched, phase="rolled")
    return {"pipeline": "pool", "rolls": enriched}


@router.post("/locations/{location_id}/pools/{entity_id}/hitches/mark-bought")
async def mark_hitches_bought(location_id: str, entity_id: str, req: MarkBoughtRequest):
    """Mark the given pool dice as bought so the GM can't re-buy them."""
    store = get_scene_store()
    dice = store.get_pool(location_id, entity_id)
    for i in req.indices:
        if 0 <= i < len(dice):
            dice[i]["bought"] = True
    store.save_pool(location_id, entity_id, dice)
    broadcast_pool_change(location_id, entity_id, dice=dice, phase="rolled")
    return {"dice": dice}


@router.post("/locations/{location_id}/pools/{entity_id}/select")
async def select_dice(location_id: str, entity_id: str, req: SelectRequest):
    """Flag the chosen result/effect dice (``role``) on the stored pool."""
    store = get_scene_store()
    dice = store.get_pool(location_id, entity_id)
    for d in dice:
        d["role"] = None
    for i in req.total_indices:
        if 0 <= i < len(dice):
            dice[i]["role"] = "total"
    if req.effect_index is not None and 0 <= req.effect_index < len(dice):
        dice[req.effect_index]["role"] = "effect"
    store.save_pool(location_id, entity_id, dice)
    broadcast_pool_change(location_id, entity_id, dice=dice, phase="selected")
    return {"dice": dice}


@router.post("/locations/{location_id}/pools/{entity_id}/resolve")
async def resolve_pool(location_id: str, entity_id: str):
    """Mark a rolled+selected pool as resolved (committed).

    Sets the persisted phase to ``resolved`` so a client re-fetch (tab switch
    or refresh) restores the committed result screen rather than the picking
    screen. Also fires the roll-resolution events (``on_set``/``on_result``)
    that the contest ``/set`` endpoint fires, so a non-contest test reaches the
    same auto-fire + armed SFX.
    """
    store = get_scene_store()
    dice = store.get_pool(location_id, entity_id)

    total = sum(d.get("result") or 0 for d in dice if d.get("role") == "total")
    effect = next((d for d in dice if d.get("role") == "effect"), None)
    effect_die = effect.get("die") if effect else None
    difficulty = store.get_difficulty(location_id)
    tier = None
    margin = None
    if difficulty is not None:
        tier = "success" if total > difficulty else "fail"
        # Signed, and only this caller can say it: the difficulty is not on the dice.
        margin = total - difficulty

    from transversal.main import _get_repo
    entity = _get_repo().get_entity(entity_id)
    universe = entity.current_universe if entity else ""

    from transversal.services.roll_purpose import roll_purpose
    roll_context = {"effect_die": effect_die, "total": total, "tier": tier,
                    "margin": margin, "purpose": roll_purpose(dice, _get_repo()),
                    "rolls": dice}
    # Whether the contest in play is high-stakes, so a roll-timed effect can gate
    # on it (B97). Read from the tracker: the resolve call carries no stakes.
    from transversal.services.contest_tracker import get_contest_tracker
    contest = get_contest_tracker().get(location_id, entity_id)
    if contest is not None:
        roll_context["high_stakes"] = bool(contest.high_stakes)

    from transversal.services.roll_deferral import fire_armed
    fire_armed(entity_id, "on_set", universe, roll_context)
    fire_armed(entity_id, "on_result", universe, roll_context)

    from transversal.services.state_events import fire_state_sfx
    fire_state_sfx(entity_id, universe, "on_set",
                   {"effect_die": effect_die, "total": total, "margin": margin,
                    "purpose": roll_context["purpose"]})

    # This is the *test* path — a contest commits through the tracker's own
    # `/set`. Record which one it was while the flow is known: a challenge made
    # *later* must not turn a test already resolved into a contest.
    from transversal.domain import RollKind
    from transversal.services.contest_tracker import get_contest_tracker
    get_contest_tracker().mark_kind(location_id, entity_id, RollKind.TEST)

    from transversal.services.roll_orchestrator import fire_result_sfx
    fire_result_sfx(entity_id, universe, dice, effect_die=effect_die, total=total,
                    margin=margin)

    # A test is a Blue Book entry too ([[B177]]): the roller's own dice on the
    # left, the difficulty it was rolled against on the right. Recorded here —
    # the test path — so a pool later challenged as a contest does not turn a
    # test already resolved into one.
    from transversal.services import contest_history
    contest_history.record_test(
        location_id,
        entity_id,
        dice,
        total=total,
        effect_die=effect_die,
        difficulty=difficulty,
        universe=universe,
        high_stakes=bool(contest.high_stakes) if contest is not None else False,
    )

    broadcast_pool_change(location_id, entity_id, dice=dice, phase="resolved")
    return {"phase": "resolved"}


@router.get("/pools")
async def list_all_pools():
    """Return every saved dice pool across all locations (tabs are global)."""
    return {"pools": get_scene_store().list_all_pools()}


@router.get("/activity")
async def get_activity():
    """Return the full in-memory activity snapshot for the GM activity view.

    - ``pools``: {location_id: {entity_id: dice}} — location dimension intact.
    - ``difficulties``: {location_id: difficulty} — set test difficulties.
    - ``contests``: one entry per active contest, each with its ``parties``
      (multi-party-ready), location, pending decision, and stakes.
    """
    store = get_scene_store()
    return {
        "pools": store.list_all_pools_grouped(),
        "difficulties": store.list_difficulties(),
        "contests": get_contest_tracker().list_all_contests(),
    }
