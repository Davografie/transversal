<template>
  <button v-if="!show" class="gm-toggle" @click="show = true">🛠</button>

  <div v-if="show" ref="stackEl" class="panel-stack">
    <Panel :title="rootPanel?.title" closable @close="show = false">
      <template v-if="rootPanel" #default="{ open }">
        <component :is="rootPanel.component" :open="open" v-bind="rootPanel.props || {}" v-on="rootPanel.listeners || {}" />
      </template>
    </Panel>
  </div>
</template>

<script setup>
import { ref, watch, onMounted, onUnmounted, nextTick } from 'vue'
import Panel from './Panel.vue'

const props = defineProps({
  rootPanel: { type: Object, default: null },
})

const show = ref(false)
const stackEl = ref(null)

// ── Viewport-aware clipping ──
function recalc() {
  if (!stackEl.value) return
  const rect = stackEl.value.getBoundingClientRect()
  // keep for potential future use
}

let resizeTimer = null
function onResize() {
  clearTimeout(resizeTimer)
  resizeTimer = setTimeout(recalc, 50)
}

onMounted(() => {
  window.addEventListener('resize', onResize)
})
onUnmounted(() => {
  window.removeEventListener('resize', onResize)
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
