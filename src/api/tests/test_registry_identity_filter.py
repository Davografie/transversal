"""Picking a specific member of a registry collection.

`select traits` (and traitsets, entities, …) hands you the whole registry. The
step that narrows it to *these* ones is a `filter`, and the field it filters on
has to be:
  - **typed**, so the wizard offers a picker instead of a raw id box
    (`references` is what drives that), and
  - **labelled**, so the dropdown and the card read "with trait Beast" rather
    than "with id trait-2081905".

One value stores a scalar with `==`; several store a list with `in`, which the
resolver reads as membership. Both are pinned here, because the authored
experience depends on the two halves agreeing.
"""

from types import SimpleNamespace

from transversal.services import target_catalog as tc
from transversal.services.target_resolver import TargetContext, resolve
from transversal.domain import TargetSpec

#: The registry elements whose identity is pickable. `sfx` is deliberately
#: absent: there is no `sfx` picker kind, so `references="sfx"` would render a
#: picker whose candidate lookup errors — worse than a text box.
PICKABLE = ("trait", "traitset", "entity", "location", "universe",
            "life_path", "roll_table", "scheduled_event")


def test_every_pickable_registry_element_is_typed_and_labelled():
    for element in PICKABLE:
        field = tc.SCALAR_FIELDS[element]["id"]
        assert field.references == element, (
            f"{element}.id must point at {element} so a filter offers the picker"
        )
        assert field.label, f"{element}.id needs a label; 'id' is not author-facing"


def test_sfx_identity_is_left_as_a_text_field():
    """Documented as a decision, not an oversight: `sfx` is not a picker kind."""
    assert tc.SCALAR_FIELDS["sfx"]["id"].references == ""


def test_trait_and_entity_can_also_be_filtered_by_name():
    """A *search* field, alongside the unambiguous identity pick. Names are not
    unique — four traits are called "size" — which is why this is not the field
    a rule uses when it must mean exactly one thing."""
    for element in ("trait", "entity"):
        name = tc.SCALAR_FIELDS[element]["name"]
        assert name.suggest, f"{element}.name should autosuggest existing names"
        assert "in" in tc.operators_for(name), "a name filter must take a subset"


class _Repo:
    """Just enough registry for `select traits`."""

    def __init__(self, traits):
        self._traits = traits

    def get_all_traits(self):
        return self._traits


TRAITS = [
    SimpleNamespace(id="trait-138363658", name="Divine Consciousness"),
    SimpleNamespace(id="trait-138364703", name="Spiritual Power"),
    SimpleNamespace(id="trait-138364159", name="Physical Body"),
    SimpleNamespace(id="trait-2081363", name="size"),
    SimpleNamespace(id="trait-39004657", name="size"),
]


def _filter(field, operator, value):
    spec = TargetSpec(steps=[
        {"kind": "select", "collection": "traits"},
        {"kind": "filter", "field": field, "operator": operator, "value": value},
    ])
    result = resolve(spec, TargetContext(subject=None, repo=_Repo(TRAITS)))
    assert result.errors == [], [str(e) for e in result.errors]
    return [getattr(v, "id", v) for v in result.values]


def test_identity_equality_yields_exactly_one_trait():
    assert _filter("id", "==", "trait-138364159") == ["trait-138364159"]


def test_identity_membership_yields_the_subset():
    """What the Three Realms grants need: three traits from one step, which the
    effect fans out over — one application per resolved target."""
    assert _filter("id", "in", ["trait-138363658", "trait-138364703",
                                "trait-138364159"]) == [
        "trait-138363658", "trait-138364703", "trait-138364159"]


def test_a_name_match_is_a_search_and_can_hit_several():
    """The reason a name filter is offered *beside* the pick, not instead of it:
    both traits called "size" match, and the rule would grant both."""
    assert _filter("name", "==", "size") == ["trait-2081363", "trait-39004657"]
