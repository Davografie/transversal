"""Players — split out of src/api/src/transversal/db/repository.py."""

from __future__ import annotations

from transversal.db.arango import ENTITIES
from transversal.db.arango import PLAYERS
from transversal.db.arango import RELATIONSHIPS
from transversal.domain import Player


class RepositoryPlayers:
    """Mixin contributing 18 member(s) to the repository."""

    def create_player(self, player_id: str, name: str, role: str = "player") -> Player:
        doc = {"_key": player_id, "name": name, "role": role, "epoch": 0}
        self._players.insert(doc)
        return Player(id=player_id, name=name, role=role)

    def get_player(self, player_id: str) -> Player | None:
        doc = self._players.get(player_id)
        if not doc:
            return None
        return self._to_player(doc)

    def _to_player(self, doc: dict) -> Player:
        pid = doc["_key"]
        return Player(
            id=pid,
            name=doc.get("name", ""),
            role=doc.get("role", "player"),
            # Absent on documents written before this landed; 0 is right, since
            # nothing has been revoked.
            epoch=doc.get("epoch", 0),
            last_spotlight_at=doc.get("last_spotlight_at"),
            last_main_entity_id=doc.get("last_main_entity_id"),
            entity_ids=self.get_player_entities(pid),
        )

    def find_player_by_name(self, name: str) -> Player | None:
        query = f"""
            FOR p IN {PLAYERS}
            FILTER LOWER(p.name) == @name
            LIMIT 1
            RETURN p
        """
        cursor = self.db.aql.execute(query, bind_vars={"name": name.lower().strip()})
        results = list(cursor)
        return self._to_player(results[0]) if results else None

    def search_players(self, query_str: str) -> list[Player]:
        q = query_str.lower().strip()
        if not q:
            return []
        aql = f"""
            FOR p IN {PLAYERS}
            FILTER CONTAINS(LOWER(p.name), @q)
            SORT p.name
            RETURN p
        """
        return [self._to_player(doc) for doc in self.db.aql.execute(aql, bind_vars={"q": q})]

    def list_players(self) -> list[Player]:
        return [self._to_player(doc) for doc in self._players.all()]

    def update_player(self, player_id: str, updates: dict) -> bool:
        player = self._players.get(player_id)
        if player:
            player.update(updates)
            self._players.update(player)
            return True
        return False

    def delete_player(self, player_id: str) -> bool:
        # Cascade-delete agency edges
        self.db.aql.execute(
            f"FOR r IN {RELATIONSHIPS} FILTER r._from == @pref AND r.type == 'agency' REMOVE r IN {RELATIONSHIPS}",
            bind_vars={"pref": f"{PLAYERS}/{player_id}"}
        )
        try:
            self._players.delete(player_id)
            return True
        except Exception:
            return False

    def claim_entity(
        self, player_id: str, entity_id: str, main: bool | None = None
    ) -> bool:
        """Claim an entity for a player (an ``agency`` edge).

        ``main=None`` (the default) auto-designates the player's main when they
        have none (B117): a player with no flagged main — the fresh player
        creating their first, or only, character — gets this claim flagged, so
        spotlight and the troupe machinery work without a manual GM
        designation. A player who already has a main keeps it: a later claim
        never steals the flag.

        ``main=False`` is the explicit opt-out, for a claim that is known not to
        be a main (support-character creation, B59). An existing edge is never
        re-flagged — the client re-claims on every character switch, and the
        designation is changed only via ``set_agency_main``.
        """
        if not self._players.has(player_id):
            return False
        edge_key = f"edge:{player_id}:{entity_id}:agency"
        if not self._relationships.has(edge_key):
            if main is None:
                main = self.get_designated_main(player_id) is None
            self._relationships.insert({
                "_key": edge_key,
                "_from": f"{PLAYERS}/{player_id}",
                "_to": f"{ENTITIES}/{entity_id}",
                "type": "agency",
                "main": bool(main),
            })
        return True

    def set_agency_main(self, player_id: str, entity_id: str, main: bool) -> bool:
        """Set the ``main`` flag on a player's agency edge to an entity.

        Returns True only when the edge exists and was updated (a player can
        only flag entities they already own as mains).
        """
        edge_key = f"edge:{player_id}:{entity_id}:agency"
        edge = self._relationships.get(edge_key)
        if edge is None:
            return False
        edge["main"] = bool(main)
        self._relationships.update(edge)
        return True

    def get_agency_edges(self, player_id: str) -> list[dict]:
        """Return the player's agency edges (each with its ``main`` flag)."""
        query = f"""
            FOR r IN {RELATIONSHIPS}
            FILTER r._from == @pref AND r.type == 'agency'
            RETURN {{ entity_id: PARSE_IDENTIFIER(r._to).key, main: !!r.main }}
        """
        return list(self.db.aql.execute(query, bind_vars={"pref": f"{PLAYERS}/{player_id}"}))

    def release_entity(self, player_id: str, entity_id: str) -> bool:
        edge_key = f"edge:{player_id}:{entity_id}:agency"
        try:
            self._relationships.delete(edge_key)
            return True
        except Exception:
            return False

    def get_player_entities(self, player_id: str) -> list[str]:
        query = f"""
            FOR r IN {RELATIONSHIPS}
            FILTER r._from == @pref AND r.type == 'agency'
            RETURN PARSE_IDENTIFIER(r._to).key
        """
        return list(self.db.aql.execute(query, bind_vars={"pref": f"{PLAYERS}/{player_id}"}))

    def get_agency_main(self, player_id: str, entity_id: str) -> bool:
        """Whether ``entity_id`` is flagged ``main`` on the player's agency edge."""
        edge = self._relationships.get(f"edge:{player_id}:{entity_id}:agency")
        return bool(edge is not None and edge.get("main"))

    def get_agency_for_entity(self, entity_id: str) -> dict | None:
        """The agency edge pointing at an entity: ``{player_id, main}`` or None.

        The inverse of ``get_agency_edges`` — the GM panel asks who holds
        agency over an entity, which is the persistent relation, not the
        transient "who is controlling it right now".

        **One entity can have several holders** (measured live 2026-09-16: 42
        agency edges over 33 entities; one character held by 7 player records,
        which are one human's per-device identities). A single-answer read has
        to pick one, so it is ordered rather than left to plan order: a ``main``
        claim first, then player id ascending — the same determinism
        :meth:`get_designated_main` gets by sorting. Preferring ``main`` is what
        makes ``AgencyRef.main`` meaningful for a multi-held entity.
        """
        query = f"""
            FOR r IN {RELATIONSHIPS}
            FILTER r._to == @eref AND r.type == 'agency'
            SORT r.main DESC, PARSE_IDENTIFIER(r._from).key ASC
            LIMIT 1
            RETURN {{ player_id: PARSE_IDENTIFIER(r._from).key, main: !!r.main }}
        """
        rows = list(self.db.aql.execute(query, bind_vars={"eref": f"{ENTITIES}/{entity_id}"}))
        return rows[0] if rows else None

    def get_designated_main(self, player_id: str) -> str | None:
        """The player's designated main — the first agency edge flagged ``main``.

        Deterministic when a player has several mains (ordered by entity id).
        Returns ``None`` when the player has no main flagged. Distinct from
        ``last_main_entity_id`` (recency), which is only set after a control
        event; this is the structural designation that B63 falls back to.
        """
        query = f"""
            FOR r IN {RELATIONSHIPS}
            FILTER r._from == @pref AND r.type == 'agency' AND r.main == true
            SORT PARSE_IDENTIFIER(r._to).key ASC
            LIMIT 1
            RETURN PARSE_IDENTIFIER(r._to).key
        """
        results = list(self.db.aql.execute(query, bind_vars={"pref": f"{PLAYERS}/{player_id}"}))
        return results[0] if results else None

    def list_players_by_spotlight(self) -> list[Player]:
        """Players ordered oldest-first by spotlight recency (nulls = never, oldest).

        ``last_spotlight_at`` is the sort key; players who have never taken a
        main sort first (most due for a spotlight scene).
        """
        query = f"""
            FOR p IN {PLAYERS}
            SORT p.last_spotlight_at == null DESC, p.last_spotlight_at ASC, p.name ASC
            RETURN p
        """
        return [self._to_player(doc) for doc in self.db.aql.execute(query)]

    def get_entity_players(self, entity_id: str) -> list[str]:
        query = f"""
            FOR r IN {RELATIONSHIPS}
            FILTER r._to == @eref AND r.type == 'agency'
            RETURN PARSE_IDENTIFIER(r._from).key
        """
        return list(self.db.aql.execute(query, bind_vars={"eref": f"{ENTITIES}/{entity_id}"}))

    def list_support_edges(self) -> list[dict]:
        """Return every `support` relationship edge (SC → main).

        Each edge is an ArangoDB relationship doc whose ``_from``/``_to`` refs
        are of the form ``entities/{id}`` (directional SC → main).
        """
        query = f"""
            FOR r IN {RELATIONSHIPS}
            FILTER r.type == 'support'
            RETURN r
        """
        return list(self.db.aql.execute(query))
