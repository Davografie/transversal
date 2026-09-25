"""REST endpoints for image generation and animation.

POST /api/v1/imagen/{entity_id}  — trigger Flux image generation (async, returns 202)
POST /api/v1/animate/{entity_id} — trigger WanVideo loop generation (async, returns 202)

Both endpoints return immediately with 202 Accepted.
Progress is published via SSE events (event type: 'imagen_progress').
"""

from __future__ import annotations

import asyncio
import logging
import os

from fastapi import APIRouter, BackgroundTasks, Body, HTTPException

from transversal.api.sse.bus import StreamEvent, event_bus
from transversal.domain import CREDIT_ROLES, IMAGE_FLAGS, ImageType, MediaImage
from transversal.services.media_utils import ROLE_VARIANT
from transversal.imagen.orchestrator import UPSCALE_MASTER_CAP
from transversal.imagen.models import (
    AnimateRequest,
    GenerationStatus,
    GenerationType,
    ImagenRequest,
    ImagenResponse,
    ImageListResponse,
    RemoveBackgroundRequest,
)
from transversal.imagen.orchestrator import ImagenOrchestrator
from transversal.services.entity_manager import EntityManager, EntityNotFoundError

logger = logging.getLogger("transversal.imagen")
router = APIRouter(prefix="/api/v1", tags=["imagen"])

# ── Job tracker ────────────────────────────────────────
# Keyed by entity_id. Each entry: {type, status, percent, message, queued_at}
active_jobs: dict[str, dict] = {}
_job_order: list[str] = []  # submission order for queue position

def _queue_job(entity_id: str, gen_type: str):
    """Register a job as queued before it starts processing."""
    if entity_id not in active_jobs:
        _job_order.append(entity_id)
    active_jobs[entity_id] = {
        "type": gen_type,
        "status": "queued",
        "percent": 0,
        "message": "Waiting for GPU...",
    }

def _update_job(entity_id: str, gen_type: str, status: str, message: str = "", percent: int = 0):
    """Update or remove a job entry. COMPLETE/FAILED removes."""
    if status in ("complete", "failed"):
        active_jobs.pop(entity_id, None)
        if entity_id in _job_order:
            _job_order.remove(entity_id)
    else:
        active_jobs[entity_id] = {
            "type": gen_type,
            "status": status,
            "percent": percent,
            "message": message,
        }

def _job_with_queue(entity_id: str, job: dict) -> dict:
    """Attach queue_position to a job entry."""
    pos = _job_order.index(entity_id) + 1 if entity_id in _job_order and job.get("status") == "queued" else 0
    return {**job, "queue_position": pos}


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


