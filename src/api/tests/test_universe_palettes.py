"""Per-universe palettes — shape, and the visibility floor they must clear.

A universe's palette is authored content that retints the whole chrome
([[UI-UX Design#Theming]]), so the two ways it can go wrong are both structural:
a **knob that does nothing** (not in the frontend's mapping table) and a
**palette that cannot be read** (light text on a light panel). Neither is
visible to a build, and no behavioural test sees a colour — so they are pinned
here, on the authored examples themselves.

The contrast floor mirrors the frontend's `check-theme-tokens.mjs`: it is a
*visibility* floor (3:1), not an AA audit, and it measures exactly the three
tokens a palette may repaint that are used as **text** (`--text`, `--text-dim`,
`--accent`) against the surface text is measured on (`--bg-panel-solid`). A
translucent or mixed value cannot be judged without compositing, so palette
values are required to be opaque hex for those three.
"""

from __future__ import annotations

import math

import pytest

from transversal.db.universe_palettes import (
    COLOR_KNOBS,
    PALETTES,
    STYLE_TARGETS,
    THEMES,
    TOP_LEVEL_KEYS,
    palette_for,
)

# Text tokens the floor measures, and the surface it measures against.
TEXT_KNOBS = ("text", "textDim", "accent")
SURFACE_KNOB = "bgPanelSolid"
MIN_CONTRAST = 3.0


# ── colour helpers (mirroring scripts/check-theme-tokens.mjs) ───────────────

def rgb_of(value: str) -> tuple[int, int, int] | None:
    """`(r, g, b)`, or None when the value cannot be judged (translucent)."""
    value = value.strip()
    if value.startswith("#"):
        h = value[1:]
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        if len(h) != 6:
            return None
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    if value.startswith("rgb"):
        inner = value[value.index("(") + 1:value.rindex(")")]
        parts = [p.strip() for p in inner.split(",")]
        if len(parts) < 3:
            return None
        if len(parts) == 4 and float(parts[3]) < 1:
            return None
        return tuple(int(float(p)) for p in parts[:3])
    return None


def _luminance(rgb: tuple[int, int, int]) -> float:
    def f(c: int) -> float:
        s = c / 255
        return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4

    r, g, b = rgb
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def contrast(fg: tuple[int, int, int], bg: tuple[int, int, int]) -> float:
    hi, lo = sorted((_luminance(fg), _luminance(bg)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


# ── 1. shape ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("key", sorted(PALETTES))
def test_example_palette_is_within_the_vocabulary(key):
    palette = PALETTES[key]

    assert set(palette) <= TOP_LEVEL_KEYS, f"{key}: unknown top-level key(s)"
    for theme in THEMES:
        group = palette.get(theme)
        assert group, f"{key}: no '{theme}' group — both themes are carried by the palette"
        unknown = set(group) - COLOR_KNOBS
        assert not unknown, f"{key}/{theme}: knobs the frontend mapper does not know: {sorted(unknown)}"


@pytest.mark.parametrize("key", sorted(PALETTES))
def test_every_colour_is_a_colour(key):
    for theme in THEMES:
        for knob, value in PALETTES[key][theme].items():
            assert rgb_of(value) is not None or value.startswith("rgba("), \
                f"{key}/{theme}/{knob}: not a colour: {value!r}"


@pytest.mark.parametrize("key", sorted(PALETTES))
def test_font_and_radius_are_stacks_and_lengths(key):
    font = PALETTES[key].get("font")
    if font:
        assert set(font) <= {"ui", "display"}, f"{key}: unknown font slot(s)"
        for slot, stack in font.items():
            assert isinstance(stack, str) and "," in stack, \
                f"{key}/font.{slot}: expected a font stack, got {stack!r}"
    radius = PALETTES[key].get("radius")
    if radius is not None:
        assert radius.endswith(("px", "rem", "em")), f"{key}/radius: expected a length, got {radius!r}"


# ── 2. the visibility floor ─────────────────────────────────────────────────

@pytest.mark.parametrize("key", sorted(PALETTES))
@pytest.mark.parametrize("theme", THEMES)
def test_palette_text_clears_the_visibility_floor(key, theme):
    palette = PALETTES[key][theme]
    bg = rgb_of(palette[SURFACE_KNOB])
    assert bg is not None, f"{key}/{theme}: {SURFACE_KNOB} must be opaque to measure text on it"

    for knob in TEXT_KNOBS:
        fg = rgb_of(palette[knob])
        assert fg is not None, f"{key}/{theme}/{knob}: must be an opaque colour to measure"
        ratio = contrast(fg, bg)
        assert ratio >= MIN_CONTRAST, (
            f"{key}/{theme}: {knob} is {ratio:.2f}:1 on {SURFACE_KNOB} — below the {MIN_CONTRAST}:1 floor"
        )


def test_the_floor_condemns_a_palette_that_cannot_be_read():
    """The check has to fail on the failure it exists for, or the passes mean nothing."""
    unreadable = {"text": "#f4f1e2", "textDim": "#4a5a50", "accent": "#1f6b4f", SURFACE_KNOB: "#f4f1e2"}
    ratio = contrast(rgb_of(unreadable["text"]), rgb_of(unreadable[SURFACE_KNOB]))
    assert ratio < MIN_CONTRAST
    assert not math.isclose(ratio, MIN_CONTRAST)


# ── 3. the examples themselves ──────────────────────────────────────────────

def test_style_targets_are_a_known_vocabulary():
    """Per-element CSS: the keys are a fixed vocabulary, the values are declarations."""
    for key in sorted(PALETTES):
        styles = PALETTES[key].get("styles") or {}
        unknown = set(styles) - STYLE_TARGETS
        assert not unknown, f"{key}: unknown style target(s): {sorted(unknown)}"
        for target, css in styles.items():
            assert isinstance(css, str) and css.strip(), f"{key}/styles.{target}: empty"
            # A declaration block, not a selector: the runtime wraps it in a rule of
            # its own. A stray brace would end that rule early and spill the rest of
            # the declarations into the stylesheet.
            assert "{" not in css and "}" not in css, f"{key}/styles.{target}: not declarations"


def test_the_bamboo_slats_are_theme_aware():
    """The author's example: rows as slats. One block serves both themes, so it has
    to carry the difference itself (`light-dark()`), or the dark theme gets bamboo
    paper."""
    styles = PALETTES["three_realms"]["styles"]
    for target in ("traitRow", "choiceRow"):
        css = styles[target]
        assert "linear-gradient(180deg" in css, f"{target}: expected a vertical gradient"
        assert "light-dark(" in css, f"{target}: expected a per-theme value"


def test_the_seeded_universes_have_examples():
    for key in ("earth", "three_realms"):
        assert palette_for(key) is PALETTES[key]
    assert palette_for("chromotopia") is None


def test_the_two_examples_are_actually_different_looks():
    """A copy-paste would pass every check above and show two identical universes."""
    earth, realms = PALETTES["earth"], PALETTES["three_realms"]
    assert earth["radius"] != realms["radius"]
    assert earth["font"]["ui"] != realms["font"]["ui"]
    for theme in THEMES:
        assert earth[theme]["accent"] != realms[theme]["accent"]
        assert earth[theme][SURFACE_KNOB] != realms[theme][SURFACE_KNOB]
