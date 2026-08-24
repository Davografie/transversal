"""Session manager — session storage for multiplayer grouping.

Sessions group entities for a play session. The SSE bus supports session-scoped
events; this service manages the session lifecycle.

Backed by Redis when reachable (so multiple API workers share session state);
falls back to in-memory storage when Redis is unavailable (single worker /
tests).
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field

from transversal.db.redis import get_redis_client


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
    """Session store. Redis-backed when available, in-memory otherwise."""

    _KEY_PREFIX = "session:"
    _ACTIVE_SET = "sessions:active"

    def __init__(self):
        self._redis = get_redis_client()
        self._sessions: dict[str, Session] = {}  # in-memory fallback

    # ── serialization ────────────────────────────────

    @staticmethod
    def _to_dict(s: Session) -> dict:
        return {
            "id": s.id,
            "name": s.name,
            "gm_id": s.gm_id,
            "universe": s.universe,
            "entity_ids": sorted(s.entity_ids),
            "player_entities": dict(s.player_entities),
            "active": s.active,
        }

    @staticmethod
    def _from_dict(d: dict) -> Session:
        return Session(
            id=d["id"],
            name=d.get("name", ""),
            gm_id=d.get("gm_id", ""),
            universe=d.get("universe", "earth"),
            entity_ids=set(d.get("entity_ids", [])),
            player_entities=dict(d.get("player_entities", {})),
            active=d.get("active", True),
        )

    # ── storage primitives ───────────────────────────

    def _get(self, session_id: str) -> Session | None:
        if self._redis is None:
            return self._sessions.get(session_id)
        raw = self._redis.get(self._KEY_PREFIX + session_id)
        return self._from_dict(json.loads(raw)) if raw else None

    def _put(self, s: Session) -> None:
        if self._redis is None:
            self._sessions[s.id] = s
            return
        pipe = self._redis.pipeline()
        pipe.set(self._KEY_PREFIX + s.id, json.dumps(self._to_dict(s)))
        if s.active:
            pipe.sadd(self._ACTIVE_SET, s.id)
        else:
            pipe.srem(self._ACTIVE_SET, s.id)
        try:
            pipe.execute()
        except Exception:
            pass

    # ── API ──────────────────────────────────────────

    def create(self, name: str, gm_id: str = "", universe: str = "earth") -> Session:
        sid = f"session-{uuid.uuid4().hex[:8]}"
        session = Session(id=sid, name=name, gm_id=gm_id, universe=universe)
        self._put(session)
        return session

    def get(self, session_id: str) -> Session | None:
        return self._get(session_id)

    def join(self, session_id: str, entity_id: str, player_id: str = "") -> Session | None:
        session = self._get(session_id)
        if session:
            session.entity_ids.add(entity_id)
            if player_id:
                session.player_entities[player_id] = entity_id
            self._put(session)
        return session

    def leave(self, session_id: str, entity_id: str, player_id: str = "") -> Session | None:
        session = self._get(session_id)
        if session:
            session.entity_ids.discard(entity_id)
            if player_id and player_id in session.player_entities:
                del session.player_entities[player_id]
            self._put(session)
        return session

    def list_active(self) -> list[Session]:
        if self._redis is None:
            return [s for s in self._sessions.values() if s.active]
        ids = self._redis.smembers(self._ACTIVE_SET)
        out: list[Session] = []
        for sid in ids:
            raw = self._redis.get(self._KEY_PREFIX + sid)
            if raw:
                out.append(self._from_dict(json.loads(raw)))
        return out

    def close(self, session_id: str) -> None:
        session = self._get(session_id)
        if session:
            session.active = False
            self._put(session)


# Global singleton
session_manager = SessionManager()
