"""Entity manager — v2 multi-collection model.

Business logic for entity lifecycle across 7 collections.
"""

from __future__ import annotations

from typing import Optional

from transversal.api.sse.bus import StreamEvent, event_bus
from transversal.db.repository import EntityRepository
from transversal.services.change_log import change_log
from transversal.services.scene_state import resync_pool_dice_for_trait
from transversal.services.session_manager import session_manager


def _publish_to_sessions(event: StreamEvent) -> None:
    """Publish an event to all active sessions."""
    for s in session_manager.list_active():
        event_bus.publish(StreamEvent(
            event=event.event, session_id=s.id, data=event.data))


def _publish_location_changed(entity: Entity, old_location: Optional[str], old_universe: str) -> None:
    """Publish a location_changed event when an entity's active location/universe moved."""
    if entity.current_location == old_location and entity.current_universe == old_universe:
        return
    _publish_to_sessions(StreamEvent(
        event="location_changed",
        data={"entity_id": entity.id, "from": old_location or "",
              "to": entity.current_location or "", "universe": entity.current_universe},
    ))
    from transversal.services.scheduled_events import dispatch_event
    dispatch_event(None, "location_changed", entity_id=entity.id, universe=entity.current_universe)
from transversal.domain import (
    CharacterView,
    Entity,
    EntityType,
    Projection,
    RatingType,
    TraitSetting,
    TransversalType,
    dice_list_to_rating,
)
from transversal.domain.validation import validate_entity


class EntityNotFoundError(Exception):
    pass


