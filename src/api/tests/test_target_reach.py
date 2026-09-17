"""The catalog reach a flat "which targets" scope needs to be a path.

Every hop here exists because the scope vocabulary asked a question the spec
vocabulary could not answer: *inside this place*, *on this faction's roster*,
*this faction's own table*, *the timers running on me*. These tests pin the
semantics of that reach directly — the scope table is written on top of it, so a
regression here would show up there as an unexplained candidate-set change.
"""

from types import SimpleNamespace as NS

import pytest

from transversal.services.target_resolver import (
    TargetContext,
    resolve,
    serialize_candidates,
)
from transversal.services.target_spec import (
    FilterStep,
    LiteralStep,
    NavigateStep,
    SelectStep,
    TargetSpec,
)


def spec(*steps):
    return TargetSpec(steps=list(steps))


class FakeRepo:
    def __init__(self):
        self.entities = {}
        self.descendants = {}
        self.members = {}
        self.factions = {}
        self.lifepaths = {}
        self.roll_tables = []
        self.traitsets = []
        self.scheduled = []
        self.traitsettings = {}

    def get_entity(self, eid):
        return self.entities.get(eid)

    def get_entities_by_ids(self, ids):
        return [self.entities[i] for i in ids if i in self.entities]

    def list_location_descendants(self, lid):
        return list(self.descendants.get(lid, []))

    def list_faction_members(self, fid):
        return [self.entities[i] for i in self.members.get(fid, []) if i in self.entities]

    def get_entity_factions(self, eid):
        return list(self.factions.get(eid, []))

    def get_lifepath(self, lid):
        return self.lifepaths.get(lid)

    def list_all_lifepaths(self):
        return list(self.lifepaths.values())

    def list_roll_tables(self):
        return list(self.roll_tables)

    def get_roll_table(self, tid):
        return next((t for t in self.roll_tables if t.id == tid), None)

    def get_all_traitsets(self):
        return list(self.traitsets)

    def get_scheduled_event(self, eid):
        return next((e for e in self.scheduled if e.id == eid), None)

    def list_scheduled_events(self, target_type=None, target_id=None):
        return [
            e for e in self.scheduled
            if (target_type is None or e.target_type == target_type)
            and (target_id is None or e.target_id == target_id)
        ]

    def get_traitsetting(self, ts_id):
        return self.traitsettings.get(ts_id)


@pytest.fixture
def world():
    repo = FakeRepo()
    repo.entities = {
        "kael": NS(id="kael", type="character", name="Kael", current_universe="earth",
                   current_location="loc-root"),
        "iron-roots": NS(id="iron-roots", type="faction", name="Iron Roots",
                         current_universe="earth", suitable_life_path_ids=["lp-wander"]),
        "disciple": NS(id="disciple", type="gmc", name="Disciple", current_universe="earth"),
        "loc-root": NS(id="loc-root", type="location", name="Iron Roots",
                       current_universe="earth"),
        "loc-zone": NS(id="loc-zone", type="location", name="Bulwark Forge",
                       current_universe="earth"),
    }
    repo.descendants = {"loc-root": ["loc-zone", "loc-deep"]}
    repo.members = {"iron-roots": ["kael", "disciple"]}
    repo.factions = {"kael": ["iron-roots"]}
    repo.lifepaths = {
        "lp-wander": NS(id="lp-wander", name="The Wandering Sword", universe="earth"),
        "lp-other": NS(id="lp-other", name="Other Path", universe="earth"),
    }
    repo.roll_tables = [
        NS(id="rt-wander", name="Wandering", universe="earth", life_path="lp-wander"),
        NS(id="rt-other", name="Other", universe="earth", life_path="lp-other"),
    ]
    repo.traitsets = [NS(id="ts-combat", name="Combat", universes=["earth"])]
    timer = NS(id="ev-1", target_type="entity", target_id="kael", source_sfx_id="sfx-fire",
               effect=NS(action="step_up", target="trait-might"),
               timers=[NS(event="scene", remaining=2)])
    on_trait = NS(id="ev-2", target_type="trait_setting", target_id="kael:ts-1",
                  source_sfx_id="", effect=NS(action="set", target=""),
                  timers=[NS(event="session", remaining=1)])
    repo.scheduled = [timer, on_trait]
    repo.traitsettings = {"kael:ts-1": NS(id="kael:ts-1", entity_id="kael")}
    return repo


