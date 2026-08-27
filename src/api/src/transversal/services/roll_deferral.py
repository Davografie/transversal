"""Roll-scoped effect deferral — arm an SFX to fire at the next roll event.

Roll events (``on_roll``/``on_set``/``on_result``) are ephemeral and per-roll,
so they can't live in the persisted scheduled-events store (which advances on
state-change / global events). This module keeps *armed SFXs* in memory, keyed
by entity, and fires their roll-timing effects when the matching roll event
happens. It is the "rolls" side of the temporal spine: an SFX is armed at
trigger time for its ``SFX.duration`` (default one roll), and its effects fire
on each matching roll event until that duration is exhausted.

``SFX.duration`` splits into two axes:

- **rolls** — a roll-event budget, decremented on each matching roll event.
  ``None`` (no ``rolls`` timer) = no roll limit.
- **boundary events** — ``beat``/``scene``/``session`` or a state-change event
  (``location_changed``/``trait_updated``) that drops the armed SFX from the
  tracker when that event fires (see :func:`expire_armed`).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from transversal.domain import Effect, EffectTiming

log = logging.getLogger("transversal.sfx")

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
    rolls: Optional[int] = None  # remaining roll-event budget; None = no roll limit
    expiry_events: list[str] = field(default_factory=list)  # boundary/state events that drop it
    source_sfx_id: str | None = None  # SFX id the client stamps on its dice


_armed: dict[str, list[ArmedSfx]] = {}

# Passive rules (e.g. One Trick) arm once per session and apply to *every*
# entity's rolls — not keyed by entity, so late joiners are covered. They carry
# no ``source_sfx_id`` (that stamp is the player-choice signal); selection is
# declarative via ``die_filter``/spec.
_global_armed: list[ArmedSfx] = []


def _split_duration(duration) -> tuple[Optional[int], list[str]]:
    """Split an SFX duration into ``(rolls_budget, boundary_events)``."""
    rolls: Optional[int] = None
    expiry_events: list[str] = []
    if duration and getattr(duration, "timers", None):
        for timer in duration.timers:
            if timer.event == "rolls":
                rolls = max(1, timer.remaining)
            else:
                expiry_events.append(timer.event)
    return rolls, expiry_events


def arm_sfx(
    entity_id: str,
    effects: list[Effect],
    *,
    source_sfx_id: str | None = None,
    duration=None,
) -> None:
    """Arm an SFX's roll-timing ``effects`` so they fire at their roll events.

    ``duration`` is the SFX's effective lifetime (``SFX.duration``): its
    ``rolls`` timer is the roll-event budget (``None`` = no roll limit), and any
    other timer (``beat``/``scene``/``session``/state-change) is a boundary that
    drops the SFX. Effects are stored raw — roll-context ``{variables}``
    substitute at fire time, because the roll state does not exist at arm time.
    """
    rolls, expiry_events = _split_duration(duration)
    log.info(
        "[roll_deferral.arm_sfx] entity=%s sfx=%s effects=%s rolls=%s expiry=%s",
        entity_id, source_sfx_id,
        [(e.timing.value, e.type, e.action, e.target, e.die_filter) for e in effects],
        rolls, expiry_events,
    )
    _armed.setdefault(entity_id, []).append(
        ArmedSfx(
            effects=list(effects),
            rolls=rolls,
            expiry_events=expiry_events,
            source_sfx_id=source_sfx_id,
        )
    )


def arm_passive(
    effects: list[Effect],
    *,
    duration=None,
) -> None:
    """Arm a passive rule's roll-timing effects in the *global* set.

    Unlike :func:`arm_sfx`, this is not entity-keyed and carries no
    ``source_sfx_id``: a passive rule's scope is declarative, so it selects
    dice via ``die_filter`` (stamping is a player-choice signal, not used here).
    """
    rolls, expiry_events = _split_duration(duration)
    log.info(
        "[roll_deferral.arm_passive] effects=%s rolls=%s expiry=%s",
        [(e.timing.value, e.type, e.action, e.target, e.die_filter) for e in effects],
        rolls, expiry_events,
    )
    _global_armed.append(
        ArmedSfx(
            effects=list(effects),
            rolls=rolls,
            expiry_events=expiry_events,
            source_sfx_id=None,
        )
    )


def fire_armed(
    entity_id: str,
    event_type: str,
    universe: str,
    context: dict | None = None,
) -> list[Effect]:
    """Fire armed-SFX effects whose timing matches ``event_type``; consume a roll.

    Returns the applied effects. Each entity-local armed SFX survives ``rolls``
    matching events (``None`` = indefinite); a one-roll SFX fires once and is
    dropped. Passive (global) rules are not consumed — they apply to every
    entity's rolls for the whole session.
    """
    local = _armed.get(entity_id, [])
    if not local and not _global_armed:
        return []
    log.info(
        "[roll_deferral.fire_armed] entity=%s event=%s local=%s global=%s",
        entity_id, event_type,
        [(a.source_sfx_id, [e.timing.value for e in a.effects], a.rolls) for a in local],
        [(a.source_sfx_id, [e.timing.value for e in a.effects], a.rolls) for a in _global_armed],
    )
    if not universe:
        from transversal.main import _get_repo

        entity = _get_repo().get_entity(entity_id)
        if entity is not None:
            universe = entity.current_universe or ""

    rolls = (context or {}).get("rolls", [])
    applied: list[Effect] = []

    # Entity-local armed SFX — consume their roll budget per matching event.
    kept: list[ArmedSfx] = []
    for armed in local:
        if any(e.timing.value == event_type for e in armed.effects):
            applied.extend(_apply_armed(armed, event_type, entity_id, universe, context, rolls))
            # One roll event consumed (a matching event happened for this SFX).
            if armed.rolls is not None:
                armed.rolls -= 1
                if armed.rolls <= 0:
                    continue  # exhausted — drop
            kept.append(armed)
        else:
            kept.append(armed)
    _armed[entity_id] = kept

    # Passive (global) rules — not consumed; apply to this entity's rolls too.
    for armed in _global_armed:
        applied.extend(_apply_armed(armed, event_type, entity_id, universe, context, rolls))

    return applied


def _apply_armed(
    armed: ArmedSfx,
    event_type: str,
    entity_id: str,
    universe: str,
    context: dict | None,
    rolls: list[dict],
) -> list[Effect]:
    """Apply one armed entry's matching effects to ``rolls``; return them."""
    from transversal.services.effects_applier import effect_registry
    from transversal.services.effects_engine import _substitute_effect_context

    applied: list[Effect] = []
    for effect in armed.effects:
        if effect.timing.value != event_type:
            continue
        if armed.source_sfx_id is not None or bool(effect.die_filter):
            dice = [d for d in rolls if _selects_die(armed.source_sfx_id, effect, d)]
            log.info(
                "[roll_deferral._apply_armed] sfx=%s effect=%s/%s candidates=%s matched=%s",
                armed.source_sfx_id, effect.type, effect.action,
                [(d.get('armed_sfx_ids'), d.get('role'), d.get('ts_id')) for d in rolls],
                [(d.get('armed_sfx_ids'), d.get('role'), d.get('ts_id')) for d in dice],
            )
            for die in dice:
                resolved = _substitute_die_context(effect, die, context or {})
                effect_registry.apply(resolved, entity_id, universe, context or {})
                applied.append(resolved)
        else:
            resolved = _substitute_effect_context(effect, context or {})
            effect_registry.apply(resolved, entity_id, universe, context or {})
            applied.append(resolved)
    return applied


