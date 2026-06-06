"""Player management — persistent player identity and entity ownership."""

from dataclasses import dataclass, field
import json
import os
import uuid


PLAYERS_FILE = os.environ.get("PLAYERS_FILE", "/app/data/players.json")


@dataclass
class Player:
    id: str
    name: str = ""
    entity_ids: set[str] = field(default_factory=set)
    role: str = "player"  # "player" or "architect"


class PlayerManager:
    """JSON-file-backed player store."""

    def __init__(self):
        self._players: dict[str, Player] = {}
        self._load()

    def _load(self):
        try:
            with open(PLAYERS_FILE) as f:
                data = json.load(f)
            for d in data:
                p = Player(
                    id=d["id"],
                    name=d.get("name", ""),
                    entity_ids=set(d.get("entity_ids", [])),
                    role=d.get("role", "player"),
                )
                self._players[p.id] = p
        except (FileNotFoundError, json.JSONDecodeError):
            pass

    def _save(self):
        os.makedirs(os.path.dirname(PLAYERS_FILE), exist_ok=True)
        data = [
            {
                "id": p.id,
                "name": p.name,
                "entity_ids": sorted(p.entity_ids),
                "role": p.role,
            }
            for p in self._players.values()
        ]
        with open(PLAYERS_FILE, "w") as f:
            json.dump(data, f, indent=2)

    def create(self, name: str = "") -> Player:
        pid = f"player-{uuid.uuid4().hex[:6]}"
        player = Player(id=pid, name=name or pid)
        self._players[pid] = player
        self._save()
        return player

    def get(self, player_id: str) -> Player | None:
        return self._players.get(player_id)

    def claim_entity(self, player_id: str, entity_id: str) -> bool:
        player = self._players.get(player_id)
        if player:
            player.entity_ids.add(entity_id)
            self._save()
            return True
        return False

    def release_entity(self, player_id: str, entity_id: str) -> bool:
        player = self._players.get(player_id)
        if player:
            player.entity_ids.discard(entity_id)
            self._save()
            return True
        return False

    def get_player_entities(self, player_id: str) -> set[str]:
        player = self._players.get(player_id)
        return player.entity_ids if player else set()

    def find_by_name(self, name: str) -> Player | None:
        name_lower = name.lower().strip()
        for p in self._players.values():
            if p.name.lower().strip() == name_lower:
                return p
        return None

    def list_all(self) -> list[Player]:
        return list(self._players.values())

    def search(self, query: str) -> list[Player]:
        """Case-insensitive substring search on player names."""
        q = query.lower().strip()
        if not q:
            return []
        return [p for p in self._players.values() if q in p.name.lower()]

    def set_role(self, player_id: str, role: str) -> bool:
        player = self._players.get(player_id)
        if player and role in ("player", "architect"):
            player.role = role
            self._save()
            return True
        return False


player_manager = PlayerManager()