class EntityManager:
    def __init__(self, repository: EntityRepository | None = None):
        self.repo = repository or EntityRepository()

    # ── Projections ────────────────────────────────────

    def create_projection(
        self, entity_id: str, universe: str, transversal_type: str = "consciousness"
    ) -> Projection:
        entity = self.repo.get_entity(entity_id)
        if entity is None:
            raise ValueError(f"Entity '{entity_id}' not found")

        proj_id = f"{entity_id}:{universe}"
        existing = self.repo.get_projection(proj_id)
        if existing:
            return existing

        proj = Projection(
            id=proj_id, entity_id=entity_id, universe=universe,
            origin_universe=universe,
            transversal_type=transversal_type,
        )
        return self.repo.create_projection(proj)

    # ── Entity CRUD ───────────────────────────────────

    def create(
        self,
        name: str,
        entity_type: EntityType,
        universe: str,
        location: Optional[str] = None,
        razmerit: int = 0,
        entity_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Entity:
        eid = entity_id or _generate_id(name, entity_type)
        if entity_type == EntityType.UNIVERSE:
            universe = _universe_key(name, self.repo)
        proj_id = f"{eid}:{universe}"
        entity = Entity(
            id=eid,
            type=entity_type,
            name=name,
            razmerit=razmerit,
            current_universe=universe,
            current_location=location,
            current_projection=proj_id,
        )
        validate_entity(entity)
        self.repo.create_entity(entity)

        # Create initial projection
        proj = Projection(
            id=proj_id,
            entity_id=eid,
            universe=universe,
            origin_universe=universe,
            current_location=location,
            transversal_type=TransversalType.NATIVE,
        )
        self.repo.create_projection(proj)

        if session_id:
            event_bus.publish(StreamEvent(
                event="entity_created", session_id=session_id,
                data={"entity_id": entity.id, "name": entity.name, "type": entity.type.value},
            ))

        return entity

    def get(self, entity_id: str) -> Entity:
        entity = self.repo.get_entity(entity_id)
        if entity is None:
            raise EntityNotFoundError(f"Entity '{entity_id}' not found")
        return entity

    def get_character(self, entity_id: str) -> CharacterView:
        cv = self.repo.assemble_character(entity_id)
        if cv is None:
            raise EntityNotFoundError(f"Entity '{entity_id}' not found")
        return cv

    def update(self, entity: Entity) -> Entity:
        validate_entity(entity)
        old = self.repo.get_entity(entity.id)
        old_location = old.current_location if old else None
        result = self.repo.update_entity(entity)

        _publish_to_sessions(StreamEvent(
            event="entity_updated",
            data={"entity_id": entity.id, "name": entity.name,
                  "background_image": entity.background_image,
                  "current_universe": entity.current_universe,
                  "current_location": entity.current_location},
        ))

        if entity.current_location != old_location:
            _publish_to_sessions(StreamEvent(
                event="location_changed",
                data={"entity_id": entity.id, "from": old_location or "",
                      "to": entity.current_location or "",
                      "universe": entity.current_universe},
            ))

        return result

    def delete(self, entity_id: str, rmtree: bool = False) -> bool:
        return self.repo.delete_entity(entity_id, rmtree=rmtree)

    # ── Projections ───────────────────────────────────

    def add_projection(
        self,
        entity: Entity,
        universe: str,
        transversal_type: TransversalType = TransversalType.CONSCIOUSNESS,
        location: Optional[str] = None,
    ) -> Entity:
        existing = self.repo.get_projections_for_entity(entity.id)
        for p in existing:
            if p.id == f"{entity.id}:{universe}":
                raise ValueError(f"Entity already has a projection in '{universe}'")

        proj = Projection(
            id=f"{entity.id}:{universe}",
            entity_id=entity.id,
            universe=universe,
            origin_universe=universe,
            current_location=location,
            transversal_type=transversal_type,
        )
        self.repo.create_projection(proj)

        entity.current_universe = universe
        entity.current_projection = proj.id
        return self.repo.update_entity(entity)

    def remove_projection(self, projection_id: str) -> Entity:
        proj = self.repo.get_projection(projection_id)
        if proj is None:
            raise ValueError(f"Projection '{projection_id}' not found")
        self.repo.delete_projection(projection_id)
        entity = self.repo.get_entity(proj.entity_id)
        if entity is not None and entity.current_projection == projection_id:
            entity.current_projection = None
            self.repo.update_entity(entity)
        return entity

    def update_projection(
        self,
        projection_id: str,
        name: Optional[str] = None,
        background_image: Optional[str] = None,
        current_location: Optional[str] = None,
    ) -> Projection:
        """Update a projection's mutable fields (name / image / location).

        ``None`` means "leave unchanged"; an empty string clears the field.
        """
        proj = self.repo.get_projection(projection_id)
        if proj is None:
            raise ValueError(f"Projection '{projection_id}' not found")
        if name is not None:
            proj.name = name
        if background_image is not None:
            proj.background_image = background_image or None
        if current_location is not None:
            proj.current_location = current_location or None
        return self.repo.update_projection(proj)

    def activate_projection(
        self, entity_id: str, projection_id: str, location: Optional[str] = None
    ) -> Entity:
        """Make ``projection_id`` the entity's active projection.

        Also aligns the entity's current universe/location with the projection's.
        When ``location`` is given, the projection is moved there first (its
        universe follows the location's universe).
        """
        entity = self.repo.get_entity(entity_id)
        if entity is None:
            raise EntityNotFoundError(f"Entity '{entity_id}' not found")
        proj = self.repo.get_projection(projection_id)
        if proj is None:
            raise ValueError(f"Projection '{projection_id}' not found")
        old_location = entity.current_location
        old_universe = entity.current_universe
        if location is not None:
            proj.current_location = location
            loc = self.repo.get_entity(location)
            if loc is not None:
                proj.universe = loc.current_universe
            self.repo.update_projection(proj)
        entity.current_projection = projection_id
        entity.current_universe = proj.universe
        entity.current_location = proj.current_location
        result = self.repo.update_entity(entity)
        _publish_location_changed(entity, old_location, old_universe)
        return result

    def inapposite_travel(self, entity_id: str, location: str) -> Entity:
        """Physically relocate the entity's active projection to ``location``.

        The projection keeps its origin key; its ``universe``/``current_location``
        mutate, and its type becomes INAPPOSITE when crossing universes (NATIVE
        when it returns home).
        """
        entity = self.repo.get_entity(entity_id)
        if entity is None:
            raise EntityNotFoundError(f"Entity '{entity_id}' not found")
        loc = self.repo.get_entity(location)
        if loc is None:
            raise ValueError(f"Location '{location}' not found")

        old_location = entity.current_location
        old_universe = entity.current_universe

        proj = None
        if entity.current_projection:
            proj = self.repo.get_projection(entity.current_projection)

        if proj is None:
            proj = Projection(
                id=f"{entity.id}:{loc.current_universe}",
                entity_id=entity.id,
                origin_universe=loc.current_universe,
                universe=loc.current_universe,
                current_location=location,
                transversal_type=TransversalType.NATIVE,
            )
            self.repo.create_projection(proj)
        else:
            if not proj.origin_universe:
                proj.origin_universe = proj.id.rsplit(":", 1)[-1]
            proj.universe = loc.current_universe
            proj.current_location = location
            proj.transversal_type = (
                TransversalType.NATIVE
                if loc.current_universe == proj.origin_universe
                else TransversalType.INAPPOSITE
            )
            self.repo.update_projection(proj)

        entity.current_projection = proj.id
        entity.current_universe = loc.current_universe
        entity.current_location = location
        result = self.repo.update_entity(entity)
        _publish_location_changed(entity, old_location, old_universe)
        return result

    def consciousness_travel(self, entity_id: str, location: str) -> Entity:
        """Transfer the entity's consciousness to a projection at ``location``.

        Leaves the current (body) projection in place and spawns/reuses a
        CONSCIOUSNESS projection keyed by the destination universe, which becomes
        the entity's active projection.
        """
        entity = self.repo.get_entity(entity_id)
        if entity is None:
            raise EntityNotFoundError(f"Entity '{entity_id}' not found")
        loc = self.repo.get_entity(location)
        if loc is None:
            raise ValueError(f"Location '{location}' not found")

        new_universe = loc.current_universe
        old_location = entity.current_location
        old_universe = entity.current_universe

        proj_id = f"{entity.id}:{new_universe}"
        proj = self.repo.get_projection(proj_id)
        if proj is None:
            proj = Projection(
                id=proj_id,
                entity_id=entity.id,
                origin_universe=new_universe,
                universe=new_universe,
                current_location=location,
                transversal_type=TransversalType.CONSCIOUSNESS,
            )
            self.repo.create_projection(proj)
        else:
            if not proj.origin_universe:
                proj.origin_universe = proj.id.rsplit(":", 1)[-1]
            proj.universe = new_universe
            proj.current_location = location
            self.repo.update_projection(proj)

        entity.current_projection = proj.id
        entity.current_universe = new_universe
        entity.current_location = location
        result = self.repo.update_entity(entity)
        _publish_location_changed(entity, old_location, old_universe)
        return result

    def get_projections(self, entity_id: str) -> list[Projection]:
        return self.repo.get_projections_for_entity(entity_id)

    # ── Trait Settings ────────────────────────────────

    def add_traitsetting(self, ts: TraitSetting) -> TraitSetting:
        return self.repo.create_traitsetting(ts)

    def get_traitsettings(self, entity_id: str) -> list[TraitSetting]:
        return self.repo.get_traitsettings_for_entity(entity_id)

    def get_effective_traitsettings(
        self, entity_id: str, universes: Optional[list[str]] = None
    ) -> list[TraitSetting]:
        """Traits active in ``universes``, or the entity's effective universes when omitted."""
        if universes is None:
            entity = self.repo.get_entity(entity_id)
            if entity is None:
                return []
            universes = self.repo.effective_universes(entity)
        return self.repo.get_effective_traitsettings(entity_id, universes)

    def get_traitsettings_by_set(
        self, entity_id: str, traitset_id: str
    ) -> list[TraitSetting]:
        return self.repo.get_traitsettings_by_traitset(entity_id, traitset_id)

    def update_traitsetting(self, ts: TraitSetting) -> TraitSetting:
        return self.repo.update_traitsetting(ts)

    def step_up_trait(self, ts: TraitSetting, session_id: Optional[str] = None) -> TraitSetting:
        if not ts.dice:
            raise ValueError(f"Cannot step up trait '{ts.trait_id}': no dice in pool")
        old_rating = dice_list_to_rating(ts.dice)
        die = ts.dice[0]
        stepped = die.step_up()
        ts.dice[0] = stepped
        result = self.repo.update_traitsetting(ts)
        change_log.record(ts.entity_id, f"traitsetting.{ts.id}.dice", old_rating, dice_list_to_rating(ts.dice), session_id or "")

        new_dice = [d.value for d in ts.dice]
        _publish_to_sessions(StreamEvent(
            event="trait_updated",
            data={"entity_id": ts.entity_id, "trait_id": ts.trait_id,
                  "trait_setting_id": ts.id, "old_rating": old_rating,
                  "new_rating": dice_list_to_rating(ts.dice),
                  "new_dice": new_dice},
        ))
        resync_pool_dice_for_trait(ts.entity_id, ts.id, new_dice)
        from transversal.services.scheduled_events import dispatch_event
        dispatch_event(None, "trait_updated", entity_id=ts.entity_id,
                       context={"trait_id": ts.trait_id, "traitset_id": ts.traitset_id})

        return result

    def step_down_trait(self, ts: TraitSetting, session_id: Optional[str] = None) -> TraitSetting:
        if not ts.dice:
            raise ValueError(f"Cannot step down trait '{ts.trait_id}': no dice in pool")
        old_rating = dice_list_to_rating(ts.dice)
        die = ts.dice[0]
        stepped = die.step_down()
        ts.dice[0] = stepped
        result = self.repo.update_traitsetting(ts)
        change_log.record(ts.entity_id, f"traitsetting.{ts.id}.dice", old_rating, dice_list_to_rating(ts.dice), session_id or "")

        new_dice = [d.value for d in ts.dice]
        _publish_to_sessions(StreamEvent(
            event="trait_updated",
            data={"entity_id": ts.entity_id, "trait_id": ts.trait_id,
                  "trait_setting_id": ts.id, "old_rating": old_rating,
                  "new_rating": dice_list_to_rating(ts.dice),
                  "new_dice": new_dice},
        ))
        resync_pool_dice_for_trait(ts.entity_id, ts.id, new_dice)
        from transversal.services.scheduled_events import dispatch_event
        dispatch_event(None, "trait_updated", entity_id=ts.entity_id,
                       context={"trait_id": ts.trait_id, "traitset_id": ts.traitset_id})

        return result

    def get_relationship_trait_settings(
        self, entity_id: str, related_entity_id: str
    ) -> list[TraitSetting]:
        """Return trait settings on relationships between two entities."""
        return self.repo.get_relationship_traits_for_entities(entity_id, related_entity_id)

    # ── Locations ─────────────────────────────────────

    def move_to(self, entity: Entity, location: str, universe: Optional[str] = None,
                session_id: Optional[str] = None) -> Entity:
        old_location = entity.current_location
        old_universe = entity.current_universe
        entity.current_location = location
        if universe:
            entity.current_universe = universe

        # Keep the active projection's location in sync.
        new_universe = entity.current_universe
        proj_id = entity.current_projection or f"{entity.id}:{old_universe or new_universe}"
        proj = self.repo.get_projection(proj_id)
        if proj is None:
            proj = Projection(
                id=f"{entity.id}:{new_universe}",
                entity_id=entity.id,
                origin_universe=new_universe,
                universe=new_universe,
                current_location=location,
                transversal_type=TransversalType.NATIVE,
            )
            self.repo.create_projection(proj)
            entity.current_projection = proj.id
        else:
            proj.current_location = location
            proj.universe = new_universe
            self.repo.update_projection(proj)

        result = self.repo.update_entity(entity)

        event = StreamEvent(
            event="location_changed",
            data={"entity_id": entity.id, "from": old_location, "to": location,
                  "universe": entity.current_universe},
        )
        _publish_to_sessions(event)

        return result


def _universe_key(name: str, repo: EntityRepository) -> str:
    """Derive a unique universe key (current_universe) from a name."""
    import re
    base = re.sub(r"[^a-z0-9]+", "_", name.lower().strip()).strip("_") or "universe"
    existing = {u.current_universe for u in repo.list_entities_by_type(EntityType.UNIVERSE)}
    if base not in existing:
        return base
    n = 2
    while f"{base}-{n}" in existing:
        n += 1
    return f"{base}-{n}"


def _generate_id(name: str, entity_type: EntityType) -> str:
    import secrets
    slug = name.lower().replace(" ", "-")[:20]
    suffix = secrets.token_hex(4)
    return f"{entity_type.value}-{slug}-{suffix}"
