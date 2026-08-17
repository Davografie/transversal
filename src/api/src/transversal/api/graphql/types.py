"""Strawberry GraphQL types — mapping domain models to GraphQL schema."""

import strawberry
from enum import Enum
from typing import Optional

from transversal.domain import (
    DieType as DomainDieType,
    RatingType as DomainRatingType,
    EntityType as DomainEntityType,
    TransversalType as DomainTransversalType,
    ChallengePolarity as DomainChallengePolarity,
    ConditionType as DomainConditionType,
    EffectTiming as DomainEffectTiming,
    MessageKind as DomainMessageKind,
    OutcomeTier as DomainOutcomeTier,
    RollTableScheme as DomainRollTableScheme,
    RollSource as DomainRollSource,
    DiscoveryBlock,
    LifePath,
)


# ── Enums ────────────────────────────────────────────

DieType = strawberry.enum(DomainDieType)
RatingType = strawberry.enum(DomainRatingType)
EntityType = strawberry.enum(DomainEntityType)
TransversalTypeEnum = strawberry.enum(DomainTransversalType)
ChallengePolarity = strawberry.enum(DomainChallengePolarity)
EffectTimingEnum = strawberry.enum(DomainEffectTiming)
MessageKind = strawberry.enum(DomainMessageKind)
OutcomeTier = strawberry.enum(DomainOutcomeTier)
RollTableScheme = strawberry.enum(DomainRollTableScheme)
RollSource = strawberry.enum(DomainRollSource)
ConditionType = strawberry.enum(DomainConditionType)


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
    location_restricted: bool
    default_ego: bool = False
    display_names: list[TraitDisplayName] = strawberry.field(default_factory=list)


@strawberry.type
class TraitSetRef:
    id: strawberry.ID
    name: str
    universes: list[str]
    entity_types: list[EntityType]
    order: int = 0
    limit: int = 1

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
                location_restricted=t.location_restricted,
                default_ego=t.default_ego,
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
class Effect:
    """A single operational effect — shared by SFX and life-path consequences."""
    timing: EffectTimingEnum
    type: str
    action: str
    target: str = ""
    result: Optional[str] = None
    target_scope: Optional[str] = None
    context: Optional[strawberry.scalars.JSON] = None


@strawberry.input
class EffectInput:
    timing: EffectTimingEnum = EffectTimingEnum.IMMEDIATE
    type: str = ""
    action: str = ""
    target: str = ""
    result: Optional[str] = None
    target_scope: Optional[str] = None
    context: Optional[strawberry.scalars.JSON] = None


@strawberry.type
class TargetCandidate:
    """A selectable target returned by the choose/random candidate resolver."""
    id: strawberry.ID
    name: str
    universe: str = ""


@strawberry.type
class PendingChoiceRef:
    """An effect target that must be resolved before the effect can apply."""
    index: int
    kind: str
    scope: Optional[str] = None
    effect: Effect


@strawberry.type
class EffectApplicationResult:
    """Outcome of applying a set of effects, plus any unresolved targets."""
    applied: list[str]
    pending_choices: list[PendingChoiceRef] = strawberry.field(default_factory=list)


@strawberry.input
class EffectTargetResolutionInput:
    """A single resolved target for a previously-pending effect."""
    effect: EffectInput
    target: str


@strawberry.type
class SfxRef:
    """SFX reference returned by queries."""
    id: strawberry.ID
    name: str
    description: str = ""
    trigger: str = ""
    limit: str = ""
    effects: list[Effect] = strawberry.field(default_factory=list)


@strawberry.input
class SfxInput:
    """Input for creating a new SFX."""
    id: str
    name: str
    description: str = ""
    trigger: str = ""
    limit: str = ""
    effects: list[EffectInput] = strawberry.field(default_factory=list)


