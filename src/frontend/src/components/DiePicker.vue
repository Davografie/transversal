<template>
  <div class="die-picker" :class="{ multiple }">
    <template v-if="multiple">
      <button
        v-for="d in dieTypes"
        :key="d"
        class="die-btn"
        :class="{ active: (modelValue || []).includes(d) }"
        :title="`Add ${d}`"
        @click="add(d)"
      >
        <DieIcon :die="d" :label="d" />
      </button>
      <button class="die-btn empty-btn" title="Clear all" @click="clear">×</button>
      <div class="die-array">
        <span v-if="!(modelValue || []).length" class="die-array-empty">no dice</span>
        <span v-for="(d, i) in (modelValue || [])" :key="i" class="die-array-chip">
          <DieIcon :die="d" :label="d" />
          <button class="die-chip-remove" title="Remove" @click="removeAt(i)">×</button>
        </span>
      </div>
    </template>
    <template v-else>
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
    </template>
  </div>
</template>

<script setup>
import DieIcon from '@/components/DieIcon.vue'

const props = defineProps({
  modelValue: { type: [String, Array], default: '' },
  dieTypes: { type: Array, default: () => ['d4', 'd6', 'd8', 'd10', 'd12'] },
  multiple: { type: Boolean, default: false },
})

const emit = defineEmits(['update:modelValue'])

function add(d) {
  emit('update:modelValue', [...(props.modelValue || []), d])
}

function removeAt(i) {
  const next = [...(props.modelValue || [])]
  next.splice(i, 1)
  emit('update:modelValue', next)
}

function clear() {
  emit('update:modelValue', [])
}
</script>

<style scoped>
.die-picker { display: flex; gap: 4px; flex-wrap: wrap; align-items: center; }
.die-btn {
  width: 40px; height: 44px; padding: 2px;
  background: transparent; border: 2px solid var(--overlay-8);
  border-radius: 6px; cursor: pointer;
  transition: border-color 0.15s, transform 0.15s;
  display: flex; align-items: center; justify-content: center;
}
.die-btn:hover { border-color: var(--overlay-20); }
.die-btn.active { border-color: var(--accent); transform: scale(1.05); }
.die-btn .die-icon { width: 100%; height: 100%; }
.empty-btn { font-size: 18px; color: var(--text-dim); }
.empty-btn:hover { color: var(--text); }
.die-array { display: flex; gap: 4px; flex-wrap: wrap; align-items: center; width: 100%; }
.die-array-empty { font-size: 10px; color: var(--text-dim); font-style: italic; }
.die-array-chip {
  display: inline-flex; align-items: center; gap: 2px;
  background: var(--overlay-6); border: 1px solid var(--overlay-10);
  border-radius: 4px; padding: 2px 3px;
}
.die-array-chip .die-icon { width: 24px; height: 24px; }
.die-chip-remove {
  border: none; background: none; color: var(--text-dim); cursor: pointer;
  font-size: 11px; line-height: 1; padding: 0 1px;
}
.die-chip-remove:hover { color: var(--danger-soft); }
</style>