def expire_armed(entity_id: str, event_type: str) -> None:
    """Drop armed SFX whose boundary expiry matches ``event_type``."""
    if entity_id not in _armed:
        return
    _armed[entity_id] = [a for a in _armed[entity_id] if event_type not in a.expiry_events]


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
        "triggered_die_ts_id": die.get("ts_id"),
        "triggered_die_source_kind": die.get("source_kind"),
        "triggered_die_role": die.get("role"),
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


def list_armed_sfx_ids(entity_id: str) -> list[str]:
    """The SFX ids currently armed for an entity (for client re-stamp/display)."""
    return [a.source_sfx_id for a in _armed.get(entity_id, []) if a.source_sfx_id]


def expire_global(event_type: str) -> None:
    """Drop passive rules whose boundary expiry matches ``event_type``."""
    global _global_armed
    _global_armed = [a for a in _global_armed if event_type not in a.expiry_events]


def clear_global_armed() -> None:
    """Drop every passive rule (e.g. at session end)."""
    global _global_armed
    _global_armed = []


def list_global_armed() -> list[Effect]:
    """The passive (global) roll-timing effects currently armed (tests/debug)."""
    out: list[Effect] = []
    for armed in _global_armed:
        out.extend(armed.effects)
    return out


def reset() -> None:
    """Clear the whole store (tests)."""
    _armed.clear()
    _global_armed.clear()
