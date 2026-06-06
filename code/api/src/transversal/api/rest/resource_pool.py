"""REST endpoint for resource pool operations (spend/recover dice)."""

from collections import Counter

from fastapi import APIRouter
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
    rating: str
    dice: list[str]
    total: int


def _build_response(ts_id: str, die: str) -> ResourceDieResponse:
    """Build a response from the current TraitSetting state."""
    from transversal.main import _get_em
    em = _get_em()
    ts = em.repo.get_traitsetting(ts_id)
    if ts is None:
        raise ResourcePoolError(f"TraitSetting '{ts_id}' not found")

    dice_values = [d.value for d in ts.dice]

    if ts.dice:
        counts = Counter(ts.dice)
        die_type = max(counts.items(), key=lambda x: x[1])[0].value
    else:
        die_type = die

    return ResourceDieResponse(
        traitsetting_id=ts_id,
        die_type=die_type,
        rating=dice_list_to_rating(ts.dice),
        dice=dice_values,
        total=len(ts.dice),
    )


@router.post("/{traitsetting_id}/spend", response_model=ResourceDieResponse)
async def spend(traitsetting_id: str, req: ResourceDieRequest) -> ResourceDieResponse:
    """Spend dice from a resource trait's pool.

    Removes dice from the trait's dice array, one at a time.
    Called when a player adds a resource die to their dice pool.
    """
    from transversal.main import _get_em
    em = _get_em()

    ts = em.repo.get_traitsetting(traitsetting_id)
    if ts is None:
        raise ResourcePoolError(f"TraitSetting '{traitsetting_id}' not found")

    try:
        die = DieType(req.die)
    except ValueError:
        raise ResourcePoolError(f"Invalid die type: {req.die}")

    for _ in range(req.count):
        ts = spend_die(ts, die, em, session_id="")

    return _build_response(traitsetting_id, req.die)


@router.post("/{traitsetting_id}/recover", response_model=ResourceDieResponse)
async def recover(traitsetting_id: str, req: ResourceDieRequest) -> ResourceDieResponse:
    """Recover spent dice back to a resource trait's pool.

    Appends dice to the trait's dice array, one at a time.
    Called when a player removes a resource die from their dice pool
    before rolling.
    """
    from transversal.main import _get_em
    em = _get_em()

    ts = em.repo.get_traitsetting(traitsetting_id)
    if ts is None:
        raise ResourcePoolError(f"TraitSetting '{traitsetting_id}' not found")

    try:
        die = DieType(req.die)
    except ValueError:
        raise ResourcePoolError(f"Invalid die type: {req.die}")

    for _ in range(req.count):
        ts = recover_die(ts, die, em, session_id="")

    return _build_response(traitsetting_id, req.die)
