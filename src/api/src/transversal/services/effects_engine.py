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


# ── Effect Application ───────────────────────────────

EffectApplier = Callable[[Effect, str, str, dict], None]
"""Signature: (action, entity_id, universe, context) -> None"""


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

            # Condition gate (only when a repo is available to evaluate state)
            if sfx.conditions and repo is not None:
                entity = repo.get_entity(event.entity_id)
                if entity is None or not evaluate_conditions(entity, sfx.conditions, repo, event.context):
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
            # Bind the declared source variable: if the SFX states a source kind
            # and the activation carries a ``source_id``, map it to the typed
            # ``{variable}`` so effect fields resolve to the concrete id.
            effect_context = event.context
            if sfx.source_kind and event.context.get("source_id"):
                from transversal.services.target_catalog import bind_source
                effect_context = bind_source(sfx.source_kind, event.context.get("source_id"), event.context)
            roll_effects = [e for e in sfx.effects if e.timing in _deferred_timings]
            log.info(
                "[process_event] sfx=%s trigger=%s deferred_effects=%s",
                sfx.id, sfx.trigger, [e.timing.value for e in roll_effects],
            )
            if roll_effects:
                # Arm the SFX's roll-timing effects as a unit for its duration.
                from transversal.services.roll_deferral import arm_sfx
                arm_sfx(
                    event.entity_id, roll_effects,
                    source_sfx_id=sfx.id,
                    source_kind=sfx.source_kind,
                    source_id=event.context.get("source_id") if event.context else None,
                    duration=sfx.duration,
                )
                sfx_applied = True

            for effect in sfx.effects:
                if effect.timing in _deferred_timings:
                    continue  # armed above (raw; substituted at fire time)

                effect = _substitute_effect_context(effect, effect_context)
                if effect.timing == EffectTiming.IMMEDIATE:
                    if effect.refs:
                        before = len(outcome.structured)
                        resolved = resolve_refs(effect, _fire_context(event, sfx, repo), outcome.structured)
                        if len(outcome.structured) == before:
                            _effects_applier.effect_registry.apply(resolved, event.entity_id, event.universe, effect_context)
                            outcome.applied.append(resolved)
                            sfx_applied = True
                            log.info("[process_event] applied sfx=%s effect=%s/%s via refs", sfx.id, resolved.type, resolved.action)
                    elif effect.target_spec is not None:
                        before = len(outcome.structured)
                        applied = _apply_immediate_spec(
                            effect, event, sfx, effect_context, repo, outcome.structured,
                        )
                        outcome.applied.extend(applied)
                        if applied:
                            sfx_applied = True
                    elif _effects_applier.find_choose_placeholder(effect):
                        outcome.pending.append(PendingSfxEffect(
                            effect=effect,
                            sfx_name=sfx.name,
                            sfx_description=sfx.description,
                        ))
                    else:
                        _effects_applier.effect_registry.apply(effect, event.entity_id, event.universe, effect_context)
                        outcome.applied.append(effect)
                        sfx_applied = True
                        log.info("[process_event] applied sfx=%s effect=%s/%s target=%s", sfx.id, effect.type, effect.action, effect.target)
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


def _substitute_effect_context(effect: Effect, context: dict) -> Effect:
    """Replace ``{context_key}`` placeholders across an effect's string fields.

    Covers ``result`` (the original behaviour), plus ``target``, ``entity``, and
    string ``context`` values so entity/string trigger variables can drive where
    an effect points, not just a numeric/string result.
    """
    if not context:
        return effect

    def _sub(s: Optional[str]) -> Optional[str]:
        if not s:
            return s
        out = s
        for key, value in context.items():
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


def _fire_context(event: GameEvent, sfx: SFX, repo, collections: dict | None = None):
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
    )


def _structured_choice(pc, effect: Effect, field: str, sfx: Optional[SFX] = None,
                       source_kind: str = "", source_id: str = "") -> StructuredChoice:
    """Serialize a resolver pending ``choose`` (``PendingTargetChoice``) into a
    ``StructuredChoice`` whose candidates are ready for the picker."""
    from transversal.services.target_resolver import serialize_candidates

    candidates = [
        {"id": c.id, "name": c.name, "subtitle": c.subtitle, "element": c.element}
        for c in serialize_candidates(pc.element, pc.candidates)
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
    )


def resolve_refs(effect: Effect, context, structured: Optional[list] = None,
                 answers: dict[int, list[str]] | None = None,
                 source_kind: str = "", source_id: str = "") -> Effect:
    """Resolve each named ref's spec to a single id (first value) and return it.

    A no-op when the effect has no refs or no ref carries a ``spec``. Literal /
    token refs (``self``, ``{choose_*}``, raw ids) pass through unchanged; the
    handler reads ``refs[name].value``. Fan-out (one ref → many targets) is
    handled separately in the Step-3 migration.

    When a ref's spec hits a ``choose`` step, the ref is left unresolved and a
    ``StructuredChoice`` is appended to ``structured`` (if provided). ``answers``
    resumes mid-path ``choose`` steps already answered by the user.
    """
    if not effect.refs:
        return effect
    from transversal.services.target_resolver import resolve

    refs = dict(effect.refs)
    for name, ref in refs.items():
        if ref.spec is None:
            continue
        resolution = resolve(ref.spec, context, answers=answers)
        if resolution.pending_choices and structured is not None:
            for pc in resolution.pending_choices:
                structured.append(_structured_choice(pc, effect, f"refs.{name}", source_kind=source_kind, source_id=source_id))
            continue
        if resolution.values:
            rid = _resolved_id(resolution.values[0])
            if rid is not None:
                refs[name] = ref.model_copy(update={"value": rid})
    return effect.model_copy(update={"refs": refs})


def _apply_immediate_spec(
    effect: Effect,
    event: GameEvent,
    sfx: SFX,
    context: dict | None,
    repo,
    structured: Optional[list] = None,
    answers: dict[int, list[str]] | None = None,
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
        TargetContext(subject=entity, repo=repo, source=source, source_element=source_element),
        answers=answers,
    )

    if resolution.pending_choices and structured is not None:
        for pc in resolution.pending_choices:
            structured.append(_structured_choice(
                pc, effect, "target", sfx,
                source_kind=sfx.source_kind or "", source_id=event.context.get("source_id") or "",
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
    ctx = TargetContext(subject=entity, repo=repo, source=source, source_element=source_element)

    if field.startswith("refs."):
        name = field[len("refs."):]
        refs = dict(effect.refs or {})
        ref = refs.get(name)
        if ref is None or ref.spec is None:
            return [], []
        resolution = resolve(ref.spec, ctx, answers=answers)
        if resolution.pending_choices:
            return [], [_structured_choice(pc, effect, f"refs.{name}", source_kind=source_kind, source_id=source_id) for pc in resolution.pending_choices]
        if resolution.values:
            rid = _resolved_id(resolution.values[0])
            if rid is not None:
                refs[name] = ref.model_copy(update={"value": rid, "spec": None})
                return [effect.model_copy(update={"refs": refs})], []
        return [], []

    spec = effect.target_spec if field == "target" else effect.entity_spec
    if spec is None:
        return [], []
    resolution = resolve(spec, ctx, answers=answers)
    if resolution.pending_choices:
        return [], [_structured_choice(pc, effect, field, source_kind=source_kind, source_id=source_id) for pc in resolution.pending_choices]

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

