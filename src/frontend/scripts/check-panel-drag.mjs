/**
 * Executable check for the panel drag gestures: **detach by dragging the handle
 * away from the parent**, and **drop a floating window onto another panel to
 * make it that panel's child**.
 *
 * The request, verbatim: "Instead of detaching panels with a dedicated button,
 * it should be detachable by moving the drag handle away from its parent. I'd
 * also like it if dragging a floating panel's drag handle onto the edge of
 * another panel, that it can anchor on it."
 *
 * Run it against the frontend image, the same way as the other checks:
 *
 *   docker run --rm \
 *     -v /path/to/src/frontend/scripts:/app/scripts:ro \
 *     -v /path/to/src/frontend/src:/app/src:ro \
 *     -w /app transversal2-frontend:latest node scripts/check-panel-drag.mjs
 *
 * What is *behavioural* here: the drop-target registry, which is pure enough to
 * drive with a stub `document` — the deepest panel under the point wins, and the
 * dragged window's own unit is never a candidate. What is *read from the source*:
 * the gesture wiring itself, because a pointer drag is a browser fact and is
 * pinned in `e2e/tests/panel-drag.spec.js` instead (`check-*.mjs` cannot prove it,
 * and a false green is worse than an honest split).
 */
import { readFileSync } from 'node:fs'
// Imported *before* the `document` stub below: `@vue/runtime-dom` reads the
// global once, at module load, and a stub without `createElement` makes it throw.
// (Evaluating it here, with no document, is what every other check already does.)
import { isRef } from 'vue'

let pass = 0, fail = 0
const ok = (name, got, want) => {
  const same = JSON.stringify(got) === JSON.stringify(want)
  same ? pass++ : fail++
  console.log(`${same ? '  PASS' : '  FAIL'}  ${name}${same ? '' : `\n         got ${JSON.stringify(got)}  want ${JSON.stringify(want)}`}`)
}

const read = (p) => readFileSync(new URL(p, import.meta.url), 'utf8')

const PANEL = read('../src/components/gm/Panel.vue')
const WINDOW = read('../src/components/gm/PanelWindow.vue')
const STACK = read('../src/components/gm/PanelStack.vue')
const DROP = read('../src/composables/usePanelDrop.js')

// ── 1. the button is gone, and the handle carries the keyboard path ─────
console.log('\nthe rail offers no detach button; the handle is the control\n')

ok('the ⤢ detach button is not rendered anywhere',
  /Detach into a floating window/.test(PANEL), false)
ok('the drag handle is still a Button (so it is focusable, not a bare span)',
  /<Button[^>]*class="panel-action-btn panel-drag-handle"/.test(PANEL), true)
ok('and Enter detaches with it',
  /@keydown\.enter\.prevent="onHandleActivate"/.test(PANEL), true)
ok('so does Space — prevented, or the page scrolls instead',
  /@keydown\.space\.prevent="onHandleActivate"/.test(PANEL), true)
// A *click* must not detach: the same pointerdown starts a slide, so a tap would
// otherwise tear the panel out of the chain.
ok('but a click does not detach (a tap on the handle is not a drag)',
  /@click="onHandleActivate"/.test(PANEL), false)
ok('the keyboard path goes through the same detach call the button used',
  /function onHandleActivate[\s\S]{0,200}props\.onDetach\(detachAnchor\(\)\)/.test(PANEL), true)
ok('and only when this panel can detach — a root cannot',
  /function onHandleActivate[\s\S]{0,80}if \(!props\.onDetach\) return/.test(PANEL), true)

// ── 2. the drag gesture ────────────────────────────────────────────────
console.log('\ndragging the handle away from the parent detaches\n')

ok('the slide measures the perpendicular axis, not the slide axis',
  /beginSlide[\s\S]{0,2400}const perp = vertical \? ev\.clientY - startY : ev\.clientX - startX/.test(PANEL), true)
ok('behind a named threshold',
  /const DETACH_THRESHOLD = \d+/.test(PANEL), true)
ok('crossing it arms the detach rather than moving the panel',
  /perp > DETACH_THRESHOLD \|\| perp < -DETACH_THRESHOLD/.test(PANEL), true)
