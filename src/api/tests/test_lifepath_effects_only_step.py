"""A step that triggers effects — no table, and an answerable ``{choose}`` ([[B314]]).

Two halves, and the second is the one that was a dead end. ``LifePathStep.effects``
already existed, but a step could only be *reached* through a roll table — and a
``choose`` in one of its effects was reported as a bare element name and dropped.
The executor said so outright: *"Answering a step-level choice is a separate piece
of work."*

These pin both halves, and each is written to fail if its half is removed:

* an **effects-only step** (no ``table_id``) applies its own effects and follows its
  own ``next`` — nothing to roll, nothing to bind;
* a ``choose`` in one of those effects is **put to the player with its candidates**,
  the step **holds still** until it is answered, and the answer applies to the
  chosen thing and only then advances.
"""

from types import SimpleNamespace as NS

from transversal.domain import (
    Effect,
    EffectTiming,
    Entity,
    EntityType,
    LifePath,
    LifePathStep,
    RollTable,
    RollTableEntry,
    RollTableScheme,
)
from transversal.services.lifepath_executor import (
    StepResolution,
    resolve_step,
    start_term,
)
from transversal.services.lifepath_validation import validate_life_path
from transversal.services.target_spec import TargetSpec

from tests.test_lifepath_executor import ExecutorRepo


def _entity(entity_id="char-1"):
    return Entity(id=entity_id, type=EntityType.CHARACTER, name=entity_id,
                  current_universe="earth")


def _table(table_id, entries):
    return RollTable(id=table_id, name=table_id, universe="earth",
                     scheme=RollTableScheme.INDEX, entries=entries)


def _entry(label, effects=()):
    return RollTableEntry(label=label, effects=list(effects))


def _choose_effect(steps):
    """An effect whose target is a **path ending in ``choose``** — the authored form
    the owner named (*"I'll author a ``{choose}`` selection"*)."""
    return Effect(
        timing=EffectTiming.IMMEDIATE, type="relationship", action="create",
        result="origin", target_spec=TargetSpec.model_validate({"steps": steps}),
    )


def _two_path(step_one):
    """A path whose first step is ``step_one`` and whose second wraps a table."""
    if not step_one.next:
        step_one = step_one.model_copy(update={"next": "s2"})
    return LifePath(id="lp-1", name="P", universe="earth", entry_step="s1", steps=[
        step_one,
        LifePathStep(id="s2", table_id="tbl-end"),
    ])


def _cursor(entity):
    return entity.pending_terms[""].current_step_id


def test_an_effects_only_step_runs_its_effects_and_advances():
    """The whole point: the step *is* the content, so there is nothing to author a
    row for. Its effects apply once and its own ``next`` moves the term."""
    repo = ExecutorRepo()
    repo.traits["t-1"] = NS(id="t-1", traitset_id="ts-1")
    repo.lifepaths["lp-1"] = _two_path(LifePathStep(
        id="s1", table_id="", label="Study", next="s2",
        effects=[Effect(timing=EffectTiming.IMMEDIATE, type="modify_trait",
                        action="gain", target="t-1", result="d6")],
    ))
    repo.tables["tbl-end"] = _table("tbl-end", [_entry("End")])

    entity = _entity()
    start_term(entity, "", "lp-1", repo)
    summary = resolve_step(entity, repo)

    assert [ts.trait_id for ts in repo.created_traitsettings] == ["t-1"], \
        "the step's own effect ran"
    assert summary["table_id"] == "", "an effects-only step reports no table"
    assert summary["done"] is False
    assert _cursor(entity) == "s2", "and it followed its own `next`"

    # The record is its own kind, not a `roll_table` naming an empty table.
    assert repo.historical_records[-1]["record_type"] == "life_path_step"
    assert repo.historical_records[-1]["data"]["effects_only"] is True


