<template>
  <div class="bv-root">
    <!-- Each row is one name the rule resolves for itself, with the same target
         builder every other path uses. Rows are ordered: a later one may start
         from an earlier one (`select variable`), which is how a value is read
         *from* a thing named just above. -->
    <div v-for="(row, i) in rows" :key="i" class="bv-row">
      <div class="bv-row-head">
        <input
          class="bv-name"
          :value="row.name"
          placeholder="variable name"
          @input="onName(i, $event.target.value)"
        />
        <span class="bv-token">{{ '{' + (row.name || '…') + '}' }}</span>
        <span v-if="typeAt(i)" class="bv-type">{{ typeAt(i) }}</span>
        <Button class="bv-remove" variant="danger-ghost" size="sm" title="Remove" @click="remove(i)">✕</Button>
      </div>
      <PathField
        :model-value="row.spec"
        :source-element="sourceElement"
        :variables="scopeFor(i)"
        title="Value path"
        @update:model-value="onSpec(i, $event)"
      />
      <p v-if="row.name && typeAt(i)" class="bv-reads">
        usable as <code>{{ '{' + row.name + '}' }}</code> anywhere below
      </p>
      <p v-else-if="row.name" class="bv-reads bv-unresolved">
        this path resolves to nothing yet — nothing below can use it
      </p>
    </div>

    <Button class="bv-add" variant="secondary" size="sm" @click="add">+ Add variable</Button>
    <p v-if="!rows.length" class="bv-empty">
      Name a value this rule is about, before its conditions are checked — e.g.
      <em>the tier of my rating</em>. Later conditions and effects refer to it by
      name.
    </p>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import Button from '@/components/ui/Button.vue'
import PathField from './PathField.vue'
import { useTargetCatalog } from '@/composables/useTargetCatalog.js'

const props = defineProps({
  modelValue: { type: Array, default: () => [] },
  sourceElement: { type: String, default: '' },
  // The activation's own names ({trait_setting}, {order}, …) — the scope every
  // row starts from, because the engine binds them before the declarations run.
  variables: { type: Object, default: () => ({}) },
  // The declared rows' resolved types, **in declaration order** (`{element,
  // cardinality}` or null). Traced by the panel through the backend checker, so
  // this component never derives a type of its own.
  types: { type: Array, default: () => [] },
})

const emit = defineEmits(['update:modelValue'])

const { elementLabel } = useTargetCatalog()

const rows = computed(() => props.modelValue || [])

/** What row `i` may start from: the activation's names plus every *earlier* row.
 *  A later row is deliberately absent — it has not resolved yet at this point in
 *  the sequence, and offering it would promise a value the engine cannot have. */
function scopeFor(i) {
  const scope = { ...(props.variables || {}) }
  for (let j = 0; j < i; j++) {
    const t = props.types[j]
    const name = (rows.value[j]?.name || '').trim()
    if (t && name) scope[name] = { element: t.element, cardinality: t.cardinality || 'one' }
  }
  return scope
}

// A scalar has no catalog element, so `elementLabel` echoes its type name
// ("int"). Say what it *reads as* instead — the author is picking a name to use
// in an amount, not choosing a type.
const SCALAR_LABELS = { int: 'a number', number: 'a number', die: 'a die', string: 'text', boolean: 'yes/no' }

function typeAt(i) {
  const t = props.types[i]
  if (!t || !t.element) return ''
  if (SCALAR_LABELS[t.element]) return SCALAR_LABELS[t.element]
  const label = elementLabel(t.element) || t.element
  return (t.cardinality === 'many') ? `several ${label}s` : label
}

function replace(i, next) {
  const list = [...rows.value]
  list[i] = { ...list[i], ...next }
  emit('update:modelValue', list)
}

function onName(i, name) { replace(i, { name }) }
function onSpec(i, spec) { replace(i, { spec }) }

function add() {
  emit('update:modelValue', [...rows.value, { name: '', spec: { steps: [] } }])
}

function remove(i) {
  emit('update:modelValue', rows.value.filter((_row, j) => j !== i))
}
</script>

<style scoped>
.bv-root { display: flex; flex-direction: column; gap: 8px; }
.bv-row {
  display: flex; flex-direction: column; gap: 6px;
  padding: 8px; border: 1px solid var(--overlay-10); border-radius: 6px;
  background: var(--overlay-4);
}
.bv-row-head { display: flex; align-items: center; gap: 6px; }
.bv-name { flex: 1; min-width: 0; }
.bv-token { font-family: monospace; font-size: 11px; color: var(--accent-pale); white-space: nowrap; }
.bv-type { font-size: 10px; color: var(--text-dim); white-space: nowrap; }
.bv-remove { flex: none; }
.bv-reads { margin: 0; font-size: 10px; color: var(--text-dim); }
.bv-reads code { font-size: 10px; color: var(--accent-pale); }
.bv-unresolved { color: var(--warn); }
.bv-empty { margin: 0; font-size: 11px; color: var(--text-dim); }
.bv-add { align-self: flex-start; }
</style>
