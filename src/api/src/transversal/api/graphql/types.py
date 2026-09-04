"""Strawberry GraphQL types — mapping domain models to GraphQL schema."""

import strawberry
from enum import Enum
from typing import Optional

from transversal.domain import (
    DieType as DomainDieType,
    RatingType as DomainRatingType,
    EntityType as DomainEntityType,
    TransversalType as DomainTransversalType,
    Polarity as DomainPolarity,
    ConditionType as DomainConditionType,
    EffectTiming as DomainEffectTiming,
    MessageKind as DomainMessageKind,
    OutcomeTier as DomainOutcomeTier,
    RollTableScheme as DomainRollTableScheme,
    RollSource as DomainRollSource,
    TimerCombine as DomainTimerCombine,
    DiscoveryBlock,
    LifePath,
)


# ── Enums ────────────────────────────────────────────

DieType = strawberry.enum(DomainDieType)
RatingType = strawberry.enum(DomainRatingType)
EntityType = strawberry.enum(DomainEntityType)
TransversalTypeEnum = strawberry.enum(DomainTransversalType)
Polarity = strawberry.enum(DomainPolarity)
EffectTimingEnum = strawberry.enum(DomainEffectTiming)
MessageKind = strawberry.enum(DomainMessageKind)
OutcomeTier = strawberry.enum(DomainOutcomeTier)
RollTableScheme = strawberry.enum(DomainRollTableScheme)
RollSource = strawberry.enum(DomainRollSource)
ConditionType = strawberry.enum(DomainConditionType)
TimerCombineGql = strawberry.enum(DomainTimerCombine)


# ── Conditions ────────────────────────────────────────

@strawberry.type
class Condition:
    """A configurable, automatically-evaluated gate or limit."""
    type: ConditionType
    subject: str = ""
    target: str = ""
    value: Optional[str] = None
    operator: str = ">="
    narrative: str = ""
    spec: Optional[strawberry.scalars.JSON] = None


@strawberry.input
class ConditionInput:
    type: ConditionType = ConditionType.ALWAYS
    subject: str = ""
    target: str = ""
    value: Optional[str] = None
    operator: str = ">="
    narrative: str = ""
    spec: Optional[strawberry.scalars.JSON] = None


# ── SFX ownership ─────────────────────────────────────

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


# ── Trait Display Name ───────────────────────────────

@strawberry.type
class TraitDisplayName:
    """Dynamic display name for a trait, keyed by universe and rating."""
    name: str
    universe: str
    ratings: list[list[DieType]]


@strawberry.input
class TraitDisplayNameInput:
    """Input for a trait display name entry."""
    name: str
    universe: str = ""
    ratings: list[list[DieType]] = strawberry.field(default_factory=list)


# ── Trait Registry ───────────────────────────────────

@strawberry.type
class TraitRef:
    id: strawberry.ID
    name: str
    universes: list[str]
    traitset_id: strawberry.ID
    default_die_type: DieType
    default_rating_type: RatingType
    possible_sfx_ids: list[strawberry.ID]
    default_sfx_ids: list[strawberry.ID] = strawberry.field(default_factory=list)
    possible_subtrait_ids: list[strawberry.ID] = strawberry.field(default_factory=list)
    possible_subtraitset_ids: list[strawberry.ID] = strawberry.field(default_factory=list)
    location_restricted: bool
    default_ego: bool = False
    polarity: Optional[Polarity] = None
    display_names: list[TraitDisplayName] = strawberry.field(default_factory=list)


@strawberry.type
class TraitSetRef:
    id: strawberry.ID
    name: str
    universes: list[str]
    entity_types: list[EntityType]
    order: int = 0
    limit: int = 1
    polarity: Optional[Polarity] = None

    @strawberry.field
    def traits(self, info: strawberry.Info) -> list["TraitRef"]:
        from transversal.services.entity_manager import EntityManager
        em: EntityManager = info.context["entity_manager"]
        traits = em.repo.get_traits_by_traitset(self.id)
        return [
            TraitRef(
                id=t.id, name=t.name, universes=t.universes,
                traitset_id=t.traitset_id, default_die_type=t.default_die_type,
                default_rating_type=t.default_rating_type,
                possible_sfx_ids=t.possible_sfx_ids,
                default_sfx_ids=t.default_sfx_ids,
                possible_subtrait_ids=t.possible_subtrait_ids,
                possible_subtraitset_ids=t.possible_subtraitset_ids,
                location_restricted=t.location_restricted,
                default_ego=t.default_ego,
                polarity=t.polarity,
                display_names=[
                    TraitDisplayName(name=dn.name, universe=dn.universe,
                                     ratings=dn.ratings)
                    for dn in t.display_names
                ],
            )
            for t in traits
        ]


