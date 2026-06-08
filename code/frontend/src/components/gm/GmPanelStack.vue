<template>
  <!-- Close buttons between adjacent panels -->
  <button
    v-for="(_, i) in panels.slice(1)"
    :key="'close-' + i"
    class="ps-close"
    :style="closeStyle(i)"
    @click="closePanel(i)"
  >×</button>

  <!-- Panels -->
  <div
    v-for="(panel, i) in panels"
    :key="panel.id"
    class="ps-panel"
    :class="{ 'ps-active': i === panels.length - 1 }"
    :style="panelStyle(i)"
  >
    <div class="ps-header" v-if="panel.title || (i > 0 && !panel.hideBack)">
      <button v-if="i > 0 && !panel.hideBack" class="ps-back" @click="closePanel(i)">←</button>
      <h4 v-if="panel.title">{{ panel.title }}</h4>
    </div>
    <component :is="panel.component" v-bind="panel.props || {}" @close="closePanel(i)" @select="$emit('select', $event)" @save="$emit('save', $event)" @add-trait="$emit('add-trait', $event)" />
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  panels: { type: Array, default: () => [] },
})

const emit = defineEmits(['close'])

function closePanel(index) {
  // index is the level of the panel to close (closes it and all deeper)
  emit('close', index)
}

function panelStyle(level) {
  const base = 370
  return { right: (base + level * base) + 'px' }
}

function closeStyle(level) {
  // Close button for panel at `level` (1-indexed in slice)
  // Position between panel[level-1] and panel[level]
  const base = 370
  const prevRight = base + (level - 1) * base  // right edge of previous panel
  const curRight = base + level * base          // right edge of current panel
  // Center between them, accounting for panel widths (~340px)
  const mid = (prevRight + curRight) / 2 - 12
  return { right: mid + 'px' }
}
</script>

<style scoped>
.ps-panel {
  position: fixed; top: 50%; transform: translateY(-50%); z-index: 25;
  width: 340px; max-height: 80vh; overflow-y: auto;
  padding: 14px;
  background: var(--bg-panel); backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px);
  border-radius: 8px; border: 1px solid rgba(255,255,255,0.08);
  animation: psSlideIn 0.2s ease;
}
@keyframes psSlideIn { from { opacity: 0; transform: translateY(-50%) translateX(12px); } to { opacity: 1; transform: translateY(-50%) translateX(0); } }

.ps-header { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; }
.ps-header h4 { font-size: 14px; margin: 0; flex: 1; }
.ps-back { font-size: 14px; padding: 2px 8px; background: none; color: var(--text-dim); border: none; cursor: pointer; }
.ps-back:hover { color: var(--text); }

.ps-close {
  position: fixed; top: 50%; transform: translateY(-50%); z-index: 30;
  width: 30px; height: 30px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  font-size: 14px; padding: 0;
  background: var(--bg-panel); backdrop-filter: blur(12px);
  border: 1px solid rgba(255,255,255,0.15);
  animation: psFadeIn 0.15s ease;
}
@keyframes psFadeIn { from { opacity: 0; } to { opacity: 1; } }

/* Mobile: center the deepest panel */
@media (max-width: 720px) {
  .ps-panel {
    right: 50% !important;
    transform: translate(50%, -50%) !important;
    width: calc(100vw - 16px);
    max-height: 70vh;
  }
  .ps-panel:not(.ps-active) { display: none; }
  .ps-close { right: 12px !important; }
}
</style>