def test_a_step_choose_is_put_to_the_player_with_its_candidates():
    """A `choose` used to be reported as the word `entity` and skipped. Now the step
    holds still and hands back the question *and the pool* — a bare element name
    cannot be answered."""
    repo = ExecutorRepo()
    repo.entities["loc-a"] = _entity("loc-a")
    repo.entities["loc-b"] = _entity("loc-b")
    effect = _choose_effect([
        {"kind": "select", "collection": "entities"},
        {"kind": "choose", "count": 1},
    ])
    repo.lifepaths["lp-1"] = _two_path(LifePathStep(id="s1", table_id="", effects=[effect]))
    repo.tables["tbl-end"] = _table("tbl-end", [_entry("End")])

    entity = _entity()
    start_term(entity, "", "lp-1", repo)
    summary = resolve_step(entity, repo)

    assert summary["done"] is False, "a pending question is not a finished step"
    assert summary["applied"] == [], "nothing applies before the choice is answered"
    assert _cursor(entity) == "s1", "the term holds still on the step that asked"

    choices = summary["structured_choices"]
    assert len(choices) == 1
    choice = choices[0]
    assert choice.element == "entity"
    assert choice.field == "target"
    assert len(choice.candidates) >= 2, "the pool is the thing that was missing"


def test_answering_the_choose_applies_it_to_the_chosen_target_and_advances():
    """The second half of the contract: only the echoed effect is re-resolved, so
    nothing applies twice — and the step moves once nothing is pending."""
    repo = ExecutorRepo()
    repo.entities["loc-a"] = _entity("loc-a")
    repo.entities["loc-b"] = _entity("loc-b")
    effect = _choose_effect([
        {"kind": "select", "collection": "entities"},
        {"kind": "choose", "count": 1},
    ])
    repo.lifepaths["lp-1"] = _two_path(LifePathStep(id="s1", table_id="", effects=[effect]))
    repo.tables["tbl-end"] = _table("tbl-end", [_entry("End")])

    entity = _entity()
    start_term(entity, "", "lp-1", repo)
    first = resolve_step(entity, repo)
    choice = first["structured_choices"][0]
    chosen = choice.candidates[0]["id"]

    second = resolve_step(entity, repo, resolutions=[
        StepResolution(effect=effect, field=choice.field,
                       answers={choice.step_index: [chosen]}),
    ])

    assert second["structured_choices"] == []
    assert second["applied"], "the answered effect applied to what was chosen"
    assert _cursor(entity) == "s2", "and only then did the step advance"


def test_an_effects_only_step_needs_no_table_to_validate():
    """The validator has to *know* the new kind, or every effects-only step reads as
    a step whose table is missing."""
    repo = NS(get_roll_table=lambda tid: None, get_lifepath=lambda pid: None)
    path = LifePath(id="lp-1", name="P", universe="earth", entry_step="s1", steps=[
        LifePathStep(id="s1", table_id="", label="Study", next="",
                     effects=[Effect(timing=EffectTiming.IMMEDIATE, type="modify_trait",
                                     action="gain", target="t-1", result="d6")]),
    ])
    assert validate_life_path(path, repo) == []


def test_a_table_less_step_refuses_a_binding_and_reports_an_inert_one():
    repo = NS(get_roll_table=lambda tid: None, get_lifepath=lambda pid: None)
    from transversal.domain import LifePathBinding

    path = LifePath(id="lp-1", name="P", universe="earth", entry_step="s1", steps=[
        LifePathStep(id="s1", table_id="",
                     bindings=[LifePathBinding(key="row")]),
    ])
    problems = validate_life_path(path, repo)
    assert any("has no table, so it cannot bind rows" in p for p in problems)
    assert any("does nothing" in p for p in problems)


def test_the_effects_only_record_type_is_a_declared_kind():
    """The historical record goes through a model whose ``record_type`` is an
    **enum**, and nothing in this service's own tests reaches that model — the live
    walk did, and refused the write:

        Input should be 'roll_table', 'contest', 'test' or 'transversal'

    So the kind is asserted against the model here: a record type a fake repo happily
    stores is not a record type at all."""
    from transversal.domain.messaging import HistoricalRecord

    record = HistoricalRecord(entity_id="char-1", record_type="life_path_step",
                              universe="earth", data={"effects_only": True})
    assert record.record_type.value == "life_path_step"
