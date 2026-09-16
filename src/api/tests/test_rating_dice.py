"""The rating-die locus: a trait instance's own dice, reachable by a path.

A *die* lives in one of two places, and the catalog now says so with two element
types. A pool die is what a player assembled for a roll; a rating die is part of
a trait instance's definition. One `Change a Die` family targets either, and the
element a path lands on is what tells a persistent change from a transient one —
so the route, the fields and the reference form all have to be right.
"""

from types import SimpleNamespace as NS

from transversal.domain.enums import DieType
from transversal.services import target_catalog as tc
from transversal.services.target_resolver import (
    TargetContext,
    _read_field,
    resolve,
    resolved_id,
    serialize_candidates,
)
from transversal.services.target_spec import (
    AggregateStep,
    FilterStep,
    NavigateStep,
    SelectStep,
    TargetSpec,
    ValueType,
    check,
    final_type,
    trace,
)


def spec(*steps):
    return TargetSpec(steps=list(steps))


def _world(*, dice, ts_id="kael:spiritual-power"):
    return NS(id=ts_id, trait_id="trait-spiritual", traitset_id="ts-cultivation",
              entity_id="kael", projection_id=None, from_type="entity",
              statement="", dice=list(dice))


# ── The declaration ────────────────────────────────────────────

def test_the_rating_die_route_exists_and_is_typed():
    """A trait instance's rating dice are a catalog element of their own.

    Distinct from a pool die on purpose: they have no result, role or pool
    position, and the type-checker needs to know which locus a path reached.
    """
    edge = tc.edge("traitsetting", "rating_dice")
    assert edge is not None, "a trait instance must expose its rating dice"
    assert edge.target == ("rating_die",)

    back = tc.edge("rating_die", "traitsetting")
    assert back is not None and back.target == ("traitsetting",)

    # The two loci share the field name a change-die effect reads.
    assert tc.field("rating_die", "rating").type == "die"
    assert tc.field("die", "rating").type == "die"
    assert tc.field("rating_die", "index") is not None


def test_the_catalog_stays_internally_consistent():
    assert tc.validate() == []


# ── The type-checker ───────────────────────────────────────────

def test_the_route_traces_to_a_rating_die_collection():
    s = spec(SelectStep(collection="self_traitsettings"), NavigateStep(edge="rating_dice"))
    types, errors = trace(s)
    assert errors == []
    assert final_type(s).element == "rating_die"
    assert final_type(s).cardinality == "many"


def test_a_rating_die_can_be_filtered_and_ordered_by_its_size():
    """The whole point of the new route: *the lowest die of my rating* is writable."""
    s = spec(
        SelectStep(collection="self_traitsettings"),
        NavigateStep(edge="rating_dice"),
        FilterStep(field="rating", operator=">=", value="d6"),
    )
    assert trace(s)[1] == []

    top = spec(
        SelectStep(collection="self_traitsettings"),
        NavigateStep(edge="rating_dice"),
        AggregateStep(fn="top", field="rating"),
    )
    types, errors = trace(top)
    assert errors == []
    # `top` keeps the *element* (the die), which is what an effect can act on.
    assert types[-1].element == "rating_die"
    assert types[-1].cardinality == "one"


# ── The resolver ───────────────────────────────────────────────

def test_rating_dice_resolve_one_entry_per_die():
    ts = _world(dice=[DieType.D6, DieType.D8])
    repo = NS(get_traitsetting=lambda i: ts if i == ts.id else None)
    res = resolve(
        spec(SelectStep(collection="self_traitsettings"), NavigateStep(edge="rating_dice")),
        TargetContext(subject=NS(id="kael"), repo=repo, collections={"self_traitsettings": [ts]}),
    )
    assert res.errors == []
    assert len(res.values) == 2
    first, second = res.values
    assert (first["locus"], first["rating"], first["index"]) == ("rating", "d6", 0)
    assert (second["locus"], second["rating"], second["index"]) == ("rating", "d8", 1)
    assert first["ts_id"] == ts.id


