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
    PLAYERS,
    PROJECTIONS,
    RELATIONSHIPS,
    ROLL_TABLES,
    SFXS,
    TRAITS,
    TRAITSETS,
    TRAITSETTINGS,
    MESSAGES,
    get_db,
)
from transversal.domain import (
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
        self._life_paths = self.db.collection(LIFE_PATHS)
        self._roll_tables = self.db.collection(ROLL_TABLES)
        self._relationships = self.db.collection(RELATIONSHIPS)
        self._players = self.db.collection(PLAYERS)
        self._entity_images = self.db.collection(ENTITY_IMAGES)
        self._messages = self.db.collection(MESSAGES)
        self._historical_records = self.db.collection(HISTORICAL_RECORDS)

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
        """Remove projections, trait settings, relationships, images, and media."""
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
        import shutil, glob
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
            ts_removed = len(list(self.db.aql.execute(
                f"FOR ts IN {TRAITSETTINGS} FILTER ts.trait_id IN @tids REMOVE ts IN {TRAITSETTINGS} RETURN OLD._key",
                bind_vars={"tids": trait_keys}
            )))
        for tkey in trait_keys:
            self._cleanup_lifepath_trait_refs(tkey)
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
        if ts.from_type == "relationship":
            doc["_from"] = f"{RELATIONSHIPS}/{ts.entity_id}"
        else:
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
        if ts.from_type == "relationship":
            doc["_from"] = f"{RELATIONSHIPS}/{ts.entity_id}"
        else:
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
                edge_key = f"edge:{frm}:{to}:{rel_type}"
                rel = self.get_relationship(frm, to, rel_type)
                if rel:
                    results.extend(self.get_relationship_traitsettings(edge_key))
        return results

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
        self, from_id: str, to_id: str, rel_type: str, description: str = ""
    ) -> dict:
        edge = {
            "_from": f"{ENTITIES}/{from_id}",
            "_to": f"{ENTITIES}/{to_id}",
            "type": rel_type,
        }
        if description:
            edge["description"] = description
        return self._relationships.insert(edge)

    def get_relationship(
        self, from_id: str, to_id: str, rel_type: str
    ) -> dict | None:
        """Get a directional relationship edge between two entities."""
        query = f"""
            FOR r IN {RELATIONSHIPS}
            FILTER r._from == @from_ref AND r._to == @to_ref AND r.type == @rel_type
            LIMIT 1
            RETURN r
        """
        cursor = list(self.db.aql.execute(query, bind_vars={
            "from_ref": f"{ENTITIES}/{from_id}",
            "to_ref": f"{ENTITIES}/{to_id}",
            "rel_type": rel_type,
        }))
        return cursor[0] if cursor else None

    def delete_relationship(
        self, from_id: str, to_id: str, rel_type: str
    ) -> bool:
        """Delete a directional relationship edge between two entities."""
        query = f"""
            FOR r IN {RELATIONSHIPS}
            FILTER r._from == @from_ref AND r._to == @to_ref AND r.type == @rel_type
            REMOVE r IN {RELATIONSHIPS}
            RETURN OLD
        """
        result = self.db.aql.execute(query, bind_vars={
            "from_ref": f"{ENTITIES}/{from_id}",
            "to_ref": f"{ENTITIES}/{to_id}",
            "rel_type": rel_type,
        })
        return bool(list(result))

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
            RETURN { id: e._key, name: e.name, sheet_portrait: e.background_image || null }
        """
        return list(self.db.aql.execute(query, bind_vars=bind_vars))

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
