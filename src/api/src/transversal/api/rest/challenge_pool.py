"""REST endpoints for challenge pool operations (spend / recover a die)."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from transversal.domain import DieType
from transversal.services.challenge_pools import (
    ChallengePoolError,
    check_challenge_completion,
    fire_challenge_completed,
    recover_challenge_die,
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


class ChallengeRecoverRequest(BaseModel):
    die: str  # "d4" .. "d12"
    count: int = 1


class ChallengeRecoverResponse(BaseModel):
    traitsetting_id: str
    die: str
    dice: list[str]        # dice in the pool after the refund
    capacity: list[str]


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


@router.post("/{traitsetting_id}/recover", response_model=ChallengeRecoverResponse)
async def recover(traitsetting_id: str, req: ChallengeRecoverRequest) -> ChallengeRecoverResponse:
    """Refund dice back into a challenge pool.

    The mirror of the resource auto-recover: a die spent into a pool that was
    then pulled back out before rolling was never really spent. Completion is
    not re-checked (see ``recover_challenge_die``).
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

    if req.count < 1:
        raise HTTPException(status_code=400, detail="count must be at least 1")

    try:
        for _ in range(req.count):
            ts = recover_challenge_die(ts, die, em, session_id="")
    except ChallengePoolError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return ChallengeRecoverResponse(
        traitsetting_id=ts.id,
        die=req.die,
        dice=[d.value for d in ts.dice],
        capacity=[d.value for d in (ts.capacity or [])],
    )
