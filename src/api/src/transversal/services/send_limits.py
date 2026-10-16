"""Send rate limits for the account email links (B255).

One credential, two abuse shapes. The registry is the only place mapping a recovery
address to an account, so an uncapped send is both (a) a way to make the server post
mail to any address an attacker names, and (b) an enumeration oracle if the *answer*
differs when the address has an account. The callers keep their answers identical;
this caps the sending ([[Identity Programme]] §5.4).

A **fixed window** is deliberate: the requirement is "capped per address and
overall", not a smooth rate. Redis holds the counters when it is reachable, so the
cap is per deployment rather than per worker; without it the process keeps its own,
which is the same degradation the SSE bus and the session manager already accept.
"""

from __future__ import annotations

import os
import time

from transversal.db.redis import get_redis_client

#: Sends to one address inside the window. Three is enough for a mistyped link to be
#: re-requested once or twice without becoming a way to flood a mailbox.
ADDRESS_LIMIT = 3
#: The window, in seconds.
WINDOW_SECONDS = 15 * 60
#: Every send from this deployment inside the window, whatever the address.
TOTAL_LIMIT = 60

_memory: dict[str, tuple[float, int]] = {}


def _int_env(name: str, default: int) -> int:
    raw = (os.getenv(name, "") or "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _limits() -> tuple[int, int, int]:
    """Read per call, so a deployment (or a test) can set them without a restart."""
    return (
        _int_env("MAIL_MAX_PER_ADDRESS", ADDRESS_LIMIT),
        _int_env("MAIL_RATE_WINDOW_SECONDS", WINDOW_SECONDS),
        _int_env("MAIL_MAX_PER_WINDOW", TOTAL_LIMIT),
    )


def _bump_memory(key: str, window: int, now: float) -> int:
    start, count = _memory.get(key, (now, 0))
    if now - start >= window:
        start, count = now, 0
    count += 1
    _memory[key] = (start, count)
    return count


def _bump_redis(client, key: str, window: int) -> int:
    count = client.incr(key)
    if count == 1:
        client.expire(key, window)
    return int(count)


def _bump(key: str, window: int, now: float) -> int:
    client = get_redis_client()
    if client is not None:
        try:
            return _bump_redis(client, key, window)
        except Exception:
            # Redis went away mid-flight; fall back rather than refuse all mail.
            pass
    return _bump_memory(key, window, now)


def allow_send(address: str, *, now: float | None = None) -> bool:
    """True when this send is within both the per-address and the overall cap."""
    address_limit, window, total_limit = _limits()
    now = time.time() if now is None else now
    key = (address or "").strip().lower() or "unknown"
    if _bump(f"tv2:mail:addr:{key}", window, now) > address_limit:
        return False
    if _bump("tv2:mail:all", window, now) > total_limit:
        return False
    return True


def reset() -> None:
    """Forget the in-process counters. For tests."""
    _memory.clear()
