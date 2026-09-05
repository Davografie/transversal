"""Request-scoped AQL + resolver profiling.

Turns "this feels slow" into numbers: per-request AQL query count/duration and
GraphQL resolver durations, logged at request end (plus a breakdown for slow or
query-heavy requests, and per-query warnings for slow AQL).

Cheap enough to leave on. Disable with ``TRANSVERSAL_PROFILE=0``.
"""

from __future__ import annotations

import contextvars
import logging
import os
import time
from dataclasses import dataclass, field

logger = logging.getLogger("transversal.profiling")

_ENABLED = os.getenv("TRANSVERSAL_PROFILE", "1").lower() not in ("0", "false", "off")

SLOW_QUERY_MS = float(os.getenv("PROFILE_SLOW_QUERY_MS", "100"))
BREAKDOWN_MS = float(os.getenv("PROFILE_BREAKDOWN_MS", "500"))
BREAKDOWN_QUERIES = int(os.getenv("PROFILE_BREAKDOWN_QUERIES", "50"))


def enabled() -> bool:
    return _ENABLED


@dataclass
class QueryStats:
    """Accumulated timings for one HTTP request."""

    aql: list[tuple[str, float]] = field(default_factory=list)  # (query, ms)
    resolvers: list[tuple[str, float]] = field(default_factory=list)  # (field_name, ms)

    @property
    def count(self) -> int:
        return len(self.aql)

    @property
    def aql_ms(self) -> float:
        return sum(d for _, d in self.aql)

    @property
    def resolver_ms(self) -> float:
        return sum(d for _, d in self.resolvers)


_ctx: contextvars.ContextVar[QueryStats | None] = contextvars.ContextVar(
    "transversal_profiling", default=None
)


def start_request() -> None:
    if _ENABLED:
        _ctx.set(QueryStats())


def finish_request() -> QueryStats | None:
    stats = _ctx.get()
    _ctx.set(None)
    return stats


def record_aql(query: str, duration_ms: float) -> None:
    stats = _ctx.get()
    if stats is not None:
        stats.aql.append((query, duration_ms))
    if duration_ms >= SLOW_QUERY_MS:
        q = " ".join(query.split())
        logger.warning("slow AQL %.1fms: %s", duration_ms, q[:300])


def record_resolver(field_name: str, duration_ms: float) -> None:
    stats = _ctx.get()
    if stats is not None:
        stats.resolvers.append((field_name, duration_ms))


def _group(entries: list[tuple[str, float]]) -> list[tuple[str, float, int]]:
    """Aggregate (key, ms) entries by key → (key, total_ms, count), slowest first."""
    totals: dict[str, list[float]] = {}
    for key, ms in entries:
        totals.setdefault(key, []).append(ms)
    grouped = [(k, sum(v), len(v)) for k, v in totals.items()]
    grouped.sort(key=lambda x: -x[1])
    return grouped


def summarize(stats: QueryStats) -> str:
    """Multi-line breakdown of the slowest AQL queries and resolvers."""
    lines: list[str] = []
    aql_groups = _group(stats.aql)
    for q, total_ms, count in aql_groups[:5]:
        text = " ".join(q.split())
        lines.append(f"  AQL  {total_ms:7.1f}ms  x{count:<4} {text[:180]}")
    if not aql_groups:
        lines.append("  (no AQL queries)")
    lines.append("  ---")
    resolver_groups = _group(stats.resolvers)
    for field, total_ms, count in resolver_groups[:8]:
        lines.append(f"  RSLV {total_ms:7.1f}ms  x{count:<4} {field}")
    if not resolver_groups:
        lines.append("  (no resolvers timed)")
    return "\n".join(lines)


# ── ArangoDB instrumentation ─────────────────────────


class _TimedAQL:
    """Wraps python-arango's ``db.aql`` so ``execute`` is timed and recorded."""

    __slots__ = ("_aql",)

    def __init__(self, aql):
        self._aql = aql

    def execute(self, query, **kwargs):
        start = time.perf_counter()
        try:
            return self._aql.execute(query, **kwargs)
        finally:
            record_aql(query, (time.perf_counter() - start) * 1000.0)

    def __getattr__(self, name):
        return getattr(self._aql, name)


class _TimedDB:
    """Delegates every attribute to the real connection except ``.aql``."""

    __slots__ = ("_db",)

    def __init__(self, db):
        object.__setattr__(self, "_db", db)

    def __getattr__(self, name):
        if name == "aql":
            return _TimedAQL(self._db.aql)
        return getattr(self._db, name)


def instrument_db(db):
    """Wrap an ArangoDB connection so ``db.aql.execute`` is timed and recorded.

    Returns the same connection unchanged when profiling is disabled.
    """
    if not _ENABLED or db is None:
        return db
    return _TimedDB(db)
