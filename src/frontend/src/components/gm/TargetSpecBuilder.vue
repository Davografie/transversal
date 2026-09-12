<template>
  <div class="tsb-root">
    <div class="tsb-title">{{ title }}</div>

    <div v-if="!loaded" class="tsb-loading">Loading target catalog…</div>

    <template v-else>
      <div v-if="!steps.length" class="tsb-empty">
        <span>No steps yet — build a path from a context collection to the target type.</span>
        <Button class="tsb-plus" title="Add first step" variant="secondary" size="sm" @click="toggleInsert(-1)">＋</Button>
        <div v-if="insertingAt === -1" class="tsb-insert-picker">
          <Button
            v-for="k in STEP_KINDS"
            :key="k.kind"
            class="tsb-add-btn"
            variant="secondary"
            size="sm"
            :disabled="!canInsertAfter(-1, k.kind)"
            @click="insert(-1, k.kind)"
          >{{ k.label }}</Button>
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
              {{ f.label || f.name }}
            </option>
          </select>
          <select v-model="step.operator" class="tsb-op">
            <option v-for="op in operatorsFor(i)" :key="op" :value="op">{{ op }}</option>
          </select>
          <!-- An enum filter takes one value or several; several is stored as a
               list with `in` (the resolver reads it as *any of*). -->
          <select v-if="fieldOptionsFor(i)" multiple :value="enumValues(i)" @change="onEnumChange(i, $event)">
            <option v-for="o in fieldOptionsFor(i)" :key="o" :value="o">{{ o }}</option>
          </select>
          <span v-else-if="isTokenValue(step.value)" class="tsb-value-token">
            <select v-if="variableChoicesFor(i).length" :value="step.value" @change="onFilterValue(i, $event)">
              <option v-for="[name, entry] in variableChoicesFor(i)" :key="name" :value="`{${name}}`">
                {{ name }} <em>({{ elementLabel(entry.element) }})</em>
              </option>
            </select>
            <input v-else :value="step.value" placeholder="{name}" @input="onFilterValue(i, $event)" />
            <button type="button" class="tsb-token-btn active" title="Pick a value instead" @click="useToken(i, false)">{ }</button>
          </span>
          <span v-else-if="fieldReferences(i)" class="tsb-value-token">
            <!-- Autosuggest by name; a universe stores its *handle* (`earth`),
                 which is what a projection's `universe` holds. -->
            <TargetPicker
              :kind="fieldReferences(i)"
              :model-value="step.value"
              :clearable="false"
              placeholder="Pick…"
              @select="(opt) => onFilterPicked(i, opt)"
              @update:model-value="(v) => onFilterPickerValue(i, v)"
            />
            <button type="button" class="tsb-token-btn" title="Compare against a bound value" @click="useToken(i, true)">{ }</button>
          </span>
          <span v-else-if="isTagField(i)" class="tsb-tags">
            <!-- The tags editor, not a text box: the same chips the trait editor
                 uses, so a filter reads like the thing it filters on. One tag
                 stores a string (`contains fire`); several store a list with
                 `contains`, which the resolver reads as *any of* — the
                 one-or-several convention an enum filter already follows. -->
            <TagInput
              :model-value="tagValuesOf(i)"
              :suggestions="tagSuggestions"
              placeholder="Add tag…"
              aria-label="Filter by tag"
              @update:model-value="(v) => onTagsChange(i, v)"
            />
          </span>
          <input v-else-if="fieldSuggest(i)" :value="step.value" placeholder="value"
                 :list="suggestListId" @input="onFilterValue(i, $event)" />
          <input v-else :value="step.value" placeholder="value" @input="onFilterValue(i, $event)" />
          <!-- Free-form fields whose values are *data*: known ones are proposed,
               typing a new one stays allowed. `suggest` in the catalog names the
               source (trait tags, SFX names / triggers / source kinds). -->
          <datalist v-if="fieldSuggest(i)" :id="suggestListId">
            <option v-for="o in suggestOptions(i)" :key="o.id" :value="o.id" />
          </datalist>
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
              {{ f.label || f.name }}
            </option>
          </select>
        </div>

        <!-- top: keep the extreme element by a comparable field -->
        <div v-else-if="step.kind === 'top'" class="tsb-config tsb-top">
          <select v-model="step.field">
            <option value="">— field —</option>
            <option v-for="f in orderableFieldsFor(priorElement(i))" :key="f.name" :value="f.name">
              {{ f.label || f.name }}
            </option>
          </select>
          <select v-model="step.direction">
            <option value="desc">highest / most recent</option>
            <option value="asc">lowest / least recent</option>
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
          <select v-if="evalFieldOptions(i).length" v-model="step.field" class="tsb-field">
            <option value="count">count</option>
            <option v-for="f in evalFieldOptions(i)" :key="f.name" :value="f.name">
              {{ f.label || f.name }}
            </option>
          </select>
          <span v-else class="tsb-eval-lhs">{{ evalLhsLabel(i) }}</span>
          <select v-model="step.operator" class="tsb-op">
            <option v-for="op in EVALUATE_OPERATORS" :key="op" :value="op">{{ op }}</option>
          </select>
          <template v-if="step.operator !== 'exists'">
            <DiePicker v-if="evalValueIsDie(i)" :model-value="step.value" @update:model-value="(v) => onEvaluateValue(i, v)" />
            <select v-else-if="fieldOptionsFor(i)" :value="step.value" @change="onEvaluateValue(i, $event)">
              <option value="">—</option>
              <option v-for="o in fieldOptionsFor(i)" :key="o" :value="o">{{ o }}</option>
            </select>
            <TargetPicker v-else-if="fieldReferences(i)" :kind="fieldReferences(i)" :model-value="step.value" :clearable="false" placeholder="Pick…" @update:model-value="(v) => onEvaluateValue(i, v)" />
            <input v-else-if="evalValueIsNumber(i)" type="number" min="0" step="1" :value="step.value" placeholder="n" @input="onEvaluateValue(i, $event)" />
            <input v-else :value="step.value" placeholder="value" @input="onEvaluateValue(i, $event)" />
          </template>
          <em v-else class="tsb-eval-hint">non-empty</em>
        </div>

        <div v-if="step.output != null" class="tsb-output-row">
          <span class="tsb-outputs-type">{{ typeLabel(i) }}</span>
          <input v-model="step.output" type="text" placeholder="variable name" />
        </div>
        </div>
        <div class="tsb-step-rail">
          <Button class="tsb-btn tsb-remove" title="Remove" variant="danger-ghost" size="sm" @click="remove(i)">✕</Button>
          <button
            type="button"
            class="tsb-lightbulb"
            :class="{ 'tsb-lightbulb-on': step.output != null }"
            :title="step.output != null ? 'Exposed as variable' : 'Expose as variable'"
            @click="toggleOutput(i)"
          >💡</button>
          <Button class="tsb-plus" title="Add step after" variant="secondary" size="sm" @click="toggleInsert(i)">＋</Button>
        </div>
        </div>
        <div v-if="insertingAt === i" class="tsb-insert-picker">
          <span class="tsb-add-label">Add after:</span>
          <Button
            v-for="k in STEP_KINDS"
            :key="k.kind"
            class="tsb-add-btn"
            variant="secondary"
            size="sm"
            :disabled="!canInsertAfter(i, k.kind)"
            @click="insert(i, k.kind)"
          >{{ k.label }}</Button>
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
import { computed, onMounted, ref, useId, watch } from 'vue'
import { useTargetCatalog } from '@/composables/useTargetCatalog.js'
import { useTraitsConfig } from '@/composables/useTraitsConfig.js'
import { useSfxMeta } from '@/composables/useSfxMeta.js'
import TargetPicker from '@/components/ui/TargetPicker.vue'
import TagInput from '@/components/ui/TagInput.vue'
import DiePicker from '../DiePicker.vue'
import GmList from '@/components/ui/GmList.vue'
import Button from '@/components/ui/Button.vue'

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

