"""Traits — split out of src/api/src/transversal/db/repository.py."""

from __future__ import annotations

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
        loop = self.nomination_cycle(trait)
        if loop:
            raise ValueError(
                "Trait nomination would be circular: " + " → ".join(loop))
        doc = trait.model_dump()
        doc["_key"] = trait.id
        self._traits.insert(doc)
        self._invalidate_traits_index()
        return trait

    def get_trait(self, trait_id: str) -> Optional[Trait]:
        doc = self._traits_index().get(trait_id)
        return Trait.model_validate({**doc, "id": doc["_key"]}) if doc else None

    def list_traits_declaring_sfx(self, sfx_id: str) -> list[Trait]:
        """The registry traits that nominate this rule, in one read.

        A trait can *provision* a rule onto its instances (`default_sfx_ids`) or
        merely *offer* it (`possible_sfx_ids`). The editor needs both answers for a
        rule it is showing — "who hands this out?" is otherwise invisible from the
        rule's side — and it reads from the cached traits index rather than
        scanning the collection for a field the caller may not know exists.
        """
        out: list[Trait] = []
        for doc in self._traits_index().values():
            if sfx_id in (doc.get("default_sfx_ids") or []) \
                    or sfx_id in (doc.get("possible_sfx_ids") or []):
                out.append(Trait.model_validate({**doc, "id": doc["_key"]}))
        return sorted(out, key=lambda t: (t.name or "").lower())

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

    def get_trait_tags_by_universe(self, universe: str) -> list[str]:
        """The distinct tags across every trait in a universe, deduped and sorted.

        Aggregated in AQL on purpose: a caller that only wants the tag *pool*
        (an editor's suggestions) would otherwise transfer every trait in the
        universe — 613 of them in ``three_realms`` — to extract a handful of
        strings.
        """
        query = f"""
            FOR t IN {TRAITS}
            FILTER @u IN t.universes
            FOR tag IN NOT_NULL(t.tags, [])
            FILTER tag != null AND tag != ""
            COLLECT distinct_tag = tag
            SORT distinct_tag
            RETURN distinct_tag
        """
        return list(self.db.aql.execute(query, bind_vars={"u": universe}))

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

    def nomination_cycle(self, trait: Trait) -> list[str] | None:
        """The loop ``trait`` would close, as trait names — or ``None`` if acyclic.

        A registry trait nominates what may be put *inside* it: individual traits
        (``possible_subtrait_ids``) and whole trait sets
        (``possible_subtraitset_ids``, meaning every trait in the set). Following
        those has to stay a path. If it can arrive back at the trait, the registry
        is saying a trait may contain itself, and every walker that recurses over
        nominations would spin. Nothing walks them recursively today, which is
        exactly why this is cheaper to refuse now than to debug later
        ([[B143]]).

        The proposal replaces whatever is stored for ``trait``, so a walk is only
        ever asked about a graph that is about to exist. This is checked on every
        registry write and refusals name the loop. Live data measured at 802
        traits / 858 direct nominations / 20 set nominations, so the walk is
        trivial — no cache, no invalidation surface.

        Note this is the *nomination* graph, not the containment graph: a
        setting's own sub-trait chain is guarded separately by
        ``_would_cycle``, and a shortcut trait *referencing* another is a
        different relation again ([[Shortcut Traits Design Log]]).
        """
        index: dict[str, dict] = dict(self._traits_index())
        index[trait.id] = {**trait.model_dump(), "_key": trait.id}

        # Whole-set nominations expand to every trait in the set, so a set has to
        # be resolved before the walk rather than during it.
        by_set: dict[str, list[str]] = {}
        for key, doc in index.items():
            by_set.setdefault(doc.get("traitset_id") or "", []).append(key)

        def nominations(key: str) -> list[str]:
            doc = index[key]
            out: list[str] = list(doc.get("possible_subtrait_ids") or [])
            for set_id in doc.get("possible_subtraitset_ids") or []:
                for member in by_set.get(set_id, []):
                    if member not in out:
                        out.append(member)
            return out

        def _names(keys: list[str]) -> list[str]:
            return [index[k].get("name") or k for k in keys]

        stack: list[tuple[str, list[str]]] = [(trait.id, [trait.id])]
        seen = {trait.id}
        while stack:
            current, path = stack.pop()
            for nxt in nominations(current):
                if nxt == trait.id:
                    return _names(path + [nxt])
                if nxt in index and nxt not in seen:
                    seen.add(nxt)
                    stack.append((nxt, path + [nxt]))
        return None

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
        loop = self.nomination_cycle(trait)
        if loop:
            raise ValueError(
                "Trait nomination would be circular: " + " → ".join(loop))
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
