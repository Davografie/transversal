<template>
  <div class="die-picker">
    <button
      v-for="d in dieTypes"
      :key="d"
      class="die-btn"
      :class="{ active: selected.includes(d) }"
      @click="toggle(d)"
    >
      <DieIcon :die="d" :label="d" />
    </button>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import DieIcon from '@/components/DieIcon.vue'

const props = defineProps({
  modelValue: { type: Array, default: () => [] },
  dieTypes: { type: Array, default: () => ['d4', 'd6', 'd8', 'd10', 'd12'] },
})

const emit = defineEmits(['update:modelValue', 'add-die'])

const selected = computed(() =>
  Array.isArray(props.modelValue) ? props.modelValue : []
)

function toggle(d) {
  const current = [...selected.value]
  const idx = current.indexOf(d)
  if (idx >= 0) current.splice(idx, 1)
  else current.push(d)
  emit('update:modelValue', current)
  emit('add-die', d)
}
</script>

<style scoped>
.die-picker { display: flex; gap: 4px; flex-wrap: wrap; }
.die-btn {
  width: 40px; height: 44px; padding: 2px;
  background: transparent; border: 2px solid rgba(255,255,255,0.08);
  border-radius: 6px; cursor: pointer;
  transition: border-color 0.15s, transform 0.15s;
}
.die-btn:hover { border-color: rgba(255,255,255,0.2); }
.die-btn.active { border-color: var(--accent); transform: scale(1.05); }
.die-btn .die-icon { width: 100%; height: 100%; }
</style>
