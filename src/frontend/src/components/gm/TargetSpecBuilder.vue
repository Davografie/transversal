<template>
  <div class="tsb-root">
    <div class="tsb-title">{{ title }}</div>

    <div v-if="!loaded" class="tsb-loading">Loading target catalog…</div>

    <template v-else>
      <div v-if="!steps.length" class="tsb-empty">
        <span>No steps yet — build a path from a context collection to the target type.</span>
        <button type="button" class="tsb-plus" title="Add first step" @click="toggleInsert(-1)">＋</button>
        <div v-if="insertingAt === -1" class="tsb-insert-picker">
          <button
            v-for="k in STEP_KINDS"
            :key="k.kind"
            type="button"
            class="tsb-add-btn"
            :disabled="!canInsertAfter(-1, k.kind)"
            @click="insert(-1, k.kind)"
          >{{ k.label }}</button>
        </div>
      </div>

      <GmList v-if="steps.length" :items="steps" item-key="" reorderable drag-handle @reorder="onReorder">
        <template #item="{ item: step, index: i }">
        <div class="tsb-step" :class="{ 'tsb-valid': stepIsValid(i), 'tsb-error': stepHasError(i) }">
        <div class="tsb-step-row">
        <div class="tsb-step-main">
        <div class="tsb-step-head">
          <span class="tsb-step-index">{{ i + 1 }}</span>
          <select v-model="step.kind" class="tsb-kind">
            <option v-for="k in STEP_KINDS" :key="k.kind" :value="k.kind">{{ k.label }}</option>
          </select>
          <span class="tsb-type">{{ typeLabel(i) }}</span>
          <span v-if="stepIsValid(i)" class="tsb-match">✓ {{ destinationLabel }}</span>
        </div>

        <div v-if="stepError(i)" class="tsb-err">{{ stepError(i) }}</div>

        <!-- select: seed a context collection (first step only) -->
        <div v-if="step.kind === 'select'" class="tsb-config">
          <select v-model="step.collection">
            <option value="">— pick a collection —</option>
            <option v-if="sourceElement" value="source">SFX source <em>({{ sourceElement }})</em></option>
            <option value="variable">Bound variable</option>
            <option v-for="c in collections()" :key="c.name" :value="c.name">
              {{ c.label }} <em>({{ c.element }})</em>
            </option>
          </select>
          <select v-if="step.collection === 'variable'" v-model="step.variable">
            <option value="">— variable —</option>
            <option v-for="(entry, name) in variablesMap" :key="name" :value="name">
              {{ name }} <em>({{ elementLabel(entry.element) }}<span v-if="entry.cardinality === 'many'"> ·many</span>)</em>
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
            <option v-for="op in operatorsFor(i)" :key="op" :value="op">{{ op }}</option>
          </select>
          <select v-if="fieldOptionsFor(i)" :value="step.value" @change="onFilterValue(i, $event)">
            <option value="">—</option>
            <option v-for="o in fieldOptionsFor(i)" :key="o" :value="o">{{ o }}</option>
          </select>
          <TargetPicker
            v-else-if="fieldReferences(i)"
            :kind="fieldReferences(i)"
            :model-value="step.value"
            :clearable="false"
            placeholder="Pick…"
            @update:model-value="(v) => onFilterPickerValue(i, v)"
          />
          <input v-else :value="step.value" placeholder="value" @input="onFilterValue(i, $event)" />
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

        <!-- random: sample a subset of the current collection -->
        <div v-else-if="step.kind === 'random'" class="tsb-config tsb-random">
          <label class="tsb-check">
            <span>pick</span>
            <input type="number" min="1" :value="step.count ?? 1" @input="onCount(i, $event)" />
            <em>1 = single · N = subset</em>
          </label>
        </div>

        <!-- choose: interactive collapse of the current collection -->
        <div v-else-if="step.kind === 'choose'" class="tsb-config tsb-choose">
          <label class="tsb-check">
            <span>pick</span>
            <input type="number" min="1" :value="step.count ?? 1" @input="onCount(i, $event)" />
            <em>1 = single pick · N = multi-select</em>
          </label>
        </div>

        <!-- evaluate: terminal boolean test (exists / comparison) -->
        <div v-else-if="step.kind === 'evaluate'" class="tsb-config tsb-evaluate">
          <select v-model="step.operator" class="tsb-op">
            <option v-for="op in EVALUATE_OPERATORS" :key="op" :value="op">{{ op }}</option>
          </select>
          <em v-if="step.operator === 'exists'" class="tsb-eval-hint">non-empty</em>
          <input v-else :value="step.value" placeholder="value (count / d8 / …)" @input="onEvaluateValue(i, $event)" />
        </div>

        <div v-if="step.output != null" class="tsb-output-row">
          <span class="tsb-outputs-type">{{ typeLabel(i) }}</span>
          <input v-model="step.output" type="text" placeholder="variable name" />
        </div>
        </div>
        <div class="tsb-step-rail">
          <button type="button" class="tsb-btn tsb-remove" title="Remove" @click="remove(i)">✕</button>
          <button
            type="button"
            class="tsb-lightbulb"
            :class="{ 'tsb-lightbulb-on': step.output != null }"
            :title="step.output != null ? 'Exposed as variable' : 'Expose as variable'"
            @click="toggleOutput(i)"
          >💡</button>
          <button type="button" class="tsb-plus" title="Add step after" @click="toggleInsert(i)">＋</button>
        </div>
        </div>
        <div v-if="insertingAt === i" class="tsb-insert-picker">
          <span class="tsb-add-label">Add after:</span>
          <button
            v-for="k in STEP_KINDS"
            :key="k.kind"
            type="button"
            class="tsb-add-btn"
            :disabled="!canInsertAfter(i, k.kind)"
            @click="insert(i, k.kind)"
          >{{ k.label }}</button>
        </div>
        </div>
        </template>
      </GmList>

      <div class="tsb-summary">
        <span class="tsb-summary-type">final: {{ finalLabel() }}</span>
        <span v-if="destination || booleanTerminal" class="tsb-summary-dest" :class="{ 'tsb-ok': booleanTerminal ? terminalOk : trace.valid }">
          {{ booleanTerminal ? 'passes when:' : 'target:' }} {{ destinationLabel }}
        </span>
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useTargetCatalog } from '@/composables/useTargetCatalog.js'
import TargetPicker from './TargetPicker.vue'
import GmList from './GmList.vue'

