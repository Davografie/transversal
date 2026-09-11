"""Plans — split out of src/api/src/transversal/db/repository.py."""

from __future__ import annotations

from transversal.db.arango import ENTITIES
from transversal.db.arango import PLAN_ENTITIES
from transversal.db.arango import PLAN_RELATIONSHIPS
from transversal.db.arango import RELATIONSHIPS


class RepositoryPlans:
    """Mixin contributing 8 member(s) to the repository."""

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
