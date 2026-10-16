"""Fork provisioning — clone the canonical database (B88, Phase 2).

Under [[Global Multiverse and Forks]] a fork is a **verbatim copy** of the global
multiverse into a new database. It is cheap enough to do this way because every
``_key`` is a stable string and edges are ``collection/key``, so a document copied
unchanged into a same-named collection keeps **every edge resolving** — no handle
remapping, no dependency closure, no reference audit ([[Global Multiverse and
Forks]] §2).

What this module does, in order:

1. derive the fork's database name from its display name;
2. bootstrap the target database's collections through ``get_db()`` **without
   indexes** — the same 20-collection schema a campaign has, not a hand-rolled one;
3. copy the **content** collections verbatim, skipping the play-only ones unless
   asked otherwise (the first migration wants a full duplicate — see §6);
4. build the indexes **last**, and only then write the routing row.

Step 4 is not an optimisation, it is a correctness fix found by doing it the other
way round. The campaign bootstrap builds ``traits (name, universe)`` **unique**; the
live global violates it — **57 duplicate groups, 64 documents** — so the index was
never built there (the helper swallows the failure). On a fresh fork the index
builds, and a copy *after* that silently drops those 64 rows. Copying first and
indexing second reproduces the source exactly, which is what "verbatim" has to mean;
``clone_database`` also refuses to route a clone that lost any rows at all.

The content/play split is **per edge as well as per collection**. ``relationships``
holds structural edges *and* the ``agency`` edges that point at ``players``, so a
content-only fork prunes any edge whose endpoint it did not copy. Without that, a
fork of the played-in database carries ownership edges into players it does not
have — a dangling edge, the exact class the fork model claims to avoid. Pruning is
reported (``CloneReport.edges_dropped``) and logged, because it also means the
source was not a clean global.

Idempotent by refusal rather than by repetition: a second call for the same fork
returns the existing row, and cloning into a database that already exists but has
no row is refused as an orphan, because a half-created campaign is worse than none
([[Tenancy Rollout Plan]] Phase 2).
"""

from __future__ import annotations

import logging
import os
import re
import uuid
from dataclasses import dataclass, field

from transversal.db.arango import (
    HISTORICAL_RECORDS,
    JOIN_TOKENS,
    MESSAGES,
    PLAYERS,
    SCHEDULED_EVENTS,
    ArangoConfig,
    _ensure_indexes,
    forget_database,
    get_db,
    use_database,
)

logger = logging.getLogger("transversal.provisioner")

#: Collections that are a campaign's **play state**, not its content: copying them
#: into a fresh fork would hand the new table someone else's history, roster and
#: open admission windows. The list is [[Global Multiverse and Forks]] §3's, made
#: executable.
PLAY_COLLECTIONS = frozenset(
    {
        HISTORICAL_RECORDS,
        JOIN_TOKENS,
        MESSAGES,
        PLAYERS,
        SCHEDULED_EVENTS,
    }
)

#: ArangoDB database names: letters, digits, underscore and hyphen only.
_UNSAFE = re.compile(r"[^a-z0-9]+")
_MAX_DATABASE_NAME = 64

#: A DNS label is at most 63 characters, and a hostname is case-insensitive.
_MAX_SLUG = 63


def fork_database_name(name: str, *, suffix: str | None = None) -> str:
    """A database name for a fork: ``tv2_fork_<slug>_<6 hex>``.

    The slug keeps it legible in a database list; the suffix keeps two forks of the
    same name apart (and is injectable so a test — or the first migration — can pin
    an exact name).
    """
    slug = _UNSAFE.sub("_", (name or "").strip().lower()).strip("_") or "fork"
    token = suffix or uuid.uuid4().hex[:6]
    room = _MAX_DATABASE_NAME - len("tv2_fork_") - len(token) - 1
    return f"tv2_fork_{slug[:room]}_{token}"


def fork_slug(name: str) -> str:
    """The DNS label a fork answers on: lowercase, hyphens, no leading/trailing one.

    Deliberately **not** unique — the caller checks the registry and says so with a
    409 — because silently suffixing a requested name is how two campaigns end up
    answering on `daves-game-2` without anyone choosing that.
    """
    slug = _UNSAFE.sub("-", (name or "").strip().lower()).strip("-")
    return (slug or "campaign")[:_MAX_SLUG].strip("-")


