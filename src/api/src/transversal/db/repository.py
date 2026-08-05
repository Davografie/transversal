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
    ENTITY_IMAGES,
    PLAYERS,
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
    EntityImage,
    EntityType,
    ImageType,
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
        self._players = self.db.collection(PLAYERS)
        self._entity_images = self.db.collection(ENTITY_IMAGES)

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

    def delete_entity(self, entity_id: str, rmtree: bool = False) -> bool:
        """Delete an entity, optionally pruning a location subtree.

        For non-location entities this is a simple delete with cascade
        cleanup of projections, trait settings, and relationships.

        For locations there are two modes:

        * ``rmtree=False`` (default) — **reparent**: occupants and
          sub-locations are moved to the deleted location's parent.
        * ``rmtree=True`` — **prune**: the location, all descendant
          sub-locations, and all of their occupants are deleted
          recursively.
        """
        entity = self.get_entity(entity_id)
        if entity is None:
            return False

        if entity.type == EntityType.LOCATION:
            return self._delete_location(entity_id, rmtree)
        else:
            return self._delete_simple(entity_id)

    def _delete_simple(self, entity_id: str) -> bool:
        """Delete a non-location entity with full cascade cleanup."""
        self._cascade_cleanup(entity_id)
        try:
            self._entities.delete(entity_id)
            return True
        except Exception:
            return False

    def _delete_location(self, location_id: str, rmtree: bool) -> bool:
        """Delete a location, reparenting or pruning its subtree."""
        eref = f"{ENTITIES}/{location_id}"

        # Find parent (via outbound super edge, if any)
        parent_ref = None
        parent_query = f"""
            FOR r IN {RELATIONSHIPS}
            FILTER r._from == @eref AND r.type == 'super'
            RETURN r._to
        """
        cursor = list(self.db.aql.execute(parent_query, bind_vars={"eref": eref}))
        parent_ref = cursor[0] if cursor else None

        if rmtree:
            # ── Prune: recursively delete sub-locations and their occupants ──
            descendant_query = f"""
                FOR v IN 0..100 INBOUND @eref {RELATIONSHIPS}
                FILTER v._key != @lid
                RETURN v._key
            """
            descendants = [
                d for d in self.db.aql.execute(
                    descendant_query, bind_vars={"eref": eref, "lid": location_id}
                )
            ]
            # Delete bottom-up to avoid dangling references
            for desc_id in reversed(descendants):
                desc_eref = f"{ENTITIES}/{desc_id}"
                # Delete occupants of this sub-location
                self.db.aql.execute(
                    f"FOR e IN {ENTITIES} FILTER e.current_location == @lid AND e._key != @lid REMOVE e IN {ENTITIES}",
                    bind_vars={"lid": desc_id},
                )
                # Cascade-cleanup the sub-location entity itself
                self._cascade_cleanup(desc_id)
                self._entities.delete(desc_id)
            # Now delete occupants of the target location itself
            self.db.aql.execute(
                f"FOR e IN {ENTITIES} FILTER e.current_location == @lid AND e._key != @lid REMOVE e IN {ENTITIES}",
                bind_vars={"lid": location_id},
            )
        else:
            # ── Reparent: move occupants and sub-locations to parent ──
            new_parent_id = parent_ref.split("/", 1)[1] if parent_ref else None
            if new_parent_id:
                # Move occupants
                self.db.aql.execute(
                    f"FOR e IN {ENTITIES} FILTER e.current_location == @lid UPDATE e WITH {{current_location: @pid}} IN {ENTITIES}",
                    bind_vars={"lid": location_id, "pid": new_parent_id},
                )
                # Move sub-location super edges
                self.db.aql.execute(
                    f"""
                    FOR r IN {RELATIONSHIPS}
                    FILTER r._to == @eref AND r.type == 'super'
                    UPDATE r WITH {{_to: @pref}} IN {RELATIONSHIPS}
                    """,
                    bind_vars={"eref": eref, "pref": parent_ref},
                )
            else:
                # No parent: clear occupants' location, sub-locations become roots
                self.db.aql.execute(
                    f"FOR e IN {ENTITIES} FILTER e.current_location == @lid UPDATE e WITH {{current_location: null}} IN {ENTITIES}",
                    bind_vars={"lid": location_id},
                )

        # Final cascade cleanup and delete
        self._cascade_cleanup(location_id)
        try:
            self._entities.delete(location_id)
            return True
        except Exception:
            return False

    def _cascade_cleanup(self, entity_id: str) -> None:
        """Remove projections, trait settings, and relationships for an entity."""
        eref = f"{ENTITIES}/{entity_id}"
        for proj in self._projections.find({"entity_id": entity_id}):
            self._projections.delete(proj["_key"])
        self.db.aql.execute(
            f"FOR ts IN {TRAITSETTINGS} FILTER ts.entity_id == @eid REMOVE ts IN {TRAITSETTINGS}",
            bind_vars={"eid": entity_id},
        )
        self.db.aql.execute(
            f"FOR r IN {RELATIONSHIPS} FILTER r._from == @eref OR r._to == @eref REMOVE r IN {RELATIONSHIPS}",
            bind_vars={"eref": eref},
        )

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
            FILTER @u IN t.universes
            RETURN t
        """
        return [
            Trait.model_validate({**doc, "id": doc["_key"]})
            for doc in self.db.aql.execute(query, bind_vars={"u": universe})
        ]

    def get_trait_by_name(self, name: str, universe: str) -> Optional[Trait]:
        query = f"""
            FOR t IN {TRAITS}
            FILTER t.name == @name AND @u IN t.universes
            RETURN t
        """
        cursor = self.db.aql.execute(query, bind_vars={"name": name, "u": universe})
        docs = list(cursor)
        return Trait.model_validate({**docs[0], "id": docs[0]["_key"]}) if docs else None

    def get_traits_by_traitset(self, traitset_id: str) -> list[Trait]:
        query = f"""
            FOR t IN {TRAITS}
            FILTER t.traitset_id == @tsid
            SORT t.name ASC
            RETURN t
        """
        return [
            Trait.model_validate({**doc, "id": doc["_key"]})
            for doc in self.db.aql.execute(query, bind_vars={"tsid": traitset_id})
        ]

    def update_trait(self, trait: Trait) -> Trait:
        doc = trait.model_dump()
        doc["_key"] = trait.id
        self._traits.replace(doc)
        return trait

    def delete_trait(self, trait_id: str) -> bool:
        """Delete a trait and cascade-remove any trait settings referencing it."""
        ts_removed = len(list(self.db.aql.execute(
            f"FOR ts IN {TRAITSETTINGS} FILTER ts.trait_id == @tid REMOVE ts IN {TRAITSETTINGS} RETURN OLD._key",
            bind_vars={"tid": trait_id}
        )))
        try:
            self._traits.delete(trait_id)
            return True
        except Exception:
            return False

    # ── SFX Registry ────────────────────────────────────

    def create_sfx(self, sfx: SFX) -> SFX:
        doc = sfx.model_dump()
        doc["_key"] = sfx.id
        self._sfxs.insert(doc)
        return sfx

    def get_sfx(self, sfx_id: str) -> Optional[SFX]:
        doc = self._sfxs.get(sfx_id)
        return SFX.model_validate({**doc, "id": doc["_key"]}) if doc else None

    def get_all_sfxs(self) -> list[SFX]:
        query = f"FOR s IN {SFXS} RETURN s"
        return [
            SFX.model_validate({**doc, "id": doc["_key"]})
            for doc in self.db.aql.execute(query)
        ]

    def update_sfx(self, sfx: SFX) -> SFX:
        doc = sfx.model_dump()
        doc["_key"] = sfx.id
        self._sfxs.replace(doc)
        return sfx

    def delete_sfx(self, sfx_id: str) -> bool:
        try:
            self._sfxs.delete(sfx_id)
            return True
        except Exception:
            return False

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
            FILTER @u IN ts.universes
            SORT ts.order ASC, ts.name ASC
            RETURN ts
        """
        return [
            TraitSet.model_validate({**doc, "id": doc["_key"]})
            for doc in self.db.aql.execute(query, bind_vars={"u": universe})
        ]

    def get_all_traitsets(self) -> list[TraitSet]:
        query = f"FOR ts IN {TRAITSETS} SORT ts.order ASC, ts.name ASC RETURN ts"
        return [
            TraitSet.model_validate({**doc, "id": doc["_key"]})
            for doc in self.db.aql.execute(query)
        ]

    def update_traitset(self, traitset: TraitSet) -> TraitSet:
        doc = traitset.model_dump()
        doc["_key"] = traitset.id
        existing = self._traitsets.get(traitset.id)
        if existing:
            doc["_rev"] = existing["_rev"]
            self._traitsets.replace(doc)
        return traitset

    def delete_traitset(self, traitset_id: str) -> dict:
        """Cascade delete: traitset → traits → trait settings."""
        trait_keys = [
            r for r in self.db.aql.execute(
                f"FOR t IN {TRAITS} FILTER t.traitset_id == @tsid RETURN t._key",
                bind_vars={"tsid": traitset_id}
            )
        ]
        ts_removed = 0
        if trait_keys:
            ts_removed = len(list(self.db.aql.execute(
                f"FOR ts IN {TRAITSETTINGS} FILTER ts.trait_id IN @tids REMOVE ts IN {TRAITSETTINGS} RETURN OLD._key",
                bind_vars={"tids": trait_keys}
            )))
        for tkey in trait_keys:
            try: self._traits.delete(tkey)
            except Exception: pass
        try: self._traitsets.delete(traitset_id)
        except Exception: pass
        return {"deleted": True, "traits_removed": len(trait_keys), "settings_removed": ts_removed}

    def reorder_traitsets(self, ordered_ids: list[str]) -> None:
        for i, tsid in enumerate(ordered_ids):
            doc = self._traitsets.get(tsid)
            if doc:
                ts = TraitSet.model_validate({**doc, "id": doc["_key"]})
                ts.order = i + 1
                upd = ts.model_dump()
                upd["_key"] = ts.id
                upd["_rev"] = doc["_rev"]
                self._traitsets.replace(upd)

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
                FILTER @universe IN t.universes
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

    # ── Players ──────────────────────────────────────

    def create_player(self, player_id: str, name: str, role: str = "player") -> dict:
        doc = {"_key": player_id, "name": name, "role": role}
        self._players.insert(doc)
        return doc

    def get_player(self, player_id: str) -> dict | None:
        return self._players.get(player_id)

    def find_player_by_name(self, name: str) -> dict | None:
        query = f"""
            FOR p IN {PLAYERS}
            FILTER LOWER(p.name) == @name
            LIMIT 1
            RETURN p
        """
        cursor = self.db.aql.execute(query, bind_vars={"name": name.lower().strip()})
        results = list(cursor)
        return results[0] if results else None

    def search_players(self, query_str: str) -> list[dict]:
        q = query_str.lower().strip()
        if not q:
            return []
        aql = f"""
            FOR p IN {PLAYERS}
            FILTER CONTAINS(LOWER(p.name), @q)
            SORT p.name
            RETURN p
        """
        return list(self.db.aql.execute(aql, bind_vars={"q": q}))

    def list_players(self) -> list[dict]:
        return list(self._players.all())

    def update_player(self, player_id: str, updates: dict) -> bool:
        player = self._players.get(player_id)
        if player:
            player.update(updates)
            self._players.update(player)
            return True
        return False

    def delete_player(self, player_id: str) -> bool:
        # Cascade-delete agency edges
        self.db.aql.execute(
            f"FOR r IN {RELATIONSHIPS} FILTER r._from == @pref AND r.type == 'agency' REMOVE r IN {RELATIONSHIPS}",
            bind_vars={"pref": f"{PLAYERS}/{player_id}"}
        )
        try:
            self._players.delete(player_id)
            return True
        except Exception:
            return False

    def claim_entity(self, player_id: str, entity_id: str) -> bool:
        if not self._players.has(player_id):
            return False
        edge_key = f"edge:{player_id}:{entity_id}:agency"
        if not self._relationships.has(edge_key):
            self._relationships.insert({
                "_key": edge_key,
                "_from": f"{PLAYERS}/{player_id}",
                "_to": f"{ENTITIES}/{entity_id}",
                "type": "agency",
            })
        return True

    def release_entity(self, player_id: str, entity_id: str) -> bool:
        edge_key = f"edge:{player_id}:{entity_id}:agency"
        try:
            self._relationships.delete(edge_key)
            return True
        except Exception:
            return False

    def get_player_entities(self, player_id: str) -> list[str]:
        query = f"""
            FOR r IN {RELATIONSHIPS}
            FILTER r._from == @pref AND r.type == 'agency'
            RETURN PARSE_IDENTIFIER(r._to).key
        """
        return list(self.db.aql.execute(query, bind_vars={"pref": f"{PLAYERS}/{player_id}"}))

    def get_entity_players(self, entity_id: str) -> list[str]:
        query = f"""
            FOR r IN {RELATIONSHIPS}
            FILTER r._to == @eref AND r.type == 'agency'
            RETURN PARSE_IDENTIFIER(r._from).key
        """
        return list(self.db.aql.execute(query, bind_vars={"eref": f"{ENTITIES}/{entity_id}"}))

    # ── Location Navigation ────────────────────────────

    def location_tree(self) -> list[dict]:
        """Return the full location hierarchy as a nested tree.

        Universes are the top-level nodes.  Locations are nested under their
        universe (keyed on ``current_universe``), with their own ``super``
        edges forming sub-hierarchies within each universe.
        """
        # ── Get all UNIVERSE entities ─────────────────
        universe_query = f"""
            FOR e IN {ENTITIES}
            FILTER e.type == 'universe'
            RETURN {{ id: e._key, name: e.name, current_universe: e.current_universe }}
        """
        universes = {
            doc["current_universe"]: doc
            for doc in self.db.aql.execute(universe_query)
        }

        # ── Get all LOCATION entities ─────────────────
        location_query = f"""
            FOR e IN {ENTITIES}
            FILTER e.type == 'location'
            RETURN {{ id: e._key, name: e.name, current_universe: e.current_universe }}
        """
        locations = {doc["id"]: doc for doc in self.db.aql.execute(location_query)}

        # ── Get all super relationships ───────────────
        rel_query = f"""
            FOR r IN {RELATIONSHIPS}
            FILTER r.type == 'super'
            RETURN {{ child: PARSE_IDENTIFIER(r._from).key, parent: PARSE_IDENTIFIER(r._to).key }}
        """
        parent_of: dict[str, str] = {}
        children_of: dict[str, list[str]] = {}
        for rel in self.db.aql.execute(rel_query):
            parent_of[rel["child"]] = rel["parent"]
            children_of.setdefault(rel["parent"], []).append(rel["child"])

        # Fill gaps for edge-referenced entities not in the locations dict
        for child_id in parent_of:
            if child_id not in locations:
                locations[child_id] = {"id": child_id, "name": child_id, "current_universe": ""}
        for parent_id in children_of:
            if parent_id not in locations:
                locations[parent_id] = {"id": parent_id, "name": parent_id, "current_universe": ""}

        def build_node(loc_id: str) -> dict:
            loc = locations.get(loc_id, {"id": loc_id, "name": loc_id, "current_universe": ""})
            children = children_of.get(loc_id, [])
            return {
                "id": loc["id"],
                "name": loc["name"],
                "node_type": "location",
                "universe": loc.get("current_universe", ""),
                "children": [build_node(c) for c in sorted(children)],
            }

        # Root locations: locations with no parent super edge
        roots = [lid for lid in locations if lid not in parent_of]

        # Group root locations by their current_universe
        uni_roots: dict[str, list[str]] = {}
        orphans: list[str] = []  # locations with no matching universe
        for lid in roots:
            ukey = locations[lid].get("current_universe", "")
            if ukey in universes:
                uni_roots.setdefault(ukey, []).append(lid)
            else:
                orphans.append(lid)

        # Build universe nodes
        result: list[dict] = []
        for ukey, uni in sorted(universes.items(), key=lambda kv: kv[1]["name"]):
            loc_roots = uni_roots.get(ukey, [])
            result.append({
                "id": uni["id"],
                "name": uni["name"],
                "node_type": "universe",
                "universe": ukey,
                "children": [build_node(r) for r in sorted(loc_roots)],
            })

        # Orphan locations (no matching universe entity) still appear as
        # top-level nodes so nothing is silently dropped.
        for lid in sorted(orphans):
            result.append(build_node(lid))

        return result

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

    # ── Entity Images ─────────────────────────────────

    def create_entity_image(self, image: EntityImage) -> EntityImage:
        doc = image.model_dump()
        doc["_key"] = image.id
        self._entity_images.insert(doc)
        return image

    def get_entity_images(
        self, entity_id: str, universe: str | None = None, image_type: ImageType | None = None
    ) -> list[EntityImage]:
        filters = [("entity_id", entity_id)]
        if universe:
            filters.append(("universe", universe))
        if image_type:
            filters.append(("image_type", image_type.value))

        # Build simple filter query
        parts = [f"doc.{f} == @v{i}" for i, (f, _) in enumerate(filters)]
        binds = {f"v{i}": v for i, (_, v) in enumerate(filters)}
        query = f"""
            FOR doc IN {ENTITY_IMAGES}
            FILTER {' AND '.join(parts)}
            SORT doc.created_at DESC
            RETURN doc
        """
        return [
            EntityImage.model_validate({**doc, "id": doc["_key"]})
            for doc in self.db.aql.execute(query, bind_vars=binds)
        ]

    def get_entity_image(self, image_id: str) -> EntityImage | None:
        doc = self._entity_images.get(image_id)
        return EntityImage.model_validate({**doc, "id": doc["_key"]}) if doc else None

    def update_entity_image(self, image_id: str, updates: dict) -> EntityImage | None:
        doc = self._entity_images.get(image_id)
        if not doc:
            return None
        self._entity_images.update({**doc, **updates})
        return self.get_entity_image(image_id)

    def delete_entity_image(self, image_id: str) -> bool:
        return self._entity_images.delete(image_id)

    # ── Helpers ───────────────────────────────────────

    def _doc_to_entity(self, doc: dict) -> Entity:
        doc = dict(doc)
        doc["id"] = doc.pop("_key", doc.get("id", ""))
        for key in ["_id", "_rev"]:
            doc.pop(key, None)
        return Entity.model_validate(doc)