# ── SFX Registry ──────────────────────────────────────

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
class TargetCandidate:
    """A selectable target returned by the choose/random candidate resolver."""
    id: strawberry.ID
    name: str
    universe: str = ""
    subtitle: str = ""


@strawberry.type
class FilterFieldOption:
    """A candidate field the author may filter on, plus editor metadata."""
    field: str
    label: str
    value_type: str = "boolean"
    kinds: list[str] = strawberry.field(default_factory=list)
    options: list[str] = strawberry.field(default_factory=list)


@strawberry.type
class ScopeVariable:
    """A ``{variable}`` token an SFX author may use, plus its data type."""
    name: str
    type: str  # "number" | "entity" | "die" | "string"


@strawberry.type
class EffectVariable:
    """A typed output variable an effect exposes for later effects/steps."""
    name: str
    element: str
    cardinality: str = "one"  # "one" | "many"


@strawberry.type
class TriggerOption:
    """One activation trigger selectable in the SFX editor."""
    value: str
    label: str
    group: str = "auto"  # "auto" | "manual" | "menu"


@strawberry.type
class ConditionTypeOption:
    """One condition type selectable in the SFX editor, plus target hints."""
    value: str
    label: str
    needs_target: bool = False
    target_placeholder: str = ""
    target_kind: str = ""
    value_kind: str = ""
    operators: list[str] = strawberry.field(default_factory=list)
    target_options: list[str] = strawberry.field(default_factory=list)
    uses_spec: bool = False


@strawberry.type
class TargetCatalogElement:
    """A kind of game object a targeting spec can resolve to."""
    name: str
    label: str


@strawberry.type
class TargetCatalogEdge:
    """A named navigation hop from one element type to another."""
    name: str
    source: str
    targets: list[str]
    cardinality: str  # "one" | "many"
    label: str = ""


@strawberry.type
class TargetCatalogField:
    """A comparable/aggregatable scalar field on an element type."""
    element: str
    name: str
    type: str  # "int" | "number" | "die" | "string"
    options: list[str] = strawberry.field(default_factory=list)
    operators: list[str] = strawberry.field(default_factory=list)
    references: str = ""  # element type this id field points at (e.g. traitset)


@strawberry.type
class TargetCatalogAggregation:
    """A collapse of a collection to a scalar."""
    name: str
    label: str
    output: str  # "int" | "number" | "same"
    needs_field: bool


@strawberry.type
class TargetCatalogCollection:
    """A context collection a spec may seed from via ``select``."""
    name: str
    element: str
    label: str
    singular: bool = False


@strawberry.type
class SourceKindOption:
    """A declarative SFX source kind (owner type + its exposed variable)."""
    value: str
    label: str
    element: str
    variable: str
    owner_surface: str


@strawberry.type
class TargetCatalog:
    """The full declarative targeting catalog, consumed by the wizard."""
    elements: list[TargetCatalogElement]
    edges: list[TargetCatalogEdge]
    fields: list[TargetCatalogField]
    aggregations: list[TargetCatalogAggregation]
    collections: list[TargetCatalogCollection]
    source_kinds: list[SourceKindOption]


@strawberry.input
class TargetSpecStepInput:
    """One step of a targeting spec (kind discriminates the relevant fields)."""
    kind: str  # "select" | "filter" | "navigate" | "aggregate" | "random" | "choose"
    collection: Optional[str] = None
    variable: Optional[str] = None  # for kind == "select" + collection == "variable"
    output: Optional[str] = None  # bound variable name this step exposes
    field: Optional[str] = None
    operator: str = "=="
    value: Optional[strawberry.scalars.JSON] = None
    edge: Optional[str] = None
    dedup: bool = False
    fn: Optional[str] = None
    count: Optional[int] = None  # random/choose: elements to sample (default 1)


@strawberry.input
class TargetSpecInput:
    """An ordered pipeline of targeting steps."""
    steps: list[TargetSpecStepInput] = strawberry.field(default_factory=list)


