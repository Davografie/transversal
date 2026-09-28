"""Per-universe palettes — the authored look of each universe.

A palette is a plain JSON object stored on the **universe entity**'s
``palette`` field. The frontend applies it as ``:root`` custom-property
overrides whenever that universe is the one in play ([[UI-UX Design#Theming]]),
so the app's chrome — panels, sheet, roller, buttons, rows — takes on the
universe's accent, surfaces, borders and type. It is **content, not code**: a
new universe needs a palette on its entity, not a frontend release.

Shape (every key optional except the colour groups you want to change)::

    {
      "font":   {"ui": "<stack>", "display": "<stack>"},
      "radius": "<length>",
      "styles": {"traitRow": "<declarations>", "choiceRow": "<declarations>", ...},
      "dark":   { "<knob>": "<css value>", ... },
      "light":  { "<knob>": "<css value>", ... }
    }

``styles`` is the per-**element** half: each key is a named element (see
``STYLE_TARGETS`` in ``src/frontend/src/assets/universePalette.js`` for the
vocabulary and the selector each one means) and each value is a block of CSS
**declarations** — no selector, because the runtime supplies one, scoped to the
universe. It is how a universe styles *shapes* rather than colours: the Three
Realms rows below are bamboo slats, a vertical gradient of the roll's shading.

The colour knobs are **semantic, not token names** — one knob per decision a
palette makes, mapped to the CSS custom properties in
``src/frontend/src/assets/universePalette.js`` (the single mapping table; a knob
that is not in it does nothing, and the frontend check fails on one):

======================  ====================================================
``accent``              the universe's ink — buttons, chips, highlights
``accentDim``           the dim accent *fill* (paired with light text)
``accentActive``        the selected/hover accent fill
``bgDeep``              the page background behind everything
``bgOverlay``           the translucent full-screen overlay
``bgPanel``             translucent panel fill
``bgPanelSolid``        solid panel fill (the surface text is measured on)
``bgPanelRaised``       raised cards / inputs inside a panel
``text``                body text (neutral overlays derive from it)
``textDim``             secondary text
``border``              the standard border
``borderSoft``          hairline borders
``borderStrong``        emphasised rules
======================  ====================================================

Both ``dark`` and ``light`` are carried **by the same palette**, because the
frontend writes them inline on ``<html>``, where they would otherwise outrank
the ``html.light`` fallback block. A palette that omits ``light`` therefore
leaves the light theme's neutral values for those knobs in place, and one that
sets only ``dark`` is a deliberate dark-only look.

The two palettes below are worked examples, and the seed/backfill write them
onto the universe entities. They are *examples of the mechanism*, not special
cases in it: pressing them onto a universe is what makes them visible, and
editing the universe entity is how they change.
"""

from __future__ import annotations


# The vocabulary. `COLOR_KNOBS` is the set a `dark`/`light` group may carry;
# `THEMES` and `TOP_LEVEL_KEYS` are the object's own shape. The frontend's
# mapping table (`src/frontend/src/assets/universePalette.js`) is the mirror of
# this list — a knob here with no entry there is ignored, and its own check
# fails on an unknown knob rather than letting a typo do nothing.
TOP_LEVEL_KEYS = frozenset({"font", "radius", "styles", "dark", "light"})
# The named elements a palette may style. Mirrors `STYLE_TARGETS` in
# `src/frontend/src/assets/universePalette.js` — that table owns the selector each
# key means, this one only says which keys exist.
STYLE_TARGETS = frozenset({"sheet", "traitRow", "choiceRow"})
THEMES = ("dark", "light")
COLOR_KNOBS = frozenset({
    "accent", "accentDim", "accentActive",
    "bgDeep", "bgOverlay", "bgPanel", "bgPanelSolid", "bgPanelRaised",
    "text", "textDim",
    "border", "borderSoft", "borderStrong",
})


# ── Earth — a printed form, a filing system ─────────────────────────────────
# Paper and ink: the light theme is an actual form (warm paper, near-black ink,
# ruled lines, no corner radius), the dark theme is the same bureaucracy after
# hours (cold slate, the same ink blue). Typewriter values, printed headings.
EARTH_PALETTE = {
    "font": {
        "ui": "'Courier New', Courier, 'Liberation Mono', monospace",
        "display": "Georgia, 'Times New Roman', 'Liberation Serif', serif",
    },
    "radius": "0px",
    "dark": {
        "accent": "#4a7fb5",
        "accentDim": "#28405c",
        "accentActive": "#2f5b86",
        "bgDeep": "#0e1013",
        "bgOverlay": "rgba(12, 14, 17, 0.75)",
        "bgPanel": "rgba(22, 25, 30, 0.88)",
        "bgPanelSolid": "#16191e",
        "bgPanelRaised": "#1e222a",
        "text": "#dfe3e8",
        "textDim": "#8d949e",
        "border": "rgba(200, 210, 225, 0.30)",
        "borderSoft": "rgba(200, 210, 225, 0.16)",
        "borderStrong": "rgba(200, 210, 225, 0.50)",
    },
    "light": {
        "accent": "#1f4e79",
        "accentDim": "#c3d3e2",
        "accentActive": "#1f4e79",
        "bgDeep": "#e6e2d6",
        "bgOverlay": "rgba(240, 236, 226, 0.75)",
        "bgPanel": "rgba(250, 248, 242, 0.92)",
        "bgPanelSolid": "#f7f5ee",
        "bgPanelRaised": "#ffffff",
        "text": "#1b1c1e",
        "textDim": "#4f5359",
        "border": "rgba(27, 28, 30, 0.35)",
        "borderSoft": "rgba(27, 28, 30, 0.18)",
        "borderStrong": "rgba(27, 28, 30, 0.55)",
    },
}


