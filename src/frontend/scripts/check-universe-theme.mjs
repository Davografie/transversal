/**
 * Static check: a palette knob always reaches a real token, and a theme only
 * gets its own half.
 *
 * Per-universe styling has one silent failure mode and one loud one. The loud
 * one is a palette that cannot be read (that is `tests/test_universe_palettes.py`,
 * measured on the authored examples). The silent one is a **knob that maps to
 * nothing** — a typo in this table, or a token renamed in `styles.css` — which
 * renders as "the universe just doesn't change that part", with no error
 * anywhere. This script is that guard, plus the theme-separation rule that an
 * inline `:root` override makes load-bearing (a dark-only palette must paint
 * nothing in light, or the light theme inherits a dark value).
 *
 * No browser and no dependency: `assets/universePalette.js` is pure, so the
 * check is plain node with assertions. Run it against the frontend image:
 *
 *   docker run --rm \
 *     -v /path/to/src/frontend/scripts:/app/scripts:ro \
 *     -v /path/to/src/frontend/src:/app/src:ro \
 *     -w /app transversal2-frontend:latest node scripts/check-universe-theme.mjs
 */
import { readFileSync } from 'node:fs'
import {
  KNOWN_KNOBS, PALETTE_VARS, cleanPalette, paletteContrastWarnings, paletteFor, paletteVars, unknownKnobs,
} from '../src/assets/universePalette.js'

let pass = 0, fail = 0
/** `bad` is the list of problems; empty means pass. */
const ok = (name, bad) => {
  bad.length ? fail++ : pass++
  console.log(`  ${bad.length ? 'FAIL' : 'PASS'}  ${name}${bad.length ? `\n         ${bad.join('\n         ')}` : ''}`)
}
/** For a plain boolean: the problem is the value that failed the claim. */
const yes = (name, cond, got = '') => ok(name, cond ? [] : [String(got)])

// ── the tokens the stylesheet actually declares ─────────────────────────────
const css = readFileSync('src/assets/styles.css', 'utf8')
const declared = new Set()
for (const m of css.matchAll(/(--[\w-]+)\s*:/g)) declared.add(m[1])

// A maximal palette: every known knob, in both themes.
const maximal = {
  font: { ui: 'ui-stack, sans-serif', display: 'display-stack, serif' },
  radius: '0px',
  dark: Object.fromEntries(KNOWN_KNOBS.color.map((k) => [k, '#123456'])),
  light: Object.fromEntries(KNOWN_KNOBS.color.map((k) => [k, '#654321'])),
}

console.log('\nuniverse palettes — the mapping table\n')

// ── 1. every knob reaches a token that exists ───────────────────────────────
{
  const vars = paletteVars(maximal, 'dark')
  const missing = Object.keys(vars).filter((v) => !declared.has(v))
  ok(`every var the mapper writes is declared in styles.css (${Object.keys(vars).length} vars)`, missing)
}

// ── 2. nothing the mapper can write escapes the clear list ──────────────────
// The composable clears exactly PALETTE_VARS before painting; a var it can emit
// but not clear would survive a walk into a universe that does not set it.
{
  const emitted = new Set([
    ...Object.keys(paletteVars(maximal, 'dark')),
    ...Object.keys(paletteVars(maximal, 'light')),
  ])
  const uncleared = [...emitted].filter((v) => !PALETTE_VARS.includes(v))
  ok('every var it can paint is in the clear list', uncleared)
}

// ── 3. a theme only paints its own half (shape is theme-independent) ────────
{
  const SHAPE = ['--font-ui', '--radius', '--radius-pill']
  const darkOnly = { dark: { accent: '#111111', text: '#eeeeee' }, radius: '0px', font: { ui: 'x, sans-serif' } }

  const light = Object.keys(paletteVars(darkOnly, 'light'))
  const coloursInLight = light.filter((v) => !SHAPE.includes(v))
  ok('a dark-only palette paints no dark colour in the light theme', coloursInLight)
  ok('…while its type and corners still carry over — those are not per-theme',
    SHAPE.every((v) => light.includes(v)) ? [] : light)

  const dark = Object.keys(paletteVars(darkOnly, 'dark')).sort()
  ok('…and the dark theme paints its colour knobs plus the same shape',
    JSON.stringify(dark) === JSON.stringify([...SHAPE, '--accent', '--text'].sort()) ? [] : dark)
}

// ── 4. font.display defaults, radius carries the pill ───────────────────────
{
  const uiOnly = paletteVars({ font: { ui: 'x, sans-serif' } }, 'dark')
  ok('a palette naming only font.ui leaves --font-display to the stylesheet',
    Object.keys(uiOnly).join() === '--font-ui' ? [] : Object.keys(uiOnly))

  const withRadius = paletteVars({ radius: '0px' }, 'dark')
  ok('a radius carries the pill with it (one corner language per universe)',
    withRadius['--radius'] === '0px' && withRadius['--radius-pill'] === '0px' ? [] : withRadius)
  ok('no radius → no pill override',
    Object.keys(paletteVars({ dark: {} }, 'dark')).length === 0 ? [] : Object.keys(paletteVars({ dark: {} }, 'dark')))
}

