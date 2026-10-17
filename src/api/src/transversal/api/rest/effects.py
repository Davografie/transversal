"""REST endpoint for SFX triggering."""

from fastapi import APIRouter, Request
from pydantic import BaseModel

from transversal.services.entity_manager import EntityManager
from transversal.services.effects_engine import EffectsEngine, GameEvent

router = APIRouter(prefix="/api/v1/effects", tags=["effects"])


class TriggerRequest(BaseModel):
    entity_id: str
    sfx_name: str
    universe: str = "earth"
    trigger: str = "manual"
    context: dict = {}


class ApplyRequest(BaseModel):
    """One effect, as the editor holds it, and who to run it on."""

    entity_id: str
    #: The `EffectInput` shape the effect form edits — camelCase, specs included.
    effect: dict = {}
    context: dict = {}


class EndRequest(BaseModel):
    entity_id: str
    sfx_id: str
    #: The caller is dropping an activation it still holds a **question** for.
    #: Such an activation may have booked nothing at all — `sfx-gift` blocks on its
    #: first choice *before* applying anything, so it has no hold, no revert row and
    #: no armed entry — and then `end_activation` finds nothing, the take-back is
    #: silent, and the chip the press lit stays lit (the human, 2026-09-29). The
    #: client is the only one that knows a question is open, so it says so.
    pending: bool = False


def _with_notes(applied: list, notes: list[dict]) -> list[dict]:
    """Each applied effect, joined to what it did.

    Joined on the applied order: ``notes`` is appended by the commit as each effect
    lands, so the nth note is the nth effect. Effects that never reach the commit
    path (a razmerit transfer, a passthrough) simply have no note, and keep the
    bare shape — an absent note is honest where an invented one is not.
    """
    out: list[dict] = []
    for i, a in enumerate(applied):
        entry = {"type": a.type, "action": a.action, "target": a.target}
        if i < len(notes):
            entry["note"] = notes[i].get("note", "")
        out.append(entry)
    return out


@router.post("/apply")
async def apply_effect(req: ApplyRequest, request: Request):
    """Run **one** effect against an entity — the GM effect editor's test run.

    The author is looking at a single effect and wants to know what it does, now,
    on the entity they are acting as. Firing the whole rule would run the effect's
    neighbours too and answer a different question.

    Two things are deliberately *not* done, and they are what makes this a test
    rather than a fire:

    - **nothing is broadcast.** No `sfx_choice_required`, no `sfx_updated`: the
      question count comes back in the reply instead. A test run that pops a picker
      across the table is not a test.
    - **nothing is armed or scheduled.** A deferred part simply does not fire;
      `commit_effects` applies what is immediate.

    So this reports; it does not announce. A 404 means the entity is not there, a
    422 means the body is not an effect — both are the author's to fix, and both
    say which.
    """
    from fastapi import HTTPException

    from transversal.main import _get_em, _get_repo
    from transversal.services.effects_commit import commit_effects
    from transversal.services.effects_engine.wire import effect_from_wire_dict

    em = _get_em()
    entity = em.get(req.entity_id)
    if entity is None:
        raise HTTPException(status_code=404, detail=f"Entity '{req.entity_id}' not found")

    try:
        effect = effect_from_wire_dict(req.effect or {})
    except Exception as e:  # pydantic lives below this; the body is author input
        raise HTTPException(status_code=422, detail=f"not an effect: {e}") from e

    repo = _get_repo()
    result = commit_effects(entity, [effect], repo, req.context or None)
    fresh = repo.get_entity(req.entity_id) or entity

    return {
        # What each effect did, or why it did nothing — the summary is the whole
        # point, and an empty list is an answer, not a failure.
        "applied": [a.summary for a in result.applied],
        "pending": len(result.pending_choices),
        "effect": {"type": effect.type, "action": effect.action},
        # Read back rather than echoed: the effect may have moved the entity, and
        # "where they are now" is the thing an author checks.
        "entity": {
            "id": fresh.id,
            "name": getattr(fresh, "name", ""),
            "location_id": getattr(fresh, "current_location", None),
            "universe": getattr(fresh, "current_universe", ""),
            "razmerit": getattr(fresh, "razmerit", 0),
        },
    }


@router.post("/end")
async def end_sfx(req: EndRequest, request: Request):
    """Take back a manual activation that has not committed yet.

    Applies the undos it still owes — the effect reverts and the holds — in
    reverse order of application, drops the deferred parts it never reached, and
    un-arms anything still waiting on a roll. Once the dice have been rolled, or
    a delayed part of the activation has fired, there is nothing left to end and
    the summary reports zero records.

    ``pending`` covers the case where there was never anything to end: an
    activation blocked on a question it has not answered yet may have booked no
    row at all. It is still **over** when the caller drops it, so ``ended`` says
    so and the ``sfx_ended`` push goes out — otherwise the only client that knows
    (the one that pressed) keeps a chip lit and every other screen keeps its card.
    """
    from transversal.main import _get_repo
    from transversal.services.scheduled_events import end_activation

    summary = end_activation(_get_repo(), req.entity_id, req.sfx_id)
    ended = bool(summary["records"]) or req.pending
    if ended:
        from transversal.services.effects_engine import _emit_sfx_ended

        _emit_sfx_ended(req.entity_id, req.sfx_id)
    return {"ended": ended, "pending": req.pending, **summary}


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

    # (The legacy ``{"reverse": true}`` branch is retired: a rule's costs are
    # reversed by *ending the activation* — ``POST /effects/end`` — which applies
    # the same declared inverses the engine books. Two reversal mechanisms could
    # disagree, and did: the old one reversed an earn a second time.)

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
    # A manual press on a character sheet: the question belongs with the sheet it was
    # pressed on, not in the roller (the author's call, 2026-09-26).
    _emit_pending_choices(req.entity_id, req.universe, outcome.pending,
                          outcome.structured, outcome.loops, origin="sheet")
    applied = outcome.applied

    # Effects are already applied by process_event internally.
    # We just report what happened.

    return {
        "applied": len(applied) > 0,
        "effects_applied": len(applied),
        # What each effect did, or why it did nothing. `applied` says *which* ran;
        # this says what happened to each, which is the difference the author could
        # not see when Gift reported two effects for one real one and one no-op
        # ([[B236]]). An effect with no recorded note keeps the bare shape rather
        # than inventing one.
        "effects": _with_notes(applied, outcome.notes),
        "pending": len(outcome.pending) + len(outcome.structured),
    }