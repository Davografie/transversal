"""Traitset settings — split out of src/api/src/transversal/db/repository.py."""

from __future__ import annotations

from transversal.db.arango import ENTITIES
from transversal.db.arango import PROJECTIONS
from transversal.db.arango import TRAITS
from transversal.db.arango import TRAITSETS
from transversal.db.arango import TRAITSETSETTINGS
from transversal.db.arango import TRAITSETTINGS
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
        """One entity's **stored** set settings — documents only, deliberately.

        This backs the ``entity → traitsetsettings`` *targeting* hop, and [[B243]]
        drew that boundary on purpose: enumerating the derived pairs through a path
        would hand an effect thousands of rows whose content is "nothing". The
        sheet's read is :meth:`get_traitsetsettings_for_entities`, which *does*
        include the held pairs ([[B244]]) — the two questions are different: a path
        asks where an effect may land, a sheet asks what this entity has.
        """
        query = f"""
            FOR tss IN {TRAITSETSETTINGS}
            FILTER tss.entity_id == @eid
            RETURN tss
        """
        return [
            TraitSetSetting.model_validate({**doc, "id": doc["_key"]})
            for doc in self.db.aql.execute(query, bind_vars={"eid": entity_id})
        ]

    def get_traitset_ids_for_entities(
        self, entity_ids: list[str], universes: Optional[list[str]] = None
    ) -> dict[str, list[str]]:
        """The trait sets each entity **holds** a trait of — read through the trait.

        The set is a fact about the registry definition ([[B209]]: an instance
        records none), so this joins each instance to its trait. Nested instances are
        excluded exactly as ``entity → traitsettings`` excludes them — a sub-trait
        rides the set its parent already names. ``universes``, when given, keeps only
        sets declared for one of them, mirroring the gate the stored rows are read
        under; a set that declares no universes is available everywhere.
        """
        if not entity_ids:
            return {}
        query = f"""
            FOR ts IN {TRAITSETTINGS}
            FILTER ts.entity_id IN @eids AND ts.from_type != 'traitsetting'
            LET tr = DOCUMENT(CONCAT(@traitdoc, ts.trait_id))
            FILTER tr != null AND tr.traitset_id != null
            LET st = DOCUMENT(CONCAT(@setdoc, tr.traitset_id))
            FILTER @universes == null OR st == null OR st.universes == null
                OR LENGTH(INTERSECTION(st.universes, @universes)) > 0
            COLLECT entity_id = ts.entity_id, traitset_id = tr.traitset_id
            RETURN {{ entity_id, traitset_id }}
        """
        out: dict[str, list[str]] = {eid: [] for eid in entity_ids}
        for doc in self.db.aql.execute(
            query,
            bind_vars={
                "eids": list(entity_ids),
                "traitdoc": f"{TRAITS}/",
                "setdoc": f"{TRAITSETS}/",
                "universes": list(universes) if universes is not None else None,
            },
        ):
            out.setdefault(doc["entity_id"], []).append(doc["traitset_id"])
        return out

    def _with_held_pairs(
        self,
        grouped: dict[str, list[TraitSetSetting]],
        universes: Optional[list[str]] = None,
    ) -> dict[str, list[TraitSetSetting]]:
        """Add a **virtual** setting for every set an entity holds and has not overridden.

        A trait-set setting is an override, so the pair is meaningful whether or not a
        document was ever written (``services/traitset_settings``): the sheet hangs a
        granted rule on that pair, and before this the node simply did not exist for
        the 260 of 261 entities that had never written one ([[B244]]). One grouped read
        for the held sets, so a fan-out pays a single extra query, not one per entity.

        A pair that has *any* stored row is left alone — including a projection-anchored
        one — because two nodes for one ``traitsetId`` would collide in the client's
        ``traitsetId → setting`` map (measured live: no such pair exists today).
        """
        from transversal.services.traitset_settings import default_for

        held = self.get_traitset_ids_for_entities(list(grouped), universes=universes)
        for entity_id, set_ids in held.items():
            have = {t.traitset_id for t in grouped.get(entity_id, [])}
            for set_id in set_ids:
                if set_id not in have:
                    grouped.setdefault(entity_id, []).append(default_for(entity_id, set_id))
        return grouped

    def get_traitsetsettings_for_entities(
        self, entity_ids: list[str]
    ) -> dict[str, list[TraitSetSetting]]:
        """Batch: trait-set settings grouped by owning entity.

        **Stored rows *and* the pairs that have none.** This is the sheet's read
        (``Entity.traitSetSettings``), and a set the entity holds has a setting
        whether or not anyone has overridden it — see :meth:`_with_held_pairs`.
        """
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
        return self._with_held_pairs(grouped)

    def get_traitsetsettings_for_traitset(self, traitset_id: str) -> list[TraitSetSetting]:
        """Every stored override for one trait set — the ``traitset → setting`` hop.

        Documents only, deliberately: the pair is *addressable* without one (see
        ``services/traitset_settings``), but enumerating the defaults for a set
        would mean one row per entity that could hold it, which is thousands of
        rows whose content is "nothing".
        """
        query = f"""
            FOR tss IN {TRAITSETSETTINGS}
            FILTER tss.traitset_id == @tsid
            RETURN tss
        """
        return [
            TraitSetSetting.model_validate({**doc, "id": doc["_key"]})
            for doc in self.db.aql.execute(query, bind_vars={"tsid": traitset_id})
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
        A set the entity holds is included whether or not it was ever overridden —
        the granted-rule membership test is a set of *ids*, and a set nobody has
        overridden still has the derived pair ([[B244]]).
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
        return self._with_held_pairs(
            {entity_id: [
                TraitSetSetting.model_validate({**doc, "id": doc["_key"]})
                for doc in self.db.aql.execute(
                    query, bind_vars={"eid": entity_id, "universes": universes}
                )
            ]},
            universes=universes,
        )[entity_id]

    def get_effective_traitsetsettings_bulk(
        self, entity_ids: list[str], universes: list[str]
    ) -> dict[str, list[TraitSetSetting]]:
        """Batch variant of :meth:`get_effective_traitsetsettings` (one AQL query).

        Returns ``{entity_id: [TraitSetSetting]}`` with an entry for every
        requested id (empty list when the entity has none). Used by global
        boundary fan-outs so they don't pay a per-entity round-trip. Held-but-
        unoverridden pairs are included, exactly as the singular read includes them.
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
        return self._with_held_pairs(grouped, universes=universes)

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
