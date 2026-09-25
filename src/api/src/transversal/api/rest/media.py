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
async def upload_media(
    owner_id: str = "",
    owner_kind: str = "entity",
    variant_id: str = "",
    universe: str = "",
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

    If `universe` is provided, the image is registered under that universe.
    If empty, the owner's own universe is used — an entity's `current_universe`,
    or a trait's first listed universe.
    """
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)

    entity_id = entity_id or ""
    owner_id = owner_id or entity_id
    variant_id = variant_id or projection_id or ""

    if owner_kind not in ("entity", "trait"):
        raise HTTPException(status_code=400, detail="owner_kind must be 'entity' or 'trait'")

    # These all become path components below — validate before anything
    # touches disk.
    owner_id = _safe_component(owner_id, "owner_id") if owner_id else ""
    universe = _safe_component(universe, "universe") if universe else ""
    variant_id = _safe_component(variant_id, "variant_id") if variant_id else ""

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
        except Exception:
            pass  # Don't fail the upload if image registration fails

    return {
        "filename": flat_filename,
        "path": f"/media/{flat_filename}",
        "size": len(converted),
        "image_id": image_id,
    }
