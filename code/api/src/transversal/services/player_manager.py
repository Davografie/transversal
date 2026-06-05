"""Player management — persistent player identity and entity ownership."""

from dataclasses import dataclass, field
import uuid


@dataclass
class Player:
    id: str
    name: str = ""
    entity_ids: set[str] = field(default_factory=set)


class PlayerManager:
    """In-memory player store. Replace with ArangoDB collection for persistence."""

    def __init__(self):
        self._players: dict[str, Player] = {}

    def create(self, name: str = "") -> Player:
        pid = f"player-{uuid.uuid4().hex[:6]}"
        player = Player(id=pid, name=name or pid)
        self._players[pid] = player
        return player

    def get(self, player_id: str) -> Player | None:
        return self._players.get(player_id)

    def claim_entity(self, player_id: str, entity_id: str) -> bool:
        player = self._players.get(player_id)
        if player:
            player.entity_ids.add(entity_id)
            return True
        return False

    def release_entity(self, player_id: str, entity_id: str) -> bool:
        player = self._players.get(player_id)
        if player:
            player.entity_ids.discard(entity_id)
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


player_manager = PlayerManager()
