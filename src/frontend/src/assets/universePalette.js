/**
 * A universe's palette → the `:root` custom properties it repaints.
 *
 * This is the **single mapping table** between the authored vocabulary
 * (`palette.dark` / `palette.light` knob groups on the universe entity, see
 * `docs/Technical/UI-UX Design.md` § Theming) and the app's tokens. It is pure
 * and dependency-free on purpose: the composable applies its output, and
 * `scripts/check-universe-theme.mjs` asserts against it without a browser.
 *
 * Two rules it exists to keep:
 *
 * 1. **Knobs are semantic, never token names.** A palette says `accent`, not
 *    `--accent`, so the token API can move without breaking authored content —
 *    and a misspelled knob is reported rather than quietly doing nothing.
 * 2. **A knob maps to exactly one token.** The hue tints (`--accent-12`,
 *    `--danger-45`, …) are `color-mix`es of a base token, so they retint for
 *    free; nothing here enumerates them, and their absence from this table is
 *    the point.
 */

/** Theme-independent knobs: type and shape, not colour. */
const FONT_SLOTS = { ui: '--font-ui', display: '--font-display' }
const RADIUS_VAR = '--radius'
const PILL_VAR = '--radius-pill'

/** Colour knobs, allowed in a `dark` or a `light` group. */
const COLOR_VARS = {
  accent: '--accent',
  accentDim: '--accent-dim',
  accentActive: '--accent-active',
  bgDeep: '--bg-deep',
  bgOverlay: '--bg-overlay',
  bgPanel: '--bg-panel',
  bgPanelSolid: '--bg-panel-solid',
  bgPanelRaised: '--bg-panel-raised',
  text: '--text',
  textDim: '--text-dim',
  border: '--border',
  borderSoft: '--border-soft',
  borderStrong: '--border-strong',
}

export const THEMES = ['dark', 'light']

/** Every knob the mapper knows — the check reports authored drift against this. */
export const KNOWN_KNOBS = {
  shape: [...Object.keys(FONT_SLOTS).map((s) => `font.${s}`), 'radius'],
  color: Object.keys(COLOR_VARS),
}

/** Every CSS property a palette can write. The composable clears exactly these. */
export const PALETTE_VARS = [...Object.values(FONT_SLOTS), RADIUS_VAR, PILL_VAR, ...Object.values(COLOR_VARS)]

const isValue = (v) => typeof v === 'string' && v.trim() !== ''

/**
 * The vars a palette paints, for one theme.
 *
 * `theme` is the *resolved* theme ('dark' | 'light'), not the preference: the
 * palette carries both, and the caller re-applies on a flip. A group the
 * palette does not define contributes nothing — the stylesheet's own value for
 * that theme stands, which is what makes a dark-only palette deliberate rather
 * than broken.
 *
 * @param {object|null|undefined} palette
 * @param {'dark'|'light'} theme
 * @returns {Record<string, string>} CSS custom property → value
 */
export function paletteVars(palette, theme = 'dark') {
  const out = {}
  if (!palette || typeof palette !== 'object') return out

  for (const [slot, cssVar] of Object.entries(FONT_SLOTS)) {
    const value = palette.font?.[slot]
    if (isValue(value)) out[cssVar] = value.trim()
  }
  if (isValue(palette.radius)) {
    out[RADIUS_VAR] = palette.radius.trim()
    // One corner language per universe. A pill (`--radius-pill`) means "fully
    // round" as a *style*, and a universe that says "square" should not keep
    // capsule chips — so the pill follows the same value. The smaller steps
    // derive from `--radius` in the stylesheet; a palette that sets no radius
    // changes nothing.
    out[PILL_VAR] = palette.radius.trim()
  }

  const colors = palette[theme]
  if (colors && typeof colors === 'object') {
    for (const [knob, cssVar] of Object.entries(COLOR_VARS)) {
      if (isValue(colors[knob])) out[cssVar] = colors[knob].trim()
    }
  }
  return out
}

/**
 * Knobs in a palette that the mapper does not know — a typo, or content written
 * against a newer vocabulary than this build has. Returned rather than thrown:
 * the app should still render (that universe simply does not repaint that
 * token), but `check-universe-theme.mjs` fails on a non-empty result for the
 * shipped examples, and the composable warns once per palette.
 *
 * @returns {string[]} e.g. `['dark.accentHue', 'font.heading']`
 */
export function unknownKnobs(palette) {
  if (!palette || typeof palette !== 'object') return []
  const bad = []
  const groups = ['font', 'radius', ...THEMES]

  for (const key of Object.keys(palette)) {
    if (!groups.includes(key)) bad.push(key)
  }
  for (const slot of Object.keys(palette.font || {})) {
    if (!(slot in FONT_SLOTS)) bad.push(`font.${slot}`)
  }
  for (const theme of THEMES) {
    for (const knob of Object.keys(palette[theme] || {})) {
      if (!KNOWN_KNOBS.color.includes(knob)) bad.push(`${theme}.${knob}`)
    }
  }
  return bad
}

/** The palette for a universe key, from a `{ key: palette }` map. */
export function paletteFor(palettes, universeKey) {
  return (palettes && universeKey && palettes[universeKey]) || null
}
