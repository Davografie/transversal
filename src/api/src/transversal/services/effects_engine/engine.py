"""Engine — split out of src/api/src/transversal/services/effects_engine.py."""

from __future__ import annotations

import transversal.services.effects_applier as _effects_applier

from transversal.domain import Effect
from transversal.domain import EffectTiming
from transversal.domain import SFX
from transversal.services.conditions import evaluate_conditions
from transversal.services.roll_deferral import DEFERRED_TIMINGS as _deferred_timings
from typing import Optional
from transversal.services.effects_engine.events import (
    EventOutcome,
    GameEvent,
    PendingSfxEffect,
)
from transversal.services.effects_engine.firing import (
    _apply_immediate_spec,
    _attach_continuation,
    _fire_context,
    _resolve_activation_source,
    _resolve_primary_targets,
)
from transversal.services.effects_engine.refs import (
    _substitute_effect_context,
    resolve_refs,
)
from transversal.services.effects_engine.shared import (
    log,
)


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
        arm_deferred: bool = True,
    ) -> EventOutcome:
        """Process a game event, returning applied + pending effects.

        Immediate effects with a ``{choose_*}`` target are not applied — they
        are returned in ``outcome.pending`` so the caller can surface a choice.
        Deferred effects are queued internally as before.

        When ``repo`` is provided, SFX with ``conditions`` are gated on the
        entity's current state (evaluate_conditions).

        ``arm_deferred=False`` skips queueing this SFX's deferred (roll/outcome
        -timing) effects; the caller owns arming. The session-start fan-out uses
        it so the per-entity walk applies only non-deferred effects while a
        single global pass arms the passives once (``arm_passive`` appends, so
        arming inside the walk would stack N copies of the same rule).
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

            # Per-activation variable scope. Sealed *before* the gate because a
            # condition's targeting path can publish named outputs into it ("the
            # d4 traits in this roll"), which the SFX's effects may then target.
            # Effect outputs extend the same scope, so later effects see them.
            bindings: dict = {}

            # Condition gate (only when a repo is available to evaluate state)
            if sfx.conditions and repo is not None:
                entity = repo.get_entity(event.entity_id)
                if entity is None or not evaluate_conditions(
                    entity, sfx.conditions, repo, event.context,
                    source=source, source_element=source_element,
                    out_bindings=bindings,
                ):
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
            # Carry the activation's variable scope to the applier, so an effect's
            # ``entity_spec`` can resolve ``select variable`` against what the SFX's
            # conditions (and any earlier effect) bound.
            effect_context = {
                **(effect_context or {}),
                _effects_applier.BINDINGS_CONTEXT_KEY: bindings,
            }
            roll_effects = [e for e in sfx.effects if e.timing in _deferred_timings]
            log.info(
                "[process_event] sfx=%s trigger=%s deferred_effects=%s arm_deferred=%s",
                sfx.id, sfx.trigger, [e.timing.value for e in roll_effects], arm_deferred,
            )
            if roll_effects and arm_deferred:
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
                # Resolve any authored ``entity_spec`` against this activation's
                # variable scope before dispatch, so every handler — the razmerit
                # service included — receives a concrete entity id rather than a
                # spec it would silently ignore.
                effect = _effects_applier.resolve_effect_entity(
                    effect, event.entity_id, repo, effect_context,
                )
                if effect.timing == EffectTiming.IMMEDIATE:
                    blocked = False
                    if effect.refs:
                        before = len(outcome.structured)
                        fire_ctx = _fire_context(event, sfx, repo, bindings=bindings)
                        # An effect may carry both a primary target path and named
                        # references — "attune *these people* to *their projection*".
                        # Walk the target path first: its named outputs join the
                        # activation scope in place, so a reference path can start
                        # (`select variable`) from where the target path landed.
                        targets: list[Optional[str]] = [None]
                        if effect.target_spec is not None and effect.target_spec.steps:
                            targets, target_blocked = _resolve_primary_targets(
                                effect, fire_ctx, outcome.structured, sfx,
                                source_id=event.context.get("source_id") or "",
                            )
                            if target_blocked:
                                blocked = True
                        # Nothing found on the target path → nothing to apply for this
                        # activation (fail closed; creating the missing thing is a
                        # separate, deliberate feature).
                        resolved_list = (
                            [] if blocked
                            else resolve_refs(effect, fire_ctx, outcome.structured,
                                              source_sfx_id=sfx.id)
                        )
                        if len(outcome.structured) > before:
                            blocked = True
                        else:
                            for resolved in resolved_list:
                                for target in targets:
                                    concrete = resolved if target is None else resolved.model_copy(
                                        update={"target": target, "target_spec": None})
                                    _effects_applier.effect_registry.apply(
                                        concrete, event.entity_id, event.universe, effect_context)
                                    outcome.applied.append(concrete)
                                    sfx_applied = True
                                    log.info("[process_event] applied sfx=%s effect=%s/%s target=%s via refs", sfx.id, concrete.type, concrete.action, concrete.target)
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
                # Resolved through the package module, not imported by value: the
                # broadcaster is module-level state that callers (and tests) swap
                # by rebinding ``effects_engine._emit_sfx_triggered``.
                from transversal.services import effects_engine as _pkg
                _pkg._emit_sfx_triggered(event.entity_id, sfx)

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
