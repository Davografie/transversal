"""Tests for the effect-action metadata contract."""

from transversal.services.effects_registry import EFFECT_ACTION_REGISTRY, effect_card


def _meta(effect_action):
    for m in EFFECT_ACTION_REGISTRY:
        if m.effect_action == effect_action:
            return m
    return None


def test_the_change_die_family_accepts_either_locus():
    """One family, one question: *which die, and what happens to it*. The path
    answers which — a die in the assembled pool, or a die of a trait instance's
    rating — and where it lands answers what the change means.

    A die is not a *picker* kind (there is no die picker), so these actions declare
    no `target_kind`; the two questions were one field before."""
    for action_id in ("set_die", "step_up_die", "step_down_die",
                      "double_die", "split_die", "remove_die"):
        meta = next(m for m in EFFECT_ACTION_REGISTRY if m.action_id == action_id)
        assert meta.target_kind is None, action_id
        assert set(meta.path_element) == {"die", "rating_die"}, action_id
        assert "target" in [f.name for f in meta.fields], action_id


def test_a_change_to_a_rating_can_be_timed_but_a_pool_die_cannot():
    """A pool is rebuilt every roll, so a duration on it would be a field that
    lies; a rating is a fact about the character, so a duration there is real.
    The declaration names the one element a duration is offered for."""
    for action_id in ("set_die", "step_up_die", "step_down_die",
                      "double_die", "split_die", "remove_die"):
        meta = next(m for m in EFFECT_ACTION_REGISTRY if m.action_id == action_id)
        assert meta.supports_duration is True, action_id
        assert meta.duration_elements == ("rating_die",), action_id


def test_reroll_die_is_pool_only():
    """Rolling a die's *result* needs a result, and a rating die has none — so the
    destination is the pool alone. The type-checker says so while authoring rather
    than the applier refusing at fire time."""
    meta = next(m for m in EFFECT_ACTION_REGISTRY if m.action_id == "reroll_die")
    assert meta.path_element == ("die",)
    assert meta.supports_duration is False


def test_the_family_takes_a_count_where_it_needs_one():
    """Step up/down take steps, double/split take extra dice — one `count` key,
    with the label saying which for that verb. Set and remove name a size and a
    die, not a number of them.

    It has to be a *context* field, not a plain field: the editor persists only
    `target`/`entity`/`result` out of `fields`, so a count declared there would be
    silently dropped on save, and the applier reads it from `context`."""
    for action_id in ("step_up_die", "step_down_die", "double_die", "split_die"):
        meta = next(m for m in EFFECT_ACTION_REGISTRY if m.action_id == action_id)
        assert "count" not in [f.name for f in meta.fields], action_id
        count = next(f for f in meta.context_fields if f.name == "count")
        assert count.field_type == "number", action_id
        assert count.default == "1", action_id
    for action_id in ("set_die", "remove_die"):
        meta = next(m for m in EFFECT_ACTION_REGISTRY if m.action_id == action_id)
        assert "count" not in [f.name for f in meta.context_fields], action_id


def test_the_change_die_family_reads_as_one_group():
    """The author asked for these to be grouped; the group is the declaration the
    editor optgroups by. The two effect-die comparisons belong here too — the
    effect die is their reference instead of a number."""
    for action_id in ("set_die", "step_up_die", "step_down_die",
                      "double_die", "split_die", "remove_die", "reroll_die",
                      "reduce_by_effect_die", "increase_by_effect_die"):
        meta = next(m for m in EFFECT_ACTION_REGISTRY if m.action_id == action_id)
        assert meta.group == "Change a Die", action_id


