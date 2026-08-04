"""Session manager — in-memory session storage for multiplayer grouping.

Sessions group entities for a play session. The SSE bus already
supports session-scoped events; this service manages the session lifecycle.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field


@dataclass
class Session:
    id: str
    name: str
    gm_id: str = ""
    universe: str = "earth"
    entity_ids: set[str] = field(default_factory=set)
    player_entities: dict[str, str] = field(default_factory=dict)  # player_id → entity_id
    active: bool = True


class SessionManager:
    """In-memory session store. Replace with Redis for persistence."""

    def __init__(self):
        self._sessions: dict[str, Session] = {}

    def create(self, name: str, gm_id: str = "", universe: str = "earth") -> Session:
        sid = f"session-{uuid.uuid4().hex[:8]}"
        session = Session(id=sid, name=name, gm_id=gm_id, universe=universe)
        self._sessions[sid] = session
        return session

    def get(self, session_id: str) -> Session | None:
        return self._sessions.get(session_id)

    def join(self, session_id: str, entity_id: str, player_id: str = "") -> Session | None:
        session = self._sessions.get(session_id)
        if session:
            session.entity_ids.add(entity_id)
            if player_id:
                session.player_entities[player_id] = entity_id
        return session

    def leave(self, session_id: str, entity_id: str, player_id: str = "") -> Session | None:
        session = self._sessions.get(session_id)
        if session:
            session.entity_ids.discard(entity_id)
            if player_id and player_id in session.player_entities:
                del session.player_entities[player_id]
        return session

    def list_active(self) -> list[Session]:
        return [s for s in self._sessions.values() if s.active]

    def close(self, session_id: str) -> None:
        session = self._sessions.get(session_id)
        if session:
            session.active = False


# Global singleton
session_manager = SessionManager()
