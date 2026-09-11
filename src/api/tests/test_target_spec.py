"""Tests for the target spec type-checker."""

from pydantic import ValidationError

from transversal.services.target_spec import (
    AggregateStep,
    ChooseStep,
    FilterStep,
    NavigateStep,
    RandomStep,
    SelectStep,
    TargetSpec,
    TopStep,
    ValueType,
    check,
    final_type,
    trace,
)


def spec(*steps):
    return TargetSpec(steps=list(steps))


def test_select_rolled_dice_is_many_die():
    types, errors = trace(spec(SelectStep(collection="rolled_dice")))
    assert errors == []
    assert types[-1] == ValueType("die", "many")


def test_select_self_is_one_entity():
    types, errors = trace(spec(SelectStep(collection="self")))
    assert errors == []
    assert types[-1] == ValueType("entity", "one")


def test_select_variable_uses_declared_element():
    types, errors = trace(spec(SelectStep(collection="variable", variable="complication")), variables={"complication": "traitsetting"})
    assert errors == []
    assert types[-1] == ValueType("traitsetting", "one")


def test_select_unknown_variable_is_an_error():
    types, errors = trace(spec(SelectStep(collection="variable", variable="nope")), variables={"complication": "traitsetting"})
    assert errors and "unknown variable" in errors[0].message


def test_step_output_is_visible_to_later_steps():
    s = spec(
        SelectStep(collection="self", output="who"),
        SelectStep(collection="variable", variable="who"),
    )
    types, errors = trace(s)
    assert errors == []
    assert types[-1] == ValueType("entity", "one")


def test_spec_variables_collects_step_outputs():
    from transversal.services.target_spec import spec_variables
    s = spec(
        SelectStep(collection="self", output="who"),
        NavigateStep(edge="location", output="where"),
    )
    scope = spec_variables(s)
    assert {k: v.element for k, v in scope.items()} == {"who": "entity", "where": "location"}
    assert all(v.cardinality == "one" for v in scope.values())


def test_spec_variables_preserves_cardinality():
    from transversal.services.target_spec import spec_variables
    s = spec(SelectStep(collection="rolled_dice", output="friends"))
    scope = spec_variables(s)
    assert scope["friends"] == ValueType("die", "many")


def test_select_variable_type_checks_as_many():
    # A later effect re-uses a many-valued output as a many collection.
    types, errors = trace(
        spec(SelectStep(collection="variable", variable="friends")),
        variables={"friends": ValueType("entity", "many")},
    )
    assert errors == []
    assert types[-1] == ValueType("entity", "many")


def test_filter_does_not_change_type():
    s = spec(SelectStep(collection="rolled_dice"), FilterStep(field="source_kind", value="trait"))
    types, errors = trace(s)
    assert errors == []
    assert types[-1] == ValueType("die", "many")


def test_navigate_many_to_one_is_still_many():
    # many dice → one traitsetting each → still a set
    s = spec(SelectStep(collection="rolled_dice"), NavigateStep(edge="traitsetting"))
    types, errors = trace(s)
    assert errors == []
    assert types[-1] == ValueType("traitsetting", "many")


def test_navigate_one_to_many_is_many():
    # one entity → many projections
    s = spec(SelectStep(collection="self"), NavigateStep(edge="projections"))
    types, errors = trace(s)
    assert errors == []
    assert types[-1] == ValueType("projection", "many")


def test_aggregate_count_collapses_to_int():
    s = spec(SelectStep(collection="rolled_dice"), AggregateStep(fn="count"))
    types, errors = trace(s)
    assert errors == []
    assert types[-1] == ValueType("int", "one")


def test_aggregate_min_needs_field():
    s = spec(SelectStep(collection="rolled_dice"), AggregateStep(fn="min"))
    types, errors = trace(s)
    assert any("needs a field" in e.message for e in errors)


def test_aggregate_min_over_die_result():
    s = spec(SelectStep(collection="rolled_dice"), AggregateStep(fn="min", field="result"))
    types, errors = trace(s)
    assert errors == []
    assert types[-1] == ValueType("int", "one")


