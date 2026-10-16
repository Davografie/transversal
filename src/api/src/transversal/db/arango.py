"""ArangoDB client and database setup — v2 multi-collection model.

Collections:
  entities      — document: core entity metadata
  projections   — document: per-universe body grouping
  traits        — document: trait registry per universe
  traitsets     — document: trait grouping registry
  traitsettings — edge: entity → trait, carries entity-specific config
  sfxs          — document: SFX registry
  relationships — edge: entity → entity connections

Graph:
  entity ──(traitsettings)──> trait ──> traitset
  entity ──(has_projection)──> projection
  entity ──(relationships)──> entity
  trait  ──(possible_sfxs)──> sfx
"""

from __future__ import annotations

import os
from collections import OrderedDict
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from arango import ArangoClient
    from arango.database import StandardDatabase


@dataclass
class ArangoConfig:
    url: str = "http://localhost:8529"
    username: str = "root"
    password: str = "transversal"
    database: str = "transversal"

    @classmethod
    def from_env(cls) -> ArangoConfig:
        return cls(
            url=os.getenv("ARANGO_URL", "http://localhost:8529"),
            username=os.getenv("ARANGO_USERNAME", "root"),
            password=os.getenv("ARANGO_ROOT_PASSWORD", "transversal"),
            database=os.getenv("ARANGO_DATABASE", "transversal"),
        )


# Collection names
ENTITIES = "entities"
PROJECTIONS = "projections"
TRAITS = "traits"
TRAITSETS = "traitsets"
TRAITSETTINGS = "traitsettings"    # edge collection
TRAITSETSETTINGS = "traitsetsettings"  # edge collection: entity → traitset
SFX_OWNERS = "sfx_owners"           # document: named SFX owner buckets (table, gm)
SFXS = "sfxs"
SCHEDULED_EVENTS = "scheduled_events"  # document: centrally-scheduled timed reverts/effects
PLAYERS = "players"
JOIN_TOKENS = "join_tokens"        # document: campaign admission tokens (SEC-3).
#   Holds only *liveness* — id, when it was minted, when it expires, when it was
#   closed. The token itself is signed and self-describing, so verification does
#   not need this collection; being able to close one early does. In the
#   campaign-per-database model these live in the campaign's own database.
RELATIONSHIPS = "relationships"    # edge collection
MESSAGES = "messages"              # inter-entity persistent messages
IMAGES = "images"                  # image metadata, owned by an entity or a trait
LIFE_PATHS = "life_paths"          # life path definitions
ROLL_TABLES = "roll_tables"        # reusable roll tables (life path steps + general)
HISTORICAL_RECORDS = "historical_records"  # append-only entity event log
PLAN_ENTITIES = "plan_entities"            # document: staged entity drafts
PLAN_RELATIONSHIPS = "plan_relationships"  # edge: staged relationship drafts

COLLECTIONS = {
    ENTITIES: False,
    PROJECTIONS: False,
    TRAITS: False,
    TRAITSETS: False,
    TRAITSETTINGS: True,  # edge
    TRAITSETSETTINGS: True,  # edge
    SFX_OWNERS: False,    # document
    SFXS: False,
    SCHEDULED_EVENTS: False,  # document
    PLAYERS: False,
    JOIN_TOKENS: False,   # document
    RELATIONSHIPS: True,  # edge
    MESSAGES: False,      # document
    IMAGES: False,
    LIFE_PATHS: False,    # document
    ROLL_TABLES: False,   # document
    HISTORICAL_RECORDS: False,  # document
    PLAN_ENTITIES: False,     # document
    PLAN_RELATIONSHIPS: True,  # edge
}


# ── The connection cache, and which database a context acts on ────────

#: How many databases to keep connected at once. One pool per database for the
#: process lifetime is correct for one campaign and unbounded at a thousand
#: ([[B88]]), so the cache is an LRU. Override with ``DB_CACHE_MAX``.
DEFAULT_DB_CACHE_MAX = 32