@strawberry.input
class SfxUpdateInput:
    """Input for updating an existing SFX."""
    id: strawberry.ID
    name: Optional[str] = None
    description: Optional[str] = None
    trigger: Optional[str] = None
    limit: Optional[str] = None
    effects: Optional[list[EffectInput]] = None


# ── Roll Tables ─────────────────────────────────────

@strawberry.type
class Condition:
    """A configurable, automatically-evaluated gate or limit."""
    type: ConditionType
    target: str = ""
    value: Optional[str] = None
    narrative: str = ""


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
class ConditionInput:
    type: ConditionType = ConditionType.ALWAYS
    target: str = ""
    value: Optional[str] = None
    narrative: str = ""


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
class EffectActionMeta:
    """Metadata for one effect action the editor can create."""
    action_id: str
    label: str
    description: str
    category: str
    effect_type: str
    effect_action: str
    valid_timings: list[str]
    fields: list[EffectFieldDef] = strawberry.field(default_factory=list)
    implicit_target: Optional[str] = None
    implicit_result: Optional[str] = None
    implicit_timing: Optional[str] = None
    requires_choice: bool = False
    target_kind: Optional[str] = None


@strawberry.input
class TraitInput:
    id: str
    name: str
    universes: list[str] = strawberry.field(default_factory=list)
    traitset_id: strawberry.ID
    default_die_type: DieType = DieType.D6
    default_rating_type: RatingType = RatingType.STATIC
    possible_sfx_ids: list[strawberry.ID] = strawberry.field(default_factory=list)
    default_sfx_ids: list[strawberry.ID] = strawberry.field(default_factory=list)
    location_restricted: bool = False
    default_ego: bool = False
    display_names: list[TraitDisplayNameInput] = strawberry.field(default_factory=list)


@strawberry.input
class TraitUpdateInput:
    name: Optional[str] = None
    universes: Optional[list[str]] = None
    traitset_id: Optional[strawberry.ID] = None
    default_die_type: Optional[DieType] = None
    default_rating_type: Optional[RatingType] = None
    possible_sfx_ids: Optional[list[strawberry.ID]] = None
    default_sfx_ids: Optional[list[strawberry.ID]] = None
    location_restricted: Optional[bool] = None
    default_ego: Optional[bool] = None
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
    polarity: Optional[ChallengePolarity] = None
    statement: str
    negative: bool
    ego: bool
    from_type: str = "entity"  # "entity" | "projection" | "relationship"
    projection_id: Optional[strawberry.ID] = None
    sfx_ids: list[strawberry.ID]
    known_to: list[strawberry.ID] = strawberry.field(default_factory=list)

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
        from transversal.services.entity_manager import EntityManager
        em = info.context["entity_manager"]
        ts = em.repo.get_traitset_by_id(self.traitset_id)
        return ts.limit if ts else 1

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


@strawberry.input
class TraitSettingInput:
    trait_id: strawberry.ID
    traitset_id: strawberry.ID
    dice: list[DieType] = strawberry.field(default_factory=list)
    rating_type: RatingType = RatingType.STATIC
    polarity: Optional[ChallengePolarity] = None
    statement: str = ""
    negative: bool = False
    ego: bool = False
    from_type: Optional[str] = None  # "entity" | "projection"
    projection_id: Optional[strawberry.ID] = None
    sfx_ids: list[strawberry.ID] = strawberry.field(default_factory=list)


@strawberry.input
class TraitSettingUpdateInput:
    dice: Optional[list[DieType]] = None
    rating_type: Optional[RatingType] = None
    polarity: Optional[ChallengePolarity] = None
    statement: Optional[str] = None
    negative: Optional[bool] = None
    ego: Optional[bool] = None
    from_type: Optional[str] = None  # "entity" | "projection"
    projection_id: Optional[strawberry.ID] = None
    sfx_ids: Optional[list[strawberry.ID]] = None
    known_to: Optional[list[strawberry.ID]] = None


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


