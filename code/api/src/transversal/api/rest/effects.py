"""REST endpoint for SFX triggering."""

from fastapi import APIRouter, Request
from pydantic import BaseModel

from transversal.domain import EffectAction
from transversal.services.entity_manager import EntityManager
from transversal.services.effects_engine import EffectsEngine, GameEvent

router = APIRouter(prefix="/api/v1/effects", tags=["effects"])


class TriggerRequest(BaseModel):
    entity_id: str
    sfx_name: str
    universe: str = "earth"
    trigger: str = "on_activate"
    context: dict = {}


@router.post("/trigger")
async def trigger_sfx(req: TriggerRequest, request: Request):
    """Trigger an SFX for an entity.

    Creates a GameEvent with the specified trigger type and
    processes it through the effects engine. The engine matches
    the event against the entity's available SFXs, checks costs,
    and applies effects via the registered handlers.
    """
    from transversal.main import _get_em, _get_engine
    em: EntityManager = _get_em()
    engine = _get_engine()

    # Get entity razmerit and available SFXs
    entity = em.get(req.entity_id)
    if entity is None:
        return {"applied": False, "error": f"Entity '{req.entity_id}' not found"}

    # Only activate the specifically requested SFX
    available_sfx_ids: list[str] = [req.sfx_name] if req.sfx_name else []

    # Reverse: apply the opposite razmerit effect
    if req.context.get("reverse"):
        sfx = engine.get(req.sfx_name)
        if sfx is None:
            return {"applied": False, "error": f"SFX '{req.sfx_name}' not found"}
        # Reverse the cost: spend becomes earn, earn becomes spend
        from transversal.services.effects_applier import effect_registry
        if sfx.cost > 0:
            # Normal: cost was spent. Reverse: refund (earn)
            effect_registry.apply(
                EffectAction(type="transfer_razmerit", action="earn", target="self", result=str(sfx.cost)),
                req.entity_id, req.universe, req.context)
        # Reverse the SFX's own razmerit effects
        for effect in sfx.effects:
            if effect.type == "transfer_razmerit" and effect.action == "earn":
                # Normal: earned. Reverse: spend
                effect_registry.apply(
                    EffectAction(type="transfer_razmerit", action="spend", target="self", result=effect.result or "1"),
                    req.entity_id, req.universe, req.context)
        return {"applied": True, "effects_applied": 1, "effects": [{"type": "reverse", "action": "reverse"}]}

    # Create the event
    event = GameEvent(
        type=req.trigger,
        entity_id=req.entity_id,
        universe=req.universe,
        context=req.context,
    )

    # Process
    applied = engine.process_event(
        event=event,
        available_sfx_ids=available_sfx_ids,
        razmerit_balance=entity.razmerit,
    )

    # Effects are already applied by process_event internally.
    # We just report what happened.

    return {
        "applied": len(applied) > 0,
        "effects_applied": len(applied),
        "effects": [{"type": a.type, "action": a.action, "target": a.target} for a in applied],
    }
