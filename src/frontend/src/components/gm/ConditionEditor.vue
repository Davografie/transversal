<template>
  <div class="ce-root">
    <div v-for="(c, i) in conditions" :key="i" class="ce-row">
      <select v-model="c.type">
        <option v-for="t in typeOptions" :key="t.value" :value="t.value">{{ t.label }}</option>
      </select>
      <input v-if="needsSubject(c.type)" v-model="c.subject" placeholder="entity (blank = current)" class="ce-subject" />
      <input v-if="needsTarget(c.type)" v-model="c.target" :placeholder="targetPlaceholder(c.type)" class="ce-target" />
      <select v-if="c.type === 'TRAIT_RATING'" v-model="c.value" class="ce-value">
        <option value="d4">d4</option>
        <option value="d6">d6</option>
        <option value="d8">d8</option>
        <option value="d10">d10</option>
        <option value="d12">d12</option>
      </select>
      <input v-if="c.type === 'NARRATIVE'" v-model="c.narrative" placeholder="narrative text" class="ce-target" />
      <button class="ce-del" @click="remove(i)">✕</button>
    </div>
    <button class="ce-add" @click="add">＋ Add condition</button>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useSfxMeta } from '@/composables/useSfxMeta.js'

const props = defineProps({
  modelValue: { type: Array, default: () => [] },
})
const emit = defineEmits(['update:modelValue'])

const conditions = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const { load: loadSfxMeta, conditionTypes } = useSfxMeta()
loadSfxMeta()

// Backend condition-type vocabulary, plus any current type not listed yet
// (so saving never silently drops a legacy/unknown type).
const typeOptions = computed(() => {
  const opts = [...conditionTypes.value]
  for (const c of props.modelValue) {
    if (c.type && !opts.some(o => o.value === c.type)) {
      opts.push({ value: c.type, label: c.type })
    }
  }
  return opts
})

function needsTarget(type) {
  return conditionTypes.value.some(c => c.value === type && c.needsTarget)
}

function needsSubject(type) {
  return type !== 'ALWAYS' && type !== 'NARRATIVE'
}

function targetPlaceholder(type) {
  const meta = conditionTypes.value.find(c => c.value === type)
  return meta?.targetPlaceholder || 'target id'
}

function add() {
  const next = [...props.modelValue, { type: 'ALWAYS', subject: '', target: '', value: '', narrative: '' }]
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
.ce-subject { flex: 1.5 !important; }
.ce-value { flex: 1 !important; }
.ce-del { background: none; border: none; color: var(--danger); cursor: pointer; font-size: 12px; }
.ce-add { font-size: 10px; padding: 3px 8px; background: rgba(255,255,255,0.04); border: 1px dashed rgba(255,255,255,0.15); border-radius: 4px; color: var(--text-dim); cursor: pointer; }
.ce-add:hover { color: var(--text); }
</style>
