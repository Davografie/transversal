<template>
  <div class="ce-root">
    <div v-for="(c, i) in conditions" :key="i" class="ce-row">
      <select v-model="c.type">
        <option value="ALWAYS">Always</option>
        <option value="AT_LOCATION">At location</option>
        <option value="HAS_TRAIT">Has trait</option>
        <option value="HAS_RELATIONSHIP">Has relationship</option>
        <option value="NARRATIVE">Narrative</option>
      </select>
      <input v-if="c.type !== 'ALWAYS' && c.type !== 'NARRATIVE'" v-model="c.target" placeholder="target id" class="ce-target" />
      <input v-if="c.type === 'HAS_TRAIT' || c.type === 'AT_LOCATION'" v-model="c.value" placeholder="value" class="ce-value" />
      <input v-if="c.type === 'NARRATIVE'" v-model="c.narrative" placeholder="narrative text" class="ce-target" />
      <button class="ce-del" @click="remove(i)">✕</button>
    </div>
    <button class="ce-add" @click="add">＋ Add condition</button>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  modelValue: { type: Array, default: () => [] },
})
const emit = defineEmits(['update:modelValue'])

const conditions = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

function add() {
  const next = [...props.modelValue, { type: 'ALWAYS', target: '', value: '', narrative: '' }]
  emit('update:modelValue', next)
}

function remove(i) {
  const next = [...props.modelValue]
  next.splice(i, 1)
  emit('update:modelValue', next)
}
</script>

<style scoped>
.ce-root { display: flex; flex-direction: column; gap: 4px; }
.ce-row { display: flex; gap: 4px; align-items: center; }
.ce-row select, .ce-row input {
  font-size: 11px; padding: 4px 6px;
  background: rgba(255,255,255,0.06); color: var(--text);
  border: 1px solid rgba(255,255,255,0.1); border-radius: 4px;
  font-family: inherit; flex: 1; min-width: 0;
}
.ce-target { flex: 2 !important; }
.ce-value { flex: 1 !important; }
.ce-del { background: none; border: none; color: var(--danger); cursor: pointer; font-size: 12px; }
.ce-add { font-size: 10px; padding: 3px 8px; background: rgba(255,255,255,0.04); border: 1px dashed rgba(255,255,255,0.15); border-radius: 4px; color: var(--text-dim); cursor: pointer; }
.ce-add:hover { color: var(--text); }
</style>
