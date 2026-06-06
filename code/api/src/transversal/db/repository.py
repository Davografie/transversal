"""Entity repository — v2 multi-collection model.

CRUD across entities, projections, traits, traitsets, traitsettings, and sfxs.
Assembles CharacterView from multiple collections.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from arango.database import StandardDatabase

from transversal.db.arango import (
    ENTITIES,
    PROJECTIONS,
    RELATIONSHIPS,
    SFXS,
    TRAITS,
    TRAITSETS,
    TRAITSETTINGS,
    get_db,
)
from transversal.domain import (
    CharacterView,
    Entity,
    EntityType,
    Projection,
    SFX,
    Trait,
    TraitSet,
    TraitSetting,
)


def _key(doc_id: str) -> str:
    return doc_id


class EntityRepository:
    """Multi-collection entity repository."""

    def __init__(self, db: "StandardDatabase | None" = None):
        self.db = db or get_db()
        self._entities = self.db.collection(ENTITIES)
        self._projections = self.db.collection(PROJECTIONS)
        self._traits = self.db.collection(TRAITS)
        self._traitsets = self.db.collection(TRAITSETS)
        self._traitsettings = self.db.collection(TRAITSETTINGS)
        self._sfxs = self.db.collection(SFXS)
        self._relationships = self.db.collection(RELATIONSHIPS)

    # ── Entity CRUD ───────────────────────────────────

    def create_entity(self, entity: Entity) -> Entity:
        doc = entity.model_dump()
        doc["_key"] = entity.id
        self._entities.insert(doc)
        return entity

    def get_entity(self, entity_id: str) -> Optional[Entity]:
        doc = self._entities.get(entity_id)
        return Entity.model_validate({**doc, "id": doc["_key"]}) if doc else None

    def update_entity(self, entity: Entity) -> Entity:
        doc = entity.model_dump()
        doc["_key"] = entity.id
        self._entities.replace(doc)
        return entity

    def delete_entity(self, entity_id: str) -> bool:
        # Clean up projections and traitsettings
        for proj in self._projections.find({"entity_id": entity_id}):
            self._projections.delete(proj["_key"])
        query = f"""
            FOR ts IN {TRAITSETTINGS}
            FILTER ts.entity_id == @eid
            REMOVE ts IN {TRAITSETTINGS}
        """
        self.db.aql.execute(query, bind_vars={"eid": entity_id})
        try:
            self._entities.delete(entity_id)
            return True
        except Exception:
            return False

    def list_entities_by_type(
        self, entity_type: EntityType, universe: Optional[str] = None
    ) -> list[Entity]:
        filters = [f"e.type == '{entity_type.value}'"]
        if universe:
            filters.append(f"e.current_universe == '{universe}'")
        query = f"FOR e IN {ENTITIES} FILTER {' AND '.join(filters)} RETURN e"
        return [self._doc_to_entity(doc) for doc in self.db.aql.execute(query)]

    def list_all_entities(self, universe: Optional[str] = None) -> list[Entity]:
        """List all entities, optionally filtered by universe."""
        if universe:
            query = f"FOR e IN {ENTITIES} FILTER e.current_universe == '{universe}' RETURN e"
        else:
            query = f"FOR e IN {ENTITIES} RETURN e"
        return [self._doc_to_entity(doc) for doc in self.db.aql.execute(query)]

    def list_entities_by_location(self, location_id: str) -> list[Entity]:
        """List all entities currently at a given location."""
        query = f"""
            FOR e IN {ENTITIES}
            FILTER e.current_location == @lid
            RETURN e
        """
        return [
            self._doc_to_entity(doc)
            for doc in self.db.aql.execute(query, bind_vars={"lid": location_id})
        ]

    # ── Projections ───────────────────────────────────

    def create_projection(self, projection: Projection) -> Projection:
        doc = projection.model_dump()
        doc["_key"] = projection.id
        self._projections.insert(doc)
        return projection

    def get_projection(self, projection_id: str) -> Optional[Projection]:
        doc = self._projections.get(projection_id)
        return Projection.model_validate({**doc, "id": doc["_key"]}) if doc else None

    def get_projections_for_entity(self, entity_id: str) -> list[Projection]:
        query = f"""
            FOR p IN {PROJECTIONS}
            FILTER p.entity_id == @eid
            RETURN p
        """
        return [
            Projection.model_validate({**doc, "id": doc["_key"]})
            for doc in self.db.aql.execute(query, bind_vars={"eid": entity_id})
        ]

    def update_projection(self, projection: Projection) -> Projection:
        doc = projection.model_dump()
        doc["_key"] = projection.id
        self._projections.replace(doc)
        return projection

    def delete_projection(self, projection_id: str) -> bool:
        try:
            self._projections.delete(projection_id)
            return True
        except Exception:
            return False

    # ── Trait Registry ────────────────────────────────

    def create_trait(self, trait: Trait) -> Trait:
        doc = trait.model_dump()
        doc["_key"] = trait.id
        self._traits.insert(doc)
        return trait

    def get_trait(self, trait_id: str) -> Optional[Trait]:
        doc = self._traits.get(trait_id)
        return Trait.model_validate({**doc, "id": doc["_key"]}) if doc else None

    def get_traits_by_universe(self, universe: str) -> list[Trait]:
        query = f"""
            FOR t IN {TRAITS}
            FILTER t.universe == @u
            RETURN t
        """
        return [
            Trait.model_validate({**doc, "id": doc["_key"]})
            for doc in self.db.aql.execute(query, bind_vars={"u": universe})
        ]

    def get_trait_by_name(self, name: str, universe: str) -> Optional[Trait]:
        query = f"""
            FOR t IN {TRAITS}
            FILTER t.name == @name AND t.universe == @u
            RETURN t
        """
        cursor = self.db.aql.execute(query, bind_vars={"name": name, "u": universe})
        docs = list(cursor)
        return Trait.model_validate({**docs[0], "id": docs[0]["_key"]}) if docs else None

    # ── TraitSet Registry ─────────────────────────────

    def create_traitset(self, traitset: TraitSet) -> TraitSet:
        doc = traitset.model_dump()
        doc["_key"] = traitset.id
        self._traitsets.insert(doc)
        return traitset

    def get_traitset_by_id(self, traitset_id: str) -> Optional[TraitSet]:
        doc = self._traitsets.get(traitset_id)
        return TraitSet.model_validate({**doc, "id": doc["_key"]}) if doc else None

    def get_traitsets_by_universe(self, universe: str) -> list[TraitSet]:
        query = f"""
            FOR ts IN {TRAITSETS}
            FILTER ts.universe == @u
            RETURN ts
        """
        return [
            TraitSet.model_validate({**doc, "id": doc["_key"]})
            for doc in self.db.aql.execute(query, bind_vars={"u": universe})
        ]

    # ── TraitSettings (edge) ──────────────────────────

    def create_traitsetting(self, ts: TraitSetting) -> TraitSetting:
        doc = ts.model_dump()
        doc["_key"] = ts.id
        doc["_from"] = f"{ENTITIES}/{ts.entity_id}"
        doc["_to"] = f"{TRAITS}/{ts.trait_id}"
        self._traitsettings.insert(doc)
        return ts

    def get_traitsetting(self, ts_id: str) -> Optional[TraitSetting]:
        doc = self._traitsettings.get(ts_id)
        return TraitSetting.model_validate({**doc, "id": doc["_key"]}) if doc else None

    def get_traitsettings_for_entity(self, entity_id: str) -> list[TraitSetting]:
        query = f"""
            FOR ts IN {TRAITSETTINGS}
            FILTER ts.entity_id == @eid
            RETURN ts
        """
        return [
            TraitSetting.model_validate({**doc, "id": doc["_key"]})
            for doc in self.db.aql.execute(query, bind_vars={"eid": entity_id})
        ]

    def get_traitsettings_by_traitset(
        self, entity_id: str, traitset_id: str
    ) -> list[TraitSetting]:
        query = f"""
            FOR ts IN {TRAITSETTINGS}
            FILTER ts.entity_id == @eid AND ts.traitset_id == @tsid
            RETURN ts
        """
        return [
            TraitSetting.model_validate({**doc, "id": doc["_key"]})
            for doc in self.db.aql.execute(
                query, bind_vars={"eid": entity_id, "tsid": traitset_id}
            )
        ]

    def update_traitsetting(self, ts: TraitSetting) -> TraitSetting:
        doc = ts.model_dump()
        doc["_key"] = ts.id
        doc["_from"] = f"{ENTITIES}/{ts.entity_id}"
        doc["_to"] = f"{TRAITS}/{ts.trait_id}"
        self._traitsettings.replace(doc)
        return ts

    def delete_traitsetting(self, ts_id: str) -> bool:
        try:
            self._traitsettings.delete(ts_id)
            return True
        except Exception:
            return False

    # ── Character Assembly ────────────────────────────

    def assemble_character(self, entity_id: str) -> Optional[CharacterView]:
        entity = self.get_entity(entity_id)
        if entity is None:
            return None

        projections = {
            p.universe: p for p in self.get_projections_for_entity(entity_id)
        }
        # All trait settings (morph + ego)
        all_settings = self.get_traitsettings_for_entity(entity_id)

        return CharacterView(
            entity=entity,
            projections=projections,
            trait_settings=all_settings,
        )

    def get_effective_traitsettings(
        self, entity_id: str, universe: str
    ) -> list[TraitSetting]:
        """Get traitsettings active in a given universe.

        Includes: morph traits whose trait is native to `universe`,
        plus all ego traits (regardless of universe).
        """
        # Get the trait IDs for the given universe
        query = f"""
            LET universe_traits = (
                FOR t IN {TRAITS}
                FILTER t.universe == @universe
                RETURN t._key
            )
            FOR ts IN {TRAITSETTINGS}
            FILTER ts.entity_id == @eid
            FILTER ts.trait_id IN universe_traits OR ts.ego == true
            RETURN ts
        """
        return [
            TraitSetting.model_validate({**doc, "id": doc["_key"]})
            for doc in self.db.aql.execute(
                query, bind_vars={"eid": entity_id, "universe": universe}
            )
        ]

    # ── Queries ───────────────────────────────────────

    def find_entities_with_trait(
        self, trait_name: str, universe: str, min_die: Optional[str] = None
    ) -> list[str]:
        """Find entity IDs that have a specific trait in a given universe.

        Uses graph traversal: trait → traitsettings (inbound) → entity.
        """
        # First find the trait ID
        trait = self.get_trait_by_name(trait_name, universe)
        if not trait:
            return []

        query = f"""
            FOR ts IN 1..1 INBOUND @trait_ref {TRAITSETTINGS}
            FILTER ts.negative == false
            RETURN DISTINCT ts.entity_id
        """
        cursor = self.db.aql.execute(
            query,
            bind_vars={"trait_ref": f"{TRAITS}/{trait.id}"},
        )
        return list(cursor)

    # ── Relationships ─────────────────────────────────

    def create_relationship(
        self, from_id: str, to_id: str, rel_type: str
    ) -> dict:
        edge = {
            "_from": f"{ENTITIES}/{from_id}",
            "_to": f"{ENTITIES}/{to_id}",
            "type": rel_type,
        }
        return self._relationships.insert(edge)

    # ── Location Navigation ────────────────────────────

    def location_tree(self) -> list[dict]:
        """Return the full location hierarchy as a nested tree.

        Root locations have no parent (no outbound 'super' edge).
        Children are nested under their parent.
        """
        # Get all LOCATION entities
        location_query = f"""
            FOR e IN {ENTITIES}
            FILTER e.type == 'location'
            RETURN {{ id: e._key, name: e.name, current_universe: e.current_universe }}
        """
        locations = {doc["id"]: doc for doc in self.db.aql.execute(location_query)}

        # Get all super relationships
        rel_query = f"""
            FOR r IN {RELATIONSHIPS}
            FILTER r.type == 'super'
            RETURN {{ child: PARSE_IDENTIFIER(r._from).key, parent: PARSE_IDENTIFIER(r._to).key }}
        """
        # child → parent mapping
        parent_of: dict[str, str] = {}
        children_of: dict[str, list[str]] = {}
        for rel in self.db.aql.execute(rel_query):
            parent_of[rel["child"]] = rel["parent"]
            children_of.setdefault(rel["parent"], []).append(rel["child"])

        def build_node(loc_id: str) -> dict:
            loc = locations.get(loc_id, {"id": loc_id, "name": loc_id, "current_universe": ""})
            children = children_of.get(loc_id, [])
            return {
                "id": loc["id"],
                "name": loc["name"],
                "universe": loc.get("current_universe", ""),
                "children": [build_node(c) for c in sorted(children)],
            }

        # Root locations: locations with no parent
        roots = [lid for lid in locations if lid not in parent_of]

        # Also include locations not in the locations dict (edge references)
        for child_id in parent_of:
            if child_id not in locations:
                locations[child_id] = {"id": child_id, "name": child_id, "current_universe": ""}
        for parent_id in children_of:
            if parent_id not in locations:
                locations[parent_id] = {"id": parent_id, "name": parent_id, "current_universe": ""}

        return [build_node(r) for r in sorted(roots)]

    def navigate_from(self, location_id: str) -> dict:
        """Return navigation options from a location.

        Returns parent (via 'super' edge), children (inbound 'super'),
        transversal destinations (any 'transversal' edges), and occupants.
        """
        query = f"""
            LET loc = DOCUMENT(@loc_ref)
            LET parent = FIRST(
                FOR r IN {RELATIONSHIPS}
                FILTER r._from == @loc_ref AND r.type == 'super'
                RETURN DOCUMENT(r._to)
            )
            LET children = (
                FOR r IN {RELATIONSHIPS}
                FILTER r._to == @loc_ref AND r.type == 'super'
                RETURN DOCUMENT(r._from)
            )
            LET transversal = (
                FOR r IN {RELATIONSHIPS}
                FILTER r._from == @loc_ref AND r.type == 'transversal'
                RETURN DOCUMENT(r._to)
            )
            LET occupants = (
                FOR e IN {ENTITIES}
                FILTER e.current_location == @lid
                  AND e.type IN ['character', 'gmc']
                RETURN {{
                    name: e.name, type: e.type, id: e._key,
                    image: e.background_image,
                    map_x: e.map_x, map_y: e.map_y
                }}
            )
            RETURN {{
                location: loc,
                parent: parent,
                children: children,
                transversal: transversal,
                occupants: occupants
            }}
        """
        cursor = self.db.aql.execute(query, bind_vars={
            "loc_ref": f"{ENTITIES}/{location_id}",
            "lid": location_id,
        })
        results = list(cursor)
        default = {"location": None, "parent": None, "children": [], "transversal": [], "occupants": []}
        return results[0] if results else default

    # ── Helpers ───────────────────────────────────────

    def _doc_to_entity(self, doc: dict) -> Entity:
        doc = dict(doc)
        doc["id"] = doc.pop("_key", doc.get("id", ""))
        for key in ["_id", "_rev"]:
            doc.pop(key, None)
        return Entity.model_validate(doc)
