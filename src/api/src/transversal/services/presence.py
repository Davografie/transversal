"""Player presence — which players are considered online.

A player is "online" while they have an active SSE connection, and for a grace
window after the last connection drops (a phone/laptop sleeping mid-session must
not make them vanish from the troupe overview). In-memory (single-worker).

``mark_online``/``mark_offline`` return True only when the player's *visible*
online state flips, so callers broadcast a presence change only then.
"""

from __future__ import annotations

import time

GRACE_SECONDS = 10 * 60  # how long a player stays "online" after their last disconnect

_online: dict[str, int] = {}       # player_id → active SSE connection count
_last_seen: dict[str, float] = {}  # player_id → last moment a connection existed


def _now() -> float:
    return time.time()


def _in_grace(player_id: str, now: float) -> bool:
    ts = _last_seen.get(player_id)
    return ts is not None and (now - ts) <= GRACE_SECONDS


def mark_online(player_id: str) -> bool:
    """Record a connection; return True when the player just became visible online."""
    was_online = is_online(player_id)
    _online[player_id] = _online.get(player_id, 0) + 1
    _last_seen[player_id] = _now()
    return not was_online


def mark_offline(player_id: str) -> bool:
    """Release a connection. The grace window keeps them online, so never a flip."""
    n = _online.get(player_id, 0) - 1
    if n <= 0:
        _online.pop(player_id, None)
        _last_seen[player_id] = _now()  # grace starts from the disconnect
    else:
        _online[player_id] = n
    return False


def list_online_players() -> list[str]:
    """Player ids with an active connection or within the grace window."""
    now = _now()
    ids = set(_online.keys())
    for player_id in _last_seen:
        if _in_grace(player_id, now):
            ids.add(player_id)
    return list(ids)


def is_online(player_id: str) -> bool:
    return _online.get(player_id, 0) > 0 or _in_grace(player_id, _now())
