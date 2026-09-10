<template>
  <button
    v-if="!show"
    ref="toggleEl"
    class="gm-toggle"
    :class="{ 'is-dragging': dragging }"
    :style="toggleStyle"
    @pointerdown="onTogglePointerDown"
    @click="onToggleClick"
  >🛠</button>

  <div v-if="show" class="panel-viewport">
    <Panel
      :anchor="anchorRect"
      :direction="direction"
      :min-visible-depth="minVisibleDepth"
      :body-scroll="props.rootPanel?.bodyScroll !== false"
      :title="props.rootPanel?.title"
      :id="props.rootPanel?.id"
      :spec="props.rootPanel"
      :window-id="'root'"
      closable
      @close="show = false"
    >
      <template v-if="props.rootPanel" #default>
        <component :is="props.rootPanel.component" v-bind="props.rootPanel.props || {}" v-on="props.rootPanel.listeners || {}" />
      </template>
    </Panel>
  </div>

  <!-- Floating windows are independent of the stack: switching the 🛠 off hides
       the chain, not the windows. -->
  <div v-if="windows.length" class="panel-viewport">
    <PanelWindow
      v-for="w in windows"
      :key="w.id"
      :win="w"
      :dockable="isDockable(w)"
      @close="closeWindow(w.id)"
      @dock="dockWindow(w.id)"
    />
  </div>
</template>

<script setup>
import { ref, computed, provide, reactive, onMounted, onUnmounted, watch, nextTick } from 'vue'
import Panel from './Panel.vue'
import PanelWindow from './PanelWindow.vue'
import { usePanelWindows } from '@/composables/usePanelWindows.js'
import { usePanelAnchor } from '@/composables/usePanelAnchor.js'
import { lookupPanelIdentity } from '@/composables/usePanel.js'
import { dumpPanelLayoutSoon } from '@/composables/usePanelDiagnostics.js'

const props = defineProps({
  rootPanel: { type: Object, default: null },
})

const { windows, close: closeWindow } = usePanelWindows()
const { direction, resolveAnchor, deriveDirection, snapToEdge, setAnchor } = usePanelAnchor()

const show = ref(false)

// ── Floating windows ─────────────────────────────────
// A window docks back into the panel it was detached from — matched by what
// that panel *was* (component + spec id), so a parent that was closed and
// re-opened is a valid target again. While no such panel is open, the window
// has no dock target and the affordance is hidden.
function isDockable(w) {
  return !!(w.sourceParentKey && lookupPanelIdentity(w.sourceParentKey))
}

function dockWindow(id) {
  const w = windows.value.find((x) => x.id === id)
  if (!w) return
  const target = w.sourceParentKey ? lookupPanelIdentity(w.sourceParentKey) : null
  if (!target) return
  // openChild makes the returning panel the parent's active child.
  target.openChild(w.spec)
  closeWindow(id)
}

// ── Top-level windows ────────────────────────────────
// The root window's spec is a prop (its props stay live from App.vue); extra
// windows come from the window registry (detached panels).

// ── Anchor: the 🛠 toggle / the rail's ⠿ handle ────────
// The chain derives its position from one point: the toggle's spot when the
// stack is closed, the shallowest visible panel's rail when it is open (the
// two occupy the same spot — the button “becomes” the rail). The point is
// draggable: the 🛠 itself (with a click/drag threshold, so a tap still opens)
// and the rail's ⠿ handle (drag-only). Every panel re-derives from the anchor,
// so the whole chain follows the drag. See usePanelAnchor.js for the position.
const TOGGLE_SIZE = 42

const viewportWidth = ref(window.innerWidth)
const viewportHeight = ref(window.innerHeight)

const anchorCenter = computed(() => resolveAnchor(viewportWidth.value, viewportHeight.value))

// The chain's open direction follows the anchor's edge — but only while the
// anchor is inside an edge band; away from every edge it keeps the direction it
// had, so a mid-screen drag doesn't flip the stack back and forth. At rest the
// anchor is always snapped to an edge, so the direction is stable there.
watch(anchorCenter, (a) => {
  const next = deriveDirection(a.x, a.y, viewportWidth.value, viewportHeight.value)
  if (next) direction.value = next
}, { immediate: true })

const anchorRect = computed(() => {
  const { x, y } = anchorCenter.value
  const half = TOGGLE_SIZE / 2
  return {
    left: x - half,
    right: x + half,
    top: y - half,
    bottom: y + half,
    centerX: x,
    centerY: y,
  }
})

const toggleStyle = computed(() => ({
  left: (anchorCenter.value.x - TOGGLE_SIZE / 2) + 'px',
  top: (anchorCenter.value.y - TOGGLE_SIZE / 2) + 'px',
}))

