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
    assert names == ["rating_dice", "capacity_dice", "trait", "traitset", "entity",
                     "projection", "parent", "subtraits", "relationship"]


def test_the_sub_trait_edge_reaches_nested_instances():
    """A root hangs *from* the trait it is a facet of, so the only way a path
    reaches it is through its parent (`Spiritual Power → its elemental roots`).
    It is deliberately absent from `entity → traitsettings`, which filters the
    nested instances out. See [[Elements and Spiritual Roots]]."""
    e = tc.edge("traitsetting", "subtraits")
    assert e is not None
    assert e.target == ("traitsetting",)
    assert e.cardinality == "many"
    assert (e.noun, e.plural) == ("sub-trait", "sub-traits")


def test_a_pool_hop_reaches_its_dice():
    """The pool element used to be a dead end: you could reach *whose* pool, and
    stop. `pool → dice` is what lets a path walk into the dice assembled there."""
    e = tc.edge("pool", "dice")
    assert e is not None
    assert e.target == ("die",)
    assert e.cardinality == "many"
    assert (e.noun, e.plural) == ("die", "dice")


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


def test_the_opposing_dice_collection_is_declared():
    """The other side of a contest is a seed of its own, so a path can *start*
    there ("their metal against my fire") — not only be compared against."""
    c = tc.collection("opposing_dice")
    assert c is not None
    assert c.element == "die"
    assert (c.noun, c.plural) == ("die", "dice")
    assert c.origin == "in the opposing pool"


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
    assert tc.operators_for(tc.field("traitsetting", "rating_type")) == ("==", "!=", "in", "not in")


def test_id_reference_fields_declare_reference():
    assert tc.field("traitsetting", "traitset_id").references == "traitset"
    assert tc.field("traitsetting", "trait_id").references == "trait"
    assert tc.field("traitsetting", "entity_id").references == "entity"
    assert tc.field("traitsetting", "projection_id").references == "projection"
    assert tc.field("trait", "traitset_id").references == "traitset"
    # enum-like fields are not references
    assert tc.field("traitsetting", "polarity").references == ""


def test_source_kinds_are_declared_and_consistent():
    from transversal.services import target_catalog as tc

    assert {s.value for s in tc.SOURCE_KINDS} == {
        "trait_setting", "traitset_setting", "entity", "location", "projection", "faction",
        "table", "gm",
    }
    surfaces = {"trait_instance", "trait", "trait_set", "entity", "location", "projection", "table", "gm"}
    for s in tc.SOURCE_KINDS:
        assert s.owner_surfaces, s.value
        assert set(s.owner_surfaces) <= surfaces, s.value
        # Typed sources resolve to a catalog element; bucket sources (table/gm)
        # are non-resolving (empty element).
        if s.element:
            assert s.element in tc.ELEMENT_TYPES, s.value
        else:
            assert s.value in ("table", "gm")


def test_traitsetsetting_element_and_polarity_field_exist():
    from transversal.services import target_catalog as tc

    assert tc.element("traitsetsetting") is not None
    pol = tc.field("traitsetting", "polarity")
    assert pol is not None
    assert pol.options == ("positive", "negative")


def test_pool_element_and_edges_exist():
    from transversal.services import target_catalog as tc

    assert tc.element("pool") is not None
    pairs = {(e.source, e.name): e for e in tc.EDGES}
    assert ("entity", "pool") in pairs
    assert ("location", "difficulty_pool") in pairs
    assert pairs[("entity", "pool")].target == ("pool",)
    assert pairs[("location", "difficulty_pool")].target == ("pool",)


def test_a_trait_definition_reaches_its_instances():
    """A definition has no exposed surface, so nothing can own a rule on one.
    The hop down to the settings is what makes a registry-seeded reach selector
    writable ("all traits of the assets set", "all traits tagged utility") —
    [[Dynamic SFX Reach]]. Its card noun mirrors `entity → traitsettings`."""
    from transversal.services import target_catalog as tc

    pairs = {(e.source, e.name): e for e in tc.EDGES}
    edge = pairs[("trait", "traitsettings")]
    assert edge.target == ("traitsetting",)
    assert edge.cardinality == "many"
    assert tc.edge_noun(edge) == ("trait instance", "trait instances")


