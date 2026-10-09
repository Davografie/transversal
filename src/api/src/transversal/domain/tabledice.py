"""Table dice — a die notation wider than the Cortex ladder.

A roll table's fixed die is not a Cortex trait die. It is a *number generator*
that selects an entry, and tables are written against dice the Cortex ladder has
no business knowing about: a percentile, a d20, a d88. Those must be rollable
without a d20 ever becoming a valid trait rating — the ladder (``d4`` → ``d12``,
:meth:`DieType.step_up`, :func:`die_tier`) is what a *trait* stands on, and
widening it would let a trait be rated off the end of it.

So this is deliberately **not** :class:`DieType`. It is a superset used by the
pool machinery (which rolls it) and by :class:`RollTable` (which names it), while
:class:`DieType` stays the closed ladder the rules are written in.

Two readings, and the second one is a trap:

``dN``
    One die showing ``1..N`` — ``d20``, ``d100``, ``d7``.

``dNN`` — a *repeated-digit* notation
    By convention, not one die of that size but **several dice read as digits**.
    ``d66`` is two d6 → 11, 12, … 66: 36 outcomes that never include 7 or 17 or
    60. ``d88`` is two d8 → 11..88, and the pattern continues (``d666`` reads
    three d6 → 111..666). Reading ``d66`` as ``1..66`` would be a silently
    different distribution, and every table authored against it would be wrong —
    so the notation decides, not the number it happens to spell.

The rule is one rule, not a special case for ``d66``: **digits all the same, and
that digit 2–9**. It is what leaves ``d100`` a plain hundred-sided die (its
digits are not all the same) while ``d88`` is a digit read — the difference is in
the notation, and both are what an author typing them means.
"""

from __future__ import annotations

import itertools
import re
from enum import Enum
from typing import Any

from pydantic import GetCoreSchemaHandler
from pydantic_core import core_schema

#: The Cortex ladder, by value. A die in here has an outcome tier; one outside it
#: does not — which is the whole reason the two types are kept apart.
CORTEX_DICE: tuple[str, ...] = ("d4", "d6", "d8", "d10", "d12")

#: ``dN`` for N sides. Bounded so a typo (`d100000`) is rejected at the edge
#: rather than rolled. It doubles as the cap on a digit read's width: four
#: repeated digits (`d2222`) is already past it.
_MIN_SIDES = 2
_MAX_SIDES = 1000

#: The smallest repeated digit that reads as a *digit read*. ``d11`` is excluded
#: on purpose — two d1 could only ever show 11 — so it stays a plain 11-sided die.
_MIN_DIGIT_READ = 2

_PATTERN = re.compile(r"^d(\d+)$")


def _digit_read(digits: str) -> int | None:
    """The face count of a digit read, or ``None`` when this is a plain die.

    ``"66"`` → 6 (two d6), ``"888"`` → 8 (three d8). ``"100"`` → None (the digits
    differ), ``"11"`` → None (a repeated 1 is degenerate, so a d11 is a d11).
    """
    if len(digits) >= 2 and len(set(digits)) == 1:
        face = int(digits[0])
        if _MIN_DIGIT_READ <= face <= 9:
            return face
    return None


