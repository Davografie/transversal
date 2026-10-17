"""A rule is something a path can reach ([[B327]]).

`select sfxs` seeds the whole registry, so a path could **search** every rule in
the game. What it could not do is **walk to one**: no navigation edge ended on the
`sfx` element, so "the rule this trait carries" had no expression, and the author
building `sfx-artifact-creation` was left with a `navigate` step whose `edge` was
the empty string — which resolves to nobody and reports nothing.

Two halves, and both are tested here: the catalog declares a hop per owner surface
(the declaration is what the wizard offers and the trace checks), and the resolver
reads the one list that surface keeps.
"""

from types import SimpleNamespace as NS

from transversal.domain import (
    Effect, EffectTiming, Entity, EntityType, RatingType, TargetRef, Trait,
    TraitSetting,
)
from transversal.services import target_catalog as tc
from transversal.services.target_resolver import TargetContext, resolve
from transversal.services.target_spec import (
    FilterStep, LiteralStep, NavigateStep, SelectStep, TargetSpec, trace,
)

TS = "char-1:formation"


def spec(*steps):
    return TargetSpec(steps=list(steps))


class Repo:
    """The reads these hops use — and nothing else, so a hop that needs more fails."""

    def __init__(self, *, traits=None, settings=None, sfxs=None, entities=None):
        self.traits = {t.id: t for t in (traits or [])}
        self.settings = {s.id: s for s in (settings or [])}
        self.sfxs = {s.id: s for s in (sfxs or [])}
        self.entities = {e.id: e for e in (entities or [])}

    def get_sfx(self, sfx_id):
        return self.sfxs.get(sfx_id)

    def get_trait(self, trait_id):
        return self.traits.get(trait_id)

    def get_traitsetting(self, ts_id):
        return self.settings.get(ts_id)

    def get_entity(self, entity_id):
        return self.entities.get(entity_id)


def _trait(**kw):
    base = dict(id="trait-formation", name="Formation", traitset_id="ts-tactics",
                possible_sfx_ids=["sfx-offered"], default_sfx_ids=["sfx-granted"])
    base.update(kw)
    return Trait(**base)


def _instance(sfx_ids):
    return TraitSetting(id=TS, entity_id="char-1", trait_id="trait-formation",
                        rating_type=RatingType.STATIC, dice=[], sfx_ids=list(sfx_ids))


def _sfx(sfx_id, trigger="manual"):
    return NS(id=sfx_id, name=sfx_id, trigger=trigger, source_kind=None)


# ── The declaration ──────────────────────────────────

def test_every_owner_surface_declares_a_hop_to_its_rules():
    """One hop per surface, all landing on `sfx` — the element the reference and
    the effect both name."""
    for element in ("traitsetting", "traitsetsetting", "entity", "location",
                    "projection"):
        edge = tc.edge(element, "sfxs")
        assert edge is not None, f"{element} has no hop to its rules"
        assert edge.target == ("sfx",) and edge.cardinality == "many"


def test_a_trait_definition_has_a_hop_for_each_of_its_two_lists():
    """Offered and granted are different facts; one hop would have to lie."""
    assert tc.edge("trait", "possible_sfxs").target == ("sfx",)
    assert tc.edge("trait", "default_sfxs").target == ("sfx",)
    assert tc.edge("trait", "possible_sfxs").label != tc.edge("trait", "default_sfxs").label


# ── The reads ────────────────────────────────────────

def test_a_trait_instance_reaches_the_rules_it_carries():
    """The author's path: a rolled die → its trait instance → the rules on it."""
    repo = Repo(settings=[_instance(["sfx-offered", "sfx-granted"])],
                sfxs=[_sfx("sfx-offered"), _sfx("sfx-granted")])
    res = resolve(spec(LiteralStep(element="traitsetting", value=TS),
                       NavigateStep(edge="sfxs")), TargetContext(repo=repo))
    assert res.errors == []
    assert [v.id for v in res.values] == ["sfx-offered", "sfx-granted"]


def test_a_definition_reads_offered_and_granted_separately():
    repo = Repo(traits=[_trait()],
                sfxs=[_sfx("sfx-offered"), _sfx("sfx-granted")])
    offered = resolve(spec(LiteralStep(element="trait", value="trait-formation"),
                           NavigateStep(edge="possible_sfxs")), TargetContext(repo=repo))
    granted = resolve(spec(LiteralStep(element="trait", value="trait-formation"),
                           NavigateStep(edge="default_sfxs")), TargetContext(repo=repo))
    assert [v.id for v in offered.values] == ["sfx-offered"]
    assert [v.id for v in granted.values] == ["sfx-granted"]


def test_an_entity_reaches_its_own_rules():
    entity = Entity(id="char-1", type=EntityType.CHARACTER, name="Kael",
                    current_universe="earth", sfx_ids=["sfx-offered"])
    repo = Repo(entities=[entity], sfxs=[_sfx("sfx-offered")])
    res = resolve(spec(LiteralStep(element="entity", value="char-1"),
                       NavigateStep(edge="sfxs")), TargetContext(repo=repo))
    assert [v.id for v in res.values] == ["sfx-offered"]


def test_a_deleted_rule_is_skipped_not_refused():
    """The list is content: a rule deleted out from under it leaves a dangling id,
    and refusing the hop would make every *other* rule on that trait unreachable."""
    repo = Repo(settings=[_instance(["sfx-gone", "sfx-offered"])],
                sfxs=[_sfx("sfx-offered")])
    res = resolve(spec(LiteralStep(element="traitsetting", value=TS),
                       NavigateStep(edge="sfxs")), TargetContext(repo=repo))
    assert res.errors == []
    assert [v.id for v in res.values] == ["sfx-offered"]


# ── The path the author was writing ──────────────────

def test_the_rolled_die_path_traces_to_a_rule():
    """Die → trait instance → its rules, as a *type-checked* draft. This is the
    half that makes the wizard offer the step: without the edge the trace refuses
    the hop and the builder cannot draw it."""
    s = spec(SelectStep(collection="rolled_dice"),
             NavigateStep(edge="traitsetting"),
             NavigateStep(edge="sfxs"))
    types, errors = trace(s)
    assert errors == []
    assert types[-1].element == "sfx"
    assert types[-1].cardinality == "many"


def test_an_empty_edge_step_is_an_error_not_a_silent_nothing():
    """What the author actually had stored: `navigate` with `edge: ""`. Left
    un-checked it resolves to nobody and the effect reports nothing at all — the
    shape B316 was about, one layer over."""
    s = spec(SelectStep(collection="rolled_dice"),
             NavigateStep(edge="traitsetting"),
             NavigateStep(edge=""))
    types, errors = trace(s)
    assert errors, "an empty edge must be refused, not silently dropped"
    assert types[-1] is None or types[-1].element != "sfx"
