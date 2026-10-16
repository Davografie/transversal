"""Outbound mail (B255) — the account email links, and nothing else.

Mail in this app has exactly one job: deliver a single-use link that **verifies an
address** or **signs an account in**. Players never receive mail ([[Identity
Programme]] §5.8), so there is no notification, digest or per-player verification
surface to build.

Transport is chosen by ``MAIL_TRANSPORT``:

- ``console`` (the default): the message is logged, which is how the link is
  reachable on a loopback dev box with no SMTP server.
- anything else: **not built**, and it raises rather than silently dropping what is
  the only credential this tier has. SMTP is a deliberate later addition — one
  secret, one dependency ([[Identity Programme]] §5.8).
"""

from __future__ import annotations

import logging
import os
from typing import Protocol

logger = logging.getLogger("transversal.mailer")

#: The one transport that exists. Named so a deployment can say so out loud.
TRANSPORT_CONSOLE = "console"


class Mailer(Protocol):
    def send(self, to: str, subject: str, body: str) -> None: ...


class MailNotConfiguredError(RuntimeError):
    """Raised when no real transport is configured. Fail loudly, not silently."""


class ConsoleMailer:
    """Logs the message instead of sending it. Dev only, by construction."""

    def send(self, to: str, subject: str, body: str) -> None:
        logger.warning(
            "[mail:console] to=%s subject=%s\n%s", to, subject, body
        )


def get_mailer() -> Mailer:
    """The configured transport. Unknown/absent values fail closed."""
    transport = (os.getenv("MAIL_TRANSPORT", "") or TRANSPORT_CONSOLE).strip().lower()
    if transport == TRANSPORT_CONSOLE:
        return ConsoleMailer()
    raise MailNotConfiguredError(
        f"MAIL_TRANSPORT={transport!r} is not implemented; "
        f"only {TRANSPORT_CONSOLE!r} is available"
    )
