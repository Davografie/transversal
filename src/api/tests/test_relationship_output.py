"""A created relationship edge can be named, and its contact reached by navigating.

The author, 2026-10-13: *"I saw that create relationship still doesn't give me the
ability to expose the outcome."* The outcome of the action is the **edge** — a
relationship trait hangs on the tie, not on the person — so that is what
``output_element`` publishes, and the contact is one navigation away
(``relationship → contact``). Four pieces had to line up: the declaration, the
commit recording the edge's key, the published id, and the resolver being able to
look a relationship up by key (without that last one the name would bind and then
seed nothing).
"""

from __future__ import annotations

from types import SimpleNamespace as NS

from transversal.domain import Effect, EffectTiming, Entity, EntityType
from transversal.services.effects_applier.datatypes import BINDINGS_CONTEXT_KEY
from transversal.services.effects_applier.registry import publish_effect_output
from transversal.services.effects_commit import commit_effects
from transversal.services.target_resolver import TargetContext, resolve
from transversal.services.target_spec import NavigateStep, SelectStep, TargetSpec


class _Repo:
    """Edges keyed like Arango keys them, plus the reads the commit and resolver make."""

    def __init__(self):
        self.entities = {"kael": NS(id="kael", type="character", sfx_ids=[]),
                         "gmc-1": NS(id="gmc-1", type="gmc", sfx_ids=[])}
        self.edges = {}

    def get_entity(self, eid):
        return self.entities.get(eid)

    def create_relationship(self, from_id, to_id, rel_type, description=""):
        key = f"{from_id}-{rel_type}-{to_id}"
        edge = {"_key": key, "id": key, "from": from_id, "to": to_id, "type": rel_type,
                "owner_id": from_id, "contact_id": to_id}
        self.edges[key] = edge
        return edge

    def get_relationship_by_key(self, key):
        return self.edges.get(key)

    # Anything else the commit reaches for is a no-op read here.
    def __getattr__(self, name):
        return lambda *a, **k: [] if name.startswith("list_") else None


def _effect(output: str = "tie") -> Effect:
    return Effect(timing=EffectTiming.IMMEDIATE, type="relationship", action="create",
                  target="gmc-1", result="membership", output=output)


def test_a_created_edge_is_named_and_its_contact_is_reachable():
    repo = _Repo()
    entity = Entity(id="kael", name="Kael", type=EntityType.CHARACTER, current_universe="three_realms")
    effect = _effect()

    context = {BINDINGS_CONTEXT_KEY: {}}
    result = commit_effects(entity, [effect], repo, context)
    publish_effect_output(effect, result, context)      # what the registry's _commit does

    bound = context[BINDINGS_CONTEXT_KEY].get("tie")
    assert bound is not None, "the edge was not published under the author's name"
    assert bound.element == "relationship"
    assert bound.value == "kael-membership-gmc-1", "the bound id is the edge's own key"

    # …and the name can *seed a path*, which is the half that was missing: the tie
    # first, then the person through it.
    spec = TargetSpec(steps=[
        SelectStep(collection="variable", variable="tie"),
        NavigateStep(edge="contact"),
    ])
    resolution = resolve(spec, TargetContext(repo=repo, bindings=context[BINDINGS_CONTEXT_KEY]))
    assert [getattr(v, "id", v) for v in resolution.values] == ["gmc-1"]
    assert resolution.errors == []


def test_the_edge_itself_is_what_the_path_selects():
    """`select variable tie` yields the edge, not the contact — the author's choice."""
    repo = _Repo()
    entity = Entity(id="kael", name="Kael", type=EntityType.CHARACTER, current_universe="three_realms")
    effect = _effect()
    context = {BINDINGS_CONTEXT_KEY: {}}
    publish_effect_output(effect, commit_effects(entity, [effect], repo, context), context)

    spec = TargetSpec(steps=[SelectStep(collection="variable", variable="tie")])
    got = resolve(spec, TargetContext(repo=repo, bindings=context[BINDINGS_CONTEXT_KEY]))
    # An edge is a dict in this model, not an object.
    assert [v["id"] for v in got.values] == ["kael-membership-gmc-1"]
