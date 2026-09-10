"""Step values that name a bound value instead of a literal.

This is the join that lets one path depend on a decision made in another — the
Attune case: *the who's projection whose universe is the one just chosen*.
"""

from transversal.domain import Effect, EffectTiming
from transversal.services import roll_deferral
from transversal.services.effects_engine import resolve_refs
from transversal.services.target_resolver import TargetContext, resolve
from transversal.services.target_spec import TargetSpec


class _Entity:
    def __init__(self, id, name, projections, type="character", current_universe=""):
        self.id = id
        self.name = name
        self._projections = projections
        self.type = type
        self.current_universe = current_universe

    @property
    def current_projection(self):
        return self._projections[0].id if self._projections else ""


class _Projection:
    def __init__(self, id, universe):
        self.id = id
        self.universe = universe


class _Repo:
    def __init__(self, world):
        self._world = world

    def get_entity(self, eid):
        return self._world.get(eid)

    def get_projection(self, pid):
        for entity in self._world.values():
            for p in getattr(entity, "_projections", []):
                if p.id == pid:
                    return p
        return None

    def get_projections_for_entity(self, entity_id):
        entity = self._world.get(entity_id)
        return list(getattr(entity, "_projections", []))


def _spec(*steps):
    return TargetSpec.model_validate({"steps": list(steps)})


def _ctx(repo, entity, bindings=None):
    return TargetContext(subject=entity, repo=repo, bindings=bindings or {})


def test_a_filter_can_compare_against_a_bound_name():
    world = {
        "kael": _Entity("kael", "Kael", [
            _Projection("kael:earth", "earth"),
            _Projection("kael:dreamlands", "the-dreamlands"),
        ]),
    }
    repo = _Repo(world)
    kael = world["kael"]

    spec = _spec(
        {"kind": "select", "collection": "self"},
        {"kind": "navigate", "edge": "projections"},
        {"kind": "filter", "field": "universe", "operator": "==", "value": "{chosen_universe}"},
    )

    # With the name bound, the path lands on the matching life.
    resolved = resolve(spec, _ctx(repo, kael, {
        "chosen_universe": type("B", (), {"value": "the-dreamlands", "cardinality": "one"})(),
    }))
    assert [v.id for v in resolved.values] == ["kael:dreamlands"]

    # With nothing bound the reference cannot match, so the path yields nothing
    # rather than silently matching everything.
    empty = resolve(spec, _ctx(repo, kael))
    assert empty.values == []


def test_a_reference_value_is_in_scope_for_the_next_reference():
    """Declaration order defines the dependency: universe first, then the life."""
    world = {
        "kael": _Entity("kael", "Kael", [
            _Projection("kael:earth", "earth"),
            _Projection("kael:dreamlands", "the-dreamlands"),
        ]),
        "universe-the-dreamlands": _Entity("universe-the-dreamlands", "the Dreamlands", [],
                                             type="universe", current_universe="the-dreamlands"),
    }
    repo = _Repo(world)
    kael = world["kael"]
    context = _ctx(repo, kael)

    effect = Effect(
        timing=EffectTiming.IMMEDIATE, type="attune", action="enable", target="kael",
        refs={
            # "which world" — resolved to a universe *entity*, as a path ending on
            # one would. It binds as the handle (its `current_universe`), which is
            # what a projection stores.
            "universe": {"value": "universe-the-dreamlands"},
            "projection": {"spec": _spec(
                {"kind": "select", "collection": "self"},
                {"kind": "navigate", "edge": "projections"},
                {"kind": "filter", "field": "universe", "operator": "==", "value": "{universe}"},
            )},
        },
    )

    out = resolve_refs(effect, context)
    assert len(out) == 1
    refs = out[0].refs
    assert refs["universe"].value == "universe-the-dreamlands"
    assert context.bindings["universe"].value == "the-dreamlands"
    assert refs["projection"].value == "kael:dreamlands"