def _ids(result):
    return [getattr(v, "id", v) for v in result.values]


def test_a_place_includes_everything_under_it(world):
    result = resolve(
        spec(LiteralStep(element="location", value="loc-root"), NavigateStep(edge="subtree")),
        TargetContext(repo=world),
    )
    assert result.errors == []
    assert _ids(result) == ["loc-root", "loc-zone"]


def test_members_and_factions_are_inverse_but_directed(world):
    roster = resolve(
        spec(LiteralStep(element="entity", value="iron-roots"), NavigateStep(edge="members")),
        TargetContext(repo=world),
    )
    assert _ids(roster) == ["kael", "disciple"]

    mine = resolve(
        spec(LiteralStep(element="entity", value="kael"), NavigateStep(edge="factions")),
        TargetContext(repo=world),
    )
    assert _ids(mine) == ["iron-roots"]

    # The reverse of `members` is not `factions`: a member's factions are the orgs
    # it is on, which is a one-element answer against a two-member roster.
    assert _ids(mine) != _ids(roster)


def test_a_faction_reaches_its_own_table(world):
    result = resolve(
        spec(LiteralStep(element="entity", value="iron-roots"),
             NavigateStep(edge="life_paths"),
             NavigateStep(edge="roll_tables")),
        TargetContext(repo=world),
    )
    assert result.errors == []
    assert _ids(result) == ["rt-wander"]


def test_registry_seeds_range_over_definitions(world):
    traitsets = resolve(spec(SelectStep(collection="traitsets")), TargetContext(repo=world))
    assert _ids(traitsets) == ["ts-combat"]

    paths = resolve(spec(SelectStep(collection="life_paths")), TargetContext(repo=world))
    assert _ids(paths) == ["lp-wander", "lp-other"]

    tables = resolve(spec(SelectStep(collection="roll_tables")), TargetContext(repo=world))
    assert _ids(tables) == ["rt-wander", "rt-other"]


def test_life_path_and_roll_table_are_literal_targets(world):
    table = resolve(spec(LiteralStep(element="roll_table", value="rt-wander")),
                    TargetContext(repo=world))
    assert _ids(table) == ["rt-wander"]
    path = resolve(spec(LiteralStep(element="life_path", value="lp-other")),
                   TargetContext(repo=world))
    assert _ids(path) == ["lp-other"]


def test_timers_on_the_entity_and_on_its_trait_instances(world):
    result = resolve(
        spec(LiteralStep(element="entity", value="kael"), NavigateStep(edge="scheduled_events")),
        TargetContext(repo=world),
    )
    assert _ids(result) == ["ev-1", "ev-2"]
    # A timer on someone *else's* trait instance is not this entity's business.
    other = resolve(
        spec(LiteralStep(element="entity", value="disciple"),
             NavigateStep(edge="scheduled_events")),
        TargetContext(repo=world),
    )
    assert _ids(other) == []


def test_a_timer_labels_itself_from_its_effect(world):
    event = world.get_scheduled_event("ev-1")
    [candidate] = serialize_candidates("scheduled_event", [event], world)
    assert candidate.name == "step_up trait-might (sfx-fire)"
    assert candidate.subtitle == "2 scenes"


def test_excluding_self_is_a_filter_on_a_bound_id(world):
    """*Everyone here but me* needs no special notion of "self" in the catalog:
    bind the actor's id, then filter it out."""
    result = resolve(
        spec(SelectStep(collection="self", output="me"),
             SelectStep(collection="occupants"),
             FilterStep(field="id", operator="!=", value="{me}")),
        TargetContext(subject=world.get_entity("kael"), repo=world,
                      collections={"occupants": list(world.entities.values())}),
    )
    assert result.errors == []
    assert "kael" not in _ids(result)
    assert "disciple" in _ids(result)
