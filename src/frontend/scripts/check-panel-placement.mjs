/**
 * Executable check for the panel chain's placement (the "child opens above the
 * viewport" bug).
 *
 * The frontend has no test runner and no DOM, so this is a plain node script
 * that drives the **shipped** placement math — `crossStart` / `chainOffset` /
 * `activePosition` / `viewportFix` / `nodeStyle`, lifted out of `Panel.vue` —
 * through a chain of panels, with the measurement triggers the component
 * actually has. Run it against the frontend image:
 *
 *   docker run --rm \
 *     -v /path/to/src/frontend/scripts:/app/scripts:ro \
 *     -v /path/to/src/frontend/src:/app/src:ro \
 *     -w /app transversal2-frontend:latest node scripts/check-panel-placement.mjs
 *
 * The report: a child panel sometimes opened above the top of the viewport, its
 * own handle unable to bring it down, until the *parent's* handle was moved —
 * with the anchor near the top of the screen, and two levels down.
 *
 * The mechanism: a panel's measured node origin (`wrapperTopPx`/`wrapperLeftPx`)
 * is the origin its children are placed from, but it was only re-measured when
 * the panel's *offset props* or size changed. `viewportFix` can move a panel on
 * its own, and an ancestor moving moves it too (a new `originTop`, offsets
 * unchanged) — so the cached origin went stale. The levels below were then
 * placed from a position the panel no longer occupied, and because a child's own
 * clamp is computed in that same stale space the error compounded rather than
 * correcting, leaving a grandchild above the viewport. Moving the parent's
 * handle cured it because a slide calls `queueMeasure()`.
 *
 * The trigger is read from the shipping source, so this cannot pass while the
 * component lacks the fix — and the pre-fix trigger is run too, and must
 * reproduce the crop.
 */
import { readFileSync } from 'node:fs'
import { ref, computed } from 'vue'

let pass = 0, fail = 0
const ok = (name, got, want) => {
  const same = JSON.stringify(got) === JSON.stringify(want)
  same ? pass++ : fail++
  console.log(`${same ? '  PASS' : '  FAIL'}  ${name}${same ? '' : `\n         got ${JSON.stringify(got)}  want ${JSON.stringify(want)}`}`)
}

const PANEL = readFileSync(new URL('../src/components/gm/Panel.vue', import.meta.url), 'utf8')
const between = (src, from, to) => {
  const i = src.indexOf(from)
  const j = src.indexOf(to, i)
  if (i < 0 || j < 0) throw new Error(`marker missing: ${from}`)
  return src.slice(i, j)
}

const MARGIN = 12
const RAIL_OVERHANG = 20
const GAP = 8
const VH = 900, VW = 1440

// ── the shipped math ─────────────────────────────────────────────────────
const OFFSETS = between(PANEL, 'const crossTotal = computed(', '// Cap the active panel so the strip')
const FIX = between(PANEL, 'const viewportFix = computed(', '// The scope children clamp their rail to')

function makePanel({ depth, dir, w, h, vh, vw, anchor }) {
  const isVertical = dir === 'up' || dir === 'down'
  const isRoot = ref(depth === 0)
  const effectiveTop = ref(null), effectiveLeft = ref(null)
  const slideOffset = ref(0)
  const nodeSize = { w, h }
  const viewWidth = ref(vw), viewHeight = ref(vh)
  const originTop = ref(null), originLeft = ref(null)
  const tabExtent = ref(0), stripGap = ref(0), activeExtent = ref(0)
  const activeSize = ref({ w: 0, h: 0 })
  const activeChild = ref({ key: 'child' })   // `activePosition` only asks if one exists
  const isDepthHidden = ref(false)
  const placed = ref(true)
  const props = {
    direction: dir, gap: GAP, anchor,
    get originTop() { return originTop.value },
    get originLeft() { return originLeft.value },
    get top() { return effectiveTop.value },
    get left() { return effectiveLeft.value },
  }
  const scope = { ref, computed, isRoot, isVertical, effectiveTop, effectiveLeft, slideOffset,
    nodeSize, viewWidth, viewHeight, tabExtent, stripGap, activeExtent, activeSize, props,
    activeChild, isDepthHidden, placed, VIEWPORT_MARGIN: MARGIN }
  const api = new Function(...Object.keys(scope), `
    ${OFFSETS}
    ${FIX}
    return { crossStart, chainOffset, activePosition, viewportFix, nodeStyle }
  `)(...Object.values(scope))
  return { depth, dir, w, h, isVertical, effectiveTop, effectiveLeft, slideOffset, nodeSize,
    originTop, originLeft, tabExtent, stripGap, activeExtent, activeSize, props, ...api,
    wrapperTop: null, renderedTop: null, stale: false, fixY: 0 }
}

