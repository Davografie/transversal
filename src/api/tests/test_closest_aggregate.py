"""`aggregate closest` — the nearest of a set of places ([[B328]]).

A path could pick a place at random, or by a field it already carries. It could not
answer *which one is nearest*, because distance is not a column: it is measured
from **whoever is acting** to each candidate, along the location graph. That is why
this is an aggregate with no field, and why it is constrained by the *element* it
ranks rather than by a field type.

The measure is the app's own: `repo.get_location_distances_from`, the Dijkstra the
canvas and the nearest-faction list already rank by — so "closest" cannot come to
mean two different things.
"""

from types import SimpleNamespace as NS

from transversal.domain import Entity, EntityType
from transversal.services import target_catalog as tc
from transversal.services.target_resolver import Binding, TargetContext, resolve
from transversal.services.target_spec import (
    AggregateStep, LiteralStep, NavigateStep, SelectStep, TargetSpec, trace,
)

KING_1, KING_2, KING_3 = "king-1", "king-2", "king-3"
HERE, NEAR, FAR, NOWHERE = "loc-here", "loc-near", "loc-far", "loc-nowhere"


def spec(*steps):
    return TargetSpec(steps=list(steps))


class Repo:
    """Places, the kings standing in them, and a distance table."""

    def __init__(self, distances=None):
        self.distances = dict(distances or {})
        self.entities = {}
        for eid, place in ((KING_1, NEAR), (KING_2, FAR), (KING_3, NOWHERE)):
            self.entities[eid] = Entity(id=eid, type=EntityType.GMC, name=eid,
                                        current_universe="three_realms",
                                        current_location=place)
        for place in (HERE, NEAR, FAR, NOWHERE):
            self.entities[place] = Entity(id=place, type=EntityType.LOCATION,
                                          name=place, current_universe="three_realms")
        self.calls = []

    def get_entity(self, eid):
        return self.entities.get(eid)

    def get_location_distances_from(self, origin, targets, exclude_hidden=False):
        self.calls.append((origin, set(targets)))
        reachable = {k: v for k, v in self.distances.items() if k in targets}
        return reachable


def _traveller(place=HERE):
    return Entity(id="char-1", type=EntityType.CHARACTER, name="Kael",
                  current_universe="three_realms", current_location=place)


def _kings(repo):
    """The binding the roll table declares: the beast kings, as entities."""
    return {"beast_kings": Binding(value=KING_1, values=[KING_1, KING_2, KING_3],
                                   element="entity", cardinality="many")}


# ── The declaration ──────────────────────────────────

def test_closest_is_a_no_field_aggregate_for_places_only():
    agg = tc.aggregation("closest")
    assert agg is not None
    assert agg.needs_field is False
    assert agg.output == "element"
    assert agg.accepts_elements == ("location",)


def test_it_is_offered_for_a_place_collection_and_nothing_else():
    """The same declaration feeds the editor and the type-check, so offering it
    over dice would be offering a function that cannot resolve."""
    assert "closest" in {a.name for a in tc.aggregations_for(None, "location")}
    assert "closest" not in {a.name for a in tc.aggregations_for(None, "die")}
    assert "closest" not in {a.name for a in tc.aggregations_for("int", "location")}


# ── The type-check ───────────────────────────────────

def test_a_place_collection_collapses_to_the_closest_one():
    s = spec(SelectStep(collection="locations"), AggregateStep(fn="closest"))
    types, errors = trace(s)
    assert errors == []
    assert (types[-1].element, types[-1].cardinality) == ("location", "one")


def test_another_collection_is_refused_by_the_trace():
    s = spec(SelectStep(collection="entities"), AggregateStep(fn="closest"))
    types, errors = trace(s)
    assert errors, "closest over entities is not a distance question"


# ── The reads ────────────────────────────────────────

def test_the_author_path_lands_on_the_nearest_kings_place():
    """`beast_kings → location → closest` — the shape `rt-7923babf` holds, with the
    random pick replaced. King 3 is in a place with no route, so it is skipped
    rather than ranked."""
    repo = Repo({NEAR: 2, FAR: 5})
    res = resolve(
        spec(SelectStep(collection="variable", variable="beast_kings"),
             NavigateStep(edge="location", dedup=True),
             AggregateStep(fn="closest")),
        TargetContext(subject=_traveller(), repo=repo, bindings=_kings(repo)),
    )
    assert res.errors == []
    assert [v.id for v in res.values] == [NEAR]
    # One read for the whole candidate set, from the traveller's own place.
    assert repo.calls == [(HERE, {NEAR, FAR, NOWHERE})]


def test_a_place_you_are_already_in_is_the_closest():
    repo = Repo({HERE: 0, NEAR: 2})
    res = resolve(
        spec(LiteralStep(element="location", value=HERE),
             LiteralStep(element="location", value=NEAR)),
        TargetContext(repo=repo),
    )
    assert res.errors == []          # literals are a sanity check on the fixture
    res = resolve(
        spec(SelectStep(collection="locations"), AggregateStep(fn="closest")),
        TargetContext(subject=_traveller(), repo=repo, collections={"locations": [
            repo.get_entity(HERE), repo.get_entity(NEAR)]}),
    )
    assert [v.id for v in res.values] == [HERE]


def test_ties_break_on_id_so_the_answer_is_stable():
    repo = Repo({FAR: 3, NEAR: 3})
    res = resolve(
        spec(SelectStep(collection="locations"), AggregateStep(fn="closest")),
        TargetContext(subject=_traveller(), repo=repo,
                      collections={"locations": [repo.get_entity(FAR),
                                                 repo.get_entity(NEAR)]}),
    )
    assert [v.id for v in res.values] == [FAR]   # "loc-far" < "loc-near"


def test_nothing_reachable_resolves_to_nobody_rather_than_a_wrong_place():
    """Unreachable is **absent** from the distance read, never a sentinel: picking
    the smallest sentinel would lead the party somewhere the kings are not."""
    repo = Repo({})
    res = resolve(
        spec(SelectStep(collection="locations"), AggregateStep(fn="closest")),
        TargetContext(subject=_traveller(), repo=repo,
                      collections={"locations": [repo.get_entity(NEAR)]}),
    )
    assert res.errors == []
    assert res.values == []


def test_an_actor_with_no_place_resolves_to_nobody():
    """An unplaced body stands nowhere; guessing a destination from no origin is
    worse than saying nothing."""
    repo = Repo({NEAR: 2})
    res = resolve(
        spec(SelectStep(collection="locations"), AggregateStep(fn="closest")),
        TargetContext(subject=_traveller(place=None), repo=repo,
                      collections={"locations": [repo.get_entity(NEAR)]}),
    )
    assert res.values == []
    assert repo.calls == []


def test_a_gm_pressing_on_a_place_measures_from_that_place():
    """The subject is the location itself when a rule runs against the scene — the
    same distinction a spawn makes about where the copy lands."""
    repo = Repo({NEAR: 1})
    res = resolve(
        spec(SelectStep(collection="locations"), AggregateStep(fn="closest")),
        TargetContext(subject=repo.get_entity(FAR), repo=repo,
                      collections={"locations": [repo.get_entity(NEAR)]}),
    )
    assert [v.id for v in res.values] == [NEAR]
    assert repo.calls == [(FAR, {NEAR})]
