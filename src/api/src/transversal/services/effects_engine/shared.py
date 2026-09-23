"""Shared — split out of src/api/src/transversal/services/effects_engine.py."""

from __future__ import annotations

import logging
from contextvars import ContextVar


log = logging.getLogger("transversal.sfx")

#: The rules whose effects are being applied right now, on **this** call chain,
#: as ``(sfx_id, change)`` frames — the loop guard.
#:
#: A rule that is about to apply *for a change it is already handling* is
#: re-entering itself: its own effect caused another event of the thing it is
#: acting on. Rather than recurse (or silently refuse, which is what the old
#: `(entity, event_type)` guard did), the round is offered to the table.
#:
#: Two properties matter. It is a **stack**, so a frame is still present while
#: the effects it caused are being applied — exactly the window a loop recurses
#: in — and it is **per-request** (a ``ContextVar``), so two concurrent requests
#: cannot see or drop each other's chains. The key includes the *change*, not
#: just the rule, so a rule legitimately acting on a second, different thing (an
#: agenda rule filling its parent) is a new application rather than a loop.
RULE_CHAIN: ContextVar[tuple] = ContextVar("sfx_rule_chain", default=())
