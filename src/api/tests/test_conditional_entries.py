"""Conditional roll-table entries ([[B179]]): fall back to the previous matching one.

The author's call (2026-09-25). An entry's `conditions` were stored and never read;
now the *roll* path falls back to the nearest earlier entry that applies, and a
*chosen* row (the menu) is refused instead — silently running a different row than
the one someone picked is the worse surprise.
"""

from types import SimpleNamespace as NS

from transversal.domain import Condition, ConditionType, RollTable, RollTableEntry
from transversal.services.roll_table import entry_applies, resolve_applicable_entry


def _always(operator=">=", value=0):
    """A condition that reads razmerit, so the tests can make it true or false."""
    return Condition(type=ConditionType.HAS_RAZMERIT, operator=operator, value=str(value))


def _entity(razmerit=0):
    return NS(id="char-1", razmerit=razmerit, current_universe="three_realms",
              current_location="loc-1", current_projection=None, life_paths=[],
              pending_term=None)


def _table(entries):
    return RollTable(id="rt-x", name="X", scheme="range", entries=list(entries))


def test_an_entry_with_no_conditions_always_applies():
    assert entry_applies(RollTableEntry(label="plain"), _entity(), repo=NS()) is True


def test_a_roll_on_an_excluded_entry_falls_back_to_the_previous_one_that_applies():
    """Two rows apply, the third does not: a roll reaching the third runs the second
    — the row above it — rather than redistributing the die or refusing."""
    entries = [
        RollTableEntry(label="first", min_value=1, max_value=2),
        RollTableEntry(label="second", min_value=3, max_value=4),
        RollTableEntry(label="third", min_value=5, max_value=6,
                       conditions=[_always(">=", 5)]),
    ]
    table = _table(entries)
    broke = _entity(razmerit=0)
    rich = _entity(razmerit=9)

    assert resolve_applicable_entry(table, rich, repo=NS(), roll=5).label == "third"
    assert resolve_applicable_entry(table, broke, repo=NS(), roll=5).label == "second"
    # A roll that never reaches the excluded row is untouched.
    assert resolve_applicable_entry(table, broke, repo=NS(), roll=1).label == "first"


def test_it_walks_back_past_several_excluded_rows():
    entries = [
        RollTableEntry(label="first", min_value=1, max_value=2),
        RollTableEntry(label="second", min_value=3, max_value=4,
                       conditions=[_always(">=", 5)]),
        RollTableEntry(label="third", min_value=5, max_value=6,
                       conditions=[_always(">=", 5)]),
    ]
    table = _table(entries)
    assert resolve_applicable_entry(table, _entity(razmerit=0), repo=NS(),
                                    roll=6).label == "first"


def test_nothing_applies_is_no_entry_rather_than_a_wrong_one():
    entries = [RollTableEntry(label="only", conditions=[_always(">=", 5)])]
    assert resolve_applicable_entry(_table(entries), _entity(razmerit=0), repo=NS(),
                                    index=0) is None


def test_a_chosen_row_is_refused_not_steered():
    """The menu path checks the *chosen* entry; the picker caller turns a False into
    a refusal, which is what `roll_table_menu.apply_entry` raises."""
    entry = RollTableEntry(label="chosen", conditions=[_always(">=", 5)])
    assert entry_applies(entry, _entity(razmerit=0), repo=NS()) is False


def test_a_row_condition_can_read_a_table_level_variable():
    """[[B281]]: the reason the table-level layer exists.

    A row's condition tests a name the **table** resolved once — *"is the thing this
    table is about the one I care about?"* — instead of repeating that targeting path
    on every row. It only works because a table's names resolve **before a row is
    chosen**: `resolve_applicable_entry` builds that scope and hands it to
    `entry_applies`. A row's own declarations cannot be here, because which row
    applies is the question being asked.

    Before this, every caller passed no bindings at all, so a row's conditions saw
    *no* declared name — table-level included — and this condition could never pass.
    """
    from transversal.domain import BoundVariable
    from transversal.services.target_spec import TargetSpec

    def _reads_the_flag():
        return Condition(type=ConditionType.TARGET_PATH, spec=TargetSpec.model_validate(
            {"steps": [{"kind": "select", "collection": "variable", "variable": "flagged"}]}))

    flagged = BoundVariable(name="flagged", spec=TargetSpec.model_validate(
        {"steps": [{"kind": "literal", "element": "location", "value": "loc-2"}]}))

    entries = [
        RollTableEntry(label="first", min_value=1, max_value=2),
        RollTableEntry(label="gated", min_value=3, max_value=4, conditions=[_reads_the_flag()]),
    ]
    declaring = _table(entries)
    declaring.bound_variables = [flagged]
    silent = _table(entries)

    # A `literal` resolves by fetching the id, so the repo has to know it.
    repo = NS(get_entity=lambda eid: NS(id=eid))

    assert resolve_applicable_entry(declaring, _entity(), repo=repo, roll=3).label == "gated", \
        "the table declared `flagged`, so the row's condition passes"
    assert resolve_applicable_entry(silent, _entity(), repo=repo, roll=3).label == "first", \
        "nothing declares `flagged`, so the condition is unmet and the roll falls back"


def test_a_row_condition_can_read_a_name_the_path_supplies():
    """[[B290]]: the **caller's** layer resolves before a row is chosen, exactly as the
    table's does, which is what lets a *shared* table's row condition test the context
    its path gave it — `{sect}` — instead of hardcoding a faction in a condition.

    This is the link that would break silently: `resolve_applicable_entry` builds the
    scope the condition reads, so the path/step layers have to reach *it* and not only
    the effects resolved after the row.
    """
    from transversal.domain import BoundVariable
    from transversal.services.target_spec import TargetSpec

    def _reads_the_sect():
        return Condition(type=ConditionType.TARGET_PATH, spec=TargetSpec.model_validate(
            {"steps": [{"kind": "select", "collection": "variable", "variable": "sect"}]}))

    sect = BoundVariable(name="sect", spec=TargetSpec.model_validate(
        {"steps": [{"kind": "literal", "element": "location", "value": "loc-2"}]}))

    entries = [
        RollTableEntry(label="first", min_value=1, max_value=2),
        RollTableEntry(label="gated", min_value=3, max_value=4, conditions=[_reads_the_sect()]),
    ]
    table = _table(entries)
    path = NS(id="lp-a", bound_variables=[sect])
    repo = NS(get_entity=lambda eid: NS(id=eid))

    assert resolve_applicable_entry(table, _entity(), repo=repo, roll=3,
                                    path=path).label == "gated", \
        "the path supplied `sect`, so the row's condition passes"
    assert resolve_applicable_entry(table, _entity(), repo=repo, roll=3).label == "first", \
        "with no path there is no `sect`, so the condition is unmet and the roll falls back"
