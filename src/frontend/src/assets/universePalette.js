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

/**
 * The **elements** a palette may style, as named targets.
 *
 * A palette's `styles` is a map of target → **declarations** (not selectors): the
 * author writes `background: linear-gradient(…)` and the runtime puts it in a rule
 * for the selector below, prefixed with the universe. Two reasons it is a fixed
 * vocabulary rather than raw CSS:
 *
 *   1. **Scoping and precedence.** The injected rule is
 *      `html[data-universe="…"] .trait-row { … }`, which both confines it to the
 *      universe in play *and* outranks the components' own scoped rules
 *      (`.trait-row[data-v-…]` is 0-2-0; the prefixed selector is 0-2-1). Raw CSS
 *      from a textarea would have to solve that itself, differently in each place.
 *   2. **A GM can't break the page.** Declarations cannot escape their rule, and
 *      there is no selector to typo into something else's rules.
 *
 * A target's declarations apply in **both themes**; be theme-aware with
 * `light-dark(a, b)` (the app sets `color-scheme` per theme) or by referencing the
 * palette's own tokens, which already flip.
 */
export const STYLE_TARGETS = {
  sheet: { label: 'Character sheet panel', selector: '.sheet-embedded' },
  traitRow: { label: 'Trait rows', selector: '.trait-row' },
  choiceRow: { label: 'Choice table rows', selector: '.ct-row' },
}

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
  const groups = ['font', 'radius', 'styles', ...THEMES]

  for (const key of Object.keys(palette)) {
    if (!groups.includes(key)) bad.push(key)
  }
  for (const slot of Object.keys(palette.font || {})) {
    if (!(slot in FONT_SLOTS)) bad.push(`font.${slot}`)
  }
  for (const target of Object.keys(palette.styles || {})) {
    if (!(target in STYLE_TARGETS)) bad.push(`styles.${target}`)
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

/**
 * The stylesheet a palette's `styles` becomes: one rule per target, scoped to the
 * universe and carrying its declarations verbatim.
 *
 * The rules are **not** applied by this module — `useUniverseTheme` owns the single
 * `<style>` element, the same way it owns the `:root` properties — but building the
 * text is pure, so a check can assert the scoping without a browser.
 *
 * @returns {string} the CSS, or '' when nothing is styled
 */
export function universeStyleCss(universeKey, palette) {
  if (!universeKey) return ''
  const rules = []
  for (const [target, spec] of Object.entries(STYLE_TARGETS)) {
    const css = palette?.styles?.[target]
    if (!isValue(css)) continue
    // The universe attribute is the scope *and* the specificity: it lifts these
    // above the components' own scoped rules (0-2-1 beats 0-2-0), so an author
    // does not have to fight `!important` to restyle a row.
    rules.push(`html[data-universe="${universeKey}"] ${spec.selector} { ${css.trim()} }`)
  }
  return rules.join('\n')
}

// ── the colour picker's dialect ─────────────────────────────────────────────
// The palette stores what CSS wants (`#rrggbb`, or `rgba(…)` where a surface is
// translucent); the picker speaks hex with an optional alpha byte. These convert
// both ways, and a picker edit only changes the *form* when alpha is in play.
const clamp255 = (n) => Math.max(0, Math.min(255, Math.round(n)))

/** `value` → `#rrggbb` / `#rrggbbaa`, for the picker. Null when unreadable. */
export function toPickerColor(value) {
  if (!isValue(value)) return null
  const v = value.trim()
  const hex = v.match(/^#([0-9a-f]{3}|[0-9a-f]{4}|[0-9a-f]{6}|[0-9a-f]{8})$/i)
  if (hex) {
    let h = hex[1]
    if (h.length <= 4) h = h.split('').map((c) => c + c).join('')
    return '#' + h.toLowerCase()
  }
  const fn = v.match(/^rgba?\(([^)]+)\)$/i)
  if (fn) {
    const parts = fn[1].split(',').map((x) => parseFloat(x.trim()))
    if (parts.length < 3 || parts.some((n, i) => i < 3 && !Number.isFinite(n))) return null
    const [r, g, b] = parts.slice(0, 3).map(clamp255)
    const a = parts.length === 4 && Number.isFinite(parts[3]) ? clamp255(parts[3] * 255) : 255
    const hexParts = [r, g, b, a].map((n) => n.toString(16).padStart(2, '0')).join('')
    return '#' + (a === 255 ? hexParts.slice(0, 6) : hexParts)
  }
  return null
}

/** The picker's hex → the value the palette stores. */
export function fromPickerColor(hex) {
  if (!isValue(hex)) return ''
  const h = String(hex).replace('#', '').toLowerCase()
  if (h.length === 6) return '#' + h
  if (h.length === 8) {
    const [r, g, b, a] = [0, 2, 4, 6].map((i) => parseInt(h.slice(i, i + 2), 16))
    // Alpha is what makes the difference: keep hex while it is opaque, and speak
    // rgba the moment it is not — which is what the tokens already use.
    if (a === 255) return '#' + h.slice(0, 6)
    const alpha = Math.round((a / 255) * 100) / 100
    return `rgba(${r}, ${g}, ${b}, ${alpha})`
  }
  return ''
}

/**
 * What an editor may safely save: known knobs only, and **no empty values**.
 *
 * An empty string is not "unset but present" in this vocabulary — a palette
 * *omits* a knob to leave the app's own value in place (see `paletteVars`), so an
 * editor's blank fields have to be dropped rather than written. Empty groups go
 * too, and a palette with nothing left is `{}` — which the editor sends as `""`,
 * the value the resolver reads as "clear it".
 *
 * @returns {object} a palette safe to `JSON.stringify` into the entity field
 */
export function cleanPalette(palette) {
  const out = {}
  if (!palette || typeof palette !== 'object') return out

  for (const target of Object.keys(STYLE_TARGETS)) {
    const css = palette.styles?.[target]
    if (isValue(css)) (out.styles ||= {})[target] = css.trim()
  }

  const font = {}
  for (const slot of Object.keys(FONT_SLOTS)) {
    const v = palette.font?.[slot]
    if (isValue(v)) font[slot] = v.trim()
  }
  if (Object.keys(font).length) out.font = font
  if (isValue(palette.radius)) out.radius = palette.radius.trim()

  for (const theme of THEMES) {
    const group = {}
    for (const knob of KNOWN_KNOBS.color) {
      const v = palette[theme]?.[knob]
      if (isValue(v)) group[knob] = v.trim()
    }
    if (Object.keys(group).length) out[theme] = group
  }
  return out
}

// ── the visibility floor, for an editor's own warning ───────────────────────
// The same 3:1 floor the API test applies to the shipped examples and
// `check-theme-tokens.mjs` applies to the stylesheet, here as a hint while a GM
// types: an authored palette *can* be unreadable, and whoever is authoring it is
// the one who can fix it. Translucent or mixed values are skipped rather than
// guessed at, exactly as the other two do.
export const MIN_CONTRAST = 3

const rgbOf = (value) => {
  if (typeof value !== 'string') return null
  const v = value.trim()
  const hex = v.match(/^#([0-9a-f]{3}|[0-9a-f]{6})$/i)
  if (hex) {
    const h = hex[1].length === 3 ? hex[1].split('').map((c) => c + c).join('') : hex[1]
    return [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16))
  }
  const fn = v.match(/^rgba?\(([^)]+)\)$/i)
  if (fn) {
    const parts = fn[1].split(',').map((s) => parseFloat(s.trim()))
    if (parts.length < 3 || (parts.length === 4 && parts[3] < 1)) return null
    return parts.slice(0, 3)
  }
  return null
}

const luminance = ([r, g, b]) => {
  const f = (c) => { const s = c / 255; return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4 }
  return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)
}

export function contrastRatio(a, b) {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x)
  return (hi + 0.05) / (lo + 0.05)
}

/** The knobs a palette may repaint that are read as *text* on the panel. */
export const TEXT_KNOBS = ['text', 'textDim', 'accent']
const SURFACE_KNOB = 'bgPanelSolid'

/**
 * Knobs in one theme whose text would be hard to read on that theme's own panel.
 * Worst first; empty when either value is translucent (it cannot be judged
 * without compositing).
 *
 * @returns {{knob: string, ratio: number, against: string}[]}
 */
export function paletteContrastWarnings(palette, theme) {
  const group = palette?.[theme]
  const surface = rgbOf(group?.[SURFACE_KNOB])
  if (!surface) return []
  return TEXT_KNOBS
    .map((knob) => {
      const fg = rgbOf(group?.[knob])
      return fg ? { knob, ratio: contrastRatio(fg, surface), against: SURFACE_KNOB } : null
    })
    .filter((w) => w && w.ratio < MIN_CONTRAST)
    .sort((a, b) => a.ratio - b.ratio)
}
