<template>
  <div class="tsb-root">
    <div class="tsb-title">{{ title }}</div>

    <div v-if="!loaded" class="tsb-loading">Loading target catalog…</div>

    <template v-else>
      <div v-if="!steps.length" class="tsb-empty">
        No steps yet — build a path from a context collection to the target type.
      </div>

      <div v-for="(step, i) in steps" :key="i" class="tsb-step" :class="{ 'tsb-valid': stepIsValid(i), 'tsb-error': stepHasError(i) }">
        <div class="tsb-step-head">
          <span class="tsb-step-index">{{ i + 1 }}</span>
          <select v-model="step.kind" class="tsb-kind">
            <option v-for="k in STEP_KINDS" :key="k.kind" :value="k.kind">{{ k.label }}</option>
          </select>
          <span class="tsb-type">{{ typeLabel(i) }}</span>
          <span v-if="stepIsValid(i)" class="tsb-match">✓ {{ destinationLabel }}</span>
          <div class="tsb-step-actions">
            <button type="button" class="tsb-btn" :disabled="i === 0" title="Move up" @click="move(i, -1)">↑</button>
            <button type="button" class="tsb-btn" :disabled="i === steps.length - 1" title="Move down" @click="move(i, 1)">↓</button>
            <button type="button" class="tsb-btn tsb-remove" title="Remove" @click="remove(i)">✕</button>
          </div>
        </div>

        <div v-if="stepError(i)" class="tsb-err">{{ stepError(i) }}</div>

        <!-- select: seed a context collection (first step only) -->
        <div v-if="step.kind === 'select'" class="tsb-config">
          <select v-model="step.collection">
            <option value="">— pick a collection —</option>
            <option v-for="c in collections()" :key="c.name" :value="c.name">
              {{ c.label }} <em>({{ c.element }})</em>
            </option>
          </select>
        </div>

        <!-- filter: narrow by a comparable field -->
        <div v-else-if="step.kind === 'filter'" class="tsb-config tsb-filter">
          <select v-model="step.field" :disabled="!priorType(i)">
            <option value="">— field —</option>
            <option v-for="f in fieldsFor(priorElement(i))" :key="f.name" :value="f.name">
              {{ f.name }} <em>({{ f.type }})</em>
            </option>
          </select>
          <select v-model="step.operator" class="tsb-op">
            <option v-for="op in OPERATORS" :key="op" :value="op">{{ op }}</option>
          </select>
          <input :value="step.value" placeholder="value" @input="onFilterValue(i, $event)" />
        </div>

        <!-- navigate: hop an edge -->
        <div v-else-if="step.kind === 'navigate'" class="tsb-config tsb-nav">
          <select v-model="step.edge" :disabled="!priorType(i)">
            <option value="">— edge —</option>
            <option v-for="e in edgesFrom(priorElement(i))" :key="e.name" :value="e.name">
              {{ e.label || e.name }} → {{ e.targets.join(' | ') }}<em v-if="e.cardinality === 'many'"> ·many</em>
            </option>
          </select>
          <label class="tsb-check">
            <input type="checkbox" v-model="step.dedup" />
            dedup
          </label>
        </div>

        <!-- aggregate: collapse to a scalar -->
        <div v-else-if="step.kind === 'aggregate'" class="tsb-config tsb-agg">
          <select v-model="step.fn">
            <option value="">— fn —</option>
            <option v-for="a in aggregations()" :key="a.name" :value="a.name">
              {{ a.label }} <em>({{ a.output }})</em>
            </option>
          </select>
          <select v-if="aggNeedsField(step.fn)" v-model="step.field">
            <option value="">— field —</option>
            <option v-for="f in fieldsFor(priorElement(i))" :key="f.name" :value="f.name">
              {{ f.name }} <em>({{ f.type }})</em>
            </option>
          </select>
        </div>
      </div>

      <div class="tsb-add">
        <span class="tsb-add-label">Add step:</span>
        <button
          v-for="k in STEP_KINDS"
          :key="k.kind"
          type="button"
          class="tsb-add-btn"
          :disabled="!canAdd(k.kind)"
          @click="add(k.kind)"
        >{{ k.label }}</button>
      </div>

      <div class="tsb-summary">
        <span class="tsb-summary-type">final: {{ finalLabel() }}</span>
        <span v-if="destination" class="tsb-summary-dest" :class="{ 'tsb-ok': trace.valid }">
          target: {{ destinationLabel }}
        </span>
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useTargetCatalog } from '@/composables/useTargetCatalog.js'

