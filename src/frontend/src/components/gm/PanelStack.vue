<template>
  <button v-if="!show" class="gm-toggle" @click="show = true">🛠</button>

  <div v-if="show" class="panel-viewport">
    <Panel
      v-for="w in allWindows"
      :key="w.id"
      :anchor="anchorRect"
      :direction="'left'"
      :min-visible-depth="minVisibleDepth"
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
import { ref, computed, provide, reactive, onMounted, onUnmounted, watch } from 'vue'
import Panel from './Panel.vue'
import { usePanelWindows } from '@/composables/usePanelWindows.js'

const props = defineProps({
  rootPanel: { type: Object, default: null },
})

const { windows, close: closeWindow, replace: replaceWindow } = usePanelWindows()

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

// ── Anchor: the 🛠 toggle ─────────────────────────────
// The root panel is anchored to the toggle, centered on it as much as possible
// but always clamped inside the viewport (see Panel.vue `computeRootPosition`).
//
// Phase 1 derives the anchor arithmetically from the toggle's fixed CSS
// (`position: fixed; top: 50%; right: 12px; 42×42`). When the toggle becomes
// draggable (Phase 3), replace this with a live getBoundingClientRect() of the
// toggle element + its remembered edge/anchor.
const TOGGLE_SIZE = 42
const TOGGLE_RIGHT = 12

const viewportWidth = ref(window.innerWidth)
const viewportHeight = ref(window.innerHeight)

const anchorRect = computed(() => {
  const left = viewportWidth.value - TOGGLE_RIGHT - TOGGLE_SIZE
  const top = viewportHeight.value / 2 - TOGGLE_SIZE / 2
  return {
    left,
    right: left + TOGGLE_SIZE,
    top,
    bottom: top + TOGGLE_SIZE,
    centerX: left + TOGGLE_SIZE / 2,
    centerY: viewportHeight.value / 2,
  }
})

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
  // Space left of the toggle: viewport − (toggle 42 + right 12 + gap 8) − margin.
  const available = viewportWidth.value - 72
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
    available: viewportWidth.value - 72,
    depthWidths: summary,
  }))
})

function onResize() {
  viewportWidth.value = window.innerWidth
  viewportHeight.value = window.innerHeight
}

let resizeTimer = null
function debouncedResize() {
  clearTimeout(resizeTimer)
  resizeTimer = setTimeout(onResize, 100)
}

onMounted(() => {
  window.addEventListener('resize', debouncedResize)
})
onUnmounted(() => {
  window.removeEventListener('resize', debouncedResize)
})
</script>

<style scoped>
.gm-toggle {
  position: fixed; top: 50%; right: 12px; transform: translateY(-50%); z-index: 26;
  width: 42px; height: 42px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  font-size: 20px; padding: 0;
  background: var(--bg-panel); backdrop-filter: blur(12px);
  border: 1px solid var(--overlay-10);
  cursor: pointer;
}

/* Full-viewport, pointer-transparent coordinate space. Panels position
   themselves absolutely inside it; the root's offsets are viewport coords
   because this element sits at (0,0) with no transform/filter (which would
   otherwise create a containing block for fixed descendants). */
.panel-viewport {
  position: fixed; inset: 0; z-index: 25;
  pointer-events: none;
}
</style>
