"""Where an occupant is, in its own prompt (GMC + asset, not characters).

v1 gave npc and asset prompts the containing location and its ancestors
("located in …", decaying 0.6 per level); v2 dropped it. Restored here, gated by
the entity's own ``prompt_include_ancestors`` toggle — the same **Surroundings**
checkbox locations use.

Deliberately excluded: **characters** (a PC is generated wherever the player
wants, not pinned to where the soul currently sits) and **sub-locations** (those
describe what a place contains, which is right for a location's own backdrop and
wrong for someone standing in it).

Note there is still **no cutoff**: with the toggle on the whole chain to the root
is included. A passage under a dungeon under a theme park gets all three.
"""

import pytest

from transversal.domain import Entity, EntityType
from transversal.domain.traits import TraitSetting
from transversal.imagen import prompt_builder

UNIVERSE = "test_universe"

PASSAGE = "loc-passage"
DUNGEON = "loc-dungeon"
THEME_PARK = "loc-theme-park"


class _StubTrait:
    def __init__(self, name):
        self.name = name


class _StubProjection:
    def __init__(self, current_location):
        self.current_location = current_location
        self.universe = UNIVERSE
        self.origin_universe = UNIVERSE


class _StubRepository:
    def __init__(self, places, ancestors, appearances=None, projection_location=None):
        self._places = places                  # key -> Entity
        self._ancestors = ancestors            # location_id -> [ancestor ids]
        self._appearances = appearances or {}  # key -> list[TraitSetting]
        self._projection_location = projection_location

    def get_trait(self, trait_id):
        return _StubTrait("appearance") if trait_id == "t-appearance" else None

    def get_entity(self, entity_id):
        return self._places.get(entity_id)

    def get_location_ancestors(self, location_id):
        return self._ancestors.get(location_id, [])

    def get_projection(self, projection_id):
        return _StubProjection(self._projection_location)

    def get_prompt_traitsettings(self, entity_id, universes, projection_id=None):
        return self._appearances.get(entity_id, [])


def _place(key, name):
    return Entity(id=key, type=EntityType.LOCATION, name=name, current_universe=UNIVERSE)


def _appearance(text):
    return TraitSetting(
        id=f"ts-{text}", entity_id="x", trait_id="t-appearance",
        traitset_id="set1", notes=text,
    )


def _repo():
    return _StubRepository(
        places={
            PASSAGE: _place(PASSAGE, "The Passage"),
            DUNGEON: _place(DUNGEON, "The Dungeon"),
            THEME_PARK: _place(THEME_PARK, "Disneyland"),
        },
        # get_location_ancestors returns the WHOLE chain, nearest first.
        ancestors={PASSAGE: [DUNGEON, THEME_PARK], DUNGEON: [THEME_PARK], THEME_PARK: []},
        appearances={
            PASSAGE: [_appearance("a narrow torchlit corridor")],
            DUNGEON: [_appearance("endless corridors, iron doors")],
            THEME_PARK: [_appearance("a castle, fireworks")],
        },
    )


def _occupant(entity_type=EntityType.GMC, include=False, location=PASSAGE, projection=None):
    return Entity(
        id="e1",
        type=entity_type,
        name="Grukk",
        current_universe=UNIVERSE,
        current_location=location,
        current_projection=projection,
        prompt_include_ancestors=include,
    )


def _prompt(entity, repo=None, projection_id=None):
    repo = repo or _repo()
    return prompt_builder.build_imagen_prompt(entity, UNIVERSE, repo, projection_id)["prompt"]


def test_toggle_off_builds_the_same_prompt_as_before():
    prompt = _prompt(_occupant())

    assert "located" not in prompt
    assert prompt.startswith("(a solo upper body character portrait of Grukk:1.2),")


def test_toggle_on_describes_the_containing_location_and_its_ancestors():
    prompt = _prompt(_occupant(include=True))

    # Nearest first, 0.6 decay per level — v1's shape.
    assert "located in (The Passage, a narrow torchlit corridor" in prompt
    assert (
        "in (The Dungeon, endless corridors, iron doors "
        "in (Disneyland, a castle, fireworks:0.216):0.36):0.6" in prompt
    )


def test_the_whole_chain_is_included_there_is_no_cutoff():
    """Documents the current behaviour: the theme park is in there too.

    The dungeon cannot yet say "stop above me" — that boundary flag is not
    implemented, so a cut-off location gets its real ancestors regardless.
    """
    prompt = _prompt(_occupant(include=True))

    assert "Disneyland" in prompt


def test_place_appearances_come_along():
    prompt = _prompt(_occupant(include=True))

    assert "The Passage, a narrow torchlit corridor" in prompt
    assert "The Dungeon, endless corridors, iron doors" in prompt


def test_sub_locations_are_never_part_of_an_occupants_context():
    prompt = _prompt(_occupant(include=True))

    assert "the different zones" not in prompt


def test_the_projections_location_wins_over_the_entities():
    """A body can be somewhere its soul is not."""
    entity = _occupant(include=True, location=THEME_PARK, projection="e1:earth")
    repo = _repo()
    repo._projection_location = PASSAGE

    prompt = _prompt(entity, repo=repo)

    # The chain must *start* at the body's location. Asserting on the root, not
    # on Disneyland's absence — Disneyland is a genuine ancestor of the Passage.
    assert "located in (The Passage" in prompt
    assert "located in (Disneyland" not in prompt


def test_an_asset_gets_the_chain_too():
    """v1 covered npc *and* asset."""
    prompt = _prompt(_occupant(entity_type=EntityType.ASSET, include=True))

    assert "located in (The Passage" in prompt


def test_characters_are_excluded():
    """A player character is generated wherever the player wants."""
    prompt = _prompt(_occupant(entity_type=EntityType.CHARACTER, include=True))

    assert "located" not in prompt
    assert "Disneyland" not in prompt


def test_an_occupant_with_no_location_gets_no_clause():
    prompt = _prompt(_occupant(include=True, location=None))

    assert "located" not in prompt
