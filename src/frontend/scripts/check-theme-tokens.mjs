/**
 * Static check: a text colour must stay *visible* in the light theme.
 *
 * The frontend has no visual tests, so this is a plain node script with
 * assertions — no dependency added. Run it against the frontend image:
 *
 *   docker run --rm \
 *     -v /path/to/src/frontend/scripts:/app/scripts:ro \
 *     -v /path/to/src/frontend/src:/app/src:ro \
 *     -w /app transversal2-frontend:latest node scripts/check-theme-tokens.mjs
 *
 * Why it exists: the location tree's partial-reveal chevron was given
 * `color: var(--accent-dim)`. Every *fill* token is fine in dark theme; light
 * theme is where the palette flips, and `--accent-dim` flips to `#b9d3ec` — a
 * pale tint meant for backgrounds. As text on the light panel it came out at
 * **1.41:1** against a 3:1 floor: invisible. `--accent` is 4.68:1 there. No
 * behavioural check could see it (the harnesses are
 * DOM-free) and the build is happy with any colour. The human found it in the
 * browser.
 *
 * So the rule is the real one — contrast, not a token-name blocklist. A token
 * whose light-theme value cannot carry text is a bug wherever it is used as one;
 * a token that happens to be called `-dim` or `-active` but stays dark is fine
 * (see `.btn-link:active`, which uses `--accent-active` correctly).
 *
 * **This is a visibility floor (3:1), not an AA audit.** It is meant to catch
 * "cannot be read", which is the failure that actually shipped. Tokens that are
 * translucent or mixed (`color-mix`, `rgba(…, <1)`) cannot be judged without
 * compositing, so they are counted and reported rather than guessed at.
 */
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join } from 'node:path'

const SRC = 'src'
const STYLES = 'src/assets/styles.css'
// Deliberately light text: these exist to sit on a saturated accent *fill*, so
// the panel background is the wrong thing to measure them against.
const ON_FILL = new Set(['--text-on-accent', '--text-on-accent-dim'])
const MIN_CONTRAST = 3

let pass = 0, fail = 0
const ok = (name, bad) => {
  bad.length ? fail++ : pass++
  console.log(`  ${bad.length ? 'FAIL' : 'PASS'}  ${name}${bad.length ? `\n         ${bad.join('\n         ')}` : ''}`)
}

// ── the light-theme palette ──────────────────────────────────────────────
const css = readFileSync(STYLES, 'utf8')
const lightBlock = (css.match(/html\.light\s*\{([\s\S]*?)\n\}/) || [, ''])[1]
const lightVars = new Map()
for (const m of lightBlock.matchAll(/(--[\w-]+):\s*([^;]+);/g)) lightVars.set(m[1], m[2].trim())

/** `[r, g, b]`, or null when the value cannot be judged (translucent/mixed). */
function rgbOf(value) {
  if (!value) return null
  const hex = value.match(/^#([0-9a-f]{3}|[0-9a-f]{6})$/i)
  if (hex) {
    const h = hex[1].length === 3 ? hex[1].split('').map((c) => c + c).join('') : hex[1]
    return [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16))
  }
  const fn = value.match(/^rgba?\(([^)]+)\)$/i)
  if (fn) {
    const parts = fn[1].split(',').map((s) => parseFloat(s.trim()))
    if (parts.length < 3) return null
    if (parts.length === 4 && parts[3] < 1) return null
    return parts.slice(0, 3)
  }
  return null
}

const luminance = ([r, g, b]) => {
  const f = (c) => { const s = c / 255; return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4 }
  return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)
}
const contrast = (a, b) => {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x)
  return (hi + 0.05) / (lo + 0.05)
}

const panel = rgbOf(lightVars.get('--bg-panel-solid'))
if (!panel) throw new Error('could not read --bg-panel-solid from the light theme')

// ── 1. every text colour on the light panel ──────────────────────────────
console.log('\ntheme contrast — light theme\n')

// `color:` as a property in its own right: a leading `-` (as in `border-color:`)
// means it is a fill or a border, not text.
const TEXT_COLOR = /(^|[;{\s])color:\s*var\((--[\w-]+)\)/g

function walk(dir, out = []) {
  for (const name of readdirSync(dir)) {
    const path = join(dir, name)
    if (statSync(path).isDirectory()) walk(path, out)
    else if (/\.(vue|css)$/.test(name)) out.push(path)
  }
  return out
}

const files = walk(SRC)
const unjudgeable = new Set()     // translucent or mixed: cannot composite here
const surfaceSpecific = new Set() // the light theme does not restyle these
const dim = []
for (const file of files) {
  const lines = readFileSync(file, 'utf8').split('\n')
  lines.forEach((line, i) => {
    for (const m of line.matchAll(TEXT_COLOR)) {
      const token = m[2]
      if (ON_FILL.has(token)) continue
      const raw = lightVars.get(token)
      // The light block is the declaration of what the *panel* palette looks like.
      // A token it does not restyle is deliberately left alone — the map, canvas
      // and die colours — and is measured against their own surfaces, not this one
      // (`--map-text: #e0e0e0` is light text over the dark map, and would look
      // like a failure here while being exactly right).
      if (raw === undefined) { surfaceSpecific.add(token); continue }
      const rgb = rgbOf(raw)
      if (!rgb) { unjudgeable.add(token); continue }
      const ratio = contrast(rgb, panel)
      if (ratio < MIN_CONTRAST) {
        dim.push(`${file}:${i + 1}  color: var(${token})  →  ${ratio.toFixed(2)}:1 on the light panel`)
      }
    }
  })
}
ok(`every text colour clears ${MIN_CONTRAST}:1 in the light theme (${files.length} files)`, dim)
if (surfaceSpecific.size) {
  console.log(`  note  not restyled by the light theme, so not measured against the panel: ${[...surfaceSpecific].sort().join(', ')}`)
}
if (unjudgeable.size) {
  console.log(`  note  translucent or mixed; needs compositing to judge: ${[...unjudgeable].sort().join(', ')}`)
}

// ── 2. the check can fail ────────────────────────────────────────────────
// The resolver has to actually condemn the value that shipped, or the pass above
// means nothing.
{
  const bad = contrast(rgbOf(lightVars.get('--accent-dim')), panel)
  ok('it condemns the value that shipped (--accent-dim on light)',
    bad < MIN_CONTRAST ? [] : [`--accent-dim came out ${bad.toFixed(2)}:1`])
  const good = contrast(rgbOf(lightVars.get('--text-dim')), panel)
  ok('…without condemning the ordinary dim text',
    good >= MIN_CONTRAST ? [] : [`--text-dim came out ${good.toFixed(2)}:1`])
  const active = contrast(rgbOf(lightVars.get('--accent-active')), panel)
  ok('…or a token that is named like a fill but stays dark (--accent-active)',
    active >= MIN_CONTRAST ? [] : [`--accent-active came out ${active.toFixed(2)}:1`])
  ok('a border colours are not text',
    [...'.x { border-color: var(--accent-dim); }'.matchAll(TEXT_COLOR)].length ? ['matched border-color'] : [])
}

console.log(fail ? `\n  ${fail} failed\n` : '\n  all clear\n')
process.exit(fail ? 1 : 0)
