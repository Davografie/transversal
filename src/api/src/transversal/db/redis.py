"""Redis helpers — cross-worker SSE fan-out and shared session state.

Redis is optional: when unreachable the app degrades to in-process behaviour
(single worker, in-memory sessions). Multi-worker requires ``REDIS_URL`` to be
reachable and consistent across workers.
"""

from __future__ import annotations

import os
from typing import Optional

import redis as redis_sync

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

_client: Optional[redis_sync.Redis] = None
_client_checked = False


def get_redis_client() -> Optional[redis_sync.Redis]:
    """Return a cached sync Redis client, or ``None`` when Redis is unreachable.

    The reachability check runs once and is memoized; a down-at-startup Redis
    means the process stays in fallback mode until restarted.
    """
    global _client, _client_checked
    if _client_checked:
        return _client
    _client_checked = True
    try:
        c = redis_sync.Redis.from_url(
            REDIS_URL, decode_responses=True, socket_connect_timeout=1, socket_timeout=1
        )
        c.ping()
        _client = c
    except Exception:
        _client = None
    return _client
