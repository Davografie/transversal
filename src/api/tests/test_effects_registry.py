"""Tests for the effect-action metadata contract."""

from transversal.services.effects_registry import EFFECT_ACTION_REGISTRY, effect_card


def _meta(effect_action):
    for m in EFFECT_ACTION_REGISTRY:
        if m.effect_action == effect_action:
            return m
    return None


def test_the_step_die_actions_declare_a_path_element():
    """A die in a pool is not a *picker* kind — there is no die picker, so these
    actions declare no `target_kind` and their literal mode stays a keyword box.
    But a path to a die is perfectly writable, which is what `path_element` says
    (the two questions were one field before: `target_kind` named both the picker
    and the path's destination)."""
    for action_id in ("step_up_die", "step_down_die"):
        meta = next(m for m in EFFECT_ACTION_REGISTRY if m.action_id == action_id)
        assert meta.target_kind is None, action_id
        assert meta.path_element == "die", action_id
        assert [f.name for f in meta.fields] == ["target"]


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


def test_increase_by_effect_die_mirrors_reduce():
    """P1.8's positive comparison: 'set if the effect die beats the rating, else
    step up'. Same declared shape as its negative twin, opposite direction."""
    meta = next(m for m in EFFECT_ACTION_REGISTRY if m.action_id == "increase_by_effect_die")
    assert (meta.effect_type, meta.effect_action) == ("modify_trait", "increase_by_effect")
    assert meta.target_kind == "trait"
    assert [f.name for f in meta.fields] == ["target", "entity"]
    ctx = {f.name: f for f in meta.context_fields}
    assert ctx["effect_die"].default == "{effect_die}"
    assert effect_card("modify_trait", "increase_by_effect") == "increase {target} by the effect die"

    twin = next(m for m in EFFECT_ACTION_REGISTRY if m.action_id == "reduce_by_effect_die")
    assert meta.valid_timings == twin.valid_timings
    assert [f.name for f in meta.fields] == [f.name for f in twin.fields]
    assert sorted(f.name for f in meta.context_fields) == sorted(f.name for f in twin.context_fields)
    # Both are Trait actions in the editor (they were falling into "Other").
    assert meta.group == "Trait" and twin.group == "Trait"