ok('the panel is lifted while armed, so the gesture is visible',
  /if \(armed\) \{[\s\S]{0,160}lifting\.value = true/.test(PANEL) && /is-lifting/.test(PANEL), true)
ok('and the drop happens where the pointer let go',
  /if \(armed\) \{[\s\S]{0,320}props\.onDetach\(\{ x: last\.x, y: last\.y/.test(PANEL), true)

// ── 3. the drop-target registry, driven ────────────────────────────────
console.log('\nthe panel under the pointer is the drop target\n')

const rect = (left, top, w, h) => ({ left, top, right: left + w, bottom: top + h, width: w, height: h })
const el = (r, unit, z = 0) => ({
  getBoundingClientRect: () => r,
  closest: (sel) => (sel === '[data-panel-unit]' ? { dataset: { panelUnit: unit }, style: { zIndex: String(z) } } : null),
})

const outer = el(rect(0, 0, 400, 300), 'root')
const inner = el(rect(100, 100, 120, 80), 'root')
// Disjoint from the chain, so the exclusion test has a point of its own.
const otherUnit = el(rect(500, 0, 400, 300), 'gm-win-1', 5)
// Parked over the chain's corner, the way a detached window lands — higher rank,
// and deliberately small so it does not also cover the "deepest panel" point.
const topFloat = el(rect(0, 0, 90, 90), 'gm-win-2', 9)

globalThis.document = {
  querySelectorAll: (sel) => (sel === '.panel-node' ? [outer, inner, otherUnit, topFloat] : []),
}

const { registerDropTarget, openChildAt, targetAt, dropTargetEl } =
  await import('../src/composables/usePanelDrop.js')

let opened = null
registerDropTarget(outer, () => { opened = 'outer' })
registerDropTarget(inner, () => { opened = 'inner' })
registerDropTarget(otherUnit, () => { opened = 'other' })
registerDropTarget(topFloat, () => { opened = 'top' })

ok('a point inside nothing is no target', targetAt(1000, 500, null), null)
ok('a point inside the chain picks the panel there', targetAt(150, 120, null), inner)
ok('the deepest panel wins, not the chain root that contains it',
  targetAt(150, 120, null) === inner && targetAt(380, 280, null) === outer, true)
ok('and the unit on top wins when units overlap — a float parks on the panel it came from',
  targetAt(10, 10, null), topFloat)
ok('the dragged window\'s own unit is never a candidate',
  targetAt(600, 100, 'gm-win-1'), null)
ok('though that same point is a target for anyone else',
  targetAt(600, 100, null), otherUnit)
ok('a registered panel opens a child into itself', openChildAt(inner, { component: 'X' }), true)
ok('and receives the actual spec', opened, 'inner')
ok('an unregistered node is refused rather than throwing',
  openChildAt(el(rect(0, 0, 10, 10), 'root'), { component: 'X' }), false)
ok('the hovered node is a ref the panels can render from', isRef(dropTargetEl), true)

// ── 4. who registers, who drops ────────────────────────────────────────
console.log('\nboth halves are wired\n')

ok('the registry is keyed by the panel\'s own node, so nothing needs unregistering',
  /new WeakMap\(\)/.test(DROP), true)
ok('every Panel registers as a drop target', /registerDropTarget\(/.test(PANEL), true)
ok('and draws the highlight',
  /is-drop-target/.test(PANEL) && /dropTargetEl/.test(PANEL), true)
ok('a window hit-tests while it is being dragged', /targetAt\(/.test(WINDOW), true)
ok('clearing the highlight when the gesture ends',
  /dropTargetEl\.value = null/.test(WINDOW), true)
ok('and dropping makes it that panel\'s *child* — the settled semantics',
  /openChildAt\(target, props\.win\.spec\)/.test(WINDOW) && /emit\('close'\)/.test(WINDOW), true)
ok('the dock-back affordance is untouched (this is not a replacement for ⤓)',
  /canDock/.test(PANEL) && /dockWindow\(/.test(STACK), true)

console.log(fail ? `\n  ${fail} failed\n` : '\n  all clear\n')
process.exit(fail ? 1 : 0)
