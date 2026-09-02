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

    def get_effective_traitsettings(self, entity_id, universes):
        return self.trait_settings

    def get_effective_traitsetsettings(self, entity_id, universes):
        return getattr(self, "traitset_settings", [])

    def get_sfx_owner(self, owner_id):
        return getattr(self, "sfx_owners", {}).get(owner_id)

    def get_projection(self, projection_id):
        return getattr(self, "projections", {}).get(projection_id)

    def get_trait(self, trait_id):
        return self.traits.get(trait_id)

    def get_location_ancestors(self, location_id):
        return self.ancestors.get(location_id, [])

    def get_entity(self, entity_id):
        return self.locations.get(entity_id)

    def get_sfx(self, sfx_id):
        return self.sfxs.get(sfx_id)

    def create_sfx(self, sfx):
        self.sfxs[sfx.id] = sfx

    def update_sfx_owner(self, owner):
        self.sfx_owners[owner.id] = owner


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


def _base_move_repo():
    """A MenuRepo seeded with the placement=menu base moves (as SFX)."""
    from transversal.services.sfx_owner import ensure_base_move_sfxs

    repo = MenuRepo()
    repo.sfx_owners = {"table": SimpleNamespace(id="table", sfx_ids=[])}
    ensure_base_move_sfxs(repo)
    return repo


def test_player_side_returns_base_player_options():
    out = assemble_consequence_menu(_entity(), _base_move_repo(), "player")
    labels = _labels(out)
    assert "Proceed the narrative" in labels
    assert "Create a scene trait" in labels
    assert "Decrease the doom pool" in labels
    assert "Work on a project" in labels


def test_gm_side_returns_base_gm_options():
    out = assemble_consequence_menu(_entity(), _base_move_repo(), "gm")
    labels = _labels(out)
    assert "Increase the doom pool" in labels
    assert "Give a GMC an asset" in labels
    # Player moves are role-gated out of the GM menu.
    assert "Proceed the narrative" not in labels


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
    repo = _base_move_repo()
    player = {o.id: o for o in assemble_consequence_menu(_entity(), repo, "player")}
    assert player["sfx:create_scene_trait"].effects[0].result == "{effect_die}"

    gm = {o.id: o for o in assemble_consequence_menu(_entity(), repo, "gm")}
    assert gm["sfx:give_asset"].effects[0].result == "{effect_die}"


def test_menu_context_sfx_appears_only_in_matching_context():
    repo = MenuRepo()
    repo.trait_settings = [SimpleNamespace(sfx_ids=["sfx-apply"], trait_id="origin")]
    repo.traits = {"origin": SimpleNamespace(default_sfx_ids=[])}
    repo.sfxs = {"sfx-apply": SFX(id="sfx-apply", name="Apply", trigger="",
                                  menu_context="contest_win", effects=[])}

    contest = {o.id: o for o in assemble_consequence_menu(_entity(), repo, "player", "contest_win")}
    assert "sfx:sfx-apply" in contest

    test = {o.id: o for o in assemble_consequence_menu(_entity(), repo, "player", "test_success")}
    assert "sfx:sfx-apply" not in test


def test_contest_sfx_appears_only_in_matching_outcome():
    from transversal.services.sfx_owner import ensure_contest_complication_sfx

    repo = _base_move_repo()
    ensure_contest_complication_sfx(repo)
    repo.sfx_owners["table"].sfx_ids += ["apply-complication", "take-complication"]

    contest_win = {o.id for o in assemble_consequence_menu(_entity(), repo, "player", "contest_win")}
    assert "sfx:apply-complication" in contest_win
    assert "sfx:take-complication" not in contest_win

    give_in = {o.id for o in assemble_consequence_menu(_entity(), repo, "player", "contest_give_in")}
    assert "sfx:take-complication" in give_in
    assert "sfx:apply-complication" not in give_in

    test = {o.id for o in assemble_consequence_menu(_entity(), repo, "player", "test_success")}
    assert "sfx:apply-complication" not in test
    assert "sfx:take-complication" not in test


