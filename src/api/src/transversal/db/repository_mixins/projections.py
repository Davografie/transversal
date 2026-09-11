"""Projections — split out of src/api/src/transversal/db/repository.py."""

from __future__ import annotations

from transversal.db.arango import ENTITY_IMAGES
from transversal.db.arango import PROJECTIONS
from transversal.db.arango import RELATIONSHIPS
from transversal.db.arango import TRAITSETSETTINGS
from transversal.db.arango import TRAITSETTINGS
from transversal.domain import Projection
from typing import Optional


class RepositoryProjections:
    """Mixin contributing 7 member(s) to the repository."""

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

    def get_projections_for_entities(
        self, entity_ids: list[str]
    ) -> dict[str, list[Projection]]:
        """Batch: projections grouped by owning entity (one AQL query)."""
        if not entity_ids:
            return {}
        query = f"""
            FOR p IN {PROJECTIONS}
            FILTER p.entity_id IN @eids
            RETURN p
        """
        grouped: dict[str, list[Projection]] = {eid: [] for eid in entity_ids}
        for doc in self.db.aql.execute(query, bind_vars={"eids": list(entity_ids)}):
            proj = Projection.model_validate({**doc, "id": doc["_key"]})
            grouped.setdefault(proj.entity_id, []).append(proj)
        return grouped

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
