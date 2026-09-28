"""Canvas — split out of src/api/src/transversal/db/repository.py."""

from __future__ import annotations

import heapq

from transversal.db.arango import ENTITIES
from transversal.db.arango import PROJECTIONS
from transversal.db.arango import RELATIONSHIPS
from transversal.db.arango import TRAITS
from transversal.db.arango import TRAITSETTINGS
from transversal.domain import Entity
from transversal.domain import dice_list_to_rating
from transversal.db.repository_mixins.common import (
    _STRUCTURAL_TYPES_AQL,
)

# The two traits that make a tie a *roster* entry: `role` names the place in the
# org, `rank` rates it. Matched by **name**, because the registry carries more
# than one trait called `role`.
ROLE_TRAIT_NAME = "role"
RANK_TRAIT_NAME = "rank"

# The two kinds of faction *presence* the distance read reports, and why it
# reports which. Authored ground is the stronger statement, so it wins a tie at
# equal distance. A `control`-traited tie is no longer the *gate* — it is just
# one authored tie among others (`CONTROL_TRAIT_NAME` used to be, and the author
# widened it 2026-09-26: "just a faction/location relationship should already
# carry the faction presence to the GM's awareness").
PRESENCE_GROUND = "holds_ground"   # an authored faction → location tie
PRESENCE_PEOPLE = "has_people"     # a member of the faction standing there

# What a portal costs when it crosses a universe boundary, in the same units as
# one `super`/same-universe step. Inside a universe a portal is just a door, so it
# costs 1; across universes the trip is meant to read as further away, which keeps
# same-universe factions above other-universe ones in a distance-sorted list.
# **This is the one number the author left open** — it is a dial, not a finding.
CROSS_UNIVERSE_WEIGHT = 10


