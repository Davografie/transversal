"""Media upload endpoint — saves files with deterministic, collision-safe names."""

import uuid
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile

router = APIRouter(prefix="/api/v1", tags=["media"])

MEDIA_DIR = Path("/app/media")
ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}
MAX_SIZE = 10 * 1024 * 1024  # 10 MB


@router.post("/media/upload")
async def upload_media(entity_id: str = "", file: UploadFile = File(...)):
    """Upload a media file. Returns the public path on success.

    The file is renamed to `{entity_id}_{uuid}{ext}` for uniqueness.
    """
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)

    # Validate extension
    ext = Path(file.filename or "unknown").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )

    # Read and validate size
    contents = await file.read()
    if len(contents) > MAX_SIZE:
        raise HTTPException(status_code=400, detail="File exceeds 10 MB limit")

    # Generate a clean filename
    prefix = f"{entity_id}_" if entity_id else ""
    filename = f"{prefix}{uuid.uuid4().hex[:12]}{ext}"
    filepath = MEDIA_DIR / filename

    filepath.write_bytes(contents)

    return {
        "filename": filename,
        "path": f"/media/{filename}",
        "size": len(contents),
    }
