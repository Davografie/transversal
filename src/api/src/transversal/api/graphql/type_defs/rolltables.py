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
    label: str = ""
    description: str = ""
    min_value: Optional[int] = None
    max_value: Optional[int] = None
    weight: Optional[int] = None
    tier: Optional[OutcomeTier] = None
    conditions: list[Condition]
    cost_effects: list[Effect] = strawberry.field(default_factory=list)
    effects: list[Effect]

@strawberry.type
class RollTable:
    """A reusable roll table whose entries execute effects when selected."""
    id: strawberry.ID
    name: str
    universe: str = ""
    life_path: Optional[str] = None
    scheme: RollTableScheme
    roll_source: RollSource = RollSource.FIXED_DIE
    trait_dice_count: int = 1
    die: DieType
    check: Optional[RollTableCheck] = None
    entries: list[RollTableEntry]
    # Names the table resolves for itself before an entry's effects run — the
    # declaration an SFX already has (B164, route 2). Ambient facts (the term's
    # faction, this table's path faction, the roll) exist without declaring anything.
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
    label: str = ""
    description: str = ""
    min_value: Optional[int] = None
    max_value: Optional[int] = None
    weight: Optional[int] = None
    tier: Optional[OutcomeTier] = None
    conditions: list[ConditionInput] = strawberry.field(default_factory=list)
    cost_effects: list[EffectInput] = strawberry.field(default_factory=list)
    effects: list[EffectInput] = strawberry.field(default_factory=list)

@strawberry.input
class RollTableInput:
    id: str = ""
    name: str = ""
    universe: str = ""
    life_path: Optional[str] = None
    scheme: RollTableScheme = RollTableScheme.RANGE
    roll_source: RollSource = RollSource.FIXED_DIE
    trait_dice_count: int = 1
    die: DieType = DieType.D6
    check: Optional[RollTableCheckInput] = None
    entries: list[RollTableEntryInput] = strawberry.field(default_factory=list)
    bound_variables: list[BoundVariableInput] = strawberry.field(default_factory=list)
