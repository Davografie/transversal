"""REST endpoints: dice resolution.

Three decomposed endpoints (P2.10d G5) replace the monolithic resolve for the
game UI. Only rolling is automatic — the client drives total/effect selection:

  - ``/cortex-roll``     3+ dice, hitches apply → rolls + hitches + botch
  - ``/simplified-roll`` 1-2 dice → rolls + hitches + botch + highest/tier/effect
  - ``/difficulty-roll`` GM difficulty → rolls only (no hitches, no SFX)

``/roll`` is retained as the legacy monolithic resolve for compatibility.
"""

from types import SimpleNamespace

from fastapi import APIRouter
from pydantic import BaseModel, Field, field_validator

from transversal.domain import (
    DicePoolRequest,
    DieSpec,
    RollResult,
    _coerce_die_list,
)
from transversal.services.dice_resolver import (
    detect_hitches,
    determine_tier,
    is_botch,
    resolve as resolve_dice,
    roll_dice as roll_pool_dice,
)
from transversal.services.roll_orchestrator import fire_roll_sfx

router = APIRouter(prefix="/api/v1", tags=["dice"])


class DifficultyRollRequest(BaseModel):
    """A GM difficulty roll is stateless — just the dice, no entity/hitches."""

    dice: list[DieSpec] = Field(default_factory=list)

    @field_validator("dice", mode="before")
    @classmethod
    def _coerce_dice(cls, v):
        return _coerce_die_list(v)


def _static_difficulty(request: DicePoolRequest):
    """Echo the static difficulty back so the client can compare against it."""
    if request.opposition and request.opposition.type == "static_difficulty":
        return request.opposition.static_difficulty
    return None


def _fire_roll_sfx(request: DicePoolRequest, rolls, hitches, botch) -> None:
    """Fire roll SFX against the decomposed result (rolls/hitches/botch)."""
    from transversal.main import _get_engine, _get_repo

    fire_roll_sfx(
        _get_engine(), _get_repo(), request.entity_id, request.universe,
        SimpleNamespace(rolls=rolls, hitches=hitches, botch=botch),
    )


@router.post("/roll", response_model=RollResult)
async def roll_dice(request: DicePoolRequest) -> RollResult:
    """Legacy monolithic resolve — kept for compatibility/tests.

    Superseded by the decomposed endpoints below.
    """
    result = resolve_dice(request)
    from transversal.main import _get_engine, _get_repo

    fire_roll_sfx(_get_engine(), _get_repo(), request.entity_id, request.universe, result)
    return result


@router.post("/cortex-roll")
async def cortex_roll(request: DicePoolRequest):
    """Roll a 3+ dice pool and return rolls + hitches only.

    The client picks the two dice for the total and the effect die.
    """
    rolls = roll_pool_dice(request.dice)
    hitches = detect_hitches(rolls) if request.hitches_apply else []
    botch = is_botch(rolls) if request.hitches_apply else False
    _fire_roll_sfx(request, rolls, hitches, botch)
    return {
        "pipeline": "pool",
        "rolls": rolls,
        "hitches": hitches,
        "botch": botch,
        "opposition_total": _static_difficulty(request),
    }


@router.post("/simplified-roll")
async def simplified_roll(request: DicePoolRequest):
    """Roll 1-2 dice and derive highest/tier/effect deterministically."""
    rolls = roll_pool_dice(request.dice)
    hitches = detect_hitches(rolls) if request.hitches_apply else []
    botch = is_botch(rolls) if request.hitches_apply else False
    highest = max(r.result for r in rolls)
    tier = determine_tier(highest)
    _fire_roll_sfx(request, rolls, hitches, botch)
    return {
        "pipeline": "simplified",
        "rolls": rolls,
        "hitches": hitches,
        "botch": botch,
        "highest": highest,
        "tier": tier.value,
        "effect_die": tier.effect_die.value if tier.effect_die else None,
        "opposition_total": _static_difficulty(request),
    }


@router.post("/difficulty-roll")
async def difficulty_roll(request: DifficultyRollRequest):
    """Roll GM difficulty dice (no hitches). The client picks the total."""
    rolls = roll_pool_dice(request.dice)
    return {"pipeline": "pool", "rolls": rolls}