const props = defineProps({
  modelValue: { type: Object, default: () => ({ steps: [] }) },
  destination: { type: Object, default: null }, // { element, cardinality }
  title: { type: String, default: 'Targeting path' },
})
const emit = defineEmits(['update:modelValue'])

const { loaded, load, traceSpec, elementLabel, edgesFrom, fieldsFor, aggregations, collections } = useTargetCatalog()

const STEP_KINDS = [
  { kind: 'select', label: 'Select' },
  { kind: 'filter', label: 'Filter' },
  { kind: 'navigate', label: 'Navigate' },
  { kind: 'aggregate', label: 'Aggregate' },
]
const OPERATORS = ['==', '!=', '>', '>=', '<', '<=', 'in', 'contains']

const steps = computed({
  get: () => (props.modelValue && Array.isArray(props.modelValue.steps) ? props.modelValue.steps : []),
  set: (v) => emit('update:modelValue', { steps: v }),
})

const trace = ref({ types: [], errors: [], valid: false })
let traceTimer = null

function errorAt(i) {
  return trace.value.errors.find((e) => e.stepIndex === i) || null
}

function typeAt(i) {
  return (trace.value.types && trace.value.types[i]) || null
}

function priorType(i) {
  return i > 0 ? typeAt(i - 1) : null
}

function priorElement(i) {
  const t = priorType(i)
  return (t && t.element) || ''
}

function typeLabel(i) {
  const t = typeAt(i)
  if (!t || !t.element) return '∅'
  return `${t.element}/${t.cardinality}`
}

function finalLabel() {
  const t = trace.value.types && trace.value.types[trace.value.types.length - 1]
  return t && t.element ? `${t.element}/${t.cardinality}` : '∅'
}

function stepError(i) {
  const e = errorAt(i)
  return e ? e.message : ''
}

function stepHasError(i) {
  return !!errorAt(i)
}

function stepIsValid(i) {
  if (!props.destination || !props.destination.element) return false
  const t = typeAt(i)
  if (!t || !t.element || t.element !== props.destination.element) return false
  if (props.destination.cardinality && t.cardinality !== props.destination.cardinality) return false
  return !errorAt(i)
}

function aggNeedsField(fn) {
  return (aggregations().find((a) => a.name === fn) || {}).needsField
}

function fieldTypeFor(i) {
  const field = steps.value[i]?.field
  const f = fieldsFor(priorElement(i)).find((x) => x.name === field)
  return f ? f.type : null
}

// Type the value at authoring time (decision 4): an int/number field stores a
// number, die/string fields keep their string. Downstream logic then always has
// typed values and can do typed ops without late coercion.
function coerceValue(type, raw) {
  if (type === 'int') {
    const n = Number(raw)
    return raw !== '' && Number.isFinite(n) ? Math.trunc(n) : raw
  }
  if (type === 'number') {
    const n = Number(raw)
    return raw !== '' && Number.isFinite(n) ? n : raw
  }
  return raw
}

function onFilterValue(i, e) {
  steps.value[i].value = coerceValue(fieldTypeFor(i), e.target.value)
}

function canAdd(kind) {
  if (kind === 'select') return steps.value.length === 0
  // Subsequent steps need a resolvable type before them.
  return steps.value.length > 0 && !!priorType(steps.value.length)
}

function add(kind) {
  const blank = { kind, collection: '', field: '', operator: '==', value: '', edge: '', dedup: false, fn: '' }
  steps.value = [...steps.value, blank]
}

function remove(i) {
  const next = [...steps.value]
  next.splice(i, 1)
  steps.value = next
}

