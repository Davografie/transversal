"""The read-only spec resolution surface (``resolveTargetSpec``).

Why it exists: an inspection has to make a wrong step *visible*. A path that
selects two trait instances and then filters to none has to show that collapse —
a single final list cannot, and an empty result is otherwise indistinguishable
from "nothing was there to match". So these assert on the per-step trace and the
pending pool, not only on the final values.
"""

from types import SimpleNamespace as NS

from tests.test_entity_manager import InMemoryRepository

from transversal.api.graphql.resolvers.queries_targeting import QueriesTargeting
from transversal.api.graphql.types import TargetSpecInput, TargetSpecStepInput
from transversal.domain import DieType, Entity, EntityType, Trait, TraitSet, TraitSetting

ENTITY_ID = "kael"


def _repo():
    repo = InMemoryRepository()
    repo.create_entity(Entity(
        id=ENTITY_ID, type=EntityType.CHARACTER, name="Kael",
        current_universe="earth", current_location="loc-1",
    ))
    repo.create_traitset(TraitSet(id="ts-combat", name="Combat", universe="earth"))
    repo.create_traitset(TraitSet(id="ts-qi", name="Qi", universe="earth"))
    repo.create_trait(Trait(id="trait-martial", name="martial", universe="earth",
                            traitset_id="ts-combat", default_die_type=DieType.D8))
    repo.create_trait(Trait(id="trait-qi", name="qi", universe="earth",
                            traitset_id="ts-qi", default_die_type=DieType.D6))
    repo.create_traitsetting(TraitSetting(
        id="kael:trait-martial", entity_id=ENTITY_ID, trait_id="trait-martial",
         dice=[DieType.D8], statement="martial arts",
    ))
    repo.create_traitsetting(TraitSetting(
        id="kael:trait-qi", entity_id=ENTITY_ID, trait_id="trait-qi",
         dice=[DieType.D6], statement="qi",
    ))
    return repo


def _resolve(repo, steps, **kwargs):
    """Call the query field directly — the conversion, the walk, and the
    serialization are what is under test, not the HTTP transport."""
    return QueriesTargeting().resolve_target_spec(
        NS(context={"entity_manager": NS(repo=repo)}),
        input=TargetSpecInput(steps=steps), entity_id=ENTITY_ID, **kwargs,
    )


def _select(collection, variable=""):
    return TargetSpecStepInput(kind="select", collection=collection, variable=variable)


def test_every_step_is_traced_with_its_type_and_count():
    result = _resolve(_repo(), [_select("self_traitsettings"),
                                TargetSpecStepInput(kind="navigate", edge="trait")])
    assert result.valid is True
    assert [s.step_kind for s in result.steps] == ["select", "navigate"]
    assert [s.element for s in result.steps] == ["traitsetting", "trait"]
    assert [s.cardinality for s in result.steps] == ["many", "many"]
    assert [s.count for s in result.steps] == [2, 2]
    # A value carries a display label, so an inspection never shows a raw id.
    assert sorted(v.name for v in result.steps[0].values) == ["martial arts", "qi"]
    assert sorted(v.name for v in result.values) == ["martial", "qi"]


def test_a_step_that_collapses_is_visible_as_a_zero_count():
    result = _resolve(_repo(), [
        _select("self_traitsettings"),
        TargetSpecStepInput(kind="filter", field="traitset_id", operator="==", value="ts-nope"),
    ])
    # Matching nothing is not an error — it is the answer the caller came for.
    assert result.valid is True
    assert result.errors == []
    assert result.values == []
    assert result.steps[0].count == 2
    assert result.steps[1].count == 0
    # ...and the type survives the filter, so the zero reads as "none matched",
    # not "the path broke here".
    assert result.steps[1].element == "traitsetting"
    assert result.steps[1].error == ""


def test_values_can_be_capped_without_losing_the_count():
    result = _resolve(_repo(), [_select("self_traitsettings")], values_limit=1)
    assert result.steps[0].count == 2
    assert len(result.steps[0].values) == 1
    assert len(result.values) == 1


def test_a_choose_step_reports_its_pool_and_stops_the_walk():
    result = _resolve(_repo(), [_select("self_traitsettings"),
                                TargetSpecStepInput(kind="choose", count=1)])
    assert result.valid is True
    assert [s.index for s in result.steps] == [0, 1]
    assert result.steps[1].pending is True
    # Empty values *and* pending: the pool below is the missing piece, so a zero
    # here is never mistaken for a collapse.
    assert result.steps[1].count == 0
    assert result.steps[1].element == "traitsetting"
    assert len(result.pending_choices) == 1
    choice = result.pending_choices[0]
    assert choice.step_index == 1
    assert choice.count == 1
    assert sorted(c.name for c in choice.candidates) == ["martial arts", "qi"]


def test_a_scalar_step_labels_its_own_value():
    result = _resolve(_repo(), [
        _select("self_traitsettings"),
        TargetSpecStepInput(kind="aggregate", fn="count"),
    ])
    assert result.steps[1].element == "int"
    assert result.values[0].id == "2"
    assert result.values[0].name == "2"


def test_an_error_is_reported_against_its_own_step():
    result = _resolve(_repo(), [_select("self_traitsettings"),
                                TargetSpecStepInput(kind="navigate", edge="nope")])
    assert result.valid is False
    assert result.steps[0].error == ""
    assert "no edge/resolver" in result.steps[1].error
    assert result.errors[0].step_index == 1


def test_bindings_seed_a_variable_step():
    result = _resolve(
        _repo(),
        [_select("variable", variable="boon")],
        bindings={"boon": {"element": "traitsetting", "value": "kael:trait-qi"}},
    )
    assert result.valid is True
    assert [v.id for v in result.values] == ["kael:trait-qi"]
    assert result.values[0].name == "qi"


def test_a_typed_but_valueless_binding_is_an_error_not_an_empty_path():
    """A declared type with nothing under it used to resolve to nothing — the
    same reading as "nothing matched". It says so instead."""
    result = _resolve(_repo(), [_select("variable", variable="boon")],
                      bindings={"boon": "traitsetting"})
    assert result.valid is False
    assert "no value bound" in result.errors[0].message
    assert result.steps[0].count == 0
