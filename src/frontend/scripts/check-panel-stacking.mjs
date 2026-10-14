/**
 * Executable check for dynamic panel stacking (a click brings a panel forward).
 *
 * The frontend has no test runner, so this is a plain node script with
 * assertions — no dependency added. Run it against the frontend image, the same
 * way as the other checks:
 *
 *   docker run --rm \
 *     -v /path/to/src/frontend/scripts:/app/scripts:ro \
 *     -v /path/to/src/frontend/src:/app/src:ro \
 *     -w /app transversal2-frontend:latest node scripts/check-panel-stacking.mjs
 *
 * The request: "I want panels I clicked last to be rendered on top."
 *
 * The unit of stacking is a **unit**, not a panel: the chain (whose panels are
 * laid out side by side and so never overlap each other) is one, and each
 * floating window is one. Two units really do overlap — a detached window parks
 * exactly where its panel was — and that is what has to reorder.
 *
 * Two things this check cannot do, and the e2e spec next to it does: whether the
 * browser paints them in that order, and whether a click raises. The rules that
 * *can* be lifted out and run directly (`panelWindowPersistence.js`, which imports
 * nothing but Vue's predicates) are run directly below.
 */
import { readFileSync } from 'node:fs'

let pass = 0, fail = 0
const ok = (name, got, want) => {
  const same = JSON.stringify(got) === JSON.stringify(want)
  same ? pass++ : fail++
  console.log(`${same ? '  PASS' : '  FAIL'}  ${name}${same ? '' : `\n         got ${JSON.stringify(got)}  want ${JSON.stringify(want)}`}`)
}
const yes = (name, got) => ok(name, !!got, true)

const read = (p) => readFileSync(new URL(p, import.meta.url), 'utf8')
const { deserializeWindows } = await import('../src/composables/panelWindowPersistence.js')

const WINDOWS = read('../src/composables/usePanelWindows.js')
const STACK = read('../src/components/gm/PanelStack.vue')
const PERSIST = read('../src/composables/panelWindowPersistence.js')

const A = { name: 'A' }
const lookup = (name) => (name === 'A' ? A : null)
const rec = (z, title) => ({ name: 'A', title, props: {}, z })

// ── 1. the restored ranks ───────────────────────────────────────────────
// `z` is a *ranking* — the highest paints on top. Records written before
// stacking existed carry the spawn index (`windows.length`), whose first value is
// 0: left alone, that ties with the chain's rank and lands the restored window
// *behind* the chain, which is the opposite of where a detached window belongs.
console.log('\nrestored stacking ranks\n')

{
  const back = deserializeWindows([rec(0, 'a'), rec(0, 'b'), rec(0, 'c')], lookup)
  ok('a stale store comes back as a dense run, one rank each',
    back.map((w) => w.z), [1, 2, 3])
  ok('and the array order is that rank order',
    back.map((w) => w.spec.title), ['a', 'b', 'c'])
}

{
  const back = deserializeWindows([rec(3, 'top'), rec(1, 'bottom'), rec(2, 'middle')], lookup)
  ok('ranks that were raised out of order restore in rank order',
    back.map((w) => [w.spec.title, w.z]), [['bottom', 1], ['middle', 2], ['top', 3]])
}

{
  const back = deserializeWindows([rec(0, 'old'), rec(9, 'raised')], lookup)
  yes('no window is left ranked at 0 — the rank that ties with the chain',
    back.every((w) => w.z >= 1))
  ok('and the raised one is still on top of the stale one',
    back.map((w) => w.spec.title), ['old', 'raised'])
}

{
  ok('a single window is rank 1 — never 0',
    deserializeWindows([rec(0, 'only')], lookup).map((w) => w.z), [1])
  ok('a record with no rank at all is ranked rather than dropped',
    deserializeWindows([{ name: 'A', props: {} }], lookup).map((w) => [w.spec.title, w.z]),
    [['', 1]])
  ok('equal ranks keep the order they were written in',
    deserializeWindows([rec(2, 'first'), rec(2, 'second')], lookup).map((w) => w.spec.title),
    ['first', 'second'])
  ok('a dropped record does not leave a gap in the run',
    deserializeWindows([rec(1, 'a'), { name: 'Gone', z: 2 }, rec(3, 'b')], lookup).map((w) => w.z),
    [1, 2])
}

// ── 2. the registry hands ranks out ─────────────────────────────────────
console.log('\nthe rank counter\n')

yes('a new window is ranked above everything already open',
  /z: \+\+zSeq,/.test(WINDOWS) && /never reused/.test(WINDOWS))
yes('the counter is not the array length — two windows may share a length 0',
  !/z: windows\.value\.length/.test(WINDOWS))
yes('the counter is re-derived from the restored windows, so a spawn after a reload is still on top',
  /zSeq = restored\.reduce\(\(max, w\) => Math\.max\(max, w\.z\), 0\)/.test(WINDOWS))
yes('raising a window bumps its rank', /function raise\(id\)/.test(WINDOWS) && /w\.z = \+\+zSeq/.test(WINDOWS))
yes('raising the chain bumps the chain\'s own rank', /rootZ\.value = \+\+zSeq/.test(WINDOWS))
yes('and a raise that would change nothing burns no rank (nor a storage write)',
  /if \(rootZ\.value < zSeq\)/.test(WINDOWS) && /if \(w && w\.z < zSeq\)/.test(WINDOWS))
