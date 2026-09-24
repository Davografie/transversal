"""The three gain verbs differ in *where* the trait is anchored.

`Gain Trait` puts it on the subject entity, `Gain Relationship Trait` on a
relationship edge (a tie to someone), `Gain Sub-trait` under another trait
instance (a facet of it). They share one applier — gaining means the same thing in
all three — so the only thing that decides is the **owner**, and the owner is
declared by the action (`owner_elements`) rather than guessed from the value.
"""

from types import SimpleNamespace as NS

from transversal.domain import (
    Effect,
    EffectTiming,
    Entity,
    EntityType,
    TargetSpec,
)
from transversal.services.effects_applier import apply_effects
from transversal.services.effects_applier.datatypes import OWNER_ID_CONTEXT_KEY


class Repo:
    """A character with one relationship edge and one top-level trait."""

    def __init__(self):
        self.entities = {
            "kael": Entity(id="kael", name="Kael", type=EntityType.CHARACTER,
                           current_universe="earth", current_location="loc-1"),
        }
        self.traits = {
            "trait-beast": NS(id="trait-beast", traitset_id="ts-x", default_ego=True),
            "trait-spiritual": NS(id="trait-spiritual", traitset_id="ts-x", default_ego=True),
        }
        self.traitsets = {"ts-x": NS(id="ts-x", allow_duplicates=False, polarity=None)}
        self.edges = [{"id": "rel-1", "type": "membership", "owner_id": "kael",
                       "contact_id": "guild", "description": "sworn"}]
        self.traitsettings = {
            "kael:trait-spiritual": NS(
                id="kael:trait-spiritual", trait_id="trait-spiritual", entity_id="kael",
                from_type="entity", parent_traitsetting_id=None, dice=[],
                enabled=True, order=None, rating_type="static", polarity="positive",
                statement="", notes="", projection_id=None),
        }

    def get_entity(self, eid):
        return self.entities.get(eid)

    def get_trait(self, tid):
        return self.traits.get(tid)

    def get_traitset_by_id(self, tid):
        return self.traitsets.get(tid)

    def get_traitsetting(self, tid):
        return self.traitsettings.get(tid)

    def list_relationships_for_entity(self, eid):
        return [e for e in self.edges if e["owner_id"] == eid or e["contact_id"] == eid]

    def get_relationship_traitsettings(self, key):
        return [ts for ts in self.traitsettings.values()
                if ts.entity_id == key and getattr(ts, "from_type", "") == "relationship"]

    def get_traitsettings_for_entity(self, eid):
        return [ts for ts in self.traitsettings.values()
                if ts.entity_id == eid and getattr(ts, "from_type", "") != "traitsetting"]

    def get_sub_traitsettings(self, parent_id):
        return [ts for ts in self.traitsettings.values()
                if getattr(ts, "parent_traitsetting_id", None) == parent_id]

    def resolve_traitsetting_id(self, owner_id, trait_id, statement="", allow_duplicates=False):
        return f"{owner_id}:{trait_id}"

    def resolve_subtrait_id(self, parent_id, trait_id, statement=""):
        return f"{parent_id}:{trait_id}"


THE_EDGE = TargetSpec(steps=[
    {"kind": "select", "collection": "self"},
    {"kind": "navigate", "edge": "relationships"},
])

THE_CONTAINER = TargetSpec(steps=[
    {"kind": "select", "collection": "self_traitsettings"},
    {"kind": "filter", "field": "trait_id", "operator": "==", "value": "trait-spiritual"},
])


def _gain(action, owner_spec=None, **context):
    return Effect(timing=EffectTiming.IMMEDIATE, type="modify_trait", action=action,
                  target="trait-beast", result="d6", owner_spec=owner_spec,
                  context=dict(context))


def _apply(effect, repo=None):
    repo = repo or Repo()
    result = apply_effects(repo.entities["kael"], [effect], repo)
    made = [*result.new_trait_settings, *result.updated_trait_settings]
    assert made, [a.summary for a in result.applied]
    return made[0]


def test_gain_trait_anchors_to_the_entity():
    made = _apply(_gain("gain"))
    assert (made.from_type, made.entity_id) == ("entity", "kael")
    assert not getattr(made, "parent_traitsetting_id", None)


def test_gain_relationship_trait_anchors_to_the_edge():
    """The edge is *the owner*, not the entity: a rank on a membership is stored on
    the edge, and the path is how the author says which one."""
    made = _apply(_gain("gain_relationship", THE_EDGE))
    assert (made.from_type, made.entity_id) == ("relationship", "rel-1")


def test_gain_subtrait_nests_under_the_container():
    """A facet hangs under the instance, keeps the *parent's* entity, and takes the
    parent-scoped key — plus the two fields that only mean anything here."""
    made = _apply(_gain("gain_subtrait", THE_CONTAINER, order="2", enabled="false"))
    assert made.from_type == "traitsetting"
    assert made.parent_traitsetting_id == "kael:trait-spiritual"
    assert made.entity_id == "kael", "a nested instance belongs to the parent's entity"
    assert made.id == "kael:trait-spiritual:trait-beast"
    assert made.order == 2
    assert made.enabled is False


def test_an_unordered_subtrait_is_left_unranked_rather_than_first():
    """`order` unauthored is not 0 — the model treats an unordered instance as
    unranked, and an ordering step relies on that."""
    assert _apply(_gain("gain_subtrait", THE_CONTAINER)).order is None


def test_the_owner_kind_comes_from_the_declaration_not_the_value():
    """An id alone does not say which collection reads it back.

    A verb that declares a *single* kind still reads stored content of that shape
    (an id with no kind — what resolution wrote before the kind travelled with
    it), but one that declares several cannot guess: an untyped id anchors to the
    subject entity rather than to some other collection's row."""
    repo = Repo()
    effect = _gain("gain")
    effect.context[OWNER_ID_CONTEXT_KEY] = "rel-1"
    made = _apply(effect, repo)
    assert (made.from_type, made.entity_id) == ("entity", "kael")
