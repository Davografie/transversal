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
    source_sfx_id: str | None = None  # SFX id the client stamps on its dice


_armed: dict[str, list[ArmedEffect]] = {}


def _rolls_budget(effect: Effect) -> int:
    """Remaining fire budget from ``Effect.rolls`` (default 1 = one-shot)."""
    return max(1, effect.rolls or 1)


def arm_effect(entity_id: str, effect: Effect, source_sfx_id: str | None = None) -> None:
    """Arm ``effect`` so it fires at its roll-event timing (see :func:`fire_armed`).

    The effect is stored *raw* — roll-context ``{variables}`` are substituted at
    fire time, because the roll state does not exist at arm time. ``source_sfx_id``
    is the SFX id the client stamps onto its pool dice as ``armed_sfx_ids``, so the
    effect can match its own dice at fire time.
    """
    _armed.setdefault(entity_id, []).append(
        ArmedEffect(effect=effect, rolls=_rolls_budget(effect), source_sfx_id=source_sfx_id)
    )


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
            if _selects_dice(armed):
                dice = [d for d in (context or {}).get("rolls", []) if _selects_die(armed, d)]
                for die in dice:
                    resolved = _substitute_die_context(armed.effect, die, context or {})
                    effect_registry.apply(resolved, entity_id, universe, context or {})
                    applied.append(resolved)
            else:
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


def _selects_dice(armed: ArmedEffect) -> bool:
    """True when the armed effect iterates over a selected dice set."""
    return armed.source_sfx_id is not None or bool(armed.effect.die_filter)


def _selects_die(armed: ArmedEffect, die: dict) -> bool:
    """True when ``die`` belongs to the armed effect's selected set.

    The SFX id (stamped client-side as ``armed_sfx_ids``) identifies the effect's
    own dice; ``die_filter`` adds further equality predicates (e.g. ``role: None``).
    """
    if armed.source_sfx_id is not None:
        if armed.source_sfx_id not in (die.get("armed_sfx_ids") or []):
            return False
    return _die_matches(die, armed.effect.die_filter)


def _die_matches(die: dict, die_filter: dict) -> bool:
    """True when ``die`` satisfies every equality predicate in ``die_filter``."""
    return all(die.get(key) == value for key, value in (die_filter or {}).items())


def _substitute_die_context(effect: Effect, die: dict, context: dict) -> Effect:
    """Substitute roll-context + ``{triggered_die_*}`` variables for one die."""
    from transversal.services.effects_engine import _substitute_effect_context

    merged = dict(context or {})
    merged.update({
        "triggered_die_tier": die.get("tier"),
        "triggered_die_effect_die": die.get("effect_die"),
        "triggered_die_result": die.get("result"),
        "triggered_die_die": die.get("die"),
    })
    return _substitute_effect_context(effect, merged)


def clear_armed(entity_id: str) -> None:
    """Drop all armed effects for an entity (e.g. when its pool is cleared)."""
    _armed.pop(entity_id, None)


def list_armed(entity_id: str) -> list[Effect]:
    """The armed effects currently queued for an entity (tests/debug)."""
    return [a.effect for a in _armed.get(entity_id, [])]


def reset() -> None:
    """Clear the whole store (tests)."""
    _armed.clear()
