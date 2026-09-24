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