# ── Three Realms — jade and bamboo scroll ───────────────────────────────────
# Bamboo paper and jade ink: the light theme is a scroll (warm pale paper, deep
# jade ink, softer corners, brushed serif), the dark theme is a night garden
# (ink-green ground, jade highlights, rice-paper text).
THREE_REALMS_PALETTE = {
    "font": {
        "ui": "Georgia, 'Noto Serif', 'Liberation Serif', 'Times New Roman', serif",
        "display": "'Palatino Linotype', Palatino, 'Book Antiqua', Georgia, serif",
    },
    "radius": "6px",
    "dark": {
        "accent": "#4fc79a",
        "accentDim": "#1f5f49",
        "accentActive": "#2a7a5e",
        "bgDeep": "#0a1210",
        "bgOverlay": "rgba(8, 18, 15, 0.75)",
        "bgPanel": "rgba(18, 30, 26, 0.86)",
        "bgPanelSolid": "#121e1a",
        "bgPanelRaised": "#1a2a24",
        "text": "#e2ece4",
        "textDim": "#8aa094",
        "border": "rgba(150, 200, 175, 0.28)",
        "borderSoft": "rgba(150, 200, 175, 0.15)",
        "borderStrong": "rgba(150, 200, 175, 0.48)",
    },
    "light": {
        "accent": "#1f6b4f",
        "accentDim": "#c2dccd",
        "accentActive": "#1f6b4f",
        "bgDeep": "#e7e2cf",
        "bgOverlay": "rgba(240, 236, 219, 0.75)",
        "bgPanel": "rgba(246, 243, 229, 0.90)",
        "bgPanelSolid": "#f4f1e2",
        "bgPanelRaised": "#fbf9f0",
        "text": "#1c2620",
        "textDim": "#4a5a50",
        "border": "rgba(28, 60, 45, 0.30)",
        "borderSoft": "rgba(28, 60, 45, 0.15)",
        "borderStrong": "rgba(28, 60, 45, 0.50)",
    },
    # ── Element CSS: the rows as bamboo slats ───────────────────────────────
    # What the author asked for by name: "style the Three Realms rows as bamboo
    # slats of a bamboo scroll". A slat is a vertical gradient (the roll's
    # shading: a highlight just under the top edge, deepening to a darker belly),
    # a thin dark seam at the bottom, and square-ish ends.
    #
    # `light-dark()` is what makes one block work in both themes — bamboo paper
    # in the light theme, a night-garden slat in the dark one — and the runtime
    # sets `color-scheme` per theme, so it resolves by itself.
    #
    # These are *declarations*, not selectors: the runtime wraps each in a rule
    # scoped to the universe (`html[data-universe="three_realms"] .trait-row`),
    # which is also what lets an ordinary declaration outrank the component's own
    # scoped styles. A *state* (a trait in the pool, a row the dice found, hover)
    # still wins on purpose, so state reads through the styling; `!important` is
    # the escape hatch if a universe wants the slat to survive even that.
    "styles": {
        "traitRow": (
            "background: linear-gradient(180deg,"
            " light-dark(#fbf8e8, #1b2a23) 0%,"
            " light-dark(#ece3c2, #16241e) 45%,"
            " light-dark(#d9cf9f, #111d18) 100%);"
            " border: 1px solid light-dark(rgba(120, 105, 60, 0.45), rgba(120, 200, 170, 0.22));"
            " border-radius: 5px;"
            " box-shadow: inset 0 1px 0 light-dark(rgba(255, 255, 255, 0.65), rgba(255, 255, 255, 0.06)),"
            " inset 0 -1px 0 light-dark(rgba(90, 75, 40, 0.28), rgba(0, 0, 0, 0.35));"
        ),
        "choiceRow": (
            "background: linear-gradient(180deg,"
            " light-dark(#fbf8e8, #1b2a23) 0%,"
            " light-dark(#ece3c2, #16241e) 45%,"
            " light-dark(#d9cf9f, #111d18) 100%);"
            " border: 1px solid light-dark(rgba(120, 105, 60, 0.45), rgba(120, 200, 170, 0.22));"
            " border-radius: 5px;"
            " box-shadow: inset 0 1px 0 light-dark(rgba(255, 255, 255, 0.65), rgba(255, 255, 255, 0.06)),"
            " inset 0 -1px 0 light-dark(rgba(90, 75, 40, 0.28), rgba(0, 0, 0, 0.35));"
        ),
    },
}


# Universe key (`Entity.current_universe` on the universe entity) → palette.
PALETTES: dict[str, dict] = {
    "earth": EARTH_PALETTE,
    "three_realms": THREE_REALMS_PALETTE,
}


def palette_for(universe_key: str) -> dict | None:
    """The example palette for a universe key, or None when it has none."""
    return PALETTES.get(universe_key)