const props = defineProps({
  modelValue: { type: Object, default: () => ({ steps: [] }) },
  destination: { type: Object, default: null }, // { element, cardinality }
  sourceElement: { type: String, default: '' },  // catalog element of the SFX's source_kind
  variables: { type: Object, default: null },     // { name: {element, cardinality} } bound output variables
  title: { type: String, default: 'Targeting path' },
  booleanTerminal: { type: Boolean, default: false }, // condition mode: the path's result is "non-empty → boolean"
})
const emit = defineEmits(['update:modelValue'])

function normalizeVar(entry) {
  if (!entry) return { element: '', cardinality: 'one' }
  if (typeof entry === 'string') return { element: entry, cardinality: 'one' }
  return { element: entry.element || '', cardinality: entry.cardinality || 'one' }
}

const variablesMap = computed(() => {
  const map = {}
  for (const [name, entry] of Object.entries(props.variables || {})) map[name] = normalizeVar(entry)
  // Intra-spec: outputs declared by earlier steps, typed by the trace result.
  for (let i = 0; i < steps.value.length; i++) {
    const step = steps.value[i]
    const type = trace.value.types?.[i]
    if (step.output && type?.element) map[step.output] = { element: type.element, cardinality: type.cardinality || 'one' }
  }
  return map
})

const { loaded, load, traceSpec, elementLabel, edgesFrom, fieldsFor, aggregations, collections } = useTargetCatalog()

const STEP_KINDS = [
  { kind: 'select', label: 'Select' },
  { kind: 'filter', label: 'Filter' },
  { kind: 'navigate', label: 'Navigate' },
  { kind: 'aggregate', label: 'Aggregate' },
  { kind: 'random', label: 'Random' },
  { kind: 'choose', label: 'Choose' },
  { kind: 'evaluate', label: 'Evaluate' },
]
const OPERATORS = ['==', '!=', '>', '>=', '<', '<=', 'in', 'contains']
const EVALUATE_OPERATORS = ['exists', '==', '!=', '>', '>=', '<', '<=']