// ── 5. unknown knobs are reported, not swallowed ────────────────────────────
{
  const cases = [
    [{ dark: { accentHue: '#fff' } }, 'dark.accentHue'],
    [{ ligth: {} }, 'ligth'],
    [{ font: { heading: 'x' } }, 'font.heading'],
    [{ light: { bgDeep: '#000' } }, null],
    [{}, null],
    [null, null],
  ]
  const bad = []
  for (const [palette, expected] of cases) {
    const got = unknownKnobs(palette)
    if (expected === null ? got.length : !got.includes(expected)) {
      bad.push(`${JSON.stringify(palette)} → ${JSON.stringify(got)}${expected ? ` (expected ${expected})` : ''}`)
    }
  }
  ok('unknown groups, colour knobs and font slots are all reported', bad)
}

// ── 6. the lookup ───────────────────────────────────────────────────────────
{
  const map = { earth: { dark: {} } }
  const bad = []
  if (paletteFor(map, 'earth') !== map.earth) bad.push('earth not found')
  if (paletteFor(map, 'nowhere') !== null) bad.push('missing key did not return null')
  if (paletteFor(null, 'earth') !== null) bad.push('no map did not return null')
  if (paletteFor(map, '') !== null) bad.push('empty key did not return null')
  ok('paletteFor returns the palette or null, never undefined', bad)
}

// ── 7. the authoring half ───────────────────────────────────────────────────
// The editor must write through the *same* vocabulary the runtime reads, and it
// must not become a second source of truth for the mapping. Its two quiet
// failure modes: saving empty strings as if they were values (an omitted knob is
// how the runtime falls back), and naming a CSS property itself.
console.log('\nthe authoring panel\n')
{
  const clean = cleanPalette({
    font: { ui: 'Georgia, serif', display: '' },
    radius: '0px',
    dark: { accent: '#ff0000', border: '', nope: '#123456' },
    light: {},
    extra: 'dropped',
  })
  const want = { font: { ui: 'Georgia, serif' }, radius: '0px', dark: { accent: '#ff0000' } }
  yes('blank fields are dropped, not saved as empty strings',
    JSON.stringify(clean) === JSON.stringify(want), JSON.stringify(clean))
  yes('an empty palette is exactly {}',
    JSON.stringify(cleanPalette({ dark: { accent: '' } })) === '{}',
    JSON.stringify(cleanPalette({ dark: { accent: '' } })))
  yes('unknown keys cannot be saved',
    !('extra' in cleanPalette({ extra: 1, radius: '4px' })))

  const warned = paletteContrastWarnings({ dark: { bgPanelSolid: '#f4f1e2', textDim: '#f0efe8', text: '#1c2620' } }, 'dark')
  yes('an unreadable pair is flagged, on the text knob',
    warned.length === 1 && warned[0].knob === 'textDim', JSON.stringify(warned))
  yes('…with the ratio and the surface it was measured against',
    warned[0] && warned[0].ratio < 3 && warned[0].against === 'bgPanelSolid')
  yes('a readable pair is not flagged',
    paletteContrastWarnings({ dark: { bgPanelSolid: '#f4f1e2', text: '#1c2620' } }, 'dark').length === 0)
  yes('translucent values are not guessed at',
    paletteContrastWarnings({ dark: { bgPanelSolid: 'rgba(240,240,240,0.9)', textDim: '#ffffff' } }, 'dark').length === 0)

  const panel = readFileSync('src/components/gm/GmPalettePanel.vue', 'utf8')
  yes('the panel saves through the shared cleaning + vocabulary',
    /cleanPalette/.test(panel) && /KNOWN_KNOBS/.test(panel))
  yes('…previews through the single writer of the :root properties',
    /setPalettePreview/.test(panel))
  yes('…and names no CSS custom property itself (one mapping table)',
    !/--[a-z-]+:/.test(panel.replace(/<!--[\s\S]*?-->/g, '')))
  yes('…it never silently no-ops a save',
    /still loading — nothing was saved/.test(panel))

  // The doorway is the universe entity's own editor, beside the LoRA config and
  // the roll tables — where the palette lives — and *only* there, so there is one
  // place a GM can be told to look.
  const editor = readFileSync('src/components/gm/GmEntityEditPanel.vue', 'utf8')
  yes('the universe entity editor opens it, for a universe only',
    /v-if="form\.type === 'UNIVERSE'"/.test(editor) && /openPalettePanel/.test(editor) && /GmPalettePanel/.test(editor))
  yes('…and the Prep tools no longer carry a second doorway',
    !/GmPalettePanel/.test(readFileSync('src/components/GmPanel.vue', 'utf8')))
}

console.log(fail ? `\n  ${fail} failed\n` : '\n  all clear\n')
process.exit(fail ? 1 : 0)