@strawberry.type
class Entity:
    id: strawberry.ID
    type: EntityType
    name: str
    razmerit: int
    current_universe: str
    current_location: Optional[str] = None
    current_projection: Optional[str] = None
    hidden: bool = False
    known_to: list[strawberry.ID] = strawberry.field(default_factory=list)
    _background_image: strawberry.Private[Optional[str]] = None
    _sheet_portrait: strawberry.Private[Optional[str]] = None
    zones: list[Zone] = strawberry.field(default_factory=list)
    map_x: Optional[float] = None
    map_y: Optional[float] = None
    overlay: Optional[str] = None
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
                       current_location=p.current_location, transversal_type=p.transversal_type)
            for p in projs
        ]

    @strawberry.field
    def background_image(self) -> Optional[str]:
        from transversal.db.repository import EntityRepository
        from transversal.domain import ImageType
        repo = EntityRepository()
        images = repo.get_entity_images(str(self.id))
        for img in images:
            if "background" in img.roles:
                if img.image_type == ImageType.ANIMATED:
                    return f"/media/animated/{img.entity_id}/{img.universe}/{img.filename}.{img.extension}"
                else:
                    return f"/media/imagen/{img.entity_id}/{img.universe}/{img.filename}_Large.{img.extension}"
        return self._background_image

    @strawberry.field
    def sheet_portrait(self) -> Optional[str]:
        from transversal.db.repository import EntityRepository
        from transversal.domain import ImageType
        repo = EntityRepository()
        images = repo.get_entity_images(str(self.id))
        for img in images:
            if "sheet" in img.roles:
                if img.image_type == ImageType.ANIMATED:
                    return f"/media/animated/{img.entity_id}/{img.universe}/{img.filename}.{img.extension}"
                else:
                    return f"/media/imagen/{img.entity_id}/{img.universe}/{img.filename}_Large.{img.extension}"
        # Fall back to background image
        return self.background_image()

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
        return [
            TraitSetting(
                id=s.id, entity_id=s.entity_id, trait_id=s.trait_id,
                traitset_id=s.traitset_id,
                rating_type=s.rating_type, dice=s.dice,
                polarity=s.polarity,
                statement=s.statement, negative=s.negative,
                ego=s.ego, from_type=s.from_type, projection_id=s.projection_id,
                sfx_ids=s.sfx_ids,
                known_to=s.known_to,
            )
            for s in settings
        ]

    @strawberry.field
    def effective_trait_settings(self, info: strawberry.Info) -> list[TraitSetting]:
        from transversal.services.entity_manager import EntityManager
        em = info.context["entity_manager"]
        settings = em.get_effective_traitsettings(str(self.id))
        return [
            TraitSetting(
                id=s.id, entity_id=s.entity_id, trait_id=s.trait_id,
                traitset_id=s.traitset_id,
                rating_type=s.rating_type, dice=s.dice,
                polarity=s.polarity,
                statement=s.statement, negative=s.negative,
                ego=s.ego, from_type=s.from_type, projection_id=s.projection_id,
                sfx_ids=s.sfx_ids,
                known_to=s.known_to,
            )
            for s in settings
        ]


@strawberry.input
class CreateEntityInput:
    name: str
    type: EntityType
    universe: str
    location: Optional[str] = None
    razmerit: int = 0


@strawberry.input
class UpdateEntityInput:
    id: strawberry.ID
    name: Optional[str] = None
    razmerit: Optional[int] = None
    current_universe: Optional[str] = None
    current_location: Optional[str] = None
    hidden: Optional[bool] = None
    known_to: Optional[list[str]] = None
    background_image: Optional[str] = None
    overlay: Optional[str] = None
    nav_positions: Optional[str] = None
    owned_by: Optional[str] = None
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


@strawberry.input
class DeleteRelationshipInput:
    """Input for deleting a relationship edge."""
    from_entity_id: strawberry.ID
    to_entity_id: strawberry.ID
    type: str = "associate"


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
