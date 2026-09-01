"""REST endpoint for challenge pool operations (spend a die)."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from transversal.domain import DieType
from transversal.services.challenge_pools import (
    ChallengePoolError,
    check_challenge_completion,
    fire_challenge_completed,
    spend_challenge_die,
)

router = APIRouter(prefix="/api/v1/challenge-pool", tags=["challenge-pool"])


class ChallengeSpendRequest(BaseModel):
    die: str  # "d4" .. "d12"
    destination: str = "opposition"  # "opposition" (doom) | "pool" (progress partial use)


class ChallengeSpendResponse(BaseModel):
    traitsetting_id: str
    die: str
    resource: bool
    dice: list[str]        # remaining dice in the pool
    capacity: list[str]    # target/ceiling (empty when unset)
    completed: bool        # positive pool reached capacity on this spend


@router.post("/{traitsetting_id}/spend", response_model=ChallengeSpendResponse)
async def spend(traitsetting_id: str, req: ChallengeSpendRequest) -> ChallengeSpendResponse:
    """Spend one die from a challenge pool.

    - ``destination="opposition"``: a doom die the GM spends to oppose
      (returned as a plain die to route into the GMC/difficulty pool).
    - ``destination="pool"``: a progress die spent for partial use (returned
      flagged ``resource`` to add to the caller's pool as a resource die).
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

    if req.destination not in ("opposition", "pool"):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid destination: {req.destination} (expected 'opposition' or 'pool')",
        )

    try:
        result = spend_challenge_die(ts, die, em, destination=req.destination)
    except ChallengePoolError as e:
        raise HTTPException(status_code=400, detail=str(e))

    completed = fire_challenge_completed(result.ts)

    return ChallengeSpendResponse(
        traitsetting_id=result.ts.id,
        die=result.die.value,
        resource=result.resource,
        dice=[d.value for d in result.ts.dice],
        capacity=[d.value for d in (result.ts.capacity or [])],
        completed=completed,
    )