def _db_cache_max() -> int:
    """The bound, from ``DB_CACHE_MAX``; a malformed or non-positive value falls
    back to the default rather than disabling the bound."""
    raw = os.getenv("DB_CACHE_MAX", "").strip()
    if not raw:
        return DEFAULT_DB_CACHE_MAX
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_DB_CACHE_MAX
    return value if value > 0 else DEFAULT_DB_CACHE_MAX


@dataclass
class _PooledConnection:
    """A cached connection and the client that owns it.

    The client is kept so eviction can **close** it. python-arango holds a
    connection pool per client, so dropping only the ``db`` reference would leave
    the sockets to GC rather than bounding them — which is the whole point of the
    bound. Eviction takes the least-recently-used entry, so a request that is
    actively using a database is not the one closed.
    """

    db: "StandardDatabase"
    client: "ArangoClient"


#: Per-process LRU, keyed by the connection tuple. get_db() was previously
#: re-running the full bootstrap (ArangoClient + has_database + has_collection x20
#: + _ensure_indexes) on every call — every EntityRepository() construction paid
#: that cost, and the GraphQL media resolvers construct a fresh repository per
#: field per entity. The connection pool is safe to share across the process.
_db_cache: "OrderedDict[tuple, _PooledConnection]" = OrderedDict()

#: The database the current context is acting on. ``None`` means the process
#: default (``ARANGO_DATABASE``). The routing layer sets this once a request has
#: been resolved to a fork; **nothing sets it yet**, so today's behaviour — one
#: database for the process — is unchanged.
_request_database: ContextVar[str | None] = ContextVar(
    "transversal_request_database", default=None
)


def current_database() -> str | None:
    """The database the current context is acting on, or None for the default."""
    return _request_database.get()


@contextmanager
def use_database(database: str):
    """Act on ``database`` for the duration of the block.

    This is the seam per-request resolution hangs off ([[B88]]): a fork is an
    ArangoDB database, and every ``get_db()`` inside one request must resolve to
    it. It is a context variable rather than an argument because ``get_db()`` is
    called from repository constructors all over the codebase, none of which carry
    a request.
    """
    token = _request_database.set(database)
    try:
        yield
    finally:
        _request_database.reset(token)


def _close_quietly(entry: _PooledConnection) -> None:
    try:
        entry.client.close()
    except Exception:
        # Closing is hygiene, never a reason to fail a caller.
        pass


def reset_db_cache() -> None:
    """Close and forget every cached connection. For tests and teardown."""
    while _db_cache:
        _, entry = _db_cache.popitem(last=False)
        _close_quietly(entry)


def get_db(
    config: ArangoConfig | None = None, *, ensure_indexes: bool = True
) -> "StandardDatabase":
    """Return a (cached) connection, creating database and collections if needed.

    Memoized per process on (url, username, password, database) in a bounded LRU,
    so the create-db/collection/index bootstrap runs once per database and the
    number of live pools cannot grow without bound.

    An explicit ``config`` is used exactly as given — a caller that names a
    database means it. The env default, by contrast, is overridden by a
    request-scoped database (``use_database``) when one is set.

    ``ensure_indexes=False`` creates the database and its 20 collections but skips
    the index pass. That exists for **provisioning**: a clone must write its
    documents before the unique indexes are built, or any source row that already
    violates one is silently dropped instead of copied ([[B88]]). The flag is a
    bootstrap-time decision — a database already in the cache is returned as-is.
    """
    if config is None:
        config = ArangoConfig.from_env()
        requested = _request_database.get()
        if requested and requested != config.database:
            config = replace(config, database=requested)

    cache_key = (config.url, config.username, config.password, config.database)
    cached = _db_cache.get(cache_key)
    if cached is not None:
        _db_cache.move_to_end(cache_key)
        return cached.db

    from arango import ArangoClient

    client = ArangoClient(hosts=config.url)
    sys_db = client.db("_system", username=config.username, password=config.password)

    if not sys_db.has_database(config.database):
        sys_db.create_database(config.database)

    db = client.db(config.database, username=config.username, password=config.password)

    for name, is_edge in COLLECTIONS.items():
        if not db.has_collection(name):
            db.create_collection(name, edge=is_edge)

    if ensure_indexes:
        _ensure_indexes(db)
    from transversal.db.profiling import instrument_db

    wrapped = instrument_db(db)
    _db_cache[cache_key] = _PooledConnection(db=wrapped, client=client)
    _db_cache.move_to_end(cache_key)
    while len(_db_cache) > _db_cache_max():
        _, evicted = _db_cache.popitem(last=False)
        _close_quietly(evicted)
    return wrapped


