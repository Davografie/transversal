"""Auto-fire SFX after a roll or contest resolves.

The dice resolver stays stateless; these functions run *after* resolution and
drive the effects engine using each entity's current SFX ownership + razmerit.

Automatic SFX apply immediately (synchronously), before any consequence menu
or next phase appears. Immediate effects with a ``{choose_*}`` target are not
applied blindly — they are emitted as a ``sfx_choice_required`` SSE event so the
frontend can prompt the user and re-apply once resolved.
"""

from __future__ import annotations

from transversal.domain import RollResult
from transversal.services import effects_applier
from transversal.services.effects_engine import (
    EffectsEngine,
    GameEvent,
)
from transversal.services.sfx_owner import get_available_sfx_ids


def _entity_sfx_context(repo, entity_id: str, universe: str) -> tuple[list[str], int]:
    """Return (available_sfx_ids, razmerit_balance) for an entity."""
    entity = repo.get_entity(entity_id)
    if entity is None:
        return [], 0
    return get_available_sfx_ids(entity_id, universe, repo), entity.razmerit


def loop_choice_to_dict(loop) -> dict:
    """The wire shape for a loop prompt — a rule offering to run one more round.

    ``loop: True`` is what tells the picker this is a yes/no rather than a
    candidate list: the same ``sfx_choice_required`` channel carries both, so a
    table that already knows how to answer a ``choose`` step knows how to answer
    this. The payload carries the moment, so ``resolveSfxLoop`` can re-run *this
    rule for this change* — its conditions and targets re-resolved from live
    state, which is why a round that has become impossible simply does nothing.
    """
    return {
        "loop": True,
        "sfx_id": loop.sfx_id,
        "sfx_name": loop.sfx_name,
        "sfx_description": loop.sfx_description,
        "iteration": loop.iteration,
        "event_type": loop.event_type,
        "entity_id": loop.entity_id,
        "universe": loop.universe,
        "context": loop.context,
    }


def _emit_pending_choices(entity_id: str, universe: str, effects: list,
                          structured: list | None = None,
                          loops: list | None = None,
                          origin: str = "roll") -> None:
    """Broadcast a ``sfx_choice_required`` SSE event for unresolved effects.

    ``effects`` are deferred **context-policy** choices (``{choose_projection}``);
    ``structured`` are ``StructuredChoice``s from a ``choose`` step in a spec or
    reference, which carry their own pre-resolved candidates; ``loops`` are rules
    that would re-enter the change they are already handling, offered a round at
    a time rather than recursed.

    ``origin`` says **where the question came from**, so the client can put it where
    the author of the question is looking (the author's rule, 2026-09-26): ``sheet``
    is a manual press on a character sheet, ``roll`` is a roll or a roll-timed effect
    firing, and ``auto`` is a state change or a timer nobody pressed — a question with
    no obvious place, which therefore wants a floating panel rather than the roller.
    Every choice in the event carries it, so a client that renders one copy of the
    table can decide where that copy goes. Follow-ups inherit it client-side, because
    the client is the one that knows where it is still rendering.
    """
    if not effects and not structured and not loops:
        return

    from transversal.api.sse.bus import StreamEvent, event_bus
    from transversal.services.effects_engine import effect_to_wire_dict
    from transversal.services.session_manager import session_manager

    choices = []
    for p in effects:
        choices.append({
            "origin": origin,
            "kind": p.kind,
            "field": p.field_name,
            "sfx_name": p.sfx_name,
            "sfx_description": p.sfx_description,
            "effect": effect_to_wire_dict(p.effect),
            **({"continuation": [effect_to_wire_dict(e) for e in p.continuation]} if p.continuation else {}),
        })
    for c in (structured or []):
        choices.append({
            "origin": origin,
            "structured": True,
            "element": c.element,
            "candidates": c.candidates,
            "count": c.count,
            "field": c.field,
            "step_index": c.step_index,
            "source_kind": c.source_kind,
            "source_id": c.source_id,
            "source_sfx_id": c.source_sfx_id,
            "answers_so_far": c.answers_so_far,
            "sfx_name": c.sfx_name,
            "sfx_description": c.sfx_description,
            "effect": effect_to_wire_dict(c.effect),
            **({"continuation": [effect_to_wire_dict(e) for e in c.continuation]} if c.continuation else {}),
        })
    for l in (loops or []):
        choices.append(loop_choice_to_dict(l))
    for session in session_manager.list_active():
        event_bus.publish(StreamEvent(
            event="sfx_choice_required",
            session_id=session.id,
            data={
                "entity_id": entity_id,
                "universe": universe,
                "choices": choices,
            },
        ))


