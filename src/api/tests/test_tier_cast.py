"""The ``tier`` cast — a die read as its ladder position, not its side count.

Raised by the author authoring *Cultivation Stage*: "increase the dicepool total
limit by the tier of this rating", so ``d4`` → 1 … ``d12`` → 5. Two things make
this worth its own tests rather than a line in the aggregation suite: the system
*already* converts a die to a number somewhere else with a different answer
(``_to_number`` gives the side count, ``"d8"`` → 8), so the distinction is a
contract and not an implementation detail; and a cast reads **one** value, so a
collection has to be refused rather than silently sampled.
"""

from types import SimpleNamespace as NS

from transversal.domain.enums import DieType
from transversal.domain.rating import die_tier
from transversal.services import target_catalog as tc
from transversal.services.target_resolver import TargetContext, resolve
from transversal.services.target_spec import (
    AggregateStep,
    NavigateStep,
    SelectStep,
    TargetSpec,
    ValueType,
    trace,
)

from tests.test_target_resolver import FakeRepo


def spec(*steps):
    return TargetSpec(steps=list(steps))


# ── The conversion ────────────────────────────────────────────

def test_the_tier_is_the_ladder_position():
    assert [die_tier(d) for d in DieType] == [1, 2, 3, 4, 5]
    assert die_tier(DieType.D12) == 5


def test_the_tier_is_not_the_side_count():
    """The whole reason the cast is named. Both readings are *correct*; they
    answer different questions, and an implicit one would silently pick."""
    assert die_tier("d8") == 3
    assert DieType.D8.max_value == 8


def test_a_value_that_names_no_die_casts_to_nothing():
    """``None`` means *nothing to cast* — not *cast to zero*. A trait with an
    empty rating must not quietly add +0 where the author meant +3."""
    for value in (None, "", "d20", "fire", "8", 8, NS(rating="d6")):
        assert die_tier(value) is None, value


def test_a_rating_field_may_carry_an_enum_or_a_string():
    assert die_tier(DieType.D6) == 2
    assert die_tier("d6") == 2
    assert die_tier("D6") == 2  # a stored rating is not case-normalized for us


# ── What the catalog offers ───────────────────────────────────

def test_the_cast_is_offered_for_die_fields_only():
    offered = {a.name for a in tc.aggregations_for("die")}
    assert "tier" in offered
    # A string field (the *outcome* tier lives on a pool die as a string) cannot
    # be cast — so the two meanings of "tier" never meet in one dropdown.
    assert "tier" not in {a.name for a in tc.aggregations_for("string")}


# ── In a path ─────────────────────────────────────────────────

def _cultivation_world(rating="d8"):
    kael = NS(id="kael", type="character", current_location="loc-1",
              current_universe="earth", current_projection=None, razmerit=0)
    qi = NS(id="kael:spiritual-power", trait_id="trait-qi", traitset_id="ts-cultivation",
            entity_id="kael", projection_id=None, rating=rating)
    return kael, qi, FakeRepo(entities={"kael": kael},
                              traitsettings={"kael:spiritual-power": qi})


def _cast_source_rating():
    return spec(
        SelectStep(collection="source"),
        AggregateStep(fn="tier", field="rating"),
    )


def test_the_source_rating_casts_to_its_tier():
    kael, qi, repo = _cultivation_world("d8")
    ctx = TargetContext(subject=kael, repo=repo, source=qi, source_element="traitsetting")

    types, errors = trace(_cast_source_rating(), source_element="traitsetting")
    assert errors == []
    assert types[-1] == ValueType("int", "one")

    result = resolve(_cast_source_rating(), ctx)
    assert result.errors == []
    assert result.values == [3]  # d8 → 3, and *not* 8


def test_every_rung_casts_to_its_own_tier():
    for rating, expected in (("d4", 1), ("d6", 2), ("d8", 3), ("d10", 4), ("d12", 5)):
        kael, qi, repo = _cultivation_world(rating)
        result = resolve(
            _cast_source_rating(),
            TargetContext(subject=kael, repo=repo, source=qi, source_element="traitsetting"),
        )
        assert result.values == [expected], rating


def test_an_empty_rating_casts_to_nothing_rather_than_zero():
    kael, qi, repo = _cultivation_world("")
    result = resolve(
        _cast_source_rating(),
        TargetContext(subject=kael, repo=repo, source=qi, source_element="traitsetting"),
    )
    assert result.errors == []
    assert result.values == []


# ── A cast reads one value ────────────────────────────────────

def test_a_collection_is_refused_rather_than_sampled():
    """Which die's tier? Picking the first would be a wrong number that looks
    like a right one, so the step is refused and the author narrows first."""
    kael, _qi, repo = _cultivation_world("d8")
    s = spec(
        SelectStep(collection="self_traitsettings"),
        AggregateStep(fn="tier", field="rating"),
    )

    _types, errors = trace(s)
    assert [e.step_index for e in errors] == [1]
    assert "single value" in errors[0].message

    result = resolve(s, TargetContext(subject=kael, repo=repo))
    assert result.errors, "the resolver must refuse it too, not only the checker"
    assert result.values == []


def test_narrowing_first_makes_the_cast_legal():
    kael, _qi, repo = _cultivation_world("d8")
    s = spec(
        SelectStep(collection="self_traitsettings"),
        AggregateStep(fn="top", field="rating"),
        AggregateStep(fn="tier", field="rating"),
    )
    _types, errors = trace(s)
    # `top` yields the element carrying the extreme value, so the cast is legal;
    # the trailing `rating` read is what makes it a die-typed field again.
    assert errors == []
    result = resolve(s, TargetContext(subject=kael, repo=repo))
    assert result.errors == []
    assert result.values == [3]
