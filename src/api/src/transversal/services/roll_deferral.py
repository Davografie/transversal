"""Roll-scoped effect deferral — arm an effect to fire at the next roll event.

Roll events (``on_roll``/``on_set``/``on_result``) are ephemeral and per-roll,
so they can't live in the persisted scheduled-events store (which advances on
state-change / global events). This module keeps armed effects in memory, keyed
by entity, and fires them when the matching roll event happens. It is the
"rolls" side of the temporal spine: a roll-timing effect is armed at trigger
time and fired at its roll event, consuming its ``duration: rolls: N`` budget.
"""

from __future__ import annotations

from dataclasses import dataclass

from transversal.domain import Effect, EffectTiming

# EffectTiming values that defer to a per-roll event rather than a time
# boundary or persisted state change.
ROLL_TIMINGS = frozenset({
    EffectTiming.ON_ROLL,
    EffectTiming.ON_SET,
    EffectTiming.ON_RESULT,
})


@dataclass
class ArmedEffect:
    effect: Effect
    rolls: int  # remaining matching-event budget (>= 1)


_armed: dict[str, list[ArmedEffect]] = {}


def _rolls_budget(effect: Effect) -> int:
    """Remaining fire budget from ``duration: rolls: N`` (default 1 = one-shot)."""
    if not effect.duration or not effect.duration.timers:
        return 1
    for timer in effect.duration.timers:
        if timer.event == "rolls":
            return max(1, timer.remaining)
    return 1


def arm_effect(entity_id: str, effect: Effect) -> None:
    """Arm ``effect`` so it fires at its roll-event timing (see :func:`fire_armed`).

    The effect is stored *raw* — roll-context ``{variables}`` are substituted at
    fire time, because the roll state does not exist at arm time.
    """
    _armed.setdefault(entity_id, []).append(ArmedEffect(effect=effect, rolls=_rolls_budget(effect)))


def fire_armed(
    entity_id: str,
    event_type: str,
    universe: str,
    context: dict | None = None,
) -> list[Effect]:
    """Fire armed effects whose timing matches ``event_type``; consume their budget.

    Returns the applied effects. Each armed effect fires at most ``rolls`` times;
    a one-shot effect (no ``rolls`` duration) fires once and is dropped.
    """
    if entity_id not in _armed:
        return []
    if not universe:
        from transversal.main import _get_repo

        entity = _get_repo().get_entity(entity_id)
        if entity is not None:
            universe = entity.current_universe or ""

    from transversal.services.effects_applier import effect_registry
    from transversal.services.effects_engine import _substitute_effect_context

    applied: list[Effect] = []
    kept: list[ArmedEffect] = []
    for armed in _armed[entity_id]:
        if armed.effect.timing.value == event_type:
            resolved = _substitute_effect_context(armed.effect, context or {})
            effect_registry.apply(resolved, entity_id, universe, context or {})
            applied.append(resolved)
            armed.rolls -= 1
            if armed.rolls > 0:
                kept.append(armed)
        else:
            kept.append(armed)
    _armed[entity_id] = kept
    return applied


def clear_armed(entity_id: str) -> None:
    """Drop all armed effects for an entity (e.g. when its pool is cleared)."""
    _armed.pop(entity_id, None)


def list_armed(entity_id: str) -> list[Effect]:
    """The armed effects currently queued for an entity (tests/debug)."""
    return [a.effect for a in _armed.get(entity_id, [])]


def reset() -> None:
    """Clear the whole store (tests)."""
    _armed.clear()