const { loaded, load, traceSpec, elementLabel, edgesFrom, fieldsFor, aggregations, collections, sourceKinds } = useTargetCatalog()

// Free-form fields whose values are data, not schema. The catalog names the
// source; these are the lists that exist right now. One table, so a new
// suggestable field is a catalog line plus a row here.
const { allSfxs, traitsets, fetchTraitsConfig } = useTraitsConfig()
const { load: loadSfxMeta, triggers } = useSfxMeta()

const suggestListId = `tsb-suggest-options-${useId()}`

const tagOptions = computed(() => {
  const seen = new Set()
  for (const ts of traitsets.value || []) {
    for (const t of ts.traits || []) {
      for (const tag of t.tags || []) if (tag) seen.add(tag)
    }
  }
  return [...seen].sort().map((tag) => ({ id: tag, name: tag }))
})

const sfxNameOptions = computed(() =>
  (allSfxs.value || []).map((s) => ({ id: s.id, name: s.name })))

const sfxTriggerOptions = computed(() =>
  (triggers.value || []).map((t) => ({ id: t.value, name: t.label })))

const sfxSourceKindOptions = computed(() =>
  (sourceKinds() || []).map((s) => ({ id: s.value, name: s.label })))

const SUGGEST_SOURCES = {
  trait_tags: tagOptions,
  sfx_names: sfxNameOptions,
  sfx_triggers: sfxTriggerOptions,
  sfx_source_kinds: sfxSourceKindOptions,
}

