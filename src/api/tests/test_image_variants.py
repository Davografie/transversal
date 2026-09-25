"""The variant ladder (`B206`).

Every tier is scaled to fit a **long side**, aspect preserved, and **never
upscaled**. This file exists because the two copies of this logic that used to
exist disagreed: one squeezed portraits on the width axis (832×1216 → 478×700)
while the other left them alone, so the same source produced different files
depending on which pipeline wrote it.
"""

import io

import pytest
from PIL import Image

from transversal.services.media_utils import ROLE_VARIANT, save_image_variants


def _source(width, height, mode="RGB"):
    img = Image.new(mode, (width, height), (120, 90, 60) if mode == "RGB" else (120, 90, 60, 128))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _write(tmp_path, data, base="probe"):
    return save_image_variants(data, tmp_path, base)


def _dims(tmp_path, name):
    with Image.open(tmp_path / name) as im:
        return im.size


def test_every_tier_is_written(tmp_path):
    names = _write(tmp_path, _source(832, 1216))
    assert set(names) == {"original", "xlarge", "large", "small", "mini"}
    for name in names.values():
        assert (tmp_path / name).exists()


def test_a_tier_never_upscales(tmp_path):
    """An 832×1216 master has 1.0 MP; XLarge must hand that over as-is rather
    than interpolate to 2048 — bigger, softer and no more truthful."""
    names = _write(tmp_path, _source(832, 1216))
    assert _dims(tmp_path, names["xlarge"]) == (832, 1216)
    assert (tmp_path / names["xlarge"]).read_bytes() == (tmp_path / names["original"]).read_bytes()


def test_a_large_master_is_scaled_to_fit_each_long_side(tmp_path):
    names = _write(tmp_path, _source(3000, 2000))
    assert _dims(tmp_path, names["original"]) == (3000, 2000)
    assert _dims(tmp_path, names["xlarge"]) == (2048, 1365)
    assert _dims(tmp_path, names["large"]) == (1024, 683)
    assert _dims(tmp_path, names["small"]) == (240, 160)
    assert _dims(tmp_path, names["mini"]) == (48, 32)


def test_portrait_aspect_ratio_is_preserved(tmp_path):
    """The regression that started this: a portrait master must not be squeezed.

    Aspect is checked rather than a literal size, so a rounding convention change
    does not fail the test for the wrong reason.
    """
    names = _write(tmp_path, _source(832, 1216))
    for key in ("xlarge", "large", "small", "mini"):
        w, h = _dims(tmp_path, names[key])
        assert abs((w / h) - (832 / 1216)) < 0.01, f"{key} distorted: {w}x{h}"


def test_alpha_survives_every_tier(tmp_path):
    """A cutout must stay transparent in all of them, not just the original."""
    names = _write(tmp_path, _source(1000, 1000, mode="RGBA"))
    for key, name in names.items():
        with Image.open(tmp_path / name) as im:
            assert im.mode == "RGBA", f"{key} lost its alpha channel"


# ── The map the surfaces read ─────────────────────────


def test_background_renders_from_the_biggest_tier():
    assert ROLE_VARIANT["background"] == "XLarge"
    # The small surfaces stay small: a map dot and a panel portrait pay nothing
    # for pixels nobody sees.
    assert ROLE_VARIANT["navdot"] == "Large"
    assert ROLE_VARIANT["sheet"] == "Small"


def test_the_graphql_resolvers_share_one_map():
    from transversal.api.graphql.type_defs import entities, traits
    assert entities.Entity._ROLE_VARIANT is ROLE_VARIANT
    assert traits._ROLE_VARIANT is ROLE_VARIANT
