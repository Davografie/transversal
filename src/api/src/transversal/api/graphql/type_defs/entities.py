"""Entities — split out of src/api/src/transversal/api/graphql/types.py."""

import strawberry

from typing import Optional
from transversal.api.graphql.type_defs.enums import (
    EffectTimingEnum,
    EntityType,
    TransversalTypeEnum,
)
from transversal.api.graphql.type_defs.traits import (
    TraitSetSetting,
    TraitSetting,
    _gql_trait_setting,
)


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

    @strawberry.field
    def sheet_image_transparent(self, info: strawberry.Info) -> bool:
        """Whether this body's sheet role image has a transparent background."""
        em = info.context["entity_manager"]
        entry = em.repo.resolve_role_image_entry(str(self.entity_id), "sheet", str(self.id))
        return entry.transparent if entry is not None else False

@strawberry.type
class Zone:
    name: str
    background_image: Optional[str] = None
    location_id: Optional[str] = None
    x: float = 50.0
    y: float = 50.0

@strawberry.type
class Attunement:
    """A projection grant (attune = add, suppress = remove)."""
    op: str = "add"
    universe: Optional[str] = None
    projection_id: Optional[strawberry.ID] = None
    scope: str = "self"
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
class AgencyRef:
    """Who holds agency over an entity — the persistent player→entity relation."""
    player_id: strawberry.ID
    player_name: str = ""
    main: bool = False

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
    support_eligible: bool = False
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
    async def projections(self, info: strawberry.Info) -> list[Projection]:
        projs = await info.context["loaders"].projections.load(str(self.id))
        return [
            Projection(id=p.id, entity_id=p.entity_id, origin_universe=p.origin_universe,
                       universe=p.universe, name=p.name, background_image=p.background_image,
                       current_location=p.current_location, transversal_type=p.transversal_type,
                       sfx_ids=p.sfx_ids)
            for p in projs
        ]

    @strawberry.field
    async def trait_set_settings(self, info: strawberry.Info) -> list[TraitSetSetting]:
        """This entity's per-trait-set settings (SFX + limit override)."""
        tss_list = await info.context["loaders"].traitsetsettings.load(str(self.id))
        return [
            TraitSetSetting(
                id=tss.id, entity_id=tss.entity_id, traitset_id=tss.traitset_id,
                from_type=tss.from_type, projection_id=tss.projection_id,
                sfx_ids=tss.sfx_ids, limit=tss.limit,
            )
            for tss in tss_list
        ]

    @strawberry.field
    def background_image(self, info: strawberry.Info) -> Optional[str]:
        em = info.context["entity_manager"]
        url = em.repo.resolve_role_image(str(self.id), "background", None, "Large")
        return url if url is not None else self._background_image

    @strawberry.field
    def agency(self, info: strawberry.Info) -> Optional[AgencyRef]:
        """The player holding agency over this entity, if any.

        Read from the ``agency`` relationship edge (player → entity) rather than
        from transient control state, so it answers for a main whose player is
        offline and for a support character alike. ``owned_by`` is a separate,
        mostly-unpopulated field — do not conflate them.
        """
        em = info.context["entity_manager"]
        edge = em.repo.get_agency_for_entity(str(self.id))
        if not edge:
            return None
        player = em.repo.get_player(edge["player_id"])
        return AgencyRef(
            player_id=edge["player_id"],
            player_name=(getattr(player, "name", "") or ""),
            main=bool(edge.get("main")),
        )

    @strawberry.field
    def sheet_portrait(self, info: strawberry.Info) -> Optional[str]:
        em = info.context["entity_manager"]
        # Sheet portraits render at ~40px — serve the small variant.
        url = em.repo.resolve_role_image(str(self.id), "sheet", None, "Small")
        if url is not None:
            return url
        # Fall back to background image
        return self.background_image(info)

    @strawberry.field
    def sheet_portrait_transparent(self, info: strawberry.Info) -> bool:
        """Whether the resolved sheet portrait has a transparent background.

        Mirrors ``sheet_portrait``'s fallback chain (sheet role image, then
        the background image); the legacy denormalized background is unknown
        and reported as opaque.
        """
        em = info.context["entity_manager"]
        entry = em.repo.resolve_role_image_entry(str(self.id), "sheet", None)
        if entry is not None:
            return entry.transparent
        entry = em.repo.resolve_role_image_entry(str(self.id), "background", None)
        return entry.transparent if entry is not None else False

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
    async def trait_settings(self, info: strawberry.Info) -> list[TraitSetting]:
        settings = await info.context["loaders"].traitsettings.load(str(self.id))
        result = [_gql_trait_setting(s) for s in settings]
        for enriched in await info.context["loaders"].relationship_traitsettings.load(str(self.id)):
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
    support_eligible: Optional[bool] = None
    known_to: Optional[list[str]] = None
    background_image: Optional[str] = None
    overlay: Optional[str] = None
    starter_location: Optional[bool] = None
    nav_positions: Optional[str] = None
    owned_by: Optional[str] = None
    suitable_life_path_ids: Optional[list[str]] = None
    lora_config: Optional[str] = None

@strawberry.type
class RazmeritResult:
    from_id: strawberry.ID
    from_balance: int
    to_id: Optional[strawberry.ID] = None
    to_balance: Optional[int] = None
    amount: int
    reason: str

@strawberry.type
class CharacterView:
    entity: Entity
    projections: list[Projection]
    trait_settings: list[TraitSetting]
