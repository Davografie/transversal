"""Session manager — session storage for multiplayer grouping.

Sessions group entities for a play session. The SSE bus supports session-scoped
events; this service manages the session lifecycle.

Backed by Redis when reachable (so multiple API workers share session state);
falls back to in-memory storage when Redis is unavailable (single worker /
tests).

**A session belongs to a campaign** ([[B305]]). Both halves of every key name it —
``session:<campaign>:<id>`` and ``sessions:active:<campaign>`` — because before this
the deployment kept **one** namespace: ``list_active()`` returned every campaign's
sessions, and 24 call sites fanned events out to all of them. The campaign is an
opaque id (a fork id, or a database name where there is no routing row — see
``services/campaign_scope``).

Two deliberate choices:

- **``list_active(campaign)`` takes no default.** Removing the zero-argument form is
  the mechanism that finds every caller at review time, and it stops the next
  publisher from re-introducing "all campaigns" by omission. The other methods
  default to ``current_campaign()`` — they run in request scope — and refuse an empty
  campaign rather than guess.
- **One release of a compatibility read.** Sessions written before the scoping carry
  no campaign, so a read for the *default* campaign also consults the legacy key and
  the legacy active set. The fallback is read-only and never crosses campaigns: a
  non-default campaign cannot see them. The migration script renames the rest, and the
  fallback is removed in the release after ([[Campaign-Scoped Transient State Plan]] §6).
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field

from transversal.db.redis import get_redis_client
from transversal.services.campaign_scope import current_campaign

logger = logging.getLogger("transversal.sessions")


@dataclass
class Session:
    id: str
    name: str
    gm_id: str = ""
    universe: str = "earth"
    #: Which campaign this session belongs to ([[B305]]). Required for storage; the
    #: dataclass default exists only so older serialised records still load.
    campaign: str = ""
    entity_ids: set[str] = field(default_factory=set)
    player_entities: dict[str, str] = field(default_factory=dict)  # player_id → entity_id
    active: bool = True
    in_session: bool = False  # the play period has started (Start/End toggle)


def _default_campaign() -> str:
    """The campaign the legacy (unscoped) records belong to — the playroom."""
    from transversal.services.campaign_scope import campaign_for_database, default_database

    return campaign_for_database(default_database())


class SessionManager:
    """Session store. Redis-backed when available, in-memory otherwise."""

    _KEY = "session:{}:{}"
    _LEGACY_KEY = "session:{}"
    _ACTIVE = "sessions:active:{}"
    _LEGACY_ACTIVE = "sessions:active"

    def __init__(self):
        self._redis = get_redis_client()
        self._sessions: dict[tuple[str, str], Session] = {}  # (campaign, id) → Session

    # ── keys ─────────────────────────────────────────

    @staticmethod
    def _scope(campaign: str | None) -> str:
        """The campaign to act under: the argument, else this request's scope.

        Empty is a refusal, not a wildcard — the bug this whole module is being
        fixed for was what "no campaign" used to mean.
        """
        if campaign:
            return campaign
        resolved = current_campaign()
        if not resolved:
            raise ValueError(
                "a session operation needs a campaign: none was given and this "
                "context names none (use capture_scope()/use_scope() for background work)"
            )
        return resolved

    @classmethod
    def _key(cls, campaign: str, session_id: str) -> str:
        return cls._KEY.format(campaign, session_id)

    @classmethod
    def _active_key(cls, campaign: str) -> str:
        return cls._ACTIVE.format(campaign)

    @classmethod
    def _legacy_readable(cls, campaign: str) -> bool:
        return campaign == _default_campaign()

    # ── serialization ────────────────────────────────

    @staticmethod
    def _to_dict(s: Session) -> dict:
        return {
            "id": s.id,
            "name": s.name,
            "gm_id": s.gm_id,
            "universe": s.universe,
            "campaign": s.campaign,
            "entity_ids": sorted(s.entity_ids),
            "player_entities": dict(s.player_entities),
            "active": s.active,
            "in_session": s.in_session,
        }

    @staticmethod
    def _from_dict(d: dict) -> Session:
        return Session(
            id=d["id"],
            name=d.get("name", ""),
            gm_id=d.get("gm_id", ""),
            universe=d.get("universe", "earth"),
            campaign=d.get("campaign", ""),
            entity_ids=set(d.get("entity_ids", [])),
            player_entities=dict(d.get("player_entities", {})),
            active=d.get("active", True),
            in_session=d.get("in_session", False),
        )

    # ── storage primitives ───────────────────────────

    def _read(self, key: str) -> str | None:
        if self._redis is None:
            return None
        return self._redis.get(key)

    def _get(self, session_id: str, campaign: str) -> Session | None:
        if self._redis is None:
            return self._sessions.get((campaign, session_id))
        raw = self._read(self._key(campaign, session_id))
        if raw is None and self._legacy_readable(campaign):
            # Written before the scoping existed; readable by the default campaign only.
            raw = self._read(self._LEGACY_KEY.format(session_id))
        if not raw:
            return None
        session = self._from_dict(json.loads(raw))
        if not session.campaign:
            # A record from before the scoping carries no campaign. It adopts the one it
            # was read under, **or a later save writes it to `session::<id>`** — a key no
            # campaign ever lists, which silently loses the session on its next update.
            session.campaign = campaign
        return session

    def _put(self, s: Session) -> None:
        if self._redis is None:
            self._sessions[(s.campaign, s.id)] = s
            return
        pipe = self._redis.pipeline()
        pipe.set(self._key(s.campaign, s.id), json.dumps(self._to_dict(s)))
        if s.active:
            pipe.sadd(self._active_key(s.campaign), s.id)
        else:
            pipe.srem(self._active_key(s.campaign), s.id)
        try:
            pipe.execute()
        except Exception:
            pass

    # ── API ──────────────────────────────────────────

    def create(
        self,
        name: str,
        gm_id: str = "",
        universe: str = "earth",
        *,
        campaign: str | None = None,
    ) -> Session:
        scope = self._scope(campaign)
        sid = f"session-{uuid.uuid4().hex[:8]}"
        session = Session(
            id=sid, name=name, gm_id=gm_id, universe=universe, campaign=scope
        )
        self._put(session)
        return session

    def get(self, session_id: str, *, campaign: str | None = None) -> Session | None:
        return self._get(session_id, self._scope(campaign))

    def join(
        self,
        session_id: str,
        entity_id: str,
        player_id: str = "",
        *,
        campaign: str | None = None,
    ) -> Session | None:
        session = self._get(session_id, self._scope(campaign))
        if session:
            session.entity_ids.add(entity_id)
            if player_id:
                session.player_entities[player_id] = entity_id
            self._put(session)
        return session

    def leave(
        self,
        session_id: str,
        entity_id: str,
        player_id: str = "",
        *,
        campaign: str | None = None,
    ) -> Session | None:
        session = self._get(session_id, self._scope(campaign))
        if session:
            session.entity_ids.discard(entity_id)
            if player_id and player_id in session.player_entities:
                del session.player_entities[player_id]
            self._put(session)
        return session

    def list_active(self, campaign: str | None = None) -> list[Session]:
        """This campaign's active sessions — never every campaign's.

        ``None`` means *the scope this code is running in*, resolved by
        ``current_campaign()``; with no scope the answer is an empty list, so a caller
        that forgets to name a campaign gets silence rather than everyone's sessions
        ([[B305]]).

        The plan for this change wanted the argument to have **no** default, so that the
        compiler would find all 24 fan-out sites. Defaulting to the established scope
        achieves the same end more safely: the sites are not merely found, they are
        correct without being touched, and "all campaigns" is unreachable by omission.
        The two mechanisms that remain are the empty-scope guard here and
        :meth:`EventBus.publish`'s refusal to send an unscoped event.
        """
        scope = campaign or current_campaign()
        if not scope:
            logger.warning(
                "list_active() with no campaign — returning nothing rather than "
                "every campaign's sessions"
            )
            return []
        if self._redis is None:
            return [
                s
                for (owner, _), s in self._sessions.items()
                if owner == scope and s.active
            ]

        ids = set(self._redis.smembers(self._active_key(scope)))
        if self._legacy_readable(scope):
            # Read-only compatibility: unscoped records are this campaign's, never
            # another's. Deduplicated, so a session the new code has already re-saved
            # is not reported twice.
            ids |= set(self._redis.smembers(self._LEGACY_ACTIVE))

        out: dict[str, Session] = {}
        for sid in ids:
            session = self._get(sid, scope)
            if session is not None and session.active:
                out[session.id] = session
        return list(out.values())

    def close(self, session_id: str, *, campaign: str | None = None) -> None:
        scope = self._scope(campaign)
        session = self._get(session_id, scope)
        if not session:
            return
        session.active = False
        self._put(session)
        if self._redis is not None and self._legacy_readable(scope):
            # A compatibility record must not keep the closed session in the legacy
            # active set, or it would still be listed as live.
            try:
                pipe = self._redis.pipeline()
                pipe.srem(self._LEGACY_ACTIVE, session_id)
                pipe.delete(self._LEGACY_KEY.format(session_id))
                pipe.execute()
            except Exception:
                pass

    def set_in_session(
        self, session_id: str, in_session: bool, *, campaign: str | None = None
    ) -> Session | None:
        """Toggle whether the play period is in progress (Start/End boundary).

        Independent of ``active`` (SSE/join membership): a session stays live
        and receiving events while ``in_session`` is False, so players can still
        do session setup between sessions.
        """
        session = self._get(session_id, self._scope(campaign))
        if session:
            session.in_session = in_session
            self._put(session)
        return session


# Global singleton
session_manager = SessionManager()
