"""Player management — ArangoDB-backed player identity and entity ownership.

Players are stored in the `players` collection (see ``domain.Player``).
Player→entity associations are `relationships` edges (type: `agency`), and are
resolved from the graph at read time rather than stored on the player document.
"""

from __future__ import annotations

import uuid

from transversal.db.repository import EntityRepository
from transversal.domain import Player

# Module-level active-main registry: player_id → the main entity currently
# controlled by that player. In-memory (mirrors the in-memory SSE bus); written
# only by ``record_control``, read by the troupe availability query (B57).
_active_main: dict[str, str] = {}

# Module-level current-body registry: player_id → the entity currently
# controlled by that player (main OR support character). Written on every
# ``record_control``; read by the troupe overview's "now playing" column (B66+).
_current_body: dict[str, str] = {}


def _set_active_main(player_id: str, main_id: str | None) -> None:
    if main_id is None:
        _active_main.pop(player_id, None)
    else:
        _active_main[player_id] = main_id


def is_main_active(player_id: str, main_id: str) -> bool:
    """Whether ``main_id`` is currently the active main of ``player_id``."""
    return _active_main.get(player_id) == main_id


def list_active_mains() -> dict[str, str]:
    """Snapshot of the active mains: player_id → active main entity id (B66)."""
    return dict(_active_main)


def list_current_bodies() -> dict[str, str]:
    """Snapshot of player_id → currently-controlled entity id (main or SC)."""
    return dict(_current_body)


class PlayerManager:
    """ArangoDB-backed player store."""

    def __init__(self, repo: EntityRepository | None = None):
        # An injected repository (tests) wins. Otherwise **every call** builds one for
        # the current database: the database is request-scoped ([[B88]]), so a repo
        # captured at import would pin players and `agency` edges — a campaign's
        # identity — to whichever campaign happened to be constructed first.
        self._injected_repo = repo

    @property
    def _repo(self) -> EntityRepository:
        return self._injected_repo or EntityRepository()

    @_repo.setter
    def _repo(self, repo: EntityRepository | None) -> None:
        # Kept assignable: injecting a repository by attribute (or forcing the real
        # one with `None`) is how the existing tests drive this class.
        self._injected_repo = repo

    def create(self, name: str = "") -> Player:
        pid = f"player-{uuid.uuid4().hex[:6]}"
        return self._repo.create_player(pid, name=name or pid, role="player")

    def get(self, player_id: str) -> Player | None:
        return self._repo.get_player(player_id)

    def claim_entity(self, player_id: str, entity_id: str, main: bool | None = None) -> bool:
        """Claim an entity; ``main=None`` auto-designates a first character (B117)."""
        return self._repo.claim_entity(player_id, entity_id, main=main)

    def release_entity(self, player_id: str, entity_id: str) -> bool:
        return self._repo.release_entity(player_id, entity_id)

    def set_agency_main(self, player_id: str, entity_id: str, main: bool) -> bool:
        return self._repo.set_agency_main(player_id, entity_id, main)

    def get_player_entities(self, player_id: str) -> list[str]:
        return self._repo.get_player_entities(player_id)

    def find_by_name(self, name: str) -> Player | None:
        return self._repo.find_player_by_name(name)

    def list_all(self) -> list[Player]:
        return self._repo.list_players()

    def search(self, query: str) -> list[Player]:
        return self._repo.search_players(query)

    def set_role(self, player_id: str, role: str) -> bool:
        return self._repo.update_player(player_id, {"role": role})

    def set_spotlight(
        self, player_id: str, last_main_entity_id: str | None, timestamp: str | None = None
    ) -> bool:
        """Stamp spotlight recency for a player (actor-keyed; see B55).

        ``last_main_entity_id`` is the main the player last took control of;
        ``timestamp`` defaults to the current ISO time. This is the *only* path
        that writes ``last_spotlight_at`` so the GM possessing a main can never
        falsely stamp a player.
        """
        from datetime import datetime, timezone

        updates: dict = {"last_main_entity_id": last_main_entity_id}
        updates["last_spotlight_at"] = timestamp or datetime.now(timezone.utc).isoformat()
        return self._repo.update_player(player_id, updates)

    def record_control(self, player_id: str, entity_id: str, stamp: bool = True) -> bool:
        """Handle a player taking control of an entity (B55).

        Stamps ``last_spotlight_at``/``last_main_entity_id`` only when the
        entity is one of the player's mains (agency edge ``main`` flag) — the
        spotlight signal is *taking control of a main*, not any body switch.
        The stamp is actor-keyed: it keys on the explicit ``player_id``, so a
        GM possessing/roaming as a main never reaches this path.

        ``stamp=False`` is that GM path, made explicit: the body is recorded (so
        the entity shows up in ``playerBodies`` and its map dot sizes up) and
        ``body_changed`` is broadcast, but **no** spotlight recency is stamped
        and no main flips active — recency belongs to the owning player's own
        switches.

        Broadcasts ``main_active`` via SSE in both directions (a main becoming
        active when taken, inactive when the player switches to a non-main).

        Returns True when the entity is a main (and was stamped).
        """
        from transversal.services.state_events import (
            broadcast_main_active,
            broadcast_body_changed,
            fire_state_sfx,
        )

        # Track the current body on every switch — main, support character, or a
        # GM's possessed GMC.
        _current_body[player_id] = entity_id

        # "Someone took control of this entity" — the state change, fired for
        # every switch and both audiences. What it *means* (a GM assuming a
        # hidden occupant, a player taking their main back) is a rule's business,
        # so a condition decides rather than this call: see [[B121]].
        fire_state_sfx(entity_id, "", "assumed", {})

        if not stamp:
            broadcast_body_changed(player_id, entity_id)
            return False

        is_main = self._repo.get_agency_main(player_id, entity_id)

        if is_main:
            self.set_spotlight(player_id, entity_id)
            _set_active_main(player_id, entity_id)
            broadcast_main_active(player_id, entity_id, True)
            return True

        # Player switched to a non-main (support character) — their previous
        # main is no longer active. Do not stamp spotlight.
        p = self._repo.get_player(player_id)
        if p is not None and p.last_main_entity_id:
            _set_active_main(player_id, None)
            broadcast_main_active(player_id, p.last_main_entity_id, False)
        return False

    def clear_control(self, player_id: str) -> None:
        """Forget the body a player was driving (they went to free-roam).

        Without this the last possessed entity would stay in ``playerBodies``
        forever, and its map dot would stay sized up after the GM let go.
        """
        if _current_body.pop(player_id, None) is not None:
            from transversal.services.state_events import broadcast_body_changed
            broadcast_body_changed(player_id, None)

    def revoke_sessions(self, player_id: str) -> int | None:
        """End every session that names ``player_id`` (SEC-3).

        A signed session cookie cannot be recalled, so revoking is an *epoch
        bump*: validation compares the cookie's epoch against this record, and
        every cookie issued under the old value stops being accepted on its next
        request. Returns the new epoch, or ``None`` when there is no such player.

        Deliberately does **not** delete the player: their characters are entities
        owned through ``agency`` edges, and removing the record would orphan them.
        Revoking ends access; deleting is a separate, explicit act.
        """
        player = self._repo.get_player(player_id)
        if not player:
            return None
        epoch = int(player.epoch) + 1
        self._repo.update_player(player_id, {"epoch": epoch})
        return epoch


# Global singleton
player_manager = PlayerManager()
