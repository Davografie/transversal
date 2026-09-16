"""Targeting reach: the two whole-world seeds, and the relationship route.

Two additions that make a targeting path able to say two things it could not:

- **`select traits` / `select universes`** — the whole registry of trait
  *definitions*, and every universe. A definition seed is how an action that
  creates or teaches names *what* it is about without a picker.
- **`entity → relationships → traitsettings`** — a trait instance can hang off a
  relationship *edge* rather than off the entity (your standing with a faction),
  and a path could not reach one at all.
"""

from types import SimpleNamespace as NS

from transversal.services import target_catalog as tc
from transversal.services.target_resolver import (
    TargetContext,
    _seed_collection,
    resolve,
)
from transversal.services.target_spec import (
    FilterStep,
    NavigateStep,
    SelectStep,
    TargetSpec,
    final_type,
    trace,
)


def spec(*steps):
    return TargetSpec(steps=list(steps))


class Repo:
    """Only the reads these routes use."""

    def __init__(self, *, relationships=None, traits=None, universes=None):
        self._relationships = relationships or []
        self._traits = traits or []
        self._universes = universes or []

    def list_relationships_for_entity(self, entity_id):
        return [r for r in self._relationships if r["owner_id"] == entity_id]

    def get_relationship_traitsettings(self, edge_key):
        return [_ts(f"{edge_key}:standing", "trait-standing", edge_key)]

    def get_relationship_by_key(self, edge_key):
        return next((r for r in self._relationships if r["id"] == edge_key), None)

    def get_entity(self, eid):
        assert eid != "edge-key", "an edge key is not an entity id"
        return NS(id=eid, type="faction", current_location=None, current_universe="earth")

    def get_all_traits(self):
        return self._traits

    def list_entities_by_type(self, entity_type):
        # The real repo takes the enum; a `str` Enum member's *value* is the wire
        # currency (`str(EntityType.UNIVERSE)` would be "EntityType.UNIVERSE").
        wanted = getattr(entity_type, "value", entity_type)
        return [u for u in self._universes if u.type == wanted]


def _ts(ts_id, trait_id, edge_key):
    return NS(id=ts_id, trait_id=trait_id, entity_id=edge_key, from_type="relationship",
              dice=[], statement="", projection_id=None)


MEMBERSHIP = {"id": "edge-key", "type": "membership", "owner_id": "kael",
              "contact_id": "sect-1", "contact_name": "Verdant Steps Sect"}


# ── The relationship element ───────────────────────────────────

def test_the_catalog_declares_a_relationship_element_and_its_route():
    assert tc.element("relationship") is not None
    assert tc.edge("entity", "relationships").cardinality == "many"
    assert tc.edge("relationship", "traitsettings").target == ("traitsetting",)
    # The fields a path can narrow on.
    for name in ("type", "contact_id", "contact_name", "owner_id"):
        assert tc.field("relationship", name) is not None, name
    assert tc.validate() == []


def test_a_path_reaches_a_relationship_anchored_trait_instance():
    """The route the author asked for, end to end: my membership of a faction →
    the trait instance that lives on that edge."""
    s = spec(
        SelectStep(collection="self"),
        NavigateStep(edge="relationships"),
        FilterStep(field="type", value="membership"),
        NavigateStep(edge="traitsettings"),
    )
    types, errors = trace(s)
    assert errors == []
    assert final_type(s).element == "traitsetting"
    assert final_type(s).cardinality == "many"

    subject = NS(id="kael", type="character", current_location="loc-1", current_universe="earth")
    res = resolve(s, TargetContext(subject=subject, repo=Repo(relationships=[MEMBERSHIP])))
    assert res.errors == []
    assert [v.id for v in res.values] == ["edge-key:standing"]


