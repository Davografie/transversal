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
  KNOWN_KNOBS, PALETTE_VARS, paletteFor, paletteVars, unknownKnobs,
} from '../src/assets/universePalette.js'

let pass = 0, fail = 0
const ok = (name, bad) => {
  bad.length ? fail++ : pass++
  console.log(`  ${bad.length ? 'FAIL' : 'PASS'}  ${name}${bad.length ? `\n         ${bad.join('\n         ')}` : ''}`)
}

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

console.log(fail ? `\n  ${fail} failed\n` : '\n  all clear\n')
process.exit(fail ? 1 : 0)
