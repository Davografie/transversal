"""What a roll table states about its own names has to be consistent ([[B285]]).

A table **reserves** a name by stating a type with no value (``RollTable.bound_variables``),
and a **row assigns** it by giving a path (``RollTableEntry.bound_variables``). The
reservation is a promise to every reader of that name — a downstream effect written
against ``location/one`` — so a row whose path resolves something else cannot be
allowed to reach the store. That check is pure and catalog-driven, which is why it
runs at the write boundary rather than at run time.
"""

from transversal.domain import BoundVariable, RollTable, RollTableEntry
from transversal.services.roll_table import roll_table_problems
from transversal.services.target_spec import TargetSpec


def _spec(*steps):
    return TargetSpec.model_validate({"steps": list(steps)})


def _literal(value="loc-1"):
    return _spec({"kind": "literal", "element": "location", "value": value})


def _collection():
    """`select locations` — a many-cardinality collection and nothing collapsing it."""
    return _spec({"kind": "select", "collection": "locations"})


def _reserved(name="picked", element="location", cardinality="one"):
    return BoundVariable(name=name, element=element, cardinality=cardinality)


def _assigned(name="picked", spec=None):
    return BoundVariable(name=name, spec=spec if spec is not None else _literal())


def _table(declared=(), entries=()):
    return RollTable(id="rt-x", name="X",
                     bound_variables=list(declared), entries=list(entries))


def _row(declared=(), label="India"):
    return RollTableEntry(label=label, bound_variables=list(declared))


# ── Consistent tables ────────────────────────────────────────────────

def test_a_reservation_and_a_matching_assignment_are_consistent():
    table = _table([_reserved()], [_row([_assigned()])])
    assert roll_table_problems(table) == []


def test_a_table_that_reserves_nothing_may_still_have_free_form_rows():
    """The scoping decision, pinned: the leak check applies to a table that
    **reserves something**. Refusing every free-form row would refuse the next save
    of live content whose table has no reservation yet — and with the editors unable
    to author one, the author could not get out of it."""
    table = _table([], [_row([_assigned()]), _row([_assigned("other")])])
    assert roll_table_problems(table) == []


def test_a_typed_table_declaration_that_reaches_its_type_is_consistent():
    """A table declaration may state a type *and* resolve a value — then the path is
    checked against what was stated, exactly as a row's assignment is."""
    table = _table([BoundVariable(name="spot", spec=_literal(), element="location",
                                  cardinality="one")])
    assert roll_table_problems(table) == []


# ── The reservation broken ───────────────────────────────────────────

def test_a_row_that_makes_a_reserved_name_many_is_a_problem():
    """The author's case: sixteen rows pin a location and one starts from a
    collection, so `{picked_location}` is `many` for that row alone."""
    table = _table([_reserved()], [_row([_assigned(spec=_collection())], label="Australia")])

    problems = roll_table_problems(table)
    assert len(problems) == 1
    assert "'Australia'" in problems[0], "the problem names the row"
    assert "location/many" in problems[0] and "location/one" in problems[0], \
        "and says both types, so the author does not have to work out which is which"


def test_a_row_may_not_assign_a_name_its_governed_table_never_reserved():
    """The contract leak, closed where the table governs: once a table says what its
    names mean, a row cannot introduce one behind its back."""
    table = _table([_reserved()], [_row([_assigned("picked_location")])])

    problems = roll_table_problems(table)
    assert any("does not reserve" in p and "'picked_location'" in p for p in problems), problems


def test_a_table_declaration_whose_path_disagrees_with_its_type_is_a_problem():
    table = _table([BoundVariable(name="spot", spec=_collection(), element="location",
                                  cardinality="one")])

    problems = roll_table_problems(table)
    assert any("declared location/one" in p for p in problems), problems


# ── Statability ──────────────────────────────────────────────────────

def test_a_reservation_must_name_an_element_the_catalog_knows():
    problems = roll_table_problems(_table([_reserved(element="locaton")]))
    assert any("unknown element 'locaton'" in p for p in problems), problems


def test_a_reservation_must_use_the_vocabularys_cardinality():
    """Anything but `one`/`many` would match no traced type, so every assignment
    would be refused with a message about a mismatch that is really a typo here."""
    problems = roll_table_problems(_table([_reserved(cardinality="lots")]))
    assert any("unknown cardinality 'lots'" in p for p in problems), problems


def test_the_same_name_cannot_be_reserved_twice():
    problems = roll_table_problems(_table([_reserved(), _reserved(cardinality="many")]))
    assert any("reserved twice" in p for p in problems), problems


def test_a_slot_cannot_also_be_given_a_value():
    """A reservation and a default for the same name at once: the table's own value
    binds first, so every row's assignment is shadow-refused and the slot is one
    nothing can fill. That is a dead name, and it is caught here rather than at run
    time where it would look like a row that simply does nothing."""
    problems = roll_table_problems(_table([
        _reserved(),
        BoundVariable(name="picked", spec=_literal(), element="location", cardinality="one"),
    ]))
    assert any("both reserved and given a value" in p for p in problems), problems


def test_a_nameless_declaration_is_reported_rather_than_ignored():
    problems = roll_table_problems(_table([BoundVariable(name="", element="location")]))
    assert any("has no name" in p for p in problems), problems


def test_an_assignment_with_no_path_is_reported():
    """A row variable with no path cannot be stored (the converter drops it), so this
    is a guard on the shape rather than a live state — but a table built by any other
    route must not read as consistent."""
    problems = roll_table_problems(_table([_reserved()], [_row([BoundVariable(name="picked")])]))
    assert any("has no path" in p for p in problems), problems


# ── What it deliberately does not say ────────────────────────────────

def test_a_path_it_cannot_type_is_not_reported_as_a_mismatch():
    """A path starting from a name the table does not state cannot be typed here.

    Reporting that as a mismatch would refuse a legitimate assignment — the same rule
    that keeps a name resolving to nothing unbound rather than bound empty. The
    checker says nothing rather than guessing, and the run time is what decides.
    """
    from_elsewhere = _spec({"kind": "select", "collection": "variable", "variable": "anchor"})
    table = _table([_reserved()], [_row([_assigned(spec=from_elsewhere)])])
    assert roll_table_problems(table) == []


def test_a_path_that_resolves_nothing_is_not_a_problem_here():
    """Resolving to nothing needs values and a repo, and it is the run time's answer:
    an unbound name is a clean no-op, not a contradiction."""
    far_away = _spec({"kind": "literal", "element": "location", "value": "loc-does-not-exist"})
    table = _table([_reserved()], [_row([_assigned(spec=far_away)])])
    assert roll_table_problems(table) == []
