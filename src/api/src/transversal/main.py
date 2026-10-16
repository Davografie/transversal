"""Transversal API — FastAPI application.

REST, GraphQL, and SSE endpoints.
"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.responses import Response
from strawberry.fastapi import GraphQLRouter

from contextlib import asynccontextmanager

import mimetypes
import os
import time

from transversal.api.graphql.schema import schema
from transversal.api.graphql.loaders import build_loaders
from transversal.api.rest.roll import router as roll_router
from transversal.api.rest.effects import router as effects_router
from transversal.api.rest.players import router as players_router
from transversal.api.rest.access import router as access_router
from transversal.api.rest.session_events import router as session_events_router
from transversal.api.rest.locations import router as locations_router
from transversal.api.rest.media import router as media_router
from transversal.api.rest.plans import router as plans_router
from transversal.api.rest.bundles import router as bundles_router
from transversal.api.rest.resource_pool import router as resource_pool_router
from transversal.api.rest.challenge_pool import router as challenge_pool_router
from transversal.api.rest.contest_pools import router as contest_pools_router
from transversal.api.rest.targeting_bans import router as targeting_bans_router
from transversal.api.rest.scene_state import router as scene_state_router
from transversal.api.rest.sessions import router as sessions_router
from transversal.api.rest.imagen import router as imagen_router
from transversal.api.sse.stream import router as sse_router
from transversal.api.auth import router as auth_router
from transversal.api.account_auth import router as account_auth_router
from transversal.api.forks import router as forks_router
from transversal.db.arango import current_database
from transversal.db.repository import EntityRepository
from transversal.services.campaign_provisioning import provision_campaign
from transversal.services.effects_engine import EffectsEngine
from transversal.services.entity_manager import EntityManager
from transversal.services.razmerit import RazmeritService


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Wire core services on startup.

    There is no seed-on-startup: all data is migrated (`migrate_*.py`). The old
    ``python -m transversal seed`` command and its module were removed 2026-09-27.

    Defined ahead of ``app`` (the DI helpers it calls resolve at startup time, not
    at import time).
    """
    await _startup()
    yield


app = FastAPI(
    title="Transversal API",
    version="0.2.0",
    description="VTTRPG backend for multiverse traversal",
    lifespan=lifespan,
)

def _cors_origins() -> list[str]:
    """Allowed browser origins (SEC-7).

    Nothing *needs* CORS here: in every supported deployment the app is
    same-origin — both the Vite dev server and the nginx edge proxy ``/api`` and
    ``/media``. The previous ``["*"]`` let any web page read API responses
    wherever the API was browser-reachable. These defaults cover the local dev
    surfaces; set ``CORS_ALLOW_ORIGINS`` (comma-separated) to override, ``*``
    included if that is genuinely what you mean.
    """
    raw = os.getenv("CORS_ALLOW_ORIGINS", "").strip()
    if raw:
        return [o.strip() for o in raw.split(",") if o.strip()]
    return [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
    ]


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_methods=["*"],
    allow_headers=["*"],
)

# SEC-3: slide an in-use session cookie forward, but only when it is getting old.
from transversal.api import auth as _auth  # noqa: E402

app.middleware("http")(_auth.session_refresh_middleware)

# B88: scope a request to the fork its host names (inert without FORKS_BASE_DOMAIN).
# A pure ASGI middleware, added rather than registered with `app.middleware`, because
# the database context variable must be set in the same task as the endpoint.
from transversal.api.tenancy import ForkScopeMiddleware  # noqa: E402

app.add_middleware(ForkScopeMiddleware)

# ── Suppress noisy polling logs ──────────────────────

import logging

# Ensure our diagnostic INFO logs (contest flow, etc.) are emitted.
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("transversal.graphql")

class _NoisyPathFilter(logging.Filter):
    """Suppress access logs for paths that generate constant poll traffic."""
    _quiet = {"/api/v1/imagen/jobs", "/health"}

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        for path in self._quiet:
            if path in msg and "200" in msg:
                return False
        return True

logging.getLogger("uvicorn.access").addFilter(_NoisyPathFilter())

# ── Request profiling (AQL + resolver timing) ─────────

from transversal.db import profiling

_prof_logger = logging.getLogger("transversal.profiling")
_QUIET_PROFILE_PATHS = {"/health", "/api/v1/imagen/jobs"}


@app.middleware("http")
async def profiling_middleware(request: Request, call_next):
    profiling.start_request()
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        profiling.finish_request()
        raise
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    stats = profiling.finish_request()
    if stats is not None and request.url.path not in _QUIET_PROFILE_PATHS:
        _log_profile(request, elapsed_ms, stats)
    return response


def _log_profile(request: Request, elapsed_ms: float, stats) -> None:
    if stats.count == 0 and not stats.resolvers:
        return
    line = (
        f"{request.method} {request.url.path} {elapsed_ms:.0f}ms — "
        f"{stats.count} AQL ({stats.aql_ms:.0f}ms), "
        f"{len(stats.resolvers)} resolvers (max {stats.resolver_max:.0f}ms)"
    )
    if elapsed_ms >= profiling.BREAKDOWN_MS or stats.count >= profiling.BREAKDOWN_QUERIES:
        _prof_logger.warning("%s\n%s", line, profiling.summarize(stats))
    else:
        _prof_logger.info(line)

# ── Dependency injection (lazy — swapped in tests) ───

#: Test seam: when set, every service built here uses this repository instead of one
#: for the request's database. `None` in production.
_repo: EntityRepository | None = None