class RepositoryCanvas:
    """Mixin contributing 22 member(s) to the repository."""

    def location_tree(self) -> list[dict]:
        """Return the full location hierarchy as a nested tree.

        Universes are the top-level nodes.  Locations are nested under their
        universe (keyed on ``current_universe``), with their own ``super``
        edges forming sub-hierarchies within each universe.
        """
        # ── Get all UNIVERSE entities ─────────────────
        universe_query = f"""
            FOR e IN {ENTITIES}
            FILTER e.type == 'universe'
            RETURN {{ id: e._key, name: e.name, current_universe: e.current_universe }}
        """
        universes = {
            doc["current_universe"]: doc
            for doc in self.db.aql.execute(universe_query)
        }

        # ── Get all LOCATION entities ─────────────────
        location_query = f"""
            FOR e IN {ENTITIES}
            FILTER e.type == 'location'
            RETURN {{ id: e._key, name: e.name, current_universe: e.current_universe }}
        """
        locations = {doc["id"]: doc for doc in self.db.aql.execute(location_query)}

        # ── Get all super relationships ───────────────
        rel_query = f"""
            FOR r IN {RELATIONSHIPS}
            FILTER r.type == 'super'
            RETURN {{ child: PARSE_IDENTIFIER(r._from).key, parent: PARSE_IDENTIFIER(r._to).key }}
        """
        parent_of: dict[str, str] = {}
        children_of: dict[str, list[str]] = {}
        for rel in self.db.aql.execute(rel_query):
            parent_of[rel["child"]] = rel["parent"]
            children_of.setdefault(rel["parent"], []).append(rel["child"])

        # Fill gaps for edge-referenced entities not in the locations dict
        for child_id in parent_of:
            if child_id not in locations:
                locations[child_id] = {"id": child_id, "name": child_id, "current_universe": ""}
        for parent_id in children_of:
            if parent_id not in locations:
                locations[parent_id] = {"id": parent_id, "name": parent_id, "current_universe": ""}

        def by_name(ids: list[str]) -> list[str]:
            """Those ids in alphabetical order by display name.

            Casefolded, so `the Dreamlands` files with the other T's instead of
            after every capitalised name, and ties break on id so the order is
            total — it must not depend on the order Arango happened to return,
            which is what sorting on the id alone was really doing.
            """
            return sorted(
                ids,
                key=lambda lid: ((locations.get(lid, {}).get("name") or lid).casefold(), lid),
            )

        def build_node(loc_id: str) -> dict:
            loc = locations.get(loc_id, {"id": loc_id, "name": loc_id, "current_universe": ""})
            children = children_of.get(loc_id, [])
            return {
                "id": loc["id"],
                "name": loc["name"],
                "node_type": "location",
                "universe": loc.get("current_universe", ""),
                "children": [build_node(c) for c in by_name(children)],
            }

        # Root locations: locations with no parent super edge
        roots = [lid for lid in locations if lid not in parent_of]

        # Group root locations by their current_universe
        uni_roots: dict[str, list[str]] = {}
        orphans: list[str] = []  # locations with no matching universe
        for lid in roots:
            ukey = locations[lid].get("current_universe", "")
            if ukey in universes:
                uni_roots.setdefault(ukey, []).append(lid)
            else:
                orphans.append(lid)

        # Build universe nodes
        result: list[dict] = []
        for ukey, uni in sorted(
            universes.items(),
            key=lambda kv: ((kv[1]["name"] or kv[0]).casefold(), kv[0]),
        ):
            loc_roots = uni_roots.get(ukey, [])
            result.append({
                "id": uni["id"],
                "name": uni["name"],
                "node_type": "universe",
                "universe": ukey,
                "children": [build_node(r) for r in by_name(loc_roots)],
            })

        # Orphan locations (no matching universe entity) still appear as
        # top-level nodes so nothing is silently dropped.
        for lid in by_name(orphans):
            result.append(build_node(lid))

        return result

    def location_graph(self) -> dict:
        """Full location hierarchy plus all transversal edges, for the overview canvas."""
        tree = self.location_tree()
        rel_query = f"""
            FOR r IN {RELATIONSHIPS}
            FILTER r.type == 'transversal'
            RETURN {{
                from: PARSE_IDENTIFIER(r._from).key,
                to: PARSE_IDENTIFIER(r._to).key,
                transversal_type: r.transversal_type
            }}
        """
        transversal = list(self.db.aql.execute(rel_query))
        return {"tree": tree, "transversal": transversal}

    def _universe_docs(self) -> list[dict]:
        query = f"""
            FOR e IN {ENTITIES}
            FILTER e.type == 'universe'
            RETURN {{ id: e._key, name: e.name, universe: e.current_universe }}
        """
        return list(self.db.aql.execute(query))

    def _all_location_docs(self) -> list[dict]:
        query = f"""
            FOR e IN {ENTITIES}
            FILTER e.type == 'location'
            RETURN {{ id: e._key, name: e.name, universe: e.current_universe }}
        """
        return list(self.db.aql.execute(query))

    def _all_super_edges(self) -> list[dict]:
        query = f"""
            FOR r IN {RELATIONSHIPS}
            FILTER r.type == 'super'
            RETURN {{ child: PARSE_IDENTIFIER(r._from).key, parent: PARSE_IDENTIFIER(r._to).key }}
        """
        return list(self.db.aql.execute(query))

    def _all_transversal_edges(self) -> list[dict]:
        query = f"""
            FOR r IN {RELATIONSHIPS}
            FILTER r.type == 'transversal'
            RETURN {{ from: PARSE_IDENTIFIER(r._from).key, to: PARSE_IDENTIFIER(r._to).key, transversal_type: r.transversal_type }}
        """
        return list(self.db.aql.execute(query))

    def _faction_member_ids(self, faction_id: str) -> list[str]:
        """Member ids by the roster read — one definition of "member", not two."""
        return [m["id"] for m in self.get_faction_roster(faction_id)]

    def list_faction_members(self, faction_id: str) -> list[Entity]:
        """Return member entities (character/gmc) of a faction via its roster."""
        member_ids = self._faction_member_ids(faction_id)
        if not member_ids:
            return []
        query = f"""
            FOR e IN {ENTITIES}
            FILTER e._key IN @mids AND e.type IN ['character', 'gmc']
            RETURN e
        """
        return [
            self._doc_to_entity(doc)
            for doc in self.db.aql.execute(query, bind_vars={"mids": member_ids})
        ]

    def _faction_member_locations(self, faction_id: str) -> set[str]:
        """Location keys where a faction's members are occupants (direct or projected)."""
        member_ids = self._faction_member_ids(faction_id)
        if not member_ids:
            return set()
        query = f"""
            LET direct = (
                FOR e IN {ENTITIES}
                FILTER e._key IN @mids AND e.type IN ['character', 'gmc', 'asset']
                RETURN e.current_location
            )
            LET projected = (
                FOR p IN {PROJECTIONS}
                FILTER p.entity_id IN @mids
                RETURN p.current_location
            )
            FOR loc IN UNION(direct, projected)
            FILTER loc != null
            RETURN DISTINCT loc
        """
        return set(self.db.aql.execute(query, bind_vars={"mids": member_ids}))

    def _role_urls(
        self,
        entity_ids: list[str],
        role: str,
        bodies: dict[str, str] | None = None,
    ) -> dict[str, str]:
        """Resolve one image URL per entity for a role tag.

        Each entity is resolved through a body first, falling back to
        entity-level images. ``role`` is a canonical role tag
        (background/sheet/navdot); which **render** and tier it serves comes from
        the resolved record (see ``ROLE_RENDER``) — a picture with a matte serves it
        here exactly as it does everywhere else.

        ``bodies`` overrides **which** body, per entity: ``{entity_id: body_id}``.
        Default is the entity's *active* body (``current_projection``) — right for
        a sheet or a roster, where "this entity's face" is what is wanted. A caller
        drawing a **place** must pass the body standing *there* instead: an entity
        that consciousness-travelled away is present on the map as the body it left
        behind, and resolving through the active body dresses that body in the face
        of the one the consciousness went to ([[B137]] S1).
        """
        if not entity_ids:
            return {}
        # Map each entity to its active projection id.
        proj_query = f"""
            FOR e IN {ENTITIES}
            FILTER e._key IN @ids
            RETURN {{ id: e._key, current_projection: e.current_projection }}
        """
        current_proj: dict[str, str | None] = {
            row["id"]: row.get("current_projection")
            for row in self.db.aql.execute(proj_query, bind_vars={"ids": entity_ids})
        }
        for eid, body_id in (bodies or {}).items():
            if body_id:
                current_proj[eid] = body_id
        return {
            eid: url
            for eid in entity_ids
            if (url := self.resolve_role_image(eid, role, current_proj.get(eid))) is not None
        }

    def _navdot_urls(self, entity_ids: list[str], bodies: dict[str, str] | None = None) -> dict[str, str]:
        """Resolve one navdot image URL per entity, from the body given (or active)."""
        return self._role_urls(entity_ids, "navdot", bodies=bodies)

    def _occupants_for_locations(self, location_ids: list[str], faction_id: str | None = None) -> dict:
        """Map location key → occupant dicts, optionally filtered to a faction."""
        if not location_ids:
            return {}

        binds: dict = {"lids": location_ids}
        member_filter = ""
        if faction_id:
            member_ids = self._faction_member_ids(faction_id)
            if not member_ids:
                return {}
            binds["mids"] = member_ids
            member_filter = " AND e._key IN @mids"

        query = f"""
            LET direct = (
                FOR e IN {ENTITIES}
                FILTER e.type IN ['character', 'gmc', 'asset']
                  AND e.current_location IN @lids
                  {member_filter}
                LET here = FIRST(
                    FOR p IN {PROJECTIONS}
                    FILTER p.entity_id == e._key AND p.current_location == e.current_location
                    RETURN p._key
                )
                RETURN {{ id: e._key, name: e.name, type: e.type, location_id: e.current_location,
                          body_id: here }}
            )
            LET projected = (
                FOR p IN {PROJECTIONS}
                FILTER p.current_location IN @lids
                FOR e IN {ENTITIES}
                FILTER e._key == p.entity_id AND e.type IN ['character', 'gmc', 'asset']
                  {member_filter}
                RETURN {{ id: e._key, name: e.name, type: e.type, location_id: p.current_location,
                          body_id: p._key }}
            )
            FOR o IN UNION(direct, projected)
            RETURN o
        """
        rows = list(self.db.aql.execute(query, bind_vars=binds))

        # One row per (location, entity). The two branches can name the same pair —
        # an occupant both standing there and with a body there — so keep the body
        # either branch found rather than whichever row happened to arrive first.
        by_key: dict = {}
        for row in rows:
            key = (row["location_id"], row["id"])
            existing = by_key.get(key)
            if existing is None:
                by_key[key] = row
            elif not existing.get("body_id") and row.get("body_id"):
                existing["body_id"] = row["body_id"]

        result: dict = {}
        for (loc_id, _eid), row in by_key.items():
            result.setdefault(loc_id, []).append(row)

        occupant_ids = [row["id"] for loc_rows in result.values() for row in loc_rows]
        bodies = {
            row["id"]: row["body_id"]
            for loc_rows in result.values() for row in loc_rows
            if row.get("body_id")
        }
        navdots = self._navdot_urls(occupant_ids, bodies=bodies)
        memberships = self._faction_memberships_for(occupant_ids)
        for loc_rows in result.values():
            for row in loc_rows:
                row["image"] = navdots.get(row["id"])
                row["factions"] = memberships.get(row["id"], [])
        return result

    def location_canvas(self, root: str = "all", depth: int = -1, focus: str | None = None, faction: str | None = None) -> dict:
        """Return a scoped location graph for the unified relational canvas."""
        universes = self._universe_docs()
        locations = self._all_location_docs()
        super_edges = self._all_super_edges()
        transversal_edges = self._all_transversal_edges()

        location_by_id = {l["id"]: l for l in locations}
        parent_of = {e["child"]: e["parent"] for e in super_edges}
        children_of: dict[str, list[str]] = {}
        for e in super_edges:
            children_of.setdefault(e["parent"], []).append(e["child"])

        included: set[str] = set()
        universe_docs: list[dict] = []

        def walk_children(lid: str, remaining: int) -> None:
            if lid in included or lid not in location_by_id:
                return
            included.add(lid)
            if remaining == 0:
                return
            next_remaining = remaining - 1 if remaining > 0 else -1
            for child in children_of.get(lid, []):
                walk_children(child, next_remaining)

        if root.startswith("location:"):
            loc_id = root.split(":", 1)[1]
            if loc_id in location_by_id:
                included.add(loc_id)
                if loc_id in parent_of and parent_of[loc_id] in location_by_id:
                    included.add(parent_of[loc_id])
                for child in children_of.get(loc_id, []):
                    walk_children(child, depth)
                for t in transversal_edges:
                    if t["from"] == loc_id and t["to"] in location_by_id:
                        included.add(t["to"])
                    elif t["to"] == loc_id and t["from"] in location_by_id:
                        included.add(t["from"])
            universe_docs = []
        else:
            if root.startswith("universe:"):
                uni_key = root.split(":", 1)[1]
                universe_docs = [u for u in universes if u["id"] == uni_key or u["universe"] == uni_key]
            else:
                universe_docs = universes

            uni_keys = {u["universe"] for u in universe_docs}
            all_uni_keys = {u["universe"] for u in universes}
            for loc in locations:
                if loc["id"] in parent_of:
                    continue
                if loc["universe"] in uni_keys:
                    walk_children(loc["id"], depth)
                elif root == "all" and loc["universe"] not in all_uni_keys:
                    walk_children(loc["id"], depth)

        included = {lid for lid in included if lid in location_by_id}

        # When filtering by faction in a full-tree/universe scope, prune the
        # location set to member locations plus their ancestors.
        if faction and not root.startswith("location:"):
            member_locs = self._faction_member_locations(faction)
            keep: set[str] = set()
            for lid in member_locs:
                if lid not in location_by_id:
                    continue
                cur: str | None = lid
                while cur is not None and cur in location_by_id and cur not in keep:
                    keep.add(cur)
                    cur = parent_of.get(cur)
            included = {lid for lid in included if lid in keep}
            universe_docs = [
                u for u in universe_docs
                if any(location_by_id[lid]["universe"] == u["universe"] for lid in included)
            ]

        included_super = [e for e in super_edges if e["child"] in included and e["parent"] in included]
        included_transversal = [t for t in transversal_edges if t["from"] in included and t["to"] in included]

        occupants = self._occupants_for_locations(sorted(included), faction)

        occupant_relations: list[dict] = []
        if occupants:
            occupant_ids = [o["id"] for loc_rows in occupants.values() for o in loc_rows]
            occupant_relations = self._relations_between(occupant_ids)

        faction_doc = None
        if faction:
            f = self.get_entity(faction)
            if f:
                faction_doc = {"id": f.id, "name": f.name}

        return {
            "focus": focus if focus in included else None,
            "faction": faction_doc,
            "universes": universe_docs,
            "locations": [location_by_id[lid] for lid in sorted(included)],
            "super_edges": included_super,
            "transversal_edges": included_transversal,
            "occupants": occupants,
            "occupant_relations": occupant_relations,
        }

    def navigate_from(self, location_id: str) -> dict:
        """Return navigation options from a location.

        Returns parent (via 'super' edge), children (inbound 'super'),
        transversal destinations (any 'transversal' edges), and occupants.
        """
        query = f"""
            LET loc = DOCUMENT(@loc_ref)
            LET parent = FIRST(
                FOR r IN {RELATIONSHIPS}
                FILTER r._from == @loc_ref AND r.type == 'super'
                RETURN DOCUMENT(r._to)
            )
            LET children = (
                FOR r IN {RELATIONSHIPS}
                FILTER r._to == @loc_ref AND r.type == 'super'
                RETURN DOCUMENT(r._from)
            )
            LET transversal = (
                FOR r IN {RELATIONSHIPS}
                FILTER r._from == @loc_ref AND r.type == 'transversal'
                RETURN MERGE(DOCUMENT(r._to), {{ transversal_type: r.transversal_type, effects: r.effects || [] }})
            )
            LET bodies = (
                FOR p IN {PROJECTIONS}
                FILTER p.current_location == @lid
                RETURN {{ entity_id: p.entity_id, body_id: p._key }}
            )
            LET occupant_ids = (
                FOR b IN bodies
                RETURN DISTINCT b.entity_id
            )
            LET occupants = (
                FOR e IN {ENTITIES}
                FILTER e.type IN ['character', 'gmc', 'asset']
                FILTER e._key IN occupant_ids OR e.current_location == @lid
                LET here = FIRST(
                    FOR b IN bodies
                    FILTER b.entity_id == e._key
                    RETURN b.body_id
                )
                RETURN {{
                    name: e.name, type: e.type, id: e._key,
                    map_x: e.map_x, map_y: e.map_y, unpublished: e.unpublished == true,
                    body_id: here
                }}
            )
            RETURN {{
                location: loc,
                parent: parent,
                children: children,
                transversal: transversal,
                occupants: occupants
            }}
        """
        cursor = self.db.aql.execute(query, bind_vars={
            "loc_ref": f"{ENTITIES}/{location_id}",
            "lid": location_id,
        })
        results = list(cursor)
        default = {"location": None, "parent": None, "children": [], "transversal": [], "occupants": []}
        result = results[0] if results else default

        # Resolve occupant navdot images from the role tag (not the legacy
        # background_image field). The REST layer can still override with a
        # more specific resolution, but this is the canonical source.
        #
        # Each occupant resolves through the body standing **here** (``body_id``),
        # not the entity's active body: an entity that travelled away is present as
        # the body it left behind, and the active body's face is not its face
        # ([[B137]] S1).
        occupants = result.get("occupants", [])
        occ_ids = [o["id"] for o in occupants]
        bodies = {o["id"]: o["body_id"] for o in occupants if o.get("body_id")}
        navdots = self._navdot_urls(occ_ids, bodies=bodies)
        for occ in occupants:
            occ["image"] = navdots.get(occ["id"])

        return result

    def canvas_neighborhood(self, location_id: str) -> dict:
        """Return a location's neighborhood for the relational canvas.

        Extends ``navigate_from`` with faction memberships for occupants and
        occupant-to-occupant relationship edges (labeled).
        """
        result = self.navigate_from(location_id)
        if result["location"] is None:
            return result

        occupant_ids = [o["id"] for o in result.get("occupants", [])]
        result["faction_memberships"] = self._faction_memberships_for(occupant_ids)
        result["occupant_relations"] = self._relations_between(occupant_ids)
        return result

    def get_faction_roster(self, faction_id: str) -> list[dict]:
        """The faction's roster: ``{id, name, type, location_id, role, rank}``.

        A roster entry is a ``membership`` edge — or a ``relation`` tie carrying a
        roster trait, which is the shape the authored sect rosters are in. The
        traits are matched by **name**, not by key: the registry holds two traits
        called ``role`` (``trait-12795986``, which the migrated content uses, and
        ``trait-13684952``), so a key comparison silently misses the real data.

        The direction rule matters: only ``member → faction`` ties count. The
        reverse is the *organisation's* view of someone (Azure Dawn's "outer sect
        disciple"), which is a posture, not a roster slot.

        This is the single roster read — the canvas and the GraphQL roster fields
        all go through it, so they cannot disagree.
        """
        # A roster entry is a `membership` edge — or a `relation` tie carrying a
        # roster trait, which is the shape the authored sect rosters are in.
        trait_names = {t.id: t.name for t in self.get_all_traits()}
        tie_query = f"""
            FOR r IN {RELATIONSHIPS}
            FILTER r._to == @faction_ref AND r.type IN ['membership', 'relation']
            RETURN {{ edge_key: r._key, type: r.type, member_key: PARSE_IDENTIFIER(r._from).key }}
        """
        ties = list(self.db.aql.execute(
            tie_query, bind_vars={"faction_ref": f"{ENTITIES}/{faction_id}"}
        ))

        roster: list[dict] = []
        for tie in ties:
            role = None
            rank = None
            for ts in self.get_relationship_traitsettings(tie["edge_key"]):
                name = trait_names.get(ts.trait_id)
                if name == ROLE_TRAIT_NAME:
                    role = ts.statement or ts.trait_id
                elif name == RANK_TRAIT_NAME and ts.dice:
                    rank = dice_list_to_rating(ts.dice)
            if tie["type"] != "membership" and role is None and rank is None:
                continue  # a posture tie between the faction and something else
            roster.append({"id": tie["member_key"], "role": role, "rank": rank})

        if not roster:
            return []
        entity_query = f"""
            FOR e IN {ENTITIES}
            FILTER e._key IN @keys AND e.type IN ['gmc', 'character', 'asset']
            RETURN {{ id: e._key, name: e.name, type: e.type, location_id: e.current_location }}
        """
        by_id = {
            doc["id"]: doc
            for doc in self.db.aql.execute(
                entity_query, bind_vars={"keys": [r["id"] for r in roster]}
            )
        }
        return [
            {**by_id[r["id"]], "role": r["role"], "rank": r["rank"]}
            for r in roster
            if r["id"] in by_id
        ]

    def get_entity_factions(self, entity_id: str) -> list[str]:
        """Faction ids this entity is on the roster of.

        The inverse of :meth:`get_faction_roster`, and it uses the same two shapes
        (``membership``, or a roster-trait ``relation`` tie) so the two reads agree.
        """
        trait_names = {t.id: t.name for t in self.get_all_traits()}
        query = f"""
            FOR r IN {RELATIONSHIPS}
            FILTER r._from == @eref AND r.type IN ['membership', 'relation']
            LET faction = DOCUMENT(r._to)
            FILTER faction != null AND faction.type == 'faction'
            RETURN {{ edge_key: r._key, type: r.type, faction: faction._key }}
        """
        rows = list(self.db.aql.execute(
            query, bind_vars={"eref": f"{ENTITIES}/{entity_id}"}
        ))
        factions: list[str] = []
        for row in rows:
            if row["type"] != "membership":
                names = {
                    trait_names.get(ts.trait_id)
                    for ts in self.get_relationship_traitsettings(row["edge_key"])
                }
                if not (ROLE_TRAIT_NAME in names or RANK_TRAIT_NAME in names):
                    continue  # posture only
            if row["faction"] not in factions:
                factions.append(row["faction"])
        return factions

    def get_factions_for_entities(self, entity_ids: list[str]) -> list[dict]:
        """Bulk association read: which factions each entity is tied to, either direction.

        The batched sibling of :meth:`get_entity_factions`, on the broader
        semantics the GM filter needs: **any** tie to a faction counts, including
        a posture the *faction* holds toward the entity (``faction → entity``).
        The roster read is deliberately narrower — a ``relation`` tie is a roster
        slot there only when it carries ``role``/``rank``, and only in the
        member → faction direction — so this is a second read, not a widening of
        the first.

        Three facts shape the result, all from the edge model rather than taste:

        * **Direction decides where a role can be written.** A roster slot is
          ``entity → faction`` — also the only direction :meth:`get_faction_roster`
          counts. A ``faction → entity`` tie is the organisation's posture toward
          someone. Each row reports the two directions' tie types separately, so a
          caller can tell a tie it may write a role onto from one it must not.
        * **One pair can hold both directions** — the live Azure Dawn pair does —
          so rows are merged per ``(entity, faction)`` rather than returned per
          edge; a list keyed by faction would otherwise show a faction twice.
        * **Only entity-level edges count**, matching :meth:`get_related_entities`,
          the read this replaces. An edge anchored to one of an entity's
          projections associates the *body*, not the entity.

        Returns ``[{entity_id, faction_id, name, out_tie_type, in_tie_type}]``
        sorted by entity then faction name — one row per association, one query
        for the whole list (nothing here loads the trait registry, which is what
        made the per-entity read unbatched).
        """
        if not entity_ids:
            return []
        query = f"""
            FOR r IN {RELATIONSHIPS}
            FILTER r._from IN @refs OR r._to IN @refs
            LET f = PARSE_IDENTIFIER(r._from)
            LET t = PARSE_IDENTIFIER(r._to)
            FILTER f.collection == 'entities' AND t.collection == 'entities'
            LET fe = DOCUMENT(r._from)
            LET te = DOCUMENT(r._to)
            FILTER fe != null AND te != null
            LET out_hit = f.key IN @ids AND te.type == 'faction'
            LET in_hit = t.key IN @ids AND fe.type == 'faction'
            FILTER out_hit OR in_hit
            RETURN {{
                entity_id: out_hit ? f.key : t.key,
                faction_id: out_hit ? t.key : f.key,
                name: out_hit ? te.name : fe.name,
                out_tie_type: out_hit ? r.type : '',
                in_tie_type: in_hit ? r.type : '',
            }}
        """
        refs = [f"{ENTITIES}/{eid}" for eid in entity_ids]
        merged: dict[tuple[str, str], dict] = {}
        for row in self.db.aql.execute(
            query, bind_vars={"refs": refs, "ids": list(entity_ids)}
        ):
            key = (row["entity_id"], row["faction_id"])
            found = merged.get(key)
            if found is None:
                merged[key] = dict(row)
                continue
            # The same pair reached from the other direction: keep whichever
            # direction each field came from rather than letting the last write win.
            if not found["out_tie_type"]:
                found["out_tie_type"] = row["out_tie_type"]
            if not found["in_tie_type"]:
                found["in_tie_type"] = row["in_tie_type"]
        return sorted(merged.values(), key=lambda r: (r["entity_id"], r["name"]))

    def _location_adjacency(self, exclude_hidden: bool = False) -> dict[str, list[tuple[str, int]]]:
        """The location graph as an undirected adjacency map.

        ``super`` **and** ``transversal`` edges, each step costing 1 — except a
        ``transversal`` that crosses a universe boundary, which costs
        ``CROSS_UNIVERSE_WEIGHT``. A ``super`` edge is a hierarchy link, never a
        boundary crossing, so it always costs one step.

        One definition, shared by every distance read — the faction ranking
        (:meth:`get_faction_distances_for_location`), the point-to-point read
        (:meth:`get_location_distances_from`) and the guided route
        (:meth:`get_route_next_hop`) — so "how far" cannot come to mean two
        different things.

        ``exclude_hidden`` drops every edge touching a location flagged
        ``hidden``, which removes that node from the graph (a node with no edges
        is unreachable, and one that is unreachable can never be stepped through).
        The guided route uses it to keep concealed places concealed — see
        :meth:`get_route_next_hop`.
        """
        edge_query = f"""
            FOR r IN {RELATIONSHIPS}
            FILTER r.type IN ['super', 'transversal']
            LET f = PARSE_IDENTIFIER(r._from)
            LET t = PARSE_IDENTIFIER(r._to)
            FILTER f.collection == 'entities' AND t.collection == 'entities'
            LET fe = DOCUMENT(r._from)
            LET te = DOCUMENT(r._to)
            FILTER fe != null AND te != null
            FILTER fe.type == 'location' AND te.type == 'location'
            RETURN {{
                type: r.type,
                from: f.key,
                to: t.key,
                cross: fe.current_universe != te.current_universe,
                from_hidden: fe.hidden == true,
                to_hidden: te.hidden == true,
            }}
        """
        adjacency: dict[str, list[tuple[str, int]]] = {}
        for row in self.db.aql.execute(edge_query):
            if exclude_hidden and (row["from_hidden"] or row["to_hidden"]):
                continue
            # Only a *portal* can cross a boundary; a `super` edge is a hierarchy
            # link and always costs one step.
            cost = (
                CROSS_UNIVERSE_WEIGHT
                if row["type"] == "transversal" and row["cross"]
                else 1
            )
            adjacency.setdefault(row["from"], []).append((row["to"], cost))
            adjacency.setdefault(row["to"], []).append((row["from"], cost))
        return adjacency

    def get_location_distances_from(
        self, origin: str, targets: set[str], exclude_hidden: bool = False
    ) -> dict[str, int]:
        """Weighted distance from ``origin`` to each **reachable** target location.

        The point-to-point sibling of :meth:`get_faction_distances_for_location`,
        over the same graph and weights (:meth:`_location_adjacency`): ``super``
        and ``transversal`` edges walked undirected, a step costing 1 unless a
        portal crosses a universe boundary (``CROSS_UNIVERSE_WEIGHT``).

        Unreachable targets are **absent** from the result rather than present as
        a sentinel, so the caller decides what "nowhere near" means for its own
        candidates. The graph is fragmentary in practice (195 of 410 locations
        unreachable from the single authored control point), so a caller ranking
        candidates must not read a sentinel as a number. ``origin`` itself scores
        ``0`` when it is one of the targets.

        Dijkstra, settling nearest-first, stopping once every target is settled —
        so an unreachable target costs walking its component, not the whole graph.

        ``exclude_hidden`` walks the graph with every ``hidden`` location removed
        (:meth:`_location_adjacency`), for callers that must not route through
        concealed places.
        """
        remaining = {t for t in targets if t}
        found: dict[str, int] = {}
        if not remaining:
            return found
        adjacency = self._location_adjacency(exclude_hidden=exclude_hidden)
        seen: set[str] = set()
        heap: list[tuple[int, str]] = [(0, origin)]
        while heap:
            dist, node = heapq.heappop(heap)
            if node in seen:
                continue
            seen.add(node)
            if node in remaining:
                found[node] = dist
                remaining.discard(node)
                if not remaining:
                    break
            for neighbour, cost in adjacency.get(node, ()):
                if neighbour not in seen:
                    heapq.heappush(heap, (dist + cost, neighbour))
        return found

    def get_route_next_hop(self, origin: str, destination: str) -> str | None:
        """The next location to step to when walking from ``origin`` toward ``destination``.

        The read behind the guided route ([[Location Viewer]]): given where a
        character stands and the destination they were handed, which neighbouring
        location is the first step? The viewer lights **that one** navdot and
        nothing else, so following directions still means travelling — one hop at
        a time — instead of reading the whole route off the map.

        **Hidden locations stay hidden unless they are unavoidable.** The search
        runs twice: first over a graph with every ``hidden`` location removed, and
        only if that leaves ``origin`` unreachable does it fall back to the full
        graph. So a concealed place is never given away while a way around it
        exists, and a destination behind one is still reachable rather than
        silently out of reach. That is the requested rule exactly, not a weighted
        approximation: a cheap hidden shortcut versus a long open detour is a
        different answer from "avoid it if you can".

        Returns the neighbour's location id, or ``None`` when ``origin`` already
        *is* the destination or nothing connects the two.

        Reuses :meth:`get_location_distances_from` rather than a second Dijkstra:
        the graph is undirected, so ``dist(destination → neighbour)`` is the same
        number as ``dist(neighbour → destination)``, which is exactly the quantity
        the choice needs. The cost of the step out of ``origin`` is added back on
        top of it.
        """
        if not origin or not destination or origin == destination:
            return None
        for exclude_hidden in (True, False):
            adjacency = self._location_adjacency(exclude_hidden=exclude_hidden)
            steps = adjacency.get(origin) or []
            if not steps:
                continue
            to_destination = self.get_location_distances_from(
                destination, {n for n, _ in steps}, exclude_hidden=exclude_hidden
            )
            if not to_destination:
                continue
            # Cheapest total walk out of the origin: this step, plus the rest of
            # the way from the neighbour. Ties break on id, so the hop is stable.
            _total, nxt = min(
                (cost + to_destination[n], n) for n, cost in steps if n in to_destination
            )
            return nxt
        return None

    def get_faction_distances_for_location(self, location_id: str) -> list[dict]:
        """Every faction with its weighted distance to this location, nearest first.

        The read behind a distance-sorted faction list ([[Tickets#B134]]).
        Distance runs along the **location graph** — ``super`` and
        ``transversal`` edges, walked **undirected** — from this location to the
        nearest location the faction is **present** at; a faction present at this
        very place scores 0.

        **Presence is two things, and the author widened it (2026-09-26):**

        * **Authored ground** — any ``faction → location`` relationship, whatever
          trait it carries, reported as ``holds_ground``. It used to *require* a
          ``control`` setting, and gating on that one trait was too narrow: a
          faction↔place tie is itself the statement that the faction is here, and
          the gate hid every other authored tie (7 of 12 live ties, measured).
          ``control`` is still the strongest reading of ground; it is simply no
          longer the gate.
        * **People present** — a member of the faction standing at the location,
          reported as ``has_people``: ``membership`` edges (member → faction)
          joined to where the member's **body** is, by the same direct-or-projected
          rule the occupant read uses ([[B137]] S1), so the GM's list and the map
          cannot disagree about who is somewhere. **Assets are excluded** — a
          parked asset is not ears. A member anywhere makes their whole faction
          present there, which is the point: *an informant becomes visible*.

        That widening is worth its cost because the derived half is already
        maintained for free: measured 2026-09-26 there are 94 memberships (66 GMC,
        27 character, 1 asset) and **every** member carries a location, while only
        **1 of 81** factions held any ``control`` ground. Presence covers **21**.

        Four decisions, all the author's (2026-09-16, extended 2026-09-26):

        * **Undirected.** ``super`` is stored child → parent only, so following
          stored direction reaches **49 of 410** locations from the Iron Roots
          seat against **215** undirected — a directed walk answers a different
          and much smaller question. (100 of 354 ``transversal`` edges also lack
          a stored return edge, mostly places that are plainly two-way, so they
          only work undirected too.)
        * **``super`` and ``transversal`` both count**, so a faction's reach can
          cross universes.
        * **A portal costs 1 inside its universe and ``CROSS_UNIVERSE_WEIGHT``
          across a boundary**; a ``super`` edge always costs 1.
        * **A tie's die is ignored** — a d10 "sect seat" says *how much*, not *how
          far*.

        A presence tie is a **faction → location** edge. Direction matters: the
        reverse (a location's posture toward a faction) is not presence.

        **Computed on read, deliberately not materialized.** Measured 2026-09-16:
        a full recompute for all 74 factions is ~2.4 ms at 410 locations and 711
        edges, and one location needs a single search. Materializing would add an
        invalidation surface spanning every location, ``super``/``transversal``
        edge, tie and member move, to save a fraction of a millisecond. **Revisit
        if the graph or the faction count grows by orders of magnitude** — the
        design log records the trigger.

        Returns ``[{faction_id, name, distance, nearest_location_id,
        nearest_location_name, presence}]`` for **every** faction, sorted:
        reachable ones by distance, then authored ground before derived people,
        then name, then the rest by name. ``distance`` is None when the faction is
        present nowhere reachable — those are kept so a caller can show the whole
        faction list with the near ones at the top.
        """
        adjacency = self._location_adjacency()

        # Both presence sources resolve a **projection to the entity behind it**,
        # because a tie or a membership is often anchored to a body: three live
        # `control` ties sat on `projections/…` edges and were silently dropped by
        # the old `f.type == 'faction'` document filter, since projections carry
        # `type: null`.
        ground_query = f"""
            FOR r IN {RELATIONSHIPS}
            FILTER r.type == 'relation'
            LET fc = PARSE_IDENTIFIER(r._from).collection
            LET tc = PARSE_IDENTIFIER(r._to).collection
            LET fraw = DOCUMENT(r._from)
            LET traw = DOCUMENT(r._to)
            FILTER fraw != null AND traw != null
            LET f = fc == 'projections' ? DOCUMENT(CONCAT('entities/', fraw.entity_id)) : fraw
            LET t = tc == 'projections' ? DOCUMENT(CONCAT('entities/', traw.entity_id)) : traw
            FILTER f != null AND t != null
            FILTER f.type == 'faction' AND t.type == 'location'
            RETURN DISTINCT {{ faction: f._key, location: t._key }}
        """
        # A member's standing places: their own `current_location` (the active
        # body's) plus every body of theirs parked somewhere — the same union the
        # occupant read builds, so "who is here" has one answer.
        people_query = f"""
            FOR r IN {RELATIONSHIPS}
            FILTER r.type == 'membership'
            LET mc = PARSE_IDENTIFIER(r._from).collection
            LET fc = PARSE_IDENTIFIER(r._to).collection
            LET mraw = DOCUMENT(r._from)
            LET fraw = DOCUMENT(r._to)
            FILTER mraw != null AND fraw != null
            LET f = fc == 'projections' ? DOCUMENT(CONCAT('entities/', fraw.entity_id)) : fraw
            LET m = mc == 'projections' ? DOCUMENT(CONCAT('entities/', mraw.entity_id)) : mraw
            FILTER f != null AND f.type == 'faction'
            FILTER m != null AND m.type IN ['character', 'gmc']
            FOR l IN UNION_DISTINCT(
                (m.current_location != null AND m.current_location != ''
                    ? [m.current_location] : []),
                (FOR p IN {PROJECTIONS}
                    FILTER p.entity_id == m._key
                      AND p.current_location != null AND p.current_location != ''
                    RETURN p.current_location))
            RETURN DISTINCT {{ faction: f._key, location: l }}
        """
        # Authored ground is written first so that, where both hold, the stronger
        # reading survives the `setdefault` below.
        by_location: dict[str, dict[str, str]] = {}
        for row in self.db.aql.execute(ground_query):
            by_location.setdefault(row["location"], {})[row["faction"]] = PRESENCE_GROUND
        for row in self.db.aql.execute(people_query):
            by_location.setdefault(row["location"], {}).setdefault(
                row["faction"], PRESENCE_PEOPLE
            )
        present = {f for factions_here in by_location.values() for f in factions_here}

        # One Dijkstra from the requested location settles nodes nearest-first, so
        # the first time a faction's presence is reached *is* its nearest one — no
        # per-faction search needed.
        found: dict[str, tuple[int, str, str]] = {}
        seen: set[str] = set()
        heap: list[tuple[int, str]] = [(0, location_id)]
        while heap:
            dist, node = heapq.heappop(heap)
            if node in seen:
                continue
            seen.add(node)
            for faction_id, kind in by_location.get(node, {}).items():
                found.setdefault(faction_id, (dist, node, kind))
            if len(found) == len(present):
                break  # every faction that is present anywhere has been reached
            for neighbour, cost in adjacency.get(node, ()):
                if neighbour not in seen:
                    heapq.heappush(heap, (dist + cost, neighbour))

        # Name the places the ranking points at, in one read: "has people in
        # Murkwell Caves" is the reminder the list exists to give.
        nearest_ids = sorted({hit[1] for hit in found.values()})
        names: dict[str, str] = {}
        if nearest_ids:
            for row in self.db.aql.execute(
                f"FOR e IN {ENTITIES} FILTER e._key IN @ids "
                "RETURN { id: e._key, name: e.name }",
                bind_vars={"ids": nearest_ids},
            ):
                names[row["id"]] = row["name"]

        factions = list(self.db.aql.execute(
            f"FOR e IN {ENTITIES} FILTER e.type == 'faction' "
            "RETURN { id: e._key, name: e.name }"
        ))
        rows = []
        for faction in factions:
            hit = found.get(faction["id"])
            rows.append({
                "faction_id": faction["id"],
                "name": faction["name"],
                "distance": hit[0] if hit else None,
                "nearest_location_id": hit[1] if hit else None,
                "nearest_location_name": names.get(hit[1]) if hit else None,
                "presence": hit[2] if hit else None,
            })
        rows.sort(key=lambda r: (
            r["distance"] is None,
            r["distance"] or 0,
            0 if r["presence"] == PRESENCE_GROUND else 1,
            r["name"],
        ))
        return rows

    def canvas_faction(self, faction_id: str) -> dict:
        """Return conspyramid data for a faction.

        Returns members (with rank/role), the locations where members are
        placed, ancestor scaffolding for the pruned tree, and labeled
        relations between members.
        """
        faction = self.get_entity(faction_id)
        if faction is None:
            return {"faction": None, "members": [], "locations": [], "ancestors": [], "location_edges": [], "relations": []}

        # The canvas renders people and places, so assets are filtered out here —
        # the roster read itself keeps them (an org owns things).
        members = [m for m in self.get_faction_roster(faction_id) if m["type"] != "asset"]

        member_ids = [m["id"] for m in members]
        member_locations = [m["location_id"] for m in members if m["location_id"]]

        locations = self._location_dicts(member_locations)
        location_keys = {l["id"] for l in locations}

        ancestors: set[str] = set()
        for lid in member_locations:
            for a in self.get_location_ancestors(lid):
                ancestors.add(a)
        ancestor_locations = [
            l for l in self._location_dicts(list(ancestors))
            if l["id"] not in location_keys
        ]

        # Super edges among the pruned location set (member locations + their
        # ancestors), so the frontend can render the hierarchy as a tree.
        relevant_ids = list(set(member_locations) | ancestors)
        location_edges: list[dict] = []
        if relevant_ids:
            edge_query = f"""
                FOR r IN {RELATIONSHIPS}
                FILTER r.type == 'super'
                LET child = PARSE_IDENTIFIER(r._from).key
                LET parent = PARSE_IDENTIFIER(r._to).key
                FILTER child IN @ids AND parent IN @ids
                RETURN {{ child: child, parent: parent }}
            """
            location_edges = list(self.db.aql.execute(edge_query, bind_vars={"ids": relevant_ids}))

        relations = self._relations_between(member_ids)

        return {
            "faction": {"id": faction.id, "name": faction.name},
            "members": members,
            "locations": locations,
            "ancestors": ancestor_locations,
            "location_edges": location_edges,
            "relations": relations,
        }

    def canvas_gmc_web(self, gmc_id: str) -> dict:
        """Return a GMC's relational web: the GMC, its location, and direct
        relations to other GMCs plus their locations."""
        gmc = self.get_entity(gmc_id)
        if gmc is None:
            return {"gmc": None, "location": None, "relations": []}

        location = self.get_entity(gmc.current_location) if gmc.current_location else None

        query = f"""
            FOR r IN {RELATIONSHIPS}
            FILTER (r._from == @gmc_ref OR r._to == @gmc_ref)
              AND r.type NOT IN {_STRUCTURAL_TYPES_AQL}
            LET other_key = PARSE_IDENTIFIER(r._from).key == @gid
                ? PARSE_IDENTIFIER(r._to).key
                : PARSE_IDENTIFIER(r._from).key
            FOR e IN {ENTITIES}
            FILTER e._key == other_key AND e.type IN ['gmc', 'character']
            RETURN {{
                from: PARSE_IDENTIFIER(r._from).key,
                to: PARSE_IDENTIFIER(r._to).key,
                type: r.type,
                description: NOT_NULL(r.description, ''),
                other_id: e._key,
                other_name: e.name,
                other_location_id: e.current_location,
            }}
        """
        relations = list(self.db.aql.execute(query, bind_vars={
            "gmc_ref": f"{ENTITIES}/{gmc_id}",
            "gid": gmc_id,
        }))

        loc_ids = {r["other_location_id"] for r in relations if r["other_location_id"]}
        loc_map = {l["id"]: l["name"] for l in self._location_dicts(list(loc_ids))}
        for r in relations:
            r["other_location_name"] = loc_map.get(r["other_location_id"]) if r["other_location_id"] else None

        return {
            "gmc": {"id": gmc.id, "name": gmc.name},
            "location": {"id": location.id, "name": location.name} if location else None,
            "relations": relations,
        }

    def _faction_memberships_for(self, entity_ids: list[str]) -> dict:
        """Map entity_id → list of {{id, name}} factions via membership edges."""
        if not entity_ids:
            return {}
        query = f"""
            FOR r IN {RELATIONSHIPS}
            FILTER r.type == 'membership'
            LET member_key = PARSE_IDENTIFIER(r._from).key
            FILTER member_key IN @ids
            FOR f IN {ENTITIES}
            FILTER f._key == PARSE_IDENTIFIER(r._to).key AND f.type == 'faction'
            RETURN {{ member: member_key, id: f._key, name: f.name }}
        """
        result: dict = {}
        for row in self.db.aql.execute(query, bind_vars={"ids": entity_ids}):
            result.setdefault(row["member"], []).append({"id": row["id"], "name": row["name"]})
        return result

    def _relations_between(self, entity_ids: list[str]) -> list[dict]:
        """Return non-structural relationships whose endpoints are all in ``entity_ids``.

        Each relation carries its relationship-anchored traits so the canvas can
        annotate the edge. ``statement`` is the authored distinction; ``name`` is
        the trait registry's generic name, which the canvas falls back to when the
        statement is blank. Both are resolved inline so the whole payload still
        costs one query rather than one per relation.
        """
        if len(entity_ids) < 2:
            return []
        query = f"""
            FOR r IN {RELATIONSHIPS}
            LET from_key = PARSE_IDENTIFIER(r._from).key
            LET to_key = PARSE_IDENTIFIER(r._to).key
            FILTER from_key IN @ids AND to_key IN @ids
              AND r.type NOT IN {_STRUCTURAL_TYPES_AQL}
            LET traits = (
                FOR ts IN {TRAITSETTINGS}
                FILTER ts.entity_id == r._key AND ts.from_type == 'relationship'
                LET t = DOCUMENT({TRAITS}, ts.trait_id)
                RETURN {{ name: t.name, statement: NOT_NULL(ts.statement, '') }}
            )
            RETURN {{ from: from_key, to: to_key, type: r.type,
                      description: NOT_NULL(r.description, ''),
                      traits: traits }}
        """
        return list(self.db.aql.execute(query, bind_vars={"ids": entity_ids}))

    def _location_dicts(self, location_ids: list[str]) -> list[dict]:
        """Return light location dicts for a set of location keys."""
        if not location_ids:
            return []
        query = f"""
            FOR e IN {ENTITIES}
            FILTER e.type == 'location' AND e._key IN @ids
            RETURN {{ id: e._key, name: e.name, universe: e.current_universe }}
        """
        return list(self.db.aql.execute(query, bind_vars={"ids": location_ids}))

    def get_location_ancestors(self, location_id: str) -> list[str]:
        """Return all ancestor location IDs by following 'super' edges upward.

        The chain goes child → parent → grandparent → …  Returns location
        ``_key`` values sorted from nearest ancestor to root.
        """
        if self.db is not None:
            # Load every 'super' edge in one index scan (they number in the
            # hundreds) and walk the child→parent chain in Python. The previous
            # `1..10 OUTBOUND … FILTER e.type == 'super'` traversed *all*
            # relationship types and filtered after, exploding combinatorially
            # on the dense relationship graph (measured 60s+).
            parent: dict[str, str] = {}
            for doc in self.db.aql.execute(
                f"FOR r IN {RELATIONSHIPS} FILTER r.type == 'super' RETURN r"
            ):
                child = doc["_from"].split("/", 1)[1]
                parent.setdefault(child, doc["_to"].split("/", 1)[1])
            ancestors: list[str] = []
            current = location_id
            for _ in range(10):
                nxt = parent.get(current)
                if not nxt:
                    break
                ancestors.append(nxt)
                current = nxt
            return ancestors
        else:
            # In-memory mode
            ancestors = []
            current = location_id
            for _ in range(10):
                parent = None
                for rel in self._relationships:
                    if (rel.get("_from") == f"{ENTITIES}/{current}"
                            and rel.get("type") == "super"):
                        parent = rel.get("_to", "").replace(f"{ENTITIES}/", "")
                        break
                if parent:
                    ancestors.append(parent)
                    current = parent
                else:
                    break
            return ancestors

    def list_location_descendants(self, location_id: str) -> list[str]:
        """Return all descendant location IDs by following 'super' edges downward.

        ``super`` edges point child → parent, so descendants are found by an
        inbound traversal from the root. Returns location ``_key`` values (the
        root itself is not included).
        """
        if self.db is not None:
            # Load every 'super' edge once and BFS downward — same logic as the
            # in-memory fallback, without the 1..10 INBOUND traversal explosion.
            children: dict[str, list[str]] = {}
            for doc in self.db.aql.execute(
                f"FOR r IN {RELATIONSHIPS} FILTER r.type == 'super' RETURN r"
            ):
                parent = doc["_to"].split("/", 1)[1]
                child = doc["_from"].split("/", 1)[1]
                children.setdefault(parent, []).append(child)
            descendants: list[str] = []
            frontier = [location_id]
            for _ in range(10):
                next_frontier: list[str] = []
                for loc in frontier:
                    for child in children.get(loc, []):
                        if child not in descendants and child != location_id:
                            descendants.append(child)
                            next_frontier.append(child)
                if not next_frontier:
                    break
                frontier = next_frontier
            return descendants
        else:
            # In-memory mode: follow child → parent edges in reverse.
            descendants: list[str] = []
            frontier = [location_id]
            for _ in range(10):
                next_frontier = []
                for rel in self._relationships:
                    if rel.get("type") != "super":
                        continue
                    child = rel.get("_from", "").replace(f"{ENTITIES}/", "")
                    parent = rel.get("_to", "").replace(f"{ENTITIES}/", "")
                    if parent in frontier and child not in descendants and child != location_id:
                        descendants.append(child)
                        next_frontier.append(child)
                if not next_frontier:
                    break
                frontier = next_frontier
            return descendants
