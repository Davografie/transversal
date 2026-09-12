"""Traits — split out of src/api/src/transversal/api/graphql/types.py."""

import strawberry

from typing import Optional
from transversal.api.graphql.type_defs.enums import (
    DieType,
    EntityType,
    Polarity,
    RatingType,
)


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
    default_ego: bool = False
    tags: list[str] = strawberry.field(default_factory=list)
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
    allow_duplicates: bool = False
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
                default_ego=t.default_ego,
                tags=t.tags,
                polarity=t.polarity,
                display_names=[
                    TraitDisplayName(name=dn.name, universe=dn.universe,
                                     ratings=dn.ratings)
                    for dn in t.display_names
                ],
            )
            for t in traits
        ]

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
    default_ego: bool = False
    tags: list[str] = strawberry.field(default_factory=list)
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
    default_ego: Optional[bool] = None
    tags: Optional[list[str]] = None
    polarity: Optional[Polarity] = None
    clear_polarity: bool = False
    display_names: Optional[list[TraitDisplayNameInput]] = None

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
    tags: list[str] = strawberry.field(default_factory=list)
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
        # The universe only matters when the trait has per-universe/per-rating
        # display names; skip the entity lookup (an N+1 per trait setting) in
        # the common case where the name is static.
        if not trait.display_names or not self.dice:
            return trait.name
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
    async def traitset_limit(self, info: strawberry.Info) -> int:
        """Effective trait-set limit: per-entity override, else registry default."""
        repo = info.context["entity_manager"].repo
        ts = repo.get_traitset_by_id(self.traitset_id)
        default = ts.limit if ts else 1
        for tss in await info.context["loaders"].traitsetsettings.load(str(self.entity_id)):
            if tss.traitset_id == self.traitset_id and tss.from_type == "entity" and tss.limit is not None:
                return tss.limit
        return default

    @strawberry.field
    def possible_sfx_ids(self, info: strawberry.Info) -> list[strawberry.ID]:
        from transversal.services.entity_manager import EntityManager
        em = info.context["entity_manager"]
        trait = em.repo.get_trait(self.trait_id)
        return trait.possible_sfx_ids if trait else []

    @strawberry.field
    def registry_tags(self, info: strawberry.Info) -> list[str]:
        """Tags inherited from the registry ``Trait`` (B116).

        A setting may also carry its own ``tags``, and matching sees both — this
        read-through field is the *inherited* half only, so an editor can show
        what comes from the trait definition separately from what is set here.
        """
        em = info.context["entity_manager"]
        trait = em.repo.get_trait(self.trait_id)
        return trait.tags if trait else []

    @strawberry.field
    def possible_subtrait_ids(self, info: strawberry.Info) -> list[strawberry.ID]:
        """Resolved sub-traits that may be nested under this trait (ids + set refs)."""
        from transversal.services.entity_manager import EntityManager
        em = info.context["entity_manager"]
        trait = em.repo.get_trait(self.trait_id)
        return em.repo.resolve_possible_subtrait_ids(trait) if trait else []

    @strawberry.field
    async def sub_trait_settings(self, info: strawberry.Info) -> list["TraitSetting"]:
        """Sub-trait settings nested directly under this trait setting."""
        subs = await info.context["loaders"].sub_traitsettings.load(str(self.id))
        return [_gql_trait_setting(s) for s in subs]

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
    tags: list[str] = strawberry.field(default_factory=list)
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
    tags: Optional[list[str]] = None
    from_type: Optional[str] = None  # "entity" | "projection" | "traitsetting"
    projection_id: Optional[strawberry.ID] = None
    parent_traitsetting_id: Optional[strawberry.ID] = None
    sfx_ids: Optional[list[strawberry.ID]] = None
    known_to: Optional[list[strawberry.ID]] = None
    enabled: Optional[bool] = None

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
        tags=s.tags,
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
