"""Relationships — split out of src/api/src/transversal/db/repository.py."""

from __future__ import annotations

from transversal.db.arango import ENTITIES
from transversal.db.arango import PROJECTIONS
from transversal.db.arango import RELATIONSHIPS
from transversal.db.arango import TRAITSETTINGS
from transversal.domain import EntityType
from transversal.domain import PERSONAL_RELATIONSHIP_TYPE
from transversal.domain import TraitSetting
from transversal.domain import Zone


class RepositoryRelationships:
    """Mixin contributing 11 member(s) to the repository."""

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
        for rel_type in [PERSONAL_RELATIONSHIP_TYPE]:
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

    def get_relationship_traitsettings_for_entities(
        self, entity_ids: list[str]
    ) -> dict[str, list[dict]]:
        """Batch outgoing relationship traits across many entities.

        Mirrors :meth:`get_relationship_traitsettings_for_entity` but resolves
        the whole set in a constant number of AQL queries (projections, edges,
        edge trait settings) instead of one per entity + one per edge.
        """
        if not entity_ids:
            return {}
        grouped: dict[str, list[dict]] = {eid: [] for eid in entity_ids}

        # All projections for all entities → build ``_from`` refs + owner map.
        projs_by_entity = self.get_projections_for_entities(entity_ids)
        from_refs: list[str] = []
        ref_to_owner: dict[str, str] = {}
        for eid in entity_ids:
            ref = f"{ENTITIES}/{eid}"
            from_refs.append(ref)
            ref_to_owner[ref] = eid
            for p in projs_by_entity.get(eid, []):
                pref = f"{PROJECTIONS}/{p.id}"
                from_refs.append(pref)
                ref_to_owner[pref] = eid

        # All outgoing relationship edges for the whole set.
        query = f"""
            FOR r IN {RELATIONSHIPS}
            FILTER r._from IN @from_refs
            RETURN r
        """
        edges = list(self.db.aql.execute(query, bind_vars={"from_refs": from_refs}))

        # All relationship trait settings for those edges.
        edge_keys = [e["_key"] for e in edges]
        ts_by_edge: dict[str, list[TraitSetting]] = {k: [] for k in edge_keys}
        if edge_keys:
            ts_query = f"""
                FOR ts IN {TRAITSETTINGS}
                FILTER ts.from_type == 'relationship' AND ts.entity_id IN @ekeys
                RETURN ts
            """
            for doc in self.db.aql.execute(ts_query, bind_vars={"ekeys": edge_keys}):
                ts = TraitSetting.model_validate({**doc, "id": doc["_key"]})
                ts_by_edge.setdefault(ts.entity_id, []).append(ts)

        # Assemble per-owner results (contact resolution stays direct-key lookups).
        for edge in edges:
            owner = ref_to_owner.get(edge["_from"])
            if owner is None:
                continue
            contact = self._resolve_relationship_contact(edge["_to"])
            if contact is None:
                continue
            for ts in ts_by_edge.get(edge["_key"], []):
                grouped[owner].append({
                    "setting": ts,
                    "contact_id": contact["id"],
                    "contact_name": contact["name"],
                    "contact_type": contact["type"],
                    "edge_type": edge.get("type", ""),
                })
        return grouped

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

    def collapse_legacy_personal_relationship_types(self) -> int:
        """Idempotently fold retired personal edge types onto ``relation``.

        ``associate``/``gifted``/``suspects``/``hostile_to`` are retired — the
        single personal type is ``relation``. This flips any edges written before
        the collapse, preserving ``description`` and dropping exact duplicates.
        Returns the number of edges renamed (not counting pure duplicate drops).
        """
        renamed = 0
        for legacy in ("associate", "gifted", "suspects", "hostile_to"):
            rows = list(self.db.aql.execute(
                f"FOR r IN {RELATIONSHIPS} FILTER r.type == @t RETURN r",
                bind_vars={"t": legacy},
            ))
            for r in rows:
                dup = list(self.db.aql.execute(
                    f"""
                    FOR x IN {RELATIONSHIPS}
                    FILTER x._from == @f AND x._to == @t AND x.type == @rel
                    LIMIT 1
                    RETURN x._key
                    """,
                    bind_vars={"f": r["_from"], "t": r["_to"], "rel": PERSONAL_RELATIONSHIP_TYPE},
                ))
                if dup:
                    self._relationships.delete(r["_key"])
                    continue
                self._relationships.insert({
                    "_from": r["_from"],
                    "_to": r["_to"],
                    "type": PERSONAL_RELATIONSHIP_TYPE,
                    "description": r.get("description", ""),
                })
                self._relationships.delete(r["_key"])
                renamed += 1
        return renamed
