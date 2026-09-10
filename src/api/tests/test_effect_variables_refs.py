"""Named references are offered as variables, typed by what they resolve to.

The editor's `select variable` / `{name}` lists come from ``effectVariables``.
A reference's own name is part of that scope — the engine binds each resolved
ref (``effects_engine._bind_ref_value``) — so the wizard must offer it, and type
it, or an author cannot reference the thing they just declared.
"""

from transversal.api.graphql.schema import Query
from transversal.domain import EffectTiming


def _variables(effects):
    """Run the schema's effectVariables resolver directly (no HTTP)."""
    return Query().effect_variables(None, effects)


def _effect(**overrides):
    payload = {
        "timing": EffectTiming.IMMEDIATE,
        "type": "attune",
        "action": "enable",
        "target": "",
        "refs": {
            "universe": {"spec": {"steps": [
                {"kind": "select", "collection": "entities"},
                {"kind": "filter", "field": "type", "operator": "==", "value": "universe"},
                {"kind": "choose", "count": 1},
            ]}},
            "projection": {"spec": {"steps": [
                {"kind": "select", "collection": "variable", "variable": "universe"},
            ]}},
        },
    }
    payload.update(overrides)
    from transversal.api.graphql.types import EffectInput

    return EffectInput(**payload)


def test_a_reference_is_offered_as_a_typed_variable():
    names = {v.name: v.element for v in _variables([_effect()])}
    # Declared, so a later path can compare against the chosen world...
    assert names.get("universe") == "universe"
    # ...and the thing the effect ultimately acts on.
    assert names.get("projection") == "projection"


def test_step_outputs_still_come_through():
    effect = _effect(refs={"projection": {"spec": {"steps": [
        {"kind": "select", "collection": "self", "output": "attune_target"},
    ]}}})
    names = {v.name: v.element for v in _variables([effect])}
    assert names.get("attune_target") == "entity"
