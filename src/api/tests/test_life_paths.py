"""Tests for life path domain models and discovery service."""

import pytest

from transversal.domain import (
    DieType,
    DiscoveryBlock,
    Enrollment,
    Entity,
    EntityType,
    LifePath,
    PendingTerm,
    Trait,
    TraitSet,
    TraitSetting,
)


# ── Domain Model Tests ──────────────────────────────────


class TestDiscoveryBlock:
    def test_empty_block_all_conditions_false(self):
        d = DiscoveryBlock()
        assert d.at_location == []
        assert d.knows_entity == []
        assert d.possesses_trait == []
        assert d.has_trait_rating == {}
        assert d.has_relationship == []

    def test_single_location_condition(self):
        d = DiscoveryBlock(at_location=["loc-valley"])
        assert d.at_location == ["loc-valley"]

    def test_multiple_conditions(self):
        d = DiscoveryBlock(
            at_location=["loc-valley"],
            knows_entity=["gmc-elder"],
            possesses_trait=["trait-jian"],
            has_trait_rating={"trait-cultivation": DieType.D10},
            has_relationship=["faction-sect"],
        )
        assert len(d.at_location) == 1
        assert len(d.knows_entity) == 1
        assert len(d.possesses_trait) == 1
        assert d.has_trait_rating["trait-cultivation"] == DieType.D10
        assert len(d.has_relationship) == 1


class TestLifePath:
    def test_minimal_life_path(self):
        lp = LifePath(
            id="lp-test",
            name="Test Path",
            universe="earth",
        )
        assert lp.id == "lp-test"
        assert lp.entry_table_id == ""
        assert lp.discovery is None

    def test_life_path_with_entry_and_discovery(self):
        lp = LifePath(
            id="lp-verdant",
            name="Verdant Steps",
            universe="three_realms",
            description="The safe cultivation path",
            entry_table_id="tbl-verdant-qualification",
            discovery=DiscoveryBlock(at_location=["loc-valley"]),
        )
        assert lp.entry_table_id == "tbl-verdant-qualification"
        assert lp.discovery.at_location == ["loc-valley"]


class TestEntityLifePathFields:
    def test_defaults(self):
        e = Entity(
            id="kael-1",
            type=EntityType.CHARACTER,
            name="Kael",
            current_universe="earth",
        )
        assert e.life_paths == []
        assert e.discovered_life_paths == []
        assert e.pending_term is None

    def test_with_enrollments(self):
        e = Entity(
            id="kael-1",
            type=EntityType.CHARACTER,
            name="Kael",
            current_universe="earth",
            discovered_life_paths=["lp-drifter", "lp-verdant", "lp-secret"],
            life_paths=[
                Enrollment(faction_id="fac-1", path_id="lp-verdant", mustered=True),
                Enrollment(faction_id="fac-2", path_id="lp-drifter"),
            ],
        )
        assert len(e.life_paths) == 2
        assert e.life_paths[0].mustered is True
        assert e.life_paths[1].mustered is False
        assert len(e.discovered_life_paths) == 3


class TestTraitSettingProvenance:
    def test_default_no_provenance(self):
        ts = TraitSetting(
            id="kael:hacking",
            entity_id="kael-1",
            trait_id="trait-hacking",
            traitset_id="ts-skills",
            dice=[DieType.D8],
        )
        assert ts.source_type is None
        assert ts.source_entity_id is None
        assert ts.source_trait_setting_id is None
        assert ts.source_life_path_id is None
        assert ts.source_term_number is None

    def test_taught_provenance(self):
        ts = TraitSetting(
            id="kael:hacking",
            entity_id="kael-1",
            trait_id="trait-hacking",
            traitset_id="ts-skills",
            dice=[DieType.D6],
            source_type="taught",
            source_entity_id="mira-1",
            source_trait_setting_id="mira:hacking",
        )
        assert ts.source_type == "taught"
        assert ts.source_entity_id == "mira-1"

    def test_life_path_provenance(self):
        ts = TraitSetting(
            id="kael:qi-reserves",
            entity_id="kael-1",
            trait_id="trait-qi-reserves",
            traitset_id="ts-cultivation",
            dice=[DieType.D4, DieType.D4],
            source_type="life_path_term",
            source_life_path_id="lp-verdant",
            source_term_number=2,
        )
        assert ts.source_type == "life_path_term"
        assert ts.source_life_path_id == "lp-verdant"
        assert ts.source_term_number == 2

    def test_taken_provenance(self):
        ts = TraitSetting(
            id="kael:jian",
            entity_id="kael-1",
            trait_id="trait-jian",
            traitset_id="ts-assets",
            dice=[DieType.D12],
            source_type="taken",
            source_entity_id="yuan-1",
        )
        assert ts.source_type == "taken"
        assert ts.source_entity_id == "yuan-1"
