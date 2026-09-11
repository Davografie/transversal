"""Firing — split out of src/api/src/transversal/services/effects_engine.py."""

import transversal.services.effects_applier as _effects_applier

from transversal.domain import Effect
from transversal.domain import SFX
from typing import Callable
from typing import Optional
from transversal.services.effects_engine.events import (
    EventOutcome,
    GameEvent,
)
from transversal.services.effects_engine.refs import (
    _resolved_id,
    _structured_choice,
)
from transversal.services.effects_engine.shared import (
    log,
)


EffectApplier = Callable[[Effect, str, str, dict], None]

def _resolve_activation_source(sfx: SFX, event: GameEvent, repo):
    """Resolve the SFX's activation source as ``(object, element, source_id)``.

    An explicit ``source_id`` in the event context wins (manual activation — the
    client says which instance was clicked); the raw id is always preserved so
    ``{variable}`` binding works even without a repo. For automatic triggers
    (``on_roll`` etc.) with no explicit id, fall back to ownership resolution:
    the source is the trait/trait-set setting that grants this SFX to the entity.
    """
    raw_source_id = (event.context or {}).get("source_id") if event.context else None
    source_id = raw_source_id
    if sfx.source_kind and raw_source_id and repo is not None:
        from transversal.services.target_resolver import resolve_source
        resolved = resolve_source(sfx.source_kind, raw_source_id, repo)
        if resolved:
            return resolved[0], resolved[1], raw_source_id
    if sfx.source_kind and repo is not None:
        from transversal.services.sfx_owner import resolve_sfx_source
        resolved = resolve_sfx_source(repo, event.entity_id, event.universe, sfx.id, sfx.source_kind)
        if resolved:
            source, element = resolved
            return source, element, getattr(source, "id", None)
    return None, None, source_id

def _attach_continuation(outcome: EventOutcome, continuation: list[Effect]) -> None:
    """Attach the deferred (post-choice) effects to the last pending choice."""
    if not continuation:
        return
    if outcome.structured:
        outcome.structured[-1].continuation = continuation
    elif outcome.pending:
        outcome.pending[-1].continuation = continuation

def _emit_sfx_triggered(entity_id: str, sfx) -> None:
    """Broadcast an ``sfx_triggered`` SSE event so clients can toast it."""
    from transversal.api.sse.bus import StreamEvent, event_bus
    from transversal.services.session_manager import session_manager

    for s in session_manager.list_active():
        event_bus.publish(StreamEvent(
            event="sfx_triggered",
            session_id=s.id,
            data={
                "entity_id": entity_id,
                "sfx_id": sfx.id,
                "sfx_name": sfx.name,
            },
        ))

def _fire_context(event: GameEvent, sfx: SFX, repo, collections: dict | None = None, bindings: dict | None = None):
    """Build the resolver context for a fire-time effect (spec + refs paths share it)."""
    from transversal.services.target_resolver import TargetContext, resolve_source

    entity = repo.get_entity(event.entity_id) if repo is not None else None
    source_id = event.context.get("source_id") if event.context else None
    source, source_element = (
        resolve_source(sfx.source_kind or "", source_id, repo)
        if sfx.source_kind and source_id and repo is not None
        else (None, None)
    )
    return TargetContext(
        subject=entity, repo=repo, collections=collections or {},
        source=source, source_element=source_element,
        bindings=bindings if bindings is not None else {},
    )

def _resolve_primary_targets(effect: Effect, context, structured, sfx: SFX,
                             source_id: str = "") -> tuple[list[str], bool]:
    """Resolve an effect's ``target_spec`` to concrete ids (immediate path).

    Returns ``(ids, blocked)``. ``blocked`` is True when the spec stopped at a
    ``choose`` step — the choice is appended to ``structured`` for the caller to
    resume from — and ``ids`` is empty. Resolving here (rather than inside
    :func:`resolve_refs`) is what lets an effect carry *both* a target path and
    named references: the resolution binds the path's named outputs into
    ``context.bindings`` in place, so a reference path can start from them.
    """
    from transversal.services.target_resolver import resolve

    resolution = resolve(effect.target_spec, context)
    if resolution.pending_choices:
        if structured is not None:
            for pc in resolution.pending_choices:
                structured.append(_structured_choice(
                    pc, effect, "target", sfx,
                    source_kind=sfx.source_kind or "", source_id=source_id,
                    source_sfx_id=sfx.id, repo=getattr(context, "repo", None),
                ))
        return [], True
    return [rid for value in resolution.values if (rid := _resolved_id(value))], False

def _apply_immediate_spec(
    effect: Effect,
    event: GameEvent,
    sfx: SFX,
    context: dict | None,
    repo,
    structured: Optional[list] = None,
    answers: dict[int, list[str]] | None = None,
    bindings: dict | None = None,
) -> list[Effect]:
    """Resolve an immediate effect's ``target_spec`` and apply once per target.

    The immediate counterpart of ``roll_deferral._apply_spec_target``: resolve
    the spec (with the SFX's activation source for ``select source``) and fan
    out one concrete effect per resolved target. Returns the applied effects.

    When the spec hits a ``choose`` step, nothing is applied and a
    ``StructuredChoice`` is appended to ``structured`` (if provided).
    """
    from transversal.main import _get_repo
    from transversal.services.target_resolver import TargetContext, resolve, resolve_source

    repo = repo if repo is not None else _get_repo()
    entity = repo.get_entity(event.entity_id) if repo is not None else None

    source, source_element = (
        resolve_source(sfx.source_kind or "", event.context.get("source_id"), repo)
        if sfx.source_kind and event.context.get("source_id") and repo is not None
        else (None, None)
    )
    resolution = resolve(
        effect.target_spec,
        TargetContext(subject=entity, repo=repo, source=source, source_element=source_element, bindings=bindings if bindings is not None else {}),
        answers=answers,
    )

    if resolution.pending_choices and structured is not None:
        for pc in resolution.pending_choices:
            structured.append(_structured_choice(
                pc, effect, "target", sfx,
                source_kind=sfx.source_kind or "", source_id=event.context.get("source_id") or "",
                source_sfx_id=sfx.id,
                repo=repo,
            ))
        return []

    applied: list[Effect] = []
    for value in resolution.values:
        target_id = _resolved_id(value)
        if target_id is None:
            continue
        resolved = effect.model_copy(update={"target": target_id, "target_spec": None})
        _effects_applier.effect_registry.apply(resolved, event.entity_id, event.universe, context or {})
        applied.append(resolved)
        log.info("[process_event] applied sfx=%s effect=%s/%s target=%s (spec)", sfx.id, resolved.type, resolved.action, resolved.target)
    return applied

def _noop_applier(action: Effect, entity_id: str, universe: str, context: dict) -> None:
    """Default no-op applier for testing."""
    pass
