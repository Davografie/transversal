"""Player presence — which players are considered online.

A player is "online" while they have an active SSE connection, and for a grace
window after the last connection drops (a phone/laptop sleeping mid-session must
not make them vanish from the troupe overview). In-memory (single-worker).

**Presence belongs to a campaign** ([[B305]]). Both registries used to be keyed by
player alone, so one campaign's connected players were listed as online in
another; the campaign is an opaque id (a fork id, or a database name where there
is no routing row — see ``services/campaign_scope``).

``mark_online``/``mark_offline`` return True only when the player's *visible*
online state flips, so callers broadcast a presence change only then.

With no campaign the store answers **empty**: "no campaign" is not "everyone",
which is how the old global registry leaked across campaigns.
"""

from __future__ import annotations

import logging
import time

from transversal.services.campaign_scope import current_campaign

logger = logging.getLogger("transversal.presence")

GRACE_SECONDS = 10 * 60  # how long a player stays "online" after their last disconnect

#: (campaign, player_id) → active SSE connection count
_online: dict[tuple[str, str], int] = {}
#: (campaign, player_id) → last moment a connection existed
_last_seen: dict[tuple[str, str], float] = {}


def _now() -> float:
    return time.time()


def _scope(campaign: str | None = None) -> str:
    """The campaign to act under: the argument, else this context's scope.

    Empty is a refusal, not a wildcard ([[B305]]).
    """
    return campaign or current_campaign()


def _in_grace(campaign: str, player_id: str, now: float) -> bool:
    ts = _last_seen.get((campaign, player_id))
    return ts is not None and (now - ts) <= GRACE_SECONDS


def mark_online(player_id: str, campaign: str | None = None) -> bool:
    """Record a connection; return True when the player just became visible online."""
    scope = _scope(campaign)
    if not scope:
        logger.debug(
            "mark_online(%s) with no campaign — not recording presence", player_id
        )
        return False
    was_online = is_online(player_id, scope)
    _online[(scope, player_id)] = _online.get((scope, player_id), 0) + 1
    _last_seen[(scope, player_id)] = _now()
    return not was_online


def mark_offline(player_id: str, campaign: str | None = None) -> bool:
    """Release a connection. The grace window keeps them online, so never a flip."""
    scope = _scope(campaign)
    if not scope:
        logger.debug(
            "mark_offline(%s) with no campaign — not releasing presence", player_id
        )
        return False
    key = (scope, player_id)
    n = _online.get(key, 0) - 1
    if n <= 0:
        _online.pop(key, None)
        _last_seen[key] = _now()  # grace starts from the disconnect
    else:
        _online[key] = n
    return False


def list_online_players(campaign: str | None = None) -> list[str]:
    """Player ids *in this campaign* with an active connection or in the grace window."""
    scope = _scope(campaign)
    if not scope:
        logger.warning(
            "list_online_players() with no campaign — returning nothing rather than "
            "every campaign's players"
        )
        return []
    now = _now()
    ids = {pid for (owner, pid) in _online if owner == scope}
    for owner, pid in _last_seen:
        if owner == scope and _in_grace(scope, pid, now):
            ids.add(pid)
    return list(ids)


def is_online(player_id: str, campaign: str | None = None) -> bool:
    scope = _scope(campaign)
    if not scope:
        logger.debug("is_online(%s) with no campaign — answering False", player_id)
        return False
    return _online.get((scope, player_id), 0) > 0 or _in_grace(scope, player_id, _now())
