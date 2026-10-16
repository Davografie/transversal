"""Bundles — the document-level reads a content bundle export is built on.

A content bundle ([[B301]]) is a **file**, and it carries **whole documents**
rather than domain models. That is deliberate and it is the one decision this
module exists to serve: the Pydantic models are a *view*, so a model-based export
silently drops every field the model does not know — measured live 2026-09-29:
`traits.location_restricted` survives on **642** documents after the field was
removed end-to-end, and `roll_tables.entries[].cost_effects` is on **169** rows
against a [[Data Model]] that does not document it. A bundle that loses those on
the way out cannot round-trip, and nothing would say so.

So the reads here return **raw Arango documents**, with only the volatile
bookkeeping removed by the caller (`_id`, `_rev`); `_key` is kept because every
edge and every derived id is keyed by it.
"""

from __future__ import annotations

from transversal.db.arango import RELATIONSHIPS, TRAITS, TRAITSETSETTINGS, TRAITSETTINGS


class RepositoryBundles:
    """Mixin contributing 5 member(s) to the repository."""

    def raw_documents(self, collection: str, keys: list[str]) -> dict[str, dict]:
        """Fetch documents by key, verbatim, as ``{_key: doc}``.

        ``collection`` is interpolated as a **collection name**, never a value; it
        comes from the bundle's own element declaration rather than a request body.
        """
        if not keys:
            return {}
        query = """
            FOR d IN @@collection
            FILTER d._key IN @keys
            RETURN d
        """
        docs = self.db.aql.execute(
            query, bind_vars={"@collection": collection, "keys": list(keys)}
        )
        return {d["_key"]: d for d in docs}

    def locate_documents(self, collections: list[str], keys: list[str]) -> dict[str, str]:
        """Which collection holds each key, as ``{key: collection}``.

        One round trip for every candidate at once. This is what makes a bundle's
        closure **exact rather than pattern-matched**: instead of guessing what a
        value is from the field it sits in, the database is asked, and an id that
        nothing holds is absent from the answer. `content_bundle` uses it for both
        jobs at once — *what is this?* and *does it exist?* — which is why the
        export can report a dangling reference by name.

        A key that exists in more than one collection is reported against the first
        collection in ``collections`` order, and the caller passes them in the
        bundle's declared order so the answer is stable.
        """
        keys = [k for k in dict.fromkeys(keys) if k]
        if not keys or not collections:
            return {}
        branches = ",\n                ".join(
            f"(FOR d IN {c} FILTER d._key IN @keys RETURN {{k: d._key, c: '{c}'}})"
            for c in collections
        )
        query = f"""
            FOR row IN UNION(
                {branches}
            )
            RETURN row
        """
        out: dict[str, str] = {}
        for row in self.db.aql.execute(query, bind_vars={"keys": keys}):
            out.setdefault(row["k"], row["c"])
        return out

    def raw_edges_by_anchor(self, collection: str, handles: list[str]) -> list[dict]:
        """Edge documents whose ``_from`` is one of ``handles``, verbatim.

        Exact by construction: ``traitsettings.entity_id`` is denormalized and
        **indexed**, but filtering on it would over-pull — a projection's settings
        share the owning entity's ``entity_id``, so asking for the entity returns
        its other bodies' settings too. ``_from`` is the anchor, and it is what
        "these settings belong to this thing" actually means.
        """
        if not handles:
            return []
        query = """
            FOR d IN @@collection
            FILTER d._from IN @handles
            RETURN d
        """
        return list(
            self.db.aql.execute(
                query, bind_vars={"@collection": collection, "handles": list(handles)}
            )
        )

    def raw_relationships_touching(self, handles: list[str]) -> list[dict]:
        """Relationship edges with **at least one** endpoint in ``handles``.

        ``handles`` are Arango handles (``entities/<id>``, ``projections/<id>``) —
        an edge's endpoints are database-local handles, never bare ids. Both
        directions are returned, and the caller decides what an edge with its far
        endpoint outside the bundle means: it is reported, never carried, because
        an edge with one end missing is not a fact.
        """
        if not handles:
            return []
        query = """
            FOR r IN @@collection
            FILTER r._from IN @handles OR r._to IN @handles
            RETURN r
        """
        return list(
            self.db.aql.execute(
                query, bind_vars={"@collection": RELATIONSHIPS, "handles": list(handles)}
            )
        )

    def raw_traitsettings_by_anchor(self, handles: list[str]) -> list[dict]:
        """Trait settings anchored on these handles (entity, projection, edge,
        or another setting — a sub-trait is anchored to its parent)."""
        return self.raw_edges_by_anchor(TRAITSETTINGS, handles)

    def raw_traitsetsettings_by_anchor(self, handles: list[str]) -> list[dict]:
        """Trait-set settings anchored on these handles (entity or projection)."""
        return self.raw_edges_by_anchor(TRAITSETSETTINGS, handles)

    def raw_traits_for_traitsets(self, traitset_ids: list[str]) -> list[dict]:
        """The traits a set defines — a **reverse** read.

        ``traits.traitset_id`` points *up* at the set, so a closure that followed
        only the references a document carries would ship a trait set as an empty
        grouping. A set's traits are what the set *is*, so the export reaches back
        down to them; `traits.traitset_id` carries a hash index, so it is one
        indexed query.
        """
        if not traitset_ids:
            return []
        query = """
            FOR d IN @@collection
            FILTER d.traitset_id IN @ids
            RETURN d
        """
        return list(
            self.db.aql.execute(
                query, bind_vars={"@collection": TRAITS, "ids": list(traitset_ids)}
            )
        )
