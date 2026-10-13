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

    ``key`` is the row's **identity**, and it is not any of those: a life path
    superimposes meaning on a row by naming its key (``LifePathBinding.key``), so
    the key must survive a band being re-cut. Deriving it from ``min_value`` —
    which is all the surfaces had before — means editing ``1–12`` to ``1–10``
    silently orphans every binding written against it. Stable, author-visible,
    generated once when absent (see ``services/roll_table.row_key``).
    """
    key: str = ""
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
    #: Values this **row** names and resolves for itself once it has been chosen,
    #: before its own effects run — the declaration an SFX already has. A row is
    #: what a life path superimposes meaning on (``LifePathBinding.key``), so a row
    #: is what exposes the names that binding's effects consume.
    #:
    #: The **second** of two declaration layers, and the later one, which is what
    #: separates it from ``RollTable.bound_variables``. A table's names resolve
    #: *before* any row is picked, so a row's ``conditions`` can test them; a row's
    #: names can differ per row but are only known once that row already applies,
    #: so no row condition can read them — that would be circular. Use this layer
    #: for a value only this row has (a location, a rival), and the table's for
    #: something every row is about.
    bound_variables: list[BoundVariable] = Field(default_factory=list)

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
    #: **Deprecated** — the owning life path. Ownership is inverted now: a path
    #: names the tables it wraps (``LifePath.steps``), so a table is shared by
    #: being wrapped by nobody or by several. Kept while content migrates; a
    #: table's effective scope is derived from the paths that wrap it.
    life_path: Optional[str] = None
    #: What this table may be rolled **for** — the element type of the subject its
    #: entries' effects land on, from the same vocabulary the effect system uses
    #: for owners (``entity`` / ``projection`` / ``relationship`` / ``traitsetting``,
    #: see ``TRAIT_OWNER_ELEMENTS``). ``""`` = unconstrained.
    #:
    #: This is a roll table's answer to an SFX's ``source_kind``: an entry effect
    #: that names a trait assumes a *character* was rolled for, and silently means
    #: something else — or nothing — when the table is rolled for a projection or
    #: for no subject at all. Declaring it is what lets a table be checked against
    #: how it is actually rolled.
    subject_kind: str = ""
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
    # Values this table names and resolves *for itself* **before any row is
    # chosen**, so they are in scope for a row's ``conditions`` as well as its
    # effects. That is the layer's whole purpose: a row condition can test
    # ``{rival}`` instead of repeating an elaborate targeting path on every row
    # ("is the thing this table is about the one I care about?").
    #
    # It resolves once per activation, so every row shares one value — which is
    # exactly why ``RollTableEntry.bound_variables`` also exists, for a value only
    # one row has. Ambient facts (the term's faction, this table's path faction,
    # the roll) are in scope whether or not anything is declared.
    bound_variables: list[BoundVariable] = Field(default_factory=list)
    # Canvas layout persistence (GM manual arrangement of life-path nodes).
    canvas_x: Optional[float] = None
    canvas_y: Optional[float] = None
