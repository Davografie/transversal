"""Player presence — which players currently have an active SSE connection.

In-memory (single-worker), ref-counted so a character switch — which tears down
one SSE connection and opens another for the same player — never transiently
marks them offline. ``mark_online``/``mark_offline`` return True only when the
player's online state actually flips, so callers can broadcast a presence change.
"""

from __future__ import annotations

_online: dict[str, int] = {}  # player_id → active SSE connection count


def mark_online(player_id: str) -> bool:
    """Record a connection; return True when the player just came online."""
    n = _online.get(player_id, 0) + 1
    _online[player_id] = n
    return n == 1


def mark_offline(player_id: str) -> bool:
    """Release a connection; return True when the player just went offline."""
    n = _online.get(player_id, 0) - 1
    if n <= 0:
        _online.pop(player_id, None)
        return True
    _online[player_id] = n
    return False


def list_online_players() -> list[str]:
    """Player ids with at least one active connection."""
    return list(_online.keys())


def is_online(player_id: str) -> bool:
    return _online.get(player_id, 0) > 0
