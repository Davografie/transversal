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
            :disabled="kindBlocked(k.kind) || !canInsertAfter(-1, k.kind)"
            :title="kindBlocked(k.kind) ? KIND_BLOCKED_REASON : ''"
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
            <option v-for="k in STEP_KINDS" :key="k.kind" :value="k.kind" :disabled="kindBlocked(k.kind)">
              {{ k.label }}{{ kindBlocked(k.kind) ? ' — needs an answer' : '' }}
            </option>
          </select>
          <span class="tsb-type">{{ typeLabel(i) }}</span>
          <span v-if="stepIsValid(i)" class="tsb-match">✓ {{ destinationLabel }}</span>
        </div>

        <div v-if="stepError(i)" class="tsb-err">{{ stepError(i) }}</div>

        <!-- select: seed a context collection (first step only) -->
        <div v-if="step.kind === 'select'" class="tsb-config">
          <select v-model="step.collection">
            <option value="">— pick a collection —</option>
            <option v-if="sourceElement && (allowSource || step.collection === 'source')" value="source">SFX source <em>({{ sourceElement }})</em></option>
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

        <!-- literal: name one specific thing, by id — a pin rather than a query.
             This is the shape that makes a value `one`: a filtered collection has
             no size the engine can know, so it can only ever be `many` ([[B281]]). -->
        <div v-else-if="step.kind === 'literal'" class="tsb-config tsb-literal">
          <select v-model="step.element">
            <option value="">— element —</option>
            <option v-for="e in (catalog?.elements || [])" :key="e.name" :value="e.name">
              {{ e.label || e.name }}
            </option>
          </select>
          <!-- Pick by name, store the identity — the **universal picker**, the same
               one every other target field composes rather than a text box
               ([[UI-UX Design#Pickers]]). It is backed by `targetCandidates(kind)`,
               so what is offered is the set the engine can actually resolve. -->
          <TargetPicker
            v-if="step.element"
            :kind="step.element"
            :model-value="step.value"
            :clearable="false"
            placeholder="Pick one…"
            :option-to-value="(opt) => literalOptionToValue(i, opt)"
            @update:model-value="(v) => onLiteralValue(i, v)"
          />
          <!-- …and an id box beside it, deliberately kept. **Nine of the eighteen**
               catalog elements have no candidate source (`die`, `capacity_die`,
               `pool`, `contest`, `traitsetting`, `traitsetsetting`, `relationship`,
               `sfx`, `scheduled_event`), so for those the picker is legitimately
               empty and without this the step could not be authored at all. It is
               also the way out when a pickable kind has no candidates in scope. -->
          <input
            class="tsb-literal-id"
            :value="step.value"
            placeholder="or type an id"
            @input="onLiteralValue(i, $event.target.value)"
          />
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
               list with `in` (the resolver reads it as *any of*). Edited like the
               tag field: chips for the picks, the input opens the vocabulary. -->
          <TagInput
            v-if="fieldOptionsFor(i)"
            class="tsb-enum"
            :model-value="oneOrSeveral(i)"
            :suggestions="fieldOptionsFor(i)"
            :allow-custom="false"
            placeholder="value"
            @update:model-value="onOneOrSeveralPicked(i, $event)"
          />
          <select v-else-if="isBooleanField(i)" class="tsb-bool" :value="boolValue(i)"
                  @change="onBooleanPicked(i, $event)">
            <option value="">—</option>
            <option value="true">true</option>
            <option value="false">false</option>
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
            <!-- Pick by name, store the identity: the dropdown lists names and
                 the step keeps the id, so the rule means exactly one thing even
                 when several registry entries share a name. Several picks become
                 a list with `in`. A universe stores its *handle* (`earth`),
                 which is what a projection's `universe` field actually holds. -->
            <TargetPicker
              :kind="fieldReferences(i)"
              :model-value="step.value"
              :clearable="false"
              placeholder="Pick…"
              multiple
              :option-to-value="optionToValueFor(i)"
              @update:model-value="(v) => onReferenceValue(i, v)"
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
          <!-- A field whose values are *data*: the known ones are chips you can
               pick, and typing a name nobody has used stays allowed — the value
               may be something not in the list yet. One stays a scalar (`==`),
               several become a list (`in`) — the same one-or-several rule an
               enum filter follows. -->
          <TagInput
            v-else-if="fieldSuggest(i)"
            class="tsb-enum"
            :model-value="oneOrSeveral(i)"
            :suggestions="suggestOptions(i)"
            placeholder="value"
            @update:model-value="onOneOrSeveralPicked(i, $event)"
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

        <!-- aggregate: the FIELD first, then the functions that field supports
             (a datetime cannot be averaged, so it is not offered one) -->
        <div v-else-if="step.kind === 'aggregate'" class="tsb-config tsb-agg">
          <select v-model="step.field" @change="onAggFieldChange(i)">
            <option value="">— the collection —</option>
            <option v-for="f in orderableFieldsFor(priorElement(i))" :key="f.name" :value="f.name">
              {{ f.label || f.name }} <em>({{ f.type }})</em>
            </option>
          </select>
          <select v-model="step.fn">
            <option value="">— fn —</option>
            <option v-for="a in aggregationsForField(i)" :key="a.name" :value="a.name">
              {{ a.label }} <em>({{ aggOutputLabel(a, i) }})</em>
            </option>
          </select>
          <label v-if="aggNeedsCount(step.fn)" class="tsb-check">
            <span>pick</span>
            <input type="number" min="1" :value="step.count ?? 1" @input="onCount(i, $event)" />
            <em>1 = single · 2 or more = subset</em>
          </label>
        </div>

        <!-- choose: interactive collapse of the current collection -->
        <div v-else-if="step.kind === 'choose'" class="tsb-config tsb-choose">
          <!-- A one/multiple **toggle**, not a number: the count only ever decided
               single-pick vs multi-select, so a number read as a cap it never
               enforced. `null` is "as many as they like". -->
          <SegmentedControl
            class="tsb-choose-mode"
            :model-value="step.count == null ? MULTI : ONE"
            :options="CHOOSE_MODES"
            aria-label="How many they pick"
            @update:model-value="onChooseMode(i, $event)"
          />
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
            :disabled="kindBlocked(k.kind) || !canInsertAfter(i, k.kind)"
            :title="kindBlocked(k.kind) ? KIND_BLOCKED_REASON : ''"
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
import { computed, onMounted, ref, watch } from 'vue'
import { useTargetCatalog } from '@/composables/useTargetCatalog.js'
import { useTraitsConfig } from '@/composables/useTraitsConfig.js'
import { useSfxMeta } from '@/composables/useSfxMeta.js'
import { useApi } from '@/composables/useApi.js'
import TargetPicker from '@/components/ui/TargetPicker.vue'
import TagInput from '@/components/ui/TagInput.vue'
import DiePicker from '../DiePicker.vue'
import GmList from '@/components/ui/GmList.vue'
import Button from '@/components/ui/Button.vue'
import SegmentedControl from '@/components/ui/SegmentedControl.vue'

const props = defineProps({
  modelValue: { type: Object, default: () => ({ steps: [] }) },
  destination: { type: Object, default: null }, // { elements: [...], cardinality }
  sourceElement: { type: String, default: '' },  // catalog element of the SFX's source_kind
  variables: { type: Object, default: null },     // { name: {element, cardinality} } bound output variables
  title: { type: String, default: 'Targeting path' },
  booleanTerminal: { type: Boolean, default: false }, // condition mode: the path's result is "non-empty → boolean"
  // Whether `select source` may be *chosen* here. It is a real seed for an effect
  // or a condition — the thing the rule is attached to — but a **reach
  // declaration** has no source at all: it is resolved for the whole world, with
  // no activation and nobody asking, so a path starting there selects nobody and
  // says nothing about it. A stored `source` step stays visible (below) so an
  // existing declaration is never silently mangled.
  allowSource: { type: Boolean, default: true },
})
const emit = defineEmits(['update:modelValue', 'resolve'])

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

const { loaded, load, traceSpec, elementLabel, edgesFrom, fieldsFor, aggregations, collections, sourceKinds, catalog } = useTargetCatalog()

// Free-form fields whose values are data, not schema. The catalog names the
// source; these are the lists that exist right now. One table, so a new
// suggestable field is a catalog line plus a row here.
const { allSfxs, traitsets, fetchTraitsConfig } = useTraitsConfig()
const { load: loadSfxMeta, triggers } = useSfxMeta()
const { graphql } = useApi()

// The universe's name / location / entity vocabularies come from the entity
// list, which is far larger than the trait config — so it is fetched the first
// time a field actually suggests from it, not on mount.
const entityRows = ref([])
let entityRowsLoading = false
async function loadEntityRows() {
  if (entityRows.value.length || entityRowsLoading) return
  entityRowsLoading = true
  try {
    const data = await graphql(`query { entities { id name type } }`)
    entityRows.value = data?.entities || []
  } catch (e) { /* a suggestion list is a convenience; typing still works */ }
  finally { entityRowsLoading = false }
}

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

const names = (list) => [...new Set(list.filter(Boolean))].sort().map((n) => ({ id: n, name: n }))

const traitNameOptions = computed(() =>
  names((traitsets.value || []).flatMap((ts) => (ts.traits || []).map((t) => t.name))))

const traitsetNameOptions = computed(() =>
  names((traitsets.value || []).map((ts) => ts.name)))

const byType = (type) => names((entityRows.value || []).filter((e) => e.type === type).map((e) => e.name))
const entityNameOptions = computed(() => names((entityRows.value || []).map((e) => e.name)))
const locationNameOptions = computed(() => byType('location'))
const universeNameOptions = computed(() => byType('universe'))

const relationshipTypeOptions = ref([])

async function loadRelationshipTypes() {
  try {
    const data = await graphql(`query { relationshipTypes }`)
    relationshipTypeOptions.value = data?.relationshipTypes || []
  } catch (e) { /* a suggestion list is a convenience; typing still works */ }
}

const SUGGEST_SOURCES = {
  relationship_types: relationshipTypeOptions,
  trait_tags: tagOptions,
  trait_names: traitNameOptions,
  traitset_names: traitsetNameOptions,
  entity_names: entityNameOptions,
  location_names: locationNameOptions,
  universe_names: universeNameOptions,
  sfx_names: sfxNameOptions,
  sfx_triggers: sfxTriggerOptions,
  sfx_source_kinds: sfxSourceKindOptions,
}

// Anything served from the entity list needs that list; ask for it on first use.
const ENTITY_BACKED_SUGGESTS = new Set(['entity_names', 'location_names', 'universe_names'])

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
  // A deliberate choice is left alone afterwards — this only fires on a fill-in,
  // and a deliberate `not contains` is a choice like any other.
  if (!had && list.length && !LIST_OPERATORS.includes(step.operator)) step.operator = 'contains'
}

function fieldSuggest(i) {
  const field = steps.value[i]?.field
  const f = fieldsFor(priorElement(i)).find((x) => x.name === field)
  return f && f.suggest ? f.suggest : null
}

/** The option list for whichever suggest source this step's field names. */
function suggestOptions(i) {
  const source = fieldSuggest(i)
  if (source && ENTITY_BACKED_SUGGESTS.has(source)) loadEntityRows()
  if (source === 'relationship_types' && !relationshipTypeOptions.value.length) loadRelationshipTypes()
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
  // A **pin**, not a query: name one specific thing by id. Without it the only way
  // to reach "this location" was `select locations → filter name == India`, which
  // stays `many` because a filtered collection has no size the engine can know —
  // and collapsing it needs `choose`, which asks the *player*. So a value that is
  // really one pinned entity could not be authored as `one` at all, which is what
  // made a location roller's row awkward to expose as a single location ([[B281]]).
  { kind: 'literal', label: 'Pick one thing' },
  { kind: 'filter', label: 'Filter' },
  { kind: 'navigate', label: 'Navigate' },
  { kind: 'aggregate', label: 'Aggregate' },
  { kind: 'choose', label: 'Choose' },
  { kind: 'evaluate', label: 'Evaluate' },
]

// A condition is a filter. `choose` needs a person to answer, and a gate has
// nobody to ask — such a step resolves to nothing and the condition silently
// never passes. Offered *disabled with the reason* rather than hidden, per the
// author's foolproofing rule.
const KIND_BLOCKED_REASON = 'a condition is a filter — choose needs someone to answer'

const OPERATORS = ['==', '!=', '>', '>=', '<', '<=', 'in', 'contains']
// A `choose` step's two modes, stored in `count`: 1, or `null` for "as many as
// they like". Numbers above 1 are no longer written — they only ever meant
// "more than one", and reading them as a cap was the lie the toggle removes.
const ONE = 1
const MULTI = null
const CHOOSE_MODES = [
  { value: ONE, label: 'Choose one' },
  { value: MULTI, label: 'Choose multiple', title: 'As many as they like — no limit' },
]
// The operators that only mean something for a *list* field. A pick must land in
// this family but must not overwrite a deliberate choice within it — picking a
// value for "nobody knows this" is still that rule.
const LIST_OPERATORS = ['contains', 'not contains']
const EVALUATE_OPERATORS = ['exists', '==', '!=', '>', '>=', '<', '<=']

const steps = computed({
  get: () => (props.modelValue && Array.isArray(props.modelValue.steps) ? props.modelValue.steps : []),
  set: (v) => emit('update:modelValue', { steps: v }),
})

const trace = ref({ types: [], errors: [], valid: false })
const insertingAt = ref(null)  // index of the step whose "+" was clicked (-1 = before the first)
let traceTimer = null

// Tell the parent which element the path currently resolves to. An effect that
// means different things at different destinations reads this — a change to a
// rating die can be timed, a change to a pool die cannot.
watch(trace, (t) => {
  const last = t?.types?.[t.types.length - 1]
  emit('resolve', last?.element || '')
})

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
  // A destination may accept more than one element (a die in a pool *or* a die of
  // a trait's rating), so the match is against the whole set.
  const wanted = props.destination?.elements || []
  if (!wanted.length) return false
  if (!t || !t.element || !wanted.includes(t.element)) return false
  if (props.destination.cardinality && t.cardinality !== props.destination.cardinality) return false
  return !errorAt(i)
}

// The functions the chosen field supports. No field → the collection-level ones
// (`count`, `random`); a field → the functions whose declared types accept it, so
// a `datetime` field never offers an average.
function aggregationsForField(i) {
  const t = aggFieldType(i)
  return aggregations().filter((a) => (t
    ? a.needsField && (!(a.accepts || []).length || a.accepts.includes(t))
    : !a.needsField))
}

function aggFieldType(i) {
  const name = steps.value[i]?.field
  if (!name) return ''
  return (fieldsFor(priorElement(i)).find((f) => f.name === name) || {}).type || ''
}

// What the function produces, in the chosen field's own terms: `same` is the
// field's type, `element` is what the collection holds (so the path keeps walking).
function aggOutputLabel(a, i) {
  if (a.output === 'same') return aggFieldType(i) || 'value'
  if (a.output === 'element') return priorElement(i) || 'element'
  return a.output
}

// Changing the field can invalidate the function; keep it only while it is still
// supported.
function onAggFieldChange(i) {
  const step = steps.value[i]
  if (!step) return
  if (!aggregationsForField(i).some((a) => a.name === step.fn)) step.fn = ''
  if (!aggNeedsCount(step.fn)) step.count = 1
}

// `random` samples the collection instead of collapsing it, so it asks how many
// rather than which field.
function aggNeedsCount(fn) {
  return (aggregations().find((a) => a.name === fn) || {}).needsCount
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

function optionToValueFor(i) {
  // A universe field holds the world's *handle* (`earth`), not its entity id
  // (`universe-earth`) — the one kind where the stored value differs from the
  // candidate's id.
  return fieldReferences(i) === 'universe' ? ((opt) => opt?.universe || opt?.id || '') : null
}

// ── A literal's value: the universal picker, plus an id escape hatch ──
// The picker is what an author should reach for (`[[UI-UX Design#Pickers]]`), and
// the id box is what keeps the nine candidate-less elements authorable.

function literalOptionToValue(i, opt) {
  // A universe holds its *handle* (`earth`), not its entity id — the same single
  // case a filter's reference value has, for the same reason.
  return steps.value[i]?.element === 'universe'
    ? (opt?.universe || opt?.id || '')
    : (opt?.id || '')
}

function onLiteralValue(i, val) {
  const step = steps.value[i]
  if (!step) return
  // `one`, never a list: a literal names exactly one thing, which is the whole
  // reason it exists.
  step.value = Array.isArray(val) ? (val[0] || '') : (val || '')
}

function onReferenceValue(i, val) {
  const step = steps.value[i]
  if (!step) return
  const values = (Array.isArray(val) ? val : (val ? [val] : [])).filter(Boolean)
  step.value = values.length > 1 ? values : (values[0] || '')
  if (isListField(i)) {
    // A field that declares `contains` and not `in` is a list, and a list is only
    // ever matched by `contains`/`not contains` — one pick means *is on the list*
    // (or *is not*), several mean *any of* (or *none of*), which is what the
    // resolver reads. Forcing `in` here wrote a step the resolver evaluates as "the
    // whole list equals one of these", which can never be true, so the filter
    // looked authored and matched nothing. A deliberate `not contains` stays.
    if (!LIST_OPERATORS.includes(step.operator)) step.operator = 'contains'
  } else if (values.length > 1) {
    step.operator = 'in'
  } else if (step.operator === 'in') {
    step.operator = '=='
  }
}

/** Whether a field holds a *list* of values.
 *
 * Declared, not guessed from the value: `contains` is the operator that only
 * means something for a list, and a field that also offers `in` is a scalar
 * taking one-or-several. That is how `tags`, `universes` and `known_to` are
 * distinguished from `entity.type` or `traitset_id`.
 */
function isListField(i) {
  const f = fieldsFor(priorElement(i)).find((x) => x.name === steps.value[i]?.field)
  const ops = f?.operators || []
  return ops.includes('contains') && !ops.includes('in')
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
function oneOrSeveral(i) {
  const v = steps.value[i]?.value
  return Array.isArray(v) ? v : (v ? [v] : [])
}

function onOneOrSeveralPicked(i, picked) {
  const values = [...picked]
  steps.value[i].value = values.length > 1 ? values : (values[0] || '')
  if (values.length > 1) steps.value[i].operator = 'in'
  else if (steps.value[i].operator === 'in') steps.value[i].operator = '=='
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
  // A boolean has to *be* a boolean: a string "true" would not equal the
  // instance's flag at resolve time.
  if (type === 'boolean') {
    if (raw === '' || raw == null) return ''
    return raw === true || raw === 'true'
  }
  return raw
}

// A boolean field renders as true/false rather than a text box that would store
// the string.
function isBooleanField(i) {
  return fieldTypeFor(i) === 'boolean'
}

function boolValue(i) {
  const v = steps.value[i]?.value
  if (v === true) return 'true'
  if (v === false) return 'false'
  return ''
}

function onBooleanPicked(i, e) {
  steps.value[i].value = coerceValue('boolean', e.target.value)
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

function onChooseMode(i, mode) {
  const step = steps.value[i]
  if (step) step.count = (mode == null ? null : Number(mode))
}

function toggleOutput(i) {
  const cur = steps.value[i]?.output
  steps.value[i].output = (cur == null) ? '' : null
}

function canInsertAfter(i, kind) {
  // A literal is a *seed* like `select` — it starts a path rather than narrowing
  // one — so it is offered only where a seed goes.
  if (kind === 'literal') return i === -1
  if (i === -1) return kind === 'select'  // first step is always a seed
  if (kind === 'select') return false
  const prior = typeAt(i)
  if (!prior || !prior.element) return false
  // evaluate is terminal: a boolean result can't be followed.
  if (prior.element === 'boolean') return false
  // choose collapses a *many* collection by asking the user; only offer it over
  // a set. (Whether the asking is *possible* is `kindBlocked`'s question.)
  if (kind === 'choose') return prior.cardinality === 'many'
  return true
}

// Context, not structure: what the path is *for* decides whether a step can
// exist at all.
function kindBlocked(kind) {
  return props.booleanTerminal && kind === 'choose'
}

function toggleInsert(i) {
  insertingAt.value = insertingAt.value === i ? null : i
}

function insert(i, kind) {
  // `value` is shared by `filter` and `literal` on purpose — both name one thing
  // in the step's own terms, and the resolver reads it the same way.
  const blank = { kind, collection: '', variable: '', element: '', output: null, field: kind === 'evaluate' ? 'count' : '', operator: '==', value: '', edge: '', dedup: false, fn: '', count: 1 }
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
  const dest = props.destination
  if (!dest?.elements?.length) return ''
  // Several accepted elements read as a choice ("die or rating_die").
  const names = dest.elements.join(' or ')
  return dest.cardinality ? `${names}/${dest.cardinality}` : names
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
.tsb-filter .tsb-enum { flex: none; width: 100%; min-width: 0; }
.tsb-filter .tsb-enum :deep(.tag-input) { min-height: 26px; padding: 3px 5px; }
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
