"""Tests for the effect-action metadata contract."""

from transversal.services.effects_registry import EFFECT_ACTION_REGISTRY


def _meta(effect_action):
    for m in EFFECT_ACTION_REGISTRY:
        if m.effect_type == "modify_trait" and m.effect_action == effect_action:
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
