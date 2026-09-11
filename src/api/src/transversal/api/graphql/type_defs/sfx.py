"""Sfx — split out of src/api/src/transversal/api/graphql/types.py."""

import strawberry

from enum import Enum
from typing import Optional
from transversal.api.graphql.type_defs.conditions import (
    Condition,
    ConditionInput,
)
from transversal.api.graphql.type_defs.effects import (
    Effect,
    EffectDuration,
    EffectDurationInput,
    EffectInput,
)


class SfxOwnerKind(str, Enum):
    """Every surface that can own SFX ids."""
    TABLE = "table"
    GM = "gm"
    ENTITY = "entity"
    PROJECTION = "projection"
    TRAIT = "trait"
    TRAIT_INSTANCE = "trait_instance"
    TRAIT_SET = "trait_set"

SfxOwnerKindGql = strawberry.enum(SfxOwnerKind)

@strawberry.type
class SfxRef:
    """SFX reference returned by queries."""
    id: strawberry.ID
    name: str
    description: str = ""
    trigger: str = ""
    limit: str = ""
    source_kind: Optional[str] = None
    placement: Optional[str] = None
    arming_scope: Optional[str] = None
    listener_spec: Optional[strawberry.scalars.JSON] = None
    conditions: list[Condition] = strawberry.field(default_factory=list)
    effects: list[Effect] = strawberry.field(default_factory=list)
    duration: Optional[EffectDuration] = None
    # Derived natural-language rules text — see [[SFX Natural Language Plan]].
    card_text: str = ""

@strawberry.input
class SfxInput:
    """Input for creating a new SFX."""
    id: str
    name: str
    description: str = ""
    trigger: str = ""
    limit: str = ""
    source_kind: Optional[str] = None
    placement: Optional[str] = None
    arming_scope: Optional[str] = None
    listener_spec: Optional[strawberry.scalars.JSON] = None
    conditions: list[ConditionInput] = strawberry.field(default_factory=list)
    effects: list[EffectInput] = strawberry.field(default_factory=list)
    duration: Optional[EffectDurationInput] = None

@strawberry.input
class SfxUpdateInput:
    """Input for updating an existing SFX."""
    id: strawberry.ID
    name: Optional[str] = None
    description: Optional[str] = None
    trigger: Optional[str] = None
    limit: Optional[str] = None
    source_kind: Optional[str] = None
    placement: Optional[str] = None
    arming_scope: Optional[str] = None
    listener_spec: Optional[strawberry.scalars.JSON] = None
    conditions: Optional[list[ConditionInput]] = None
    effects: Optional[list[EffectInput]] = None
    duration: Optional[EffectDurationInput] = None

@strawberry.type
class SfxOwnerRef:
    """A flattened owner instance in the SFX ownership manager."""
    owner_type: SfxOwnerKindGql
    owner_id: strawberry.ID
    label: str
    sfx_ids: list[strawberry.ID] = strawberry.field(default_factory=list)

@strawberry.input
class OwnerRefInput:
    """Reference to one owner instance for a batch add/remove operation."""
    owner_type: SfxOwnerKindGql
    owner_id: strawberry.ID
