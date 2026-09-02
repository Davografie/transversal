"""Entity repository — v2 multi-collection model.

CRUD across entities, projections, traits, traitsets, traitsettings, and sfxs.
Assembles CharacterView from multiple collections.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from arango.database import StandardDatabase

from transversal.db.arango import (
    ENTITIES,
    ENTITY_IMAGES,
    HISTORICAL_RECORDS,
    LIFE_PATHS,
    MESSAGES,
    PLAN_ENTITIES,
    PLAN_RELATIONSHIPS,
    PLAYERS,
    PROJECTIONS,
    RELATIONSHIPS,
    ROLL_TABLES,
    SCHEDULED_EVENTS,
    SFX_OWNERS,
    SFXS,
    TRAITS,
    TRAITSETS,
    TRAITSETSETTINGS,
    TRAITSETTINGS,
    get_db,
)
from transversal.domain import (
    SFX,
    AttunementScope,
    CharacterView,
    Entity,
    EntityImage,
    EntityType,
    HistoricalRecord,
    ImageType,
    LifePath,
    Message,
    Projection,
    RollTable,
    ScheduledEvent,
    SfxOwner,
    Trait,
    TraitSet,
    TraitSetSetting,
    TraitSetting,
    TransversalType,
    Zone,
    dice_list_to_rating,
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
        self._traitsetsettings = self.db.collection(TRAITSETSETTINGS)
        self._sfxs = self.db.collection(SFXS)
        self._sfx_owners = self.db.collection(SFX_OWNERS)
        self._scheduled_events = self.db.collection(SCHEDULED_EVENTS)
        self._life_paths = self.db.collection(LIFE_PATHS)
        self._roll_tables = self.db.collection(ROLL_TABLES)
        self._relationships = self.db.collection(RELATIONSHIPS)
        self._players = self.db.collection(PLAYERS)
        self._entity_images = self.db.collection(ENTITY_IMAGES)
        self._messages = self.db.collection(MESSAGES)
        self._historical_records = self.db.collection(HISTORICAL_RECORDS)
        self._plan_entities = self.db.collection(PLAN_ENTITIES)
        self._plan_relationships = self.db.collection(PLAN_RELATIONSHIPS)

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

    def list_all_projections(self) -> list[Projection]:
        query = f"""
            FOR p IN {PROJECTIONS}
            RETURN p
        """
        return [
            Projection.model_validate({**doc, "id": doc["_key"]})
            for doc in self.db.aql.execute(query)
        ]

    def update_projection(self, projection: Projection) -> Projection:
        doc = projection.model_dump()
        doc["_key"] = projection.id
        self._projections.replace(doc)
        return projection

    def delete_projection(self, projection_id: str) -> bool:
        """Delete a projection and cascade-remove its dependents.

        Removes relationship edges touching the projection (and any trait
        settings anchored to those edges), projection-anchored trait settings
        and trait-set settings (including nested sub-traits), and
        projection-scoped images — otherwise they orphan when the body goes.
        """
        pref = f"{PROJECTIONS}/{projection_id}"

        # Relationship edges touching the projection, plus trait settings
        # anchored to those edges (relationship ratings).
        edge_keys = list(self.db.aql.execute(
            f"""
            FOR r IN {RELATIONSHIPS}
            FILTER r._from == @pref OR r._to == @pref
            RETURN r._key
            """,
            bind_vars={"pref": pref},
        ))
        if edge_keys:
            rel_ts_keys = list(self.db.aql.execute(
                f"""
                FOR ts IN {TRAITSETTINGS}
                FILTER ts.from_type == 'relationship' AND ts.entity_id IN @keys
                RETURN ts._key
                """,
                bind_vars={"keys": edge_keys},
            ))
            if rel_ts_keys:
                self._delete_traitsettings_subtree(rel_ts_keys)
            self.db.aql.execute(
                f"""
                FOR r IN {RELATIONSHIPS}
                FILTER r._from == @pref OR r._to == @pref
                REMOVE r IN {RELATIONSHIPS}
                """,
                bind_vars={"pref": pref},
            )

        # Projection-anchored trait settings (roots) and their sub-trait subtrees.
        proj_ts_keys = list(self.db.aql.execute(
            f"""
            FOR ts IN {TRAITSETTINGS}
            FILTER ts.from_type == 'projection'
                AND (ts.projection_id == @pid OR ts._from == @pref)
            RETURN ts._key
            """,
            bind_vars={"pid": projection_id, "pref": pref},
        ))
        if proj_ts_keys:
            self._delete_traitsettings_subtree(proj_ts_keys)

        # Projection-anchored trait-set settings.
        self.db.aql.execute(
            f"""
            FOR tss IN {TRAITSETSETTINGS}
            FILTER tss.from_type == 'projection'
                AND (tss.projection_id == @pid OR tss._from == @pref)
            REMOVE tss IN {TRAITSETSETTINGS}
            """,
            bind_vars={"pid": projection_id, "pref": pref},
        )

        # Projection-scoped images (entity-level images have no projection_id).
        self.db.aql.execute(
            f"FOR img IN {ENTITY_IMAGES} FILTER img.projection_id == @pid REMOVE img IN {ENTITY_IMAGES}",
            bind_vars={"pid": projection_id},
        )

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

    def resolve_possible_subtrait_ids(self, trait: Trait) -> list[str]:
        """Resolve a trait's possible sub-traits.

        A trait can nominate sub-traits two ways: individual trait ids
        (``possible_subtrait_ids``) and whole trait sets (``possible_subtraitset_ids``
        — every trait in the set is eligible). This returns the flattened,
        de-duplicated trait id list for read/Effects consumption.
        """
        ids: list[str] = list(trait.possible_subtrait_ids)
        for set_id in trait.possible_subtraitset_ids:
            for st in self.get_traits_by_traitset(set_id):
                if st.id not in ids:
                    ids.append(st.id)
        return ids

    def get_all_traits(self) -> list[Trait]:
        query = f"""
            FOR t IN {TRAITS}
            SORT t.name ASC
            RETURN t
        """
        return [
            Trait.model_validate({**doc, "id": doc["_key"]})
            for doc in self.db.aql.execute(query)
        ]

    def update_trait(self, trait: Trait) -> Trait:
        doc = trait.model_dump()
        doc["_key"] = trait.id
        self._traits.replace(doc)
        return trait

    def delete_trait(self, trait_id: str) -> bool:
        """Delete a trait and cascade-remove any trait settings referencing it."""
        keys = list(self.db.aql.execute(
            f"FOR ts IN {TRAITSETTINGS} FILTER ts.trait_id == @tid RETURN ts._key",
            bind_vars={"tid": trait_id}
        ))
        self._delete_traitsettings_subtree(keys)
        self._cleanup_lifepath_trait_refs(trait_id)
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

    # ── Life Paths ────────────────────────────────────

    def create_lifepath(self, lp: LifePath) -> LifePath:
        doc = lp.model_dump()
        doc["_key"] = lp.id
        self._life_paths.insert(doc)
        return lp

    def get_lifepath(self, lp_id: str) -> Optional[LifePath]:
        doc = self._life_paths.get(lp_id)
        return LifePath.model_validate({**doc, "id": doc["_key"]}) if doc else None

    def list_lifepaths_by_universe(self, universe: str) -> list[LifePath]:
        query = f"""
            FOR lp IN {LIFE_PATHS}
            FILTER lp.universe == @universe
            SORT lp.name ASC
            RETURN lp
        """
        return [
            LifePath.model_validate({**doc, "id": doc["_key"]})
            for doc in self.db.aql.execute(query, bind_vars={"universe": universe})
        ]

    def list_all_lifepaths(self) -> list[LifePath]:
        query = f"FOR lp IN {LIFE_PATHS} SORT lp.universe ASC, lp.name ASC RETURN lp"
        return [
            LifePath.model_validate({**doc, "id": doc["_key"]})
            for doc in self.db.aql.execute(query)
        ]

    def update_lifepath(self, lp: LifePath) -> LifePath:
        doc = lp.model_dump()
        doc["_key"] = lp.id
        self._life_paths.replace(doc)
        return lp

    def delete_lifepath(self, lp_id: str) -> bool:
        """Delete a life path and the roll tables it owns."""
        self.db.aql.execute(
            f"FOR t IN {ROLL_TABLES} FILTER t.life_path == @lp REMOVE t IN {ROLL_TABLES}",
            bind_vars={"lp": lp_id},
        )
        try:
            self._life_paths.delete(lp_id)
            return True
        except Exception:
            return False

    # ── Roll Tables ──────────────────────────────────

    def create_roll_table(self, table: RollTable) -> RollTable:
        doc = table.model_dump()
        doc["_key"] = table.id
        self._roll_tables.insert(doc)
        return table

    def get_roll_table(self, table_id: str) -> Optional[RollTable]:
        doc = self._roll_tables.get(table_id)
        return RollTable.model_validate({**doc, "id": doc["_key"]}) if doc else None

    def list_roll_tables(self, life_path_id: Optional[str] = None) -> list[RollTable]:
        if life_path_id is not None:
            query = f"""
                FOR t IN {ROLL_TABLES}
                FILTER t.life_path == @lp
                SORT t.name ASC
                RETURN t
            """
            docs = self.db.aql.execute(query, bind_vars={"lp": life_path_id})
        else:
            query = f"FOR t IN {ROLL_TABLES} SORT t.name ASC RETURN t"
            docs = self.db.aql.execute(query)
        return [RollTable.model_validate({**doc, "id": doc["_key"]}) for doc in docs]

    def update_roll_table(self, table: RollTable) -> RollTable:
        doc = table.model_dump()
        doc["_key"] = table.id
        self._roll_tables.replace(doc)
        return table

    def delete_roll_table(self, table_id: str) -> bool:
        try:
            self._roll_tables.delete(table_id)
            return True
        except Exception:
            return False

    def set_roll_table_position(self, table_id: str, x: Optional[float], y: Optional[float]) -> Optional[RollTable]:
        table = self.get_roll_table(table_id)
        if table is None:
            return None
        table.canvas_x = x
        table.canvas_y = y
        self.update_roll_table(table)
        return table

    def clear_roll_table_positions(self, life_path_id: str) -> int:
        count = 0
        for table in self.list_roll_tables(life_path_id):
            table.canvas_x = None
            table.canvas_y = None
            self.update_roll_table(table)
            count += 1
        return count

    def _cleanup_lifepath_trait_refs(self, trait_id: str) -> None:
        """Remove `trait_id` from every life path that references it.

        Deletes curriculum items / qualification blocks that become empty
        as a result.  Saves each modified life path.
        """
        if self.db is not None:
            query = f"""
                FOR lp IN {LIFE_PATHS}
                FILTER CONTAINS(TO_STRING(lp), @tid)
                RETURN lp
            """
            docs = list(self.db.aql.execute(query, bind_vars={"tid": trait_id}))
        else:
            docs = []
            for lp in self._life_paths_docs:
                if trait_id in str(lp):
                    docs.append(lp)

        for doc in docs:
            lp = LifePath.model_validate({**doc, "id": doc["_key"]})
            changed = False

            # Life paths now reference traits only through ``discovery``;
            # term content lives in roll tables.
            if lp.discovery and trait_id in lp.discovery.possesses_trait:
                lp.discovery.possesses_trait = [t for t in lp.discovery.possesses_trait if t != trait_id]
                changed = True

            if lp.discovery and trait_id in lp.discovery.has_trait_rating:
                del lp.discovery.has_trait_rating[trait_id]
                changed = True

            if changed:
                self.update_lifepath(lp)

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
            setting_keys = list(self.db.aql.execute(
                f"FOR ts IN {TRAITSETTINGS} FILTER ts.trait_id IN @tids RETURN ts._key",
                bind_vars={"tids": trait_keys}
            ))
            ts_removed = self._delete_traitsettings_subtree(setting_keys)
        for tkey in trait_keys:
            self._cleanup_lifepath_trait_refs(tkey)
            try: self._traits.delete(tkey)
            except Exception: pass
        # Trait-set settings (entity↔traitset edges) reference the set by id.
        self.db.aql.execute(
            f"FOR tss IN {TRAITSETSETTINGS} FILTER tss.traitset_id == @tsid REMOVE tss IN {TRAITSETSETTINGS}",
            bind_vars={"tsid": traitset_id},
        )
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
        ts = self._provision_trait_default_sfx(ts)
        doc = ts.model_dump()
        doc["_key"] = ts.id
        if ts.from_type == "relationship":
            doc["_from"] = f"{RELATIONSHIPS}/{ts.entity_id}"
        elif ts.from_type == "projection":
            doc["_from"] = f"{PROJECTIONS}/{ts.projection_id or ts.entity_id}"
        elif ts.from_type == "traitsetting":
            doc["_from"] = f"{TRAITSETTINGS}/{ts.parent_traitsetting_id}"
        else:
            doc["_from"] = f"{ENTITIES}/{ts.entity_id}"
        doc["_to"] = f"{TRAITS}/{ts.trait_id}"
        self._traitsettings.insert(doc)
        return ts

    def _provision_trait_default_sfx(self, ts: TraitSetting) -> TraitSetting:
        """Provision a trait's default SFX onto a newly-created instance.

        ``Trait.default_sfx_ids`` is a provisioning template (seeded at grant
        time, never a read-time authority). Merge it into the instance's
        ``sfx_ids`` so a freshly-granted trait carries its default SFX
        immediately — the #218 carry-over.
        """
        trait = self.get_trait(ts.trait_id)
        defaults = list(trait.default_sfx_ids or []) if trait is not None else []
        if not defaults:
            return ts
        merged = list(dict.fromkeys(defaults + list(ts.sfx_ids or [])))
        if merged == list(ts.sfx_ids or []):
            return ts
        return ts.model_copy(update={"sfx_ids": merged})

    def get_traitsetting(self, ts_id: str) -> Optional[TraitSetting]:
        doc = self._traitsettings.get(ts_id)
        return TraitSetting.model_validate({**doc, "id": doc["_key"]}) if doc else None

    def get_traitsettings_for_entity(self, entity_id: str) -> list[TraitSetting]:
        query = f"""
            FOR ts IN {TRAITSETTINGS}
            FILTER ts.entity_id == @eid AND ts.from_type != 'traitsetting'
            RETURN ts
        """
        return [
            TraitSetting.model_validate({**doc, "id": doc["_key"]})
            for doc in self.db.aql.execute(query, bind_vars={"eid": entity_id})
        ]

    def list_all_traitsettings(self) -> list[TraitSetting]:
        """Return every trait setting (entity↔trait edge)."""
        query = f"""
            FOR ts IN {TRAITSETTINGS}
            RETURN ts
        """
        return [
            TraitSetting.model_validate({**doc, "id": doc["_key"]})
            for doc in self.db.aql.execute(query)
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

    def get_sub_traitsettings(self, parent_traitsetting_id: str) -> list[TraitSetting]:
        """Return sub-trait settings nested under a parent trait setting.

        Sub-traits are stored in the same `traitsettings` edge collection, with
        ``from_type == 'traitsetting'`` and ``_from`` anchored to the parent's
        document (mirroring the relationship edge-anchoring pattern).
        """
        query = f"""
            FOR ts IN {TRAITSETTINGS}
            FILTER ts.from_type == 'traitsetting'
                AND ts.parent_traitsetting_id == @pid
            SORT ts.traitset_id, ts.trait_id
            RETURN ts
        """
        return [
            TraitSetting.model_validate({**doc, "id": doc["_key"]})
            for doc in self.db.aql.execute(
                query, bind_vars={"pid": parent_traitsetting_id}
            )
        ]

    def get_traitsettings_by_trait(self, trait_id: str) -> list[TraitSetting]:
        """Return every trait setting that references a trait (across entities)."""
        query = f"""
            FOR ts IN {TRAITSETTINGS}
            FILTER ts.trait_id == @tid
            RETURN ts
        """
        return [
            TraitSetting.model_validate({**doc, "id": doc["_key"]})
            for doc in self.db.aql.execute(query, bind_vars={"tid": trait_id})
        ]

    def get_traitsettings_by_traitset_all(self, traitset_id: str) -> list[TraitSetting]:
        """Return every trait setting belonging to a trait set (across entities)."""
        query = f"""
            FOR ts IN {TRAITSETTINGS}
            FILTER ts.traitset_id == @tsid
            RETURN ts
        """
        return [
            TraitSetting.model_validate({**doc, "id": doc["_key"]})
            for doc in self.db.aql.execute(query, bind_vars={"tsid": traitset_id})
        ]

    def update_traitsetting(self, ts: TraitSetting) -> TraitSetting:
        doc = ts.model_dump()
        doc["_key"] = ts.id
        if ts.from_type == "relationship":
            doc["_from"] = f"{RELATIONSHIPS}/{ts.entity_id}"
        elif ts.from_type == "projection":
            doc["_from"] = f"{PROJECTIONS}/{ts.projection_id or ts.entity_id}"
        elif ts.from_type == "traitsetting":
            doc["_from"] = f"{TRAITSETTINGS}/{ts.parent_traitsetting_id}"
        else:
            doc["_from"] = f"{ENTITIES}/{ts.entity_id}"
        doc["_to"] = f"{TRAITS}/{ts.trait_id}"
        self._traitsettings.replace(doc)
        return ts

    def _delete_traitsettings_subtree(self, keys: list[str]) -> int:
        """Delete trait settings and their nested sub-trait descendants.

        ``keys`` are trait setting ``_key``s. Sub-traits are anchored via
        ``parent_traitsetting_id``, so we walk descendants iteratively rather
        than rely on a graph traversal (an edge document cannot be a graph
        vertex in Arango). Returns the number of documents removed.
        """
        pending = set(keys)
        removed = 0
        removed_keys: list[str] = []
        while pending:
            batch = list(pending)
            # Collect children before removing the current batch.
            children = set(self.db.aql.execute(
                f"FOR ts IN {TRAITSETTINGS} FILTER ts.parent_traitsetting_id IN @keys RETURN ts._key",
                bind_vars={"keys": batch},
            ))
            result = self.db.aql.execute(
                f"FOR ts IN {TRAITSETTINGS} FILTER ts._key IN @keys REMOVE ts IN {TRAITSETTINGS} RETURN OLD._key",
                bind_vars={"keys": batch},
            )
            batch_removed = list(result)
            removed += len(batch_removed)
            removed_keys.extend(batch_removed)
            pending = children
        if removed_keys:
            # Clean up any scheduled-event timers anchored to the removed settings.
            self.delete_scheduled_events(target_type="trait_setting", target_ids=removed_keys)
        return removed

    def delete_traitsetting(self, ts_id: str) -> bool:
        try:
            # Cascade: remove this setting and all nested sub-traits.
            self._delete_traitsettings_subtree([ts_id])
            return True
        except Exception:
            return False

    # ── Trait Set Settings ─────────────────────────────

    def create_traitsetsetting(self, tss: TraitSetSetting) -> TraitSetSetting:
        doc = tss.model_dump()
        doc["_key"] = tss.id
        if tss.from_type == "projection":
            doc["_from"] = f"{PROJECTIONS}/{tss.projection_id or tss.entity_id}"
        else:
            doc["_from"] = f"{ENTITIES}/{tss.entity_id}"
        doc["_to"] = f"{TRAITSETS}/{tss.traitset_id}"
        self._traitsetsettings.insert(doc)
        return tss

    def get_traitsetsetting(self, tss_id: str) -> Optional[TraitSetSetting]:
        doc = self._traitsetsettings.get(tss_id)
        return TraitSetSetting.model_validate({**doc, "id": doc["_key"]}) if doc else None

    def get_traitsetsettings_for_entity(self, entity_id: str) -> list[TraitSetSetting]:
        query = f"""
            FOR tss IN {TRAITSETSETTINGS}
            FILTER tss.entity_id == @eid
            RETURN tss
        """
        return [
            TraitSetSetting.model_validate({**doc, "id": doc["_key"]})
            for doc in self.db.aql.execute(query, bind_vars={"eid": entity_id})
        ]

    def list_all_traitsetsettings(self) -> list[TraitSetSetting]:
        """Return every trait set setting (entity↔traitset edge)."""
        query = f"""
            FOR tss IN {TRAITSETSETTINGS}
            RETURN tss
        """
        return [
            TraitSetSetting.model_validate({**doc, "id": doc["_key"]})
            for doc in self.db.aql.execute(query)
        ]

    def get_effective_traitsetsettings(
        self, entity_id: str, universes: list[str]
    ) -> list[TraitSetSetting]:
        """Trait set settings active in a set of universes.

        Entity-anchored settings are gated by the trait set's universes
        intersecting ``universes``. Projection-anchored settings are gated by
        their projection's ``origin_universe`` (falling back to the key suffix).
        """
        query = f"""
            FOR tss IN {TRAITSETSETTINGS}
            FILTER tss.entity_id == @eid
            LET is_projection = (tss.from_type == 'projection')
            LET proj = is_projection ? DOCUMENT(tss._from) : null
            LET origin = proj != null
                ? (proj.origin_universe ? proj.origin_universe : SPLIT(proj._key, ":")[1])
                : null
            LET set_doc = DOCUMENT(CONCAT('{TRAITSETS}/', tss.traitset_id))
            FILTER (
                NOT is_projection
                AND (set_doc == null OR LENGTH(INTERSECTION(set_doc.universes, @universes)) > 0)
            )
            OR (
                is_projection AND proj != null
                AND origin IN @universes
                AND (set_doc == null OR origin IN set_doc.universes)
            )
            RETURN tss
        """
        return [
            TraitSetSetting.model_validate({**doc, "id": doc["_key"]})
            for doc in self.db.aql.execute(
                query, bind_vars={"eid": entity_id, "universes": universes}
            )
        ]

    def update_traitsetsetting(self, tss: TraitSetSetting) -> TraitSetSetting:
        doc = tss.model_dump()
        doc["_key"] = tss.id
        if tss.from_type == "projection":
            doc["_from"] = f"{PROJECTIONS}/{tss.projection_id or tss.entity_id}"
        else:
            doc["_from"] = f"{ENTITIES}/{tss.entity_id}"
        doc["_to"] = f"{TRAITSETS}/{tss.traitset_id}"
        self._traitsetsettings.replace(doc)
        return tss

    def delete_traitsetsetting(self, tss_id: str) -> bool:
        try:
            self._traitsetsettings.delete(tss_id)
            return True
        except Exception:
            return False

    # ── SFX Owners ───────────────────────────────────

    def get_sfx_owner(self, owner_id: str) -> Optional[SfxOwner]:
        doc = self._sfx_owners.get(owner_id)
        return SfxOwner.model_validate({**doc, "id": doc["_key"]}) if doc else None

    def create_sfx_owner(self, owner: SfxOwner) -> SfxOwner:
        doc = owner.model_dump()
        doc["_key"] = owner.id
        self._sfx_owners.insert(doc)
        return owner

    def update_sfx_owner(self, owner: SfxOwner) -> SfxOwner:
        doc = owner.model_dump()
        doc["_key"] = owner.id
        self._sfx_owners.replace(doc)
        return owner

    def delete_sfx_owner(self, owner_id: str) -> bool:
        try:
            self._sfx_owners.delete(owner_id)
            return True
        except Exception:
            return False

    # ── Scheduled Events ──────────────────────────────

    def create_scheduled_event(self, event: ScheduledEvent) -> ScheduledEvent:
        doc = event.model_dump()
        doc["_key"] = event.id
        self._scheduled_events.insert(doc)
        return event

    def get_scheduled_event(self, event_id: str) -> Optional[ScheduledEvent]:
        doc = self._scheduled_events.get(event_id)
        return ScheduledEvent.model_validate({**doc, "id": doc["_key"]}) if doc else None

    def update_scheduled_event(self, event: ScheduledEvent) -> ScheduledEvent:
        doc = event.model_dump()
        doc["_key"] = event.id
        self._scheduled_events.replace(doc)
        return event

    def delete_scheduled_event(self, event_id: str) -> bool:
        try:
            self._scheduled_events.delete(event_id)
            return True
        except Exception:
            return False

    def delete_scheduled_events(
        self,
        *,
        target_type: Optional[str] = None,
        target_id: Optional[str] = None,
        target_ids: Optional[list[str]] = None,
    ) -> int:
        """Delete scheduled events scoped to target owners; return count removed.

        At least one scope must be given (a bare call would wipe the store).
        ``target_id`` scopes to a single owner; ``target_ids`` to a set of owners.
        """
        if target_type is None and target_id is None and target_ids is None:
            raise ValueError("delete_scheduled_events requires a scope")
        filters = []
        bind_vars = {}
        if target_type is not None:
            filters.append("e.target_type == @target_type")
            bind_vars["target_type"] = target_type
        if target_id is not None:
            filters.append("e.target_id == @target_id")
            bind_vars["target_id"] = target_id
        if target_ids is not None:
            filters.append("e.target_id IN @target_ids")
            bind_vars["target_ids"] = target_ids
        query = (
            f"FOR e IN {SCHEDULED_EVENTS} "
            f"FILTER {' AND '.join(filters)} "
            f"REMOVE e IN {SCHEDULED_EVENTS} RETURN OLD._key"
        )
        return len(list(self.db.aql.execute(query, bind_vars=bind_vars)))

    def list_all_scheduled_events(self) -> list[ScheduledEvent]:
        query = f"FOR e IN {SCHEDULED_EVENTS} RETURN e"
        return [
            ScheduledEvent.model_validate({**doc, "id": doc["_key"]})
            for doc in self.db.aql.execute(query)
        ]

    def list_scheduled_events(
        self,
        target_type: Optional[str] = None,
        target_id: Optional[str] = None,
        target_ids: Optional[list[str]] = None,
    ) -> list[ScheduledEvent]:
        """List scheduled events, optionally scoped to target owners.

        ``target_type`` is ``"entity"`` or ``"trait_setting"``. ``target_id``
        scopes to a single owner (entity id or trait-setting id); ``target_ids``
        scopes to a set of owners. When every filter is omitted this is the full
        store; otherwise the query is filtered on the owner columns.
        """
        if target_type is None and target_id is None and target_ids is None:
            return self.list_all_scheduled_events()
        filters = []
        bind_vars = {}
        if target_type is not None:
            filters.append("e.target_type == @target_type")
            bind_vars["target_type"] = target_type
        if target_id is not None:
            filters.append("e.target_id == @target_id")
            bind_vars["target_id"] = target_id
        if target_ids is not None:
            filters.append("e.target_id IN @target_ids")
            bind_vars["target_ids"] = target_ids
        query = f"FOR e IN {SCHEDULED_EVENTS} FILTER {' AND '.join(filters)} RETURN e"
        return [
            ScheduledEvent.model_validate({**doc, "id": doc["_key"]})
            for doc in self.db.aql.execute(query, bind_vars=bind_vars)
        ]

    def list_sfx_owners(self) -> list[SfxOwner]:
        """Return every SFX owner bucket (``table``, ``gm``)."""
        return [
            SfxOwner.model_validate({**doc, "id": doc["_key"]})
            for doc in self._sfx_owners.all()
        ]

    def get_relationship_traitsettings(self, edge_key: str) -> list[TraitSetting]:
        """Get trait settings attached to a relationship edge."""
        query = f"""
            FOR ts IN {TRAITSETTINGS}
            FILTER ts.entity_id == @ekey AND ts.from_type == 'relationship'
            RETURN ts
        """
        return [
            TraitSetting.model_validate({**doc, "id": doc["_key"]})
            for doc in self.db.aql.execute(query, bind_vars={"ekey": edge_key})
        ]

    def get_relationship_traits_for_entities(
        self, entity_id_a: str, entity_id_b: str
    ) -> list[TraitSetting]:
        """Get all trait settings on relationships between two entities (either direction)."""
        results: list[TraitSetting] = []
        for rel_type in ["relation", "associate", "gifted", "suspects", "hostile_to"]:
            for frm, to in [(entity_id_a, entity_id_b), (entity_id_b, entity_id_a)]:
                rel = self.get_relationship(frm, to, rel_type)
                if rel:
                    results.extend(self.get_relationship_traitsettings(rel["_key"]))
        return results

    def get_relationship_traitsettings_for_entity(self, entity_id: str) -> list[dict]:
        """Outgoing relationship traits — what ``entity_id`` holds *about* others.

        Only edges where the entity (or one of its projections) is the ``_from``
        side are returned, so each sheet shows what they think of others, not what
        others think of them. The contact is always the edge's ``_to`` endpoint.
        """
        proj_ids = [p.id for p in self.get_projections_for_entity(entity_id)]
        from_refs = [f"{ENTITIES}/{entity_id}"] + [f"{PROJECTIONS}/{pid}" for pid in proj_ids]

        query = f"""
            FOR r IN {RELATIONSHIPS}
            FILTER r._from IN @from_refs
            RETURN r
        """
        edges = list(self.db.aql.execute(query, bind_vars={"from_refs": from_refs}))

        results: list[dict] = []
        for edge in edges:
            contact = self._resolve_relationship_contact(edge["_to"])
            if contact is None:
                continue
            for ts in self.get_relationship_traitsettings(edge["_key"]):
                results.append({
                    "setting": ts,
                    "contact_id": contact["id"],
                    "contact_name": contact["name"],
                    "contact_type": contact["type"],
                    "edge_type": edge.get("type", ""),
                })
        return results

    def _resolve_relationship_contact(self, ref: str) -> dict | None:
        """Resolve a relationship endpoint ref to {id, name, type}."""
        if ref.startswith(f"{ENTITIES}/"):
            e = self.get_entity(ref[len(f"{ENTITIES}/"):])
            if e is not None:
                return {"id": e.id, "name": e.name, "type": e.type.value}
        elif ref.startswith(f"{PROJECTIONS}/"):
            p = self.get_projection(ref[len(f"{PROJECTIONS}/"):])
            if p is not None:
                e = self.get_entity(p.entity_id)
                if e is not None:
                    return {"id": e.id, "name": e.name, "type": e.type.value}
        return None

    # ── Character Assembly ────────────────────────────

    def assemble_character(self, entity_id: str) -> Optional[CharacterView]:
        entity = self.get_entity(entity_id)
        if entity is None:
            return None

        projections = self.get_projections_for_entity(entity_id)
        # All trait settings (morph + ego)
        all_settings = self.get_traitsettings_for_entity(entity_id)

        return CharacterView(
            entity=entity,
            projections=projections,
            trait_settings=all_settings,
        )

    def _active_universe(self, entity: Entity) -> str:
        """The entity's active universe — the active projection's current universe.

        Falls back to the legacy ``current_universe`` field when the entity has
        no ``current_projection`` (or its projection is missing).
        """
        if entity.current_projection:
            proj = self.get_projection(entity.current_projection)
            if proj and proj.universe:
                return proj.universe
        return entity.current_universe

    def _active_location(self, entity: Entity) -> Optional[str]:
        """The entity's active location — the active projection's current location.

        Falls back to the denormalized ``current_location`` cache when the entity
        has no active projection (or its projection has no location).
        """
        if entity.current_projection:
            proj = self.get_projection(entity.current_projection)
            if proj and proj.current_location:
                return proj.current_location
        return entity.current_location

    def effective_universes(self, entity: Entity) -> list[str]:
        """Compute the set of universes governing the entity's trait availability.

        Union of: the active universe (active projection), all NATIVE projection
        universes when the entity has more than one (a multiversal being — this
        replaces the removed ``transversal`` flag), self-scoped attunements, and
        domain-scoped attunements from entities at this entity's location or its
        ancestors.
        """
        result: set[str] = set()
        active = self._active_universe(entity)
        if active:
            result.add(active)
        native_universes = [
            p.universe for p in self.get_projections_for_entity(entity.id)
            if p.transversal_type == TransversalType.NATIVE and p.universe
        ]
        if len(native_universes) > 1:
            result.update(native_universes)
        for att in entity.attunements:
            if att.scope == AttunementScope.SELF:
                result.add(att.universe)
        result.update(self._domain_attunement_universes(entity))
        return sorted(result)

    def is_transversal(self, entity: Entity) -> bool:
        """Whether an entity exists in multiple universes (multiversal).

        Occupant types (character/gmc/asset) are transversal when they hold more
        than one NATIVE projection in distinct universes. Factions are
        transversal when they list more than one active universe. Everything else
        (locations, universes, subtraits, relations) is universe-local.
        """
        if entity.type == EntityType.FACTION:
            return len(set(entity.active_universes or [])) > 1
        if entity.type in (EntityType.CHARACTER, EntityType.GMC, EntityType.ASSET):
            native = {
                p.universe for p in self.get_projections_for_entity(entity.id)
                if p.transversal_type == TransversalType.NATIVE and p.universe
            }
            return len(native) > 1
        return False

    def _domain_attunement_universes(self, entity: Entity) -> set[str]:
        """Universes from domain-scoped attunements over this entity's active location chain."""
        location = self._active_location(entity)
        if not location:
            return set()
        chain = [location] + self.get_location_ancestors(location)
        query = f"""
            FOR e IN {ENTITIES}
            FILTER e.current_location IN @chain AND LENGTH(e.attunements) > 0
            FOR att IN e.attunements
            FILTER att.scope == 'domain'
            RETURN DISTINCT att.universe
        """
        return set(self.db.aql.execute(query, bind_vars={"chain": chain}))

    def get_effective_traitsettings(
        self, entity_id: str, universes: list[str]
    ) -> list[TraitSetting]:
        """Get trait settings active in a set of universes.

        Ego traits (``from_type='entity'``) are always returned. Projection-anchored
        morph traits are gated by their projection's ``origin_universe`` being in
        ``universes`` (falling back to the projection key's universe suffix for
        pre-migration data).
        """
        query = f"""
            FOR ts IN {TRAITSETTINGS}
            FILTER ts.entity_id == @eid
            LET is_projection = (ts.from_type == 'projection')
            LET proj = is_projection ? DOCUMENT(ts._from) : null
            LET origin = proj != null
                ? (proj.origin_universe ? proj.origin_universe : SPLIT(proj._key, ":")[1])
                : null
            LET trait = DOCUMENT(ts._to)
            LET set_doc = (trait.traitset_id != null)
                ? DOCUMENT(CONCAT('{TRAITSETS}/', trait.traitset_id)) : null
            FILTER ts.from_type == 'entity'
                OR (
                    is_projection AND proj != null
                    AND origin IN @universes
                    AND origin IN trait.universes
                    AND (set_doc == null OR origin IN set_doc.universes)
                )
            RETURN ts
        """
        return [
            TraitSetting.model_validate({**doc, "id": doc["_key"]})
            for doc in self.db.aql.execute(
                query, bind_vars={"eid": entity_id, "universes": universes}
            )
        ]

    # ── Queries ───────────────────────────────────────

    def get_prompt_traitsettings(
        self, entity_id: str, universes: list[str], projection_id: str | None = None
    ) -> list[TraitSetting]:
        """Trait settings used to build a generation prompt.

        Returns ego traits (``from_type='entity'`` — the entity soul) and, when
        ``projection_id`` is given, that projection's morph traits only.
        Projection-anchored traits are excluded for entity-level generation
        (``projection_id=None``).
        """
        query = f"""
            FOR ts IN {TRAITSETTINGS}
            FILTER ts.entity_id == @eid
            LET is_projection = (ts.from_type == 'projection')
            LET proj = is_projection ? DOCUMENT(ts._from) : null
            LET origin = proj != null
                ? (proj.origin_universe ? proj.origin_universe : SPLIT(proj._key, ":")[1])
                : null
            LET trait = DOCUMENT(ts._to)
            LET set_doc = (trait.traitset_id != null)
                ? DOCUMENT(CONCAT('{TRAITSETS}/', trait.traitset_id)) : null
            FILTER ts.from_type == 'entity'
                OR (
                    is_projection AND @projection_id != null AND proj != null
                    AND proj._key == @projection_id
                    AND origin IN @universes
                    AND origin IN trait.universes
                    AND (set_doc == null OR origin IN set_doc.universes)
                )
            RETURN ts
        """
        return [
            TraitSetting.model_validate({**doc, "id": doc["_key"]})
            for doc in self.db.aql.execute(
                query,
                bind_vars={"eid": entity_id, "universes": universes, "projection_id": projection_id},
            )
        ]

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
            FILTER ts.polarity != 'negative'
            RETURN DISTINCT ts.entity_id
        """
        cursor = self.db.aql.execute(
            query,
            bind_vars={"trait_ref": f"{TRAITS}/{trait.id}"},
        )
        return list(cursor)

    # ── Relationships ─────────────────────────────────

    def create_relationship(
        self, from_id: str, to_id: str, rel_type: str, description: str = "",
        from_projection: bool = False, to_projection: bool = False,
    ) -> dict:
        edge = {
            "_from": f"{PROJECTIONS}/{from_id}" if from_projection else f"{ENTITIES}/{from_id}",
            "_to": f"{PROJECTIONS}/{to_id}" if to_projection else f"{ENTITIES}/{to_id}",
            "type": rel_type,
        }
        if description:
            edge["description"] = description
        created = self._relationships.insert(edge)

        # A sub-location needs a matching zone hotspot on its parent's background
        # or it is invisible in the location viewer. Register one (centered) on
        # ``super`` edge creation so API/MCP-authored children show up immediately;
        # the GM can drag the dot into place afterwards.
        if rel_type == "super":
            self._ensure_child_zone(from_id, to_id)

        return created

    def _ensure_child_zone(self, child_id: str, parent_id: str) -> None:
        """Add a default zone to ``parent_id`` for the child sub-location, if absent."""
        parent = self.get_entity(parent_id)
        child = self.get_entity(child_id)
        if parent is None or child is None:
            return
        if parent.type != EntityType.LOCATION or child.type != EntityType.LOCATION:
            return
        for zone in parent.zones:
            if zone.location_id == child_id or (not zone.location_id and zone.name == child.name):
                return  # already registered
        parent.zones.append(Zone(name=child.name, x=50.0, y=50.0, location_id=child_id))
        self.update_entity(parent)

    def get_relationship(
        self, from_id: str, to_id: str, rel_type: str,
        from_projection: bool = False, to_projection: bool = False,
    ) -> dict | None:
        """Get a directional relationship edge between two entities.

        ``from_projection`` / ``to_projection`` match edges whose respective
        endpoint is a projection.
        """
        from_ref = f"{PROJECTIONS}/{from_id}" if from_projection else f"{ENTITIES}/{from_id}"
        to_ref = f"{PROJECTIONS}/{to_id}" if to_projection else f"{ENTITIES}/{to_id}"
        query = f"""
            FOR r IN {RELATIONSHIPS}
            FILTER r._from == @from_ref AND r._to == @to_ref AND r.type == @rel_type
            LIMIT 1
            RETURN r
        """
        cursor = list(self.db.aql.execute(query, bind_vars={
            "from_ref": from_ref,
            "to_ref": to_ref,
            "rel_type": rel_type,
        }))
        return cursor[0] if cursor else None

    def get_relationship_by_key(self, edge_key: str) -> dict | None:
        """Get a relationship edge by its ArangoDB ``_key``."""
        return self._relationships.get(edge_key)

    def delete_relationship(
        self, from_id: str, to_id: str, rel_type: str,
        from_projection: bool = False, to_projection: bool = False,
    ) -> bool:
        """Delete a directional relationship edge and its trait settings.

        Relationship-anchored trait settings (``from_type == 'relationship'``)
        reference the edge by ``_key``; they must be removed with the edge or
        they orphan (including nested sub-traits and their scheduled timers).
        """
        from_ref = f"{PROJECTIONS}/{from_id}" if from_projection else f"{ENTITIES}/{from_id}"
        to_ref = f"{PROJECTIONS}/{to_id}" if to_projection else f"{ENTITIES}/{to_id}"
        match = {"from_ref": from_ref, "to_ref": to_ref, "rel_type": rel_type}
        edge_keys = list(self.db.aql.execute(
            f"""
            FOR r IN {RELATIONSHIPS}
            FILTER r._from == @from_ref AND r._to == @to_ref AND r.type == @rel_type
            RETURN r._key
            """,
            bind_vars=match,
        ))
        if edge_keys:
            rel_ts_keys = list(self.db.aql.execute(
                f"""
                FOR ts IN {TRAITSETTINGS}
                FILTER ts.from_type == 'relationship' AND ts.entity_id IN @keys
                RETURN ts._key
                """,
                bind_vars={"keys": edge_keys},
            ))
            if rel_ts_keys:
                self._delete_traitsettings_subtree(rel_ts_keys)
            self.db.aql.execute(
                f"""
                FOR r IN {RELATIONSHIPS}
                FILTER r._from == @from_ref AND r._to == @to_ref AND r.type == @rel_type
                REMOVE r IN {RELATIONSHIPS}
                """,
                bind_vars=match,
            )
        return bool(edge_keys)

    # ── Plan (staging) CRUD ──────────────────────────

    def create_plan_entity(self, doc: dict) -> dict:
        """Insert a staged entity draft (document must include ``plan_id``)."""
        return self._plan_entities.insert(doc)

    def get_plan_entity(self, key: str) -> dict | None:
        return self._plan_entities.get(key)

    def list_plan_entities(self, plan_id: str) -> list[dict]:
        query = f"""
            FOR e IN {PLAN_ENTITIES}
            FILTER e.plan_id == @pid
            SORT e._key
            RETURN e
        """
        return list(self.db.aql.execute(query, bind_vars={"pid": plan_id}))

    def delete_plan_entities(self, plan_id: str) -> int:
        query = f"""
            FOR e IN {PLAN_ENTITIES}
            FILTER e.plan_id == @pid
            REMOVE e IN {PLAN_ENTITIES}
            RETURN OLD
        """
        return len(list(self.db.aql.execute(query, bind_vars={"pid": plan_id})))

    def create_plan_relationship(self, doc: dict) -> dict:
        """Insert a staged relationship draft (edge; must include ``plan_id``)."""
        return self._plan_relationships.insert(doc)

    def list_plan_relationships(self, plan_id: str) -> list[dict]:
        query = f"""
            FOR r IN {PLAN_RELATIONSHIPS}
            FILTER r.plan_id == @pid
            SORT r._key
            RETURN r
        """
        return list(self.db.aql.execute(query, bind_vars={"pid": plan_id}))

    def delete_plan_relationships(self, plan_id: str) -> int:
        query = f"""
            FOR r IN {PLAN_RELATIONSHIPS}
            FILTER r.plan_id == @pid
            REMOVE r IN {PLAN_RELATIONSHIPS}
            RETURN OLD
        """
        return len(list(self.db.aql.execute(query, bind_vars={"pid": plan_id})))

    def get_related_entities(self, entity_id: str, name_query: str = "") -> list[dict]:
        """Get entities connected via any relationship edge, optionally filtered by name."""
        eref = f"{ENTITIES}/{entity_id}"
        bind_vars = {"eref": eref}
        query = f"""
            FOR r IN {RELATIONSHIPS}
            FILTER r._from == @eref OR r._to == @eref
            LET other_key = r._from == @eref
                ? PARSE_IDENTIFIER(r._to).key
                : PARSE_IDENTIFIER(r._from).key
            COLLECT key = other_key
            FOR e IN {ENTITIES}
            FILTER e._key == key
        """
        if name_query:
            query += "FILTER CONTAINS(LOWER(e.name), @nq) "
            bind_vars["nq"] = name_query.lower()
        query += """
            SORT e.name
            RETURN { id: e._key, name: e.name }
        """
        rows = list(self.db.aql.execute(query, bind_vars=bind_vars))
        sheet_urls = self._role_urls([r["id"] for r in rows], "sheet", "Small")
        for r in rows:
            r["sheet_portrait"] = sheet_urls.get(r["id"], "")
        return rows

    # ── Messages ──────────────────────────────────────

    def _doc_to_message(self, doc: dict) -> "Message":
        """Convert an ArangoDB messages document to a Message model."""
        return Message(
            id=doc["_key"],
            sender_entity_id=doc["sender_entity_id"],
            recipient_entity_id=doc["recipient_entity_id"],
            kind=doc.get("kind", "letter"),
            title=doc.get("title", ""),
            body=doc.get("body", ""),
            images=doc.get("images", []),
            after_ids=doc.get("after_ids", []),
            threads=doc.get("threads", []),
            created_at=doc.get("created_at", ""),
        )

    def send_message(
        self,
        sender_entity_id: str,
        recipient_entity_id: str,
        body: str = "",
        kind: str = "letter",
        title: str = "",
        images: list[str] | None = None,
        after_ids: list[str] | None = None,
        threads: list[str] | None = None,
    ) -> "Message":
        import uuid
        from datetime import datetime, timezone

        # Journal entries are self-referential — the character writes to themselves
        if kind == "journal":
            recipient_entity_id = sender_entity_id

        msg_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc).isoformat()
        doc = {
            "_key": msg_id,
            "sender_entity_id": sender_entity_id,
            "recipient_entity_id": recipient_entity_id,
            "kind": kind,
            "title": title,
            "body": body,
            "images": images or [],
            "after_ids": after_ids or [],
            "threads": threads or [],
            "created_at": created_at,
        }
        self._messages.insert(doc)
        return self._doc_to_message(doc)

    def get_incoming_messages(self, entity_id: str) -> list["Message"]:
        """Get messages addressed to an entity, newest first."""
        query = f"""
            FOR m IN {MESSAGES}
            FILTER m.recipient_entity_id == @eid
            SORT m.created_at DESC
            RETURN m
        """
        results = self.db.aql.execute(query, bind_vars={"eid": entity_id})
        return [self._doc_to_message(m) for m in results]

    def get_conversation(self, entity_a: str, entity_b: str) -> list["Message"]:
        """Get all messages between two entities (for GM view), newest first."""
        query = f"""
            FOR m IN {MESSAGES}
            FILTER (m.sender_entity_id == @a AND m.recipient_entity_id == @b)
                OR (m.sender_entity_id == @b AND m.recipient_entity_id == @a)
            SORT m.created_at DESC
            RETURN m
        """
        results = self.db.aql.execute(query, bind_vars={"a": entity_a, "b": entity_b})
        return [self._doc_to_message(m) for m in results]

    def get_recent_messages(
        self, since: str = "", kind: str = ""
    ) -> list["Message"]:
        """Get all messages across all entities (GM activity feed), newest first.

        Optionally filter by kind (letter, journal, report, gm_note)
        and/or by a minimum created_at timestamp.
        """
        filters = []
        bind_vars = {}
        if since:
            filters.append("m.created_at >= @since")
            bind_vars["since"] = since
        if kind:
            filters.append("m.kind == @kind")
            bind_vars["kind"] = kind
        filter_clause = f"FILTER {' AND '.join(filters)}" if filters else ""
        query = f"""
            FOR m IN {MESSAGES}
            {filter_clause}
            SORT m.created_at DESC
            LIMIT 200
            RETURN m
        """
        results = self.db.aql.execute(query, bind_vars=bind_vars)
        return [self._doc_to_message(m) for m in results]

    def get_journal(self, entity_id: str) -> list["Message"]:
        """Get an entity's personal journal entries (self-referential, kind=journal)."""
        query = f"""
            FOR m IN {MESSAGES}
            FILTER m.sender_entity_id == @eid
                AND m.recipient_entity_id == @eid
                AND m.kind == 'journal'
            SORT m.created_at DESC
            RETURN m
        """
        results = self.db.aql.execute(query, bind_vars={"eid": entity_id})
        return [self._doc_to_message(m) for m in results]

    # ── Historical records ─────────────────────────────

    def add_historical_record(
        self,
        entity_id: str,
        record_type,
        data: dict,
        universe: str = "",
        session_id: str = "",
    ) -> HistoricalRecord:
        """Append a historical event for an entity.

        ``record_type`` is a ``HistoricalRecordType`` (or its string value).
        ``data`` is the type-specific payload.
        """
        import uuid
        from datetime import datetime, timezone

        rtype = record_type.value if hasattr(record_type, "value") else record_type
        rec_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc).isoformat()
        doc = {
            "_key": rec_id,
            "entity_id": entity_id,
            "record_type": rtype,
            "universe": universe,
            "session_id": session_id,
            "data": data or {},
            "created_at": created_at,
        }
        self._historical_records.insert(doc)
        return HistoricalRecord(
            id=rec_id,
            entity_id=entity_id,
            record_type=rtype,
            universe=universe,
            session_id=session_id,
            data=data or {},
            created_at=created_at,
        )

    def list_historical_records(
        self,
        entity_id: str = "",
        record_type: str = "",
    ) -> list[HistoricalRecord]:
        """List historical records, newest first, optionally filtered."""
        filters = []
        bind_vars = {}
        if entity_id:
            filters.append("h.entity_id == @eid")
            bind_vars["eid"] = entity_id
        if record_type:
            filters.append("h.record_type == @rtype")
            bind_vars["rtype"] = record_type
        where = f"FILTER {' AND '.join(filters)}" if filters else ""
        query = f"""
            FOR h IN {HISTORICAL_RECORDS}
            {where}
            SORT h.created_at DESC
            RETURN h
        """
        results = self.db.aql.execute(query, bind_vars=bind_vars)
        return [
            HistoricalRecord(
                id=h["_key"],
                entity_id=h.get("entity_id", ""),
                record_type=h.get("record_type", "roll_table"),
                universe=h.get("universe", ""),
                session_id=h.get("session_id", ""),
                data=h.get("data") or {},
                created_at=h.get("created_at", ""),
            )
            for h in results
        ]

    def get_all_threads(self) -> list[str]:
        """Return all distinct threads across all messages, sorted."""
        query = f"""
            FOR m IN {MESSAGES}
            FOR tag IN (m.threads || [])
            COLLECT tags = tag
            SORT tags
            RETURN tags
        """
        return list(self.db.aql.execute(query))

    def get_timeline(
        self,
        entity_id: str = "",
        threads: list[str] | None = None,
    ) -> list["Message"]:
        """Fetch messages and return them in topological (causal) order.

        Filters by entity (sender or recipient) and/or threads.
        Orders messages by their ``after_ids`` DAG using Kahn's algorithm.
        Messages with no ``after_ids`` come first; ties break on ``created_at``.
        Cycles are broken by removing the oldest edge and logging a warning.
        """
        import logging
        logger = logging.getLogger(__name__)

        # ── Fetch candidate messages ─────────────────
        filters = []
        bind_vars = {}
        if entity_id:
            filters.append("(m.sender_entity_id == @eid OR m.recipient_entity_id == @eid)")
            bind_vars["eid"] = entity_id
        if threads:
            # Any tag match (OR semantics)
            filters.append("LENGTH(INTERSECTION(m.threads, @tags)) > 0")
            bind_vars["tags"] = tags
        filter_clause = f"FILTER {' AND '.join(filters)}" if filters else ""
        query = f"""
            FOR m IN {MESSAGES}
            {filter_clause}
            RETURN m
        """
        raw = list(self.db.aql.execute(query, bind_vars=bind_vars))
        messages = [self._doc_to_message(m) for m in raw]

        # ── Build index and DAG ───────────────────────
        msg_map = {m.id: m for m in messages}
        in_degree: dict[str, int] = {m.id: 0 for m in messages}
        children: dict[str, list[str]] = {m.id: [] for m in messages}

        for m in messages:
            for after_id in m.after_ids:
                if after_id in msg_map:
                    children.setdefault(after_id, []).append(m.id)
                    in_degree[m.id] = in_degree.get(m.id, 0) + 1

        # ── Kahn's topological sort ───────────────────
        # Start with nodes that have no predecessors
        queue = [m.id for m in messages if in_degree.get(m.id, 0) == 0]
        # Stable sort: floaters tiebreak by created_at descending (newest first for equal-rank)
        queue.sort(key=lambda mid: msg_map[mid].created_at)

        result: list[Message] = []
        while queue:
            node_id = queue.pop(0)
            result.append(msg_map[node_id])
            for child_id in children.get(node_id, []):
                in_degree[child_id] -= 1
                if in_degree[child_id] == 0:
                    queue.append(child_id)
                    # Re-sort to maintain stable order
                    queue.sort(key=lambda mid: msg_map[mid].created_at)

        # ── Cycle detection ───────────────────────────
        if len(result) < len(messages):
            missing = [m.id for m in messages if m.id not in {r.id for r in result}]
            logger.warning(
                "timeline: %d message(s) in cycle, breaking at oldest edge — %s",
                len(missing), missing[:5],
            )
            # Break cycles: for each missing node, remove all after_ids and re-insert
            for mid in missing:
                msg_map[mid].after_ids = []
            result.extend(msg_map[mid] for mid in missing)
            result.sort(key=lambda m: m.created_at, reverse=True)

        return result

    def update_message(
        self, message_id: str, after_ids: list[str] | None = None, threads: list[str] | None = None
    ) -> bool:
        """Update the after_ids and/or threads of an existing message."""
        doc = self._messages.get(message_id)
        if not doc:
            return False
        if after_ids is not None:
            doc["after_ids"] = after_ids
        if threads is not None:
            doc["threads"] = threads
        self._messages.update(doc)
        return True

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

    def location_graph(self) -> dict:
        """Full location hierarchy plus all transversal edges, for the overview canvas."""
        tree = self.location_tree()
        rel_query = f"""
            FOR r IN {RELATIONSHIPS}
            FILTER r.type == 'transversal'
            RETURN {{
                from: PARSE_IDENTIFIER(r._from).key,
                to: PARSE_IDENTIFIER(r._to).key,
                transversal_type: r.transversal_type
            }}
        """
        transversal = list(self.db.aql.execute(rel_query))
        return {"tree": tree, "transversal": transversal}

    def _universe_docs(self) -> list[dict]:
        query = f"""
            FOR e IN {ENTITIES}
            FILTER e.type == 'universe'
            RETURN {{ id: e._key, name: e.name, universe: e.current_universe }}
        """
        return list(self.db.aql.execute(query))

    def _all_location_docs(self) -> list[dict]:
        query = f"""
            FOR e IN {ENTITIES}
            FILTER e.type == 'location'
            RETURN {{ id: e._key, name: e.name, universe: e.current_universe }}
        """
        return list(self.db.aql.execute(query))

    def _all_super_edges(self) -> list[dict]:
        query = f"""
            FOR r IN {RELATIONSHIPS}
            FILTER r.type == 'super'
            RETURN {{ child: PARSE_IDENTIFIER(r._from).key, parent: PARSE_IDENTIFIER(r._to).key }}
        """
        return list(self.db.aql.execute(query))

    def _all_transversal_edges(self) -> list[dict]:
        query = f"""
            FOR r IN {RELATIONSHIPS}
            FILTER r.type == 'transversal'
            RETURN {{ from: PARSE_IDENTIFIER(r._from).key, to: PARSE_IDENTIFIER(r._to).key, transversal_type: r.transversal_type }}
        """
        return list(self.db.aql.execute(query))

    def _faction_member_ids(self, faction_id: str) -> list[str]:
        query = f"""
            FOR r IN {RELATIONSHIPS}
            FILTER r.type == 'membership' AND PARSE_IDENTIFIER(r._to).key == @fid
            RETURN PARSE_IDENTIFIER(r._from).key
        """
        return list(self.db.aql.execute(query, bind_vars={"fid": faction_id}))

    def list_faction_members(self, faction_id: str) -> list[Entity]:
        """Return member entities (character/gmc) of a faction via membership edges."""
        member_ids = self._faction_member_ids(faction_id)
        if not member_ids:
            return []
        query = f"""
            FOR e IN {ENTITIES}
            FILTER e._key IN @mids AND e.type IN ['character', 'gmc']
            RETURN e
        """
        return [
            self._doc_to_entity(doc)
            for doc in self.db.aql.execute(query, bind_vars={"mids": member_ids})
        ]

    def _faction_member_locations(self, faction_id: str) -> set[str]:
        """Location keys where a faction's members are occupants (direct or projected)."""
        member_ids = self._faction_member_ids(faction_id)
        if not member_ids:
            return set()
        query = f"""
            LET direct = (
                FOR e IN {ENTITIES}
                FILTER e._key IN @mids AND e.type IN ['character', 'gmc', 'asset']
                RETURN e.current_location
            )
            LET projected = (
                FOR p IN {PROJECTIONS}
                FILTER p.entity_id IN @mids
                RETURN p.current_location
            )
            FOR loc IN UNION(direct, projected)
            FILTER loc != null
            RETURN DISTINCT loc
        """
        return set(self.db.aql.execute(query, bind_vars={"mids": member_ids}))

    def _role_urls(self, entity_ids: list[str], role: str, variant: str = "Large") -> dict[str, str]:
        """Resolve one image URL per entity for a role tag.

        Each entity is resolved through its active projection (body) first,
        falling back to entity-level images. ``role`` is a canonical role tag
        (background/sheet/navdot); ``variant`` is the static size suffix
        (Large/Small). Animated images return their video URL regardless of
        variant.
        """
        if not entity_ids:
            return {}
        # Map each entity to its active projection id.
        proj_query = f"""
            FOR e IN {ENTITIES}
            FILTER e._key IN @ids
            RETURN {{ id: e._key, current_projection: e.current_projection }}
        """
        current_proj: dict[str, str | None] = {
            row["id"]: row.get("current_projection")
            for row in self.db.aql.execute(proj_query, bind_vars={"ids": entity_ids})
        }
        return {
            eid: url
            for eid in entity_ids
            if (url := self.resolve_role_image(eid, role, current_proj.get(eid), variant)) is not None
        }

    def _navdot_urls(self, entity_ids: list[str]) -> dict[str, str]:
        """Resolve one navdot image URL per entity, projection-scoped first."""
        return self._role_urls(entity_ids, "navdot")

    def _occupants_for_locations(self, location_ids: list[str], faction_id: str | None = None) -> dict:
        """Map location key → occupant dicts, optionally filtered to a faction."""
        if not location_ids:
            return {}

        binds: dict = {"lids": location_ids}
        member_filter = ""
        if faction_id:
            member_ids = self._faction_member_ids(faction_id)
            if not member_ids:
                return {}
            binds["mids"] = member_ids
            member_filter = " AND e._key IN @mids"

        query = f"""
            LET direct = (
                FOR e IN {ENTITIES}
                FILTER e.type IN ['character', 'gmc', 'asset']
                  AND e.current_location IN @lids
                  {member_filter}
                RETURN {{ id: e._key, name: e.name, type: e.type, location_id: e.current_location }}
            )
            LET projected = (
                FOR p IN {PROJECTIONS}
                FILTER p.current_location IN @lids
                FOR e IN {ENTITIES}
                FILTER e._key == p.entity_id AND e.type IN ['character', 'gmc', 'asset']
                  {member_filter}
                RETURN {{ id: e._key, name: e.name, type: e.type, location_id: p.current_location }}
            )
            FOR o IN UNION(direct, projected)
            RETURN o
        """
        rows = list(self.db.aql.execute(query, bind_vars=binds))

        result: dict = {}
        seen: set = set()
        for row in rows:
            key = (row["location_id"], row["id"])
            if key in seen:
                continue
            seen.add(key)
            result.setdefault(row["location_id"], []).append(row)

        occupant_ids = [row["id"] for loc_rows in result.values() for row in loc_rows]
        navdots = self._navdot_urls(occupant_ids)
        memberships = self._faction_memberships_for(occupant_ids)
        for loc_rows in result.values():
            for row in loc_rows:
                row["image"] = navdots.get(row["id"])
                row["factions"] = memberships.get(row["id"], [])
        return result

    def location_canvas(self, root: str = "all", depth: int = -1, focus: str | None = None, faction: str | None = None) -> dict:
        """Return a scoped location graph for the unified relational canvas."""
        universes = self._universe_docs()
        locations = self._all_location_docs()
        super_edges = self._all_super_edges()
        transversal_edges = self._all_transversal_edges()

        location_by_id = {l["id"]: l for l in locations}
        parent_of = {e["child"]: e["parent"] for e in super_edges}
        children_of: dict[str, list[str]] = {}
        for e in super_edges:
            children_of.setdefault(e["parent"], []).append(e["child"])

        included: set[str] = set()
        universe_docs: list[dict] = []

        def walk_children(lid: str, remaining: int) -> None:
            if lid in included or lid not in location_by_id:
                return
            included.add(lid)
            if remaining == 0:
                return
            next_remaining = remaining - 1 if remaining > 0 else -1
            for child in children_of.get(lid, []):
                walk_children(child, next_remaining)

        if root.startswith("location:"):
            loc_id = root.split(":", 1)[1]
            if loc_id in location_by_id:
                included.add(loc_id)
                if loc_id in parent_of and parent_of[loc_id] in location_by_id:
                    included.add(parent_of[loc_id])
                for child in children_of.get(loc_id, []):
                    walk_children(child, depth)
                for t in transversal_edges:
                    if t["from"] == loc_id and t["to"] in location_by_id:
                        included.add(t["to"])
                    elif t["to"] == loc_id and t["from"] in location_by_id:
                        included.add(t["from"])
            universe_docs = []
        else:
            if root.startswith("universe:"):
                uni_key = root.split(":", 1)[1]
                universe_docs = [u for u in universes if u["id"] == uni_key or u["universe"] == uni_key]
            else:
                universe_docs = universes

            uni_keys = {u["universe"] for u in universe_docs}
            all_uni_keys = {u["universe"] for u in universes}
            for loc in locations:
                if loc["id"] in parent_of:
                    continue
                if loc["universe"] in uni_keys:
                    walk_children(loc["id"], depth)
                elif root == "all" and loc["universe"] not in all_uni_keys:
                    walk_children(loc["id"], depth)

        included = {lid for lid in included if lid in location_by_id}

        # When filtering by faction in a full-tree/universe scope, prune the
        # location set to member locations plus their ancestors.
        if faction and not root.startswith("location:"):
            member_locs = self._faction_member_locations(faction)
            keep: set[str] = set()
            for lid in member_locs:
                if lid not in location_by_id:
                    continue
                cur: str | None = lid
                while cur is not None and cur in location_by_id and cur not in keep:
                    keep.add(cur)
                    cur = parent_of.get(cur)
            included = {lid for lid in included if lid in keep}
            universe_docs = [
                u for u in universe_docs
                if any(location_by_id[lid]["universe"] == u["universe"] for lid in included)
            ]

        included_super = [e for e in super_edges if e["child"] in included and e["parent"] in included]
        included_transversal = [t for t in transversal_edges if t["from"] in included and t["to"] in included]

        occupants = self._occupants_for_locations(sorted(included), faction)

        occupant_relations: list[dict] = []
        if occupants:
            occupant_ids = [o["id"] for loc_rows in occupants.values() for o in loc_rows]
            occupant_relations = self._relations_between(occupant_ids)

        faction_doc = None
        if faction:
            f = self.get_entity(faction)
            if f:
                faction_doc = {"id": f.id, "name": f.name}

        return {
            "focus": focus if focus in included else None,
            "faction": faction_doc,
            "universes": universe_docs,
            "locations": [location_by_id[lid] for lid in sorted(included)],
            "super_edges": included_super,
            "transversal_edges": included_transversal,
            "occupants": occupants,
            "occupant_relations": occupant_relations,
        }

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
                RETURN MERGE(DOCUMENT(r._to), {{ transversal_type: r.transversal_type, effects: r.effects || [] }})
            )
            LET occupant_ids = (
                FOR p IN {PROJECTIONS}
                FILTER p.current_location == @lid
                RETURN DISTINCT p.entity_id
            )
            LET occupants = (
                FOR e IN {ENTITIES}
                FILTER e.type IN ['character', 'gmc', 'asset']
                FILTER e._key IN occupant_ids OR e.current_location == @lid
                RETURN {{
                    name: e.name, type: e.type, id: e._key,
                    map_x: e.map_x, map_y: e.map_y, unpublished: e.unpublished == true
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
        result = results[0] if results else default

        # Resolve occupant navdot images from the role tag (not the legacy
        # background_image field). The REST layer can still override with a
        # more specific resolution, but this is the canonical source.
        occ_ids = [o["id"] for o in result.get("occupants", [])]
        navdots = self._navdot_urls(occ_ids)
        for occ in result.get("occupants", []):
            occ["image"] = navdots.get(occ["id"])

        return result

    # ── Relational Canvas ─────────────────────────────

    def canvas_neighborhood(self, location_id: str) -> dict:
        """Return a location's neighborhood for the relational canvas.

        Extends ``navigate_from`` with faction memberships for occupants and
        occupant-to-occupant relationship edges (labeled).
        """
        result = self.navigate_from(location_id)
        if result["location"] is None:
            return result

        occupant_ids = [o["id"] for o in result.get("occupants", [])]
        result["faction_memberships"] = self._faction_memberships_for(occupant_ids)
        result["occupant_relations"] = self._relations_between(occupant_ids)
        return result

    def canvas_faction(self, faction_id: str) -> dict:
        """Return conspyramid data for a faction.

        Returns members (with rank/role), the locations where members are
        placed, ancestor scaffolding for the pruned tree, and labeled
        relations between members.
        """
        faction = self.get_entity(faction_id)
        if faction is None:
            return {"faction": None, "members": [], "locations": [], "ancestors": [], "location_edges": [], "relations": []}

        member_query = f"""
            FOR r IN {RELATIONSHIPS}
            FILTER r.type == 'membership' AND r._to == @faction_ref
            LET member_key = PARSE_IDENTIFIER(r._from).key
            FOR e IN {ENTITIES}
            FILTER e._key == member_key AND e.type IN ['gmc', 'character']
            RETURN {{ id: e._key, name: e.name, location_id: e.current_location, edge_key: r._key }}
        """
        members = list(self.db.aql.execute(
            member_query, bind_vars={"faction_ref": f"{ENTITIES}/{faction_id}"}
        ))

        for m in members:
            m["rank"] = None
            m["role"] = None
            for ts in self.get_relationship_traitsettings(m["edge_key"]):
                if ts.trait_id == "trait-rel-rank" and ts.dice:
                    m["rank"] = dice_list_to_rating(ts.dice)
                elif ts.trait_id == "trait-role-cd1b":
                    m["role"] = ts.statement or ts.trait_id
            m.pop("edge_key", None)

        member_ids = [m["id"] for m in members]
        member_locations = [m["location_id"] for m in members if m["location_id"]]

        locations = self._location_dicts(member_locations)
        location_keys = {l["id"] for l in locations}

        ancestors: set[str] = set()
        for lid in member_locations:
            for a in self.get_location_ancestors(lid):
                ancestors.add(a)
        ancestor_locations = [
            l for l in self._location_dicts(list(ancestors))
            if l["id"] not in location_keys
        ]

        # Super edges among the pruned location set (member locations + their
        # ancestors), so the frontend can render the hierarchy as a tree.
        relevant_ids = list(set(member_locations) | ancestors)
        location_edges: list[dict] = []
        if relevant_ids:
            edge_query = f"""
                FOR r IN {RELATIONSHIPS}
                FILTER r.type == 'super'
                LET child = PARSE_IDENTIFIER(r._from).key
                LET parent = PARSE_IDENTIFIER(r._to).key
                FILTER child IN @ids AND parent IN @ids
                RETURN {{ child: child, parent: parent }}
            """
            location_edges = list(self.db.aql.execute(edge_query, bind_vars={"ids": relevant_ids}))

        relations = self._relations_between(member_ids)

        return {
            "faction": {"id": faction.id, "name": faction.name},
            "members": members,
            "locations": locations,
            "ancestors": ancestor_locations,
            "location_edges": location_edges,
            "relations": relations,
        }

    def canvas_gmc_web(self, gmc_id: str) -> dict:
        """Return a GMC's relational web: the GMC, its location, and direct
        relations to other GMCs plus their locations."""
        gmc = self.get_entity(gmc_id)
        if gmc is None:
            return {"gmc": None, "location": None, "relations": []}

        location = self.get_entity(gmc.current_location) if gmc.current_location else None

        query = f"""
            FOR r IN {RELATIONSHIPS}
            FILTER (r._from == @gmc_ref OR r._to == @gmc_ref)
              AND r.type NOT IN ['super', 'membership', 'agency', 'transversal']
            LET other_key = PARSE_IDENTIFIER(r._from).key == @gid
                ? PARSE_IDENTIFIER(r._to).key
                : PARSE_IDENTIFIER(r._from).key
            FOR e IN {ENTITIES}
            FILTER e._key == other_key AND e.type IN ['gmc', 'character']
            RETURN {{
                from: PARSE_IDENTIFIER(r._from).key,
                to: PARSE_IDENTIFIER(r._to).key,
                type: r.type,
                description: NOT_NULL(r.description, ''),
                other_id: e._key,
                other_name: e.name,
                other_location_id: e.current_location,
            }}
        """
        relations = list(self.db.aql.execute(query, bind_vars={
            "gmc_ref": f"{ENTITIES}/{gmc_id}",
            "gid": gmc_id,
        }))

        loc_ids = {r["other_location_id"] for r in relations if r["other_location_id"]}
        loc_map = {l["id"]: l["name"] for l in self._location_dicts(list(loc_ids))}
        for r in relations:
            r["other_location_name"] = loc_map.get(r["other_location_id"]) if r["other_location_id"] else None

        return {
            "gmc": {"id": gmc.id, "name": gmc.name},
            "location": {"id": location.id, "name": location.name} if location else None,
            "relations": relations,
        }

    # ── Canvas helpers ────────────────────────────────

    def _faction_memberships_for(self, entity_ids: list[str]) -> dict:
        """Map entity_id → list of {{id, name}} factions via membership edges."""
        if not entity_ids:
            return {}
        query = f"""
            FOR r IN {RELATIONSHIPS}
            FILTER r.type == 'membership'
            LET member_key = PARSE_IDENTIFIER(r._from).key
            FILTER member_key IN @ids
            FOR f IN {ENTITIES}
            FILTER f._key == PARSE_IDENTIFIER(r._to).key AND f.type == 'faction'
            RETURN {{ member: member_key, id: f._key, name: f.name }}
        """
        result: dict = {}
        for row in self.db.aql.execute(query, bind_vars={"ids": entity_ids}):
            result.setdefault(row["member"], []).append({"id": row["id"], "name": row["name"]})
        return result

    def _relations_between(self, entity_ids: list[str]) -> list[dict]:
        """Return non-structural relationships whose endpoints are all in ``entity_ids``."""
        if len(entity_ids) < 2:
            return []
        query = f"""
            FOR r IN {RELATIONSHIPS}
            LET from_key = PARSE_IDENTIFIER(r._from).key
            LET to_key = PARSE_IDENTIFIER(r._to).key
            FILTER from_key IN @ids AND to_key IN @ids
              AND r.type NOT IN ['super', 'membership', 'agency', 'transversal']
            RETURN {{ from: from_key, to: to_key, type: r.type, description: NOT_NULL(r.description, '') }}
        """
        return list(self.db.aql.execute(query, bind_vars={"ids": entity_ids}))

    def _location_dicts(self, location_ids: list[str]) -> list[dict]:
        """Return light location dicts for a set of location keys."""
        if not location_ids:
            return []
        query = f"""
            FOR e IN {ENTITIES}
            FILTER e.type == 'location' AND e._key IN @ids
            RETURN {{ id: e._key, name: e.name, universe: e.current_universe }}
        """
        return list(self.db.aql.execute(query, bind_vars={"ids": location_ids}))

    def get_location_ancestors(self, location_id: str) -> list[str]:
        """Return all ancestor location IDs by following 'super' edges upward.

        The chain goes child → parent → grandparent → …  Returns location
        ``_key`` values sorted from nearest ancestor to root.
        """
        if self.db is not None:
            query = f"""
                FOR v, e IN 1..10 OUTBOUND @loc_ref {RELATIONSHIPS}
                FILTER e.type == 'super'
                RETURN v._key
            """
            cursor = self.db.aql.execute(query, bind_vars={
                "loc_ref": f"{ENTITIES}/{location_id}",
            })
            return list(cursor)
        else:
            # In-memory mode
            ancestors = []
            current = location_id
            for _ in range(10):
                parent = None
                for rel in self._relationships:
                    if (rel.get("_from") == f"{ENTITIES}/{current}"
                            and rel.get("type") == "super"):
                        parent = rel.get("_to", "").replace(f"{ENTITIES}/", "")
                        break
                if parent:
                    ancestors.append(parent)
                    current = parent
                else:
                    break
            return ancestors

    def list_location_descendants(self, location_id: str) -> list[str]:
        """Return all descendant location IDs by following 'super' edges downward.

        ``super`` edges point child → parent, so descendants are found by an
        inbound traversal from the root. Returns location ``_key`` values (the
        root itself is not included).
        """
        if self.db is not None:
            query = f"""
                FOR v, e IN 1..10 INBOUND @loc_ref {RELATIONSHIPS}
                FILTER e.type == 'super'
                RETURN DISTINCT v._key
            """
            cursor = self.db.aql.execute(query, bind_vars={
                "loc_ref": f"{ENTITIES}/{location_id}",
            })
            return list(cursor)
        else:
            # In-memory mode: follow child → parent edges in reverse.
            descendants: list[str] = []
            frontier = [location_id]
            for _ in range(10):
                next_frontier = []
                for rel in self._relationships:
                    if rel.get("type") != "super":
                        continue
                    child = rel.get("_from", "").replace(f"{ENTITIES}/", "")
                    parent = rel.get("_to", "").replace(f"{ENTITIES}/", "")
                    if parent in frontier and child not in descendants and child != location_id:
                        descendants.append(child)
                        next_frontier.append(child)
                if not next_frontier:
                    break
                frontier = next_frontier
            return descendants

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

    def get_images_for_owner(self, entity_id: str, projection_id: str | None = None) -> list[EntityImage]:
        """Images belonging to an owner: a specific projection, or the entity.

        ``projection_id=None`` returns entity-level images only (those with an
        empty ``projection_id``); a concrete id returns that projection's images.
        """
        images = self.get_entity_images(entity_id)
        return [
            img for img in images
            if (img.projection_id or None) == projection_id
        ]

    def _image_url(self, img: EntityImage, variant: str = "Large") -> str:
        """Public media URL for an image, honoring animated vs static variant."""
        if img.image_type == ImageType.ANIMATED:
            return f"/media/animated/{img.entity_id}/{img.universe}/{img.filename}.{img.extension}"
        return f"/media/imagen/{img.entity_id}/{img.universe}/{img.filename}_{variant}.{img.extension}"

    def resolve_role_image(
        self, entity_id: str, role: str, projection_id: str | None = None, variant: str = "Large"
    ) -> str | None:
        """Resolve a role image URL, projection-scoped with entity fallback.

        Resolution order:
        1. The projection's own image carrying ``role`` (newest first).
        2. Entity-level image carrying ``role`` whose universe matches the
           projection's current, then origin, universe.
        3. Any entity-level image carrying ``role``.

        With no ``projection_id`` only entity-level images are considered.
        """
        images = self.get_entity_images(entity_id)
        if projection_id:
            for img in images:
                if (img.projection_id or None) == projection_id and role in img.roles:
                    return self._image_url(img, variant)
            proj = self.get_projection(projection_id)
            universes: list[str] = []
            if proj is not None:
                if proj.universe:
                    universes.append(proj.universe)
                if proj.origin_universe and proj.origin_universe not in universes:
                    universes.append(proj.origin_universe)
            for u in universes:
                for img in images:
                    if not img.projection_id and role in img.roles and img.universe == u:
                        return self._image_url(img, variant)
        for img in images:
            if not img.projection_id and role in img.roles:
                return self._image_url(img, variant)
        return None

    def get_navdot_images(self, entity_ids: list[str]) -> dict[str, str]:
        """Resolve navdot role image URLs for many entities.

        Resolves through each entity's active projection (body) first, falling
        back to entity-level images. Returns ``{entity_id: media_url}``. The
        location navigate endpoint uses this for occupants, children,
        transversal destinations, and the parent.
        """
        return self._navdot_urls(entity_ids)

    # ── Helpers ───────────────────────────────────────

    def _doc_to_entity(self, doc: dict) -> Entity:
        doc = dict(doc)
        doc["id"] = doc.pop("_key", doc.get("id", ""))
        for key in ["_id", "_rev"]:
            doc.pop(key, None)
        return Entity.model_validate(doc)
