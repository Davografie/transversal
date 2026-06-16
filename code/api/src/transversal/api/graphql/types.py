"""Strawberry GraphQL types — mapping domain models to GraphQL schema."""

import strawberry
from typing import Optional

from transversal.domain import (
    DieType as DomainDieType,
    RatingType as DomainRatingType,
    EntityType as DomainEntityType,
    TransversalType as DomainTransversalType,
    ChallengePolarity as DomainChallengePolarity,
)


# ── Enums ────────────────────────────────────────────

DieType = strawberry.enum(DomainDieType)
RatingType = strawberry.enum(DomainRatingType)
EntityType = strawberry.enum(DomainEntityType)
TransversalTypeEnum = strawberry.enum(DomainTransversalType)
ChallengePolarity = strawberry.enum(DomainChallengePolarity)


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
    location_restricted: bool


@strawberry.type
class TraitSetRef:
    id: strawberry.ID
    name: str
    universes: list[str]
    entity_types: list[EntityType]
    order: int = 0
    limit: int = 1


# ── SFX Registry ──────────────────────────────────────

@strawberry.type
class SfxRef:
    id: strawberry.ID
    name: str
    description: str = ""
    trigger: str = ""


@strawberry.input
class SfxInput:
    id: str
    name: str
    description: str = ""
    trigger: str = ""
    timing: str = "immediate"
    cost: int = 0


@strawberry.input
class SfxUpdateInput:
    id: strawberry.ID
    name: Optional[str] = None
    description: Optional[str] = None
    trigger: Optional[str] = None
    timing: Optional[str] = None
    cost: Optional[int] = None


@strawberry.input
class TraitInput:
    id: str
    name: str
    universes: list[str] = strawberry.field(default_factory=list)
    traitset_id: strawberry.ID
    default_die_type: DieType = DieType.D6
    default_rating_type: RatingType = RatingType.STATIC
    possible_sfx_ids: list[strawberry.ID] = strawberry.field(default_factory=list)
    location_restricted: bool = False


@strawberry.input
class TraitUpdateInput:
    name: Optional[str] = None
    universes: Optional[list[str]] = None
    traitset_id: Optional[strawberry.ID] = None
    default_die_type: Optional[DieType] = None
    default_rating_type: Optional[RatingType] = None
    possible_sfx_ids: Optional[list[strawberry.ID]] = None
    location_restricted: Optional[bool] = None


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
        from transversal.services.entity_manager import EntityManager
        em = info.context["entity_manager"]
        trait = em.repo.get_trait(self.trait_id)
        return trait.name if trait else ""

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
    sfx_ids: list[strawberry.ID] = strawberry.field(default_factory=list)


@strawberry.input
class TraitSettingUpdateInput:
    dice: Optional[list[DieType]] = None
    rating_type: Optional[RatingType] = None
    polarity: Optional[ChallengePolarity] = None
    statement: Optional[str] = None
    negative: Optional[bool] = None
    ego: Optional[bool] = None
    sfx_ids: Optional[list[strawberry.ID]] = None
    known_to: Optional[list[strawberry.ID]] = None


# ── Projection ───────────────────────────────────────

@strawberry.type
class Projection:
    id: strawberry.ID
    entity_id: strawberry.ID
    universe: str
    transversal_type: TransversalTypeEnum


# ── Entity ───────────────────────────────────────────

@strawberry.type
class Zone:
    name: str
    background_image: Optional[str] = None
    x: float = 50.0
    y: float = 50.0


@strawberry.type
class Entity:
    id: strawberry.ID
    type: EntityType
    name: str
    razmerit: int
    current_universe: str
    current_location: Optional[str] = None
    hidden: bool = False
    known_to: list[strawberry.ID] = strawberry.field(default_factory=list)
    background_image: Optional[str] = None
    zones: list[Zone] = strawberry.field(default_factory=list)
    map_x: Optional[float] = None
    map_y: Optional[float] = None
    overlay: Optional[str] = None
    nav_positions: str = "{}"
    node_ids: list[strawberry.ID] = strawberry.field(default_factory=list)
    owned_by: Optional[str] = None

    @strawberry.field
    def projections(self, info: strawberry.Info) -> list[Projection]:
        from transversal.services.entity_manager import EntityManager
        em = info.context["entity_manager"]
        projs = em.get_projections(self.id)
        return [
            Projection(id=p.id, entity_id=p.entity_id, universe=p.universe,
                       transversal_type=p.transversal_type)
            for p in projs
        ]

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
                ego=s.ego, sfx_ids=s.sfx_ids,
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