def test_the_effect_die_comparisons_accept_a_die_as_well_as_a_trait():
    """They were authored against a trait's rating before a die had two homes.
    The trait picker stays (an old effect still names a trait), and a path to
    either home is now offered as well."""
    for action_id in ("reduce_by_effect_die", "increase_by_effect_die"):
        meta = next(m for m in EFFECT_ACTION_REGISTRY if m.action_id == action_id)
        assert set(meta.path_element) == {"die", "rating_die"}, action_id
        assert meta.target_kind == "trait", action_id
        assert next(f.label for f in meta.fields if f.name == "target") == "Target"


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
    # Both sit with the dice actions: the effect die is their reference, and the
    # target they compare against is a die (with the trait picker kept for
    # content authored before a die had two homes).
    assert meta.group == "Change a Die" and twin.group == "Change a Die"
    assert set(meta.path_element) == {"die", "rating_die"}
    assert set(twin.path_element) == {"die", "rating_die"}


def test_producing_actions_declare_their_output_element():
    """`Effect.output`'s type is declared on the action — one source for the
    runtime that binds the produced id and the editor that offers the name."""
    from transversal.services.effects_registry import output_element_for

    assert output_element_for("modify_trait", "gain") == "traitsetting"
    assert output_element_for("modify_trait", "gain_or_step_up") == "traitsetting"
    assert output_element_for("modify_trait", "cortex_gain") == "traitsetting"
    assert output_element_for("modify_trait", "copy") == "traitsetting"
    assert output_element_for("modify_trait", "move") == "traitsetting"
    assert output_element_for("projection", "create") == "projection"
    # Actions that produce nothing nameable declare nothing, so an author's name
    # on them is ignored rather than bound to something surprising.
    assert output_element_for("modify_roll", "play_as_rating") == ""


def test_copy_and_move_put_the_trait_before_the_recipient():
    """The form reads subject → destination.

    "Trait to Move" is the *subject* of a copy/move, and "Give To" is where it
    lands, so the ref renders above the field (``refs_first``) and the shared
    entity targeter says what this action is targeting the entity *for* — it is
    not a plain "Entity" here.
    """
    for action_id in ("copy_trait", "move_trait"):
        meta = next(m for m in EFFECT_ACTION_REGISTRY if m.action_id == action_id)
        assert meta.refs_first is True, action_id
        assert [r.element for r in meta.refs] == ["traitsetting"], action_id
        (field,) = meta.fields
        assert field.name == "entity", action_id
        assert field.label == "Give To", action_id
        assert field.description, action_id


# ── Retiring a superseded action ───────────────────────────────

def test_a_retired_action_is_not_offered_but_still_resolves():
    """Retiring is about *authoring*: the editor must not offer a superseded
    action again, while the registry keeps it — that is where an existing
    effect's inverse, its card template and its dispatch live. Nothing already
    authored is silently rewritten or left unable to revert."""
    from types import SimpleNamespace as NS

    from transversal.api.graphql.resolvers.queries_targeting import QueriesTargeting
    from transversal.services import effects_registry as reg

    retired = {m.action_id: (m.effect_type, m.effect_action)
               for m in EFFECT_ACTION_REGISTRY if m.retired}
    assert retired, "the vocabulary round retired something"

    class Repo:
        def list_all_entities(self):
            return []

    info = NS(context={"entity_manager": NS(repo=Repo())})
    served = {a.action_id for a in QueriesTargeting().effect_actions(info)}
    assert not (served & set(retired)), "a retired action is still offered"

    # Each still declares what an existing effect needs to keep working.
    for action_id, (effect_type, action) in retired.items():
        meta = next(m for m in EFFECT_ACTION_REGISTRY if m.action_id == action_id)
        assert (meta.effect_type, meta.effect_action) == (effect_type, action)
        assert reg.effect_card(effect_type, action), action_id
    # The inverse a durationed stored effect reverts through.
    assert reg.get_inverse("modify_trait", "step_up")[0] == ("modify_trait", "step_down")
    assert reg.get_inverse("modify_trait", "remove_die")[0] == ("modify_trait", "add_die")


def test_remove_trait_is_the_name_for_taking_a_trait_off():
    """`negate_complication` is retired in its favour: the outcome action implied
    which trait it meant, where this one names the instance."""
    meta = next(m for m in EFFECT_ACTION_REGISTRY if m.action_id == "delete_trait")
    assert meta.label == "Remove Trait"
    assert (meta.effect_type, meta.effect_action) == ("modify_trait", "remove")
    assert meta.retired is False
