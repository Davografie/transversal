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


#: Entity types whose pictures are **subjects** — a person or a thing — rather than
#: scenes. The same set the projection migration calls occupants ([[B214]]).
MATTE_ENTITY_TYPES = ("character", "gmc", "asset")


def wants_auto_matte(owner_kind: str, owner_type=None) -> bool:
    """Whether a picture for this owner is a subject, and so gets a matte by itself.

    A **trait**'s picture is a subject by definition (an object, a mark, a face),
    and so is an **occupant**'s. A location is a room — there is nothing to cut out
    of it — and a universe or faction is a scene too.
    """
    if owner_kind == "trait":
        return True
    value = getattr(owner_type, "value", owner_type)   # EntityType or plain string
    return str(value or "").lower() in MATTE_ENTITY_TYPES


#: Alpha at or below this counts as empty when finding a matte's subject. A
#: lossy WebP's alpha plane carries compression noise well above zero across the
#: whole canvas, so trimming on "any non-zero alpha" would find the full frame
#: and remove nothing.
TRIM_ALPHA_THRESHOLD = 8

#: A margin thinner than this fraction of a side is not worth a re-encode. It also
#: makes the trim **stable**: a lossy WebP's alpha bleeds about a pixel at the
#: edge, so trimming on an exact bounding box would shave a pixel on every pass.
TRIM_MIN_MARGIN_RATIO = 0.02


def subject_box(img: Image.Image) -> tuple[int, int, int, int] | None:
    """The box a matte's subject occupies, or None when there is none.

    Uses ``TRIM_ALPHA_THRESHOLD`` so a noisy alpha plane does not read as content.
    """
    alpha = img.getchannel("A").point(lambda v: 255 if v > TRIM_ALPHA_THRESHOLD else 0)
    return alpha.getbbox()


def trim_transparent_margins(data: bytes) -> tuple[bytes, bool]:
    """Crop an image to its subject: ``(bytes, changed)``.

    A cutout keeps the source's canvas, so a subject that filled a third of the
    frame is served at a third of the size the tier allows — a navdot or a
    portrait renders it small and floating in empty space. Trimming discards only
    transparent pixels, so nothing visible is lost, and an image whose margin is
    already thin is returned **untouched** rather than re-encoded — which costs
    quality for no gain and would let a lossy alpha edge shave a pixel per pass.
    """
    try:
        with Image.open(io.BytesIO(data)) as opened:
            img = opened.convert("RGBA")
            box = subject_box(img)
            if box is None:
                return data, False
            left, top, right, bottom = box
            if box == (0, 0, img.width, img.height):
                return data, False
            slack = round(min(img.width, img.height) * TRIM_MIN_MARGIN_RATIO)
            if left <= slack and top <= slack and right >= img.width - slack and bottom >= img.height - slack:
                return data, False   # already tight, to within what is worth doing
            buf = io.BytesIO()
            img.crop(box).save(buf, format="PNG")  # lossless intermediate
            return buf.getvalue(), True
    except Exception:
        return data, False


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


#: Which render a role prefers, and the static tier it serves at when the picture
#: has no such render. A picture can carry derived renders — a matte (``cutout``) or
#: a loop (``animated``) — alongside its static ladder, and the role decides which
#: one it gets. This is the **whole** render policy in one table; a resolver that
#: wants a URL asks the record what it has rather than retyping a tier.
#:
#: ``background`` is the only full-bleed role, so it takes the biggest static tier
#: (or the loop, whose motion is the point). ``navdot`` and ``sheet`` take the matte
#: at **their own** small tier — a matte kept only at master size would send a
#: 2048px transparent WebP for a 240px portrait.
ROLE_RENDER = {
    "background": ("animated", "XLarge"),
    "sheet": ("cutout", "Small"),
    "navdot": ("cutout", "Large"),
}

#: The static tier per role, for callers that need only a size (the ladder itself,
#: and `upscale_backgrounds`).
ROLE_VARIANT = {role: tier for role, (_, tier) in ROLE_RENDER.items()}


def render_for(role: str, renders: list[str] | None) -> tuple[str, str]:
    """``(render, tier)`` a role serves from a picture that has ``renders``.

    Falls back to the role's static tier when the preferred render is absent, which
    is why the choice can live entirely on the record: the same role means the matte
    on a cut-out picture and the plain image on one without a matte.
    """
    preferred, tier = ROLE_RENDER.get(role, ("", "Large"))
    if preferred and preferred in (renders or []):
        return preferred, tier
    return "static", tier