def _verifiable(doc: dict) -> dict:
    """A document with its database-local handles removed, ``_key`` kept.

    ``_id`` and ``_rev`` describe the *source* database's row; keeping ``_key`` is
    what makes every ``_from``/``_to`` in the copy resolve unchanged.
    """
    return {k: v for k, v in doc.items() if k not in ("_id", "_rev")}


def _is_edge(collection) -> bool:
    try:
        return int(collection.properties().get("type", 2)) == 3
    except Exception:
        return False


def source_collections(db) -> list[str]:
    """The database's application collections, system ones excluded."""
    return sorted(c["name"] for c in db.collections() if not c["name"].startswith("_"))


def _endpoint_collection(reference: str) -> str:
    """``entities/loc-1`` → ``entities``. Anything malformed → ``""``."""
    return reference.split("/", 1)[0] if isinstance(reference, str) and "/" in reference else ""


def _prune_edges(docs: list[dict], kept: set[str]) -> tuple[list[dict], int]:
    """Drop edges with an endpoint in a collection this fork did not copy.

    The content/play split is not a clean cut by collection: ``relationships`` holds
    the structural edges (location trees, memberships) **and** the ``agency`` edges
    that point at ``players``. Copying it wholesale would carry ownership of the
    source's players into a fork that has none — a dangling edge, which is the exact
    class of problem [[Global Multiverse and Forks]] §2 claims a fork cannot have.
    """
    kept_docs, dropped = [], 0
    for doc in docs:
        if (
            _endpoint_collection(doc.get("_from")) in kept
            and _endpoint_collection(doc.get("_to")) in kept
        ):
            kept_docs.append(doc)
        else:
            dropped += 1
    return kept_docs, dropped


@dataclass
class CloneReport:
    """What a clone actually did — the audit trail, not a count of intent.

    ``edges_dropped`` non-empty means the source was **not** a clean global (it
    carried play-state edges); the fork is still internally consistent, which is
    the property that matters.
    """

    copied: dict[str, int] = field(default_factory=dict)
    edges_dropped: dict[str, int] = field(default_factory=dict)

    @property
    def total_copied(self) -> int:
        return sum(self.copied.values())


def clone_database(
    source_db, target_db, *, include_play: bool = False
) -> CloneReport:
    """Copy ``source_db``'s documents into ``target_db`` verbatim.

    Returns a :class:`CloneReport` — the per-collection counts and any edges that
    could not come along. A clone that quietly copied nothing, or lost rows, raises
    rather than routing a broken fork.
    """
    skip = set() if include_play else set(PLAY_COLLECTIONS)
    kept = {name for name in source_collections(source_db) if name not in skip}
    report = CloneReport()

    for name in sorted(kept):
        source = source_db.collection(name)
        if not target_db.has_collection(name):
            target_db.create_collection(name, edge=_is_edge(source))
        edge = _is_edge(source)
        docs = [_verifiable(doc) for doc in source.all()]
        if edge:
            docs, dropped = _prune_edges(docs, kept)
            if dropped:
                report.edges_dropped[name] = dropped
        if docs:
            target_db.collection(name).insert_many(docs, overwrite=True)
        stored = target_db.collection(name).count()
        if stored != len(docs):
            # Never route a fork that quietly lost rows. This is not hypothetical:
            # the live global carries 57 duplicate (name, universe) trait groups,
            # and inserting *after* the unique index is built silently drops them.
            raise RuntimeError(
                f"clone lost documents in {name!r}: read {len(docs)}, stored {stored}"
            )
        report.copied[name] = len(docs)

    return report