// ── Dragging the anchor ───────────────────────────────
// Pointer-driven; the anchor follows and the panels re-derive, so the chain
// moves with the pointer. A threshold keeps the 🛠's click intact: below it the
// press is a click, above it a drag — and the click that follows the drag is
// swallowed so releasing doesn't also open/close the stack.
const DRAG_THRESHOLD = 4
const dragging = ref(false)
let suppressToggleClick = false

function startDrag(e, { threshold = 0 } = {}) {
  if (typeof e.button === 'number' && e.button !== 0) return
  // The ⠿ handle is drag-only, so it can claim the gesture immediately; the 🛠
  // must not, or it would eat its own click.
  if (threshold <= 0) e.preventDefault()
  const startX = e.clientX
  const startY = e.clientY
  const start = anchorCenter.value
  let moved = threshold <= 0
  suppressToggleClick = false
  dumpPanelLayoutSoon('anchor-drag-start', { source: threshold > 0 ? 'toggle' : 'rail' })

  function onMove(ev) {
    const dx = ev.clientX - startX
    const dy = ev.clientY - startY
    if (!moved && Math.hypot(dx, dy) < threshold) return
    moved = true
    dragging.value = true
    setAnchor(start.x + dx, start.y + dy)
  }
  function finish() {
    window.removeEventListener('pointermove', onMove)
    window.removeEventListener('pointerup', finish)
    window.removeEventListener('pointercancel', finish)
    if (moved) {
      // Come to rest on the nearest viewport edge: the button stays findable,
      // and the edge it lands on settles the stack's direction.
      const vw = window.innerWidth
      const vh = window.innerHeight
      const snapped = snapToEdge(anchorCenter.value.x, anchorCenter.value.y, vw, vh)
      setAnchor(snapped.x, snapped.y)
      logAnchor('drag-end-snap')
    }
    dragging.value = false
    dumpPanelLayoutSoon('anchor-drag-release', {
      source: threshold > 0 ? 'toggle' : 'rail',
      moved,
      anchor: { ...anchorCenter.value },
      direction: direction.value,
      minVisibleDepth: minVisibleDepth.value,
    })
    if (moved && threshold > 0) {
      // Swallow the click the browser fires right after this drag (browsers
      // dispatch it synchronously behind pointerup). The flag must not outlive
      // that click: if the pointerup landed off the button there is no click at
      // all, and the *next* real click would be eaten — so clear on the next
      // task, which is still after the drag's own click.
      suppressToggleClick = true
      setTimeout(() => { suppressToggleClick = false }, 0)
    }
  }
  window.addEventListener('pointermove', onMove)
  window.addEventListener('pointerup', finish)
  window.addEventListener('pointercancel', finish)
}

function onTogglePointerDown(e) {
  startDrag(e, { threshold: DRAG_THRESHOLD })
}

// Panels consume this through `inject` (the rail's ⠿ handle).
provide('panelAnchorDrag', { begin: startDrag })
// The live anchor point — the anchor rail pins itself to it.
provide('panelAnchorPoint', anchorCenter)
// Bumped on every anchor move so *all* panels re-measure (a child's rail is
// viewport-pinned too when it is the shallowest visible one).
const anchorVersion = ref(0)
watch(anchorCenter, () => { anchorVersion.value++ })
provide('anchorVersion', anchorVersion)

function logAnchor(reason) {
  if (typeof window === 'undefined' || !window.__PANEL_DEBUG__) return
  const c = anchorCenter.value
  console.log('[panel-stack] anchor', JSON.stringify({
    reason, x: Math.round(c.x), y: Math.round(c.y),
  }))
}

// Diagnostic: the REAL toggle button rect vs the arithmetic anchor, so the two
// can be compared (window.__PANEL_DEBUG__ = true).
const toggleEl = ref(null)

function onToggleClick() {
  if (suppressToggleClick) {
    // The press that just ended was a drag, not a click.
    suppressToggleClick = false
    return
  }
  logToggleAnchor('open-click')
  show.value = true
}

function toggleRect() {
  const el = toggleEl.value
  if (!el) return null
  const r = el.getBoundingClientRect()
  return {
    top: Math.round(r.top), bottom: Math.round(r.bottom),
    left: Math.round(r.left), right: Math.round(r.right),
    w: Math.round(r.width), h: Math.round(r.height),
    centerX: Math.round(r.left + r.width / 2),
    centerY: Math.round(r.top + r.height / 2),
  }
}

function logToggleAnchor(reason = '') {
  if (typeof window === 'undefined' || !window.__PANEL_DEBUG__) return
  console.log('[panel-stack] toggle-anchor', JSON.stringify({
    reason,
    rect: toggleRect(),
    computedAnchor: { ...anchorRect.value },
  }))
}

