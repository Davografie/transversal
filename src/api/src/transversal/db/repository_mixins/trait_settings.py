"""Trait settings — split out of src/api/src/transversal/db/repository.py."""

import hashlib

from transversal.db.arango import ENTITIES
from transversal.db.arango import PROJECTIONS
from transversal.db.arango import RELATIONSHIPS
from transversal.db.arango import TRAITS
from transversal.db.arango import TRAITSETTINGS
from transversal.domain import TraitSetting
from typing import Optional


class RepositoryTraitSettings:
    """Mixin contributing 18 member(s) to the repository."""

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

    def get_traitsettings_for_entity_and_trait(
        self, entity_id: str, trait_id: str
    ) -> list[TraitSetting]:
        """Every instance of ``trait_id`` the entity holds (entity-anchored)."""
        query = f"""
            FOR ts IN {TRAITSETTINGS}
            FILTER ts.entity_id == @eid AND ts.trait_id == @tid AND ts.from_type != 'traitsetting'
            RETURN ts
        """
        return [
            TraitSetting.model_validate({**doc, "id": doc["_key"]})
            for doc in self.db.aql.execute(query, bind_vars={"eid": entity_id, "tid": trait_id})
        ]

    def find_traitsetting_collision(
        self,
        entity_id: str,
        trait_id: str,
        statement: str = "",
        allow_duplicates: bool = False,
    ) -> Optional[TraitSetting]:
        """The existing setting a new (entity, trait, statement) would collide with.

        ``allow_duplicates=False`` → any instance of the trait collides (one per
        trait definition). ``allow_duplicates=True`` → only an instance with the
        same statement collides (multiple instances, distinguished by statement).
        """
        existing = self.get_traitsettings_for_entity_and_trait(entity_id, trait_id)
        if not existing:
            return None
        if not allow_duplicates:
            return existing[0]
        stmt = statement or ""
        for ts in existing:
            if (ts.statement or "") == stmt:
                return ts
        return None

    def resolve_traitsetting_id(
        self,
        entity_id: str,
        trait_id: str,
        statement: str = "",
        allow_duplicates: bool = False,
    ) -> str:
        """Deterministic TraitSetting key for a new instance.

        ``allow_duplicates=False`` → ``{entity}:{trait}`` (backward-compatible,
        one instance per trait). ``allow_duplicates=True`` + non-empty statement
        → ``{entity}:{trait}:{hash8(statement)}`` so same-statement duplicates
        collide (and are caught by :meth:`find_traitsetting_collision`) while
        distinct statements get distinct keys.
        """
        base = f"{entity_id}:{trait_id}"
        if allow_duplicates and statement:
            h = hashlib.sha1(statement.encode("utf-8")).hexdigest()[:8]
            return f"{base}:{h}"
        return base

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

    def get_traitsettings_for_entities(
        self, entity_ids: list[str]
    ) -> dict[str, list[TraitSetting]]:
        """Batch: trait settings grouped by owning entity (one AQL query)."""
        if not entity_ids:
            return {}
        query = f"""
            FOR ts IN {TRAITSETTINGS}
            FILTER ts.entity_id IN @eids AND ts.from_type != 'traitsetting'
            RETURN ts
        """
        grouped: dict[str, list[TraitSetting]] = {eid: [] for eid in entity_ids}
        for doc in self.db.aql.execute(query, bind_vars={"eids": list(entity_ids)}):
            ts = TraitSetting.model_validate({**doc, "id": doc["_key"]})
            grouped.setdefault(ts.entity_id, []).append(ts)
        return grouped

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

    def get_sub_traitsettings_for_parents(
        self, parent_ids: list[str]
    ) -> dict[str, list[TraitSetting]]:
        """Batch: sub-trait settings grouped by parent setting (one AQL query)."""
        if not parent_ids:
            return {}
        query = f"""
            FOR ts IN {TRAITSETTINGS}
            FILTER ts.from_type == 'traitsetting'
                AND ts.parent_traitsetting_id IN @pids
            SORT ts.traitset_id, ts.trait_id
            RETURN ts
        """
        grouped: dict[str, list[TraitSetting]] = {pid: [] for pid in parent_ids}
        for doc in self.db.aql.execute(query, bind_vars={"pids": list(parent_ids)}):
            ts = TraitSetting.model_validate({**doc, "id": doc["_key"]})
            grouped.setdefault(ts.parent_traitsetting_id, []).append(ts)
        return grouped

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