def provision_fork(
    registry,
    *,
    source_database: str,
    name: str,
    owner_account: str,
    database: str | None = None,
    slug: str = "",
    include_play: bool = False,
    config: ArangoConfig | None = None,
):
    """Clone ``source_database`` into a new fork and route it. Returns the ``Fork``.

    ``registry`` is a :class:`transversal.db.registry_repository.RegistryRepository`.
    ``include_play`` is for the one-off first migration, which is a full duplicate
    by the owner's 2026-10-16 decision; an ordinary fork leaves play state behind.
    ``slug`` is the DNS label the fork answers on; the caller is responsible for
    having checked it is free (a 409, not a silent suffix).
    """
    target_name = database or fork_database_name(name)

    existing = registry.find_fork_by_database(target_name)
    if existing:
        # Idempotent: the same call twice must not clone a second time.
        return existing

    source_config = config
    if source_config is None:
        source_config = ArangoConfig.from_env()
    source_config = ArangoConfig(
        url=source_config.url,
        username=source_config.username,
        password=source_config.password,
        database=source_database,
    )
    source_db = get_db(source_config)

    # Does the target already exist? `get_db` would create it, so ask the server
    # first: an existing database with no routing row is an orphan, not a fork.
    client, sys_db = _system_db(source_config)
    try:
        already_there = sys_db.has_database(target_name)
    finally:
        # `get_db` keeps its own client; this probe must not leave one behind.
        client.close()

    if already_there:
        raise ValueError(
            f"database {target_name!r} already exists but has no routing row; "
            "refusing to clone into it"
        )

    with use_database(target_name):
        target_db = get_db(ensure_indexes=False)

    report = clone_database(source_db, target_db, include_play=include_play)
    if not report.total_copied:
        raise RuntimeError("nothing was copied; refusing to route an empty fork")
    if report.edges_dropped:
        logger.warning(
            "fork %s: dropped %d play-state edges, so the source is not a clean "
            "global — %s",
            target_name,
            sum(report.edges_dropped.values()),
            report.edges_dropped,
        )

    # Indexes after the copy, deliberately — see the module docstring. A failure
    # here mirrors the source, whose own index also could not be built.
    _ensure_indexes(target_db)

    return registry.create_fork(name, target_name, owner_account, slug=slug)


def _system_db(config: ArangoConfig):
    """A client and its ``_system`` database — for the operations that are not
    scoped to a campaign (create/has/delete a database)."""
    from arango import ArangoClient

    client = ArangoClient(hosts=config.url)
    sys_db = client.db("_system", username=config.username, password=config.password)
    return client, sys_db


def drop_fork(registry, fork_id: str, *, config: ArangoConfig | None = None) -> bool:
    """Delete a fork's database and its routing row. Returns whether it existed.

    This is the act the database-per-campaign architecture was chosen for
    ([[Tenancy Rollout Plan]] §1: *"delete/archive via ``drop_database``"*). It is a
    **service, not a route**: dropping a campaign is irreversible and the policy for
    who may do it is the owner's, so it is left reachable only from an operator path
    until that is decided.

    Order matters: drop the database first, then forget the routing row. A failure
    between the two leaves a row naming a missing database — visible and re-droppable
    — rather than a database nothing knows about.
    """
    fork = registry.get_fork(fork_id)
    if not fork:
        return False

    resolved = config or ArangoConfig.from_env()
    client, sys_db = _system_db(resolved)
    try:
        if sys_db.has_database(fork.database):
            sys_db.delete_database(fork.database)
    finally:
        # The pool for a deleted database must not stay cached: a later database of
        # the same name would inherit a dead connection.
        forget_database(fork.database)
        client.close()

    logger.warning(
        "[provisioner] dropped fork %s (%s, slug %r)", fork.id, fork.database, fork.slug
    )
    return registry.delete_fork(fork_id)


def campaign_databases(
    registry, *, global_database: str | None = None, config: ArangoConfig | None = None
) -> list[str]:
    """Every database a schema change must reach: the global, then each fork.

    ``migrate_*.py`` scripts each call ``get_db()`` and so touch one database; this is
    the list they should loop instead ([[B88]]: *"migrations must enumerate every
    campaign database. One forgotten database is a silent divergence."*). The global
    comes first and names are deduplicated, so a fork that happens to be the global is
    visited once.
    """
    resolved = config or ArangoConfig.from_env()
    global_name = global_database or os.getenv("GLOBAL_DATABASE") or resolved.database
    names = [global_name]
    for fork in registry.list_forks():
        if fork.database and fork.database not in names:
            names.append(fork.database)
    return names