def test_a_relationship_carries_who_the_other_party_is():
    """So a path can filter to *this* faction rather than any membership."""
    s = spec(
        SelectStep(collection="self"),
        NavigateStep(edge="relationships"),
        FilterStep(field="contact_id", value="sect-1"),
    )
    subject = NS(id="kael", type="character", current_location="loc-1", current_universe="earth")
    # contact_id references an entity, so the value is compared as an id.
    res = resolve(s, TargetContext(subject=subject, repo=Repo(relationships=[MEMBERSHIP])))
    assert res.errors == []
    assert len(res.values) == 1
    assert res.values[0]["contact_name"] == "Verdant Steps Sect"


def test_a_relationship_navigates_back_to_the_entity_that_holds_it():
    s = spec(SelectStep(collection="self"), NavigateStep(edge="relationships"),
             NavigateStep(edge="entity"))
    subject = NS(id="kael", type="character", current_location="loc-1", current_universe="earth")
    res = resolve(s, TargetContext(subject=subject, repo=Repo(relationships=[MEMBERSHIP])))
    assert res.errors == []
    assert [v.id for v in res.values] == ["kael"]


def test_a_trait_instance_anchored_to_a_relationship_can_hop_back_to_it():
    """Only when it *is* relationship-anchored: an entity's own trait instance has
    no relationship to name, so the hop resolves to nobody rather than guessing."""
    repo = Repo(relationships=[MEMBERSHIP])
    anchored = _ts("edge-key:standing", "trait-standing", "edge-key")
    res = resolve(spec(SelectStep(collection="self_traitsettings"), NavigateStep(edge="relationship")),
                  TargetContext(subject=NS(id="kael"), repo=repo,
                                collections={"self_traitsettings": [anchored]}))
    assert res.errors == []
    assert [v["id"] for v in res.values] == ["edge-key"]

    own = NS(id="kael:brave", trait_id="trait-brave", entity_id="kael", from_type="entity")
    empty = resolve(spec(SelectStep(collection="self_traitsettings"), NavigateStep(edge="relationship")),
                    TargetContext(subject=NS(id="kael"), repo=repo,
                                  collections={"self_traitsettings": [own]}))
    assert empty.errors == []
    assert empty.values == []


# ── The two whole-world seeds ──────────────────────────────────

def test_the_catalog_declares_the_two_whole_world_seeds():
    traits = tc.collection("traits")
    universes = tc.collection("universes")
    assert (traits.element, universes.element) == ("trait", "universe")
    assert not traits.singular and not universes.singular


def test_selecting_all_traits_yields_trait_definitions():
    s = spec(SelectStep(collection="traits"))
    types, errors = trace(s)
    assert errors == []
    assert (types[0].element, types[0].cardinality) == ("trait", "many")

    repo = Repo(traits=[NS(id="trait-fire", name="Fire"), NS(id="trait-wood", name="Wood")])
    res = resolve(s, TargetContext(repo=repo))
    assert res.errors == []
    assert [v.id for v in res.values] == ["trait-fire", "trait-wood"]


def test_selecting_all_universes_yields_universes():
    s = spec(SelectStep(collection="universes"))
    types, errors = trace(s)
    assert errors == []
    assert (types[0].element, types[0].cardinality) == ("universe", "many")

    repo = Repo(universes=[NS(id="earth", type="universe", name="Earth")])
    res = resolve(s, TargetContext(repo=repo))
    assert res.errors == []
    assert [v.id for v in res.values] == ["earth"]


def test_both_seeds_are_read_from_the_repo_on_demand():
    """One seeding rule for every collection: the subject-derived and whole-world
    seeds resolve here, so a path cannot silently see a different world."""
    repo = Repo(traits=[NS(id="trait-fire", name="Fire")],
                universes=[NS(id="earth", type="universe", name="Earth")])
    ctx = TargetContext(repo=repo)
    assert [t.id for t in _seed_collection("traits", ctx)] == ["trait-fire"]
    assert [u.id for u in _seed_collection("universes", ctx)] == ["earth"]