def _run_imagen_bg(entity_id: str, universe: str, projection_id: str = ""):
    """Background task: generate image and publish final SSE event."""
    if entity_id not in active_jobs:
        logger.info(f"Imagen for {entity_id} was cancelled before starting — skipping")
        return
    orchestrator = _get_orchestrator()
    try:
        logger.info(f"Starting imagen generation for {entity_id} in {universe} (projection={projection_id or 'entity'})")
        image = asyncio.run(orchestrator.run_imagen(
            entity=EntityManager().get(entity_id),
            universe=universe,
            projection_id=projection_id,
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


def _run_upscale_bg(owner_id: str, image_id: str):
    """Background task: ESRGAN detail pass on one image's master."""
    if owner_id not in active_jobs:
        logger.info(f"Upscale for {owner_id} was cancelled before starting — skipping")
        return
    orchestrator = _get_orchestrator()
    try:
        image = asyncio.run(orchestrator.run_upscale(image_id))
        event_bus.publish(StreamEvent(
            event="imagen_progress",
            data={
                "entity_id": owner_id,
                "generation_type": GenerationType.UPSCALE.value,
                "status": GenerationStatus.COMPLETE.value,
                "message": f"{image.width}x{image.height}",
                "percent": 100,
            },
        ))
        logger.info(f"Upscale complete for {image_id}: {image.width}x{image.height}")
        _update_job(owner_id, GenerationType.UPSCALE.value, GenerationStatus.COMPLETE.value)
    except Exception as e:
        logger.exception(f"Upscale failed for {image_id}")
        event_bus.publish(StreamEvent(
            event="imagen_progress",
            data={
                "entity_id": owner_id,
                "generation_type": GenerationType.UPSCALE.value,
                "status": GenerationStatus.FAILED.value,
                "message": str(e),
                "percent": 0,
            },
        ))
        _cleanup_gpu(orchestrator)
        _update_job(owner_id, GenerationType.UPSCALE.value, GenerationStatus.FAILED.value)


def _run_animate_bg(entity_id: str, universe: str, duration: float, source_image_id: str = "", motion_hint: str = ""):
    """Background task: generate video loop and publish final SSE event."""
    if entity_id not in active_jobs:
        logger.info(f"Animate for {entity_id} was cancelled before starting — skipping")
        return
    orchestrator = _get_orchestrator()
    try:
        logger.info(f"Starting animate generation for {entity_id} in {universe}")
        image = asyncio.run(orchestrator.run_animate(
            entity=EntityManager().get(entity_id),
            universe=universe,
            duration_seconds=duration,
            source_image_id=source_image_id,
            motion_hint=motion_hint,
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


def _run_remove_bg_bg(entity_id: str, image_id: str, display_name: str = ""):
    """Background task: remove the background from a static image.

    ``entity_id`` is the owner id and the progress key — an entity or a trait,
    whichever asked. The cutout's owner comes from the *source image*, not from
    here.
    """
    if entity_id not in active_jobs:
        logger.info(f"Background removal for {entity_id} was cancelled before starting — skipping")
        return
    orchestrator = _get_orchestrator()
    try:
        image = asyncio.run(orchestrator.run_remove_background(
            owner_id=entity_id,
            image_id=image_id,
            display_name=display_name,
        ))
        event_bus.publish(StreamEvent(
            event="imagen_progress",
            data={
                "entity_id": entity_id,
                "generation_type": GenerationType.REMOVE_BG.value,
                "status": GenerationStatus.COMPLETE.value,
                "message": f"/media/imagen/{image.filename}_large.{image.extension}",
                "percent": 100,
            },
        ))
        logger.info(f"Background removal complete for {entity_id}: {image.filename}")
        _update_job(entity_id, GenerationType.REMOVE_BG.value, GenerationStatus.COMPLETE.value)
    except Exception as e:
        logger.exception(f"Background removal failed for {entity_id}")
        event_bus.publish(StreamEvent(
            event="imagen_progress",
            data={
                "entity_id": entity_id,
                "generation_type": GenerationType.REMOVE_BG.value,
                "status": GenerationStatus.FAILED.value,
                "message": str(e),
                "percent": 0,
            },
        ))
        _cleanup_gpu(orchestrator)
        _update_job(entity_id, GenerationType.REMOVE_BG.value, GenerationStatus.FAILED.value)


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

    projection_id = (request.projection_id if request else "") or ""
    universe = entity.current_universe
    if projection_id:
        proj = em.repo.get_projection(projection_id)
        if proj is None or proj.entity_id != entity_id:
            raise HTTPException(
                status_code=404,
                detail=f"Projection '{projection_id}' not found for entity '{entity_id}'",
            )
        universe = proj.universe or universe

    logger.info(f"Enqueuing imagen for {entity_id} ({entity.name}) in {universe} (projection={projection_id or 'entity'})")

    _queue_job(entity_id, GenerationType.IMAGEN.value)
    background_tasks.add_task(_run_imagen_bg, entity_id, universe, projection_id)

    return {
        "accepted": True,
        "entity_id": entity_id,
        "projection_id": projection_id or None,
        "generation_type": "imagen",
    }


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

    # Animating an existing image: pass the id and let the orchestrator read the
    # record. Building the path here instead is how the owner_id/entity_id split
    # was missed in the first place.
    source_image_id = ""
    if request and request.image_id:
        from transversal.db.repository import EntityRepository
        repo = EntityRepository()
        img = repo.get_image(request.image_id)
        if img:
            source_image_id = img.id
            logger.info(f"Animating existing image {img.id} (transparent={img.transparent})")

    logger.info(f"Enqueuing animate for {entity_id} ({entity.name}) in {universe}")

    _queue_job(entity_id, GenerationType.ANIMATE.value)
    motion_hint = request.motion_hint if request else ""
    background_tasks.add_task(_run_animate_bg, entity_id, universe, duration, source_image_id, motion_hint)

    return {"accepted": True, "entity_id": entity_id, "generation_type": "animate"}


@router.post("/remove-background/{owner_id}")
async def remove_background(
    owner_id: str,
    background_tasks: BackgroundTasks,
    owner_kind: str = "entity",
    request: RemoveBackgroundRequest | None = None,
):
    """Remove the background from an existing static image (async).

    Works for any image **owner**: an entity (`owner_kind=entity`, the default —
    what the image viewer sends) or a registry trait (`owner_kind=trait`).
    Produces a new transparent cutout image owned by the same owner *and the same
    tier* as the source; the source is untouched.

    Progress streams via SSE `imagen_progress` keyed by `owner_id`, and
    `GET /imagen/jobs` is keyed the same way — so a trait's picture is cut out
    under the trait's id exactly as an entity's is under its own.
    """
    from transversal.db.repository import EntityRepository

    if owner_kind not in ("entity", "trait"):
        raise HTTPException(status_code=400, detail="owner_kind must be 'entity' or 'trait'")

    repo = EntityRepository()
    if owner_kind == "entity":
        em = EntityManager()
        try:
            owner = em.get(owner_id)
        except EntityNotFoundError:
            raise HTTPException(status_code=404, detail=f"Entity '{owner_id}' not found")
    else:
        owner = repo.get_trait(owner_id)
        if owner is None:
            raise HTTPException(status_code=404, detail=f"Trait '{owner_id}' not found")

    if not request or not request.image_id:
        raise HTTPException(status_code=400, detail="image_id is required")

    img = repo.get_image(request.image_id)
    if not img:
        raise HTTPException(status_code=404, detail=f"Image '{request.image_id}' not found")
    if img.image_type == ImageType.ANIMATED:
        raise HTTPException(status_code=400, detail="Background removal only works on static images")
    if img.owner_id != owner_id:
        raise HTTPException(status_code=400, detail=f"Image '{request.image_id}' does not belong to '{owner_id}'")

    owner_name = getattr(owner, "name", "")
    logger.info(f"Enqueuing background removal for {owner_kind} {owner_id} ({owner_name}) from image {request.image_id}")

    _queue_job(owner_id, GenerationType.REMOVE_BG.value)
    background_tasks.add_task(_run_remove_bg_bg, owner_id, request.image_id, owner_name)

    return {"accepted": True, "owner_id": owner_id, "generation_type": "remove_bg"}


@router.post("/upscale/{image_id}")
async def upscale_image(image_id: str, background_tasks: BackgroundTasks):
    """Upscale one image's master and re-render its tiers (async).

    Offered per image rather than run as a batch: the point is to spend the GPU
    only on pictures that need it, from the surface where you are already looking
    at the picture. Refused when there is nothing to gain — a loop has no tiers,
    and a master already at the ceiling cannot get bigger than what is served.

    Progress streams via SSE `imagen_progress` and `GET /imagen/jobs`, both keyed
    by the image's **owner**, so the gallery that offered the button polls for it
    exactly as it does for a cutout.
    """
    from transversal.db.repository import EntityRepository

    repo = EntityRepository()
    img = repo.get_image(image_id)
    if not img:
        raise HTTPException(status_code=404, detail=f"Image '{image_id}' not found")
    if img.image_type == ImageType.ANIMATED:
        raise HTTPException(status_code=400, detail="Upscaling works on still images; a loop has no tiers")
    if img.width and img.height and max(img.width, img.height) >= UPSCALE_MASTER_CAP:
        raise HTTPException(
            status_code=400,
            detail=f"Already at the {UPSCALE_MASTER_CAP}px ceiling ({img.width}x{img.height})",
        )

    logger.info(f"Enqueuing upscale for image {image_id} (owner {img.owner_id})")
    _queue_job(img.owner_id, GenerationType.UPSCALE.value)
    background_tasks.add_task(_run_upscale_bg, img.owner_id, image_id)

    return {"accepted": True, "image_id": image_id, "owner_id": img.owner_id,
            "generation_type": GenerationType.UPSCALE.value}


@router.post("/imagen/{entity_id}/cancel")
async def cancel_job(entity_id: str):
    """Interrupt an active imagen/animate job for an entity."""
    job = active_jobs.get(entity_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"No active job for entity '{entity_id}'")

    orchestrator = _get_orchestrator()
    try:
        await orchestrator.comfyui.interrupt()
        await orchestrator.comfyui.free_memory()
    except Exception:
        pass  # best-effort interrupt

    _update_job(entity_id, job["type"], "failed", "Cancelled by user")
    event_bus.publish(StreamEvent(
        event="imagen_progress",
        data={
            "entity_id": entity_id,
            "generation_type": job["type"],
            "status": GenerationStatus.FAILED.value,
            "message": "Cancelled by user",
            "percent": 0,
        },
    ))
    return {"cancelled": True, "entity_id": entity_id}

@router.get("/imagen/jobs")
async def list_jobs():
    """Return all active generation/animation jobs with status and queue position."""
    return {"jobs": {eid: _job_with_queue(eid, j) for eid, j in active_jobs.items()}}

@router.get("/imagen/loras")
async def list_loras():
    """List available Flux LoRA files from the imagEN LoRA server."""
    orchestrator = _get_orchestrator()
    try:
        loras = await orchestrator.comfyui.list_loras()
        return {"loras": loras}
    except Exception:
        return {"loras": []}

@router.get("/entities/images")
async def entity_images_batch(role: str = "sheet", ids: str = ""):
    """Resolve one role image URL per entity in a single batch query.

    Used by the frontend peers bar to resolve sheet images lazily for just the
    entities at the current location, instead of loading images for the whole
    entity list.
    """
    entity_ids = [i for i in (s.strip() for s in ids.split(",")) if i]
    if not entity_ids:
        return {"images": {}}
    from transversal.db.repository import EntityRepository

    variant = ROLE_VARIANT.get(role, "Large")
    images = EntityRepository().get_role_images(entity_ids, role, variant)
    return {"images": images}

def _validated_credits(raw) -> list[dict]:
    """Validate credit rows. Raises 400 on a bad role or a non-http(s) URL.

    The URLs end up as links the UI renders, so the scheme is checked rather than
    trusted: an unchecked one is a stored-XSS vector, the same class of problem
    that got `.svg` removed from uploads (SEC-4). Blank rows are dropped, so an
    empty row in the editor does not have to be a special case.
    """
    if not isinstance(raw, list):
        raise HTTPException(status_code=400, detail="credits must be a list")
    if len(raw) > 20:
        raise HTTPException(status_code=400, detail="too many credits (max 20)")

    out: list[dict] = []
    for entry in raw:
        if not isinstance(entry, dict):
            raise HTTPException(status_code=400, detail="each credit must be an object")
        role = str(entry.get("role") or "artist").strip()
        if role not in CREDIT_ROLES:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown credit role '{role}'. Allowed: {', '.join(CREDIT_ROLES)}",
            )
        url = str(entry.get("url") or "").strip()
        if url and not url.lower().startswith(("http://", "https://")):
            raise HTTPException(
                status_code=400,
                detail="credit url must start with http:// or https://",
            )
        name = str(entry.get("name") or "").strip()
        if name or url:
            out.append({"role": role, "name": name[:200], "url": url[:500]})
    return out


@router.get("/imagen/{entity_id}", response_model=ImageListResponse)
async def list_images(entity_id: str, universe: str | None = None):
    """List generated images for an entity, optionally filtered by universe."""
    from transversal.db.repository import EntityRepository

    repo = EntityRepository()
    images = repo.get_images(entity_id, universe=universe)

    # Resolve universe display names from universe entities
    universe_names: dict[str, str] = {}
    for doc in repo._entities.find({"type": "universe"}):
        universe_names[doc.get("current_universe", doc["_key"])] = doc.get("name", doc["_key"])

    def _file_size(img: MediaImage) -> int:
        try:
            if img.image_type == ImageType.ANIMATED:
                path = f"/app/media/animated/{img.owner_id}/{img.universe}/{img.filename}.{img.extension}"
            else:
                path = f"/app/media/imagen/{img.owner_id}/{img.universe}/{img.filename}_Large.{img.extension}"
            return os.path.getsize(path)
        except OSError:
            return 0

    return ImageListResponse(
        entity_id=entity_id,
        images=[
            {
                "id": img.id,
                "universe": img.universe,
                "universe_label": universe_names.get(img.universe, img.universe),
                "image_type": img.image_type.value,
                "projection_id": img.projection_id,
                "variant_id": img.variant_id,
                "prompt": img.prompt,
                "width": img.width,
                "height": img.height,
                "created_at": img.created_at,
                "size_bytes": _file_size(img),
                "roles": img.roles,
                "transparent": img.transparent,
                "flags": img.flags,
                "credits": [c.model_dump() for c in img.credits],
                "license": img.license,
                "credit_text": img.credit_text,
                "path_large": f"/media/imagen/{img.owner_id}/{img.universe}/{img.filename}_Large.{img.extension}",
                "path_xlarge": f"/media/imagen/{img.owner_id}/{img.universe}/{img.filename}_XLarge.{img.extension}",
                # What an "Upscale" button needs to know: is there anything left
                # to gain, and has this one already been through the pass?
                "can_upscale": bool(
                    img.image_type != ImageType.ANIMATED
                    and max(img.width, img.height) < UPSCALE_MASTER_CAP
                ),
                "upscaled": os.path.exists(
                    f"/app/media/imagen/{img.owner_id}/{img.universe}/"
                    f"{img.filename}_PreUpscale.{img.extension}"
                ),
                "path_animated": f"/media/animated/{img.owner_id}/{img.universe}/{img.filename}.{img.extension}" if img.image_type == ImageType.ANIMATED else "",
            }
            for img in images
        ],
    )

@router.patch("/imagen/{image_id}")
async def update_image_roles(image_id: str, payload: dict = Body(...)):
    """Update an image's roles, universe, and/or owning projection.

    Roles are unique per (owner, role), where the owner is the image's
    projection when set, else the entity. Assigning a role removes it from
    any other image with the same owner. ``projection_id`` (string or null)
    reassigns ownership: null/empty clears it back to the entity.
    """
    from transversal.db.repository import EntityRepository
    repo = EntityRepository()

    img = repo.get_image(image_id)
    if not img:
        raise HTTPException(status_code=404, detail=f"Image '{image_id}' not found")

    updates: dict = {}

    # ── Roles (owner-scoped uniqueness) ──
    if "roles" in payload and isinstance(payload.get("roles"), list):
        new_roles = set(payload["roles"])
        old_roles = set(img.roles)
        added = new_roles - old_roles
        if added:
            siblings = repo.get_images_for_owner(img.owner_id, img.variant_id)
            for sib in siblings:
                if sib.id == image_id:
                    continue
                sib_roles = [r for r in sib.roles if r not in added]
                if sib_roles != sib.roles:
                    repo.update_image(sib.id, {"roles": sib_roles})
        updates["roles"] = payload["roles"]

    # ── Provenance flags (independent of roles) ──
    # No sibling stripping here, on purpose: a provenance label describes how an
    # image was made, so many images of one owner can carry it at once. Only the
    # vocabulary is enforced.
    if "flags" in payload:
        new_flags = payload.get("flags") or []
        if not isinstance(new_flags, list):
            raise HTTPException(status_code=400, detail="flags must be a list")
        unknown = [f for f in new_flags if f not in IMAGE_FLAGS]
        if unknown:
            raise HTTPException(status_code=400, detail=f"Unknown image flag(s): {', '.join(unknown)}")
        updates["flags"] = new_flags

    # ── Credits: where the artwork came from (TASL's Author and Source) ──
    # Structured parties plus an optional verbatim line. Like flags, independent
    # of roles: many images of one owner may credit the same artist.
    if "credits" in payload:
        updates["credits"] = _validated_credits(payload.get("credits"))
    if "license" in payload:
        updates["license"] = str(payload.get("license") or "").strip()[:200]
    if "credit_text" in payload:
        updates["credit_text"] = str(payload.get("credit_text") or "").strip()[:1000]

    # ── Ownership tier (the variant below the owner) ──
    # `projection_id` is the long-standing request field and is still accepted;
    # `variant_id` is the generalised name (a projection for an entity, a
    # traitsetting for a trait). Either way the model syncs the legacy pair.
    if "variant_id" in payload or "projection_id" in payload:
        new_owner = payload.get("variant_id", payload.get("projection_id"))
        updates["variant_id"] = new_owner or None

    # ── Auto-select all three roles when a drop leaves the image as the
    # sole image for its (new) owner (entity or projection). This is a drop
    # (ownership tier present, roles absent) landing in an empty owner scope.
    if ("variant_id" in payload or "projection_id" in payload) and "roles" not in payload:
        owner = payload.get("variant_id", payload.get("projection_id")) or None
        others = [s for s in repo.get_images_for_owner(img.owner_id, owner) if s.id != image_id]
        if not others:
            updates["roles"] = ["background", "sheet", "navdot"]

    # ── Universe (and file move) ──
    new_universe = payload.get("universe")
    if new_universe and new_universe != img.universe:
        updates["universe"] = new_universe

        # Move files to new universe directory
        import shutil
        for base in ("/app/media/imagen", "/app/media/animated"):
            old_dir = f"{base}/{img.owner_id}/{img.universe}"
            new_dir = f"{base}/{img.owner_id}/{new_universe}"
            if os.path.isdir(old_dir):
                os.makedirs(os.path.dirname(new_dir), exist_ok=True)
                shutil.move(old_dir, new_dir)

    if not updates:
        return {
            "success": True, "roles": img.roles, "universe": img.universe,
            "projection_id": img.projection_id, "flags": img.flags,
            "credits": [c.model_dump() for c in img.credits],
            "license": img.license, "credit_text": img.credit_text,
        }

    updated = repo.update_image(image_id, updates)

    return {
        "success": True,
        "roles": updated.roles if updated else img.roles,
        "universe": updated.universe if updated else img.universe,
        "projection_id": updated.projection_id if updated else img.projection_id,
        "flags": updated.flags if updated else img.flags,
        "credits": [c.model_dump() for c in (updated or img).credits],
        "license": (updated or img).license,
        "credit_text": (updated or img).credit_text,
    }


@router.delete("/imagen/{image_id}")
async def delete_image(image_id: str):
    """Delete a generated image and its variants."""
    orchestrator = _get_orchestrator()
    deleted = await orchestrator.delete_image(image_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Image '{image_id}' not found")
    return {"success": True}
