"""REST endpoint: dice resolution."""

from fastapi import APIRouter

from transversal.domain import DicePoolRequest, RollResult
from transversal.services.dice_resolver import resolve as resolve_dice

router = APIRouter(prefix="/api/v1", tags=["dice"])


@router.post("/roll", response_model=RollResult)
async def roll_dice(request: DicePoolRequest) -> RollResult:
    """Resolve a dice pool using the appropriate pipeline.

    Stateless — the resolver does not persist state.
    The caller is responsible for applying results (razmerit changes,
    challenge pool updates, trait modifications).
    """
    return resolve_dice(request)
