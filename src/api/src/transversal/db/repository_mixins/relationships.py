"""Relationships — split out of src/api/src/transversal/db/repository.py."""

from __future__ import annotations

from transversal.db.arango import ENTITIES
from transversal.db.arango import PROJECTIONS
from transversal.db.arango import RELATIONSHIPS
from transversal.db.arango import TRAITS
from transversal.db.arango import TRAITSETTINGS
from transversal.domain import Entity
from transversal.domain import EntityType
from transversal.domain import MEMBERSHIP_HOLDER_TYPES
from transversal.domain import PERSONAL_RELATIONSHIP_TYPE
from transversal.domain import TraitSetting
from transversal.domain import Zone

# Default nav-dot positions, seeded onto a location when a link is created so the
# viewer never has to guess. They mirror the location viewer's own defaults
# (``NAV_DOT_DEFAULTS`` in LocationViewer.vue) — the parent dot sits top-right,
# portal dots run down the right edge. Keep the two in step: if they drift apart,
# a location with no stored position is *drawn* at one spot and *landed on* at
# another, which reads as the destination image jumping on arrival.
DEFAULT_PARENT_NAV_POSITION = {"x": 90, "y": 15}
DEFAULT_PORTAL_NAV_POSITION = {"x": 90, "y": 50}


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

    def list_relationships_for_entity(self, entity_id: str) -> list[dict]:
        """The relationship edges ``entity_id`` holds *about* others.

        Outgoing only — the entity or one of its projections is the ``_from``
        side — the same orientation :meth:`get_relationship_traitsettings_for_entity`
        uses, so what comes back is what this entity holds about others rather
        than what others hold about it.

        Each edge carries its ``_key`` (the anchor a relationship-anchored
        ``TraitSetting`` points at) and its resolved contact, so a targeting path
        can walk ``entity → relationships → traitsettings`` with one read and
        know who the other party is without a second.
        """
        proj_ids = [p.id for p in self.get_projections_for_entity(entity_id)]
        from_refs = [f"{ENTITIES}/{entity_id}"] + [f"{PROJECTIONS}/{pid}" for pid in proj_ids]

        query = f"""
            FOR r IN {RELATIONSHIPS}
            FILTER r._from IN @from_refs
            RETURN r
        """
        out: list[dict] = []
        for edge in self.db.aql.execute(query, bind_vars={"from_refs": from_refs}):
            contact = self._resolve_relationship_contact(edge["_to"]) or {}
            out.append({
                "id": edge["_key"],
                "type": edge.get("type", ""),
                "description": edge.get("description", ""),
                "owner_id": edge["_from"].split("/", 1)[-1],
                "contact_id": contact.get("id", ""),
                "contact_name": contact.get("name", ""),
            })
        return out

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
        self.ensure_location_link_defaults(from_id, to_id, rel_type)

        return created

    def ensure_location_link_defaults(self, from_id: str, to_id: str, rel_type: str) -> None:
        """Materialise the nav-dot defaults a newly created location link needs.

        A link is stored from both ends and the viewer needs a stored dot on each
        end — one it **draws** and also **lands** on. With none stored it falls
        back to a default, and the preview and the travel used to resolve that
        default differently, so the destination image jumped at the handover:

        * ``super`` (child → parent): the child gets the 'parent' dot leading up.
        * ``transversal``: both ends get a 'portal' dot pointing at the other.

        This lives in one place because the REST edge endpoint inserts the edge
        document directly and never goes through :meth:`create_relationship` —
        seeding only one of them would leave whichever path the UI happens to use
        unseeded. Idempotent: an authored position is never overwritten.
        """
        if rel_type == "super":
            self._ensure_parent_nav_position(from_id)
        elif rel_type == "transversal":
            self._ensure_portal_nav_position(from_id)
            self._ensure_portal_nav_position(to_id)

    def _ensure_child_zone(self, child_id: str, parent_id: str) -> None:
        """Add a default zone to ``parent_id`` for the child sub-location, if absent."""
        parent = self.get_entity(parent_id)
        child = self.get_entity(child_id)
        if parent is None or child is None:
            return
        if parent.type != EntityType.LOCATION or child.type != EntityType.LOCATION:
            return
        for zone in parent.zones:
            if zone.location_id == child_id:
                return  # already registered
        parent.zones.append(Zone(x=50.0, y=50.0, location_id=child_id))
        self.update_entity(parent)

    def _ensure_parent_nav_position(self, child_id: str) -> None:
        """Give ``child_id`` a default 'parent' nav-dot position, if absent.

        The mirror of :meth:`_ensure_child_zone`, seen from the child's own end:
        the parent holds a zone for the child, and the child holds the dot that
        leads back up. Without it the viewer has no stored landing point for
        arriving at the child from its parent, so it falls back to a default —
        and when the preview and the travel disagreed about that default, the
        destination image jumped on arrival.
        """
        child = self.get_entity(child_id)
        if child is None or child.type != EntityType.LOCATION:
            return
        if child.nav_positions.get("parent"):
            return  # already registered
        child.nav_positions["parent"] = dict(DEFAULT_PARENT_NAV_POSITION)
        self.update_entity(child)

    def _ensure_portal_nav_position(self, location_id: str) -> None:
        """Give ``location_id`` a default 'portal' nav-dot position, if absent."""
        loc = self.get_entity(location_id)
        if loc is None or loc.type != EntityType.LOCATION:
            return
        if loc.nav_positions.get("portal"):
            return  # already registered
        loc.nav_positions["portal"] = dict(DEFAULT_PORTAL_NAV_POSITION)
        self.update_entity(loc)

    def list_member_factions_with_sfx(self, entity_id: str) -> list["Entity"]:
        """The factions this entity is on the roster of that **own SFX**.

        The membership scope ([[B109]]), mirroring :meth:`list_ancestor_locations_with_sfx`
        for places: a rule owned by a faction reaches its members.

        Goes through :meth:`get_entity_factions` rather than re-deriving the tie —
        that read already knows the two shapes a roster slot takes (``membership``,
        or a ``relation`` tie carrying ``role``/``rank``) and that direction
        matters, and a second query here is a second chance to disagree with the
        roster. Only factions that actually carry rules come back, so an entity in
        no faction costs a handful of id reads and nothing else.
        """
        out: list[Entity] = []
        for faction_id in self.get_entity_factions(entity_id):
            faction = self.get_entity(faction_id)
            if faction is not None and (faction.sfx_ids or []):
                out.append(faction)
        return out

    def list_member_factions_with_sfx_bulk(self, entity_ids: list[str]) -> dict[str, list[str]]:
        """``entity_id → sfx ids`` its factions grant, in one read.

        The bulk half, for the availability prefetch: the global fan-out visits
        every entity, so asking each about its own roster would put a query back on
        that path. The roster test is repeated in AQL rather than approximated —
        ``membership`` always counts, a ``relation`` only when it carries a
        ``role`` or ``rank`` trait, and only member → faction. Using the *broader*
        :meth:`get_factions_for_entities` here would hand a faction's rules to
        everyone it merely holds a posture toward, which is the one thing this
        scope must never do.
        """
        if not entity_ids:
            return {}
        refs = [f"{ENTITIES}/{eid}" for eid in entity_ids]
        # Two passes rather than one `AGGREGATE`: an aggregate over a *list* field
        # yields a list of lists (each row's array is one element), which is not
        # what the caller wants and only the live read showed it. The fan-out below
        # turns each faction's plist into one row per rule, and the collect dedupes.
        query = f"""
            LET hits = (
                FOR r IN {RELATIONSHIPS}
                  FILTER r._from IN @refs
                  FILTER r.type IN ['membership', 'relation']
                  LET f = DOCUMENT({ENTITIES}, PARSE_IDENTIFIER(r._to).key)
                  FILTER f != null AND f.type == 'faction'
                  FILTER LENGTH(f.sfx_ids || []) > 0
                  LET roster = r.type == 'membership' OR LENGTH(
                      FOR ts IN {TRAITSETTINGS}
                        FILTER ts._from == CONCAT('relationships/', r._key)
                        LET t = DOCUMENT({TRAITS}, ts.trait_id)
                        FILTER t != null AND LOWER(t.name) IN ['role', 'rank']
                        LIMIT 1 RETURN 1) > 0
                  FILTER roster
                  RETURN {{ member: PARSE_IDENTIFIER(r._from).key, sfx_ids: f.sfx_ids }}
            )
            FOR h IN hits
              FOR sid IN h.sfx_ids
                FILTER sid != null
                COLLECT member = h.member, sfx = sid
                RETURN {{ member, sfx }}
        """
        out: dict[str, list[str]] = {}
        for row in self.db.aql.execute(query, bind_vars={"refs": refs}):
            out.setdefault(row["member"], []).append(row["sfx"])
        return out

    def list_ancestor_locations_with_sfx(self, location_id: str, max_depth: int = 8) -> list["Entity"]:
        """The location and its ancestors that own SFX — the *location scope*.

        A rule owned by a place reaches the entities under it, so availability
        asks: which of the places above this one (itself included) carry rules?
        Only those are returned — the traversal filters, so a world with no
        place-owned rules costs one empty read rather than a walk.

        Traversal follows `super` edges upward only (child → parent); `PRUNE`
        stops descending through anything else, so a `transversal` portal does
        not drag other locations into scope. The `e != null` guard matters: AQL
        evaluates `PRUNE` at the start vertex too, where the edge is null —
        without it the first evaluation prunes the whole walk and the scope comes
        back empty. `max_depth` guards a cycle.
        """
        query = f"""
            FOR v, e IN 1..@max_depth OUTBOUND @loc_ref {RELATIONSHIPS}
              PRUNE e != null AND e.type != 'super'
              FILTER e.type == 'super'
              FILTER LENGTH(v.sfx_ids || []) > 0
              RETURN DISTINCT v
        """
        cursor = self.db.aql.execute(
            query, bind_vars={"loc_ref": f"{ENTITIES}/{location_id}", "max_depth": max_depth}
        )
        out = [Entity.model_validate({**doc, "id": doc["_key"]}) for doc in cursor]
        # The starting location itself is level 0 — the traversal starts at 1.
        here = self.get_entity(location_id)
        return ([here] if here is not None and (here.sfx_ids or []) else []) + out

    def validate_relationship(self, from_id: str, to_id: str, rel_type: str) -> str | None:
        """Why this edge may not exist — or ``None`` when it may.

        ``membership`` is constrained: a roster entry is member → faction, so a
        self-edge, a ``_to`` that is not a faction, or a ``_from`` that cannot
        hold membership is refused rather than written.

        ``super`` is constrained too, because it is the location tree's parent
        edge (child → parent) and a loop in it is unreachable from every root:
        the branch simply vanishes from the tree — the limbo Yinling Creek fell
        into ([[B122]]). Re-parenting a location under itself, or under anything
        in its own subtree, is refused. Everything else about a location edge is
        deliberately unchecked; the REST endpoint inserts the edge document
        directly, so this is the only place the shapes are policed.

        **The child must be a location; the parent need not be.** That asymmetry is
        the point: one `super` edge says *a sub-place of* when both ends are places
        and *carried by* when the parent is not one — a cultivator's inner world.
        A non-location **child** is refused, because it is the same corruption from
        the other side (a character rendered as a leaf inside the location tree),
        and no live edge has ever been one.

        Returns a human-readable refusal; the caller raises it.
        """
        if rel_type == "super":
            child = self.get_entity(from_id)
            parent = self.get_entity(to_id)
            if child is not None and child.type != EntityType.LOCATION:
                return (
                    f"'{child.name}' is a {child.type.value}, not a location — only "
                    "a location can be a child in the location tree (a location may "
                    "still be *carried* by a non-location)"
                )
            if from_id == to_id:
                return "a location cannot be its own parent"
            if from_id in self.get_location_ancestors(to_id):
                return (
                    f"'{parent.name if parent else to_id}' is inside "
                    f"'{child.name if child else from_id}'s own subtree — a "
                    "location cannot be re-parented under itself"
                )
            return None
        if rel_type != "membership":
            return None
        if from_id == to_id:
            return "a membership edge cannot point an entity at itself"
        member = self.get_entity(from_id)
        faction = self.get_entity(to_id)
        if member is None:
            return f"entity '{from_id}' not found"
        if faction is None:
            return f"entity '{to_id}' not found"
        if faction.type != EntityType.FACTION:
            return (
                f"'{faction.name}' is a {faction.type.value}, not a faction — "
                "membership points a member at a faction"
            )
        if member.type not in MEMBERSHIP_HOLDER_TYPES:
            return (
                f"'{member.name}' is a {member.type.value}; membership is held by "
                + ", ".join(sorted(t.value for t in MEMBERSHIP_HOLDER_TYPES))
            )
        return None

    def upsert_relationship(
        self, from_id: str, to_id: str, rel_type: str, description: str = "",
        from_projection: bool = False, to_projection: bool = False,
    ) -> dict:
        """Create the edge, or update the existing one **in place**.

        Relationship trait settings anchor to the edge ``_key``, so replacing the
        edge document orphans them — which is how re-claiming a membership used to
        silently wipe its rank and role. An existing edge therefore keeps its key
        and has only ``description`` rewritten.
        """
        existing = self.get_relationship(
            from_id, to_id, rel_type,
            from_projection=from_projection, to_projection=to_projection,
        )
        if existing is not None:
            if (existing.get("description") or "") != description:
                self._relationships.update({"_key": existing["_key"], "description": description})
                existing["description"] = description
            return existing
        return self.create_relationship(
            from_id, to_id, rel_type, description=description,
            from_projection=from_projection, to_projection=to_projection,
        )

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

    def list_relationship_types(self) -> list[str]:
        """Every relationship *type* in use — the vocabulary, not a schema enum.

        A type is **content**: `membership` and `agency` are structural wiring the
        code declares, and everything else is whatever a GM has authored (`relation`,
        a custom tie). So the answer is the live edges **plus** the declared ones —
        a type nothing currently uses must still be offered, or authoring a rule for
        it becomes impossible exactly when the graph is empty. Declared first, so
        the system's own wiring reads at the top of a picker.
        """
        from transversal.domain import PERSONAL_RELATIONSHIP_TYPE, STRUCTURAL_RELATIONSHIP_TYPES

        declared = [*sorted(STRUCTURAL_RELATIONSHIP_TYPES), PERSONAL_RELATIONSHIP_TYPE]
        live = sorted({
            t for t in self.db.aql.execute(
                f"FOR r IN {RELATIONSHIPS} RETURN DISTINCT r.type"
            ) if t
        })
        # Declared order first, then anything content added that the code does not know.
        return declared + [t for t in live if t not in set(declared)]

    def list_entities_with_relationship_type(self, rel_type: str) -> list[str]:
        """Ids of the entities that **hold** an outgoing edge of this type.

        One read for the "every support character" question: a caller that walked
        every entity and asked each about its own edges paid N queries for one
        answer. Outgoing only, matching :meth:`list_relationships_for_entity` — a
        `support` edge is held by the support character and points at its main, so
        the holder is whose ids come back.
        """
        query = f"""
            FOR r IN {RELATIONSHIPS}
            FILTER r.type == @rel_type AND STARTS_WITH(r._from, @prefix)
            RETURN DISTINCT SPLIT(r._from, '/')[1]
        """
        return [k for k in self.db.aql.execute(
            query, bind_vars={"rel_type": rel_type, "prefix": f"{ENTITIES}/"}) if k]

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