/** Root placement, verbatim from computeRootPosition. */
function rootTop(p, vh) {
  const a = p.props.anchor
  let top
  if (p.dir === 'down') top = a.bottom - RAIL_OVERHANG
  else if (p.dir === 'up') top = a.top + RAIL_OVERHANG - p.h
  else top = a.centerY - p.h / 2
  return Math.min(Math.max(top, MARGIN), Math.max(MARGIN, vh - p.h - MARGIN))
}

/**
 * Settle a chain. `trigger: 'offsets'` is the pre-fix rule (re-measure when the
 * offset props or size change); `'resolved'` is the fix (also when the panel's
 * real viewport position moves — a fix-induced move, or an ancestor's).
 */
function settle({ dir, heights, widths, trigger, vh = VH, vw = VW, anchorY, anchorX = vw - 30 }) {
  const anchor = { top: anchorY - 21, bottom: anchorY + 21, left: anchorX - 21, right: anchorX + 21,
    centerY: anchorY, centerX: anchorX }
  const chain = heights.map((h, i) => makePanel({ depth: i, dir, w: widths[i], h, vh, vw, anchor }))
  const unmeasured = new Set(chain.map((_, i) => i))
  const lastOffsets = chain.map(() => null)
  const lastSize = chain.map(() => null)
  const lastResolved = chain.map(() => null)
  let cropped = null

  for (let pass = 0; pass < 12; pass++) {
    chain.forEach((p) => { p.stale = false })

    // 1. offsets — the root's from computeRootPosition, a child's from its parent.
    chain.forEach((p, i) => {
      if (i === 0) { p.effectiveTop.value = rootTop(p, vh); p.effectiveLeft.value = 40; return }
      const parent = chain[i - 1]
      parent.activeSize.value = { w: p.w, h: p.h }
      parent.activeExtent.value = parent.isVertical ? p.w : p.h
      const pos = parent.activePosition.value
      p.effectiveTop.value = pos.top ?? 0
      p.effectiveLeft.value = pos.left ?? 0
    })

    // 2. resolve. The child sits on where its parent ACTUALLY is; its fix was
    //    computed against the parent's CACHED origin. That difference is the bug.
    chain.forEach((p, i) => {
      if (i === 0) {
        p.renderedTop = p.effectiveTop.value
        p.originTop.value = null; p.originLeft.value = null
        return
      }
      const parent = chain[i - 1]
      p.originTop.value = parent.wrapperTop
      p.originLeft.value = 20
      p.fixY = p.viewportFix.value.y
      p.renderedTop = (parent.renderedTop ?? 0) + parseFloat(p.nodeStyle.value.top)
    })

    // 3. measure — only on the triggers the component has.
    let changed = false
    chain.forEach((p, i) => {
      const size = `${p.w}x${p.h}`
      const parentTop = i === 0 ? 0 : (chain[i - 1].wrapperTop ?? 0)
      const resolved = `${Math.round(parentTop + (p.effectiveTop.value ?? 0) + (p.isVertical ? 0 : 0) + p.fixY)},` +
                       `${Math.round((i === 0 ? 0 : 20) + (p.effectiveLeft.value ?? 0) + (p.isVertical ? 0 : 0) + (p.viewportFix.value.x ?? 0))}`
      const triggers = unmeasured.has(i) || lastOffsets[i] !== `${p.effectiveTop.value},${p.effectiveLeft.value}` ||
                       lastSize[i] !== size || (trigger === 'resolved' && lastResolved[i] !== resolved)
      if (triggers) {
        unmeasured.delete(i)
        if (p.wrapperTop !== p.renderedTop) { p.wrapperTop = p.renderedTop; changed = true }
      } else if (p.wrapperTop !== p.renderedTop) p.stale = true
      lastOffsets[i] = `${p.effectiveTop.value},${p.effectiveLeft.value}`
      lastSize[i] = size
      lastResolved[i] = resolved
    })

    if (!changed) { chain.forEach((p) => { if (p.renderedTop != null && p.renderedTop < 0) cropped = p.depth }); break }
  }
  return { chain, cropped }
}

// ── the trigger the component ships ──────────────────────────────────────
console.log('\nwhich re-measure trigger the component ships\n')

