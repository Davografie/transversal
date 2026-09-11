"""Entities — split out of src/api/src/transversal/db/repository.py."""

import os

from transversal.db.arango import ENTITIES
from transversal.db.arango import ENTITY_IMAGES
from transversal.db.arango import MESSAGES
from transversal.db.arango import PROJECTIONS
from transversal.db.arango import RELATIONSHIPS
from transversal.db.arango import TRAITSETSETTINGS
from transversal.db.arango import TRAITSETTINGS
from transversal.domain import Entity
from transversal.domain import EntityType
from typing import Optional


class RepositoryEntities:
    """Mixin contributing 14 member(s) to the repository."""

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

    def _delete_occupants(self, location_id: str) -> None:
        """Delete every occupant of a location with full cascade cleanup.

        Occupants are non-location entities whose ``current_location`` is this
        location. Each is removed through ``_delete_simple`` so its projections,
        trait settings, relationships, and scheduled-event timers are cleaned
        rather than orphaned (the B49 class of bug).
        """
        occupant_ids = list(self.db.aql.execute(
            f"""
            FOR e IN {ENTITIES}
            FILTER e.current_location == @lid AND e._key != @lid
            RETURN e._key
            """,
            bind_vars={"lid": location_id},
        ))
        for oid in occupant_ids:
            self._delete_simple(oid)

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
            # Only ``super`` children are sub-locations (mirroring the reparent
            # branch). The previous 0..100 INBOUND walk over all relationship
            # types both exploded on deep/wide hierarchies and would have
            # deleted portal-linked or otherwise related entities that are not
            # sub-locations.
            descendants = self.list_location_descendants(location_id)
            # Delete bottom-up to avoid dangling references. Occupants go through
            # the cascade path (not a raw REMOVE) so their dependent records are
            # cleaned rather than orphaned (B49).
            for desc_id in reversed(descendants):
                self._delete_occupants(desc_id)
                self._cascade_cleanup(desc_id)
                self._entities.delete(desc_id)
            self._delete_occupants(location_id)
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
        """Remove projections, trait settings, relationships, images, media, and timers."""
        eref = f"{ENTITIES}/{entity_id}"

        # Delete centrally-scheduled timers targeting this entity.
        self.delete_scheduled_events(target_type="entity", target_id=entity_id)

        # Projection targets of incoming relationship edges (morph relationships).
        proj_docs = list(self._projections.find({"entity_id": entity_id}))
        proj_keys = [p["_key"] for p in proj_docs]
        proj_refs = [f"{PROJECTIONS}/{k}" for k in proj_keys]

        # Relationship edges touching the entity directly, or one of its
        # projections (incoming morph edges and any outgoing body edges).
        edge_keys = list(self.db.aql.execute(
            f"""
            FOR r IN {RELATIONSHIPS}
            FILTER r._from == @eref OR r._to == @eref
                OR r._from IN @proj_refs OR r._to IN @proj_refs
            RETURN r._key
            """,
            bind_vars={"eref": eref, "proj_refs": proj_refs},
        ))

        # Collect trait-setting roots anchored to this entity — relationship edges
        # plus entity/projection settings — then remove them and all nested
        # sub-traits in one subtree walk.
        trait_setting_keys = set()
        if edge_keys:
            trait_setting_keys.update(
                self.db.aql.execute(
                    f"""
                    FOR ts IN {TRAITSETTINGS}
                    FILTER ts.from_type == 'relationship' AND ts.entity_id IN @edge_keys
                    RETURN ts._key
                    """,
                    bind_vars={"edge_keys": edge_keys},
                )
            )
        trait_setting_keys.update(
            self.db.aql.execute(
                f"""
                FOR ts IN {TRAITSETTINGS}
                FILTER ts.entity_id == @eid AND ts.from_type != 'traitsetting'
                RETURN ts._key
                """,
                bind_vars={"eid": entity_id},
            )
        )
        if trait_setting_keys:
            self._delete_traitsettings_subtree(list(trait_setting_keys))

        # The relationship edges themselves.
        self.db.aql.execute(
            f"""
            FOR r IN {RELATIONSHIPS}
            FILTER r._from == @eref OR r._to == @eref
                OR r._from IN @proj_refs OR r._to IN @proj_refs
            REMOVE r IN {RELATIONSHIPS}
            """,
            bind_vars={"eref": eref, "proj_refs": proj_refs},
        )

        for key in proj_keys:
            self._projections.delete(key)

        # Trait-set settings anchored to this entity or one of its projections.
        self.db.aql.execute(
            f"""
            FOR tss IN {TRAITSETSETTINGS}
            FILTER tss.entity_id == @eid OR tss._from IN @proj_refs
            REMOVE tss IN {TRAITSETSETTINGS}
            """,
            bind_vars={"eid": entity_id, "proj_refs": proj_refs},
        )

        # Delete entity image records from DB
        self.db.aql.execute(
            f"FOR img IN {ENTITY_IMAGES} FILTER img.entity_id == @eid REMOVE img IN {ENTITY_IMAGES}",
            bind_vars={"eid": entity_id},
        )
        # Delete messages involving this entity
        self.db.aql.execute(
            f"FOR m IN {MESSAGES} FILTER m.sender_entity_id == @eid OR m.recipient_entity_id == @eid REMOVE m IN {MESSAGES}",
            bind_vars={"eid": entity_id},
        )
        # Delete media files from disk
        import glob
        import shutil
        media_root = "/app/media"
        # Generated images directory
        imagen_dir = f"{media_root}/imagen/{entity_id}"
        shutil.rmtree(imagen_dir, ignore_errors=True)
        # Uploaded background images (media/{entity_id}.*)
        for path in glob.glob(f"{media_root}/{entity_id}.*"):
            try:
                os.remove(path)
            except OSError:
                pass

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
        """List all entities currently at a given location (via their projections)."""
        query = f"""
            LET occupant_ids = (
                FOR p IN {PROJECTIONS}
                FILTER p.current_location == @lid
                RETURN DISTINCT p.entity_id
            )
            FOR e IN {ENTITIES}
            FILTER e.type IN ['character', 'gmc', 'asset']
            FILTER e._key IN occupant_ids OR e.current_location == @lid
            RETURN e
        """
        return [
            self._doc_to_entity(doc)
            for doc in self.db.aql.execute(query, bind_vars={"lid": location_id})
        ]

    def list_entities_by_locations(self, location_ids: list[str]) -> list[Entity]:
        """List occupants across multiple locations (character/gmc/asset)."""
        if not location_ids:
            return []
        query = f"""
            LET occupant_ids = (
                FOR p IN {PROJECTIONS}
                FILTER p.current_location IN @lids
                RETURN DISTINCT p.entity_id
            )
            FOR e IN {ENTITIES}
            FILTER e.type IN ['character', 'gmc', 'asset']
            FILTER e._key IN occupant_ids OR e.current_location IN @lids
            RETURN DISTINCT e
        """
        return [
            self._doc_to_entity(doc)
            for doc in self.db.aql.execute(query, bind_vars={"lids": location_ids})
        ]

    def get_entities_by_ids(self, entity_ids: list[str]) -> list[Entity]:
        """Fetch entities by their keys in one query, preserving input order
        (missing ids are dropped)."""
        if not entity_ids:
            return []
        ids = list(dict.fromkeys(entity_ids))  # dedupe, preserve order
        query = f"FOR e IN {ENTITIES} FILTER e._key IN @ids RETURN e"
        by_id = {
            doc["_key"]: self._doc_to_entity(doc)
            for doc in self.db.aql.execute(query, bind_vars={"ids": ids})
        }
        return [by_id[eid] for eid in ids if eid in by_id]

    def _doc_to_entity(self, doc: dict) -> Entity:
        doc = dict(doc)
        doc["id"] = doc.pop("_key", doc.get("id", ""))
        for key in ["_id", "_rev"]:
            doc.pop(key, None)
        return Entity.model_validate(doc)
