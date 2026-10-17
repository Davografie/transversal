<template>
  <div class="ce-root">
    <!-- Conditions are an ordered list: a later one may read a name an earlier
         one published, and the path builder offers variables in that order — so
         the rows are reorderable rather than fixed. `drag-handle` because every
         row is full of form controls and whole-row drag would eat text
         selection. -->
    <GmList
      v-if="conditions.length"
      :items="conditions"
      item-key=""
      reorderable
      drag-handle
      @reorder="onReorder"
    >
      <template #item="{ item: c, index: i }">
      <div class="ce-row" :class="{ 'ce-row-spec': usesSpec(c.type) }">
      <select v-model="c.type">
        <!-- The backend returns the vocabulary already banded and ordered, so the
             picker renders the grouping by grouping runs of the same band: no
             taxonomy lives here to drift from the one the backend declares. -->
        <optgroup v-for="g in typeGroups" :key="g.label" :label="g.label">
          <option v-for="t in g.options" :key="t.value" :value="t.value" :disabled="!typeUsable(t)">{{ t.label }}{{ optionReason(t) }}</option>
        </optgroup>
      </select>
      <span v-if="selectedProblem(c.type)" class="ce-warn">{{ selectedProblem(c.type) }}</span>
      <template v-if="usesSpec(c.type)">
        <!-- One line here; the builder opens in a child panel (`PathField`) — a
             path is a row of controls per step, and inlining it made a condition
             taller than every other field on the panel combined. -->
        <PathField v-model="c.spec" :source-element="sourceElement" :variables="variables" title="Condition path" boolean-terminal class="ce-spec" />
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
          <!-- An enum filter takes one value or several (*any of*), edited like the
               tag field: chips are the picked values, the input opens a filtered
               list of the vocabulary, and free text is refused (the options are
               the set). An empty pick says it never passes — no values is a set
               that matches nothing. -->
          <div v-else-if="targetOptions(c.type).length" class="ce-multi">
            <TagInput
              class="ce-multi-tags"
              :model-value="selectedTargets(c)"
              :suggestions="targetSuggestions(c.type)"
              :allow-custom="false"
              :placeholder="targetPlaceholder(c.type)"
              @update:model-value="setTargets(c, $event)"
            />
            <span v-if="!selectedTargets(c).length" class="ce-multi-empty">empty never passes</span>
          </div>
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
          <!-- A pool's **shape** is a state the per-die test cannot see: `== d8` is
               true of 1d8 and 2d8 alike, so two rungs of a ladder could not be gated
               apart. Only the types that declare modes offer them ([[B242]]). -->
          <select v-if="modes(c.type).length" :value="c.mode || 'any'"
                  class="ce-mode" title="How this rating is read"
                  @change="c.mode = $event.target.value">
            <option v-for="m in modes(c.type)" :key="m" :value="m">{{ modeLabel(m) }}</option>
          </select>
          <template v-if="(c.mode || 'any') === 'count'">
            <span class="ce-count-of">of</span>
            <input :value="c.count" type="number" min="0" placeholder="how many"
                   class="ce-count" @input="c.count = Number($event.target.value)" />
          </template>
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
      </template>
    </GmList>
    <Button class="ce-add" variant="secondary" block @click="add">＋ Add condition</Button>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useSfxMeta } from '@/composables/useSfxMeta.js'
import TargetPicker from '@/components/ui/TargetPicker.vue'
import UniversePicker from './UniversePicker.vue'
import PathField from './PathField.vue'
import TagInput from '@/components/ui/TagInput.vue'
import GmList from '@/components/ui/GmList.vue'
import Button from '@/components/ui/Button.vue'

