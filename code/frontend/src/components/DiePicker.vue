<template>
  <div class="die-picker">
    <button
      v-for="d in dieTypes"
      :key="d"
      class="die-btn"
      :class="{ active: isSelected(d) }"
      @click="toggle(d)"
    >
      <DieIcon :die="d" :label="d" />
    </button>
  </div>
</template>

<script setup>
import DieIcon from '../DieIcon.vue'

const props = defineProps({
  modelValue: { type: [String, Array], default: '' },
  multiple: { type: Boolean, default: false },
  dieTypes: { type: Array, default: () => ['d4', 'd6', 'd8', 'd10', 'd12'] },
})

const emit = defineEmits(['update:modelValue'])

function isSelected(d) {
  if (props.multiple) return Array.isArray(props.modelValue) && props.modelValue.includes(d)
  return props.modelValue === d
}

function toggle(d) {
  if (props.multiple) {
    const current = Array.isArray(props.modelValue) ? [...props.modelValue] : []
    const idx = current.indexOf(d)
    if (idx >= 0) current.splice(idx, 1)
    else current.push(d)
    emit('update:modelValue', current)
  } else {
    emit('update:modelValue', props.modelValue === d ? '' : d)
  }
}
</script>

<style scoped>
.die-picker {
  display: flex; gap: 4px; flex-wrap: wrap;
}
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
