"""The effect wire shape, both ways — the one place it is mapped.

`effect_to_wire_dict` shapes a domain effect for `EffectInput` (the REST fire
response, the SSE question payload); `effect_from_wire_dict` reads one back. They
live together because the mapping drifted every time a second copy existed: the
REST side carried the domain shape while the GraphQL side carried camelCase, and
the portal's structured specs were dropped on the way in for months.

Kept free of the repository and the engine on purpose — a converter, nothing more.
"""

from __future__ import annotations

from transversal.domain import Effect


_EFFECT_CAMEL_FIELDS = {
    "die_filter": "dieFilter",
    "target_spec": "targetSpec",
    "entity_spec": "entitySpec",
    # Both added to `Effect` after this map was written and missed here. Left in
    # snake_case they are rejected by `EffectInput`, which fails the **whole**
    # `resolveEffectTargets` mutation — so answering a structured choice silently
    # did nothing. `test_effect_wire_dict_is_a_valid_effect_input` now holds the
    # two shapes together so the next field added cannot slip through.
    "owner_spec": "ownerSpec",
    "result_spec": "resultSpec",
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


def effect_from_wire_dict(d: dict):
    """Convert a frontend effect dict (camelCase) to a domain Effect.

    The inverse of :func:`effect_to_wire_dict`, and the pair lives here so the two
    directions cannot drift apart. Two callers: `fire_portal` (a portal edge's
    stored effects) and `POST /effects/apply` (one effect, run at the GM's request
    for testing).

    ⚠ **The structured specs have to come across.** It used to map just the flat
    fields, so an effect authored with a `targetSpec` arrived with `target=""` and
    `target_spec=None`: its destination lives *only* in the spec. The applier then
    ran the legacy `("travel", "move")` handler with no destination and reported
    `applied: []` with nothing pending — the traveller simply did not move. That is
    why the Eindhoven Airport → Турышка аэропорт portal still did nothing *after*
    the 404 in `fire_portal` was fixed (2026-09-26).

    The same adapter was once a third hand-rolled copy of this mapping (the GraphQL
    converters keep their own), which is exactly how it drifted; one shared
    converter is the real fix. Known gap left deliberately: **`conditions` are not
    carried** — mapping them needs a hand-written field map (`ConditionInput` is a
    Strawberry type, not a dict) and no live portal effect uses one, so it could
    not be verified rather than guessed.
    """
    from transversal.domain import Effect, EffectDuration, EffectTiming, Timer, TimerCombine, TargetSpec, TargetRef

    def _enum(cls, value, default):
        if value is None:
            return default
        if isinstance(value, str):
            try:
                return cls[value]  # member name ("IMMEDIATE", "FIRST_TO_FIRE")
            except KeyError:
                try:
                    return cls(value)  # value ("immediate", "first_to_fire")
                except ValueError:
                    return default
        return value

    def _spec(camel: str, snake: str):
        """A targeting path, whichever spelling the caller sent."""
        raw = d.get(camel) or d.get(snake)
        return TargetSpec.model_validate(raw) if raw else None

    duration = None
    if d.get("duration"):
        dur = d["duration"]
        duration = EffectDuration(
            timers=[Timer(event=t.get("event") or "scene", remaining=t.get("remaining", 0))
                    for t in (dur.get("timers") or [])],
            combine=_enum(TimerCombine, dur.get("combine"), TimerCombine.FIRST_TO_FIRE),
        )

    return Effect(
        timing=_enum(EffectTiming, d.get("timing"), EffectTiming.IMMEDIATE),
        type=d.get("type", ""),
        action=d.get("action", ""),
        target=d.get("target", ""),
        entity=d.get("entity", ""),
        result=d.get("result"),
        die_filter=d.get("dieFilter") or d.get("die_filter") or {},
        negative=bool(d.get("negative", False)),
        context=d.get("context") or {},
        duration=duration,
        target_spec=_spec("targetSpec", "target_spec"),
        entity_spec=_spec("entitySpec", "entity_spec"),
        owner_spec=_spec("ownerSpec", "owner_spec"),
        result_spec=_spec("resultSpec", "result_spec"),
        refs={k: TargetRef.model_validate(v)
              for k, v in (d.get("refs") or {}).items()},
    )