/** The tag editor's own suggestions (string values), from the suggest table. */
const tagSuggestions = computed(() => (tagOptions.value || []).map((o) => o.id))

/** A `tags` filter is edited with the tags component, not a value box. */
function isTagField(i) {
  return fieldSuggest(i) === 'trait_tags'
}

/** The step's value as the chip list the component edits (string | list → list). */
function tagValuesOf(i) {
  const v = steps.value[i]?.value
  if (Array.isArray(v)) return v.map(String)
  return v ? [String(v)] : []
}

function onTagsChange(i, values) {
  const step = steps.value[i]
  if (!step) return
  const had = tagValuesOf(i).length
  const list = (values || []).map((v) => String(v)).filter(Boolean)
  // One tag stays a string (what every authored filter already holds); several
  // become a list, which `contains` reads as *any of*.
  step.value = list.length === 0 ? '' : (list.length === 1 ? list[0] : list)
  // `==` against a tags list can never pass for a single tag, so naming the
  // first tag lands on the operator the catalogue offers first for this field.
  // A deliberate choice is left alone afterwards — this only fires on a fill-in.
  if (!had && list.length && step.operator !== 'contains') step.operator = 'contains'
}

function fieldSuggest(i) {
  const field = steps.value[i]?.field
  const f = fieldsFor(priorElement(i)).find((x) => x.name === field)
  return f && f.suggest ? f.suggest : null
}

/** The option list for whichever suggest source this step's field names. */
function suggestOptions(i) {
  const source = fieldSuggest(i)
  const list = source ? SUGGEST_SOURCES[source] : null
  return list ? list.value : []
}

// Every suggest source is loaded up front: cheap (each is a cached config read)
// and it keeps a path authored before the list arrives from offering nothing.
function ensureSuggestSource() {
  if (!traitsets.value.length) fetchTraitsConfig()
  if (!triggers.value.length) loadSfxMeta()
}

