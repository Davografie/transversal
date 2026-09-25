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


#: The variant ladder. Each tier is scaled to fit this **long side**, aspect
#: preserved. ``XLarge`` exists because a full-bleed location backdrop is drawn
#: at viewport size: a 1080p screen wants ~1920 device pixels and a phone held
#: portrait wants ~1170×2532, so ``Large`` (1024) was the ceiling on how sharp a
#: background could ever be. See [[Media Pipeline]] § The variant ladder.
VARIANT_LONG_SIDES = {"XLarge": 2048, "Large": 1024, "Small": 240, "Mini": 48}

#: Quality for every tier. 85 is the long-standing value; the cost curve measured
#: on real backgrounds says bytes are not the constraint (8× the pixels ≈ 1.7× the
#: bytes on this art), so this is left alone rather than traded for sharpness.
WEBP_QUALITY = 85


def save_image_variants(image_data: bytes, output_dir, base_name: str) -> dict[str, str]:
    """Write ``Original`` plus each tier of the ladder. Returns variant → filename.

    **A tier never upscales.** If the source's long side is already at or below a
    tier's cap, that tier is a copy of the source rather than an interpolation —
    inventing pixels would make the file bigger, softer and no more truthful. So
    for an 832×1216 master, ``XLarge`` is the master itself and the backdrop gets
    the full 1.0 MP that exists, rather than a resampled 2048.

    It also **always preserves the aspect ratio**, scaling to fit the long side.
    This function replaces two copies that disagreed: one scaled portraits on the
    width axis (832×1216 → 478×700, a 1.74× squeeze of *both* axes) while the
    other left anything under 1024 untouched, so the same source produced
    different files depending on which pipeline wrote it.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    img = Image.open(io.BytesIO(image_data))
    width, height = img.size
    if width == 0 or height == 0:
        raise ValueError("image has no pixels")

    # Keep alpha where the source has it — cutouts must stay transparent in
    # every tier.
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
    else:
        img = img.convert("RGB")

    long_side = max(width, height)
    filenames: dict[str, str] = {}

    tiers = [("original", None, "Original")]
    tiers += [(key.lower(), cap, key) for key, cap in VARIANT_LONG_SIDES.items()]

    for variant_key, cap, label in tiers:
        if cap is None or long_side <= cap:
            resized = img  # master, or a copy when the master is already small enough
        else:
            scale = cap / long_side
            resized = img.resize(
                (max(1, round(width * scale)), max(1, round(height * scale))),
                Image.LANCZOS,
            )
        fname = f"{base_name}_{label}.webp"
        buf = io.BytesIO()
        resized.save(buf, format="WEBP", quality=WEBP_QUALITY)
        (output_dir / fname).write_bytes(buf.getvalue())
        filenames[variant_key] = fname

    return filenames


#: Which tier each role renders from.
#:
#: ``background`` is the only full-bleed one — a location backdrop is drawn at
#: viewport size, so it takes the biggest tier there is. ``navdot`` is a map dot
#: and ``sheet`` a panel portrait; both are small on screen and would only pay
#: memory for pixels nobody sees.
ROLE_VARIANT = {"background": "XLarge", "sheet": "Small", "navdot": "Large"}
