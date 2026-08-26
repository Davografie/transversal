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
from dataclasses import dataclass
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
RELATIONSHIPS = "relationships"    # edge collection
MESSAGES = "messages"              # inter-entity persistent messages
ENTITY_IMAGES = "entity_images"    # generated image metadata
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
    RELATIONSHIPS: True,  # edge
    MESSAGES: False,      # document
    ENTITY_IMAGES: False,
    LIFE_PATHS: False,    # document
    ROLL_TABLES: False,   # document
    HISTORICAL_RECORDS: False,  # document
    PLAN_ENTITIES: False,     # document
    PLAN_RELATIONSHIPS: True,  # edge
}


# Per-process connection cache. get_db() was previously re-running the full
# bootstrap (ArangoClient + has_database + has_collection x16 + _ensure_indexes)
# on every call — every EntityRepository() construction paid that cost, and the
# GraphQL media resolvers construct a fresh repository per field per entity.
# The connection pool is safe to share across the process.
_db_cache: dict[tuple, "StandardDatabase"] = {}


def get_db(config: ArangoConfig | None = None) -> "StandardDatabase":
    """Return a (cached) connection, creating database and collections if needed.

    Memoized per process on (url, username, password, database); the
    create-db/collection/index bootstrap runs once and is skipped afterwards.
    """
    if config is None:
        config = ArangoConfig.from_env()

    cache_key = (config.url, config.username, config.password, config.database)
    cached = _db_cache.get(cache_key)
    if cached is not None:
        return cached

    from arango import ArangoClient

    client = ArangoClient(hosts=config.url)
    sys_db = client.db("_system", username=config.username, password=config.password)

    if not sys_db.has_database(config.database):
        sys_db.create_database(config.database)

    db = client.db(config.database, username=config.username, password=config.password)

    for name, is_edge in COLLECTIONS.items():
        if not db.has_collection(name):
            db.create_collection(name, edge=is_edge)

    _ensure_indexes(db)
    _db_cache[cache_key] = db
    return db


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

    # entity_images
    _add_hash_index(db, ENTITY_IMAGES, ["entity_id"])
    _add_hash_index(db, ENTITY_IMAGES, ["entity_id", "universe"])

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




def _add_hash_index(db, collection: str, fields: list[str], unique: bool = False) -> None:
    try:
        col = db.collection(collection)
        opts = {"type": "hash", "fields": fields, "unique": unique, "sparse": False}
        # Skip if already exists
        for idx in col.indexes():
            if idx.get("type") == "hash" and idx.get("fields") == fields:
                return
        col.add_hash_index(fields, unique=unique, sparse=False)
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
