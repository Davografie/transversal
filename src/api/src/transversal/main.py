"""Transversal API — FastAPI application.

REST, GraphQL, and SSE endpoints.
"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.responses import Response
from strawberry.fastapi import GraphQLRouter

from contextlib import asynccontextmanager

import time

from transversal.api.graphql.schema import schema
from transversal.api.graphql.loaders import build_loaders
from transversal.api.rest.roll import router as roll_router
from transversal.api.rest.effects import router as effects_router
from transversal.api.rest.players import router as players_router
from transversal.api.rest.session_events import router as session_events_router
from transversal.api.rest.locations import router as locations_router
from transversal.api.rest.media import router as media_router
from transversal.api.rest.plans import router as plans_router
from transversal.api.rest.resource_pool import router as resource_pool_router
from transversal.api.rest.challenge_pool import router as challenge_pool_router
from transversal.api.rest.contest_pools import router as contest_pools_router
from transversal.api.rest.targeting_bans import router as targeting_bans_router
from transversal.api.rest.scene_state import router as scene_state_router
from transversal.api.rest.sessions import router as sessions_router
from transversal.api.rest.imagen import router as imagen_router
from transversal.api.sse.stream import router as sse_router
from transversal.api.auth import router as auth_router
from transversal.db.repository import EntityRepository
from transversal.services.effects_engine import EffectsEngine
from transversal.services.entity_manager import EntityManager
from transversal.services.razmerit import RazmeritService


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Wire core services on startup. Seed data runs via `python -m transversal seed`.

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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

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

_repo: EntityRepository | None = None
_entity_manager: EntityManager | None = None
_razmerit_service: RazmeritService | None = None
_effects_engine: EffectsEngine | None = None


def _get_repo() -> EntityRepository:
    global _repo
    if _repo is None:
        _repo = EntityRepository()
    return _repo


def _get_em() -> EntityManager:
    global _entity_manager
    if _entity_manager is None:
        _entity_manager = EntityManager(repository=_get_repo())
    return _entity_manager


def _get_raz() -> RazmeritService:
    global _razmerit_service
    if _razmerit_service is None:
        _razmerit_service = RazmeritService(repository=_get_repo())
    return _razmerit_service


def _get_engine():
    global _effects_engine
    if _effects_engine is None:
        _effects_engine = EffectsEngine()
    return _effects_engine


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
    """Wire core services (run by ``lifespan``). Seed data runs via `python -m transversal seed`."""
    from transversal.services.effects_applier import _register_core_handlers
    from transversal.services.sfx_owner import (
        ensure_sfx_owners,
        ensure_give_in_sfx,
        ensure_targeting_ban_sfx,
        ensure_contest_complication_sfx,
        ensure_prevent_taken_out_sfx,
        ensure_hitch_gain_complication_sfx,
        ensure_opportunity_sfx,
        ensure_offer_negative_sfx,
        ensure_starter_location_sfx,
        ensure_support_cast_sfx,
        ensure_base_move_sfxs,
        ensure_gmc_base_difficulty,
        remove_legacy_contest_complication_sfx,
        remove_legacy_buy_hitch_sfx,
        backfill_trait_default_sfx,
        backfill_source_kinds,
    )

    _register_core_handlers(_get_em(), _get_raz())

    # Load SFXs from database into the in-memory effects engine
    repo = _get_repo()
    engine = _get_engine()
    ensure_sfx_owners(repo)
    ensure_give_in_sfx(repo)
    ensure_targeting_ban_sfx(repo)
    ensure_contest_complication_sfx(repo)
    ensure_prevent_taken_out_sfx(repo)
    ensure_hitch_gain_complication_sfx(repo)
    ensure_opportunity_sfx(repo)
    ensure_offer_negative_sfx(repo)
    ensure_starter_location_sfx(repo)
    ensure_support_cast_sfx(repo)
    ensure_base_move_sfxs(repo)
    ensure_gmc_base_difficulty(repo)
    remove_legacy_contest_complication_sfx(repo)
    remove_legacy_buy_hitch_sfx(repo)
    backfill_trait_default_sfx(repo)
    backfill_source_kinds(repo)
    repo.collapse_legacy_personal_relationship_types()
    db_sfxs = repo.get_all_sfxs()
    for s in db_sfxs:
        engine.register(s)

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
app.include_router(resource_pool_router)
app.include_router(challenge_pool_router)
app.include_router(contest_pools_router)
app.include_router(targeting_bans_router)
app.include_router(scene_state_router)
app.include_router(sessions_router)
app.include_router(imagen_router)
app.include_router(sse_router)
app.include_router(auth_router)

# Serve uploaded media files
import os


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
        return response


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