yes('the chain\'s rank has a home — the stack root is a prop, not a window',
  /const rootZ = ref\(0\)/.test(WINDOWS))
yes('both are handed to PanelStack', /raise, rootZ \}/.test(WINDOWS))
yes('the rank is written to storage with the window', /z: w\.z \?\? 0,/.test(PERSIST))

// ── 3. one layer, one wrapper per unit ──────────────────────────────────
// The bug this fixes: the chain and the floats used to be two `.panel-viewport`s
// at the same z-index, so their order was DOM order — the floats were *always*
// over the chain, and clicking the chain could not change it.
console.log('\nthe units share one stacking context\n')

{
  const layers = STACK.match(/class="panel-viewport"/g) || []
  ok('exactly one panel layer — a second one would be an unraisable stacking context',
    layers.length, 1)
  yes('and it exists precisely while a unit does — `show` or a window',
    /v-if="show \|\| windows\.length" class="panel-viewport"/.test(STACK))
  yes('the chain is a unit carrying its rank',
    /class="panel-unit" data-panel-unit="root" :style="\{ zIndex: rootZ \}"/.test(STACK))
  yes('each window is a unit carrying its own',
    /class="panel-unit"\s*\n\s*:data-panel-unit="w\.id"\s*\n\s*:style="\{ zIndex: w\.z \}"/.test(STACK))
  yes('both unit kinds are inside the layer',
    STACK.indexOf('data-panel-unit="root"') > STACK.indexOf('class="panel-viewport"'))
}

// ── 4. the layer stays under the chrome ─────────────────────────────────
// Ranks are local to the layer: however high a unit climbs, panels must not
// cover the 🛠 toggle or a modal. A `z-index` on `.panel-unit` is what creates
// the unit's own stacking context, and the layer keeps its own rank.
console.log('\nthe layer keeps its place against the chrome\n')

yes('the layer is still the fixed rank it was',
  /\.panel-viewport \{\s*position: fixed; inset: 0; z-index: 25;/.test(STACK))
yes('the 🛠 toggle is still one above it', /\.gm-toggle \{\s*position: fixed; z-index: 26;/.test(STACK))
yes('a unit is a positioned box spanning the layer, so panel coordinates are unchanged',
  /\.panel-unit \{\s*position: absolute; inset: 0;/.test(STACK))
yes('and it is pointer-transparent, like the layer (`.panel-node` re-enables events)',
  /\.panel-unit \{[^}]*pointer-events: none;/.test(STACK))

// ── 4b. opening a panel raises its unit ─────────────────────────────────
// A click raises whatever unit the pointer was in, which covers the common case
// and nothing else: a panel opened by keyboard activation, or by another panel's
// reaction, would otherwise appear *behind* a window sitting over its chain. So an
// open raises too — and for that, a nested panel has to know its unit, which is
// what `windowId` now carries all the way down (it used to be passed to a
// window's root panel only, so every child of a float reported `root`).
console.log('\nopening a panel raises its unit\n')

const PANEL_SRC = read('../src/components/gm/Panel.vue')
yes('a child inherits its unit', /:window-id="windowId"/.test(PANEL_SRC))
yes('opening a child raises the unit', /function openChild[\s\S]{0,900}?raiseUnit\(\)/.test(PANEL_SRC))
yes('and so does replacing one — the subject changed, so it is what is being worked in',
  /function replaceChild[\s\S]{0,300}?raiseUnit\(\)/.test(PANEL_SRC))
yes('the unit is the window id, defaulting to the chain',
  /function raiseUnit\(\) \{\s*raise\(props\.windowId \|\| 'root'\)/.test(PANEL_SRC))
yes('and the registry hands `raise` to Panel', /raise, rootZ \}/.test(WINDOWS))

// The 🛠 is an open too, and the one open neither rule above can reach: it sits
// outside the layer (no `[data-panel-unit]` ancestor for the capture-phase
// listener) and the chain never goes through `openChild`. Left out, a float
// restored on load parks over the chain the 🛠 just opened.
{
  const toggleOpen = STACK.match(/function onToggleClick\(\)[\s\S]*?\n\}/)?.[0] || ''
  yes('the 🛠 opening the chain raises the chain itself',
    /show\.value = true[\s\S]*?raise\('root'\)/.test(toggleOpen))
  yes('and it is a real open — the toggle only exists while the chain is closed',
    /v-if="!show"[\s\S]{0,120}class="gm-toggle"/.test(STACK))
}

// ── 5. a click raises the unit ──────────────────────────────────────────
// Capture-phase on the window, not a handler per unit: a panel is full of
// controls that stop propagation (`@pointerdown.stop` on the badge and the
// collapsed chip's buttons), and any of them would be a dead spot for "bring this
// forward".
console.log('\nclicking a panel raises its unit\n')

yes('the listener is on the window, in the capture phase',
  /window\.addEventListener\('pointerdown', raiseOnPointerDown, true\)/.test(STACK))
yes('and comes off with the stack',
  /window\.removeEventListener\('pointerdown', raiseOnPointerDown, true\)/.test(STACK))
yes('it raises the nearest unit wrapper',
  /closest\?\.\('\[data-panel-unit\]'\)/.test(STACK) && /raise\(unit\.dataset\.panelUnit\)/.test(STACK))
yes('it reads the unit wrapper, not the innermost panel node',
  !/closest\?\.\('\.panel-node'\)/.test(STACK))

console.log(`\n${pass} passed, ${fail} failed\n`)
process.exit(fail ? 1 : 0)
