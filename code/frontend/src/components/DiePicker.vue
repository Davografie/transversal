<template>
  <div class="die-picker">
    <button class="die-btn empty-btn" :class="{ active: !modelValue }" @click="$emit('update:modelValue', '')">
      <span class="empty-label">×</span>
    </button>
    <button
      v-for="d in dieTypes"
      :key="d"
      class="die-btn"
      :class="{ active: modelValue === d }"
      @click="$emit('update:modelValue', d)"
    >
      <DieIcon :die="d" :label="d" />
    </button>
  </div>
</template>

<script setup>
import DieIcon from '@/components/DieIcon.vue'

defineProps({
  modelValue: { type: String, default: '' },
  dieTypes: { type: Array, default: () => ['d4', 'd6', 'd8', 'd10', 'd12'] },
})

defineEmits(['update:modelValue'])
</script>

<style scoped>
.die-picker { display: flex; gap: 4px; flex-wrap: wrap; }
.die-btn {
  width: 40px; height: 44px; padding: 2px;
  background: transparent; border: 2px solid rgba(255,255,255,0.08);
  border-radius: 6px; cursor: pointer;
  transition: border-color 0.15s, transform 0.15s;
  display: flex; align-items: center; justify-content: center;
}
.die-btn:hover { border-color: rgba(255,255,255,0.2); }
.die-btn.active { border-color: var(--accent); transform: scale(1.05); }
.die-btn .die-icon { width: 100%; height: 100%; }
.empty-btn { font-size: 18px; color: var(--text-dim); }
.empty-btn:hover { color: var(--text); }
</style>