@strawberry.type
class TargetTraceType:
    """The resolved value type after one spec step (empty = no valid type)."""
    element: str = ""
    cardinality: str = ""  # "one" | "many"


@strawberry.type
class TargetTraceError:
    """A step-level type error."""
    step_index: int
    message: str


@strawberry.type
class TargetTraceResult:
    """The type trace of a spec: the type after each step plus errors."""
    types: list[TargetTraceType]
    errors: list[TargetTraceError]
    valid: bool = False


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
    conditions: list[Condition] = strawberry.field(default_factory=list)
    effects: list[Effect] = strawberry.field(default_factory=list)
    duration: Optional[EffectDuration] = None


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


# ── Roll Tables ─────────────────────────────────────

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


# ── Effects Registry (metadata for the UI) ────────────

@strawberry.type
class EffectFieldDef:
    """A single input field required by an effect action."""
    name: str
    label: str
    field_type: str
    required: bool = True
    default: Optional[str] = None
    options: list[str] = strawberry.field(default_factory=list)


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


@strawberry.input
class TraitInput:
    id: str
    name: str
    universes: list[str] = strawberry.field(default_factory=list)
    traitset_id: strawberry.ID
    default_die_type: DieType = DieType.D6
    default_rating_type: RatingType = RatingType.STATIC
    possible_sfx_ids: list[strawberry.ID] = strawberry.field(default_factory=list)
    possible_subtrait_ids: list[strawberry.ID] = strawberry.field(default_factory=list)
    possible_subtraitset_ids: list[strawberry.ID] = strawberry.field(default_factory=list)
    default_sfx_ids: list[strawberry.ID] = strawberry.field(default_factory=list)
    location_restricted: bool = False
    default_ego: bool = False
    polarity: Optional[Polarity] = None
    display_names: list[TraitDisplayNameInput] = strawberry.field(default_factory=list)


@strawberry.input
class TraitUpdateInput:
    name: Optional[str] = None
    universes: Optional[list[str]] = None
    traitset_id: Optional[strawberry.ID] = None
    default_die_type: Optional[DieType] = None
    default_rating_type: Optional[RatingType] = None
    possible_sfx_ids: Optional[list[strawberry.ID]] = None
    possible_subtrait_ids: Optional[list[strawberry.ID]] = None
    possible_subtraitset_ids: Optional[list[strawberry.ID]] = None
    default_sfx_ids: Optional[list[strawberry.ID]] = None
    location_restricted: Optional[bool] = None
    default_ego: Optional[bool] = None
    polarity: Optional[Polarity] = None
    clear_polarity: bool = False
    display_names: Optional[list[TraitDisplayNameInput]] = None


# ── Trait Setting (edge) ─────────────────────────────

