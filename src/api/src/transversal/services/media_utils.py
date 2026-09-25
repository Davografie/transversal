"""Small shared helpers for media file processing."""

from __future__ import annotations

import io

from PIL import Image


def has_transparency(data: bytes) -> bool:
    """Return True if the image has an alpha channel with any non-opaque pixel.

    Used to tag ``MediaImage.transparent`` at ingestion time (uploads,
    generated cutouts). Opaque formats (JPEG, Flux PNG output) return False.
    """
    try:
        with Image.open(io.BytesIO(data)) as img:
            if img.mode not in ("RGBA", "LA", "PA") and "transparency" not in img.info:
                return False
            rgba = img.convert("RGBA")
            return rgba.getchannel("A").getextrema()[0] < 255
    except Exception:
        return False
