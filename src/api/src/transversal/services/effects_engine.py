"""Effects engine — SFX registry, trigger matching, and execution.

Handles the full lifecycle:
  1. Registry: load SFX definitions
  2. Trigger matching: event → available SFXs → match triggers
  3. Execution: dispatch via EffectRegistry, schedule deferred ones

Effects modify game state via the global effect_registry — any service
can register handlers for (type, action) pairs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

from transversal.domain import (
    ContestResult,
    DieType,
    DicePoolRequest,
    Effect,
    EffectTiming,
    RollResult,
    SFX,
)
import transversal.services.effects_applier as _effects_applier
from transversal.services.conditions import evaluate_conditions


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
class ScheduledEffect:
    """An effect queued for later execution."""
    sfx_name: str
    entity_id: str
    universe: str
    timing: EffectTiming
    beats_remaining: int = 0
    condition: Optional[str] = None
    effects: list[Effect] = field(default_factory=list)
    context: dict = field(default_factory=dict)


@dataclass
class PendingSfxEffect:
    """A pending ``{choose_*}`` effect plus its source SFX for display."""
    effect: Effect
    sfx_name: str
    sfx_description: str = ""


@dataclass
class EventOutcome:
    """Result of processing an event through the effects engine.

    ``applied`` are immediately-applied effects. ``pending`` are immediate
    effects with a ``{choose_*}`` target that were skipped and need user
    resolution before they can be applied.
    """
    applied: list[Effect] = field(default_factory=list)
    pending: list[PendingSfxEffect] = field(default_factory=list)


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
        self._schedule: list[ScheduledEffect] = []

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
                continue

            # Trigger match
            if not self._trigger_matches(sfx, event):
                continue

            # Condition gate (only when a repo is available to evaluate state)
            if sfx.conditions and repo is not None:
                entity = repo.get_entity(event.entity_id)
                if entity is None or not evaluate_conditions(entity, sfx.conditions, repo):
                    continue

            # Cost check: sum razmerit costs from spend effects
            total_razmerit_cost = 0
            for e in sfx.effects:
                if e.type == "transfer_razmerit" and e.action == "spend":
                    total_razmerit_cost += int(e.result or "0")
            if total_razmerit_cost > razmerit_balance:
                continue

            # Execute each effect with its own timing
            for effect in sfx.effects:
                effect = _substitute_effect_context(effect, event.context)
                if effect.timing == EffectTiming.IMMEDIATE:
                    if _effects_applier.is_choose_target(effect.target or ""):
                        outcome.pending.append(PendingSfxEffect(
                            effect=effect,
                            sfx_name=sfx.name,
                            sfx_description=sfx.description,
                        ))
                    else:
                        _effects_applier.effect_registry.apply(effect, event.entity_id, event.universe, event.context)
                        outcome.applied.append(effect)
                else:
                    self._schedule.append(
                        ScheduledEffect(
                            sfx_name=sfx.name,
                            entity_id=event.entity_id,
                            universe=event.universe,
                            timing=effect.timing,
                            beats_remaining=_beats_for_timing(effect.timing),
                            condition=event.context.get("condition"),
                            effects=[effect],
                            context=event.context,
                        )
                    )

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

        # on_relationship_create
        if trigger == "on_relationship_create" and event.type == "relationship_created":
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

    # ── Scheduling ───────────────────────────────────

    def schedule_effect(
        self,
        entity_id: str,
        universe: str,
        effect: Effect,
        sfx_name: str = "",
        context: Optional[dict] = None,
    ) -> None:
        """Queue a single deferred effect to fire at its configured timing.

        Used by the life path executor to defer non-immediate consequences into
        the same schedule that SFX effects use.
        """
        self._schedule.append(ScheduledEffect(
            sfx_name=sfx_name,
            entity_id=entity_id,
            universe=universe,
            timing=effect.timing,
            beats_remaining=_beats_for_timing(effect.timing),
            condition=None,
            effects=[effect],
            context=context or {},
        ))

    def tick_beat(self) -> list[ScheduledEffect]:
        """Advance the schedule by one beat. Returns effects that fire now."""
        fired = []
        remaining = []

        for se in self._schedule:
            if se.timing == EffectTiming.END_OF_BEAT:
                for e in se.effects:
                    _effects_applier.effect_registry.apply(e, se.entity_id, se.universe, se.context)
                fired.append(se)
            elif se.timing == EffectTiming.AFTER_BEATS:
                se.beats_remaining -= 1
                if se.beats_remaining <= 0:
                    for e in se.effects:
                        _effects_applier.effect_registry.apply(e, se.entity_id, se.universe, se.context)
                    fired.append(se)
                else:
                    remaining.append(se)
            else:
                remaining.append(se)

        self._schedule = remaining
        return fired

    def tick_scene(self) -> list[ScheduledEffect]:
        """End the scene — fire scene-level effects."""
        fired = []
        remaining = []

        for se in self._schedule:
            if se.timing == EffectTiming.END_OF_SCENE:
                for e in se.effects:
                    _effects_applier.effect_registry.apply(e, se.entity_id, se.universe, se.context)
                fired.append(se)
            else:
                remaining.append(se)

        self._schedule = remaining
        return fired

    def tick_session(self) -> list[ScheduledEffect]:
        """End the session — fire session-level effects."""
        fired = []
        for se in self._schedule:
            for e in se.effects:
                _effects_applier.effect_registry.apply(e, se.entity_id, se.universe, se.context)
            fired.append(se)
        self._schedule = []
        return fired

    @property
    def scheduled_count(self) -> int:
        return len(self._schedule)


def _substitute_effect_context(effect: Effect, context: dict) -> Effect:
    """Replace ``{context_key}`` placeholders in an effect's result from context."""
    if not context:
        return effect
    result = effect.result or ""
    new_result = result
    for key, value in context.items():
        placeholder = "{" + key + "}"
        if placeholder in new_result:
            new_result = new_result.replace(placeholder, str(value) if value is not None else "")
    if new_result == result:
        return effect
    return effect.model_copy(update={"result": new_result})