@strawberry.type
class TraitSetting:
    id: strawberry.ID
    entity_id: strawberry.ID
    trait_id: strawberry.ID
    traitset_id: strawberry.ID
    rating_type: RatingType
    dice: list[DieType]
    spent_dice: list[DieType] = strawberry.field(default_factory=list)
    capacity: Optional[list[DieType]] = None
    polarity: Polarity
    statement: str
    notes: str = ""
    from_type: str = "entity"  # "entity" | "projection" | "relationship" | "traitsetting"
    projection_id: Optional[strawberry.ID] = None
    parent_traitsetting_id: Optional[strawberry.ID] = None
    sfx_ids: list[strawberry.ID]
    known_to: list[strawberry.ID] = strawberry.field(default_factory=list)
    enabled: bool = True
    # Relationship-anchored traits carry their edge's contact for display.
    relationship_contact_id: Optional[strawberry.ID] = None
    relationship_contact_name: Optional[str] = None
    relationship_contact_type: Optional[str] = None
    relationship_type: Optional[str] = None

    @strawberry.field
    def ego(self, info: strawberry.Info) -> bool:
        """Entity-anchored traits (from_type='entity') are ego; others morph.

        Relationship traits are ego only when their edge is entity→entity
        (both soul-level); any projection endpoint makes them morph.
        """
        if self.from_type == "entity":
            return True
        if self.from_type == "relationship":
            em = info.context["entity_manager"]
            edge = em.repo.get_relationship_by_key(str(self.entity_id))
            if edge is not None:
                return (
                    str(edge.get("_from", "")).startswith("entities/")
                    and str(edge.get("_to", "")).startswith("entities/")
                )
            return False
        return False

    @strawberry.field
    def die_type(self) -> DieType:
        """Derive die_type from the first die in dice, or D6 if empty."""
        if self.dice:
            return self.dice[0]
        return DieType.D6

    @strawberry.field
    def rating(self) -> str:
        """Human-readable rating string derived from dice."""
        from transversal.domain import dice_list_to_rating
        return dice_list_to_rating(self.dice)

    @strawberry.field
    def name(self, info: strawberry.Info) -> str:
        """Resolved display name — dynamic per-universe/per-rating if configured."""
        from transversal.domain import resolve_trait_display_name
        em = info.context["entity_manager"]
        trait = em.repo.get_trait(self.trait_id)
        if not trait:
            return ""
        entity = em.repo.get_entity(self.entity_id)
        universe = entity.current_universe if entity else ""
        return resolve_trait_display_name(trait, self.dice, universe)

    @strawberry.field
    def traitset_name(self, info: strawberry.Info) -> str:
        from transversal.services.entity_manager import EntityManager
        em = info.context["entity_manager"]
        ts = em.repo.get_traitset_by_id(self.traitset_id)
        return ts.name if ts else ""

    @strawberry.field
    def universe(self, info: strawberry.Info) -> str:
        from transversal.services.entity_manager import EntityManager
        em = info.context["entity_manager"]
        trait = em.repo.get_trait(self.trait_id)
        return trait.universes[0] if trait and trait.universes else ""

    @strawberry.field
    def traitset_order(self, info: strawberry.Info) -> int:
        from transversal.services.entity_manager import EntityManager
        em = info.context["entity_manager"]
        ts = em.repo.get_traitset_by_id(self.traitset_id)
        return ts.order if ts else 0

    @strawberry.field
    def traitset_limit(self, info: strawberry.Info) -> int:
        """Effective trait-set limit: per-entity override, else registry default."""
        em = info.context["entity_manager"]
        repo = em.repo
        ts = repo.get_traitset_by_id(self.traitset_id)
        default = ts.limit if ts else 1
        for tss in repo.get_traitsetsettings_for_entity(str(self.entity_id)):
            if tss.traitset_id == self.traitset_id and tss.from_type == "entity" and tss.limit is not None:
                return tss.limit
        return default

    @strawberry.field
    def transfer_flags(self, info: strawberry.Info) -> strawberry.scalars.JSON:
        """Resolve transfer flags from trait registry (trait → traitset fallback)."""
        from transversal.domain import TransferFlags as DomainTransferFlags
        em = info.context["entity_manager"]
        trait = em.repo.get_trait(self.trait_id)
        if trait and trait.transfer_flags:
            return {
                "teachable": trait.transfer_flags.teachable,
                "giftable": trait.transfer_flags.giftable,
                "takable": trait.transfer_flags.takable,
            }
        if trait:
            ts = em.repo.get_traitset_by_id(trait.traitset_id)
            if ts and ts.transfer_flags:
                return {
                    "teachable": ts.transfer_flags.teachable,
                    "giftable": ts.transfer_flags.giftable,
                    "takable": ts.transfer_flags.takable,
                }
        return {"teachable": False, "giftable": False, "takable": False}

    @strawberry.field
    def possible_sfx_ids(self, info: strawberry.Info) -> list[strawberry.ID]:
        from transversal.services.entity_manager import EntityManager
        em = info.context["entity_manager"]
        trait = em.repo.get_trait(self.trait_id)
        return trait.possible_sfx_ids if trait else []

    @strawberry.field
    def possible_subtrait_ids(self, info: strawberry.Info) -> list[strawberry.ID]:
        """Resolved sub-traits that may be nested under this trait (ids + set refs)."""
        from transversal.services.entity_manager import EntityManager
        em = info.context["entity_manager"]
        trait = em.repo.get_trait(self.trait_id)
        return em.repo.resolve_possible_subtrait_ids(trait) if trait else []

    @strawberry.field
    def sub_trait_settings(self, info: strawberry.Info) -> list["TraitSetting"]:
        """Sub-trait settings nested directly under this trait setting."""
        from transversal.services.entity_manager import EntityManager
        em = info.context["entity_manager"]
        return [
            _gql_trait_setting(s)
            for s in em.repo.get_sub_traitsettings(str(self.id))
        ]


