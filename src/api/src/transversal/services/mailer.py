"""Outbound mail (B255) — the account email links, and nothing else.

Mail in this app has exactly one job: deliver a single-use link that **verifies an
address** or **signs an account in**. Players never receive mail ([[Identity
Programme]] §5.8), so there is no notification, digest or per-player verification
surface to build.

Transport is chosen by ``MAIL_TRANSPORT``:

- ``console`` (the default): the message is logged, which is how the link is
  reachable on a loopback dev box with no SMTP server.
- ``smtp``: any provider, configured from the environment. Standard library only
  (``smtplib``), because SMTP is the one dependency the design was willing to
  take and it needs no package to take it.
- anything else: **not built**, and it raises rather than silently dropping what is
  the only credential this tier has.

Sends are capped by :mod:`transversal.services.send_limits` before they reach here —
a mail credential in a registry that maps addresses to accounts is otherwise both a
spam relay and an enumeration oracle ([[Identity Programme]] §5.4).
"""

from __future__ import annotations

import logging
import os
import smtplib
from email.message import EmailMessage
from typing import Protocol

logger = logging.getLogger("transversal.mailer")

TRANSPORT_CONSOLE = "console"
TRANSPORT_SMTP = "smtp"


class Mailer(Protocol):
    def send(self, to: str, subject: str, body: str) -> None: ...


class MailNotConfiguredError(RuntimeError):
    """Raised when no real transport is configured. Fail loudly, not silently."""


class ConsoleMailer:
    """Logs the message instead of sending it. Dev only, by construction."""

    def send(self, to: str, subject: str, body: str) -> None:
        logger.warning("[mail:console] to=%s subject=%s\n%s", to, subject, body)


def _env_flag(name: str, default: bool) -> bool:
    raw = (os.getenv(name, "") or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


class SMTPMailer:
    """Sends over SMTP. Configured entirely from the environment.

    Requires ``SMTP_HOST`` and ``SMTP_FROM``; ``SMTP_PORT`` defaults to 587 (465 when
    ``SMTP_SSL`` is set), ``SMTP_STARTTLS`` defaults to on, and ``SMTP_USERNAME`` /
    ``SMTP_PASSWORD`` are only used when a username is given — an unauthenticated
    relay is a real configuration, not an error.
    """

    def __init__(
        self,
        *,
        host: str,
        sender: str,
        port: int = 587,
        username: str = "",
        password: str = "",
        starttls: bool = True,
        use_ssl: bool = False,
        timeout: float = 10.0,
    ):
        self.host = host
        self.sender = sender
        self.port = port
        self.username = username
        self.password = password
        self.starttls = starttls
        self.use_ssl = use_ssl
        self.timeout = timeout

    @classmethod
    def from_env(cls) -> "SMTPMailer":
        host = (os.getenv("SMTP_HOST", "") or "").strip()
        sender = (os.getenv("SMTP_FROM", "") or "").strip()
        if not host or not sender:
            raise MailNotConfiguredError(
                "MAIL_TRANSPORT=smtp needs SMTP_HOST and SMTP_FROM"
            )
        use_ssl = _env_flag("SMTP_SSL", False)
        raw_port = (os.getenv("SMTP_PORT", "") or "").strip()
        try:
            port = int(raw_port) if raw_port else (465 if use_ssl else 587)
        except ValueError:
            raise MailNotConfiguredError(f"SMTP_PORT={raw_port!r} is not a number")
        return cls(
            host=host,
            sender=sender,
            port=port,
            username=(os.getenv("SMTP_USERNAME", "") or "").strip(),
            password=os.getenv("SMTP_PASSWORD", "") or "",
            starttls=_env_flag("SMTP_STARTTLS", True),
            use_ssl=use_ssl,
        )

    def _connect(self):
        if self.use_ssl:
            return smtplib.SMTP_SSL(self.host, self.port, timeout=self.timeout)
        return smtplib.SMTP(self.host, self.port, timeout=self.timeout)

    def send(self, to: str, subject: str, body: str) -> None:
        message = EmailMessage()
        message["From"] = self.sender
        message["To"] = to
        message["Subject"] = subject
        message.set_content(body)

        with self._connect() as server:
            if self.starttls and not self.use_ssl:
                server.starttls()
            if self.username:
                server.login(self.username, self.password)
            server.send_message(message)
        logger.info("[mail:smtp] sent to=%s subject=%s", to, subject)


def get_mailer() -> Mailer:
    """The configured transport. Unknown/absent values fail closed."""
    transport = (os.getenv("MAIL_TRANSPORT", "") or TRANSPORT_CONSOLE).strip().lower()
    if transport == TRANSPORT_CONSOLE:
        return ConsoleMailer()
    if transport == TRANSPORT_SMTP:
        return SMTPMailer.from_env()
    raise MailNotConfiguredError(
        f"MAIL_TRANSPORT={transport!r} is not implemented; "
        f"only {TRANSPORT_CONSOLE!r} and {TRANSPORT_SMTP!r} are available"
    )
