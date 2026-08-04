"""REST endpoints for image generation and animation.

POST /api/v1/imagen/{entity_id}  — generate a static Flux image
POST /api/v1/animate/{entity_id} — generate an animated WanVideo loop

Both endpoints publish SSE progress events during generation.
"""

from __future__ import annotations

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

router = APIRouter(prefix="/api/v1", tags=["imagen"])


def _get_orchestrator() -> ImagenOrchestrator:
    """Lazy singleton with SSE progress callback."""
    from transversal.db.repository import EntityRepository

    repo = EntityRepository()

    async def progress_cb(entity_id, gen_type, status, message, percent):
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


@router.post("/imagen/{entity_id}", response_model=ImagenResponse)
async def generate_image(
    entity_id: str,
    request: ImagenRequest | None = None,
    background_tasks: BackgroundTasks = None,
):
    """Trigger Flux image generation for an entity.

    Generates a static character/location/faction image from the entity's
    traits, filtered by its current universe. Returns immediately with
    the image metadata once complete.

    Progress is published via SSE with event type 'imagen_progress'.
    """
    em = EntityManager()
    try:
        entity = em.get(entity_id)
    except EntityNotFoundError:
        raise HTTPException(status_code=404, detail=f"Entity '{entity_id}' not found")

    universe = entity.current_universe

    orchestrator = _get_orchestrator()

    try:
        image = await orchestrator.run_imagen(
            entity=entity,
            universe=universe,
        )
        return ImagenResponse(
            success=True,
            image_id=image.id,
            path=f"/media/imagen/{image.filename}_large.{image.extension}",
            prompt=image.prompt,
            negative_prompt=image.negative_prompt,
        )
    except Exception as e:
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
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/animate/{entity_id}", response_model=ImagenResponse)
async def generate_animation(
    entity_id: str,
    request: AnimateRequest | None = None,
):
    """Trigger video loop generation for an entity.

    Pipeline: Flux static image → Ollama gemma3:12b vision → WanVideo loop.

    Progress is published via SSE with event type 'imagen_progress'.
    """
    em = EntityManager()
    try:
        entity = em.get(entity_id)
    except EntityNotFoundError:
        raise HTTPException(status_code=404, detail=f"Entity '{entity_id}' not found")

    universe = entity.current_universe

    duration = request.duration_seconds if request else 3.0
    orchestrator = _get_orchestrator()

    try:
        image = await orchestrator.run_animate(
            entity=entity,
            universe=universe,
            duration_seconds=duration,
        )
        return ImagenResponse(
            success=True,
            image_id=image.id,
            path=f"/media/animated/{image.filename}.{image.extension}",
            prompt=image.prompt,
            negative_prompt=image.negative_prompt,
        )
    except Exception as e:
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
        raise HTTPException(status_code=500, detail=str(e))


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
                "path_large": f"/media/imagen/{img.filename}_large.{img.extension}",
                "path_animated": f"/media/animated/{img.filename}.{img.extension}" if img.image_type == ImageType.ANIMATED else "",
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
