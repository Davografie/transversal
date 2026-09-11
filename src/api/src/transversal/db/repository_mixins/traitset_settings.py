"""Traitset settings — split out of src/api/src/transversal/db/repository.py."""

from transversal.db.arango import ENTITIES
from transversal.db.arango import PROJECTIONS
from transversal.db.arango import TRAITSETS
from transversal.db.arango import TRAITSETSETTINGS
from transversal.domain import TraitSetSetting
from typing import Optional


class RepositoryTraitsetSettings:
    """Mixin contributing 9 member(s) to the repository."""

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

    def get_traitsetsettings_for_entities(
        self, entity_ids: list[str]
    ) -> dict[str, list[TraitSetSetting]]:
        """Batch: trait-set settings grouped by owning entity (one AQL query)."""
        if not entity_ids:
            return {}
        query = f"""
            FOR tss IN {TRAITSETSETTINGS}
            FILTER tss.entity_id IN @eids
            RETURN tss
        """
        grouped: dict[str, list[TraitSetSetting]] = {eid: [] for eid in entity_ids}
        for doc in self.db.aql.execute(query, bind_vars={"eids": list(entity_ids)}):
            tss = TraitSetSetting.model_validate({**doc, "id": doc["_key"]})
            grouped.setdefault(tss.entity_id, []).append(tss)
        return grouped

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

    def get_effective_traitsetsettings_bulk(
        self, entity_ids: list[str], universes: list[str]
    ) -> dict[str, list[TraitSetSetting]]:
        """Batch variant of :meth:`get_effective_traitsetsettings` (one AQL query).

        Returns ``{entity_id: [TraitSetSetting]}`` with an entry for every
        requested id (empty list when the entity has none). Used by global
        boundary fan-outs so they don't pay a per-entity round-trip.
        """
        if not entity_ids:
            return {}
        query = f"""
            FOR tss IN {TRAITSETSETTINGS}
            FILTER tss.entity_id IN @eids
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
        grouped: dict[str, list[TraitSetSetting]] = {eid: [] for eid in entity_ids}
        for doc in self.db.aql.execute(
            query, bind_vars={"eids": list(entity_ids), "universes": universes}
        ):
            tss = TraitSetSetting.model_validate({**doc, "id": doc["_key"]})
            grouped.setdefault(tss.entity_id, []).append(tss)
        return grouped

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