def _rolls_as_dicts(roll_result) -> list[dict]:
    """Normalise a roll result's dice to dicts for ``fire_armed``.

    The active roll path already yields enriched dicts; the legacy monolithic
    resolver yields ``DieRoll`` models. Both carry the identity/selection fields
    (``ts_id``/``source_kind``/…) that ``fire_armed`` reads via ``.get``.
    """
    rolls = getattr(roll_result, "rolls", None) or []
    out: list[dict] = []
    for r in rolls:
        if isinstance(r, dict):
            out.append(r)
        elif hasattr(r, "model_dump"):
            out.append(r.model_dump())
        elif hasattr(r, "__dict__"):
            out.append(vars(r))
    return out


def fire_roll_sfx(
    engine: EffectsEngine,
    repo,
    entity_id: str,
    universe: str,
    roll_result: RollResult,
) -> list:
    """Fire automatic SFX for a single test roll. Returns applied effects."""
    # Tick the central ``rolls`` timer first: a ``rolls:N`` duration on an
    # immediate effect (e.g. modify_dice_limit) reverts N rolls later. Ticking
    # before firing ``on_roll`` reverts the previous roll's bonus, then this
    # roll's bonus applies — so the delta is active for exactly one roll.
    from transversal.services.scheduled_events import advance_scheduled_events, commit_holds
    advance_scheduled_events(repo, "rolls", entity_id=entity_id)
    # The dice landing commits every in-flight manual activation for this entity:
    # from here on, what it changed is paid for for real (its holds dissolve).
    commit_holds(repo, entity_id=entity_id)

    sfx_ids, razmerit = _entity_sfx_context(repo, entity_id, universe)
    rolls = _rolls_as_dicts(roll_result)
    # Roll-bearing triggers carry the dice *and* the outcome the resolver already
    # computed. The trigger match reads it (`on_success` / `on_botch`), so a
    # condition on a matched SFX must be able to read it too — otherwise a
    # "roll tier" gate on those triggers silently reads nothing.
    roll_context: dict = {"rolls": rolls}
    tier = getattr(roll_result, "tier", None)
    if tier is not None:
        roll_context["tier"] = getattr(tier, "value", tier)
    # The margin lands here too, so the outcome triggers matched off this event
    # (`on_success` / `on_failure`) can gate on *how far* the roll got, not only
    # on the tier.
    roll_context["margin"] = getattr(roll_result, "margin", None)
    event = GameEvent(
        type="on_roll",
        entity_id=entity_id,
        universe=universe,
        roll_result=roll_result,
        # Roll-bearing triggers carry the dice in context (as ``on_result`` does),
        # so a TARGET_PATH condition can inspect *this* roll — e.g. "did it include
        # a d4 trait?" — instead of only the entity's sheet.
        context=roll_context,
    )
    outcome = engine.process_event_outcome(event, sfx_ids, razmerit, repo=repo)
    _emit_pending_choices(entity_id, universe, outcome.pending, outcome.structured, outcome.loops)
    # Fire roll-scoped deferred effects armed with ``on_roll`` timing, passing
    # the real rolled dice so per-die selection (die_filter / armed_sfx_ids) works.
    from transversal.services.roll_deferral import fire_armed
    fire_armed(entity_id, "on_roll", universe, roll_context)
    return outcome.applied


def fire_result_sfx(
    entity_id: str,
    universe: str,
    rolls: list[dict],
    effect_die: str | None = None,
    total: int | None = None,
    margin: int | None = None,
) -> list:
    """Fire automatic ``on_result`` SFX with the finalized roll state in context.

    ``rolls`` is the enriched pool dice (each carrying ``result``/``role``/
    ``tier``/``effect_die``/``ts_id``) so conditions and effects can inspect
    which dice were rolled and whether any were left unchosen (``role`` is
    None). ``effect_die``/``total`` are the committed scalars exposed as the
    trigger's ``{effect_die}``/``{total}`` variables.
    """
    from transversal.main import _get_engine, _get_repo
    from transversal.services.effects_engine import GameEvent

    repo = _get_repo()
    sfx_ids, razmerit = _entity_sfx_context(repo, entity_id, universe)
    event = GameEvent(
        type="on_result",
        entity_id=entity_id,
        universe=universe,
        context={
            "effect_die": effect_die,
            "total": total,
            "margin": margin,
            "rolls": rolls,
        },
    )
    outcome = _get_engine().process_event_outcome(event, sfx_ids, razmerit, repo=repo)
    _emit_pending_choices(entity_id, universe, outcome.pending, outcome.structured, outcome.loops)
    return outcome.applied
