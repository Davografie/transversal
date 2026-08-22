"""REST endpoint for resource pool operations (spend/recover dice)."""

from collections import Counter

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from transversal.domain import DieType, dice_list_to_rating
from transversal.services.resource_pool import (
    ResourcePoolError,
    spend_die,
    recover_die,
)

router = APIRouter(prefix="/api/v1/resource-pool", tags=["resource-pool"])


class ResourceDieRequest(BaseModel):
    die: str  # "d4", "d6", etc.
    count: int = 1


class ResourceDieResponse(BaseModel):
    traitsetting_id: str
    die_type: str
    rating: str          # current rating (available dice only)
    dice: list[str]      # currently available dice
    spent: list[str]     # spent-but-recoverable dice
    max_rating: str      # capacity rating (dice + spent)
    total: int           # current die count
    max_total: int       # capacity die count


def _build_response(ts_id: str, die: str) -> ResourceDieResponse:
    """Build a response from the current TraitSetting state."""
    from transversal.main import _get_em
    em = _get_em()
    ts = em.repo.get_traitsetting(ts_id)
    if ts is None:
        raise ResourcePoolError(f"TraitSetting '{ts_id}' not found")

    dice_values = [d.value for d in ts.dice]
    spent_values = [d.value for d in ts.spent_dice]

    if ts.dice:
        counts = Counter(ts.dice)
        die_type = max(counts.items(), key=lambda x: x[1])[0].value
    elif ts.spent_dice:
        counts = Counter(ts.spent_dice)
        die_type = max(counts.items(), key=lambda x: x[1])[0].value
    else:
        die_type = die

    return ResourceDieResponse(
        traitsetting_id=ts_id,
        die_type=die_type,
        rating=dice_list_to_rating(ts.dice),
        dice=dice_values,
        spent=spent_values,
        max_rating=dice_list_to_rating(ts.dice + ts.spent_dice),
        total=len(ts.dice),
        max_total=len(ts.dice) + len(ts.spent_dice),
    )


@router.post("/{traitsetting_id}/spend", response_model=ResourceDieResponse)
async def spend(traitsetting_id: str, req: ResourceDieRequest) -> ResourceDieResponse:
    """Spend dice from a resource trait's pool.

    Moves dice from the trait's available dice into its spent ledger, one at
    a time.  Called when a player adds a resource die to their dice pool.
    """
    from transversal.main import _get_em
    em = _get_em()

    ts = em.repo.get_traitsetting(traitsetting_id)
    if ts is None:
        raise HTTPException(status_code=404, detail=f"TraitSetting '{traitsetting_id}' not found")

    try:
        die = DieType(req.die)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid die type: {req.die}")

    available = sum(1 for d in ts.dice if d == die)
    if req.count > available:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot spend {req.count} {die.value} dice — only {available} available",
        )

    try:
        for _ in range(req.count):
            ts = spend_die(ts, die, em, session_id="")
    except ResourcePoolError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return _build_response(traitsetting_id, req.die)


@router.post("/{traitsetting_id}/recover", response_model=ResourceDieResponse)
async def recover(traitsetting_id: str, req: ResourceDieRequest) -> ResourceDieResponse:
    """Recover spent dice back to a resource trait's pool.

    Moves dice from the trait's spent ledger back into its available dice,
    one at a time.  Recovery is bounded by the ledger, so it can never push
    the pool past its capacity.
    """
    from transversal.main import _get_em
    em = _get_em()

    ts = em.repo.get_traitsetting(traitsetting_id)
    if ts is None:
        raise HTTPException(status_code=404, detail=f"TraitSetting '{traitsetting_id}' not found")

    try:
        die = DieType(req.die)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid die type: {req.die}")

    recoverable = sum(1 for d in ts.spent_dice if d == die)
    if req.count > recoverable:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot recover {req.count} {die.value} dice — only {recoverable} spent",
        )

    try:
        for _ in range(req.count):
            ts = recover_die(ts, die, em, session_id="")
    except ResourcePoolError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return _build_response(traitsetting_id, req.die)
