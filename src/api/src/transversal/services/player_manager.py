"""Player management — ArangoDB-backed player identity and entity ownership.

Players are stored in the `players` collection.
Player→entity associations are `relationships` edges (type: `agency`).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from transversal.db.repository import EntityRepository


@dataclass
class Player:
    id: str
    name: str = ""
    entity_ids: set[str] = field(default_factory=set)
    role: str = "player"  # "player" or "architect"


class PlayerManager:
    """ArangoDB-backed player store."""

    def __init__(self, repo: EntityRepository | None = None):
        self._repo = repo or EntityRepository()

    def create(self, name: str = "") -> Player:
        pid = f"player-{uuid.uuid4().hex[:6]}"
        self._repo.create_player(pid, name=name or pid, role="player")
        return Player(id=pid, name=name or pid, role="player")

    def get(self, player_id: str) -> Player | None:
        doc = self._repo.get_player(player_id)
        if not doc:
            return None
        entity_ids = set(self._repo.get_player_entities(player_id))
        return Player(
            id=doc["_key"],
            name=doc.get("name", ""),
            entity_ids=entity_ids,
            role=doc.get("role", "player"),
        )

    def claim_entity(self, player_id: str, entity_id: str) -> bool:
        return self._repo.claim_entity(player_id, entity_id)

    def release_entity(self, player_id: str, entity_id: str) -> bool:
        return self._repo.release_entity(player_id, entity_id)

    def get_player_entities(self, player_id: str) -> set[str]:
        return set(self._repo.get_player_entities(player_id))

    def find_by_name(self, name: str) -> Player | None:
        doc = self._repo.find_player_by_name(name)
        if not doc:
            return None
        return self._to_player(doc)

    def list_all(self) -> list[Player]:
        return [self._to_player(d) for d in self._repo.list_players()]

    def search(self, query: str) -> list[Player]:
        return [self._to_player(d) for d in self._repo.search_players(query)]

    def set_role(self, player_id: str, role: str) -> bool:
        return self._repo.update_player(player_id, {"role": role})

    def _to_player(self, doc: dict) -> Player:
        pid = doc["_key"]
        entity_ids = set(self._repo.get_player_entities(pid))
        return Player(
            id=pid,
            name=doc.get("name", ""),
            entity_ids=entity_ids,
            role=doc.get("role", "player"),
        )


# Global singleton
player_manager = PlayerManager()
