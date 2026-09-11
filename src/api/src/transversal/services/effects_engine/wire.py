"""Wire — split out of src/api/src/transversal/services/effects_engine.py."""

from transversal.domain import Effect


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