def test_bind_source_maps_kind_to_variable():
    from transversal.services import target_catalog as tc

    ctx = tc.bind_source("trait_setting", "char-1:martial", {})
    assert ctx == {"trait_setting": "char-1:martial"}

    # Preserves existing keys; unknown/unset kind or empty id is a no-op.
    assert tc.bind_source("trait_setting", "x", {"phase": "roll"}) == {"phase": "roll", "trait_setting": "x"}
    assert tc.bind_source("bogus", "x", {}) == {}
    assert tc.bind_source("trait_setting", None, {}) == {}
    assert tc.bind_source("trait_setting", "", {}) == {}


def test_trait_tags_are_matchable():
    """B116: a trait's free-form tags can be filtered on — on the registry trait
    and on a trait instance (which reads them through the trait it points at).
    A list, so it is matched with `contains`, never ordered."""
    for element_name in ("trait", "traitsetting"):
        f = tc.field(element_name, "tags")
        assert f is not None, element_name
        assert tc.operators_for(f) == ("contains", "==", "!=")
        assert not tc.is_orderable(f), element_name


def test_a_type_filter_narrows_the_element():
    """`entity.type == location` proves the value is a location, so a location-only
    hop (`occupants`) becomes legal after it — the author's Formation path."""
    assert tc.narrowed_element("entity", "type", "==", "location") == "location"
    assert tc.narrowed_element("entity", "type", "==", "universe") == "universe"

    # Proves nothing: inequality, a non-element type, an unknown field.
    assert tc.narrowed_element("entity", "type", "!=", "location") is None
    assert tc.narrowed_element("entity", "type", "==", "character") is None
    assert tc.narrowed_element("entity", "current_location", "==", "loc-1") is None
    assert tc.narrowed_element("traitsetting", "type", "==", "location") is None
    # A bound value's type is only known at run time.
    assert tc.narrowed_element("entity", "type", "==", "{chosen_type}") is None
    assert tc.narrowed_element("entity", "type", "==", 7) is None


def test_the_narrowing_map_only_points_at_real_elements():
    for target in tc.ELEMENT_NARROWING[("entity", "type")].values():
        assert tc.element(target) is not None, target


# ── B130: `enabled` and `order` on a trait instance ──────────

def test_a_trait_instance_exposes_enabled():
    """`enabled` is a real field on the instance, so a path can filter a landed
    portent out (or in) — something `HAS_EFFECTIVE_TRAIT` cannot do, because it
    matches by registry trait and returns the first instance's flag."""
    f = tc.field("traitsetting", "enabled")
    assert f is not None
    assert f.type == "boolean"
    assert tc.field_label(f) == "Enabled"
    # Equality/membership only: a boolean has no order, so an ordering step is
    # refused by the type-checker (and never offered by the wizard).
    assert tc.operators_for(f) == ("==", "!=", "in", "not in")
    assert not tc.is_orderable(f)


def test_a_trait_instance_exposes_order_as_an_ordered_int():
    f = tc.field("traitsetting", "order")
    assert f is not None
    assert f.type == "int"
    assert tc.field_label(f) == "Order"
    assert tc.is_orderable(f)
    # An int field can carry the whole ordering/aggregate family.
    names = [a.name for a in tc.aggregations_for(f.type)]
    for fn in ("min", "max", "top", "bottom", "mean"):
        assert fn in names, fn


# ── Fields a reach selector needs on a *definition* or a flag ──────

def test_a_hidden_entity_is_filterable():
    """Fog of war (B92). A rule *reaches* the hidden ones by filtering on the
    flag — "every hidden GMC" is a selector, not an attachment on each one."""
    f = tc.field("entity", "hidden")
    assert f is not None
    assert f.type == "boolean"
    assert "==" in tc.operators_for(f)


def test_a_traitset_limit_is_filterable():
    """The set's limit is an int, so `> 1` is sayable — "the sets that allow
    more than one" (deferred out of B228; the set exposed only id/name/universes)."""
    f = tc.field("traitset", "limit")
    assert f is not None
    assert f.type == "int"
    assert tc.is_orderable(f)
