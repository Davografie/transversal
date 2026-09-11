<template>
  <div class="ce-root">
    <div v-for="(c, i) in conditions" :key="i" class="ce-row" :class="{ 'ce-row-spec': usesSpec(c.type) }">
      <select v-model="c.type">
        <option v-for="t in typeOptions" :key="t.value" :value="t.value" :disabled="!typeUsable(t)">{{ t.label }}{{ optionReason(t) }}</option>
      </select>
      <span v-if="selectedProblem(c.type)" class="ce-warn">{{ selectedProblem(c.type) }}</span>
      <template v-if="usesSpec(c.type)">
        <TargetSpecBuilder v-model="c.spec" :source-element="sourceElement" title="Condition path" boolean-terminal class="ce-spec" />
      </template>
      <template v-else>
        <input v-if="needsSubject(c.type)" v-model="c.subject" placeholder="entity (blank = current)" class="ce-subject" />
        <template v-if="needsTarget(c.type)">
          <div v-if="targetKind(c.type) === 'universe'" class="ce-target ce-picker">
            <UniversePicker v-model="c.target" />
          </div>
          <div v-else-if="targetKind(c.type)" class="ce-target ce-picker">
            <TargetPicker v-model="c.target" :kind="targetKind(c.type)" :placeholder="targetPlaceholder(c.type)" />
          </div>
          <select v-else-if="targetOptions(c.type).length" v-model="c.target" class="ce-target">
            <option value="">{{ targetPlaceholder(c.type) }}</option>
            <option v-for="o in targetOptions(c.type)" :key="o" :value="o">{{ o }}</option>
          </select>
          <input v-else v-model="c.target" :placeholder="targetPlaceholder(c.type)" class="ce-target" />
        </template>
        <template v-if="valueKind(c.type) === 'die'">
          <select v-if="operators(c.type).length" v-model="c.operator" class="ce-operator">
            <option v-for="op in operators(c.type)" :key="op" :value="op">{{ op }}</option>
          </select>
          <select v-model="c.value" class="ce-value">
            <option value="d4">d4</option>
            <option value="d6">d6</option>
            <option value="d8">d8</option>
            <option value="d10">d10</option>
            <option value="d12">d12</option>
          </select>
        </template>
        <template v-else-if="valueKind(c.type) === 'number'">
          <select v-if="operators(c.type).length" v-model="c.operator" class="ce-operator">
            <option v-for="op in operators(c.type)" :key="op" :value="op">{{ op }}</option>
          </select>
          <input v-model="c.value" type="number" placeholder="amount" class="ce-value" />
        </template>
        <template v-else-if="valueKind(c.type) === 'tier'">
          <select v-if="operators(c.type).length" v-model="c.operator" class="ce-operator">
            <option v-for="op in operators(c.type)" :key="op" :value="op">{{ op }}</option>
          </select>
          <select v-model="c.value" class="ce-value">
            <option value="fail">fail</option>
            <option value="marginal">marginal</option>
            <option value="success">success</option>
            <option value="exceptional">exceptional</option>
            <option value="perfect">perfect</option>
          </select>
        </template>
        <input v-if="c.type === 'NARRATIVE'" v-model="c.narrative" placeholder="narrative text" class="ce-target" />
      </template>
      <Button class="ce-del" variant="danger-ghost" size="sm" @click="remove(i)">✕</Button>
    </div>
    <Button class="ce-add" variant="secondary" block @click="add">＋ Add condition</Button>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useSfxMeta } from '@/composables/useSfxMeta.js'
import TargetPicker from '@/components/ui/TargetPicker.vue'
import UniversePicker from './UniversePicker.vue'
import TargetSpecBuilder from './TargetSpecBuilder.vue'
import Button from '@/components/ui/Button.vue'

const props = defineProps({
  modelValue: { type: Array, default: () => [] },
  sourceElement: { type: String, default: '' },  // catalog element of the SFX's source_kind
  // The context keys this point supplies (`null` = not modelled, so nothing is
  // forbidden). A condition reading a key that isn't here can never pass.
  availableKeys: { type: Array, default: null },
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

function selectedMeta(type) {
  return conditionTypes.value.find(c => c.value === type) || null
}

// A condition that reads the SFX's source can only pass when the source is the
// kind it reads ("source rating" needs a trait instance). Offering it anyway is
// how a gate that can never fire gets authored, so those options are disabled
// and say why, and an already-authored one warns in place.
function missingSource(meta) {
  const need = (meta && meta.requiresSourceElements) || []
  if (!need.length || need.includes(props.sourceElement)) return ''
  return need.join(' / ')
}

function typeUsable(t) {
  return !optionReason(t)
}

function readsUnavailable(t) {
  if (props.availableKeys == null) return false
  const need = t.requiresContextAnyOf || []
  if (!need.length) return false
  return !need.some(k => props.availableKeys.includes(k))
}

function optionReason(t) {
  const need = missingSource(t)
  if (need) return ` — needs a ${need} source`
  if (readsUnavailable(t)) return ' — nothing to read here'
  return ''
}

// What is wrong with the condition that is actually selected (legacy content can
// hold a gate the vocabulary would no longer offer). The exact per-condition
// answer — which key is missing — comes from the live `validateSfx` warnings.
function selectedProblem(type) {
  const meta = selectedMeta(type)
  if (!meta) return ''
  const need = missingSource(meta)
  if (need) return `never passes: needs a ${need} source`
  if (readsUnavailable(meta)) {
    return 'never passes: it reads the moment it fires, and there is nothing to read here'
  }
  return ''
}

function usesSpec(type) {
  return conditionTypes.value.some(c => c.value === type && c.usesSpec)
}

function needsSubject(type) {
  return !['ALWAYS', 'NARRATIVE', 'PHASE'].includes(type)
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

function targetOptions(type) {
  const meta = conditionTypes.value.find(c => c.value === type)
  return meta?.targetOptions || []
}

function add() {
  const next = [...props.modelValue, { type: 'ALWAYS', subject: '', target: '', value: '', operator: '>=', narrative: '', spec: { steps: [] } }]
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
  background: var(--overlay-6); color: var(--text);
  border: 1px solid var(--overlay-10); border-radius: 4px;
  font-family: inherit; flex: 1; min-width: 0;
}
.ce-target { flex: 2 !important; }
.ce-warn { flex: 1 1 100%; font-size: 9px; color: var(--warn, #d8a13a); }
.ce-subject { flex: 1.5 !important; }
.ce-value { flex: 1 !important; }
.ce-operator { flex: none !important; width: 58px; }
.ce-picker { min-width: 0; }
/* "＋ Add condition" keeps its deliberate dashed accent (full width via the
   column flex parent); fill/radius/padding/hover come from ui/Button. */
.ce-root > .ce-add { border-style: dashed; border-color: var(--overlay-15); }
.ce-row-spec { flex-wrap: wrap; align-items: flex-start; }
.ce-row-spec > select { flex: none; width: 140px; }
.ce-spec { flex: 1 1 100%; min-width: 0; }
</style>
