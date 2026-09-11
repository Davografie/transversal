"""Effects — split out of src/api/src/transversal/api/graphql/types.py."""

import strawberry

from typing import Optional
from transversal.api.graphql.type_defs.conditions import (
    Condition,
    ConditionInput,
)
from transversal.api.graphql.type_defs.enums import (
    EffectTimingEnum,
    TimerCombineGql,
)


@strawberry.type
class Timer:
    event: str = "scene"
    remaining: int = 0

@strawberry.input
class TimerInput:
    event: str = "scene"
    remaining: int = 0

@strawberry.type
class EffectDuration:
    timers: list[Timer] = strawberry.field(default_factory=list)
    combine: TimerCombineGql = TimerCombineGql.FIRST_TO_FIRE

@strawberry.input
class EffectDurationInput:
    timers: list[TimerInput] = strawberry.field(default_factory=list)
    combine: TimerCombineGql = TimerCombineGql.FIRST_TO_FIRE

@strawberry.type
class Effect:
    """A single operational effect — shared by SFX and life-path consequences."""
    timing: EffectTimingEnum
    type: str
    action: str
    target: str = ""
    entity: str = ""
    result: Optional[str] = None
    target_scope: Optional[str] = None
    entity_scope: Optional[str] = None
    target_filter: Optional[strawberry.scalars.JSON] = None
    die_filter: Optional[strawberry.scalars.JSON] = None
    negative: bool = False
    context: Optional[strawberry.scalars.JSON] = None
    duration: Optional[EffectDuration] = None
    target_spec: Optional[strawberry.scalars.JSON] = None
    entity_spec: Optional[strawberry.scalars.JSON] = None
    refs: Optional[strawberry.scalars.JSON] = None
    conditions: list[Condition] = strawberry.field(default_factory=list)

@strawberry.input
class EffectInput:
    timing: EffectTimingEnum = EffectTimingEnum.IMMEDIATE
    type: str = ""
    action: str = ""
    target: str = ""
    entity: str = ""
    result: Optional[str] = None
    target_scope: Optional[str] = None
    entity_scope: Optional[str] = None
    target_filter: Optional[strawberry.scalars.JSON] = None
    die_filter: Optional[strawberry.scalars.JSON] = None
    negative: bool = False
    context: Optional[strawberry.scalars.JSON] = None
    duration: Optional[EffectDurationInput] = None
    target_spec: Optional[strawberry.scalars.JSON] = None
    entity_spec: Optional[strawberry.scalars.JSON] = None
    refs: Optional[strawberry.scalars.JSON] = None
    conditions: list[ConditionInput] = strawberry.field(default_factory=list)

@strawberry.type
class ScheduledEvent:
    """A running, centrally-scheduled timer and the effect it will fire."""
    id: strawberry.ID
    target_type: str = "entity"
    target_id: str = ""
    effect: Effect
    timers: list[Timer] = strawberry.field(default_factory=list)
    combine: TimerCombineGql = TimerCombineGql.FIRST_TO_FIRE
    source_sfx_id: Optional[str] = None

@strawberry.type
class ConsequenceOption:
    """A selectable entry in the post-roll consequence menu."""
    id: strawberry.ID
    label: str
    side: str = "player"
    effects: list[Effect] = strawberry.field(default_factory=list)
    source: str = "base"

@strawberry.input
class ConsequenceOptionInput:
    id: str
    label: str
    side: str = "player"
    effects: list[EffectInput] = strawberry.field(default_factory=list)

@strawberry.type
class PendingChoiceRef:
    """An effect target that must be resolved before the effect can apply."""
    index: int
    kind: str
    scope: Optional[str] = None
    field: str = "target"  # which Effect field holds this target ("target" | "entity")
    filter: Optional[strawberry.scalars.JSON] = None  # candidate-field predicates (e.g. {"starter_location": true})
    effect: Effect

@strawberry.type
class EffectApplicationResult:
    """Outcome of applying a set of effects, plus any unresolved targets."""
    applied: list[str]
    pending_choices: list[PendingChoiceRef] = strawberry.field(default_factory=list)
    structured: list[strawberry.scalars.JSON] = strawberry.field(default_factory=list)

@strawberry.input
class TargetChoiceAnswerInput:
    """A user's answer to one mid-path ``choose`` step (by step index)."""
    step_index: int
    ids: list[str] = strawberry.field(default_factory=list)

@strawberry.input
class EffectTargetResolutionInput:
    """A single resolved target for a previously-pending effect."""
    effect: EffectInput
    target: str = ""
    field: str = "target"  # "target" | "entity" | "refs.<name>"
    answers: list[TargetChoiceAnswerInput] = strawberry.field(default_factory=list)
    source_kind: str = ""
    source_id: str = ""
    source_sfx_id: str = ""
    # Immediate effects that were deferred behind this choice (sequential
    # execution) — applied in order after the resolved effect.
    continuation: list[EffectInput] = strawberry.field(default_factory=list)

@strawberry.type
class EffectFieldDef:
    """A single input field required by an effect action."""
    name: str
    label: str
    field_type: str
    required: bool = True
    default: Optional[str] = None
    options: list[str] = strawberry.field(default_factory=list)
    # Parallel to ``options`` when the option *value* is not what a person should
    # read (a universe key like ``three_realms`` vs the name "Three Realms").
    option_labels: list[str] = strawberry.field(default_factory=list)
    # Name of a ref that supersedes this field once authored (it is the fallback
    # form); the editor hides it but keeps its stored value.
    hidden_when_ref: str = ""

@strawberry.type
class RefDef:
    """A named reference an effect action declares (the multi-target model)."""
    name: str
    label: str
    element: str

@strawberry.type
class EffectActionMeta:
    """Metadata for one effect action the editor can create."""
    action_id: str
    label: str
    description: str
    category: str
    effect_type: str
    effect_action: str
    group: str = ""
    valid_timings: list[str]
    fields: list[EffectFieldDef] = strawberry.field(default_factory=list)
    context_fields: list[EffectFieldDef] = strawberry.field(default_factory=list)
    supports_duration: bool = False
    supports_polarity: bool = False
    supports_return_exit: bool = False
    implicit_target: Optional[str] = None
    implicit_result: Optional[str] = None
    implicit_timing: Optional[str] = None
    requires_choice: bool = False
    target_kind: Optional[str] = None
    refs: list[RefDef] = strawberry.field(default_factory=list)
