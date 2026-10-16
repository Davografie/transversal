"""Spawning a copy of an entity — the mob from a template ([[B311]])."""

from types import SimpleNamespace

from transversal.domain import (
    Effect,
    EffectTiming,
    Entity,
    EntityType,
    TargetRef,
    TraitSetSetting,
    TraitSetting,
)
from transversal.services.effects_applier.datatypes import EffectsResult
from transversal.services.effects_applier.handlers_world import _apply_duplicate_entity


def _entity(eid, etype=EntityType.GMC, name="Bandit", **kw):
    return Entity(id=eid, type=etype, name=name, current_universe="earth", **kw)


def _ts(tid, entity_id, trait_id, from_type="entity", **kw):
    return TraitSetting(id=tid, entity_id=entity_id, trait_id=trait_id,
                        from_type=from_type, **kw)


class FakeRepo:
    """Just enough repository for the copy, and it records every write."""

    def __init__(self, entities=(), top_traits=(), sub_traits=None,
                 set_settings=(), edges=(), edge_traits=None):
        self.entities = {e.id: e for e in entities}
        self.top_traits = list(top_traits)
        self.sub_traits = dict(sub_traits or {})
        self.set_settings = list(set_settings)
        self.edges = list(edges)
        self.edge_traits = dict(edge_traits or {})
        self.created_entities, self.created_projections = [], []
        self.created_traits, self.created_sets = [], []
        self.created_edges, self.claims = [], []
        self._seq = 0

    # reads
    def get_entity(self, eid):
        return self.entities.get(eid)

    def get_traitsettings_for_entity(self, eid):
        return [t for t in self.top_traits if t.entity_id == eid]

    def get_sub_traitsettings(self, parent_id):
        return self.sub_traits.get(parent_id, [])

    def get_traitsetsettings_for_entity(self, eid):
        return [s for s in self.set_settings if s.entity_id == eid]

    def list_relationships_for_entity(self, eid):
        return [e for e in self.edges if e.get("owner_id") == eid]

    def get_relationship_traitsettings(self, key):
        return self.edge_traits.get(key, [])

    # convention
    def resolve_traitsetting_id(self, owner, trait_id, statement, allow_duplicates):
        return f"{owner}:{trait_id}"

    def resolve_subtrait_id(self, parent_id, trait_id, statement):
        return f"{parent_id}:{trait_id}"

    def get_trait(self, trait_id):
        return SimpleNamespace(traitset_id="ts-1")

    def get_traitset_by_id(self, traitset_id):
        return SimpleNamespace(allow_duplicates=False)

    # writes
    def create_entity(self, e):
        self.created_entities.append(e)
        self.entities[e.id] = e
        return e

    def create_projection(self, p):
        self.created_projections.append(p)
        return p

    def create_traitsetting(self, ts):
        self.created_traits.append(ts)
        return ts

    def create_traitsetsetting(self, s):
        self.created_sets.append(s)
        return s

    def create_relationship(self, from_id, to_id, rel_type, description=""):
        self._seq += 1
        key = f"edge-new-{self._seq}"
        self.created_edges.append({"from": from_id, "to": to_id,
                                   "type": rel_type, "key": key,
                                   "description": description})
        return {"_key": key}

    def claim_entity(self, player_id, entity_id, main=False):
        self.claims.append((player_id, entity_id, main))


def _spawn(repo, template_id="gmc-template", subject=None, **ctx):
    effect = Effect(
        timing=EffectTiming.IMMEDIATE, type="entity", action="duplicate",
        refs={"template": TargetRef(value=template_id)},
        context=ctx or {},
    )
    result = EffectsResult()
    _apply_duplicate_entity(subject or repo.get_entity(template_id), effect, repo, result)
    return result