const steps = computed({
  get: () => (props.modelValue && Array.isArray(props.modelValue.steps) ? props.modelValue.steps : []),
  set: (v) => emit('update:modelValue', { steps: v }),
})

const trace = ref({ types: [], errors: [], valid: false })
const insertingAt = ref(null)  // index of the step whose "+" was clicked (-1 = before the first)
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
  const t = typeAt(i)
  if (props.booleanTerminal) {
    // The terminal `evaluate` step is the condition's boolean result.
    return steps.value[i]?.kind === 'evaluate' && !!t && t.element === 'boolean' && !errorAt(i)
  }
  if (!props.destination || !props.destination.element) return false
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

// Enum-like string fields declare their accepted values; the filter value then
// renders as a dropdown instead of an opaque free-text input.
function fieldOptionsFor(i) {
  const field = steps.value[i]?.field
  const f = fieldsFor(priorElement(i)).find((x) => x.name === field)
  return f && f.options && f.options.length ? f.options : null
}

// Id-reference fields (e.g. traitset_id → traitset) render a picker so the
// author selects the instance instead of copy/pasting an id.
function fieldReferences(i) {
  const field = steps.value[i]?.field
  const f = fieldsFor(priorElement(i)).find((x) => x.name === field)
  return f && f.references ? f.references : null
}

function onFilterPickerValue(i, val) {
  steps.value[i].value = val
}

