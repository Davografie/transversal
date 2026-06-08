<template>
  <div class="stack-root">
    <div
      v-for="(panel, i) in panels"
      :key="panel.id"
      class="stack-panel"
      :class="{ 'stack-active': i === panels.length - 1 }"
      :style="{ right: (i * 360) + 'px' }"
    >
      <button v-if="!panel.hideClose" class="stack-close" @click="$emit('close', i)">×</button>
      <div class="stack-body">
        <slot :name="'panel-' + i" :panel="panel">
          <component :is="panel.component" v-bind="panel.props || {}" @close="$emit('close', i)" />
        </slot>
      </div>
    </div>
  </div>
</template>

<script setup>
defineProps({
  panels: { type: Array, default: () => [] },
})
defineEmits(['close'])
</script>

<style scoped>
.stack-root {
  position: fixed; top: 50%; right: 60px; transform: translateY(-50%); z-index: 25;
  /* The stack itself sits just left of the GM panel toggle */
}

.stack-panel {
  position: absolute; top: 0;
  width: 340px; max-height: 80vh; overflow-y: auto;
  padding: 14px;
  background: var(--bg-panel); backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px);
  border-radius: 8px; border: 1px solid rgba(255,255,255,0.08);
  animation: panelSlideIn 0.2s ease;
}
@keyframes panelSlideIn { from { opacity: 0; transform: translateX(12px); } to { opacity: 1; transform: translateX(0); } }

.stack-close {
  position: absolute; top: 8px; right: 8px; z-index: 1;
  width: 28px; height: 28px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  font-size: 14px; padding: 0;
  background: var(--bg-panel); backdrop-filter: blur(12px);
  border: 1px solid rgba(255,255,255,0.15);
  cursor: pointer;
}
.stack-close:hover { background: rgba(255,255,255,0.1); }

.stack-body { margin-top: 4px; }

@media (max-width: 720px) {
  .stack-root { right: 8px; }
  .stack-panel {
    right: 0 !important; width: calc(100vw - 16px) !important;
    max-height: 70vh;
  }
  .stack-panel:not(.stack-active) { display: none; }
}
</style>