def _ensure_indexes(db) -> None:
    """Create indexes for efficient queries."""
    # entities
    _add_hash_index(db, ENTITIES, ["type"])
    _add_hash_index(db, ENTITIES, ["current_universe"])
    _add_hash_index(db, ENTITIES, ["current_location"])
    _add_persistent_index(db, ENTITIES, ["known_to[*]"])

    # projections
    _add_hash_index(db, PROJECTIONS, ["entity_id"])
    _add_hash_index(db, PROJECTIONS, ["universe"])

    # traits registry
    _add_hash_index(db, TRAITS, ["name", "universe"], unique=True)
    _add_hash_index(db, TRAITS, ["traitset_id"])
    _add_hash_index(db, TRAITS, ["universe"])

    # traitsets
    _add_hash_index(db, TRAITSETS, ["name", "universe"], unique=True)
    _add_hash_index(db, TRAITSETS, ["universe"])

    # traitsettings (edge)
    _add_hash_index(db, TRAITSETTINGS, ["entity_id"])
    _add_hash_index(db, TRAITSETTINGS, ["trait_id"])
    _add_hash_index(db, TRAITSETTINGS, ["traitset_id"])

    # traitsetsettings (edge)
    _add_hash_index(db, TRAITSETSETTINGS, ["entity_id"])
    _add_hash_index(db, TRAITSETSETTINGS, ["traitset_id"])

    # sfxs
    _add_hash_index(db, SFXS, ["name"], unique=True)

    # relationships (edge)
    _add_hash_index(db, RELATIONSHIPS, ["type"])

    # images (owner: an entity or a trait; variant_id: projection / traitsetting)
    _add_hash_index(db, IMAGES, ["owner_id"])
    _add_hash_index(db, IMAGES, ["owner_id", "universe"])

    # life paths
    _add_hash_index(db, LIFE_PATHS, ["universe"])

    # roll tables
    _add_hash_index(db, ROLL_TABLES, ["life_path"])
    _add_hash_index(db, ROLL_TABLES, ["universe"])

    # plan staging
    _add_hash_index(db, PLAN_ENTITIES, ["plan_id"])
    _add_hash_index(db, PLAN_RELATIONSHIPS, ["plan_id"])

    # historical records
    _add_hash_index(db, HISTORICAL_RECORDS, ["entity_id"])
    _add_hash_index(db, HISTORICAL_RECORDS, ["record_type"])

    # messages
    _add_hash_index(db, MESSAGES, ["sender_entity_id"])
    _add_hash_index(db, MESSAGES, ["recipient_entity_id"])




def _add_hash_index(
    db, collection: str, fields: list[str], unique: bool = False, sparse: bool = False
) -> None:
    try:
        col = db.collection(collection)
        # Skip if already exists
        for idx in col.indexes():
            if idx.get("type") == "hash" and idx.get("fields") == fields:
                return
        col.add_index({
            "type": "hash",
            "fields": fields,
            "unique": unique,
            "sparse": sparse,
        })
    except Exception:
        pass


def _add_persistent_index(db, collection: str, fields: list[str]) -> None:
    try:
        col = db.collection(collection)
        for idx in col.indexes():
            if idx.get("type") == "persistent" and idx.get("fields") == fields:
                return
        col.add_persistent_index(fields)
    except Exception:
        pass