function move(i, delta) {
  const j = i + delta
  if (j < 0 || j >= steps.value.length) return
  const next = [...steps.value]
  const [row] = next.splice(i, 1)
  next.splice(j, 0, row)
  steps.value = next
}

const destinationLabel = computed(() =>
  props.destination
    ? (props.destination.cardinality ? `${props.destination.element}/${props.destination.cardinality}` : props.destination.element)
    : ''
)

function scheduleTrace() {
  if (traceTimer) clearTimeout(traceTimer)
  traceTimer = setTimeout(runTrace, 150)
}

async function runTrace() {
  const res = await traceSpec(steps.value, props.destination)
  if (res) trace.value = res
}

onMounted(load)
watch(() => props.destination, () => scheduleTrace(), { deep: true })
watch(steps, scheduleTrace, { deep: true })
</script>

<style scoped>
.tsb-root { display: flex; flex-direction: column; gap: 6px; font-size: 11px; }
.tsb-title { font-size: 10px; font-weight: 600; color: var(--accent); text-transform: uppercase; letter-spacing: 0.5px; }
.tsb-loading, .tsb-empty { font-size: 10px; color: var(--text-dim); font-style: italic; }
.tsb-step {
  display: flex; flex-direction: column; gap: 3px;
  padding: 6px; background: rgba(255,255,255,0.03);
  border: 1px solid rgba(255,255,255,0.08); border-radius: 6px;
}
.tsb-step.tsb-valid { border-color: #40b860; background: rgba(64,184,96,0.06); }
.tsb-step.tsb-error { border-color: #d04a4a; }
.tsb-step-head { display: flex; align-items: center; gap: 5px; }
.tsb-step-index { font-size: 9px; color: var(--text-dim); font-family: monospace; min-width: 12px; }
.tsb-kind { flex: none; width: 88px; }
.tsb-type { font-family: monospace; font-size: 9px; color: var(--text-dim); }
.tsb-match { font-size: 9px; color: #40b860; }
.tsb-step-actions { margin-left: auto; display: flex; gap: 2px; }
.tsb-btn {
  width: 20px; height: 20px; line-height: 1; cursor: pointer; font-size: 10px;
  background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.12);
  border-radius: 3px; color: var(--text-dim);
}
.tsb-btn:hover:not(:disabled) { color: var(--accent); border-color: var(--accent); }
.tsb-btn:disabled { opacity: 0.35; cursor: not-allowed; }
.tsb-remove:hover:not(:disabled) { color: #d04a4a; border-color: #d04a4a; }
.tsb-err { font-size: 9px; color: #d04a4a; }
.tsb-config { display: flex; gap: 4px; flex-wrap: wrap; }
.tsb-config select, .tsb-config input {
  font-size: 10px; padding: 3px 5px; background: rgba(255,255,255,0.06);
  color: var(--text); border: 1px solid rgba(255,255,255,0.1); border-radius: 3px;
  font-family: inherit; min-width: 0;
}
.tsb-config em { font-style: normal; font-size: 8px; color: var(--text-dim); }
.tsb-filter select, .tsb-filter input { flex: 1; min-width: 60px; }
.tsb-op { flex: none; width: 52px; }
.tsb-check { display: flex; align-items: center; gap: 4px; font-size: 10px; color: var(--text); }
.tsb-check input { width: auto; }
.tsb-add { display: flex; align-items: center; gap: 4px; flex-wrap: wrap; }
.tsb-add-label { font-size: 9px; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.5px; }
.tsb-add-btn {
  font-size: 9px; padding: 2px 8px; border-radius: 3px; cursor: pointer;
  background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.12); color: var(--text);
}
.tsb-add-btn:hover:not(:disabled) { color: var(--accent); border-color: var(--accent); }
.tsb-add-btn:disabled { opacity: 0.35; cursor: not-allowed; }
.tsb-summary { display: flex; gap: 10px; align-items: center; }
.tsb-summary-type, .tsb-summary-dest { font-size: 9px; color: var(--text-dim); font-family: monospace; }
.tsb-summary-dest.tsb-ok { color: #40b860; }
</style>
