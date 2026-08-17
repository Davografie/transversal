"""Tests for post-roll consequence menu assembly."""

from types import SimpleNamespace

from transversal.domain import (
    ConsequenceOption,
    Effect,
    EffectTiming,
    Entity,
    EntityType,
    SFX,
)
from transversal.services.consequence_menu import assemble_consequence_menu


class MenuRepo:
    def __init__(self):
        self.trait_settings = []      # SimpleNamespace(sfx_ids=[], trait_id=...)
        self.traits = {}              # trait_id -> SimpleNamespace(default_sfx_ids=[...])
        self.locations = {}           # loc_id -> Entity
        self.ancestors = {}           # loc_id -> [parent, grandparent, ...]
        self.sfxs = {}                # sfx_id -> SFX

    def get_traitsettings_for_entity(self, entity_id):
        return self.trait_settings

    def get_trait(self, trait_id):
        return self.traits.get(trait_id)

    def get_location_ancestors(self, location_id):
        return self.ancestors.get(location_id, [])

    def get_entity(self, entity_id):
        return self.locations.get(entity_id)

    def get_sfx(self, sfx_id):
        return self.sfxs.get(sfx_id)


def _entity(**overrides):
    kwargs = dict(id="char-1", type=EntityType.CHARACTER, name="Kael", current_universe="earth")
    kwargs.update(overrides)
    return Entity(**kwargs)


def _loc(id, options=None):
    return Entity(id=id, type=EntityType.LOCATION, name=id, current_universe="earth",
                  consequence_options=options or [])


def _option(id, side="player", label=None):
    return ConsequenceOption(id=id, label=label or id, side=side, source="entity")


def _labels(options):
    return [o.label for o in options]


def test_player_side_returns_base_player_options():
    out = assemble_consequence_menu(_entity(), MenuRepo(), "player")
    labels = _labels(out)
    assert "Proceed the narrative" in labels
    assert "Create a scene trait" in labels
    assert "Decrease the doom pool" in labels


def test_gm_side_returns_base_gm_options():
    out = assemble_consequence_menu(_entity(), MenuRepo(), "gm")
    labels = _labels(out)
    assert "Increase the doom pool" in labels
    assert "Apply a complication" in labels
    assert "Give a GMC an asset" in labels


def test_location_and_ancestor_options_are_included():
    repo = MenuRepo()
    repo.locations = {
        "railyard": _loc("railyard", [_option("geysers", "gm", "The geysers erupt")]),
        "krasnoyarsk": _loc("krasnoyarsk", [_option("fog", "either", "Heavy fog rolls in")]),
    }
    repo.ancestors = {"railyard": ["krasnoyarsk"]}
    entity = _entity(current_location="railyard")

    gm = assemble_consequence_menu(entity, repo, "gm")
    assert "The geysers erupt" in _labels(gm)
    assert "Heavy fog rolls in" in _labels(gm)

    player = assemble_consequence_menu(entity, repo, "player")
    assert "The geysers erupt" not in _labels(player)  # gm-only
    assert "Heavy fog rolls in" in _labels(player)      # either


def test_on_consequence_sfx_becomes_player_option():
    repo = MenuRepo()
    repo.trait_settings = [SimpleNamespace(sfx_ids=["sfx-flashback"], trait_id="origin")]
    repo.traits = {"origin": SimpleNamespace(default_sfx_ids=[])}
    repo.sfxs = {
        "sfx-flashback": SFX(id="sfx-flashback", name="Flashback", trigger="on_consequence",
                             effects=[Effect(timing=EffectTiming.IMMEDIATE, type="transfer_razmerit",
                                             action="earn", target="self", result="1")]),
    }
    out = assemble_consequence_menu(_entity(), repo, "player")
    options = {o.label: o for o in out}
    assert "Flashback" in options
    assert options["Flashback"].source == "sfx"
    assert options["Flashback"].effects[0].type == "transfer_razmerit"


def test_non_on_consequence_sfx_is_ignored():
    repo = MenuRepo()
    repo.trait_settings = [SimpleNamespace(sfx_ids=["sfx-other"], trait_id="origin")]
    repo.traits = {"origin": SimpleNamespace(default_sfx_ids=[])}
    repo.sfxs = {"sfx-other": SFX(id="sfx-other", name="Other", trigger="on_roll", effects=[])}
    out = assemble_consequence_menu(_entity(), repo, "player")
    assert "Other" not in _labels(out)


def test_base_moves_carry_effect_die_placeholder():
    repo = MenuRepo()
    player = {o.id: o for o in assemble_consequence_menu(_entity(), repo, "player")}
    assert player["create_scene_trait"].effects[0].result == "{effect_die}"

    gm = {o.id: o for o in assemble_consequence_menu(_entity(), repo, "gm")}
    assert gm["apply_complication"].effects[0].result == "{effect_die}"
    assert gm["give_asset"].effects[0].result == "{effect_die}"
