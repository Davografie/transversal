"""Lifepath — split out of src/api/src/transversal/db/repository.py."""

from transversal.db.arango import LIFE_PATHS
from transversal.db.arango import ROLL_TABLES
from transversal.domain import LifePath
from transversal.domain import RollTable
from typing import Optional


class RepositoryLifepath:
    """Mixin contributing 14 member(s) to the repository."""

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

    def _cleanup_lifepath_trait_refs(self, trait_id: str) -> None:
        """Remove `trait_id` from every life path that references it.

        Deletes curriculum items / qualification blocks that become empty
        as a result.  Saves each modified life path.
        """
        query = f"""
            FOR lp IN {LIFE_PATHS}
            FILTER CONTAINS(TO_STRING(lp), @tid)
            RETURN lp
        """
        docs = list(self.db.aql.execute(query, bind_vars={"tid": trait_id}))

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
