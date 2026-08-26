<template>
  <div class="ce-root">
    <div v-for="(c, i) in conditions" :key="i" class="ce-row">
      <select v-model="c.type">
        <option v-for="t in typeOptions" :key="t.value" :value="t.value">{{ t.label }}</option>
      </select>
      <input v-if="needsSubject(c.type)" v-model="c.subject" placeholder="entity (blank = current)" class="ce-subject" />
      <template v-if="needsTarget(c.type)">
        <div v-if="targetKind(c.type) === 'universe'" class="ce-target ce-picker">
          <UniversePicker v-model="c.target" />
        </div>
        <div v-else-if="targetKind(c.type)" class="ce-target ce-picker">
          <TargetPicker v-model="c.target" :kind="targetKind(c.type)" :placeholder="targetPlaceholder(c.type)" />
        </div>
        <input v-else v-model="c.target" :placeholder="targetPlaceholder(c.type)" class="ce-target" />
      </template>
      <select v-if="valueKind(c.type) === 'die'" v-model="c.value" class="ce-value">
        <option value="d4">d4</option>
        <option value="d6">d6</option>
        <option value="d8">d8</option>
        <option value="d10">d10</option>
        <option value="d12">d12</option>
      </select>
      <template v-else-if="valueKind(c.type) === 'number'">
        <select v-if="operators(c.type).length" v-model="c.operator" class="ce-operator">
          <option v-for="op in operators(c.type)" :key="op" :value="op">{{ op }}</option>
        </select>
        <input v-model="c.value" type="number" placeholder="amount" class="ce-value" />
      </template>
      <input v-if="c.type === 'NARRATIVE'" v-model="c.narrative" placeholder="narrative text" class="ce-target" />
      <button class="ce-del" @click="remove(i)">✕</button>
    </div>
    <button class="ce-add" @click="add">＋ Add condition</button>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useSfxMeta } from '@/composables/useSfxMeta.js'
import TargetPicker from './TargetPicker.vue'
import UniversePicker from './UniversePicker.vue'

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

function targetKind(type) {
  const meta = conditionTypes.value.find(c => c.value === type)
  return meta?.targetKind || ''
}

function valueKind(type) {
  const meta = conditionTypes.value.find(c => c.value === type)
  return meta?.valueKind || ''
}

function operators(type) {
  const meta = conditionTypes.value.find(c => c.value === type)
  return meta?.operators || []
}

function add() {
  const next = [...props.modelValue, { type: 'ALWAYS', subject: '', target: '', value: '', operator: '>=', narrative: '' }]
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
.ce-operator { flex: none !important; width: 58px; }
.ce-picker { min-width: 0; }
.ce-del { background: none; border: none; color: var(--danger); cursor: pointer; font-size: 12px; }
.ce-add { font-size: 10px; padding: 3px 8px; background: rgba(255,255,255,0.04); border: 1px dashed rgba(255,255,255,0.15); border-radius: 4px; color: var(--text-dim); cursor: pointer; }
.ce-add:hover { color: var(--text); }
</style>
