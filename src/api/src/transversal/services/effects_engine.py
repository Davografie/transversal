"""Effects engine — SFX registry, trigger matching, and execution.

Handles the full lifecycle:
  1. Registry: load SFX definitions
  2. Trigger matching: event → available SFXs → match triggers
  3. Execution: dispatch via EffectRegistry, schedule deferred ones

Effects modify game state via the global effect_registry — any service
can register handlers for (type, action) pairs.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable, Optional

from transversal.domain import (
    DieType,
    DicePoolRequest,
    Effect,
    EffectTiming,
    RollResult,
    SFX,
)
import transversal.services.effects_applier as _effects_applier
from transversal.services.conditions import evaluate_conditions
from transversal.services.roll_deferral import DEFERRED_TIMINGS as _deferred_timings

log = logging.getLogger("transversal.sfx")


# ── Event Types ──────────────────────────────────────

@dataclass
class GameEvent:
    """An event that can trigger SFXs."""
    type: str  # on_roll, on_complication, on_botch, on_success, etc.
    entity_id: str
    universe: str
    context: dict = field(default_factory=dict)
    # Optional payload depending on event type
    dice_request: Optional[DicePoolRequest] = None
    roll_result: Optional[RollResult] = None


# ── Scheduled Effect ─────────────────────────────────


@dataclass
class PendingSfxEffect:
    """A pending ``{choose_*}`` effect plus its source SFX for display."""
    effect: Effect
    sfx_name: str
    sfx_description: str = ""
    # Immediate effects that come after this blocked effect; applied in order
    # once the choice resolves (sequential execution).
    continuation: list[Effect] = field(default_factory=list)


@dataclass
class StructuredChoice:
    """A structured ``choose`` step awaiting user resolution.

    ``element`` is the catalog element type; ``candidates`` are serialized
    display records (``id``/``name``/``subtitle``/``element``); ``count`` is how
    many to pick; ``field`` names where the result lands on the effect
    (``target`` | ``entity`` | ``refs.<name>``).
    """
    element: str
    candidates: list
    count: int
    field: str
    effect: Effect
    sfx_name: str = ""
    sfx_description: str = ""
    step_index: int = 0
    source_kind: str = ""
    source_id: str = ""
    source_sfx_id: str = ""
    answers_so_far: list = field(default_factory=list)
    # Immediate effects that come after this blocked effect; applied in order
    # once the choice resolves (sequential execution).
    continuation: list[Effect] = field(default_factory=list)


@dataclass
class EventOutcome:
    """Result of processing an event through the effects engine.

    ``applied`` are immediately-applied effects. ``pending`` are immediate
    effects with a ``{choose_*}`` target that were skipped and need user
    resolution before they can be applied. ``structured`` are effects whose
    ``target_spec``/``refs`` hit a ``choose`` step and carry the pre-resolved
    candidate set for the picker.
    """
    applied: list[Effect] = field(default_factory=list)
    pending: list[PendingSfxEffect] = field(default_factory=list)
    structured: list[StructuredChoice] = field(default_factory=list)


# ── Wire serialization ───────────────────────────────

_EFFECT_CAMEL_FIELDS = {
    "target_scope": "targetScope",
    "entity_scope": "entityScope",
    "target_filter": "targetFilter",
    "die_filter": "dieFilter",
    "target_spec": "targetSpec",
    "entity_spec": "entitySpec",
}


def effect_to_wire_dict(e: Effect) -> dict:
    """Serialize an ``Effect`` to the camelCase JSON dict the GraphQL
    ``EffectInput`` expects on the wire.

    Strawberry auto-camel-cases field names (``target_spec`` → ``targetSpec``)
    and exposes str-Enums by member *name* (``IMMEDIATE``, ``FIRST_TO_FIRE``,
    ``TARGET_PATH``), but ``model_dump()`` yields snake_case and enum *values*
    (``immediate``, ``first_to_fire``, ``target_path``). Round-tripping a
    ``model_dump()`` dict back through ``EffectInput`` therefore fails
    validation (unknown snake_case fields, unknown enum values), silently
    dropping the spec/ref a staged ``choose`` needs to resume. Normalize both
    here so a structured choice's effect survives the round-trip.
    """
    d = e.model_dump()
    for snake, camel in _EFFECT_CAMEL_FIELDS.items():
        if snake in d:
            d[camel] = d.pop(snake)
    if e.timing is not None:
        d["timing"] = e.timing.name
    if e.duration is not None:
        d["duration"]["combine"] = e.duration.combine.name
    if e.conditions:
        for i, cond in enumerate(e.conditions):
            d["conditions"][i]["type"] = cond.type.name
    return d


# ── Effect Application ───────────────────────────────

EffectApplier = Callable[[Effect, str, str, dict], None]
"""Signature: (action, entity_id, universe, context) -> None"""


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


class EffectsEngine:
    """Manages SFX triggers, execution, and scheduling.

    Effects are dispatched through the global effect_registry —
    any module can register handlers for (type, action) pairs.
    The engine does not directly mutate state.
    """

    def __init__(self):
        self._sfx_registry: dict[str, SFX] = {}

    # ── Registry ─────────────────────────────────────

    def register(self, sfx: SFX) -> None:
        """Register an SFX definition."""
        self._sfx_registry[sfx.id] = sfx

    def register_many(self, sfxs: list[SFX]) -> None:
        for s in sfxs:
            self.register(s)

    def get(self, sfx_id: str) -> Optional[SFX]:
        return self._sfx_registry.get(sfx_id)

    def get_all(self) -> list[SFX]:
        return list(self._sfx_registry.values())

    # ── Trigger ──────────────────────────────────────

    def process_event(
        self,
        event: GameEvent,
        available_sfx_ids: list[str],
        razmerit_balance: int,
    ) -> list[Effect]:
        """Process a game event, returning immediately-applied effects.

        Backward-compatible wrapper around :meth:`process_event_outcome`.
        """
        return self.process_event_outcome(event, available_sfx_ids, razmerit_balance).applied

    def process_event_outcome(
        self,
        event: GameEvent,
        available_sfx_ids: list[str],
        razmerit_balance: int,
        repo=None,
    ) -> EventOutcome:
        """Process a game event, returning applied + pending effects.

        Immediate effects with a ``{choose_*}`` target are not applied — they
        are returned in ``outcome.pending`` so the caller can surface a choice.
        Deferred effects are queued internally as before.

        When ``repo`` is provided, SFX with ``conditions`` are gated on the
        entity's current state (evaluate_conditions).
        """
        outcome = EventOutcome()

        for sfx_id in available_sfx_ids:
            sfx = self._sfx_registry.get(sfx_id)
            if sfx is None:
                log.info("[process_event] sfx=%s NOT in registry (skip)", sfx_id)
                continue

            # Trigger match
            if not self._trigger_matches(sfx, event):
                continue

            log.info(
                "[process_event] sfx=%s trigger=%s matches event=%s conditions=%s",
                sfx.id, sfx.trigger, event.type,
                [(c.type.value, c.target) for c in (sfx.conditions or [])],
            )

            # Resolve the activation source once: explicit source_id wins (manual
            # activation); else ownership resolution (automatic triggers).
            source, source_element, source_id = _resolve_activation_source(sfx, event, repo)

            # Condition gate (only when a repo is available to evaluate state)
            if sfx.conditions and repo is not None:
                entity = repo.get_entity(event.entity_id)
                if entity is None or not evaluate_conditions(entity, sfx.conditions, repo, event.context, source=source, source_element=source_element):
                    continue

            # Cost check: sum razmerit costs from spend effects
            total_razmerit_cost = 0
            for e in sfx.effects:
                if e.type == "transfer_razmerit" and e.action == "spend":
                    total_razmerit_cost += int(e.result or "0")
            if total_razmerit_cost > razmerit_balance:
                continue

            # Execute each effect with its own timing
            sfx_applied = False
            # Per-activation output bindings (effect outputs -> later effects).
            bindings: dict = {}
            # Bind the declared source variable: if the SFX states a source kind
            # and the activation resolved a source, map it to the typed
            # ``{variable}`` so effect fields resolve to the concrete id.
            effect_context = event.context
            if sfx.source_kind and source_id:
                from transversal.services.target_catalog import bind_source
                effect_context = bind_source(sfx.source_kind, source_id, event.context)
            # Thread the resolved activation source into the effect context so
            # per-effect ``source_rating`` / ``target_path`` conditions can gate
            # on the trait (etc.) that owns/triggered this SFX.
            if source is not None:
                effect_context = {
                    **(effect_context or {}),
                    _effects_applier.SOURCE_CONTEXT_KEY: source,
                    _effects_applier.SOURCE_ELEMENT_CONTEXT_KEY: source_element,
                }
            roll_effects = [e for e in sfx.effects if e.timing in _deferred_timings]
            log.info(
                "[process_event] sfx=%s trigger=%s deferred_effects=%s",
                sfx.id, sfx.trigger, [e.timing.value for e in roll_effects],
            )
            if roll_effects:
                # Arm the SFX's roll-timing effects as a unit for its duration,
                # routed by the SFX's declared (or trigger-derived) listener scope.
                from transversal.services.roll_deferral import arm_passive, arm_sfx
                scope = sfx.effective_arming_scope
                if scope == "global":
                    arm_passive(
                        roll_effects,
                        source_sfx_id=sfx.id,
                        source_kind=sfx.source_kind,
                        source_id=source_id,
                        duration=sfx.duration,
                    )
                else:
                    # ``listener_spec`` fan-out to a resolved entity set is not yet
                    # implemented (open decision D3, no current consumer) — fall back
                    # to the triggering entity and surface it.
                    if scope == "listener_spec":
                        log.warning(
                            "[process_event] sfx=%s scope=listener_spec not implemented; arming on self",
                            sfx.id,
                        )
                    arm_sfx(
                        event.entity_id, roll_effects,
                        source_sfx_id=sfx.id,
                        source_kind=sfx.source_kind,
                        source_id=source_id,
                        duration=sfx.duration,
                        scope="self",
                    )
                sfx_applied = True

            for idx, effect in enumerate(sfx.effects):
                if effect.timing in _deferred_timings:
                    continue  # armed above (raw; substituted at fire time)

                effect = _substitute_effect_context(effect, effect_context, bindings)
                if effect.timing == EffectTiming.IMMEDIATE:
                    blocked = False
                    if effect.refs:
                        before = len(outcome.structured)
                        resolved_list = resolve_refs(effect, _fire_context(event, sfx, repo, bindings=bindings), outcome.structured, source_sfx_id=sfx.id)
                        if len(outcome.structured) > before:
                            blocked = True
                        else:
                            for resolved in resolved_list:
                                _effects_applier.effect_registry.apply(resolved, event.entity_id, event.universe, effect_context)
                                outcome.applied.append(resolved)
                                sfx_applied = True
                                log.info("[process_event] applied sfx=%s effect=%s/%s via refs", sfx.id, resolved.type, resolved.action)
                    elif effect.target_spec is not None:
                        before = len(outcome.structured)
                        applied = _apply_immediate_spec(
                            effect, event, sfx, effect_context, repo, outcome.structured, bindings=bindings,
                        )
                        outcome.applied.extend(applied)
                        if applied:
                            sfx_applied = True
                        if len(outcome.structured) > before:
                            blocked = True
                    elif _effects_applier.find_choose_placeholder(effect):
                        outcome.pending.append(PendingSfxEffect(
                            effect=effect,
                            sfx_name=sfx.name,
                            sfx_description=sfx.description,
                        ))
                        blocked = True
                    else:
                        _effects_applier.effect_registry.apply(effect, event.entity_id, event.universe, effect_context)
                        outcome.applied.append(effect)
                        sfx_applied = True
                        log.info("[process_event] applied sfx=%s effect=%s/%s target=%s", sfx.id, effect.type, effect.action, effect.target)

                    if blocked:
                        # Sequential execution: this effect needs a choice, so the
                        # remaining immediate effects must wait for resolution.
                        continuation = [e for e in sfx.effects[idx + 1:] if e.timing == EffectTiming.IMMEDIATE]
                        _attach_continuation(outcome, continuation)
                        break
                else:
                    # Persist deferred effects in the central timer store.
                    if repo is not None:
                        from transversal.services.scheduled_events import schedule_deferred
                        schedule_deferred(repo, "entity", event.entity_id, effect, source_sfx_id=sfx.id)

            if sfx_applied:
                _emit_sfx_triggered(event.entity_id, sfx)

        return outcome

    def _trigger_matches(self, sfx: SFX, event: GameEvent) -> bool:
        """Check if an SFX's trigger matches the event.

        Supports:
          - Direct match: trigger == event.type
          - on_complication: fires when roll_result has hitches
          - on_botch: fires when all dice show 1
          - on_location_change: fires for event type "location_changed"
          - on_trait_change: fires for event type "trait_updated"
          - on_contest_loss / on_contest_win: fires from contest context
          - on_success / on_failure: fires from roll context
        """
        trigger = sfx.trigger

        # Direct match
        if trigger == event.type:
            return True

        # on_activate legacy alias for "manual" trigger
        if trigger == "on_activate" and event.type == "manual":
            return True

        # on_complication also fires for hitches within other events
        if trigger == "on_complication" and event.type in ("on_roll", "on_result"):
            if event.roll_result:
                if hasattr(event.roll_result, 'hitches') and event.roll_result.hitches:
                    return True

        # on_botch
        if trigger == "on_botch" and event.roll_result and getattr(event.roll_result, 'botch', False):
            return True

        # on_location_change
        if trigger == "on_location_change" and event.type == "location_changed":
            return True

        # on_trait_change
        if trigger == "on_trait_change" and event.type == "trait_updated":
            return True

        # on_trait_learn
        if trigger == "on_trait_learn" and event.type == "trait_learned":
            return True

        # on_trait_offered
        if trigger == "on_trait_offered" and event.type == "trait_offered":
            return True

        # on_relationship_create
        if trigger == "on_relationship_create" and event.type == "relationship_created":
            return True

        # on_character_create
        if trigger == "on_character_create" and event.type == "character_created":
            return True

        # on_projection_create
        if trigger == "on_projection_create" and event.type == "projection_created":
            return True

        # on_challenge_completed
        if trigger == "on_challenge_completed" and event.type == "challenge_completed":
            return True

        # on_contest_loss / on_contest_win (from context)
        if trigger in ("on_contest_loss", "on_contest_win"):
            contest_winner = event.context.get("contest_winner")
            if trigger == "on_contest_loss":
                # Entity lost: opponent won (ties favor the initiator)
                return contest_winner == "opponent"
            elif trigger == "on_contest_win":
                return contest_winner == "player"

        # on_success / on_failure (from roll context)
        if trigger in ("on_success", "on_failure") and event.roll_result:
            tier = getattr(event.roll_result, 'tier', None)
            if tier:
                from transversal.domain import OutcomeTier
                if trigger == "on_success" and tier != OutcomeTier.FAIL:
                    return True
                if trigger == "on_failure" and tier == OutcomeTier.FAIL:
                    return True

        return False

    # ── Scheduling is centralized in `services/scheduled_events.py` ──


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


def _substitute_effect_context(effect: Effect, context: dict, bindings: dict | None = None) -> Effect:
    """Replace ``{context_key}`` placeholders across an effect's string fields.

    Covers ``result`` (the original behaviour), plus ``target``, ``entity``, and
    string ``context`` values so entity/string trigger variables can drive where
    an effect points, not just a numeric/string result. ``bindings`` (per-
    activation output variables) override the event context on name collision.
    """
    source: dict = {}
    if context:
        source.update(context)
    if bindings:
        # Only scalar ("one") bindings substitute into string fields; a "many"
        # binding must be re-used via `select variable` (never stringified).
        source.update({
            name: b.value
            for name, b in bindings.items()
            if getattr(b, "cardinality", "one") != "many"
        })
    if not source:
        return effect

    def _sub(s: Optional[str]) -> Optional[str]:
        if not s:
            return s
        out = s
        for key, value in source.items():
            placeholder = "{" + key + "}"
            if placeholder in out:
                out = out.replace(placeholder, str(value) if value is not None else "")
        return out

    updates: dict = {}
    for field in ("result", "target", "entity", "target_scope", "entity_scope"):
        old = getattr(effect, field)
        new = _sub(old)
        if new != old:
            updates[field] = new

    if effect.refs:
        new_refs = {}
        refs_changed = False
        for name, ref in effect.refs.items():
            nv = _sub(ref.value)
            if nv != ref.value:
                new_refs[name] = ref.model_copy(update={"value": nv})
                refs_changed = True
            else:
                new_refs[name] = ref
        if refs_changed:
            updates["refs"] = new_refs

    new_context = {}
    context_changed = False
    for k, v in (effect.context or {}).items():
        if isinstance(v, str):
            nv = _sub(v)
            if nv != v:
                context_changed = True
                new_context[k] = nv
            else:
                new_context[k] = v
        else:
            new_context[k] = v
    if context_changed:
        updates["context"] = new_context

    if not updates:
        return effect
    return effect.model_copy(update=updates)


def _resolved_id(value) -> str | None:
    """Extract a target id from a resolved spec value (object or dict)."""
    if isinstance(value, dict):
        return value.get("ts_id") or value.get("id")
    return getattr(value, "ts_id", None) or getattr(value, "id", None)


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


def _structured_choice(pc, effect: Effect, field: str, sfx: Optional[SFX] = None,
                       source_kind: str = "", source_id: str = "",
                       source_sfx_id: str = "",
                       answers_so_far: list | None = None,
                       repo=None) -> StructuredChoice:
    """Serialize a resolver pending ``choose`` (``PendingTargetChoice``) into a
    ``StructuredChoice`` whose candidates are ready for the picker."""
    from transversal.services.target_resolver import serialize_candidates

    candidates = [
        {"id": c.id, "name": c.name, "subtitle": c.subtitle, "rating": c.rating, "element": c.element}
        for c in serialize_candidates(pc.element, pc.candidates, repo=repo)
    ]
    return StructuredChoice(
        element=pc.element,
        candidates=candidates,
        count=pc.count,
        field=field,
        effect=effect,
        sfx_name=sfx.name if sfx else "",
        sfx_description=sfx.description if sfx else "",
        step_index=pc.step_index,
        source_kind=source_kind,
        source_id=source_id,
        source_sfx_id=source_sfx_id,
        answers_so_far=list(answers_so_far or []),
    )


def resolve_refs(effect: Effect, context, structured: Optional[list] = None,
                 answers: dict[int, list[str]] | None = None,
                 source_kind: str = "", source_id: str = "",
                 source_sfx_id: str = "") -> list[Effect]:
    """Resolve each named ref and fan the effect out over multi-value refs.

    Returns the concrete effects to apply — one per combination of resolved ref
    values (the cartesian product across refs). A ref whose ``spec`` resolves to
    ``N`` values fans the effect out ``N`` ways; literal / token refs (``self``,
    ``{choose_*}``, raw ids) contribute one fixed value and do not fan out. If
    any ref resolves to zero values, nothing matches and an empty list is
    returned. An effect with no refs returns ``[effect]`` unchanged.

    When a ref's spec hits a ``choose`` step, the ref is left unresolved, a
    ``StructuredChoice`` is appended to ``structured`` (if provided), and an
    empty list is returned. ``answers`` resumes mid-path ``choose`` steps already
    answered by the user.
    """
    if not effect.refs:
        return [effect]
    from itertools import product
    from transversal.services.target_resolver import resolve

    answers_so_far = [{"stepIndex": k, "ids": list(v)} for k, v in sorted((answers or {}).items())]

    resolved_values: dict[str, list[str]] = {}
    for name, ref in effect.refs.items():
        if ref.spec is None:
            resolved_values[name] = [ref.value]
            continue
        resolution = resolve(ref.spec, context, answers=answers)
        if resolution.pending_choices:
            if structured is not None:
                for pc in resolution.pending_choices:
                    structured.append(_structured_choice(
                        pc, effect, f"refs.{name}",
                        source_kind=source_kind, source_id=source_id,
                        source_sfx_id=source_sfx_id, answers_so_far=answers_so_far,
                        repo=getattr(context, "repo", None),
                    ))
            return []
        ids = []
        for value in resolution.values:
            rid = _resolved_id(value)
            if rid is not None:
                ids.append(rid)
        resolved_values[name] = ids

    names = list(effect.refs.keys())
    out: list[Effect] = []
    for combo in product(*(resolved_values[n] for n in names)):
        refs = {}
        for name, value in zip(names, combo):
            ref = effect.refs[name]
            refs[name] = (
                ref if ref.spec is None
                else ref.model_copy(update={"value": value, "spec": None})
            )
        out.append(effect.model_copy(update={"refs": refs}))
    return out


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


def resolve_effect_spec_choices(
    effect: Effect,
    field: str,
    answers: dict[int, list[str]],
    entity,
    repo,
    source_kind: str = "",
    source_id: str = "",
    source_sfx_id: str = "",
    bindings: dict | None = None,
) -> tuple[list[Effect], list[StructuredChoice]]:
    """Re-resolve an effect's spec/ref with partial ``choose`` answers.

    Returns ``(resolved_effects, pending)``. ``resolved_effects`` are concrete
    effects with the spec/ref resolved (ready to commit); ``pending`` carries the
    next ``choose`` step(s) as structured choices when the path is not yet fully
    answered. Used by the resume mutation after the user answers a mid-path
    ``choose``.
    """
    from transversal.services.target_resolver import TargetContext, resolve, resolve_source

    source, source_element = (
        resolve_source(source_kind, source_id, repo)
        if source_kind and source_id and repo is not None
        else (None, None)
    )
    ctx = TargetContext(subject=entity, repo=repo, source=source, source_element=source_element, bindings=bindings if bindings is not None else {})
    answers_so_far = [{"stepIndex": k, "ids": list(v)} for k, v in sorted((answers or {}).items())]

    if field.startswith("refs."):
        structured_choices: list = []
        resolved_list = resolve_refs(
            effect, ctx, structured=structured_choices, answers=answers,
            source_kind=source_kind, source_id=source_id, source_sfx_id=source_sfx_id,
        )
        if structured_choices:
            return [], structured_choices
        # ``resolve_refs`` already cleared the resolved specs and set the
        # concrete values, fanning out one effect per value combination.
        return resolved_list, []

    spec = effect.target_spec if field == "target" else effect.entity_spec
    if spec is None:
        return [], []
    resolution = resolve(spec, ctx, answers=answers)
    if resolution.pending_choices:
        return [], [_structured_choice(pc, effect, field, source_kind=source_kind, source_id=source_id, source_sfx_id=source_sfx_id, answers_so_far=answers_so_far, repo=repo) for pc in resolution.pending_choices]

    out: list[Effect] = []
    for value in resolution.values:
        rid = _resolved_id(value)
        if rid is None:
            continue
        if field == "target":
            out.append(effect.model_copy(update={"target": rid, "target_spec": None}))
        else:
            out.append(effect.model_copy(update={"entity": rid, "entity_spec": None}))
    return out, []

