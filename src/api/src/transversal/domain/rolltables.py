"""Rolltables — split out of src/api/src/transversal/domain/__init__.py."""

from pydantic import BaseModel
from pydantic import Field
from typing import Optional
from transversal.domain.effects import (
    Condition,
    Effect,
)
from transversal.domain.sfx import BoundVariable
from transversal.domain.enums import (
    DieType,
    OutcomeTier,
    RollSource,
    RollTableScheme,
)
from transversal.domain.tabledice import TableDie


class RollTableEntry(BaseModel):
    """A single entry in a roll table.

    Which selection fields are meaningful depends on the parent table's
    ``scheme``: range uses ``min_value``/``max_value``, weight uses ``weight``,
    tier uses ``tier``, and index uses the entry's position in the list.
    """
    label: str = ""
    description: str = ""
    min_value: Optional[int] = None
    max_value: Optional[int] = None
    weight: Optional[int] = None
    tier: Optional[OutcomeTier] = None
    conditions: list[Condition] = Field(default_factory=list)
    # Price paid on pick (e.g. ``spend_razmerit``, ``step_down_trait``); applied
    # before ``effects`` so a pick is pay-then-gain.
    cost_effects: list[Effect] = Field(default_factory=list)
    effects: list[Effect] = Field(default_factory=list)

class RollTableCheck(BaseModel):
    """Dice-pool check metadata for a TIER-scheme roll table.

    When present, resolving the table assembles a pool (predetermined traits or a
    free player choice) and rolls against ``difficulty``; the outcome tier selects
    a tier-keyed entry.
    """
    trait_ids: list[str] = Field(default_factory=list)
    difficulty: DieType = DieType.D6
    free_choice: bool = False

class RollTable(BaseModel):
    """A reusable roll table whose entries execute effects when selected."""
    id: str
    name: str
    universe: str = ""
    life_path: Optional[str] = None  # owning life path id; None = shared/general
    scheme: RollTableScheme = RollTableScheme.RANGE
    roll_source: RollSource = RollSource.FIXED_DIE
    trait_dice_count: int = 1  # number of trait dice to roll (N=1 for now)
    #: The die a FIXED_DIE table rolls. A :class:`TableDie`, not a ladder
    #: ``DieType``: a table may select on a d20, a d100 or a d66, and none of
    #: those is a Cortex trait die. A repeated-digit notation reads dice as
    #: digits (``d66`` two d6 → 11..66, ``d88`` two d8 → 11..88), so a RANGE
    #: table's entries are authored against that spread.
    die: TableDie = TableDie("d6")
    check: Optional[RollTableCheck] = None  # legacy dice-pool check; unused
    entries: list[RollTableEntry] = Field(default_factory=list)
    # Values this table names and resolves *for itself* before an entry's effects
    # run — the declaration an SFX already has, so "the rival this table is about"
    # is written once rather than in every entry that acts on them. Ambient facts
    # (the term's faction, this table's path faction, the roll) are in scope
    # whether or not anything is declared.
    bound_variables: list[BoundVariable] = Field(default_factory=list)
    # Canvas layout persistence (GM manual arrangement of life-path nodes).
    canvas_x: Optional[float] = None
    canvas_y: Optional[float] = None
