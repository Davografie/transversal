"""Media upload endpoint — saves files as WebP with deterministic, collision-safe names.

Uploaded images are also registered as MediaImage records so they appear in the
gallery alongside generated images and can be animated.
"""

import io
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from PIL import Image

# Optional HEIC/HEIF support (iOS camera photos). Registers a PIL opener so
# Image.open can decode .heic/.heif. Guarded so the app still starts if the
# wheel is unavailable (HEIC uploads then fail at conversion, as before).
try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
except ImportError:
    pass

from transversal.domain import MediaImage, ImageType
from transversal.db.repository import EntityRepository
from transversal.services.media_utils import has_transparency

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


def _save_image_variants(image_data: bytes, output_dir: Path, base_name: str) -> str:
    """Save original + 3 variant sizes as webp. Returns the large variant filename."""
    output_dir.mkdir(parents=True, exist_ok=True)
    img = Image.open(io.BytesIO(image_data))
    width, height = img.size

    variants = {
        "original": (width, height, "Original"),
        "large": (min(width, 1024), int(min(width, 1024) / width * height) if width > height else int(min(height, 1024) / height * width), "Large"),
        "small": (min(width, 240), int(min(width, 240) / width * height) if width > height else int(min(height, 240) / height * width), "Small"),
        "mini": (min(width, 48), int(min(width, 48) / width * height) if width > height else int(min(height, 48) / height * width), "Mini"),
    }

    for variant_key, (w, h, label) in variants.items():
        if variant_key == "original" or (w < width and h < height):
            resized = img.resize((w, h), Image.LANCZOS)
        else:
            resized = img
        fname = f"{base_name}_{label}.webp"
        buf = io.BytesIO()
        resized.save(buf, format="WEBP", quality=85)
        (output_dir / fname).write_bytes(buf.getvalue())

    return f"{base_name}_Large.webp"


@router.post("/media/upload")
async def upload_media(entity_id: str = "", universe: str = "", file: UploadFile = File(...)):
    """Upload a media file. Converts to WebP, returns the public path on success.

    Also registers the image as an MediaImage so it appears in the gallery
    and can be animated.

    If `universe` is provided, the image is registered under that universe.
    If empty, the entity's current universe is used.
    """
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)

    # These both become path components below — validate before anything
    # touches disk.
    entity_id = _safe_component(entity_id, "entity_id") if entity_id else ""
    universe = _safe_component(universe, "universe") if universe else ""

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
    prefix = f"{entity_id}_" if entity_id else ""
    flat_filename = f"{prefix}{uuid.uuid4().hex[:12]}{out_ext}"
    filepath = MEDIA_DIR / flat_filename
    filepath.write_bytes(converted)

    # ── Register as MediaImage for gallery + animation ──
    image_id = None
    if entity_id:
        try:
            repo = EntityRepository()
            entity = repo.get_entity(entity_id)
            if entity:
                # Also a path component. The stored value is validated too, so a
                # bad universe already in the data cannot traverse either.
                resolved_universe = _safe_component(
                    universe or entity.current_universe, "universe"
                )
                image_id = uuid.uuid4().hex[:8]
                output_dir = IMAGEN_DIR / entity_id / resolved_universe
                base_name = f"upload_{image_id}"

                _save_image_variants(converted, output_dir, base_name)

                img = Image.open(io.BytesIO(converted))
                w, h = img.size

                entity_image = MediaImage(
                    id=image_id,
                    entity_id=entity_id,
                    universe=resolved_universe,
                    image_type=ImageType.UPLOADED,
                    transparent=has_transparency(converted),
                    width=w,
                    height=h,
                    filename=base_name,
                    extension="webp",
                    created_at=datetime.now(timezone.utc).isoformat(),
                )
                repo.create_entity_image(entity_image)

                # Auto-select all three roles when this upload is the sole
                # entity-level image (the soul default for every role).
                owner_images = repo.get_images_for_owner(entity_id, None)
                if len(owner_images) == 1:
                    repo.update_entity_image(image_id, {"roles": ["background", "sheet", "navdot"]})
        except Exception:
            pass  # Don't fail the upload if image registration fails

    return {
        "filename": flat_filename,
        "path": f"/media/{flat_filename}",
        "size": len(converted),
        "image_id": image_id,
    }