@strawberry.input
class TraitSettingInput:
    trait_id: strawberry.ID
    traitset_id: strawberry.ID
    dice: list[DieType] = strawberry.field(default_factory=list)
    rating_type: RatingType = RatingType.STATIC
    capacity: Optional[list[DieType]] = None
    polarity: Optional[Polarity] = None
    statement: str = ""
    notes: str = ""
    from_type: Optional[str] = None  # "entity" | "projection" | "traitsetting"
    projection_id: Optional[strawberry.ID] = None
    parent_traitsetting_id: Optional[strawberry.ID] = None
    sfx_ids: list[strawberry.ID] = strawberry.field(default_factory=list)
    enabled: bool = True


@strawberry.input
class TraitSettingUpdateInput:
    dice: Optional[list[DieType]] = None
    rating_type: Optional[RatingType] = None
    capacity: Optional[list[DieType]] = None
    polarity: Optional[Polarity] = None
    statement: Optional[str] = None
    notes: Optional[str] = None
    from_type: Optional[str] = None  # "entity" | "projection" | "traitsetting"
    projection_id: Optional[strawberry.ID] = None
    parent_traitsetting_id: Optional[strawberry.ID] = None
    sfx_ids: Optional[list[strawberry.ID]] = None
    known_to: Optional[list[strawberry.ID]] = None
    enabled: Optional[bool] = None


# ── Projection ───────────────────────────────────────

@strawberry.type
class Projection:
    id: strawberry.ID
    entity_id: strawberry.ID
    origin_universe: str = ""
    universe: str
    name: str = ""
    background_image: Optional[str] = None
    current_location: Optional[str] = None
    transversal_type: TransversalTypeEnum
    sfx_ids: list[strawberry.ID] = strawberry.field(default_factory=list)

    @strawberry.field
    def sheet_image(self, info: strawberry.Info) -> Optional[str]:
        """This body's sheet role image (with entity-level fallback)."""
        em = info.context["entity_manager"]
        return em.repo.resolve_role_image(
            str(self.entity_id), "sheet", str(self.id), "Small"
        )


# ── Entity ───────────────────────────────────────────

@strawberry.type
class Zone:
    name: str
    background_image: Optional[str] = None
    location_id: Optional[str] = None
    x: float = 50.0
    y: float = 50.0


@strawberry.type
class Attunement:
    universe: str
    scope: str
    until: Optional[EffectTimingEnum] = None
    source_sfx_id: Optional[str] = None


@strawberry.type
class PendingTerm:
    """In-progress life path term checkpoint."""
    faction_id: str
    path_id: str
    current_table_id: str
    continuation: list[str]


def _gql_trait_setting(s, contact: dict | None = None) -> TraitSetting:
    """Build a GQL TraitSetting from a domain setting + optional relationship contact."""
    contact = contact or {}
    return TraitSetting(
        id=s.id, entity_id=s.entity_id, trait_id=s.trait_id,
        traitset_id=s.traitset_id,
        rating_type=s.rating_type, dice=s.dice,
        spent_dice=s.spent_dice,
        capacity=s.capacity,
        polarity=s.polarity,
        statement=s.statement,
        notes=s.notes,
        from_type=s.from_type, projection_id=s.projection_id,
        parent_traitsetting_id=s.parent_traitsetting_id,
        sfx_ids=s.sfx_ids,
        known_to=s.known_to,
        relationship_contact_id=contact.get("contact_id"),
        relationship_contact_name=contact.get("contact_name"),
        relationship_contact_type=contact.get("contact_type"),
        relationship_type=contact.get("edge_type"),
    )


@strawberry.type
class TraitSetSetting:
    """Per-entity trait-set settings (SFX + limit override)."""
    id: strawberry.ID
    entity_id: strawberry.ID
    traitset_id: strawberry.ID
    from_type: str = "entity"
    projection_id: Optional[strawberry.ID] = None
    sfx_ids: list[strawberry.ID] = strawberry.field(default_factory=list)
    limit: Optional[int] = None


