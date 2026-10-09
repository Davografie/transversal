"""Table dice — the notation a roll table rolls, and what it actually rolls.

A roll table's fixed die is a number generator, not a Cortex trait die, so it may
be a d20, a d100 or a d66. ``d66`` is the trap worth pinning: by convention it is
**two d6 read as digits** (11–66), not a 66-sided die, so reading ``max_value``
as "roll 1..66" would give a silently different distribution — one that includes
7 and 17, and that makes a table authored 41–66 unreachable two thirds of the
time.

The Cortex ladder's dice keep their outcome tiers; a die off the ladder has none.
"""

import itertools

import pytest

from transversal.domain import DieSpec, DieType, RollTable, RollTableEntry, RollTableScheme, TableDie
from transversal.domain.tabledice import CORTEX_DICE
from transversal.services.dice_resolver import roll_dice


# ── The notation ─────────────────────────────────────

def test_the_notation_is_canonicalised_and_validated():
    assert str(TableDie("D20")) == "d20"
    assert str(TableDie(" d66 ")) == "d66"
    assert str(TableDie("D7")) == "d7"
    # The ladder is a subset of the notation, so a trait die is still rollable.
    assert str(TableDie(DieType.D8)) == "d8"

    for bad in ("", "20", "d", "d1", "d0", "d1001", "fire", "2d6", "d6+"):
        with pytest.raises(ValueError):
            TableDie(bad)


def test_the_ladder_does_not_grow_a_tail():
    """The whole point of a separate type: a d20 is not a Cortex die."""
    for die in CORTEX_DICE:
        assert TableDie(die).is_cortex
    for die in ("d20", "d66", "d100", "d7"):
        assert not TableDie(die).is_cortex


def test_a_plain_die_is_one_die_of_its_side_count():
    for notation, sides in (("d20", 20), ("d100", 100), ("d7", 7)):
        die = TableDie(notation)
        assert (die.dice_count, die.face_sides) == (1, sides)
        assert (die.min_value, die.max_value) == (1, sides)
        assert len(list(die.all_values)) == sides
        assert die.combine([sides]) == sides


def test_a_repeated_digit_reads_dice_as_digits_not_one_wide_die():
    """The convention generalises, so `d66` is not a special case.

    `d88` is two d8 and `d666` is three d6 — same rule, and the same trap if the
    written number is taken at face value.
    """
    for notation, dice, face_sides, low, high in (
        ("d44", 2, 4, 11, 44),
        ("d66", 2, 6, 11, 66),
        ("d88", 2, 8, 11, 88),
        ("d99", 2, 9, 11, 99),
        ("d666", 3, 6, 111, 666),
    ):
        die = TableDie(notation)
        assert (die.dice_count, die.face_sides) == (dice, face_sides), notation
        assert (die.min_value, die.max_value) == (low, high), notation
        # Enumerated rather than sampled: exactly the digit combinations.
        assert set(die.all_values) == {
            int("".join(str(face) for face in combo))
            for combo in itertools.product(range(1, face_sides + 1), repeat=dice)
        }, notation
        assert len(die.all_values) == face_sides ** dice, notation

    d66 = TableDie("d66")
    for unreachable in (7, 10, 17, 20, 60, 67, 70, 0):
        assert unreachable not in d66.all_values
    # The written number and the thrown dice are different facts.
    assert d66.sides == 66
    assert d66.face_sides == 6


def test_a_mixed_number_or_a_repeated_one_stays_a_plain_die():
    """The rule is what keeps `d100` the percentile an author means.

    Its digits are not all the same, so it is one hundred-sided die — not a pair
    of d10. And a repeated 1 is degenerate (two d1 could only show 11), so `d11`
    is a plain eleven-sided die rather than a digit read.
    """
    for notation, sides in (("d100", 100), ("d11", 11), ("d20", 20), ("d111", 111)):
        die = TableDie(notation)
        assert not die.is_digit_read, notation
        assert (die.dice_count, die.face_sides) == (1, sides), notation
        assert (die.min_value, die.max_value) == (1, sides), notation

    for ladder in CORTEX_DICE:
        assert not TableDie(ladder).is_digit_read, ladder


