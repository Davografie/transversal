"""Tests for the target spec type-checker."""

from pydantic import ValidationError

from transversal.services.target_spec import (
    AggregateStep,
    FilterStep,
    NavigateStep,
    RandomStep,
    SelectStep,
    TargetSpec,
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
