"""Traits — split out of src/api/src/transversal/db/repository.py."""

from transversal.db.arango import TRAITS
from transversal.db.arango import TRAITSETS
from transversal.db.arango import TRAITSETSETTINGS
from transversal.db.arango import TRAITSETTINGS
from transversal.domain import Trait
from transversal.domain import TraitSet
from typing import Optional


class RepositoryTraits:
    """Mixin contributing 16 member(s) to the repository."""

    def create_trait(self, trait: Trait) -> Trait:
        doc = trait.model_dump()
        doc["_key"] = trait.id
        self._traits.insert(doc)
        self._invalidate_traits_index()
        return trait

    def get_trait(self, trait_id: str) -> Optional[Trait]:
        doc = self._traits_index().get(trait_id)
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
        self._invalidate_traits_index()
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
            self._invalidate_traits_index()
            return True
        except Exception:
            return False

    def create_traitset(self, traitset: TraitSet) -> TraitSet:
        doc = traitset.model_dump()
        doc["_key"] = traitset.id
        self._traitsets.insert(doc)
        self._invalidate_traitsets_index()
        return traitset

    def get_traitset_by_id(self, traitset_id: str) -> Optional[TraitSet]:
        doc = self._traitsets_index().get(traitset_id)
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
        self._invalidate_traitsets_index()
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
        # The cascade also removed traits, so invalidate both indexes.
        self._invalidate_traitsets_index()
        self._invalidate_traits_index()
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