// Operators valid for the current field (from the catalog; falls back to the
// full set while the field/trace is still resolving).
function operatorsFor(i) {
  const field = steps.value[i]?.field
  const f = fieldsFor(priorElement(i)).find((x) => x.name === field)
  return f && f.operators && f.operators.length ? f.operators : OPERATORS
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

function onEvaluateValue(i, e) {
  const prior = priorType(i)
  const type = prior && (prior.cardinality === 'many' || ['int', 'number'].includes(prior.element)) ? 'number' : prior?.element || 'string'
  steps.value[i].value = coerceValue(type, e.target.value)
}

function onCount(i, e) {
  const n = Math.trunc(Number(e.target.value))
  steps.value[i].count = Number.isFinite(n) && n >= 1 ? n : 1
}

function toggleOutput(i) {
  const cur = steps.value[i]?.output
  steps.value[i].output = (cur == null) ? '' : null
}

function canInsertAfter(i, kind) {
  if (i === -1) return kind === 'select'  // first step is always a seed
  if (kind === 'select') return false
  const prior = typeAt(i)
  if (!prior || !prior.element) return false
  // evaluate is terminal: a boolean result can't be followed.
  if (prior.element === 'boolean') return false
  // random/choose collapse a *many* collection; only offer them over a set.
  if (kind === 'random' || kind === 'choose') return prior.cardinality === 'many'
  return true
}

function toggleInsert(i) {
  insertingAt.value = insertingAt.value === i ? null : i
}

function insert(i, kind) {
  const blank = { kind, collection: '', variable: '', output: null, field: '', operator: '==', value: '', edge: '', dedup: false, fn: '', count: 1 }
  const next = [...steps.value]
  next.splice(i + 1, 0, blank)
  steps.value = next
  insertingAt.value = null
}

function remove(i) {
  const next = [...steps.value]
  next.splice(i, 1)
  steps.value = next
}

function onReorder(from, to) {
  if (from === to || from < 0 || to < 0 || from >= steps.value.length || to >= steps.value.length) return
  const next = [...steps.value]
  const [moved] = next.splice(from, 1)
  next.splice(to, 0, moved)
  steps.value = next
}

const destinationLabel = computed(() => {
  if (props.booleanTerminal) {
    const last = steps.value[steps.value.length - 1]
    return last && last.kind === 'evaluate' ? 'boolean' : 'boolean (non-empty)'
  }
  return props.destination
    ? (props.destination.cardinality ? `${props.destination.element}/${props.destination.cardinality}` : props.destination.element)
    : ''
})

// A condition path is "terminal" (evaluable to true/false) once it resolves to
// some type with no step errors — the boolean is "did anything resolve?".
const terminalOk = computed(() => {
  const types = trace.value.types || []
  const final = types[types.length - 1]
  return !(trace.value.errors && trace.value.errors.length) && !!(final && final.element)
})

function scheduleTrace() {
  if (traceTimer) clearTimeout(traceTimer)
  traceTimer = setTimeout(runTrace, 150)
}

async function runTrace() {
  const res = await traceSpec(steps.value, props.destination, props.sourceElement || null, props.variables || null)
  if (res) trace.value = res
}

onMounted(load)
watch(() => [props.destination, props.sourceElement, props.variables], () => scheduleTrace(), { deep: true })
watch(steps, scheduleTrace, { deep: true, immediate: true })
</script>

<style scoped>
.tsb-root { display: flex; flex-direction: column; gap: 6px; font-size: 11px; }
.tsb-title { font-size: 10px; font-weight: 600; color: var(--accent); text-transform: uppercase; letter-spacing: 0.5px; }
.tsb-loading, .tsb-empty { font-size: 10px; color: var(--text-dim); font-style: italic; }
.tsb-step { display: flex; flex-direction: column; gap: 3px; flex: 1; min-width: 0; border-radius: 4px; }
.tsb-step.tsb-valid { box-shadow: 0 0 0 1px #40b860 inset; }
.tsb-step.tsb-error { box-shadow: 0 0 0 1px #d04a4a inset; }
.tsb-step-head { display: flex; align-items: center; gap: 5px; }
.tsb-outputs-type { font-family: monospace; font-size: 9px; color: var(--text-dim); }
.tsb-output-row { display: flex; align-items: center; gap: 4px; }
.tsb-output-row input { flex: 1; min-width: 0; }
.tsb-step-index { font-size: 9px; color: var(--text-dim); font-family: monospace; min-width: 12px; }
.tsb-kind { flex: none; width: 88px; }
.tsb-type { font-family: monospace; font-size: 9px; color: var(--text-dim); }
.tsb-match { font-size: 9px; color: #40b860; }
.tsb-step-row { display: flex; gap: 6px; }
.tsb-step-main { display: flex; flex-direction: column; gap: 3px; flex: 1; min-width: 0; }
.tsb-step-rail { display: flex; flex-direction: column; gap: 4px; flex-shrink: 0; }
.tsb-btn {
  display: inline-flex; align-items: center; justify-content: center; padding: 0;
  width: 22px; height: 22px; line-height: 1; cursor: pointer; font-size: 10px;
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
.tsb-plus {
  display: inline-flex; align-items: center; justify-content: center; padding: 0;
  width: 22px; height: 22px; line-height: 1; font-size: 13px; cursor: pointer;
  background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.12);
  border-radius: 3px; color: var(--text-dim);
}
.tsb-plus:hover { color: var(--accent); border-color: var(--accent); }
.tsb-insert-picker { display: flex; align-items: center; gap: 4px; flex-wrap: wrap; justify-content: flex-start; margin-top: 4px; }
.tsb-lightbulb {
  display: inline-flex; align-items: center; justify-content: center; padding: 0;
  width: 22px; height: 22px; font-size: 12px; cursor: pointer; line-height: 1;
  background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.12);
  border-radius: 3px; opacity: 0.55;
}
.tsb-lightbulb:hover { opacity: 0.85; }
.tsb-lightbulb-on { opacity: 1; background: rgba(255,214,102,0.15); border-color: rgba(255,214,102,0.4); }
.tsb-empty { display: flex; flex-direction: column; gap: 6px; align-items: flex-start; }
.tsb-summary { display: flex; gap: 10px; align-items: center; }
.tsb-root :deep(.gml-item) { cursor: default; }
.tsb-summary-type, .tsb-summary-dest { font-size: 9px; color: var(--text-dim); font-family: monospace; }
.tsb-summary-dest.tsb-ok { color: #40b860; }
</style>