def test_a_mob_is_a_deep_copy_with_every_handle_remapped():
    template = _entity("gmc-template", name="Bandit", current_location="loc-1",
                       map_x=12.5, map_y=40.0, starter_location=True,
                       destination_location="loc-9")
    own = _ts("gmc-template:trait-brawl", "gmc-template", "trait-brawl")
    on_body = _ts("gmc-template:trait-cut", "gmc-template", "trait-cut",
                  from_type="projection", projection_id="gmc-template:earth")
    child = _ts("gmc-template:trait-brawl:trait-facet", "gmc-template", "trait-facet",
                from_type="traitsetting", parent_traitsetting_id="gmc-template:trait-brawl")
    a_set = TraitSetSetting(id="gmc-template:ts-1", entity_id="gmc-template",
                            traitset_id="ts-1")
    edges = [
        {"id": "edge-old-1", "type": "relation", "description": "owes money",
         "owner_id": "gmc-template", "contact_id": "gmc-boss"},
        {"id": "edge-old-2", "type": "membership", "description": "",
         "owner_id": "gmc-template", "contact_id": "faction-thieves"},
    ]
    edge_traits = {"edge-old-1": [_ts("edge-old-1:trait-debt", "edge-old-1",
                                      "trait-debt", from_type="relationship")]}
    repo = FakeRepo([template], [own, on_body], {own.id: [child]}, [a_set],
                    edges, edge_traits)

    result = _spawn(repo)

    copy = repo.created_entities[0]
    assert copy.id.startswith("gmc-bandit-") and copy.id != template.id
    assert copy.name == "Bandit"
    assert copy.current_location == "loc-1" and copy.current_universe == "earth"
    assert copy.current_projection == f"{copy.id}:earth"
    # A copy is a new arrival: none of the template's *place* comes with it.
    assert (copy.map_x, copy.map_y) == (None, None)
    assert copy.destination_location is None
    assert copy.starter_location is False
    assert repo.created_projections[0].id == f"{copy.id}:earth"

    # Its own instances, remapped — including the body-anchored one, which must
    # follow the *new* entity's active body rather than the template's.
    by_id = {t.id: t for t in repo.created_traits}
    assert {f"{copy.id}:trait-brawl", f"{copy.id}:trait-cut",
            f"{copy.id}:trait-brawl:trait-facet"} <= set(by_id)
    assert by_id[f"{copy.id}:trait-cut"].projection_id == copy.current_projection
    # …and the nested one hangs under the NEW parent, which is why parents copy first.
    nested = by_id[f"{copy.id}:trait-brawl:trait-facet"]
    assert nested.parent_traitsetting_id == f"{copy.id}:trait-brawl"
    assert nested.from_type == "traitsetting"

    # Set settings follow the entity.
    assert [s.id for s in repo.created_sets] == [f"{copy.id}:ts-1"]
    assert repo.created_sets[0].entity_id == copy.id

    # Both edge families, pointing at the same far ends.
    assert [(e["from"], e["to"], e["type"]) for e in repo.created_edges] == [
        (copy.id, "gmc-boss", "relation"),
        (copy.id, "faction-thieves", "membership"),
    ]
    assert [e["description"] for e in repo.created_edges][0] == "owes money"
    # The instance anchored to the old tie is re-anchored to the NEW edge.
    edge_copy = repo.created_traits[-1]
    assert edge_copy.entity_id == "edge-new-1" and edge_copy.id == "edge-new-1:trait-debt"

    # "Without sullying the original": the template is untouched.
    assert template.id in repo.entities and template.current_location == "loc-1"
    assert result.new_entities == [copy]
    assert "spawned Bandit" in result.applied[0].summary


def test_a_gm_press_spawns_where_the_gm_is_looking():
    """The subject of a GM-owned rule is the **place**, not a character."""
    template = _entity("gmc-template", current_location="loc-far")
    place = _entity("loc-here", etype=EntityType.LOCATION, name="The Docks")
    repo = FakeRepo([template, place])
    _spawn(repo, subject=place)
    assert repo.created_entities[0].current_location == "loc-here"


def test_a_character_press_spawns_at_that_characters_location():
    template = _entity("gmc-template", current_location="loc-far")
    hero = _entity("char-1", etype=EntityType.CHARACTER, current_location="loc-here")
    repo = FakeRepo([template, hero])
    _spawn(repo, subject=hero)
    assert repo.created_entities[0].current_location == "loc-here"


def test_an_authored_place_wins_and_nothing_falls_back_when_there_is_none():
    template = _entity("gmc-template", current_location="loc-far")
    repo = FakeRepo([template])
    effect = Effect(
        timing=EffectTiming.IMMEDIATE, type="entity", action="duplicate",
        refs={"template": TargetRef(value="gmc-template"),
              "owner": TargetRef(value="loc-chosen")},
    )
    result = EffectsResult()
    _apply_duplicate_entity(template, effect, repo, result)
    assert repo.created_entities[0].current_location == "loc-chosen"

    # With nothing authored and no subject, the template's own place is the last
    # resort rather than None.
    bare = FakeRepo([template])
    _spawn(bare)
    assert bare.created_entities[0].current_location == "loc-far"


def test_the_ownership_edge_is_optional_and_never_guessed():
    template = _entity("gmc-template")
    plain = FakeRepo([template])
    _spawn(plain)
    assert plain.claims == []

    asked = FakeRepo([template])
    _spawn(asked, owner_player_id="player-7")
    assert asked.claims == [("player-7", asked.created_entities[0].id, False)]


def test_a_missing_template_is_refused_rather_than_inventing_one():
    repo = FakeRepo([])
    result = _spawn(repo, template_id="gmc-nope")
    assert repo.created_entities == []
    assert "gmc-nope" in result.applied[0].summary


def test_a_name_can_be_given_and_the_template_keeps_its_own():
    template = _entity("gmc-template", name="Bandit")
    repo = FakeRepo([template])
    _spawn(repo, name="Bandit Chief")
    assert repo.created_entities[0].name == "Bandit Chief"
    assert template.name == "Bandit"