def test_an_empty_rating_yields_no_dice_rather_than_failing():
    """An empty rating is a legal state — a trait with no dice is still a trait."""
    ts = _world(dice=[])
    res = resolve(
        spec(SelectStep(collection="self_traitsettings"), NavigateStep(edge="rating_dice")),
        TargetContext(subject=NS(id="kael"), repo=NS(),
                      collections={"self_traitsettings": [ts]}),
    )
    assert res.errors == []
    assert res.values == []


def test_a_rating_die_navigates_back_to_its_trait_instance():
    ts = _world(dice=[DieType.D8])
    repo = NS(get_traitsetting=lambda i: ts if i == ts.id else None)
    res = resolve(
        spec(SelectStep(collection="self_traitsettings"), NavigateStep(edge="rating_dice"),
             NavigateStep(edge="traitsetting")),
        TargetContext(subject=NS(id="kael"), repo=repo, collections={"self_traitsettings": [ts]}),
    )
    assert res.errors == []
    assert [v.id for v in res.values] == [ts.id]


def test_a_rating_die_resolves_to_a_rating_reference():
    """The reference an effect is applied with names *which* die of the rating."""
    die = {"locus": "rating", "rating": "d8", "ts_id": "kael:qi", "index": 1}
    assert resolved_id(die) == "rating:kael:qi:1"


def test_a_pool_die_still_resolves_to_its_position():
    """The pool form is unchanged — this is what a path through `pool → dice` gives."""
    die = {"die": "d8", "ts_id": "kael:qi", "pool_location": "loc-1",
           "pool_owner": "kael", "pool_index": 2}
    assert resolved_id(die) == "die:loc-1:kael:2"


# ── The field read both loci share ─────────────────────────────

def test_a_pool_dies_rating_is_readable():
    """A pool die carries its size under `die` while the catalog calls the field
    `rating`; reading the attribute alone returned None, which made
    `filter rating == d8` and `aggregate max rating` over dice match nothing."""
    assert _read_field({"die": "d8", "ts_id": "t"}, "rating", "die") == "d8"
    assert _read_field({"rating": "d10"}, "rating", "die") == "d10"


def test_a_pool_die_can_be_filtered_by_rating():
    ctx = TargetContext(collections={"rolled_dice": [
        {"die": "d8", "ts_id": "t1", "source_kind": "trait"},
        {"die": "d4", "ts_id": "t2", "source_kind": "trait"},
    ]})
    res = resolve(
        spec(SelectStep(collection="rolled_dice"), FilterStep(field="rating", value="d8")),
        ctx,
    )
    assert res.errors == []
    assert [v["ts_id"] for v in res.values] == ["t1"]


def test_a_pool_die_candidate_is_labelled_by_its_rating():
    """The picker label reads through the same derived reader, not the attribute."""
    cands = serialize_candidates("die", [{"die": "d8", "role": "total"}])
    assert cands[0].name == "d8"


# ── One action, two legal destinations ─────────────────────────

def test_a_destination_may_accept_either_locus():
    """A `Change a Die` effect takes a die in a pool *or* a die of a rating, and
    a path reaching either one is valid. The refusal names every type that would
    have worked, so the author is told what the field actually wants."""
    both = [ValueType("die", "one"), ValueType("rating_die", "one")]

    pool = spec(SelectStep(collection="rolled_dice"), AggregateStep(fn="top", field="rating"))
    assert check(pool, both) == (True, [])

    rating = spec(SelectStep(collection="self_traitsettings"),
                  NavigateStep(edge="rating_dice"),
                  AggregateStep(fn="top", field="rating"))
    assert check(rating, both) == (True, [])

    nowhere = spec(SelectStep(collection="self_traitsettings"))
    ok, errors = check(nowhere, both)
    assert ok is False
    assert "die/one or rating_die/one" in errors[0].message
