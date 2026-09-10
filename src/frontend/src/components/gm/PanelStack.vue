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
      v-for="w in allWindows"
      :key="w.id"
      :anchor="anchorRect"
      :direction="'left'"
      :min-visible-depth="minVisibleDepth"
      :body-scroll="w.spec?.bodyScroll !== false"
      :title="w.spec?.title"
      :id="w.spec?.id"
      closable
      :on-close="w.id === 'root' ? null : () => closeWindow(w.id)"
      :on-replace="w.id === 'root' ? null : (spec) => replaceWindow(w.id, spec)"
      @close="onWindowClose(w)"
    >
      <template v-if="w.spec" #default>
        <component :is="w.spec.component" v-bind="w.spec.props || {}" v-on="w.spec.listeners || {}" />
      </template>
    </Panel>
  </div>
</template>

<script setup>
import { ref, computed, provide, reactive, onMounted, onUnmounted, watch, nextTick } from 'vue'
import Panel from './Panel.vue'
import { usePanelWindows } from '@/composables/usePanelWindows.js'
import { usePanelAnchor } from '@/composables/usePanelAnchor.js'

const props = defineProps({
  rootPanel: { type: Object, default: null },
})

const { windows, close: closeWindow, replace: replaceWindow } = usePanelWindows()
const { resolveAnchor, setAnchor } = usePanelAnchor()

const show = ref(false)

// ── Top-level windows ────────────────────────────────
// The root window is derived from the reactive `rootPanel` prop so its props
// (universe, currentLocationId, …) stay live. Extra windows come from the
// window registry (spawned/detached). Collapse/dock rendering is added in a
// later step; for now all windows render expanded and the single-root behavior
// is preserved.
const allWindows = computed(() => [
  { id: 'root', spec: props.rootPanel },
  ...windows.value,
])

function onWindowClose(w) {
  if (w.id === 'root') show.value = false
  else closeWindow(w.id)
}

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
    if (moved) logAnchor('drag-end')
    dragging.value = false
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
const depthWidths = reactive(new Map()) // depth -> Map(uid -> width)
let panelSeq = 0

function registerPanel(depth) {
  const uid = `p${++panelSeq}`
  if (!depthWidths.has(depth)) depthWidths.set(depth, new Map())
  depthWidths.get(depth).set(uid, 0)
  return uid
}
function setPanelWidth(depth, uid, width) {
  const m = depthWidths.get(depth)
  if (m) m.set(uid, width)
}
function unregisterPanel(depth, uid) {
  const m = depthWidths.get(depth)
  if (m) {
    m.delete(uid)
    if (m.size === 0) depthWidths.delete(depth)
  }
}
provide('registerPanel', registerPanel)
provide('setPanelWidth', setPanelWidth)
provide('unregisterPanel', unregisterPanel)

const minVisibleDepth = computed(() => {
  const depths = [...depthWidths.keys()].sort((a, b) => b - a)
  if (depths.length === 0) return 0
  // Usable span for the visible chain: panels' right edge sits at vw-34 (under
  // the action rail), left margin 12 → vw-46; the fit loop adds a gap per
  // depth, so the budget is vw-46 + 8 = vw-38.
  const available = viewportWidth.value - 38
  let total = 0
  let visibleFrom = null
  for (const d of depths) {
    let maxW = 0
    for (const w of depthWidths.get(d).values()) maxW = Math.max(maxW, w)
    total += maxW + GAP
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
  const summary = {}
  for (const [d, m] of depthWidths) summary[d] = Math.max(0, ...m.values())
  console.log('[panel-stack] min-visible-depth', JSON.stringify({
    from, to,
    viewportWidth: viewportWidth.value,
    available: viewportWidth.value - 38,
    depthWidths: summary,
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