@strawberry.type
class Entity:
    id: strawberry.ID
    type: EntityType
    name: str
    razmerit: int
    total_dice_bonus: int = 0
    effect_dice_bonus: int = 0
    current_universe: str
    current_location: Optional[str] = None
    current_projection: Optional[str] = None
    hidden: bool = False
    unpublished: bool = False
    known_to: list[strawberry.ID] = strawberry.field(default_factory=list)
    sfx_ids: list[strawberry.ID] = strawberry.field(default_factory=list)
    _background_image: strawberry.Private[Optional[str]] = None
    _sheet_portrait: strawberry.Private[Optional[str]] = None
    zones: list[Zone] = strawberry.field(default_factory=list)
    map_x: Optional[float] = None
    map_y: Optional[float] = None
    overlay: Optional[str] = None
    starter_location: bool = False
    nav_positions: str = "{}"
    node_ids: list[strawberry.ID] = strawberry.field(default_factory=list)
    owned_by: Optional[str] = None
    attunements: list[Attunement] = strawberry.field(default_factory=list)
    lora_config: Optional[str] = None  # JSON string: {"CHARACTER": ["lora1"], ...}

    @strawberry.field
    def projections(self, info: strawberry.Info) -> list[Projection]:
        from transversal.services.entity_manager import EntityManager
        em = info.context["entity_manager"]
        projs = em.get_projections(self.id)
        return [
            Projection(id=p.id, entity_id=p.entity_id, origin_universe=p.origin_universe,
                       universe=p.universe, name=p.name, background_image=p.background_image,
                       current_location=p.current_location, transversal_type=p.transversal_type,
                       sfx_ids=p.sfx_ids)
            for p in projs
        ]

    @strawberry.field
    def trait_set_settings(self, info: strawberry.Info) -> list[TraitSetSetting]:
        """This entity's per-trait-set settings (SFX + limit override)."""
        from transversal.services.entity_manager import EntityManager
        em = info.context["entity_manager"]
        return [
            TraitSetSetting(
                id=tss.id, entity_id=tss.entity_id, traitset_id=tss.traitset_id,
                from_type=tss.from_type, projection_id=tss.projection_id,
                sfx_ids=tss.sfx_ids, limit=tss.limit,
            )
            for tss in em.repo.get_traitsetsettings_for_entity(str(self.id))
        ]

    @strawberry.field
    def background_image(self, info: strawberry.Info) -> Optional[str]:
        em = info.context["entity_manager"]
        url = em.repo.resolve_role_image(str(self.id), "background", None, "Large")
        return url if url is not None else self._background_image

    @strawberry.field
    def sheet_portrait(self, info: strawberry.Info) -> Optional[str]:
        em = info.context["entity_manager"]
        # Sheet portraits render at ~40px — serve the small variant.
        url = em.repo.resolve_role_image(str(self.id), "sheet", None, "Small")
        if url is not None:
            return url
        # Fall back to background image
        return self.background_image(info)

    # Canonical role-based media resolver. The only valid roles are
    # "background", "sheet", and "navdot" — resolved from the image's roles
    # tags in entity_images. ``projection_id`` scopes resolution to a body
    # (its own image first, then entity-level fallback); when omitted only
    # entity-level images are considered. There is deliberately no fallback to
    # the legacy denormalized background_image field.
    _ROLE_VARIANT = {"background": "Large", "sheet": "Small", "navdot": "Large"}

    @strawberry.field
    def image(self, info: strawberry.Info, role: str, projection_id: Optional[strawberry.ID] = None) -> Optional[str]:
        variant = self._ROLE_VARIANT.get(role)
        if variant is None:
            return None
        em = info.context["entity_manager"]
        # When no explicit projection is given, resolve through the entity's
        # active body (current_projection) so callers asking for "the entity's"
        # image get the active body's image first, falling back to entity level.
        pid = str(projection_id) if projection_id else (self.current_projection or None)
        return em.repo.resolve_role_image(str(self.id), role, pid, variant)

    @strawberry.field
    def pending_term(self, info: strawberry.Info) -> Optional[PendingTerm]:
        """The entity's in-progress life path term checkpoint, if any."""
        em = info.context["entity_manager"]
        entity = em.repo.get_entity(str(self.id))
        if entity is None or entity.pending_term is None:
            return None
        pt = entity.pending_term
        return PendingTerm(
            faction_id=pt.faction_id,
            path_id=pt.path_id,
            current_table_id=pt.current_table_id,
            continuation=pt.continuation,
        )

    @strawberry.field
    def trait_settings(self, info: strawberry.Info) -> list[TraitSetting]:
        from transversal.services.entity_manager import EntityManager
        em = info.context["entity_manager"]
        settings = em.get_traitsettings(self.id)
        result = [_gql_trait_setting(s) for s in settings]
        for enriched in em.repo.get_relationship_traitsettings_for_entity(str(self.id)):
            result.append(_gql_trait_setting(enriched["setting"], enriched))
        return result

    @strawberry.field
    def effective_trait_settings(self, info: strawberry.Info) -> list[TraitSetting]:
        from transversal.services.entity_manager import EntityManager
        em = info.context["entity_manager"]
        settings = em.get_effective_traitsettings(str(self.id))
        result = [_gql_trait_setting(s) for s in settings]
        # Relationship traits are universe-agnostic — always include them.
        for enriched in em.repo.get_relationship_traitsettings_for_entity(str(self.id)):
            result.append(_gql_trait_setting(enriched["setting"], enriched))
        return result


