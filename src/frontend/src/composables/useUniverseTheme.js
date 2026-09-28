import { computed, onScopeDispose, ref, watch } from 'vue'
import { PALETTE_VARS, paletteFor, paletteVars, universeStyleCss, unknownKnobs } from '@/assets/universePalette.js'

/**
 * Per-universe styling: the universe in play repaints the app's tokens.
 *
 * A universe entity carries a `palette` (see [[UI-UX Design#Theming]] for the
 * authored shape and `assets/universePalette.js` for the mapping). This
 * composable fetches the universes' palettes **once per session**, applies the
 * one that matches the universe in play as inline custom properties on
 * `<html>`, and re-applies on a theme flip — because inline values outrank
 * `html.light`, a palette has to be told which theme it is painting.
 *
 * Three deliberate properties:
 *
 * - **Inline, not a stylesheet.** Palettes are content; the alternative is a
 *   `html[data-universe="…"]` rule per universe in CSS, which is a frontend
 *   release per universe. Inline is the same mechanism as `?dockw`.
 * - **Cleared, then written.** A knob the new palette does not set has to go
 *   back to the stylesheet's value; leaving it would let Earth's paper survive
 *   a walk into the Three Realms (`data-universe` still names the owner).
 * - **A missing or broken palette is not a failure.** No palette (or none for
 *   this theme) simply leaves the app's own tokens in place, and an unknown
 *   knob is warned about — never a thrown error in a render path.
 */

/** One fetch per session: the palette map changes only when a GM authors one. */
let cache = null

/**
 * A palette being **edited**, painted as if it were the one in play.
 *
 * The GM palette panel needs the chrome to move while a GM picks colours, or they
 * are authoring blind. It is module-level because that editor lives deep in the GM
 * panel stack, with no prop path from the app shell — but the *composable* stays
 * the only writer of these `:root` properties (it watches this and re-applies), so
 * the single-writer rule that makes clearing correct still holds.
 *
 * `setPalettePreview(null)` ends it: on save, on revert, and on unmount.
 */
const preview = ref(null)

export function setPalettePreview(universeKey, palette) {
  preview.value = universeKey && palette ? { universeKey, palette } : null
}

export function useUniverseTheme({ graphql, universe, isLight, diag = () => {} }) {
  const palettes = ref(cache || {})

  async function load() {
    if (cache) return cache
    const data = await graphql(`{ entities(type: UNIVERSE) { currentUniverse palette } }`)
    const map = {}
    for (const u of data?.entities || []) {
      if (!u.palette) continue
      try {
        map[u.currentUniverse] = typeof u.palette === 'string' ? JSON.parse(u.palette) : u.palette
      } catch {
        // A malformed palette is content's problem, and it must not cost the
        // player their chrome: that universe keeps the app's own tokens.
        console.warn('[universe-theme] could not parse the palette for', u.currentUniverse)
      }
    }
    cache = map
    palettes.value = map
    diag(`universe-palettes: ${Object.keys(map).length} of ${(data?.entities || []).length}`)
    return map
  }

  function clear() {
    for (const name of PALETTE_VARS) document.documentElement.style.removeProperty(name)
    universeStyle.textContent = ''
  }

  // One stylesheet, owned here like the `:root` properties are: `palette.styles`
  // becomes scoped rules (see `universeStyleCss`). Written via `textContent`, so
  // authored CSS is never parsed as markup.
  const universeStyle = document.createElement('style')
  universeStyle.id = 'universe-style'
  document.head.appendChild(universeStyle)

  function apply() {
    // A preview paints the *edited* palette, whatever universe is in play: the
    // author is looking at what they are making, not at where they are standing.
    const key = preview.value?.universeKey || universe.value
    const map = preview.value
      ? { ...palettes.value, [preview.value.universeKey]: preview.value.palette }
      : palettes.value
    const palette = paletteFor(map, key)
    const root = document.documentElement

    clear()
    if (!palette) {
      delete root.dataset.universe
      return
    }

    const theme = isLight.value ? 'light' : 'dark'
    const vars = paletteVars(palette, theme)
    for (const [name, value] of Object.entries(vars)) root.style.setProperty(name, value)
    // Inspection hook: which palette is painting, and which half of it. Nothing
    // styles off this attribute — it is here so a browser can answer "why does
    // this look like that" without reading the entity.
    root.dataset.universe = key || ''

    universeStyle.textContent = universeStyleCss(key, palette)

    const unknown = unknownKnobs(palette)
    if (unknown.length) {
      console.warn(`[universe-theme] ${key}: unknown palette knob(s) ignored:`, unknown.join(', '))
    }
  }

  watch([universe, isLight, palettes, preview], apply, { immediate: true })
  onScopeDispose(() => { clear(); universeStyle.remove(); delete document.documentElement.dataset.universe })

  // The palette is fetched here rather than left to the host: a host that
  // forgot would render the app's default look with no error anywhere.
  load().catch((e) => console.warn('[universe-theme] palette fetch failed:', e?.message || e))

  return { palettes, load, apply, isPreviewing: computed(() => !!preview.value) }
}
