"""REST endpoints for image generation and animation.

POST /api/v1/imagen/{entity_id}  — trigger Flux image generation (async, returns 202)
POST /api/v1/animate/{entity_id} — trigger WanVideo loop generation (async, returns 202)

Both endpoints return immediately with 202 Accepted.
Progress is published via SSE events (event type: 'imagen_progress').
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException

from transversal.api.sse.bus import StreamEvent, event_bus
from transversal.domain import EntityImage, ImageType
from transversal.imagen.models import (
    AnimateRequest,
    GenerationStatus,
    GenerationType,
    ImagenRequest,
    ImagenResponse,
    ImageListResponse,
)
from transversal.imagen.orchestrator import ImagenOrchestrator
from transversal.services.entity_manager import EntityManager, EntityNotFoundError

logger = logging.getLogger("transversal.imagen")
router = APIRouter(prefix="/api/v1", tags=["imagen"])

# ── Job tracker ────────────────────────────────────────
# Keyed by entity_id. Persists across hot-reloads via module-level dict.
# Each entry: {type, status, percent, message}
active_jobs: dict[str, dict] = {}

def _update_job(entity_id: str, gen_type: str, status: str, message: str = "", percent: int = 0):
    """Update or remove a job entry. COMPLETE/FAILED removes after a short delay."""
    if status in ("complete", "failed"):
        active_jobs.pop(entity_id, None)
    else:
        active_jobs[entity_id] = {
            "type": gen_type,
            "status": status,
            "percent": percent,
            "message": message,
        }


def _get_orchestrator() -> ImagenOrchestrator:
    """Lazy singleton with SSE progress callback."""
    from transversal.db.repository import EntityRepository

    repo = EntityRepository()

    async def progress_cb(entity_id, gen_type, status, message, percent):
        _update_job(entity_id, gen_type.value, status.value, message, percent)
        event_bus.publish(StreamEvent(
            event="imagen_progress",
            data={
                "entity_id": entity_id,
                "generation_type": gen_type.value,
                "status": status.value,
                "message": message,
                "percent": percent,
            },
        ))

    return ImagenOrchestrator(repository=repo, progress_callback=progress_cb)


def _run_imagen_bg(entity_id: str, universe: str):
    """Background task: generate image and publish final SSE event."""
    orchestrator = _get_orchestrator()
    try:
        logger.info(f"Starting imagen generation for {entity_id} in {universe}")
        image = asyncio.run(orchestrator.run_imagen(
            entity=EntityManager().get(entity_id),
            universe=universe,
        ))
        event_bus.publish(StreamEvent(
            event="imagen_progress",
            data={
                "entity_id": entity_id,
                "generation_type": GenerationType.IMAGEN.value,
                "status": GenerationStatus.COMPLETE.value,
                "message": f"/media/imagen/{image.filename}_large.{image.extension}",
                "percent": 100,
            },
        ))
        logger.info(f"Imagen complete for {entity_id}: {image.filename}")
        _update_job(entity_id, GenerationType.IMAGEN.value, GenerationStatus.COMPLETE.value)
    except Exception as e:
        logger.exception(f"Imagen failed for {entity_id}")
        event_bus.publish(StreamEvent(
            event="imagen_progress",
            data={
                "entity_id": entity_id,
                "generation_type": GenerationType.IMAGEN.value,
                "status": GenerationStatus.FAILED.value,
                "message": str(e),
                "percent": 0,
            },
        ))
        _cleanup_gpu(orchestrator)
        _update_job(entity_id, GenerationType.IMAGEN.value, GenerationStatus.FAILED.value)


def _run_animate_bg(entity_id: str, universe: str, duration: float, existing_image_path: str = ""):
    """Background task: generate video loop and publish final SSE event."""
    orchestrator = _get_orchestrator()
    try:
        logger.info(f"Starting animate generation for {entity_id} in {universe}")
        image = asyncio.run(orchestrator.run_animate(
            entity=EntityManager().get(entity_id),
            universe=universe,
            duration_seconds=duration,
            existing_image_path=existing_image_path,
        ))
        event_bus.publish(StreamEvent(
            event="imagen_progress",
            data={
                "entity_id": entity_id,
                "generation_type": GenerationType.ANIMATE.value,
                "status": GenerationStatus.COMPLETE.value,
                "message": f"/media/animated/{image.filename}.{image.extension}",
                "percent": 100,
            },
        ))
        logger.info(f"Animate complete for {entity_id}: {image.filename}")
        _update_job(entity_id, GenerationType.ANIMATE.value, GenerationStatus.COMPLETE.value)
    except Exception as e:
        logger.exception(f"Animate failed for {entity_id}")
        event_bus.publish(StreamEvent(
            event="imagen_progress",
            data={
                "entity_id": entity_id,
                "generation_type": GenerationType.ANIMATE.value,
                "status": GenerationStatus.FAILED.value,
                "message": str(e),
                "percent": 0,
            },
        ))
        _cleanup_gpu(orchestrator)
        _update_job(entity_id, GenerationType.ANIMATE.value, GenerationStatus.FAILED.value)


def _cleanup_gpu(orchestrator) -> None:
    """Best-effort GPU memory cleanup after failure."""
    try:
        import asyncio
        asyncio.run(orchestrator.comfyui.free_memory())
    except Exception:
        pass
    try:
        import asyncio
        asyncio.run(orchestrator.ollama.unload_model())
    except Exception:
        pass


@router.post("/imagen/{entity_id}")
async def generate_image(
    entity_id: str,
    background_tasks: BackgroundTasks,
    request: ImagenRequest | None = None,
):
    """Trigger Flux image generation for an entity (async).

    Returns 202 Accepted immediately. Progress is streamed via SSE
    events of type 'imagen_progress' with statuses:
    prompting → generating → saving → complete (or failed).
    """
    em = EntityManager()
    try:
        entity = em.get(entity_id)
    except EntityNotFoundError:
        raise HTTPException(status_code=404, detail=f"Entity '{entity_id}' not found")

    universe = entity.current_universe
    logger.info(f"Enqueuing imagen for {entity_id} ({entity.name}) in {universe}")

    background_tasks.add_task(_run_imagen_bg, entity_id, universe)

    return {"accepted": True, "entity_id": entity_id, "generation_type": "imagen"}


@router.post("/animate/{entity_id}")
async def generate_animation(
    entity_id: str,
    background_tasks: BackgroundTasks,
    request: AnimateRequest | None = None,
):
    """Trigger video loop generation for an entity (async).

    Returns 202 Accepted immediately. Progress is streamed via SSE
    events of type 'imagen_progress'.
    Pipeline: Flux static → Ollama gemma3 vision → WanVideo loop.
    """
    em = EntityManager()
    try:
        entity = em.get(entity_id)
    except EntityNotFoundError:
        raise HTTPException(status_code=404, detail=f"Entity '{entity_id}' not found")

    universe = entity.current_universe
    duration = request.duration_seconds if request else 3.0

    # Resolve existing image path if image_id provided
    existing_image_path = ""
    if request and request.image_id:
        from transversal.db.repository import EntityRepository
        repo = EntityRepository()
        img = repo.get_entity_image(request.image_id)
        if img:
            existing_image_path = f"{img.entity_id}/{img.universe}/{img.filename}_Large.{img.extension}"
            logger.info(f"Animating existing image: {existing_image_path}")

    logger.info(f"Enqueuing animate for {entity_id} ({entity.name}) in {universe}")

    background_tasks.add_task(_run_animate_bg, entity_id, universe, duration, existing_image_path)

    return {"accepted": True, "entity_id": entity_id, "generation_type": "animate"}


@router.get("/imagen/jobs")
async def list_jobs():
    """Return all active generation/animation jobs with their status."""
    return {"jobs": active_jobs}

@router.get("/imagen/{entity_id}", response_model=ImageListResponse)
async def list_images(entity_id: str, universe: str | None = None):
    """List generated images for an entity, optionally filtered by universe."""
    from transversal.db.repository import EntityRepository

    repo = EntityRepository()
    images = repo.get_entity_images(entity_id, universe=universe)

    return ImageListResponse(
        entity_id=entity_id,
        images=[
            {
                "id": img.id,
                "universe": img.universe,
                "image_type": img.image_type.value,
                "prompt": img.prompt,
                "width": img.width,
                "height": img.height,
                "created_at": img.created_at,
                "path_large": f"/media/imagen/{img.entity_id}/{img.universe}/{img.filename}_Large.{img.extension}",
                "path_animated": f"/media/animated/{img.entity_id}/{img.universe}/{img.filename}.{img.extension}" if img.image_type == ImageType.ANIMATED else "",
            }
            for img in images
        ],
    )

@router.delete("/imagen/{image_id}")
async def delete_image(image_id: str):
    """Delete a generated image and its variants."""
    orchestrator = _get_orchestrator()
    deleted = await orchestrator.delete_image(image_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Image '{image_id}' not found")
    return {"success": True}
