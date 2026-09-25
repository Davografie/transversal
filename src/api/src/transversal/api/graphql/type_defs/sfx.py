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
    LOCATION = "location"
    PROJECTION = "projection"
    TRAIT = "trait"
    TRAIT_INSTANCE = "trait_instance"
    TRAIT_SET = "trait_set"

SfxOwnerKindGql = strawberry.enum(SfxOwnerKind)

@strawberry.type
class BoundVariable:
    """A named value the rule resolves before it does anything (see § Bound Variables).

    ``spec`` is a targeting path as JSON, the same wire shape ``listenerSpec`` /
    ``acquireSpec`` use. The name is the author's; the path usually starts at
    ``select source``.
    """
    name: str
    spec: Optional[strawberry.scalars.JSON] = None

@strawberry.input
class BoundVariableInput:
    name: str
    spec: Optional[strawberry.scalars.JSON] = None

@strawberry.type
class UnavailableSfx:
    """A rule the sheet lists but cannot offer, and the conditions that stop it.

    Availability answers yes/no, which is how a card ends up greyed with no reason.
    This is the other half: the failing conditions, phrased the way the rule's own
    card phrases them ("you are at Rusted Gate", "Fire is rated ≥ d8"). Only
    *static* conditions can appear — a context-gated one is unknown until it fires,
    not false, so it never greys a rule.
    """
    sfx_id: strawberry.ID
    reasons: list[str] = strawberry.field(default_factory=list)

@strawberry.type
class SfxRef:
    """SFX reference returned by queries."""
    id: strawberry.ID
    name: str
    description: str = ""
    trigger: str = ""
    limit: str = ""
    source_kind: Optional[str] = None
    # Owner surfaces this SFX may be attached to (from its declared source kind).
    # The ownership picker filters on it, so a rule that can't live somewhere is
    # never offered there. Empty for old payloads.
    owner_surfaces: list[str] = strawberry.field(default_factory=list)
    placement: Optional[str] = None
    arming_scope: Optional[str] = None
    listener_spec: Optional[strawberry.scalars.JSON] = None
    acquire_spec: Optional[strawberry.scalars.JSON] = None
    # The rule applies to the surfaces its acquisition path targets without being
    # learned first (B131) — the trait that declares it in `possibleSfxIds` simply
    # has it. False is the default and what every older payload means.
    implicit: bool = False
    # Values the rule names and resolves for itself, before the conditions run.
    bound_variables: list[BoundVariable] = strawberry.field(default_factory=list)
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
    acquire_spec: Optional[strawberry.scalars.JSON] = None
    implicit: bool = False
    bound_variables: list[BoundVariableInput] = strawberry.field(default_factory=list)
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
    acquire_spec: Optional[strawberry.scalars.JSON] = None
    implicit: Optional[bool] = None
    # ``None`` = leave as stored; ``[]`` = the author removed them all. The
    # distinction matters: a save that cannot express "none left" silently keeps
    # deleted variables alive.
    bound_variables: Optional[list[BoundVariableInput]] = None
    conditions: Optional[list[ConditionInput]] = None
    effects: Optional[list[EffectInput]] = None
    duration: Optional[EffectDurationInput] = None

@strawberry.type
class SfxOwnerRef:
    """A flattened owner instance in the SFX ownership manager."""
    owner_type: SfxOwnerKindGql
    owner_id: strawberry.ID
    label: str
    # The entity's own type ("character"/"gmc"/"faction"/"asset"/"universe"/
    # "location"), so an owner picker can label and filter rows. "" for surfaces
    # where it doesn't apply (traits, projections, buckets).
    entity_type: str = ""
    sfx_ids: list[strawberry.ID] = strawberry.field(default_factory=list)

@strawberry.type
class PlaceSfxRules:
    """The rules one place lends to whoever is standing in it.

    The audience half of a place-owned rule: the place owns them, the occupants
    may press them, and nothing is attached to anybody. Grouped by place so the
    sheet can name where they come from.
    """
    location_id: strawberry.ID
    location_name: str
    sfx_ids: list[strawberry.ID] = strawberry.field(default_factory=list)


@strawberry.input
class OwnerRefInput:
    """Reference to one owner instance for a batch add/remove operation."""
    owner_type: SfxOwnerKindGql
    owner_id: strawberry.ID
