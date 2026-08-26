"""Roll-scoped effect deferral — arm an SFX to fire at the next roll event.

Roll events (``on_roll``/``on_set``/``on_result``) are ephemeral and per-roll,
so they can't live in the persisted scheduled-events store (which advances on
state-change / global events). This module keeps *armed SFXs* in memory, keyed
by entity, and fires their roll-timing effects when the matching roll event
happens. It is the "rolls" side of the temporal spine: an SFX is armed at
trigger time for its ``SFX.duration`` (default one roll), and its effects fire
on each matching roll event until that duration's roll budget is exhausted.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from transversal.domain import Effect, EffectTiming

# EffectTiming values that defer to a per-roll event rather than a time
# boundary or persisted state change.
ROLL_TIMINGS = frozenset({
    EffectTiming.ON_ROLL,
    EffectTiming.ON_SET,
    EffectTiming.ON_RESULT,
})


@dataclass
class ArmedSfx:
    effects: list[Effect] = field(default_factory=list)  # the SFX's roll-timing effects
    rolls: int = 1  # remaining roll-event budget (>= 1)
    source_sfx_id: str | None = None  # SFX id the client stamps on its dice


_armed: dict[str, list[ArmedSfx]] = {}


def _rolls_budget(duration) -> int:
    """Remaining fire budget from an SFX duration's ``rolls`` timer (default 1)."""
    if not duration or not getattr(duration, "timers", None):
        return 1
    for timer in duration.timers:
        if timer.event == "rolls":
            return max(1, timer.remaining)
    return 1


def arm_sfx(
    entity_id: str,
    effects: list[Effect],
    *,
    source_sfx_id: str | None = None,
    duration=None,
) -> None:
    """Arm an SFX's roll-timing ``effects`` so they fire at their roll events.

    ``duration`` is the SFX's effective lifetime (``SFX.duration``); its
    ``rolls`` timer (default 1) is the roll-event budget. Effects are stored
    raw — roll-context ``{variables}`` substitute at fire time, because the roll
    state does not exist at arm time.
    """
    _armed.setdefault(entity_id, []).append(
        ArmedSfx(
            effects=list(effects),
            rolls=_rolls_budget(duration),
            source_sfx_id=source_sfx_id,
        )
    )


def fire_armed(
    entity_id: str,
    event_type: str,
    universe: str,
    context: dict | None = None,
) -> list[Effect]:
    """Fire armed-SFX effects whose timing matches ``event_type``; consume a roll.

    Returns the applied effects. Each armed SFX survives ``rolls`` matching
    events; a one-shot SFX (no ``rolls`` duration) fires once and is dropped.
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
    kept: list[ArmedSfx] = []
    rolls = (context or {}).get("rolls", [])

    for armed in _armed[entity_id]:
        if any(e.timing.value == event_type for e in armed.effects):
            for effect in armed.effects:
                if effect.timing.value != event_type:
                    continue
                if armed.source_sfx_id is not None or bool(effect.die_filter):
                    dice = [d for d in rolls if _selects_die(armed.source_sfx_id, effect, d)]
                    for die in dice:
                        resolved = _substitute_die_context(effect, die, context or {})
                        effect_registry.apply(resolved, entity_id, universe, context or {})
                        applied.append(resolved)
                else:
                    resolved = _substitute_effect_context(effect, context or {})
                    effect_registry.apply(resolved, entity_id, universe, context or {})
                    applied.append(resolved)

            # One roll event consumed (a matching event happened for this SFX).
            armed.rolls -= 1
            if armed.rolls > 0:
                kept.append(armed)
        else:
            kept.append(armed)
    _armed[entity_id] = kept
    return applied


def _selects_die(source_sfx_id: str | None, effect: Effect, die: dict) -> bool:
    """True when ``die`` belongs to the effect's selected set.

    The SFX id (stamped client-side as ``armed_sfx_ids``) identifies the SFX's
    own dice; ``die_filter`` adds further equality predicates (e.g. ``role: None``).
    """
    if source_sfx_id is not None:
        if source_sfx_id not in (die.get("armed_sfx_ids") or []):
            return False
    return _die_matches(die, effect.die_filter)


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
    """Drop all armed SFX for an entity (e.g. when its pool is cleared)."""
    _armed.pop(entity_id, None)


def list_armed(entity_id: str) -> list[Effect]:
    """The armed roll-timing effects currently queued for an entity (tests/debug)."""
    out: list[Effect] = []
    for armed in _armed.get(entity_id, []):
        out.extend(armed.effects)
    return out


def reset() -> None:
    """Clear the whole store (tests)."""
    _armed.clear()
