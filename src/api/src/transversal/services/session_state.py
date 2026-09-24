"""Whether a session is running.

A *trigger* is a moment: `on_session_start` / `on_session_end` fire once and are
gone. Nothing held the answer to *"is a session running right now?"*, so a
condition could not ask it — and until this existed there was no way to author
"only while the table is playing" as opposed to "at the start" or "at the end".

Process state is the honest scope. The app serves one table, the session boundary
is already a global event, and arming state (`roll_deferral`) has the same
lifetime — so a row would add a stored truth that a crash could leave wrong, which
is worse than one a restart resets. A restart mid-session is the same situation as
a restart mid-roll: the table says so again.
"""

from __future__ import annotations

_active = False


def set_active(value: bool) -> None:
    """Record whether a session is running. Called by the session boundaries."""
    global _active
    _active = bool(value)


def is_active() -> bool:
    """Whether a session is running now."""
    return _active
