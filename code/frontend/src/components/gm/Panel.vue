<template>
  <div class="panel-wrapper">
    <button v-if="!hideClose" class="panel-close" @click="$emit('close')">×</button>
    <div class="panel">
      <slot />
    </div>
  </div>
</template>

<script setup>
defineProps({
  hideClose: { type: Boolean, default: false },
})
defineEmits(['close'])
</script>

<style scoped>
.panel-wrapper {
  position: relative;
  flex-shrink: 0;
}
.panel-close {
  position: absolute; top: 50%; right: -22px; transform: translateY(-50%); z-index: 2;
  width: 36px; height: 36px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  font-size: 14px; padding: 0;
  background: var(--bg-panel); backdrop-filter: blur(12px);
  border: 1px solid rgba(255,255,255,0.15);
  cursor: pointer;
}
.panel-close:hover { background: rgba(255,255,255,0.1); }

.panel {
  width: 340px; max-height: 80vh; overflow-y: auto;
  padding: 14px;
  background: var(--bg-panel); backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px);
  border-radius: 8px; border: 1px solid rgba(255,255,255,0.08);
  animation: panelSlideIn 0.2s ease;
}
@keyframes panelSlideIn { from { opacity: 0; transform: translateX(12px); } to { opacity: 1; transform: translateX(0); } }
</style>