def test_one_trick_path_type_checks():
    s = spec(
        SelectStep(collection="rolled_dice"),
        FilterStep(field="source_kind", value="trait"),
        NavigateStep(edge="traitsetting", dedup=True),
    )
    assert final_type(s) == ValueType("traitsetting", "many")
    ok, errors = check(s, ValueType("traitsetting", "many"))
    assert ok, errors


def test_example_path_reaches_entities():
    # GMCs that used traits from set X: dice → their owning entity (via owner),
    # and dice → traitsetting → (filter traitset_id) → owning entity.
    s = spec(
        SelectStep(collection="rolled_dice"),
        FilterStep(field="source_kind", value="trait"),
        NavigateStep(edge="owner"),
        FilterStep(field="type", value="gmc"),
        NavigateStep(edge="traitsetting"),
        FilterStep(field="traitset_id", value="X"),
        NavigateStep(edge="entity", dedup=True),
    )
    # (note: this spec navigates owner then traitsetting from the *entity*,
    # which the catalog allows entity→traitsettings, not entity→traitsetting;
    # see test below for the corrected shape)
    types, errors = trace(s)
    assert errors != []  # entity has no "traitsetting" edge — good, caught


def test_example_path_correct_shape():
    # The intended shape: dice → traitsetting (filter traitset) → entity.
    s = spec(
        SelectStep(collection="rolled_dice"),
        FilterStep(field="source_kind", value="trait"),
        NavigateStep(edge="traitsetting"),
        FilterStep(field="traitset_id", value="X"),
        NavigateStep(edge="entity", dedup=True),
    )
    assert final_type(s) == ValueType("entity", "many")
    ok, errors = check(s, ValueType("entity", "many"))
    assert ok, errors


def test_unknown_edge_is_an_error():
    types, errors = trace(spec(SelectStep(collection="rolled_dice"), NavigateStep(edge="nope")))
    assert any("no edge die.nope" in e.message for e in errors)
    assert types[-1] is None


def test_unknown_field_is_an_error():
    types, errors = trace(spec(SelectStep(collection="rolled_dice"), FilterStep(field="nope")))
    assert any("unknown field die.nope" in e.message for e in errors)


def test_check_rejects_cardinality_mismatch():
    s = spec(SelectStep(collection="rolled_dice"), NavigateStep(edge="traitsetting"))
    ok, errors = check(s, ValueType("traitsetting", "one"))
    assert not ok
    assert any("not traitsetting/one" in e.message for e in errors)


def test_spec_deserializes_from_dicts():
    s = TargetSpec.model_validate({
        "steps": [
            {"kind": "select", "collection": "rolled_dice"},
            {"kind": "filter", "field": "source_kind", "operator": "==", "value": "trait"},
            {"kind": "navigate", "edge": "traitsetting", "dedup": True},
        ]
    })
    assert isinstance(s.steps[0], SelectStep)
    assert isinstance(s.steps[1], FilterStep)
    assert isinstance(s.steps[2], NavigateStep)
    assert final_type(s) == ValueType("traitsetting", "many")


def test_invalid_kind_is_rejected():
    try:
        TargetSpec.model_validate({"steps": [{"kind": "wat"}]})
        assert False, "expected ValidationError"
    except ValidationError:
        pass


def test_contains_operator_type_checks():
    s = spec(
        SelectStep(collection="rolled_dice"),
        FilterStep(field="armed_sfx_ids", operator="contains", value="sfx-a"),
    )
    types, errors = trace(s)
    assert errors == []
    assert types[-1] == ValueType("die", "many")


def test_literal_step_type_checks_to_one():
    from transversal.services.target_spec import LiteralStep
    s = spec(LiteralStep(element="trait", value="trait-x"))
    types, errors = trace(s)
    assert errors == []
    assert types[-1] == ValueType("trait", "one")


def test_literal_step_unknown_element_is_error():
    from transversal.services.target_spec import LiteralStep
    types, errors = trace(spec(LiteralStep(element="nope", value="x")))
    assert any("unknown literal element" in e.message for e in errors)
    assert types[-1] is None