const STEP_KINDS = [
  { kind: 'select', label: 'Select' },
  { kind: 'filter', label: 'Filter' },
  { kind: 'navigate', label: 'Navigate' },
  { kind: 'aggregate', label: 'Aggregate' },
  { kind: 'top', label: 'Top' },
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

// A value that names a bound variable rather than holding a literal.
function isTokenValue(v) {
  return typeof v === 'string' && v.startsWith('{') && v.endsWith('}')
}

const variableNames = computed(() => Object.keys(props.variables || {}))

// Names offered as a `{name}` value, filtered by what the field expects: a
// field that points at an element (a universe) offers variables of *that*
// element. When nothing matches, the whole list is shown with each name's type
// rather than a dead end — a name may be bound later by a condition.
function variableChoicesFor(i) {
  const entries = Object.entries(props.variables || {})
  const want = fieldReferences(i)
  if (!want) return entries
  const matching = entries.filter(([, entry]) => !entry?.element || entry.element === want)
  return matching.length ? matching : entries
}

// Swap a filter value between a picked value and a bound name. Entering token
// mode pre-selects the first offered name so the step is never left blank.
function useToken(i, on) {
  const first = variableChoicesFor(i)[0]
  steps.value[i].value = on ? `{${first ? first[0] : ''}}` : ''
}

// A picked candidate stores what the *field* holds: a universe's handle, not
// its entity id (a projection's `universe` is `earth`, not `universe-earth`).
// A single value stays a string with `==` (unchanged behaviour); several become a
// list with `in`, which is the operator the resolver reads as membership.
function enumValues(i) {
  const v = steps.value[i]?.value
  return Array.isArray(v) ? v : (v ? [v] : [])
}

function onEnumChange(i, event) {
  const picked = Array.from(event.target.selectedOptions || []).map((o) => o.value)
  steps.value[i].value = picked.length > 1 ? picked : (picked[0] || '')
  if (picked.length > 1) steps.value[i].operator = 'in'
  else if (steps.value[i].operator === 'in') steps.value[i].operator = '=='
}

function onFilterPicked(i, opt) {
  // A universe-valued field stores the world's *handle* (`earth`); everything
  // else stores the candidate's id. The candidate's own `universe` field only
  // says where it lives — preferring it wrote a universe handle into trait
  // filters (pick "Beast", get the universe's name/`aelor-citar`).
  const kind = fieldReferences(i)
  steps.value[i].value = kind === 'universe'
    ? (opt?.universe || opt?.id || '')
    : (opt?.id || '')
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

function onEvaluateValue(i, raw) {
  const val = (raw && typeof raw === 'object' && 'target' in raw) ? raw.target.value : raw
  steps.value[i].value = coerceValue(evalValueType(i), val)
}

// Left-hand side of an evaluate comparison. For a *many* collection the only
// sensible LHS is its count; for a single object we offer count + its scalar
// fields (e.g. rating); for a scalar element the scalar is the LHS.
function orderableFieldsFor(element) {
  // Only fields the backend will order by: numbers, dice and timestamps
  // (`is_orderable` in the catalog). A `top` step over a plain string is
  // rejected by the type-checker, so it is not offered here either.
  if (!element) return []
  return fieldsFor(element).filter((f) => ['int', 'number', 'die', 'datetime'].includes(f.type))
}

function evalFieldOptions(i) {
  const prior = priorType(i)
  if (!prior || !prior.element) return []
  if (prior.cardinality !== 'one') return []
  if (['int', 'number', 'die'].includes(prior.element)) return []
  return fieldsFor(prior.element).filter((f) => ['int', 'number', 'die', 'string'].includes(f.type))
}

function evalLhsLabel(i) {
  const prior = priorType(i)
  if (!prior || !prior.element) return 'value'
  if (prior.cardinality === 'many') return 'count'
  if (['int', 'number', 'die'].includes(prior.element)) return prior.element
  return 'value'
}

function evalValueType(i) {
  const step = steps.value[i]
  if (step.field === 'count') return 'number'
  const f = fieldsFor(priorElement(i)).find((x) => x.name === step.field)
  return f ? f.type : 'string'
}

function evalValueIsDie(i) {
  const step = steps.value[i]
  if (step.field === 'count') return false
  const f = fieldsFor(priorElement(i)).find((x) => x.name === step.field)
  return !!f && f.type === 'die'
}

function evalValueIsNumber(i) {
  const step = steps.value[i]
  if (step.field === 'count') return true
  const f = fieldsFor(priorElement(i)).find((x) => x.name === step.field)
  return !!f && ['int', 'number'].includes(f.type)
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
  const blank = { kind, collection: '', variable: '', output: null, field: kind === 'evaluate' ? 'count' : '', operator: '==', value: '', edge: '', dedup: false, fn: '', count: 1 }
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
onMounted(ensureSuggestSource)
watch(() => [props.destination, props.sourceElement, props.variables], () => scheduleTrace(), { deep: true })
watch(steps, scheduleTrace, { deep: true, immediate: true })
</script>

<style scoped>
.tsb-root { display: flex; flex-direction: column; gap: 6px; font-size: 11px; }
.tsb-title { font-size: 10px; font-weight: 600; color: var(--accent); text-transform: uppercase; letter-spacing: 0.5px; }
.tsb-loading, .tsb-empty { font-size: 10px; color: var(--text-dim); font-style: italic; }
.tsb-step { display: flex; flex-direction: column; gap: 3px; flex: 1; min-width: 0; border-radius: 4px; }
.tsb-step.tsb-valid { box-shadow: 0 0 0 1px var(--success) inset; }
.tsb-step.tsb-error { box-shadow: 0 0 0 1px var(--danger) inset; }
.tsb-step-head { display: flex; align-items: center; gap: 5px; }
.tsb-outputs-type { font-family: monospace; font-size: 9px; color: var(--text-dim); }
.tsb-output-row { display: flex; align-items: center; gap: 4px; }
.tsb-output-row input { flex: 1; min-width: 0; }
.tsb-step-index { font-size: 9px; color: var(--text-dim); font-family: monospace; min-width: 12px; }
.tsb-kind { flex: none; width: 88px; }
.tsb-type { font-family: monospace; font-size: 9px; color: var(--text-dim); }
.tsb-match { font-size: 9px; color: var(--success); }
.tsb-step-row { display: flex; gap: 6px; }
.tsb-step-main { display: flex; flex-direction: column; gap: 3px; flex: 1; min-width: 0; }
.tsb-step-rail { display: flex; flex-direction: column; gap: 4px; flex-shrink: 0; }
/* Rail buttons keep their 22px square geometry and the first-step "＋" keeps
   its compact box; the primitive owns fill/border/radius/color/hover/disabled,
   so the kept width+padding overrides are scoped to the container. */
.tsb-empty .tsb-plus, .tsb-step-rail .tsb-plus, .tsb-step-rail .tsb-btn {
  width: 22px; height: 22px; padding: 0;
}
.tsb-err { font-size: 9px; color: var(--danger); }
.tsb-config { display: flex; gap: 4px; flex-wrap: wrap; }
/* A filter value: a picked thing, or a bound name ({universe}). */
.tsb-value-token { display: flex; align-items: center; gap: 4px; flex: 1; min-width: 0; }
.tsb-value-token > :first-child { flex: 1; min-width: 0; }
.tsb-token-btn {
  flex: none; font-size: 9px; font-family: monospace; padding: 2px 5px; cursor: pointer;
  border: 1px solid var(--overlay-12); border-radius: 4px;
  background: var(--overlay-6); color: var(--text-dim);
}
.tsb-token-btn.active { border-color: var(--accent); color: var(--text); }
.tsb-config select, .tsb-config input {
  font-size: 10px; padding: 3px 5px; background: var(--overlay-6);
  color: var(--text); border: 1px solid var(--overlay-10); border-radius: 3px;
  font-family: inherit; min-width: 0;
}
.tsb-config em { font-style: normal; font-size: 8px; color: var(--text-dim); }
/* A filter is three controls, and one narrow row makes the last of them
   unreadable — the value picker had no room to say anything. Field, operator and
   value stack instead; the value gets the full width because it carries the
   content. */
.tsb-filter { display: flex; flex-direction: column; align-items: stretch; gap: 4px; }
.tsb-filter select, .tsb-filter input { flex: none; width: 100%; min-width: 0; }
.tsb-filter .tsb-value-token { flex: none; width: 100%; }
.tsb-filter .tsb-op, .tsb-filter .tsb-field { flex: none; width: 100%; }
.tsb-op { flex: none; width: 52px; }
.tsb-field { flex: none; width: 88px; }
.tsb-eval-lhs { flex: none; font-family: monospace; font-size: 9px; color: var(--text-dim); }
.tsb-eval-hint { flex: none; }
.tsb-evaluate :deep(.die-picker .die-btn) { width: 24px; height: 28px; padding: 1px; }
.tsb-check { display: flex; align-items: center; gap: 4px; font-size: 10px; color: var(--text); }
.tsb-check input { width: auto; }
.tsb-add { display: flex; align-items: center; gap: 4px; flex-wrap: wrap; }
.tsb-add-label { font-size: 9px; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.5px; }
.tsb-insert-picker { display: flex; align-items: center; gap: 4px; flex-wrap: wrap; justify-content: flex-start; margin-top: 4px; }
.tsb-lightbulb {
  display: inline-flex; align-items: center; justify-content: center; padding: 0;
  width: 22px; height: 22px; font-size: 12px; cursor: pointer; line-height: 1;
  background: var(--overlay-6); border: 1px solid var(--overlay-12);
  border-radius: 3px; opacity: 0.55;
}
.tsb-lightbulb:hover { opacity: 0.85; }
.tsb-lightbulb-on { opacity: 1; background: var(--warn-12); border-color: var(--warn-45); }
.tsb-empty { display: flex; flex-direction: column; gap: 6px; align-items: flex-start; }
.tsb-summary { display: flex; gap: 10px; align-items: center; }
.tsb-root :deep(.gml-item) { cursor: default; }
.tsb-summary-type, .tsb-summary-dest { font-size: 9px; color: var(--text-dim); font-family: monospace; }
.tsb-summary-dest.tsb-ok { color: var(--success); }
</style>
