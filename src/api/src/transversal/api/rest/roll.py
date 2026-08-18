"""REST endpoint: dice resolution."""

from fastapi import APIRouter

from transversal.domain import DicePoolRequest, RollResult
from transversal.services.dice_resolver import resolve as resolve_dice
from transversal.services.roll_orchestrator import fire_roll_sfx

router = APIRouter(prefix="/api/v1", tags=["dice"])


@router.post("/roll", response_model=RollResult)
async def roll_dice(request: DicePoolRequest) -> RollResult:
    """Resolve a dice pool using the appropriate pipeline.

    Stateless — the resolver does not persist state.
    After resolution, automatic SFX (on_roll / on_complication / on_botch /
    on_success / on_failure) fire against the rolling entity's ownership.
    """
    result = resolve_dice(request)
    from transversal.main import _get_engine, _get_repo

    fire_roll_sfx(_get_engine(), _get_repo(), request.entity_id, request.universe, result)
    return result
