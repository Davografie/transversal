"""Rolltables — split out of src/api/src/transversal/domain/__init__.py."""

from pydantic import BaseModel
from pydantic import Field
from typing import Optional
from transversal.domain.effects import (
    Condition,
    Effect,
)
from transversal.domain.enums import (
    DieType,
    OutcomeTier,
    RollSource,
    RollTableScheme,
)


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
    die: DieType = DieType.D6  # die size for range/index rolls (FIXED_DIE)
    check: Optional[RollTableCheck] = None  # legacy dice-pool check; unused
    entries: list[RollTableEntry] = Field(default_factory=list)
    # Canvas layout persistence (GM manual arrangement of life-path nodes).
    canvas_x: Optional[float] = None
    canvas_y: Optional[float] = None
