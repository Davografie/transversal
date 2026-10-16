"""The tenancy registry database (B255) — its own connection and bootstrap.

The registry is the only place that maps an **account** to the **forks** it owns and
to its edit rights on the global multiverse. It is deliberately **not** reachable
through :func:`transversal.db.arango.get_db`: that path unconditionally creates all
20 campaign collections and their indexes on first connect, so pointing it at the
registry would litter the tenancy table with a campaign's schema. This module owns a
small, explicit schema of its own instead.

Collections:

- ``accounts``       — one row per person who owns forks. The email is verified at
  enrolment, because the recovery address *is* the credential
  ([[Identity Programme]] §5.3), so an unverified one is a way in.
- ``campaigns``      — the routing table: account → the fork's database, plus what
  kind of tenant it is. This is also the switcher's data source.
- ``account_tokens`` — liveness for the single-use, short-lived email links
  (verify / sign in / recover). The link itself is signed and self-describing
  (``api/access_tokens.py``); what needs storage is being able to spend it once and
  expire it, exactly as ``join_tokens`` does for admission.

See ``docs/Technical/Global Multiverse and Forks.md`` and ``Tenancy Rollout Plan``
Phase 1.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import TYPE_CHECKING

from arango import ArangoClient

from transversal.db.arango import _add_hash_index

if TYPE_CHECKING:
    from arango.database import StandardDatabase

ACCOUNTS = "accounts"
CAMPAIGNS = "campaigns"
ACCOUNT_TOKENS = "account_tokens"

#: The whole registry schema. Kept as a tuple so a test can assert that the
#: bootstrap creates *exactly* this and never a campaign collection.
REGISTRY_COLLECTIONS = (ACCOUNTS, CAMPAIGNS, ACCOUNT_TOKENS)

#: Beside the campaign database, never inside it: a fork is a copy of the campaign
#: database, so anything stored there would be duplicated into every fork.
DEFAULT_REGISTRY_DATABASE = "transversal_registry"


@dataclass
class RegistryConfig:
    """Connection settings for the registry. Same server, its own database."""

    url: str = "http://localhost:8529"
    username: str = "root"
    password: str = "transversal"
    database: str = DEFAULT_REGISTRY_DATABASE

    @classmethod
    def from_env(cls) -> "RegistryConfig":
        return cls(
            url=os.getenv("ARANGO_URL", "http://localhost:8529"),
            username=os.getenv("ARANGO_USERNAME", "root"),
            password=os.getenv("ARANGO_ROOT_PASSWORD", "transversal"),
            database=os.getenv("REGISTRY_DATABASE", DEFAULT_REGISTRY_DATABASE),
        )


_registry_cache: dict[tuple, "StandardDatabase"] = {}


def get_registry_db(config: "RegistryConfig | None" = None) -> "StandardDatabase":
    """Return a (cached) registry connection, creating only the registry schema.

    Memoized per process on the connection tuple, like ``get_db()``, but the
    bootstrap that runs once is the registry's own list rather than ``COLLECTIONS``.
    """
    if config is None:
        config = RegistryConfig.from_env()

    cache_key = (config.url, config.username, config.password, config.database)
    cached = _registry_cache.get(cache_key)
    if cached is not None:
        return cached

    client = ArangoClient(hosts=config.url)
    sys_db = client.db("_system", username=config.username, password=config.password)

    if not sys_db.has_database(config.database):
        sys_db.create_database(config.database)

    db = client.db(
        config.database, username=config.username, password=config.password
    )

    for name in REGISTRY_COLLECTIONS:
        if not db.has_collection(name):
            db.create_collection(name)

    _ensure_registry_indexes(db)
    _registry_cache[cache_key] = db
    return db


def _ensure_registry_indexes(db) -> None:
    # An account is its email; the unique index is the duplicate-account guard.
    _add_hash_index(db, ACCOUNTS, ["email"], unique=True)
    # "my forks" — the switcher's query.
    _add_hash_index(db, CAMPAIGNS, ["owner_account"])
    # Resolving a link is always by account, then id.
    _add_hash_index(db, ACCOUNT_TOKENS, ["account_id"])


def reset_registry_cache() -> None:
    """Drop the process cache. For tests that point the registry somewhere else."""
    _registry_cache.clear()
