"""Tests for the lazy legacy-target → spec translator."""

from transversal.services.target_spec import LiteralStep, SelectStep, TargetSpec
from transversal.services.target_legacy import from_legacy_target


def test_empty_target_is_empty_spec():
    spec = from_legacy_target("", "trait")
    assert spec == TargetSpec(steps=[])


def test_self_maps_to_select_self():
    spec = from_legacy_target("self", "entity")
    assert spec.steps == [SelectStep(collection="self")]


def test_literal_id_maps_to_literal_step():
    spec = from_legacy_target("trait-environmental-hazard-58be", "trait")
    assert spec.steps == [LiteralStep(element="trait", value="trait-environmental-hazard-58be")]


def test_choose_location_maps_to_select_locations():
    spec = from_legacy_target("{choose:location}", "location")
    assert spec.steps == [SelectStep(collection="locations")]


def test_random_occupant_maps_to_select_occupants():
    spec = from_legacy_target("{random_occupant}", "occupant")
    assert spec.steps == [SelectStep(collection="occupants")]


def test_variable_target_is_unmappable():
    # {effect_die} is a variable, not a target — leave legacy.
    assert from_legacy_target("{effect_die}", "die") is None


def test_unmappable_kind_returns_none():
    # life_path/roll_table have no element type in the catalog.
    assert from_legacy_target("lp-123", "life_path") is None


def test_choose_trait_without_collection_returns_none():
    # No "all traits" collection yet — leave legacy for the author to fix.
    assert from_legacy_target("{choose:trait}", "trait") is None