// ── Horizontal fit (viewport-aware panel limit) ─────
// Track each mounted panel's width per depth. The deepest chain's horizontal
// extent (per-depth widths + gaps) decides how many shallow levels to hide so
// the leftmost panel stays inside the viewport. Per-depth MAX width is exact
// for a chain (the common case) and a safe upper bound for a tree. Hidden
// levels re-anchor the chain rightward (see Panel.vue's display:none + bridge
// pass-through).
const GAP = 8
// Per-depth measured sizes. Both axes are tracked: lateral chains fit by width,
// vertical chains by height (the extent the chain grows along).
const depthSizes = reactive(new Map()) // depth -> Map(uid -> { w, h })
let panelSeq = 0

function registerPanel(depth) {
  const uid = `p${++panelSeq}`
  if (!depthSizes.has(depth)) depthSizes.set(depth, new Map())
  depthSizes.get(depth).set(uid, { w: 0, h: 0 })
  return uid
}
function setPanelSize(depth, uid, w, h) {
  const m = depthSizes.get(depth)
  if (m) m.set(uid, { w, h })
}
function unregisterPanel(depth, uid) {
  const m = depthSizes.get(depth)
  if (m) {
    m.delete(uid)
    if (m.size === 0) depthSizes.delete(depth)
  }
}
provide('registerPanel', registerPanel)
provide('setPanelSize', setPanelSize)
provide('unregisterPanel', unregisterPanel)

const minVisibleDepth = computed(() => {
  const vertical = direction.value === 'up' || direction.value === 'down'
  const depths = [...depthSizes.keys()].sort((a, b) => b - a)
  if (depths.length === 0) return 0
  // Usable span for the visible chain, plus one gap for the fit loop. Lateral:
  // the panel's right edge sits at vw-34 (under the action rail), left margin
  // 12 → vw-46 (+8 = vw-38). Vertical: the anchor is clamped to EDGE_Y = 58 of
  // the edge, the panel's inner edge ~1 past it, opposite margin 12 → vh-71
  // (+8 = vh-63).
  const available = vertical ? viewportHeight.value - 63 : viewportWidth.value - 38
  let total = 0
  let visibleFrom = null
  for (const d of depths) {
    let maxExtent = 0
    for (const s of depthSizes.get(d).values()) {
      maxExtent = Math.max(maxExtent, vertical ? s.h : s.w)
    }
    total += maxExtent + GAP
    if (total <= available) {
      visibleFrom = d
    } else {
      break
    }
  }
  // If even the deepest alone doesn't fit, keep only the deepest visible.
  return visibleFrom === null ? depths[0] : visibleFrom
})

// Diagnostic: log the visibility threshold and per-depth widths so the chain
// can be inspected live (window.__PANEL_DEBUG__ = true).
watch(minVisibleDepth, (to, from) => {
  if (typeof window === 'undefined' || !window.__PANEL_DEBUG__) return
  const vertical = direction.value === 'up' || direction.value === 'down'
  const summary = {}
  for (const [d, m] of depthSizes) {
    summary[d] = Math.max(0, ...[...m.values()].map((s) => (vertical ? s.h : s.w)))
  }
  console.log('[panel-stack] min-visible-depth', JSON.stringify({
    from, to, direction: direction.value,
    viewport: vertical ? viewportHeight.value : viewportWidth.value,
    available: vertical ? viewportHeight.value - 63 : viewportWidth.value - 38,
    extents: summary,
  }))
})

function onResize() {
  viewportWidth.value = window.innerWidth
  viewportHeight.value = window.innerHeight
  nextTick(() => logToggleAnchor('resize'))
}

let resizeTimer = null
function debouncedResize() {
  clearTimeout(resizeTimer)
  resizeTimer = setTimeout(onResize, 100)
}

onMounted(() => {
  window.addEventListener('resize', debouncedResize)
  nextTick(() => logToggleAnchor('mount'))
})
// Log the toggle's rect when it reappears after the panels close.
watch(show, (v) => {
  if (!v) nextTick(() => logToggleAnchor('closed'))
})
onUnmounted(() => {
  window.removeEventListener('resize', debouncedResize)
})
</script>

<style scoped>
.gm-toggle {
  position: fixed; z-index: 26;
  width: 42px; height: 42px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  font-size: 20px; padding: 0;
  background: var(--bg-panel); backdrop-filter: blur(12px);
  border: 1px solid var(--overlay-10);
  cursor: grab;
  touch-action: none;
}
.gm-toggle.is-dragging { cursor: grabbing; }

/* Full-viewport, pointer-transparent coordinate space. Panels position
   themselves absolutely inside it; the root's offsets are viewport coords
   because this element sits at (0,0) with no transform/filter (which would
   otherwise create a containing block for fixed descendants). */
.panel-viewport {
  position: fixed; inset: 0; z-index: 25;
  pointer-events: none;
}
</style>