const props = defineProps({
  modelValue: { type: Array, default: () => [] },
  sourceElement: { type: String, default: '' },  // catalog element of the SFX's source_kind
  // The context keys this point supplies (`null` = not modelled, so nothing is
  // forbidden). A condition reading a key that isn't here can never pass.
  availableKeys: { type: Array, default: null },
  // Typed names a condition path may `select variable` from — the activation's
  // own (trigger + source tokens) plus whatever earlier steps bound. Passed
  // through to the path builder; this editor invents no scope of its own.
  variables: { type: Object, default: null },
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

// One optgroup per band, in the order the backend sent them. A type the backend
// doesn't know (legacy content) has no band: it lands in its own group, still
// selectable, rather than being hidden or silently reordered.
const typeGroups = computed(() => {
  const groups = []
  for (const t of typeOptions.value) {
    const label = t.group || 'Other'
    const last = groups[groups.length - 1]
    if (last && last.label === label) last.options.push(t)
    else groups.push({ label, options: [t] })
  }
  return groups
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

// How a rating gate reads its pool — declared per type by the backend, so this
// file holds no list of its own ([[B242]]).
function modes(type) {
  const meta = conditionTypes.value.find(c => c.value === type)
  return meta?.modes || []
}

const MODE_LABELS = {
  any: 'any die',
  all: 'every die',
  count: 'a number of dice',
}

function modeLabel(mode) {
  return MODE_LABELS[mode] || mode
}

// Several values live in `targets`; one stays in `target`, so anything already
// authored keeps working and every reader sees the same thing.
function selectedTargets(c) {
  return (c.targets && c.targets.length) ? [...c.targets] : (c.target ? [c.target] : [])
}

// One value stays in `target` so anything already authored keeps working; the
// list is the `targets` set every reader sees.
function setTargets(c, values) {
  const next = [...values]
  c.targets = next
  c.target = next.length === 1 ? next[0] : ''
}

// The vocabulary as tag suggestions: the stored value is the raw token, the
// label is what a person reads ("give_in" → "Give In").
function targetSuggestions(type) {
  return targetOptions(type).map((o) => ({ value: o, label: labelize(o) }))
}

// A stored value reads as a label ("give_in" → "Give In").
function labelize(value) {
  return String(value)
    .replace(/[_-]+/g, ' ')
    .replace(/\b\w/g, (ch) => ch.toUpperCase())
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

// Order is meaning here (a later condition may read an earlier one's name), so a
// move rewrites the list rather than only the display.
function onReorder(from, to) {
  if (from === to || from < 0 || to < 0) return
  const next = [...props.modelValue]
  if (from >= next.length || to >= next.length) return
  const [moved] = next.splice(from, 1)
  next.splice(to, 0, moved)
  emit('update:modelValue', next)
}
</script>

<style scoped>
.ce-root { display: flex; flex-direction: column; gap: 4px; }
/* `flex: 1` because the row is now a GmList row's child (the row owns the
   shell); the drag handle sits after it. */
.ce-row { display: flex; gap: 4px; align-items: center; flex: 1; min-width: 0; }
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
/* Enum targets are a tag field: chips for the picks, the input opens the
   vocabulary (a native multi-select hid whether anything was picked at all). */
.ce-multi { display: flex; flex-direction: column; gap: 2px; flex: 2; min-width: 0; }
.ce-multi-tags { min-width: 0; }
.ce-multi-tags :deep(.tag-input) { min-height: 24px; padding: 2px 4px; border-radius: 4px; }
.ce-multi-tags :deep(.tag-text) { font-size: 11px; }
.ce-multi-empty { font-size: 9px; color: var(--warn, #d8a13a); }
/* "＋ Add condition" keeps its deliberate dashed accent (full width via the
   column flex parent); fill/radius/padding/hover come from ui/Button. */
.ce-root > .ce-add { border-style: dashed; border-color: var(--overlay-15); }
/* Each row is a GmList row now, so the primitive owns the shell. Its defaults are
   for *clickable* list rows — a pointer cursor and centred content — which a row
   of form controls does not want. */
.ce-root :deep(.gml-item) { cursor: default; align-items: flex-start; }
.ce-row-spec { flex-wrap: wrap; align-items: flex-start; }
.ce-row-spec > select { flex: none; width: 140px; }
/* The path is one summary line spanning the row (it replaces the inline builder,
   which was the reason the row wrapped at all). */
.ce-spec { flex: 1 1 100%; min-width: 0; }
</style>
