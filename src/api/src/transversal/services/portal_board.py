"""The departure board: where a portal currently sends you ([[B323]]).

A portal used to ask *where to?* when it was fired — a ``choose`` in its effects,
which is what the whole [[B312]]–[[B322]] chain of defects was about. Instead the
board is **set when you arrive**: an ordinary rule at the airport (trigger
``on_location_change``, source ``Location``) sets this portal's destination, and
stepping through just goes.

**Edge-scoped, and not persistent** — the human's two decisions (2026-10-17):

* the value belongs to the *portal* (the ``_from → _to`` edge), not to the place,
  so two portals at one airport are two boards;
* it is session state, not content: nothing is written to the edge, so a restart
  forgets the board and play can never rewrite the world's data.

It **is** durable within a session — it lives on the server, so it survives a
page refresh and every client in the campaign shares it. That is the difference
between "not persistent" and "not durable": this design is the latter.

Scoped by campaign like every other piece of live state ([[B305]]). A read
outside a request names no campaign and gets nothing; a write outside one is
refused and logged, because a board nobody can read is worse than an honest
report. That is the same refusal ``roll_deferral._scope`` uses, and for the same
reason: "no campaign" must never mean "every campaign".
"""

from __future__ import annotations

import logging
from typing import Optional

from transversal.services.campaign_scope import current_campaign

logger = logging.getLogger("transversal.portal_board")

#: campaign → {portal edge key: destination location id}. The *only* copy — see
#: `clear_portal_destinations` for how one campaign forgets its board.
_boards: dict[str, dict[str, str]] = {}


def _scope(campaign: str | None = None) -> str:
    """The campaign to act under: the argument, else this context's scope."""
    return campaign or current_campaign()


def set_portal_destination(edge_key: str, location_id: str,
                           campaign: str | None = None) -> bool:
    """Point a portal at a place. ``False`` means no campaign named, so nothing was set.

    The caller reports that: the effect that set the board says *why* it did not
    take, rather than looking applied and doing nothing.
    """
    scope = _scope(campaign)
    if not scope:
        logger.warning(
            "set_portal_destination(%s) with no campaign — refusing to set a board "
            "nothing could read", edge_key,
        )
        return False
    _boards.setdefault(scope, {})[edge_key] = location_id
    logger.info("[portal board] %s -> %s (campaign %r)", edge_key, location_id, scope)
    return True


def get_portal_destination(edge_key: str, campaign: str | None = None) -> Optional[str]:
    """Where this portal currently sends you, or ``None`` (unset, or no campaign)."""
    scope = _scope(campaign)
    if not scope:
        return None
    return _boards.get(scope, {}).get(edge_key)


def clear_portal_destinations(campaign: str | None = None) -> int:
    """Forget one campaign's board; returns how many portals it held.

    No campaign is a no-op, never "every campaign's" — the same guard as the
    reads and writes above.
    """
    scope = _scope(campaign)
    if not scope:
        return 0
    return len(_boards.pop(scope, {}))
