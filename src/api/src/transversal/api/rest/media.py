"""Media upload endpoint — saves files as WebP with deterministic, collision-safe names.

Uploaded images are also registered as MediaImage records so they appear in the
gallery alongside generated images and can be animated.
"""

import io
import logging
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile

logger = logging.getLogger("transversal.media")
from PIL import Image

# Optional HEIC/HEIF support (iOS camera photos). Registers a PIL opener so
# Image.open can decode .heic/.heif. Guarded so the app still starts if the
# wheel is unavailable (HEIC uploads then fail at conversion, as before).
try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
except ImportError:
    pass

from transversal.domain import IMAGE_FLAGS, ImageType, MediaImage
from transversal.db.repository import EntityRepository
from transversal.services.media_utils import (
    has_transparency,
    wants_auto_matte,
    save_image_variants as _save_image_variants,
)

router = APIRouter(prefix="/api/v1", tags=["media"])

MEDIA_DIR = Path("/app/media")
IMAGEN_DIR = MEDIA_DIR / "imagen"
# `.svg` is deliberately absent: it is passed through un-re-encoded, served
# from the app's own origin, and can carry script — i.e. stored XSS (SEC-4).
ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".heic", ".heif"}
MAX_SIZE = 10 * 1024 * 1024  # 10 MB
WEBP_QUALITY = 85

#: Request-supplied values that become filesystem path components must match
#: this exactly — no separators, no `..`, no leading dot, no control characters
#: (SEC-4).
_SAFE_COMPONENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def _safe_component(value: str, field: str) -> str:
    """Validate a request value that will be used in a path. Raises 400."""
    if not _SAFE_COMPONENT.match(value):
        raise HTTPException(status_code=400, detail=f"Invalid {field}")
    return value


#: A **record id**, not a path component: a projection id or a traitsetting id.
#: Real ids contain colons (`faction-44351398:trait-description`), so the path
#: pattern above cannot be used — but the value is stored and echoed back in the
#: image list, so it is still bounded and free of control characters.
_SAFE_RECORD_ID = re.compile(r"^[^\x00-\x1f\x7f]{1,200}$")


def _safe_record_id(value: str, field: str) -> str:
    """Validate a request value that is an id, never a filename. Raises 400."""
    if not _SAFE_RECORD_ID.match(value):
        raise HTTPException(status_code=400, detail=f"Invalid {field}")
    return value


def _enqueue_matte(
    background_tasks: BackgroundTasks, owner_id: str, image_id: str, display_name: str
) -> None:
    """Queue the automatic matte for a freshly uploaded occupant/trait picture.

    Imported inside the function on purpose: the job registry and the background
    task live in `rest/imagen.py`, and reaching for them at module scope would tie
    the two routers together in an import cycle.
    """
    from transversal.api.rest.imagen import _queue_job, _run_remove_bg_bg
    from transversal.imagen.models import GenerationType

    _queue_job(owner_id, GenerationType.REMOVE_BG.value)
    background_tasks.add_task(_run_remove_bg_bg, owner_id, image_id, display_name)


def _parse_flags(raw: str) -> list[str]:
    """Parse a comma-separated provenance flag list. Raises 400 on an unknown one.

    A fixed vocabulary rather than free text: these labels are read by the UI and
    by anything deciding whether an image involved AI, so a typo would silently
    mean "no disclosure" instead of failing.
    """
    values = [f.strip() for f in (raw or "").split(",") if f.strip()]
    unknown = [f for f in values if f not in IMAGE_FLAGS]
    if unknown:
        raise HTTPException(status_code=400, detail=f"Unknown image flag(s): {', '.join(unknown)}")
    return values


def _convert_to_webp(data: bytes, source_ext: str) -> bytes:
    """Convert image data to WebP. GIFs pass through unchanged (animation)."""
    if source_ext == ".gif":
        return data

    img = Image.open(io.BytesIO(data))
    if getattr(img, 'is_animated', False):
        return data
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
    else:
        img = img.convert("RGB")

    buf = io.BytesIO()
    img.save(buf, format="WEBP", quality=WEBP_QUALITY)
    return buf.getvalue()




