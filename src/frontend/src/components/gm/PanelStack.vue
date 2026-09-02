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
import { ref, computed, provide, reactive, onMounted, onUnmounted } from 'vue'
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

// ── Depth tracking ──────────────────────────────────
// Panels register/unregister their depth on mount/unmount via provide/inject.
// Using reactive Map so the totalPanels computed reacts to changes.
// We track per-depth counts (not just total) so we can later implement
// per-depth visibility policies if needed.
const depthCounts = reactive(new Map())
function registerDepth(depth) {
  depthCounts.set(depth, (depthCounts.get(depth) || 0) + 1)
}
function unregisterDepth(depth) {
  const n = depthCounts.get(depth) || 0
  if (n <= 1) depthCounts.delete(depth)
  else depthCounts.set(depth, n - 1)
}
provide('registerDepth', registerDepth)
provide('unregisterDepth', unregisterDepth)

// ── Viewport-aware panel limit ──────────────────────
// Hides shallow panels when the stack is wider than the viewport.
// PANEL_EST_WIDTH = max-width (380px) + gap (8px)
// maxVisiblePanels = how many panels fit in (viewport - right margin)
// minVisibleDepth = panels below this depth get v-show=false
// Example: viewport 1247px, 4 panels open → minVisibleDepth=1 → depth-0 hidden
const PANEL_EST_WIDTH = 388  // max panel width + gap

const totalPanels = computed(() => {
  let sum = 0
  for (const [, n] of depthCounts) sum += n
  return sum
})
// Minimum 1 so the root panel is always visible, even on very narrow screens
const maxVisiblePanels = computed(() => Math.max(1, Math.floor((viewportWidth.value - 36) / PANEL_EST_WIDTH)))
const minVisibleDepth = computed(() => Math.max(0, totalPanels.value - maxVisiblePanels.value))

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
  border: 1px solid rgba(255,255,255,0.1);
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
