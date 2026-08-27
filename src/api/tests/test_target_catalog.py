"""Tests for the declarative targeting catalog."""

from transversal.services import target_catalog as tc


def test_catalog_is_internally_consistent():
    assert tc.validate() == []


def test_element_types_declared():
    for name in ("die", "traitsetting", "trait", "traitset", "entity", "projection", "location", "universe"):
        assert tc.element(name) is not None, name


def test_die_to_traitsetting_edge():
    e = tc.edge("die", "traitsetting")
    assert e is not None
    assert e.target == ("traitsetting",)
    assert e.cardinality == "one"


def test_die_edges():
    names = [e.name for e in tc.edges_from("die")]
    assert names == ["traitsetting", "owner"]


def test_traitsetting_edges():
    names = [e.name for e in tc.edges_from("traitsetting")]
    assert names == ["trait", "traitset", "entity", "projection"]


def test_one_trick_path_is_typed():
    # One Trick: select rolled_dice → navigate traitsetting → (target traitsetting).
    assert tc.collection("rolled_dice").element == "die"
    hop = tc.edge("die", "traitsetting")
    assert hop is not None and hop.target == ("traitsetting",)


def test_example_path_has_all_edges():
    # "GMCs that used traits from set X": die → owner (entity),
    # die → traitsetting → traitset (filter traitset == X).
    assert tc.edge("die", "owner").target == ("entity",)
    assert tc.edge("die", "traitsetting").target == ("traitsetting",)
    assert tc.edge("traitsetting", "traitset").target == ("traitset",)
    assert tc.edge("traitsetting", "entity").target == ("entity",)


def test_scalar_fields_for_dice():
    fields = {f.name: f for f in tc.fields_for("die")}
    assert fields["result"].type == "int"
    assert fields["rating"].type == "die"
    assert fields["effect_die"].type == "die"


def test_aggregations():
    assert tc.aggregation("count").output == "int"
    assert tc.aggregation("count").needs_field is False
    assert tc.aggregation("min").output == "same"
    assert tc.aggregation("min").needs_field is True
    assert tc.aggregation("mean").output == "number"


def test_collections_seed_types():
    assert tc.collection("self").singular is True
    assert tc.collection("self").element == "entity"
    assert tc.collection("rolled_dice").element == "die"
    assert tc.collection("self_traitsettings").element == "traitsetting"


def test_unknown_lookups_return_none():
    assert tc.element("nope") is None
    assert tc.edge("die", "nope") is None
    assert tc.field("die", "nope") is None
    assert tc.aggregation("nope") is None
    assert tc.collection("nope") is None


def test_operators_are_type_aware():
    assert ">" not in tc.operators_for(tc.field("die", "source_kind"))
    assert ">" in tc.operators_for(tc.field("die", "result"))
    assert tc.operators_for(tc.field("die", "armed_sfx_ids")) == ("contains", "==", "!=")
    assert tc.operators_for(tc.field("traitsetting", "rating_type")) == ("==", "!=", "in")
