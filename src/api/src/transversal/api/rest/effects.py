"""REST endpoint for SFX triggering."""

from fastapi import APIRouter, Request
from pydantic import BaseModel

from transversal.domain import Effect
from transversal.services.entity_manager import EntityManager
from transversal.services.effects_engine import EffectsEngine, GameEvent

router = APIRouter(prefix="/api/v1/effects", tags=["effects"])


class TriggerRequest(BaseModel):
    entity_id: str
    sfx_name: str
    universe: str = "earth"
    trigger: str = "manual"
    context: dict = {}


class EndRequest(BaseModel):
    entity_id: str
    sfx_id: str


@router.post("/end")
async def end_sfx(req: EndRequest, request: Request):
    """Take back a manual activation that has not committed yet.

    Applies the undos it still owes — the effect reverts and the holds — in
    reverse order of application, drops the deferred parts it never reached, and
    un-arms anything still waiting on a roll. Once the dice have been rolled, or
    a delayed part of the activation has fired, there is nothing left to end and
    the summary reports zero records.
    """
    from transversal.main import _get_repo
    from transversal.services.scheduled_events import end_activation

    summary = end_activation(_get_repo(), req.entity_id, req.sfx_id)
    return {"ended": summary["records"] > 0, **summary}


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

    # A manual activation happens mid-scene, so the contest in play is not in the
    # request. Fill the stakes flag from the tracker unless the caller sent one,
    # so a `high_stakes` condition can gate a sheet move (B97).
    context = dict(req.context or {})
    if "high_stakes" not in context and entity.current_location:
        from transversal.services.contest_tracker import get_contest_tracker
        contest = get_contest_tracker().get(entity.current_location, req.entity_id)
        if contest is not None:
            context["high_stakes"] = bool(contest.high_stakes)

    # Reverse: apply the opposite razmerit effect
    if context.get("reverse"):
        sfx = engine.get(req.sfx_name)
        if sfx is None:
            return {"applied": False, "error": f"SFX '{req.sfx_name}' not found"}
        from transversal.services.effects_applier import effect_registry
        for effect in sfx.effects:
            # Reverse razmerit costs (spend → earn)
            if effect.type == "transfer_razmerit" and effect.action == "spend":
                effect_registry.apply(
                    Effect(timing=effect.timing, type="transfer_razmerit", action="earn",
                           target="self", result=effect.result or "1"),
                    req.entity_id, req.universe, context)
            # Reverse razmerit earnings (earn → spend)
            elif effect.type == "transfer_razmerit" and effect.action == "earn":
                effect_registry.apply(
                    Effect(timing=effect.timing, type="transfer_razmerit", action="spend",
                           target="self", result=effect.result or "1"),
                    req.entity_id, req.universe, context)
        return {"applied": True, "effects_applied": 1, "effects": [{"type": "reverse", "action": "reverse"}]}

    # Create the event
    event = GameEvent(
        type=req.trigger,
        entity_id=req.entity_id,
        universe=req.universe,
        context=context,
    )

    # Process
    from transversal.main import _get_repo
    outcome = engine.process_event_outcome(
        event=event,
        available_sfx_ids=available_sfx_ids,
        razmerit_balance=entity.razmerit,
        repo=_get_repo(),
    )
    from transversal.services.roll_orchestrator import _emit_pending_choices
    _emit_pending_choices(req.entity_id, req.universe, outcome.pending, outcome.structured)
    applied = outcome.applied

    # Effects are already applied by process_event internally.
    # We just report what happened.

    return {
        "applied": len(applied) > 0,
        "effects_applied": len(applied),
        "effects": [{"type": a.type, "action": a.action, "target": a.target} for a in applied],
        "pending": len(outcome.pending) + len(outcome.structured),
    }