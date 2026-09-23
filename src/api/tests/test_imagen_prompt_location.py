"""Location prompts: sub-locations are restored, ancestors are opt-in.

The original Transversal app described a location's sub-locations ("zones") in
its image prompt and could also nest its ancestor chain ("located in …"). v2
dropped both. Sub-locations are restored unconditionally; the ancestor chain is
per-location (`Entity.prompt_include_ancestors`) because surrounding geography
helps an exterior and only adds noise to an interior.

`EntityRepository` is stubbed: these tests are about prompt assembly, not
database access.
"""

import pytest

from transversal.domain import Entity, EntityType, TraitSetting
from transversal.imagen import prompt_builder

UNIVERSE = "test_universe"  # not in UNIVERSE_STYLE_GUIDE, so no style clause


class _StubTrait:
    def __init__(self, name: str):
        self.name = name


class _StubRepository:
    """Only the lookups the location context needs."""

    def __init__(self, traits: dict, children: list, ancestors: list, entities: dict):
        self._traits = traits              # trait_id -> trait name
        self._children = children          # navigate_from()["children"]
        self._ancestors = ancestors        # get_location_ancestors()
        self._entities = entities          # _key -> Entity
        self._appearance_by_entity = {}    # entity_id -> list[TraitSetting]

    def get_trait(self, trait_id):
        name = self._traits.get(trait_id)
        return _StubTrait(name) if name else None

    def navigate_from(self, location_id):
        return {"children": self._children}

    def get_location_ancestors(self, location_id):
        return self._ancestors

    def get_entity(self, entity_id):
        return self._entities.get(entity_id)

    def get_prompt_traitsettings(self, entity_id, universes, projection_id=None):
        return self._appearance_by_entity.get(entity_id, [])


def _location(key: str, name: str) -> Entity:
    return Entity(id=key, type=EntityType.LOCATION, name=name, current_universe=UNIVERSE)


def _appearance(statement: str = "", notes: str = "", owner: str = "x") -> TraitSetting:
    return TraitSetting(
        id=f"ts-{owner}",
        entity_id=owner,
        trait_id="t-appearance",
        traitset_id="set1",
        statement=statement,
        notes=notes,
    )


def _repo(**overrides) -> _StubRepository:
    traits = {"t-appearance": "appearance"}
    children = [
        {"_key": "c1", "name": "Glade"},
        {"_key": "c2", "name": "Spring"},
    ]
    ancestors = ["a1", "a2"]
    entities = {
        "a1": _location("a1", "Wilderness"),
        "a2": _location("a2", "Verdant Dominion"),
    }
    repo = _StubRepository(traits, children, ancestors, entities)
    repo._appearance_by_entity = {
        "c1": [_appearance(notes="sunlit clearing", owner="c1")],
        "a1": [_appearance(notes="dense woods", owner="a1")],
    }
    for key, value in overrides.items():
        setattr(repo, key, value)
    return repo


def _prompt(repo, entity, include_ancestors=False):
    entity.prompt_include_ancestors = include_ancestors
    context = prompt_builder._build_location_context(repo, entity, [UNIVERSE])
    return prompt_builder._build_entity_prompt(entity, [], UNIVERSE, context)[0]


def test_location_intro_has_no_aerial_view():
    repo = _repo()
    prompt = _prompt(repo, _location("loc1", "Whispering Forest"))

    assert "seen from above" not in prompt
    assert prompt.startswith(
        "(location background image, a humanless atmospheric image focusing on "
        "Whispering Forest:1.2), "
    )


def test_sub_locations_use_the_zones_phrasing_with_uniform_weights():
    repo = _repo()
    prompt = _prompt(repo, _location("loc1", "Whispering Forest"))

    assert (
        "the different zones in Whispering Forest are "
        "((Glade, sunlit clearing:0.4) and (Spring:0.4)):0.8),"
    ) in prompt


def test_sub_locations_are_included_without_opting_in():
    """Only the ancestor chain is optional — zones are always described."""
    repo = _repo()
    prompt = _prompt(repo, _location("loc1", "Whispering Forest"), include_ancestors=False)

    assert "the different zones" in prompt


def test_ancestors_are_omitted_when_not_opted_in():
    repo = _repo()
    prompt = _prompt(repo, _location("loc1", "Whispering Forest"), include_ancestors=False)

    assert "located" not in prompt
    assert "Wilderness" not in prompt


def test_ancestors_nest_with_decaying_weights_when_opted_in():
    repo = _repo()
    prompt = _prompt(repo, _location("loc1", "Whispering Forest"), include_ancestors=True)

    assert (
        ", located in (Wilderness, dense woods in (Verdant Dominion:0.36):0.6)" in prompt
    )


def test_zones_and_ancestors_join_with_a_single_separator():
    """Both parts present: no doubled comma, and the clauses don't run together."""
    repo = _repo()
    prompt = _prompt(repo, _location("loc1", "Whispering Forest"), include_ancestors=True)

    assert ":0.8), located in (Wilderness" in prompt
    assert ", ," not in prompt


def test_non_location_ancestors_are_skipped():
    """A `super` parent may not be a place — live data has one under a character."""
    repo = _repo()
    repo._entities["a2"] = Entity(
        id="a2", type=EntityType.CHARACTER, name="Somebody", current_universe=UNIVERSE
    )
    prompt = _prompt(repo, _location("loc1", "Whispering Forest"), include_ancestors=True)

    assert "Wilderness" in prompt
    assert "Somebody" not in prompt


def test_location_without_children_or_ancestors_gets_no_context_clause():
    repo = _repo(_children=[], _ancestors=[])
    prompt = _prompt(repo, _location("loc1", "Empty Room"))

    # The assembled prompt collapses whitespace, so the intro's trailing ", "
    # is gone when nothing follows it.
    assert prompt == (
        "(location background image, a humanless atmospheric image focusing on "
        "Empty Room:1.2),"
    )


def test_child_appearance_carries_statement_and_notes():
    repo = _repo()
    repo._appearance_by_entity["c1"] = [
        _appearance(statement="cramped", notes="a low stone cellar", owner="c1")
    ]
    prompt = _prompt(repo, _location("loc1", "Whispering Forest"))

    assert "((Glade, cramped, a low stone cellar:0.4)" in prompt