class TableDie(str):
    """A die a roll table may roll: ``dN`` (uniform) or a repeated digit read.

    A ``str`` subclass, so it stores and travels as its own notation
    (``"d20"``) — the same shape the wire, the database and the authoring panel
    already speak. Constructing one validates::

        TableDie("d20")    # ok — one die, 1..20
        TableDie("d66")    # ok — two d6 read as digits, 11..66
        TableDie("d88")    # ok — two d8 read as digits, 11..88
        TableDie("d7")     # ok — any side count from 2 to 1000
        TableDie("d1")     # ValueError
        TableDie("fire")   # ValueError
    """

    def __new__(cls, value: Any) -> "TableDie":
        # A `DieType` is a str too, but `str(member)` is "DieType.D6" — read the
        # value, not the repr, so the Cortex dice keep working here.
        raw = value.value if isinstance(value, Enum) else value
        notation = str(raw).strip().lower()
        match = _PATTERN.match(notation)
        if not match:
            raise ValueError(f"{notation!r} is not a die notation (expected dN, e.g. d20, d66, d100)")
        digits = match.group(1)
        if _digit_read(digits) is None:
            sides = int(digits)
            if not _MIN_SIDES <= sides <= _MAX_SIDES:
                raise ValueError(
                    f"{notation!r} has {sides} sides; a table die takes {_MIN_SIDES}–{_MAX_SIDES}"
                )
        return super().__new__(cls, notation)

    # ── Shape ────────────────────────────────────────

    @property
    def digit_read(self) -> int | None:
        """The face count of a digit read (``d66`` → 6, ``d88`` → 8), else
        ``None`` — i.e. whether this notation is dice *read as digits*."""
        return _digit_read(str(self)[1:])

    @property
    def is_digit_read(self) -> bool:
        """True when the notation is a digit read rather than one wide die."""
        return self.digit_read is not None

    @property
    def is_cortex(self) -> bool:
        """Whether the Cortex ladder knows this die — i.e. whether it has an
        outcome tier (see :func:`dice_resolver.determine_tier`)."""
        return str(self) in CORTEX_DICE

    @property
    def sides(self) -> int:
        """The side count *as written* — ``d66`` → 66, which is exactly the
        number a digit read must not be read as. See :attr:`face_sides`."""
        return int(str(self)[1:])

    @property
    def dice_count(self) -> int:
        """How many dice are thrown: one per digit in a digit read, else one."""
        return len(str(self)) - 1 if self.is_digit_read else 1

    @property
    def face_sides(self) -> int:
        """The side count of each die actually thrown — a d66 throws d6s."""
        return self.digit_read if self.is_digit_read else self.sides

    @property
    def min_value(self) -> int:
        """The lowest number the notation can produce (``11`` for any digit
        read — you cannot roll a 0 face)."""
        return int("1" * self.dice_count) if self.is_digit_read else 1

    @property
    def max_value(self) -> int:
        """The highest number the notation can produce.

        This is what a reader *means* by the die's range, and what an entry's
        ``min_value``/``max_value`` are written against: ``11..66`` for a d66,
        ``11..88`` for a d88, ``1..100`` for a d100.
        """
        return int(str(self.face_sides) * self.dice_count) if self.is_digit_read else self.sides

    @property
    def value(self) -> str:
        """The notation. Mirrors :class:`DieType`, so a die reads the same
        whether it came from the ladder or the wider table notation."""
        return str(self)

    # ── Reading the faces ────────────────────────────

    def combine(self, faces: list[int]) -> int:
        """Turn thrown faces into the number the table selects on.

        One face passes through; a digit read is read left to right, so
        ``[3, 4]`` is 34 and ``[3, 4, 4]`` is 344.
        """
        if len(faces) != self.dice_count:
            raise ValueError(f"{self} throws {self.dice_count} dice, got {len(faces)} face(s)")
        if any(not 1 <= face <= self.face_sides for face in faces):
            raise ValueError(f"{self} shows 1–{self.face_sides}, got {faces}")
        return int("".join(str(face) for face in faces))

    @property
    def all_values(self) -> list[int]:
        """Every number this notation can produce, in order.

        **Not** ``range(min_value, max_value + 1)`` — for a digit read that
        would claim a d66 can show 17 or 60, which is the exact misreading this
        module exists to prevent. A table whose entries are written against the
        gaps simply never reaches them, so the honest list is here to author
        against.
        """
        if not self.is_digit_read:
            return list(range(1, self.sides + 1))
        return [
            int("".join(str(face) for face in combo))
            for combo in itertools.product(range(1, self.face_sides + 1), repeat=self.dice_count)
        ]

    # ── Pydantic ─────────────────────────────────────

    @classmethod
    def __get_pydantic_core_schema__(
        cls, source_type: Any, handler: GetCoreSchemaHandler
    ) -> core_schema.CoreSchema:
        """Validate from a plain string (or another str subclass) and serialise
        back to the notation, so the field is just a string on the wire."""
        return core_schema.no_info_after_validator_function(cls, core_schema.str_schema())