def test_combine_needs_the_faces_the_notation_throws():
    with pytest.raises(ValueError):
        TableDie("d66").combine([3])          # a digit read is more than one face
    with pytest.raises(ValueError):
        TableDie("d20").combine([3, 4])       # a d20 is one
    with pytest.raises(ValueError):
        TableDie("d66").combine([0, 4])       # no die shows a 0
    with pytest.raises(ValueError):
        TableDie("d66").combine([7, 4])       # nor more than its face count
    assert TableDie("d88").combine([4, 7]) == 47
    assert TableDie("d666").combine([6, 1, 6]) == 616
    assert TableDie("d100").combine([100]) == 100


# ── What comes back from a roll ──────────────────────

def test_rolling_a_table_die_stays_inside_the_notation():
    rolls = roll_dice([DieSpec(die="d66") for _ in range(200)])
    values = [r.result for r in rolls]

    assert all(11 <= v <= 66 for v in values)
    # The reading that would be wrong: a 66-sided die shows these.
    assert all(v not in (7, 10, 17, 20, 60) for v in values)
    assert {str(r.die) for r in rolls} == {"d66"}
    # All 36 pairs are reachable (a miss over 200 rolls is ~0.4%).
    assert len(set(values)) >= 30


def test_a_d100_rolls_one_to_a_hundred():
    rolls = roll_dice([DieSpec(die="d100") for _ in range(500)])
    values = [r.result for r in rolls]

    assert all(1 <= v <= 100 for v in values)
    assert len(set(values)) >= 90


def test_a_die_off_the_ladder_has_no_outcome_tier():
    """A d100 showing 87 is not a "perfect" Cortex result.

    ``determine_tier`` reads a face as an outcome on the d4–d12 scale, so an
    off-ladder die must not be given one — anything reading
    ``roll_result.tier`` (an authored SFX, the resolver) would act on nonsense.
    """
    for notation in ("d20", "d66", "d100", "d7"):
        rolls = roll_dice([DieSpec(die=notation) for _ in range(20)])
        assert all(r.tier is None for r in rolls), notation


def test_a_ladder_die_keeps_its_outcome_tier():
    """The regression the change could have caused: Cortex dice still tier."""
    rolls = roll_dice([DieSpec(die=DieType.D6) for _ in range(50)])

    assert all(1 <= r.result <= 6 for r in rolls)
    assert all(r.tier is not None for r in rolls)


# ── What it is for: selecting an entry ───────────────

def test_a_digit_read_range_table_is_authored_against_its_outcomes():
    """An entry can *match* a number the die can never roll — and then it is dead.

    This is why the notation decides the range rather than the other way round:
    a table written against all of 11..88 looks fine and silently never lands on
    the entries in the gaps.
    """
    from transversal.services.roll_table import resolve_table

    die = TableDie("d88")
    table = RollTable(
        id="tbl-d88", name="d88 table", scheme=RollTableScheme.RANGE, die=die,
        entries=[
            RollTableEntry(label="low", min_value=11, max_value=48),
            RollTableEntry(label="gap", min_value=49, max_value=50),
            RollTableEntry(label="high", min_value=51, max_value=88),
        ],
    )

    assert resolve_table(table, roll=11).label == "low"
    assert resolve_table(table, roll=48).label == "low"
    assert resolve_table(table, roll=51).label == "high"
    assert resolve_table(table, roll=88).label == "high"

    # The gap entry matches when asked directly — 49 *is* between 49 and 50 …
    assert resolve_table(table, roll=49).label == "gap"
    # … but a d88 has no face showing 9 or 0, so no roll ever reaches it.
    assert 49 not in die.all_values
    assert {resolve_table(table, roll=v).label for v in die.all_values} == {"low", "high"}