const hasResolvedWatch = /watch\(\[resolvedTop, resolvedLeft\], \(\) => queueMeasure\(\)\)/.test(PANEL)
const hasOffsetWatch = /watch\(\[effectiveTop, effectiveLeft\], \(\) => nextTick\(measureSelf\)\)/.test(PANEL)
ok('the resolved-position watch is present', hasResolvedWatch, true)
ok('the offset-only watch is gone (one position trigger, not two)', hasOffsetWatch, false)
ok('the watch reads the origin too, so an ancestor moving re-measures',
  /const resolvedTop = computed\(\(\) => \{[\s\S]*?props\.originTop/.test(PANEL), true)
ok('…for the left axis as well',
  /const resolvedLeft = computed\(\(\) => \{[\s\S]*?props\.originLeft/.test(PANEL), true)
ok('and it includes the viewport fix it must stay consistent with',
  /resolvedTop[\s\S]*?viewportFix\.value\.y/.test(PANEL), true)

const TRIGGER = hasResolvedWatch && !hasOffsetWatch ? 'resolved' : 'offsets'

// ── the reported regime ──────────────────────────────────────────────────
console.log('\nthe reported shape — anchor near the top, root → panel → panel\n')

// "Put the root toggle somewhere on the right, but near the top of the screen,
// then open prep -> traits -> assets." Near the top, `deriveDirection` picks the
// top edge and the chain grows *downward*; the middle panel (36 traitsets) is
// taller than the root, so it needs a viewport fix, and the panel opened from it
// inherits the stale origin.
const REPRO = { dir: 'down', heights: [620, 900, 900], widths: [400, 400, 400], anchorY: 70 }

{
  const pre = settle({ ...REPRO, trigger: 'offsets' })
  const tops = pre.chain.map((p) => Math.round(p.renderedTop))
  ok('pre-fix: the grandchild settles above the viewport', pre.cropped, 2)
  ok('pre-fix: and the intermediate panel\'s cached origin is stale',
    pre.chain[1].wrapperTop !== pre.chain[1].renderedTop, true)
  console.log(`         tops ${JSON.stringify(tops)}; cached origins ${JSON.stringify(pre.chain.map((p) => Math.round(p.wrapperTop)))}`)

  const post = settle({ ...REPRO, trigger: TRIGGER })
  ok('fixed: the grandchild is inside the viewport', post.cropped, null)
  ok('fixed: every panel\'s cached origin matches where it really is',
    post.chain.every((p) => Math.abs(p.wrapperTop - p.renderedTop) < 1), true)
  ok('fixed: and its top is at the margin, not above it',
    Math.round(post.chain[2].renderedTop) >= MARGIN, true)
  console.log(`         tops ${JSON.stringify(post.chain.map((p) => Math.round(p.renderedTop)))} after the fix`)
}

// ── the sweep ────────────────────────────────────────────────────────────
console.log('\nthe same question over a sweep of shapes\n')

const DIRS = ['left', 'right', 'up', 'down']
const ANCHOR_Y = [40, 70, 120, 200, 400, 700, 860]
const HEIGHTS = [
  [620, 520, 900], [620, 900, 520], [900, 520, 620], [520, 620, 900],
  [400, 400, 400], [800, 300, 300], [300, 800, 300], [300, 300, 800],
  [620, 520, 400], [1000, 400, 400], [400, 1000, 400], [400, 400, 1000],
]

function sweep(trigger) {
  let cases = 0, cropped = 0, stale = 0
  for (const dir of DIRS) {
    for (const anchorY of ANCHOR_Y) {
      for (const hs of HEIGHTS) {
        const r = settle({ dir, heights: hs, widths: hs.map(() => 400), anchorY, trigger })
        cases++
        if (r.cropped != null) cropped++
        if (r.chain.some((p) => p.stale)) stale++
      }
    }
  }
  return { cases, cropped, stale }
}

const before = sweep('offsets')
const after = sweep(TRIGGER)
console.log(`         pre-fix:  ${before.cropped}/${before.cases} cropped, ${before.stale} with a stale origin`)
console.log(`         shipped:  ${after.cropped}/${after.cases} cropped, ${after.stale} with a stale origin`)

ok('pre-fix, the sweep finds configurations that crop (so the sweep is not vacuous)',
  before.cropped > 0 && before.stale > 0, true)
ok('shipped, no configuration crops', after.cropped, 0)
ok('shipped, no configuration is left with a stale origin', after.stale, 0)

console.log(fail ? `\n  ${fail} failed\n` : '\n  all clear\n')
process.exit(fail ? 1 : 0)
