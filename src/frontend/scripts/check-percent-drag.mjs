/**
 * check-percent-drag.mjs — the drag scale, pinned.
 *
 * The bug this exists for: `usePercentDrag` converted the pointer's movement using
 * the **viewer's** box, while every map element is positioned as a percentage of the
 * **scene layer** — which is larger (overscan ×1.1, plus the teaser zoom). So a
 * dragged chip moved `scene ÷ viewer` times faster than the cursor: 1.19× on a
 * square background, 2.11× on a wide one, most visible sideways. The human's words
 * were "the movement of the chip is faster than the movement of the mouse".
 *
 * The composable is deliberately Vue-free and takes its element, its gate and its
 * extent as arguments, so it can be driven here with a fake `document`, with no
 * browser and no dependencies. Same convention as the other `check-*.mjs` scripts:
 * assert the fix, and assert the old behaviour to prove what it was.
 *
 *   node src/frontend/scripts/check-percent-drag.mjs
 */

// The composable attaches its move/end listeners to `document`, so a fake one that
// records them is all the harness needs.
const handlers = {}
globalThis.document = {
  addEventListener: (type, fn) => { (handlers[type] = handlers[type] || []).push(fn) },
  removeEventListener: (type, fn) => { handlers[type] = (handlers[type] || []).filter(h => h !== fn) },
}

const { usePercentDrag } = await import('../src/composables/usePercentDrag.js')

let fail = 0
const ok = (label, got, want) => {
  const pass = JSON.stringify(got) === JSON.stringify(want)
  if (!pass) fail++
  console.log(`${pass ? '  ok  ' : ' FAIL '} ${label}${pass ? '' : `\n         got ${JSON.stringify(got)} want ${JSON.stringify(want)}`}`)
}

// A docked-viewer map: 880×950 of viewer, overscanned to a 1045×1045 scene layer.
const VIEWER = { width: 880, height: 950 }
const SCENE = { w: 1045, h: 1045 }
const viewerEl = {
  value: { getBoundingClientRect: () => ({ left: 0, top: 0, width: VIEWER.width, height: VIEWER.height }) },
}

/** Drive one drag and report where it put the element. `span` absent = the old code. */
function drag(span, { dx = 104.5, dy = 104.5 } = {}) {
  for (const k of Object.keys(handlers)) delete handlers[k]
  let moved = null
  const d = usePercentDrag({ enabled: () => true, viewerEl, span })
  d.start(
    { preventDefault() {}, clientX: 100, clientY: 100 },
    { x: 50, y: 50, onMove: (x, y) => { moved = { x, y } } },
  )
  for (const h of handlers.mousemove || []) h({ preventDefault() {}, clientX: 100 + dx, clientY: 100 + dy })
  return moved
}

// ── The fix: the pointer's pixels are measured against the SCENE ─────────────
// 104.5px across a 1045px scene is exactly 10% of it.
ok('with the scene extent, a 104.5px drag is 10% (1045px scene)', drag(() => SCENE), { x: 60, y: 60 })

// …so the element lands where the pointer did: 10% of 1045 = 104.5px.
{
  const pct = drag(() => SCENE).x - 50
  ok('the element moves the same distance as the pointer', Math.round((pct / 100) * SCENE.w), 105)
}

// ── The old behaviour, for the record ───────────────────────────────────────
// Omitting the extent falls back to the viewer's box: 104.5/880 = 11.875% of the
// SCENE, which is 124px — a fifth further than the pointer went. Y is milder (950),
// which is exactly why the drift read as "worse to the right".
ok('pre-fix: the viewer fallback overshoots in x', drag(undefined).x, 62)
ok('pre-fix: and slightly less in y', drag(undefined).y, 61)
{
  const pre = drag(undefined)
  const pxMoved = ((pre.x - 50) / 100) * SCENE.w
  ok('pre-fix: 104.5px of pointer moved the element 125px (rounded to 62%)', Math.round(pxMoved), 125)
  ok('pre-fix: i.e. 1.2x the pointer, the reported drift', Math.round((pxMoved / 104.5) * 100) / 100, 1.2)
}

// ── The gate and the cleanup ────────────────────────────────────────────────
{
  for (const k of Object.keys(handlers)) delete handlers[k]
  let moved = null
  const d = usePercentDrag({ enabled: () => false, viewerEl, span: () => SCENE })
  d.start({ preventDefault() {}, clientX: 100, clientY: 100 }, { x: 50, y: 50, onMove: () => { moved = true } })
  ok('a disabled drag attaches nothing', Object.keys(handlers).length, 0)
  ok('and never calls onMove', moved, null)
}
{
  for (const k of Object.keys(handlers)) delete handlers[k]
  const d = usePercentDrag({ enabled: () => true, viewerEl, span: () => SCENE })
  d.start({ preventDefault() {}, clientX: 100, clientY: 100 }, { x: 50, y: 50, onMove: () => {} })
  ok('a live drag listens on document', ['mousemove', 'mouseup', 'touchmove', 'touchend'].every(t => (handlers[t] || []).length === 1), true)
  for (const h of handlers.mouseup || []) h({})
  ok('and removes every listener when it ends', Object.values(handlers).every(a => a.length === 0), true)
}

console.log(fail ? `\n  ${fail} failed\n` : '\n  all clear\n')
process.exit(fail ? 1 : 0)
