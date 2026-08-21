"""Tests for the effect-action metadata contract."""

from transversal.services.effects_registry import EFFECT_ACTION_REGISTRY


def _meta(effect_action):
    for m in EFFECT_ACTION_REGISTRY:
        if m.effect_action == effect_action:
            return m
    return None


def test_step_actions_declare_steps_context_field():
    # `steps` must be a declared structured field (rendered by the dynamic
    # editor), not an undocumented raw-JSON context key.
    for action in ("step_up", "step_down", "gain_or_step_up"):
        meta = _meta(action)
        assert meta is not None, action
        fields = {f.name: f for f in meta.context_fields}
        assert "steps" in fields, f"{action} must declare a structured 'steps' field"
        assert fields["steps"].default == "1"


def test_entity_effects_declare_entity_field():
    # Trait/razmerit effects that act on an entity must expose the `entity`
    # subject field so the editor renders an ENTITY input.
    for action in ("earn", "spend", "gain", "gain_or_step_up", "cortex_gain",
                   "step_up", "step_down", "set"):
        meta = _meta(action)
        assert meta is not None, action
        fields = {f.name: f for f in meta.fields}
        assert "entity" in fields, f"{action} must declare an 'entity' field"
        assert fields["entity"].field_type == "entity"
