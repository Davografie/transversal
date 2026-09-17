"""Canvas — split out of src/api/src/transversal/db/repository.py."""

from __future__ import annotations

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

        def build_node(loc_id: str) -> dict:
            loc = locations.get(loc_id, {"id": loc_id, "name": loc_id, "current_universe": ""})
            children = children_of.get(loc_id, [])
            return {
                "id": loc["id"],
                "name": loc["name"],
                "node_type": "location",
                "universe": loc.get("current_universe", ""),
                "children": [build_node(c) for c in sorted(children)],
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
        for ukey, uni in sorted(universes.items(), key=lambda kv: kv[1]["name"]):
            loc_roots = uni_roots.get(ukey, [])
            result.append({
                "id": uni["id"],
                "name": uni["name"],
                "node_type": "universe",
                "universe": ukey,
                "children": [build_node(r) for r in sorted(loc_roots)],
            })

        # Orphan locations (no matching universe entity) still appear as
        # top-level nodes so nothing is silently dropped.
        for lid in sorted(orphans):
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

    def _role_urls(self, entity_ids: list[str], role: str, variant: str = "Large") -> dict[str, str]:
        """Resolve one image URL per entity for a role tag.

        Each entity is resolved through its active projection (body) first,
        falling back to entity-level images. ``role`` is a canonical role tag
        (background/sheet/navdot); ``variant`` is the static size suffix
        (Large/Small). Animated images return their video URL regardless of
        variant.
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
        return {
            eid: url
            for eid in entity_ids
            if (url := self.resolve_role_image(eid, role, current_proj.get(eid), variant)) is not None
        }

    def _navdot_urls(self, entity_ids: list[str]) -> dict[str, str]:
        """Resolve one navdot image URL per entity, projection-scoped first."""
        return self._role_urls(entity_ids, "navdot")

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
                RETURN {{ id: e._key, name: e.name, type: e.type, location_id: e.current_location }}
            )
            LET projected = (
                FOR p IN {PROJECTIONS}
                FILTER p.current_location IN @lids
                FOR e IN {ENTITIES}
                FILTER e._key == p.entity_id AND e.type IN ['character', 'gmc', 'asset']
                  {member_filter}
                RETURN {{ id: e._key, name: e.name, type: e.type, location_id: p.current_location }}
            )
            FOR o IN UNION(direct, projected)
            RETURN o
        """
        rows = list(self.db.aql.execute(query, bind_vars=binds))

        result: dict = {}
        seen: set = set()
        for row in rows:
            key = (row["location_id"], row["id"])
            if key in seen:
                continue
            seen.add(key)
            result.setdefault(row["location_id"], []).append(row)

        occupant_ids = [row["id"] for loc_rows in result.values() for row in loc_rows]
        navdots = self._navdot_urls(occupant_ids)
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
            LET occupant_ids = (
                FOR p IN {PROJECTIONS}
                FILTER p.current_location == @lid
                RETURN DISTINCT p.entity_id
            )
            LET occupants = (
                FOR e IN {ENTITIES}
                FILTER e.type IN ['character', 'gmc', 'asset']
                FILTER e._key IN occupant_ids OR e.current_location == @lid
                RETURN {{
                    name: e.name, type: e.type, id: e._key,
                    map_x: e.map_x, map_y: e.map_y, unpublished: e.unpublished == true
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
        occ_ids = [o["id"] for o in result.get("occupants", [])]
        navdots = self._navdot_urls(occ_ids)
        for occ in result.get("occupants", []):
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
