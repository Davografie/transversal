"""Rolltables — split out of src/api/src/transversal/api/graphql/types.py."""

import strawberry

from typing import Optional
from transversal.api.graphql.type_defs.conditions import (
    Condition,
    ConditionInput,
)
from transversal.api.graphql.type_defs.effects import (
    Effect,
    EffectInput,
)
from transversal.api.graphql.type_defs.sfx import (
    BoundVariable,
    BoundVariableInput,
)
from transversal.api.graphql.type_defs.enums import (
    DieType,
    OutcomeTier,
    RollSource,
    RollTableScheme,
)


@strawberry.type
class RollTableCheck:
    """Dice-pool check metadata for a TIER-scheme roll table."""
    trait_ids: list[str]
    difficulty: DieType
    free_choice: bool = False

@strawberry.type
class RollTableEntry:
    """A single entry in a roll table."""
    #: The row's stable identity, and what a `LifePathBinding` names to
    #: superimpose meaning on it. Not derived from the band: re-cutting `1–12`
    #: into `1–10` must not orphan every binding written against the row.
    key: str = ""
    label: str = ""
    description: str = ""
    min_value: Optional[int] = None
    max_value: Optional[int] = None
    weight: Optional[int] = None
    tier: Optional[OutcomeTier] = None
    conditions: list[Condition]
    cost_effects: list[Effect] = strawberry.field(default_factory=list)
    effects: list[Effect]
    #: Names this **row** resolves for itself before its effects run. Per row, not
    #: per table: a table-wide declaration resolves once, before any row is picked,
    #: so every row would share one value and no row could expose its own ([[B281]]).
    bound_variables: list[BoundVariable] = strawberry.field(default_factory=list)

@strawberry.type
class RollTable:
    """A reusable roll table whose entries execute effects when selected."""
    id: strawberry.ID
    name: str
    universe: str = ""
    #: Deprecated — paths name the tables they wrap (`LifePath.steps`) now.
    life_path: Optional[str] = None
    #: What this table may be rolled *for* (`entity` / `projection` / …), the roll
    #: table's answer to an SFX's `source_kind`. "" = unconstrained.
    subject_kind: str = ""
    scheme: RollTableScheme
    roll_source: RollSource = RollSource.FIXED_DIE
    trait_dice_count: int = 1
    #: A table die notation, not the `DieType` ladder enum: `d20`, `d66`, `d100`
    #: and any `dN` are valid here, and widening the *enum* would have offered
    #: them to trait ratings too. A plain string keeps the two apart.
    die: str = "d6"
    check: Optional[RollTableCheck] = None
    entries: list[RollTableEntry]
    # Names the table resolves for itself **before any row is chosen**, so a row's
    # conditions can test them as well as its effects ([[B281]]). Resolved once per
    # activation, so every row shares one value; `RollTableEntry.bound_variables` is
    # the per-row layer. Ambient facts (the term's faction, this table's path
    # faction, the roll) exist without declaring anything.
    bound_variables: list[BoundVariable] = strawberry.field(default_factory=list)
    canvas_x: Optional[float] = None
    canvas_y: Optional[float] = None

@strawberry.input
class RollTableCheckInput:
    trait_ids: list[str] = strawberry.field(default_factory=list)
    difficulty: DieType = DieType.D6
    free_choice: bool = False

@strawberry.input
class RollTableEntryInput:
    key: str = ""
    label: str = ""
    description: str = ""
    min_value: Optional[int] = None
    max_value: Optional[int] = None
    weight: Optional[int] = None
    tier: Optional[OutcomeTier] = None
    conditions: list[ConditionInput] = strawberry.field(default_factory=list)
    cost_effects: list[EffectInput] = strawberry.field(default_factory=list)
    effects: list[EffectInput] = strawberry.field(default_factory=list)
    bound_variables: list[BoundVariableInput] = strawberry.field(default_factory=list)

@strawberry.input
class RollTableInput:
    id: str = ""
    name: str = ""
    universe: str = ""
    life_path: Optional[str] = None
    subject_kind: str = ""
    scheme: RollTableScheme = RollTableScheme.RANGE
    roll_source: RollSource = RollSource.FIXED_DIE
    trait_dice_count: int = 1
    die: str = "d6"
    check: Optional[RollTableCheckInput] = None
    entries: list[RollTableEntryInput] = strawberry.field(default_factory=list)
    bound_variables: list[BoundVariableInput] = strawberry.field(default_factory=list)
