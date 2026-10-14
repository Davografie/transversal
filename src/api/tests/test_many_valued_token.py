"""A `{name}` that holds a *set* compares as a set, not as its first id.

[[B292]], filed by [[life-path]] against the Iron Roots walkability gate: a filter
written `filter id in {iron_roots_locations}` matched only the root of a 16-location
subtree, because `_bound_value` unwrapped a `many` binding to its first id while
`_match` then read that scalar as a one-element set. The **path** form already
respected the cardinality (`select variable` expands `binding.values`), so the two
spellings of one name disagreed — the flat token truncated.

Only the membership operators expand. `==` keeps comparing the first value, which is
what it does today and what changing outright would alter.
"""

from __future__ import annotations

from types import SimpleNamespace as NS

from transversal.services.target_resolver import Binding, TargetContext, resolve
from transversal.services.target_spec import FilterStep, SelectStep, TargetSpec


class _Repo:
    def __init__(self):
        self.entities = [NS(id="loc-1", name="Root"), NS(id="loc-2", name="Branch"),
                         NS(id="loc-9", name="Elsewhere")]

    def list_all_entities(self):
        return list(self.entities)


def _ctx():
    return TargetContext(repo=_Repo(), bindings={
        "iron_roots": Binding(value="loc-1", values=["loc-1", "loc-2"],
                              element="entity", cardinality="many"),
    })


def _spec(operator: str) -> TargetSpec:
    return TargetSpec(steps=[
        SelectStep(collection="entities"),
        FilterStep(field="id", operator=operator, value="{iron_roots}"),
    ])


def test_a_many_valued_token_is_a_set_for_membership():
    got = [v.id for v in resolve(_spec("in"), _ctx()).values]
    assert got == ["loc-1", "loc-2"], "the set was truncated to its first id"


def test_the_negation_still_means_none_of_them():
    assert [v.id for v in resolve(_spec("not in"), _ctx()).values] == ["loc-9"]


def test_a_scalar_comparison_is_unchanged():
    """`==` against a many binding compares the first value — today's behaviour, kept."""
    assert [v.id for v in resolve(_spec("=="), _ctx()).values] == ["loc-1"]


def test_a_one_valued_token_is_unchanged():
    ctx = TargetContext(repo=_Repo(), bindings={
        "one": Binding(value="loc-2", values=["loc-2"], element="entity", cardinality="one"),
    })
    spec = TargetSpec(steps=[SelectStep(collection="entities"),
                             FilterStep(field="id", operator="in", value="{one}")])
    assert [v.id for v in resolve(spec, ctx).values] == ["loc-2"]
