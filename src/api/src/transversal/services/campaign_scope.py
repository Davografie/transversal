"""The campaign scope — which campaign a piece of live state belongs to (B305).

A campaign **is** an ArangoDB database, and ``use_database()`` already resolves one
per request, so every *document* is isolated. Live state — sessions, the SSE bus,
the change log, the active-main maps — is not a document, and until now nothing in
it named a campaign. This module is the missing name.

Three rules, each of which is a failure mode it exists to prevent:

1. **The id is the fork's, not the database's.** A database name is an
   implementation detail of the router; the fork id is the registry's identity,
   unique and never reused. Anything *stored* (a Redis key, a session record, a
   change-log entry) is keyed by the fork id, so a database that is dropped and a
   name that is reused cannot inherit another campaign's state. Where there is no
   routing row — a probe database, a bare test database — the database name is the
   scope: still unique, and it keeps tests and probes working.
2. **No scope means no campaign, and that is not a guess.** ``current_campaign()``
   returns ``""`` rather than inventing one. The stores treat an empty scope as
   *deliver to nobody, and log it* — never as "everyone", which is how the
   cross-campaign broadcast this module exists to remove was spelled.
3. **A scope is captured where the work is created.** Background tasks and
   ``asyncio.run`` islands do not inherit a request's assumptions (the media work
   already learned this the expensive way), so ``capture_scope()`` records the
   database *and* the campaign at the point of scheduling and ``use_scope()``
   re-enters both inside the task.

The middleware sets this for **every** request, including one with no campaign
label — the apex really is a campaign (the playroom), and naming it explicitly is
what makes "no scope" mean "out of request" rather than "the default".
"""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

from transversal.db.arango import current_database, use_database

logger = logging.getLogger("transversal.campaign")

#: Set by the middleware for every request, and by ``use_scope`` for background
#: work. ``None`` means "nothing named a campaign", which is different from a
#: campaign whose id happens to be empty.
_explicit: ContextVar[str | None] = ContextVar("transversal_campaign", default=None)

#: database name → campaign id. One registry lookup per database per process; a
#: fork's id does not change, and a stale entry for a dropped database is harmless
#: (it names keys nobody will read again).
_cache: dict[str, str] = {}


def campaign_for_database(database: str) -> str:
    """The campaign id for ``database``: its fork id, else the database name.

    Best-effort by design. A registry that cannot be reached must not break a
    request or a migration — the database name is a correct scope, just a less
    durable one, so the failure is logged at debug and swallowed.
    """
    if not database:
        return ""
    cached = _cache.get(database)
    if cached is not None:
        return cached

    resolved = database
    try:
        from transversal.db.registry_repository import RegistryRepository

        fork = RegistryRepository().find_fork_by_database(database)
        if fork is not None and fork.id:
            resolved = fork.id
    except Exception:
        logger.debug(
            "no registry row for %s; scoping by database name", database, exc_info=True
        )

    _cache[database] = resolved
    return resolved


def current_campaign() -> str:
    """The campaign this context acts on, or ``""`` when nothing named one.

    An explicit scope wins. Otherwise a *database* scope is enough — that is what
    ``use_database()`` in a migration, the operator CLI or a test provides, and the
    database is a legitimate campaign name. With neither, the answer is empty.
    """
    explicit = _explicit.get()
    if explicit:
        return explicit
    database = current_database()
    if database:
        return campaign_for_database(database)
    return ""


def default_database() -> str:
    """The process default database — the one ``get_db()`` uses out of request."""
    return os.getenv("ARANGO_DATABASE", "transversal")


@contextmanager
def use_campaign(campaign: str):
    """Name the campaign for the duration of the block."""
    token = _explicit.set(campaign or "")
    try:
        yield
    finally:
        _explicit.reset(token)


@dataclass(frozen=True)
class Scope:
    """A captured scope: what background work needs to act where it was created."""

    database: str | None
    campaign: str


def capture_scope() -> Scope:
    """Record the current database and campaign, to hand to work that runs later."""
    return Scope(database=current_database(), campaign=current_campaign())


@contextmanager
def use_scope(scope: "Scope"):
    """Re-enter a scope captured by :func:`capture_scope`."""
    if scope.database:
        with use_database(scope.database), use_campaign(scope.campaign):
            yield
    else:
        with use_campaign(scope.campaign):
            yield


def reset_campaign_cache() -> None:
    """Drop the database → campaign cache. For tests that point the registry elsewhere."""
    _cache.clear()
