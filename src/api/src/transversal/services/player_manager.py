"""Player management — ArangoDB-backed player identity and entity ownership.

Players are stored in the `players` collection (see ``domain.Player``).
Player→entity associations are `relationships` edges (type: `agency`), and are
resolved from the graph at read time rather than stored on the player document.
"""

from __future__ import annotations

import uuid

from transversal.db.repository import EntityRepository
from transversal.domain import Player


class PlayerManager:
    """ArangoDB-backed player store."""

    def __init__(self, repo: EntityRepository | None = None):
        self._repo = repo or EntityRepository()

    def create(self, name: str = "") -> Player:
        pid = f"player-{uuid.uuid4().hex[:6]}"
        return self._repo.create_player(pid, name=name or pid, role="player")

    def get(self, player_id: str) -> Player | None:
        return self._repo.get_player(player_id)

    def claim_entity(self, player_id: str, entity_id: str) -> bool:
        return self._repo.claim_entity(player_id, entity_id)

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


# Global singleton
player_manager = PlayerManager()