#: The SFX registries, **one per database** ([[B88]]). A campaign's rules are its own:
#: a fork starts as a clone, but it may diverge, and dispatching a trigger against
#: another campaign's definition is a wrong effect rather than merely a leak. Keyed by
#: the request-scoped database — `None` is the process default — and populated from
#: that database on first use.
_engines: dict[str | None, EffectsEngine] = {}

#: Test seam: when set, `_get_engine` returns this engine whatever the database is.
#: `None` in production.
_effects_engine: EffectsEngine | None = None


def _get_repo() -> EntityRepository:
    """A repository for the **current** database, or the seam's, when one is set.

    Deliberately not cached when the seam is unset. The database is request-scoped
    ([[B88]]), so a cached repository pins the process to whichever campaign was
    built first — that is a cross-campaign leak, not a saving. The expensive part,
    the connection, is what ``get_db``'s LRU holds.
    """
    return _repo or EntityRepository()


def _get_em() -> EntityManager:
    return EntityManager(repository=_get_repo())


def _get_raz() -> RazmeritService:
    return RazmeritService(repository=_get_repo())


def _get_engine() -> EffectsEngine:
    """The SFX registry for the **current** database, or the seam's engine.

    Cached per database, because it accumulates registrations — a single shared
    registry answered every campaign with the first one's definitions. The first use
    in a database loads that database's SFXs; ``_startup`` warms the default one
    after its provisioning has run.
    """
    if _effects_engine is not None:
        return _effects_engine

    key = current_database()
    engine = _engines.get(key)
    if engine is None:
        engine = EffectsEngine()
        for sfx in _get_repo().get_all_sfxs():
            engine.register(sfx)
        _engines[key] = engine
    return engine


async def get_context(request: Request) -> dict:
    logger.info("[init] graphql request")
    return {
        "entity_manager": _get_em(),
        "razmerit_service": _get_raz(),
        "effects_engine": _get_engine(),
        "loaders": build_loaders(_get_em()),
    }


# ── Startup ──────────────────────────────────────────

async def _startup():
    """Wire core services (run by ``lifespan``).

    All data is migrated, not seeded — see ``migrate_*.py``.
    """
    from transversal.services.effects_applier import _register_core_handlers

    _register_core_handlers(_get_em(), _get_raz())

    # Everything a campaign database needs beyond its schema. Callable on purpose:
    # a fork is a verbatim clone, so it never receives a rule added after it was
    # made — the operator re-runs this for forks (see
    # `services.campaign_provisioning` and `tenancy_cli provision`).
    provision_campaign(_get_repo())

    # Warm the default database's SFX registry — *after* the provisioning above,
    # because `_get_engine` loads it from the database on first use and caches it per
    # database. Warming it earlier would cache the set from before the `ensure_*`
    # calls and then never see them.
    _engines.pop(current_database(), None)
    _get_engine()

    # Cross-worker SSE fan-in (no-op when Redis is unavailable).
    from transversal.api.sse.bus import event_bus
    event_bus.start_redis_subscriber()

    # Default session creation is disabled — IDs are no longer hardcoded.
    # Sessions are created on-demand via the API by the frontend.


# ── Routers ──────────────────────────────────────────

app.include_router(roll_router)
app.include_router(effects_router)
app.include_router(players_router)
app.include_router(session_events_router)
app.include_router(locations_router)
app.include_router(media_router)
app.include_router(plans_router)
app.include_router(bundles_router)
app.include_router(resource_pool_router)
app.include_router(challenge_pool_router)
app.include_router(contest_pools_router)
app.include_router(targeting_bans_router)
app.include_router(scene_state_router)
app.include_router(sessions_router)
app.include_router(imagen_router)
app.include_router(sse_router)
app.include_router(auth_router)
app.include_router(access_router)
app.include_router(account_auth_router)
app.include_router(forks_router)

# Serve uploaded media files


class CachedStaticFiles(StaticFiles):
    """Serve media with long-lived immutable caching.

    Media filenames are content-hashed (e.g. ``_Large``, ``_anim_<hash>.webm``,
    ``upload_<hash>``), so a regenerated asset gets a new URL and can safely be
    cached indefinitely by browsers/CDNs.
    """

    def file_response(
        self,
        full_path,
        stat_result,
        scope,
        status_code: int = 200,
    ) -> Response:
        response = super().file_response(full_path, stat_result, scope, status_code)
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        # SEC-10: only safe because every extension under /media now has a real
        # type — python:3.12-slim's mimetypes did not know .webp/.webm and served
        # them as application/octet-stream, and nosniff on a wrong type blanks
        # every image. The registrations below are what make this line correct.
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response


# SEC-10: python:3.12-slim's mimetypes database has no .webp or .webm, so
# StaticFiles declared generated images and loops as application/octet-stream.
# Browsers sniffed them back into place, which is why it went unnoticed — but the
# declared type was wrong, caching and any future img-src CSP could not rely on
# it, and it made X-Content-Type-Options: nosniff unsafe to add (it would have
# blanked every image in the game). Register the types first; nosniff is sent by
# CachedStaticFiles above. Check any new served extension against this list, or
# nosniff will bite.
mimetypes.add_type("image/webp", ".webp")
mimetypes.add_type("video/webm", ".webm")

# Primary path: Docker bind mount; fallback: local dev layout
media_path = "/app/media"
if not os.path.isdir(media_path):
    media_path = os.path.realpath(
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "media")
    )
if os.path.isdir(media_path):
    app.mount("/media", CachedStaticFiles(directory=media_path), name="media")

graphql_app = GraphQLRouter(schema, context_getter=get_context)
app.include_router(graphql_app, prefix="/api/v1/graphql")


@app.get("/health")
async def health():
    return {"status": "ok"}
