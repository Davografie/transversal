"""Strawberry extension: per-resolver timing fed into the request profiler.

Attached to the GraphQL schema; each field resolver is timed and recorded into
the same request-scoped stats the AQL profiler and middleware use, so one
request-end log covers both database and resolver time.
"""

from __future__ import annotations

import inspect
import time

from strawberry.extensions import SchemaExtension

from transversal.db.profiling import enabled, record_resolver


class ResolverTimingExtension(SchemaExtension):
    async def resolve(self, _next, root, info, *args, **kwargs):
        if not enabled():
            result = _next(root, info, *args, **kwargs)
            return await result if inspect.isawaitable(result) else result
        start = time.perf_counter()
        try:
            result = _next(root, info, *args, **kwargs)
            return await result if inspect.isawaitable(result) else result
        finally:
            field = info.field_name
            path = getattr(info, "path", None)
            if path is not None:
                try:
                    field = f"{field}@/{'/'.join(str(p) for p in path.as_list())}"
                except Exception:
                    pass
            record_resolver(field, (time.perf_counter() - start) * 1000.0)
