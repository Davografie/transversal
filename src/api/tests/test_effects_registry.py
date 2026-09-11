"""Tests for the effect-action metadata contract."""

from transversal.services.effects_registry import EFFECT_ACTION_REGISTRY, effect_card


def _meta(effect_action):
    for m in EFFECT_ACTION_REGISTRY:
        if m.effect_action == effect_action:
            return m
    return None


def test_delete_trait_is_authorable():
    """`remove` existed only as the internal inverse of `gain` — an author could
    not delete a trait at all. It is now a first-class action."""
    meta = next(m for m in EFFECT_ACTION_REGISTRY if m.action_id == "delete_trait")
    assert (meta.effect_type, meta.effect_action) == ("modify_trait", "remove")
    assert meta.target_kind == "trait"
    assert [f.name for f in meta.fields] == ["target", "entity"]
    assert effect_card("modify_trait", "remove") == "remove {target}"


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


def test_dice_limit_actions_declare_amount_and_limit():
    from transversal.services.effects_registry import get_inverse
    for action in ("increase", "decrease"):
        meta = _meta(action)
        assert meta is not None, action
        assert meta.effect_type == "modify_dice_limit"
        assert meta.supports_duration is True
        fields = {f.name: f for f in meta.fields}
        assert "result" in fields, f"{action} must declare an amount field"
        assert fields["result"].field_type == "number"
        ctx = {f.name: f for f in meta.context_fields}
        assert "limit" in ctx, f"{action} must declare a 'limit' context field"
        assert ctx["limit"].field_type == "select"
        assert ctx["limit"].options == ["total", "effect"]
    # increase/decrease are mutual inverses
    assert get_inverse("modify_dice_limit", "increase") == (("modify_dice_limit", "decrease"), False)
    assert get_inverse("modify_dice_limit", "decrease") == (("modify_dice_limit", "increase"), False)