@strawberry.input
class CreateEntityInput:
    name: str
    type: EntityType
    universe: str
    location: Optional[str] = None
    razmerit: int = 0
    starter_location: bool = False


@strawberry.input
class UpdateEntityInput:
    id: strawberry.ID
    name: Optional[str] = None
    razmerit: Optional[int] = None
    current_universe: Optional[str] = None
    current_location: Optional[str] = None
    hidden: Optional[bool] = None
    unpublished: Optional[bool] = None
    known_to: Optional[list[str]] = None
    background_image: Optional[str] = None
    overlay: Optional[str] = None
    starter_location: Optional[bool] = None
    nav_positions: Optional[str] = None
    owned_by: Optional[str] = None
    suitable_life_path_ids: Optional[list[str]] = None
    lora_config: Optional[str] = None


# ── Razmerit ─────────────────────────────────────────

@strawberry.type
class RazmeritResult:
    from_id: strawberry.ID
    from_balance: int
    to_id: Optional[strawberry.ID] = None
    to_balance: Optional[int] = None
    amount: int
    reason: str


# ── Character View ───────────────────────────────────

@strawberry.type
class CharacterView:
    entity: Entity
    projections: list[Projection]
    trait_settings: list[TraitSetting]


# ── Messages ──────────────────────────────────────────

@strawberry.type
class Message:
    """A persistent message between entities, with resolved relationship info."""
    id: strawberry.ID
    sender_entity_id: strawberry.ID
    recipient_entity_id: strawberry.ID
    kind: MessageKind = MessageKind.LETTER
    title: str = ""
    body: str = ""
    images: list[str] = strawberry.field(default_factory=list)
    created_at: str = ""
    relationship_description: str = ""  # resolved from associate edge at query time
    after_ids: list[strawberry.ID] = strawberry.field(default_factory=list)
    threads: list[str] = strawberry.field(default_factory=list)


@strawberry.input
class SendMessageInput:
    """Input for sending a message to another entity."""
    sender_entity_id: strawberry.ID
    recipient_entity_id: strawberry.ID
    kind: MessageKind = MessageKind.LETTER
    title: str = ""
    body: str = ""
    images: list[str] = strawberry.field(default_factory=list)
    after_ids: list[strawberry.ID] = strawberry.field(default_factory=list)
    threads: list[str] = strawberry.field(default_factory=list)


@strawberry.input
class JournalEntryInput:
    """Input for adding a personal journal entry (self-referential, GM-visible)."""
    entity_id: strawberry.ID
    title: str = ""
    body: str = ""
    images: list[str] = strawberry.field(default_factory=list)
    after_ids: list[strawberry.ID] = strawberry.field(default_factory=list)
    threads: list[str] = strawberry.field(default_factory=list)


@strawberry.input
class UpdateMessageInput:
    """Input for updating a message's after_ids and/or threads."""
    id: strawberry.ID
    after_ids: Optional[list[strawberry.ID]] = None
    threads: Optional[list[str]] = None


@strawberry.type
class HistoricalRecord:
    """An append-only historical event for an entity."""
    id: strawberry.ID
    entity_id: strawberry.ID
    record_type: str = "roll_table"
    universe: str = ""
    session_id: str = ""
    data: strawberry.scalars.JSON = strawberry.field(default_factory=dict)
    created_at: str = ""


# ── Relationships ─────────────────────────────────────

@strawberry.type
class Relationship:
    """A directional relationship edge between two entities."""
    id: str
    from_entity_id: strawberry.ID
    to_entity_id: strawberry.ID
    type: str
    description: str = ""


@strawberry.input
class CreateRelationshipInput:
    """Input for creating or updating a relationship edge."""
    from_entity_id: strawberry.ID
    to_entity_id: strawberry.ID
    type: str = "associate"
    description: str = ""
    elevated: bool = False  # True → entity→entity (both multiversal); False → projection→projection