def test_legacy_on_consequence_sfx_appears_in_all_contexts():
    repo = MenuRepo()
    repo.trait_settings = [SimpleNamespace(sfx_ids=["sfx-flashback"], trait_id="origin")]
    repo.traits = {"origin": SimpleNamespace(default_sfx_ids=[])}
    repo.sfxs = {"sfx-flashback": SFX(id="sfx-flashback", name="Flashback",
                                     trigger="on_consequence", effects=[])}

    for context in ("test_success", "contest_win"):
        options = {o.id for o in assemble_consequence_menu(_entity(), repo, "player", context)}
        assert "sfx:sfx-flashback" in options


def test_assemble_hitch_menu_filters_owners_and_context():
    from transversal.domain import Condition, ConditionType
    from transversal.services.consequence_menu import assemble_hitch_menu

    def _hitch():
        return Condition(type=ConditionType.HITCH)

    repo = MenuRepo()
    repo.sfx_owners = {
        "gm": SimpleNamespace(sfx_ids=["hitch-gain-complication", "other-gm"]),
        "table": SimpleNamespace(sfx_ids=["hitch-table", "contest-only", "opportunity-step-down-complication", "non-hitch-player"]),
    }
    repo.sfxs = {
        "hitch-gain-complication": SFX(id="hitch-gain-complication", name="Gain a complication",
                                       trigger="manual", placement="menu", conditions=[_hitch()], effects=[]),
        "other-gm": SFX(id="other-gm", name="Other", trigger="manual", effects=[]),
        "hitch-table": SFX(id="hitch-table", name="Table hitch", trigger="manual",
                           placement="menu", conditions=[_hitch()], effects=[]),
        "contest-only": SFX(id="contest-only", name="Contest", trigger="manual",
                            placement="menu",
                            conditions=[Condition(type=ConditionType.CONTEST_OUTCOME, target="player")],
                            effects=[]),
        "opportunity-step-down-complication": SFX(
            id="opportunity-step-down-complication", name="Step down a complication",
            trigger="manual", placement="menu",
            conditions=[_hitch(), Condition(type=ConditionType.ENTITY_TYPE, subject="{buying_entity}", target="character")],
            effects=[],
        ),
        "non-hitch-player": SFX(id="non-hitch-player", name="Not hitch", trigger="manual", effects=[]),
    }

    repo.locations["buyer-1"] = Entity(id="buyer-1", type=EntityType.CHARACTER, name="Buyer", current_universe="earth")
    options = assemble_hitch_menu(repo, roller_id="roller-1", buyer_id="buyer-1")
    assert [o.id for o in options] == [
        "sfx:hitch-gain-complication", "sfx:hitch-table", "sfx:opportunity-step-down-complication",
    ]
    assert [o.side for o in options] == ["gm", "either", "player"]


def test_hitch_menu_filters_by_buyer_condition():
    from transversal.domain import Condition, ConditionType, TraitSetting
    from transversal.services.consequence_menu import assemble_hitch_menu

    repo = MenuRepo()
    repo.sfx_owners = {"table": SimpleNamespace(sfx_ids=["opportunity-step-down-complication"])}
    repo.sfxs = {
        "opportunity-step-down-complication": SFX(
            id="opportunity-step-down-complication", name="Step down", trigger="manual", placement="menu",
            conditions=[
                Condition(type=ConditionType.HITCH),
                Condition(
                    type=ConditionType.HAS_TRAIT_IN_TRAITSET,
                    subject="{buying_entity}", target="ts-complications",
                ),
            ],
            effects=[],
        ),
    }
    buyer = Entity(id="buyer-1", type=EntityType.CHARACTER, name="Buyer", current_universe="earth")
    repo.locations["buyer-1"] = buyer  # get_entity resolves the buyer via locations

    # Buyer has a complication → the SFX appears.
    repo.trait_settings = [
        TraitSetting(id="buyer-1:comp", entity_id="buyer-1", trait_id="comp",
                     traitset_id="ts-complications", dice=[]),
    ]
    assert [o.id for o in assemble_hitch_menu(repo, roller_id="roller-1", buyer_id="buyer-1")] == [
        "sfx:opportunity-step-down-complication"
    ]

    # Buyer has no complications → the SFX is filtered out.
    repo.trait_settings = []
    assert assemble_hitch_menu(repo, roller_id="roller-1", buyer_id="buyer-1") == []
