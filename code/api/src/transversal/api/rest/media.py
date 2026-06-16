"""Media upload endpoint — saves files as WebP with deterministic, collision-safe names."""

import io
import uuid
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from PIL import Image

router = APIRouter(prefix="/api/v1", tags=["media"])

MEDIA_DIR = Path("/app/media")
ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}
MAX_SIZE = 10 * 1024 * 1024  # 10 MB
WEBP_QUALITY = 85


def _convert_to_webp(data: bytes, source_ext: str) -> bytes:
    """Convert image data to WebP. SVG and GIF pass through unchanged."""
    if source_ext in (".svg",):
        return data  # SVGs are already vector — no conversion needed
    if source_ext == ".gif":
        return data  # GIFs might be animated — skip for now

    img = Image.open(io.BytesIO(data))
    if getattr(img, 'is_animated', False):
        return data  # animated WebP/GIF/APNG — pass through unchanged
    # RGBA → RGB for WebP (no alpha unless needed)
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
    else:
        img = img.convert("RGB")

    buf = io.BytesIO()
    img.save(buf, format="WEBP", quality=WEBP_QUALITY)
    return buf.getvalue()


@router.post("/media/upload")
async def upload_media(entity_id: str = "", file: UploadFile = File(...)):
    """Upload a media file. Converts to WebP, returns the public path on success.

    The file is renamed to `{entity_id}_{uuid}.webp` for uniqueness (SVG/GIF keep their extension).
    """
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)

    # Validate extension
    ext = Path(file.filename or "unknown").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )

    # Read file
    contents = await file.read()
    if len(contents) > MAX_SIZE:
        raise HTTPException(status_code=400, detail="File exceeds 10 MB limit")

    # Convert to WebP (SVG/GIF pass through)
    converted = _convert_to_webp(contents, ext)
    out_ext = ext if ext in (".svg", ".gif") else ".webp"

    # Generate a clean filename
    prefix = f"{entity_id}_" if entity_id else ""
    filename = f"{prefix}{uuid.uuid4().hex[:12]}{out_ext}"
    filepath = MEDIA_DIR / filename

    filepath.write_bytes(converted)

    return {
        "filename": filename,
        "path": f"/media/{filename}",
        "size": len(converted),
    }