@strawberry.input
class DeleteRelationshipInput:
    """Input for deleting a relationship edge."""
    from_entity_id: strawberry.ID
    to_entity_id: strawberry.ID
    type: str = "associate"
    elevated: bool = False


# ── Related Entity ────────────────────────────────────

@strawberry.type
class RelatedEntity:
    """An entity connected via a relationship edge, with portrait."""
    id: strawberry.ID
    name: str
    sheet_portrait: str = ""


# ── Life Paths ─────────────────────────────────────────

@strawberry.type
class DiscoveryBlock:
    at_location: list[str]
    knows_entity: list[str]
    possesses_trait: list[str]
    has_trait_rating: strawberry.scalars.JSON  # dict[str, DieType]
    has_relationship: list[str]


@strawberry.type
class LifePath:
    id: strawberry.ID
    name: str
    universe: str
    description: str
    entry_table_id: str
    discovery: Optional[DiscoveryBlock]

    @strawberry.field
    def faction_ids(self, info: strawberry.Info) -> list[strawberry.ID]:
        """Faction entities that list this life path as suitable (offered)."""
        em = info.context["entity_manager"]
        factions = em.repo.list_entities_by_type(DomainEntityType.FACTION)
        return [
            strawberry.ID(f.id)
            for f in factions
            if str(self.id) in f.suitable_life_path_ids
        ]


@strawberry.type
class LifePathStepResult:
    """Result of resolving one roll-table step in a life path term."""
    done: bool
    applied: list[str]
    pending_choices: list[str]
    mustered: bool
    mishap_muster: bool
    pending_term: Optional[PendingTerm]
    scheduled: int = 0
    error: Optional[str] = None
    table_id: Optional[str] = None
    entry_label: Optional[str] = None


# ── Players ──────────────────────────────────────────

@strawberry.type
class AgencyEdge:
    """A player→entity ownership edge, with its ``main`` flag."""
    entity_id: strawberry.ID
    main: bool = False


@strawberry.type
class Player:
    """A human player's identity + spotlight recency."""
    id: strawberry.ID
    name: str
    role: str = "player"
    last_spotlight_at: Optional[str] = None
    last_main_entity_id: Optional[strawberry.ID] = None
    agency: list[AgencyEdge] = strawberry.field(default_factory=list)

    @strawberry.field
    def main_entity(self, info: strawberry.Info) -> Optional["Entity"]:
        """The player's main entity for the overview (B63).

        Resolves ``last_main_entity_id`` (recency — the main last taken control
        of) when set; otherwise falls back to the player's *designated* main
        (first agency edge flagged ``main``). Only null when the player truly
        has no designated main.
        """
        em = info.context["entity_manager"]
        main_id = str(self.last_main_entity_id) if self.last_main_entity_id else None
        if not main_id:
            main_id = em.repo.get_designated_main(str(self.id))
        if not main_id:
            return None
        entity = em.get(main_id)
        if entity is None:
            return None
        from transversal.api.graphql.schema import _entity_to_gql

        return _entity_to_gql(entity)


@strawberry.input
class SetAgencyMainInput:
    """Flag (or un-flag) an owned entity as a player main."""
    player_id: strawberry.ID
    entity_id: strawberry.ID
    main: bool = True


@strawberry.type
class SupportCharacter:
    """A support character and the main it supports (B57)."""
    entity: Entity
    main: Entity
    main_owner_id: Optional[strawberry.ID] = None
    owner_id: Optional[strawberry.ID] = None
    main_active: bool = False


@strawberry.type
class ActiveMain:
    """A main currently being controlled by its player (B66)."""
    player_id: strawberry.ID
    player_name: str = ""
    main: Entity


@strawberry.type
class PlayerBody:
    """The entity a player is currently controlling (main or SC)."""
    player_id: strawberry.ID
    player_name: str = ""
    entity: Entity


# ── Trait Transfer Result Types ──────────────────────

@strawberry.type
class TeachResult:
    student_trait_setting_id: strawberry.ID
    razmerit_cost: int


@strawberry.type
class GiftResult:
    transferred_trait_id: strawberry.ID
    relationship_created: bool


@strawberry.type
class TakeResult:
    success: bool
    contest_summary: str  # "Kael rolled 14 vs Elena 9 — success"
    transferred_trait_id: Optional[strawberry.ID] = None
    stolen: bool = False