@router.post("/media/upload")
async def upload_media(
    background_tasks: BackgroundTasks,
    owner_id: str = "",
    owner_kind: str = "entity",
    variant_id: str = "",
    universe: str = "",
    flags: str = "",  # comma-separated IMAGE_FLAGS, e.g. "ai" for known-AI art
    entity_id: str = "",  # legacy alias for owner_id, still sent by existing callers
    projection_id: str = "",  # legacy alias for variant_id
    file: UploadFile = File(...),
):
    """Upload a media file. Converts to WebP, returns the public path on success.

    Also registers the image as a MediaImage so it appears in the gallery
    and can be animated.

    The owner is an **entity** or a **trait** (`owner_kind` + `owner_id`), and
    the image may sit on the tier below it (`variant_id` — a projection or a
    traitsetting); empty means the owner-level *definition* image.

    ``flags`` carries provenance labels (`IMAGE_FLAGS`) — ``ai`` is the one a
    human sets, for art whose workflow they know involved AI. The pipeline labels
    are set by the pipelines themselves, never here.

    If `universe` is provided, the image is registered under that universe.
    If empty, the owner's own universe is used — an entity's `current_universe`,
    or a trait's first listed universe.
    """
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)

    entity_id = entity_id or ""
    owner_id = owner_id or entity_id
    variant_id = variant_id or projection_id or ""
    requested_flags = _parse_flags(flags)

    if owner_kind not in ("entity", "trait"):
        raise HTTPException(status_code=400, detail="owner_kind must be 'entity' or 'trait'")

    # Only these two become path components below — validate before anything
    # touches disk. `variant_id` names no file, so it is validated as a record id
    # instead (see `_safe_record_id`): the path rules rejected the colons every
    # real projection and traitsetting id contains, which made a per-instance
    # upload impossible.
    owner_id = _safe_component(owner_id, "owner_id") if owner_id else ""
    universe = _safe_component(universe, "universe") if universe else ""
    variant_id = _safe_record_id(variant_id, "variant_id") if variant_id else ""

    ext = Path(file.filename or "unknown").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )

    contents = await file.read()
    if len(contents) > MAX_SIZE:
        raise HTTPException(status_code=400, detail="File exceeds 10 MB limit")

    converted = _convert_to_webp(contents, ext)
    out_ext = ext if ext == ".gif" else ".webp"

    # Original flat-file path (backward compat)
    prefix = f"{owner_id}_" if owner_id else ""
    flat_filename = f"{prefix}{uuid.uuid4().hex[:12]}{out_ext}"
    filepath = MEDIA_DIR / flat_filename
    filepath.write_bytes(converted)

    # ── Register as MediaImage for gallery + animation ──
    image_id = None
    if owner_id:
        try:
            repo = EntityRepository()
            owner = (
                repo.get_entity(owner_id) if owner_kind == "entity"
                else repo.get_trait(owner_id)
            )
            if owner:
                # Also a path component. The stored value is validated too, so a
                # bad universe already in the data cannot traverse either.
                #
                # A trait has no single `current_universe` — it lists the
                # universes it belongs to — so its first is the default. The 9
                # live traits with an empty list need the caller to name one.
                default_universe = (
                    owner.current_universe if owner_kind == "entity"
                    else (owner.universes[0] if owner.universes else "")
                )
                if not (universe or default_universe):
                    # A trait can belong to no universe, and then there is no
                    # directory to file the image under. Registration is skipped
                    # rather than raising: the flat file is already written and a
                    # missing gallery row must not fail the upload (SEC-4 keeps
                    # the stored-value guard on this same best-effort footing).
                    # The caller sees `image_id: null`.
                    owner = None
                if owner:
                    resolved_universe = _safe_component(
                        universe or default_universe, "universe"
                    )
                    image_id = uuid.uuid4().hex[:8]
                    output_dir = IMAGEN_DIR / owner_id / resolved_universe
                    base_name = f"upload_{image_id}"

                    _save_image_variants(converted, output_dir, base_name)

                    img = Image.open(io.BytesIO(converted))
                    w, h = img.size

                    image = MediaImage(
                        id=image_id,
                        owner_kind=owner_kind,
                        owner_id=owner_id,
                        variant_id=variant_id or None,
                        universe=resolved_universe,
                        image_type=ImageType.UPLOADED,
                        flags=requested_flags,
                        transparent=has_transparency(converted),
                        width=w,
                        height=h,
                        filename=base_name,
                        extension="webp",
                        created_at=datetime.now(timezone.utc).isoformat(),
                    )
                    repo.create_image(image)

                    # Auto-select all three roles when this upload is the sole
                    # image on its rung — the soul default for every role, and for
                    # a trait the one picture that renders wherever it is asked.
                    owner_images = repo.get_images_for_owner(owner_id, variant_id or None)
                    if len(owner_images) == 1:
                        repo.update_image(image_id, {"roles": ["background", "sheet", "navdot"]})

                    # An occupant's or a trait's picture is a subject, so it gets a
                    # matte as part of becoming one ([[B214]]). **Queued, not
                    # awaited**: an upload response must not wait on the GPU, and
                    # the gallery already polls `/imagen/jobs` for this owner, so
                    # the matte appears on its own a few seconds later.
                    if wants_auto_matte(owner_kind, getattr(owner, "type", None)):
                        _enqueue_matte(
                            background_tasks, owner_id, image_id,
                            getattr(owner, "name", ""),
                        )
        except Exception:
            # Registration is best-effort: the file is already written and a
            # missing gallery row must not fail the upload. But it is *logged* —
            # a bare `pass` here is how a failing matte enqueue hid itself.
            logger.exception("Image registration failed for %s (%s)", owner_kind, owner_id)

    return {
        "filename": flat_filename,
        "path": f"/media/{flat_filename}",
        "size": len(converted),
        "image_id": image_id,
    }
