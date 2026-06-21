<template>
  <button v-if="!show" class="gm-toggle" @click="show = true">🛠</button>

  <div v-if="show" class="panel-stack">
    <Panel :title="rootPanel?.title" :min-visible-depth="minVisibleDepth" closable @close="show = false">
      <template v-if="rootPanel" #default="{ open, close }">
        <component :is="rootPanel.component" :open="open" :close="close" v-bind="rootPanel.props || {}" v-on="rootPanel.listeners || {}" />
      </template>
    </Panel>
  </div>
</template>

<script setup>
import { ref, computed, provide, reactive, onMounted, onUnmounted } from 'vue'
import Panel from './Panel.vue'

defineProps({
  rootPanel: { type: Object, default: null },
})

const show = ref(false)

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
const viewportWidth = ref(window.innerWidth)

const totalPanels = computed(() => {
  let sum = 0
  for (const [, n] of depthCounts) sum += n
  return sum
})
const maxVisiblePanels = computed(() => Math.floor((viewportWidth.value - 36) / PANEL_EST_WIDTH))
const minVisibleDepth = computed(() => Math.max(0, totalPanels.value - maxVisiblePanels.value))

function onResize() {
  viewportWidth.value = window.innerWidth
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

 .panel-stack {
   position: fixed; top: 50%; right: 36px; transform: translateY(-50%); z-index: 25;
   display: flex; flex-direction: row-reverse; align-items: center; gap: 8px;
   pointer-events: none;
   max-width: calc(100vw - 36px);
 }
.panel-stack > :deep(*) {
  flex-shrink: 0;
  pointer-events: auto;
}

@media (max-width: 720px) {
  .gm-toggle { right: 8px; }
  .panel-stack {
    right: 8px;
    max-width: calc(100vw - 8px);
  }
}
</style>
