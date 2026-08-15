"""Entity manager — v2 multi-collection model.

Business logic for entity lifecycle across 7 collections.
"""

from __future__ import annotations

from typing import Optional

from transversal.api.sse.bus import StreamEvent, event_bus
from transversal.db.repository import EntityRepository
from transversal.services.change_log import change_log
from transversal.services.session_manager import session_manager


def _publish_to_sessions(event: StreamEvent) -> None:
    """Publish an event to all active sessions."""
    for s in session_manager.list_active():
        event_bus.publish(StreamEvent(
            event=event.event, session_id=s.id, data=event.data))
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
        entity = Entity(
            id=eid,
            type=entity_type,
            name=name,
            razmerit=razmerit,
            current_universe=universe,
            current_location=location,
        )
        validate_entity(entity)
        self.repo.create_entity(entity)

        # Create initial projection
        proj = Projection(
            id=f"{eid}:{universe}",
            entity_id=eid,
            universe=universe,
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
    ) -> Entity:
        existing = self.repo.get_projections_for_entity(entity.id)
        for p in existing:
            if p.universe == universe:
                raise ValueError(f"Entity already has a projection in '{universe}'")

        proj = Projection(
            id=f"{entity.id}:{universe}",
            entity_id=entity.id,
            universe=universe,
            transversal_type=transversal_type,
        )
        self.repo.create_projection(proj)

        entity.current_universe = universe
        return self.repo.update_entity(entity)

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

        _publish_to_sessions(StreamEvent(
            event="trait_updated",
            data={"entity_id": ts.entity_id, "trait_id": ts.trait_id,
                  "old_rating": old_rating, "new_rating": dice_list_to_rating(ts.dice)},
        ))

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

        _publish_to_sessions(StreamEvent(
            event="trait_updated",
            data={"entity_id": ts.entity_id, "trait_id": ts.trait_id,
                  "old_rating": old_rating, "new_rating": dice_list_to_rating(ts.dice)},
        ))

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
        result = self.repo.update_entity(entity)

        event = StreamEvent(
            event="location_changed",
            data={"entity_id": entity.id, "from": old_location, "to": location,
                  "universe": entity.current_universe},
        )
        _publish_to_sessions(event)

        return result


def _generate_id(name: str, entity_type: EntityType) -> str:
    import secrets
    slug = name.lower().replace(" ", "-")[:20]
    suffix = secrets.token_hex(4)
    return f"{entity_type.value}-{slug}-{suffix}"