def _beats_for_timing(timing: EffectTiming) -> int:
    """Default beat count for AFTER_BEATS timing."""
    return 3  # default; overridden by explicit value in ScheduledEffect


def _noop_applier(action: Effect, entity_id: str, universe: str, context: dict) -> None:
    """Default no-op applier for testing."""
    pass


def contest_to_events(
    contest: "ContestResult",
    player_id: str,
    opponent_id: str,
    universe: str,
) -> list[GameEvent]:
    """Create GameEvents from a ContestResult so automated SFX can fire.

    Returns events for both sides — the engine processes them separately.
    Events emitted:
      - on_roll (for each side, with their roll_result)
      - on_contest_win / on_contest_loss (per side, via context)
      - on_complication (if any hitches)
      - on_botch (if all dice show 1)
    """
    events: list[GameEvent] = []

    # Determine who won from each side's perspective.
    # Ties favor the initiator, so there's no separate tie outcome.
    if contest.winner == "player":
        player_winner = "player"
        opponent_winner = "opponent"
    else:
        player_winner = "opponent"
        opponent_winner = "player"

    # Player event
    events.append(GameEvent(
        type="on_roll",
        entity_id=player_id,
        universe=universe,
        roll_result=contest.player_result,
        context={"contest_winner": player_winner, "opponent_id": opponent_id},
    ))

    # Opponent event
    events.append(GameEvent(
        type="on_roll",
        entity_id=opponent_id,
        universe=universe,
        roll_result=contest.opponent_result,
        context={"contest_winner": opponent_winner, "opponent_id": player_id},
    ))

    return events


def fire_contest_sfx(
    engine: EffectsEngine,
    contest: "ContestResult",
    player_id: str,
    opponent_id: str,
    universe: str,
    player_sfx_ids: list[str],
    opponent_sfx_ids: list[str],
    player_razmerit: int,
    opponent_razmerit: int,
) -> list[Effect]:
    """Process a contest result through the effects engine for both sides.

    Returns all immediately-applied effects (deferred are queued internally).
    """
    events = contest_to_events(contest, player_id, opponent_id, universe)
    applied: list[Effect] = []

    for event in events:
        if event.entity_id == player_id:
            sfx_ids = player_sfx_ids
            raz = player_razmerit
        else:
            sfx_ids = opponent_sfx_ids
            raz = opponent_razmerit
        applied.extend(engine.process_event(event, sfx_ids, raz))

    return applied