"""Firing — split out of src/api/src/transversal/services/effects_engine.py."""

from __future__ import annotations

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

def _emit_sfx_ended(entity_id: str, sfx_id: str) -> None:
    """Broadcast an ``sfx_ended`` SSE event: the rule was taken back — or its cost
    left the pool before it committed, and the rule went with it."""
    from transversal.api.sse.bus import StreamEvent, event_bus
    from transversal.services.session_manager import session_manager

    name = ""
    try:  # the toast reads better with the rule's name; the id is the fallback
        from transversal.main import _get_engine

        sfx = _get_engine().get(sfx_id)
        name = getattr(sfx, "name", "") or ""
    except Exception:  # noqa: BLE001 — never let a toast break the ending
        pass

    for s in session_manager.list_active():
        event_bus.publish(StreamEvent(
            event="sfx_ended",
            session_id=s.id,
            data={"entity_id": entity_id, "sfx_id": sfx_id, "sfx_name": name},
        ))


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


def _emit_sfx_armed(sfx) -> None:
    """Broadcast an ``sfx_armed`` SSE event for a passive armed for the session.

    A rule whose effects are all roll/outcome-timed never "fires" at the moment
    it is armed, so without this the table is told nothing and the rule is
    silently on — the author's One Trick. ``scope="global"`` because a
    session-armed passive covers every entity, late joiners included, so there is
    no single entity to address; ``entity_id`` stays empty for the same reason.
    """
    from transversal.api.sse.bus import StreamEvent, event_bus
    from transversal.services.session_manager import session_manager

    for s in session_manager.list_active():
        event_bus.publish(StreamEvent(
            event="sfx_armed",
            session_id=s.id,
            data={
                "entity_id": "",
                "sfx_id": sfx.id,
                "sfx_name": sfx.name,
                "scope": "global",
            },
        ))

def _fire_context(event: GameEvent, sfx: SFX, repo, collections: dict | None = None,
                  bindings: dict | None = None, source_id: str | None = None,
                  source_element: str | None = None):
    """Build the resolver context for a fire-time effect (spec + refs paths share it).

    ``source_id``/``source_element`` are the *resolved* activation source when the
    caller has it (the engine resolves it before dispatching); without them the raw
    id from the event context is used. `added_dice` is narrowed by them — the seed
    is read from the rule's own point of view.
    """
    from transversal.services.target_resolver import TargetContext, event_collections, resolve_source

    entity = repo.get_entity(event.entity_id) if repo is not None else None
    raw_source_id = source_id or (event.context.get("source_id") if event.context else None)
    source, resolved_element = (
        resolve_source(sfx.source_kind or "", raw_source_id, repo)
        if sfx.source_kind and raw_source_id and repo is not None
        else None
    ) or (None, None)
    source_element = source_element or resolved_element
    # Event-carried dice are seeds wherever the context travels, so an immediate
    # effect can read the same collections a condition can; an explicit
    # ``collections`` argument still wins (the per-die deferred path builds it).
    seeds = event_collections(event.context, raw_source_id, source_element)
    seeds.update(collections or {})
    return TargetContext(
        subject=entity, repo=repo, collections=seeds,
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
    source_id: str | None = None,
    source_element: str | None = None,
) -> list[Effect]:
    """Resolve an immediate effect's ``target_spec`` and apply once per target.

    The immediate counterpart of ``roll_deferral._apply_spec_target``: resolve
    the spec (with the SFX's activation source for ``select source``) and fan
    out one concrete effect per resolved target. Returns the applied effects.

    ``source_id``/``source_element`` are the *resolved* activation source when the
    caller has it, and they must be threaded in. An automatic trigger carries no
    ``source_id`` in the event, so re-deriving the source from the context alone
    left ``select source`` with nothing: the step reported *requires a declared
    source_kind*, the spec resolved to zero values, and the effect was dropped
    while the rule still logged a match. :func:`_fire_context` takes the same
    pair for the reference path.

    When the spec hits a ``choose`` step, nothing is applied and a
    ``StructuredChoice`` is appended to ``structured`` (if provided).
    """
    from transversal.main import _get_repo
    from transversal.services.target_resolver import TargetContext, resolve, resolve_source

    repo = repo if repo is not None else _get_repo()
    entity = repo.get_entity(event.entity_id) if repo is not None else None

    raw_source_id = source_id or (event.context.get("source_id") if event.context else None)
    resolved = (
        resolve_source(sfx.source_kind or "", raw_source_id, repo)
        if sfx.source_kind and raw_source_id and repo is not None
        else None
    )
    source, resolved_element = resolved or (None, None)
    source_element = source_element or resolved_element
    # Event-carried dice seed this path too: an effect's own target/entity spec
    # must be able to start from the same collections a condition can
    # (`rolled_dice` / `added_dice` / `opposing_dice`). `_fire_context` does this
    # for the deferred and ref paths; this one built its context without them, so
    # an immediate effect seeded from a collection silently resolved to nobody.
    from transversal.services.target_resolver import event_collections

    resolution = resolve(
        effect.target_spec,
        TargetContext(subject=entity, repo=repo,
                      collections=event_collections(
                          event.context, raw_source_id, source_element),
                      source=source, source_element=source_element, bindings=bindings if bindings is not None else {}),
        answers=answers,
    )

    if resolution.pending_choices and structured is not None:
        for pc in resolution.pending_choices:
            structured.append(_structured_choice(
                pc, effect, "target", sfx,
                source_kind=sfx.source_kind or "", source_id=raw_source_id or "",
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