def test_literal_step_deserializes_from_dict():
    s = TargetSpec.model_validate({"steps": [{"kind": "literal", "element": "trait", "value": "trait-x"}]})
    from transversal.services.target_spec import LiteralStep
    assert isinstance(s.steps[0], LiteralStep)
    assert final_type(s) == ValueType("trait", "one")


def test_select_source_requires_source_kind():
    from transversal.services.target_spec import SelectStep, TargetSpec, trace

    spec = TargetSpec(steps=[SelectStep(collection="source")])
    _, errors = trace(spec)
    assert any("requires a declared source_kind" in e.message for e in errors)


def test_select_source_types_by_source_kind():
    from transversal.services.target_spec import SelectStep, TargetSpec, trace

    spec = TargetSpec(steps=[SelectStep(collection="source")])
    types, errors = trace(spec, source_element="traitsetting")
    assert errors == []
    assert types[-1].element == "traitsetting"
    assert types[-1].cardinality == "one"


def test_select_source_navigates_from_source_element():
    from transversal.services.target_spec import NavigateStep, SelectStep, TargetSpec, check, ValueType

    # source = traitsetting → navigate to its owning entity.
    spec = TargetSpec(steps=[
        SelectStep(collection="source"),
        NavigateStep(edge="entity"),
    ])
    ok, errors = check(spec, ValueType("entity", "one"), source_element="traitsetting")
    assert ok, errors


def test_random_collapses_many_to_one():
    s = spec(SelectStep(collection="rolled_dice"), RandomStep())
    types, errors = trace(s)
    assert errors == []
    assert types[-1] == ValueType("die", "one")


def test_random_count_many_keeps_many():
    s = spec(SelectStep(collection="rolled_dice"), RandomStep(count=3))
    types, errors = trace(s)
    assert errors == []
    assert types[-1] == ValueType("die", "many")


def test_random_requires_many_collection():
    s = spec(SelectStep(collection="self"), RandomStep())
    types, errors = trace(s)
    assert any("many-cardinality" in e.message for e in errors)


def test_random_count_must_be_positive():
    s = spec(SelectStep(collection="rolled_dice"), RandomStep(count=0))
    types, errors = trace(s)
    assert any("count must be >= 1" in e.message for e in errors)


def test_random_deserializes_from_dict():
    s = TargetSpec.model_validate({"steps": [
        {"kind": "select", "collection": "rolled_dice"},
        {"kind": "random", "count": 2},
    ]})
    assert isinstance(s.steps[1], RandomStep)
    assert final_type(s) == ValueType("die", "many")


def test_choose_collapses_many_to_one():
    s = spec(SelectStep(collection="rolled_dice"), ChooseStep())
    types, errors = trace(s)
    assert errors == []
    assert types[-1] == ValueType("die", "one")


def test_choose_count_many_keeps_many():
    s = spec(SelectStep(collection="rolled_dice"), ChooseStep(count=3))
    types, errors = trace(s)
    assert errors == []
    assert types[-1] == ValueType("die", "many")


def test_choose_requires_many_collection():
    s = spec(SelectStep(collection="self"), ChooseStep())
    types, errors = trace(s)
    assert any("many-cardinality" in e.message for e in errors)


def test_choose_count_must_be_positive():
    s = spec(SelectStep(collection="rolled_dice"), ChooseStep(count=0))
    types, errors = trace(s)
    assert any("count must be >= 1" in e.message for e in errors)


def test_choose_may_be_mid_path():
    # Terminal choose is the common case, but the grammar allows a suffix;
    # the type-checker must keep tracing past the collapse.
    s = spec(
        SelectStep(collection="rolled_dice"),
        ChooseStep(),
        NavigateStep(edge="traitsetting"),
    )
    types, errors = trace(s)
    assert errors == []
    assert types[-1] == ValueType("traitsetting", "one")


