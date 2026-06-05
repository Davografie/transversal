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
    DieType,
    DicePoolRequest,
    EffectAction,
    EffectTiming,
    RollResult,
    SFX,
)
import transversal.services.effects_applier as _effects_applier


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
    effects: list[EffectAction] = field(default_factory=list)
    context: dict = field(default_factory=dict)


# ── Effect Application ───────────────────────────────

EffectApplier = Callable[[EffectAction, str, str, dict], None]
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

    # ── Trigger ──────────────────────────────────────

    def process_event(
        self,
        event: GameEvent,
        available_sfx_ids: list[str],
        razmerit_balance: int,
    ) -> list[EffectAction]:
        """Process a game event against available SFXs.

        Args:
            event: What happened (roll, complication, etc.)
            available_sfx_ids: Which SFXs the entity has unlocked
            razmerit_balance: Current razmerit for cost checking

        Returns:
            Immediately applied effects (deferred ones are queued internally).
        """
        applied: list[EffectAction] = []

        for sfx_id in available_sfx_ids:
            sfx = self._sfx_registry.get(sfx_id)
            if sfx is None:
                continue

            # Trigger match
            if not self._trigger_matches(sfx, event):
                continue

            # Cost check
            if sfx.cost > razmerit_balance:
                continue

            # Deduct cost via registry
            spend_action = EffectAction(
                type="transfer_razmerit",
                action="spend",
                target=event.entity_id,
                result=str(sfx.cost),
            )
            _effects_applier.effect_registry.apply(spend_action, event.entity_id, event.universe, {})

            # Execute effects
            for effect in sfx.effects:
                if sfx.timing == EffectTiming.IMMEDIATE:
                    _effects_applier.effect_registry.apply(effect, event.entity_id, event.universe, event.context)
                    applied.append(effect)
                else:
                    self._schedule.append(
                        ScheduledEffect(
                            sfx_name=sfx.name,
                            entity_id=event.entity_id,
                            universe=event.universe,
                            timing=sfx.timing,
                            beats_remaining=_beats_for_timing(sfx.timing),
                            condition=event.context.get("condition"),
                            effects=[effect],
                            context=event.context,
                        )
                    )

        return applied

    def _trigger_matches(self, sfx: SFX, event: GameEvent) -> bool:
        """Check if an SFX's trigger matches the event.

        Simple string matching for now. Can be extended to pattern matching.
        """
        trigger = sfx.trigger

        # Direct match
        if trigger == event.type:
            return True

        # on_complication also fires for hitches within other events
        if trigger == "on_complication" and event.type in ("on_roll", "on_result"):
            if event.roll_result:
                if hasattr(event.roll_result, 'hitches') and event.roll_result.hitches:
                    return True

        # on_botch
        if trigger == "on_botch" and event.roll_result and getattr(event.roll_result, 'botch', False):
            return True

        return False

    # ── Scheduling ───────────────────────────────────

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


def _beats_for_timing(timing: EffectTiming) -> int:
    """Default beat count for AFTER_BEATS timing."""
    return 3  # default; overridden by explicit value in ScheduledEffect


def _noop_applier(action: EffectAction, entity_id: str, universe: str, context: dict) -> None:
    """Default no-op applier for testing."""
    pass