def test_choose_deserializes_from_dict():
    s = TargetSpec.model_validate({"steps": [
        {"kind": "select", "collection": "rolled_dice"},
        {"kind": "choose", "count": 2},
    ]})
    assert isinstance(s.steps[1], ChooseStep)
    assert final_type(s) == ValueType("die", "many")


# ── top (the ordering step) ──────────────────────────

def test_top_collapses_to_one_by_a_timestamp():
    s = spec(SelectStep(collection="self"), NavigateStep(edge="projections"),
             TopStep(field="last_used_at"))
    types, errors = trace(s)
    assert errors == []
    assert types[-1] == ValueType("projection", "one")


def test_top_rejects_an_unorderable_field():
    """A plain string has no ordering — the catalog's operators say so."""
    s = spec(SelectStep(collection="self"), NavigateStep(edge="projections"),
             TopStep(field="universe"))
    _types, errors = trace(s)
    assert any("cannot be ordered" in e.message for e in errors)


def test_top_rejects_an_unknown_field():
    s = spec(SelectStep(collection="self"), NavigateStep(edge="projections"),
             TopStep(field="nope"))
    _types, errors = trace(s)
    assert any("unknown field" in e.message for e in errors)


def test_top_needs_a_collection():
    s = spec(SelectStep(collection="self"), TopStep(field="last_used_at"))
    _types, errors = trace(s)
    assert any("requires a many-cardinality collection" in e.message for e in errors)


def test_top_exposes_its_output():
    from transversal.services.target_spec import spec_variables
    s = spec(SelectStep(collection="self"), NavigateStep(edge="projections"),
             TopStep(field="last_used_at", output="most_recent"))
    assert spec_variables(s)["most_recent"] == ValueType("projection", "one")


def test_top_deserializes_from_dict_defaulting_to_desc():
    s = TargetSpec.model_validate({"steps": [
        {"kind": "select", "collection": "self"},
        {"kind": "navigate", "edge": "projections"},
        {"kind": "top", "field": "last_used_at"},
    ]})
    assert isinstance(s.steps[2], TopStep)
    assert s.steps[2].direction == "desc"


def test_a_type_filter_enables_the_narrower_elements_edges():
    """The Formation path: an SFX on a trait → its owning entity → proven to be a
    location → that location's occupants → their trait instances."""
    from transversal.services.target_spec import FilterStep, NavigateStep, SelectStep

    def path(*narrow):
        return TargetSpec(steps=list(narrow))

    base = [
        SelectStep(collection="source"),
        NavigateStep(edge="entity"),
    ]
    # Without the proof, `occupants` is not an entity edge.
    types, errors = trace(TargetSpec(steps=base + [NavigateStep(edge="occupants")]),
                          source_element="traitsetting")
    assert errors, "entity has no occupants edge — this must fail before narrowing"

    proven = TargetSpec(steps=base + [
        FilterStep(field="type", operator="==", value="location"),
        NavigateStep(edge="occupants"),
        NavigateStep(edge="traitsettings"),
    ])
    types, errors = trace(proven, source_element="traitsetting")
    assert errors == []
    final = final_type(proven, source_element="traitsetting")
    assert (final.element, final.cardinality) == ("traitsetting", "many")


def test_a_place_source_can_walk_straight_to_its_occupants():
    """The payoff of a `location` source: a rule attached to the sect resolves the
    *place* as its source, so its path reaches the people inside without the
    trait-setting → entity → cast dance."""
    from transversal.services.target_spec import FilterStep, NavigateStep, SelectStep

    spec = TargetSpec(steps=[
        SelectStep(collection="source"),
        NavigateStep(edge="occupants"),
        NavigateStep(edge="traitsettings"),
        FilterStep(field="trait_id", operator="==", value="trait-movement"),
    ])
    types, errors = trace(spec, source_element="location")
    assert errors == []
    final = final_type(spec, source_element="location")
    assert (final.element, final.cardinality) == ("traitsetting", "many")

    # The same path from an `entity` source is unavailable — this is the gap the
    # kind closes (an entity is not known to be a place).
    _types, entity_errors = trace(spec, source_element="entity")
    assert entity_errors, "an entity source must not silently reach occupants"
