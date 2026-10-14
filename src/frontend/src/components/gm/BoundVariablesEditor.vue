<template>
  <div class="bv-root">
    <!-- Each row is one name the rule resolves for itself, with the same target
         builder every other path uses. Rows are ordered: a later one may start
         from an earlier one (`select variable`), which is how a value is read
         *from* a thing named just above. -->
    <div v-for="(row, i) in rows" :key="i" class="bv-row" :class="{ 'bv-collide': collisionAt(i) || mismatchAt(i) }">
      <div class="bv-row-head">
        <!-- An **assignment** picks a name the table reserved rather than typing
             one ([[B285]]): a typo would otherwise invent a near-duplicate that the
             save refuses. A name already stored and not reserved stays selectable,
             so opening an old row cannot silently rewrite it. -->
        <select
          v-if="assignments.length"
          class="bv-name"
          :value="row.name"
          @change="onName(i, $event.target.value)"
        >
          <option value="">— reserved variable —</option>
          <option v-for="a in assignmentOptions(i)" :key="a.name" :value="a.name">
            {{ optionLabel(a) }}
          </option>
        </select>
        <input
          v-else
          class="bv-name"
          :value="row.name"
          placeholder="variable name"
          @input="onName(i, $event.target.value)"
        />
        <span class="bv-token">{{ '{' + (row.name || '…') + '}' }}</span>
        <span v-if="typeAt(i)" class="bv-type">{{ typeAt(i) }}</span>
        <Button class="bv-remove" variant="danger-ghost" size="sm" title="Remove" @click="remove(i)">✕</Button>
      </div>
      <!-- A **reservation**: a type and no value. It binds nothing; it is what every
           row assigning this name is checked against, so that one hand-written path
           cannot make the name a different type for one row alone ([[B285]]). -->
      <div v-if="isSlot(row)" class="bv-slot">
        <select :value="row.element" @change="onElement(i, $event.target.value)">
          <option value="">— type of thing —</option>
          <option v-for="e in (catalog?.elements || [])" :key="e.name" :value="e.name">
            {{ e.label || e.name }}
          </option>
        </select>
        <select :value="row.cardinality || 'one'" @change="onCardinality(i, $event.target.value)">
          <option value="one">one</option>
          <option value="many">many</option>
        </select>
      </div>
      <PathField
        v-else
        :model-value="row.spec"
        :source-element="sourceElement"
        :variables="scopeFor(i)"
        title="Value path"
        @update:model-value="onSpec(i, $event)"
      />
      <p v-if="collisionAt(i)" class="bv-reads bv-shadows">
        ⚠ {{ collisionAt(i) }}
      </p>
      <p v-else-if="mismatchAt(i)" class="bv-reads bv-shadows">
        ⚠ {{ mismatchAt(i) }}
      </p>
      <p v-else-if="isSlot(row) && row.element" class="bv-reads">
        each entry that assigns <code>{{ '{' + row.name + '}' }}</code> must resolve
        {{ typeAt(i) }} — this slot holds no value of its own
      </p>
      <p v-else-if="row.name && typeAt(i)" class="bv-reads">
        usable as <code>{{ '{' + row.name + '}' }}</code> anywhere below
      </p>
      <p v-else-if="row.name" class="bv-reads bv-unresolved">
        this path resolves to nothing yet — nothing below can use it
      </p>
    </div>

    <div class="bv-actions">
      <Button class="bv-add" variant="secondary" size="sm" @click="add(false)">+ Add variable</Button>
      <!-- Only a table's own layer can hold a reservation: it is what the rows'
           assignments are checked against, so it is stated once, above them. -->
      <Button
        v-if="allowReservations"
        class="bv-add bv-add-slot"
        variant="secondary"
        size="sm"
        @click="add(true)"
      >+ Reserve a slot</Button>
    </div>
    <p v-if="!rows.length" class="bv-empty">
      Name a value this rule is about, before its conditions are checked — e.g.
      <em>the tier of my rating</em>. Later conditions and effects refer to it by
      name.
    </p>
    <p v-else-if="allowReservations" class="bv-empty">
      A <strong>value</strong> resolves once for the whole table. A
      <strong>reserved slot</strong> states a name's type once and binds nothing:
      each entry assigns it, and an assignment that resolves a different type is
      refused rather than silently making the name mean two things.
    </p>
  </div>
</template>

<script setup>
import { computed, onMounted } from 'vue'
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
  // Names **already in scope** when this layer resolves — the ambient facts plus
  // any earlier declaration layer (a roll table's own names, for a row's;
  // [[B281]]). The engine resolves those first and *refuses* a declaration that
  // shadows one rather than rebinding it, so a collision has to be visible here:
  // the alternative is a name that saves and then silently does nothing.
  reserved: { type: Array, default: () => [] },
  // When true a row may be a **reservation** — a name with a declared type and no
  // path ([[B285]]). Only a roll table's own layer offers this: the reservation is
  // what every row's assignment is checked against, so it is stated once, above them.
  allowReservations: { type: Boolean, default: false },
  // The **reserved slots** an assignment may pick from, `{name, element,
  // cardinality}`. Non-empty turns the name field into a picker and checks the row's
  // traced type against the slot it chose, because the table refuses a mismatched
  // save and the author should see why before it happens.
  assignments: { type: Array, default: () => [] },
})

const emit = defineEmits(['update:modelValue'])

const { elementLabel, catalog, loaded, load } = useTargetCatalog()

const rows = computed(() => props.modelValue || [])

// The element picker is the catalog's own vocabulary, loaded once per session.
onMounted(() => { if (props.allowReservations && !loaded.value) load() })

/** A row that **states a type instead of a value** — a reservation, or a slot just
 *  added and not yet typed. The shape is the test, not a flag: a row with no steps
 *  has no path, and a slot with no element is one the author has not finished. */
function isSlot(row) {
  return props.allowReservations && !(row?.spec?.steps || []).length
}

/** What row `i` may start from: the activation's names plus every *earlier* row.
 *  A later row is deliberately absent — it has not resolved yet at this point in
 *  the sequence, and offering it would promise a value the engine cannot have.
 *  A reservation is absent for the same reason: it holds no value, so a path cannot
 *  start from it, and the engine refuses to bind one. */
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

function label(t) {
  if (!t || !t.element) return ''
  if (SCALAR_LABELS[t.element]) return SCALAR_LABELS[t.element]
  const name = elementLabel(t.element) || t.element
  return (t.cardinality === 'many') ? `several ${name}s` : name
}

function typeAt(i) {
  const row = rows.value[i]
  // A slot's type is the one it *states*; the traced types below are null for it,
  // because a reservation has no path to trace.
  if (isSlot(row)) return row.element ? label({ element: row.element, cardinality: row.cardinality }) : ''
  return label(props.types[i])
}

function replace(i, next) {
  const list = [...rows.value]
  list[i] = { ...list[i], ...next }
  emit('update:modelValue', list)
}

/** Why row `i`'s name will not bind, if it will not — "" when it is fine.
 *
 *  Two ways to collide, one rule: the engine resolves names in order and refuses a
 *  declaration whose name is already bound, so the *existing* value stands. Either
 *  something outside this list already holds the name (``reserved``), or an earlier
 *  row in this list declared it. Both would otherwise fail silently at runtime. */
function collisionAt(i) {
  const name = (rows.value[i]?.name || '').trim()
  if (!name) return ''
  if ((props.reserved || []).includes(name)) {
    return `“${name}” is already in scope here — the existing value wins, so this will not bind`
  }
  for (let j = 0; j < i; j++) {
    if ((rows.value[j]?.name || '').trim() === name) {
      return `“${name}” is declared above — the first one wins, so this will not bind`
    }
  }
  return ''
}

/** The reserved slots row `i` may pick, plus whatever it already names.
 *
 *  The row's own slot is always listed — filtering it out would leave a `<select>`
 *  whose value matches no option, which renders blank and looks like the assignment
 *  was lost. A stored name the table does not reserve is listed too and flagged, so
 *  opening an old row cannot silently rewrite it and the author can see the one
 *  thing the save will refuse. */
function assignmentOptions(i) {
  const name = (rows.value[i]?.name || '').trim()
  const listed = props.assignments
  const known = listed.some((a) => a.name === name)
  return name && !known ? [{ name, element: '', cardinality: '' }, ...listed] : listed
}

function slotFor(name) {
  const wanted = (name || '').trim()
  return wanted ? props.assignments.find((a) => a.name === wanted) : null
}

/** One line per choice: the slot's name and the type it fixes, or — for a stored name
 *  the table does not reserve — that it is not one. */
function optionLabel(a) {
  return a.element ? `${a.name} (${label(a)})` : `${a.name} — not reserved`
}

/** Why row `i`'s path does not match the slot it assigns — "" when it does, when it
 *  cannot be told, or when the table reserves nothing.
 *
 *  "Cannot be told" is not a mismatch: a path the checker cannot type has no
 *  verdict, and the same rule keeps a name resolving to nothing unbound rather than
 *  bound empty. */
function mismatchAt(i) {
  const row = rows.value[i]
  const name = (row?.name || '').trim()
  if (!props.assignments.length || !name) return ''
  const slot = slotFor(name)
  if (!slot) {
    return `the table does not reserve “${name}” — the save is refused until it does`
  }
  const t = props.types[i]
  if (!t?.element) return ''
  if (slot.element !== t.element || (slot.cardinality || 'one') !== (t.cardinality || 'one')) {
    return `“${name}” is reserved as ${label(slot)}, but this path resolves ${label(t)}`
  }
  return ''
}

function onName(i, name) {
  const slot = slotFor(name)
  // Picking a slot states the name; the type comes from the slot, so a stale
  // element/cardinality on the row cannot survive as a second, quieter statement.
  replace(i, slot ? { name, element: '', cardinality: '' } : { name })
}
function onSpec(i, spec) { replace(i, { spec }) }
function onElement(i, element) { replace(i, { element }) }
function onCardinality(i, cardinality) { replace(i, { cardinality }) }

function add(reserved) {
  emit('update:modelValue', [
    ...rows.value,
    reserved ? { name: '', spec: null, element: '', cardinality: 'one' }
             : { name: '', spec: { steps: [] }, element: '', cardinality: '' },
  ])
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
/* A name that will be refused is a hard error, not a warning: it saves and then
   silently does nothing, which is the failure this makes visible. */
.bv-collide { border-color: var(--danger); }
.bv-shadows { color: var(--danger); }
.bv-empty { margin: 0; font-size: 11px; color: var(--text-dim); }
.bv-actions { display: flex; gap: 6px; flex-wrap: wrap; }
.bv-add { align-self: flex-start; }
/* A reservation picks a type instead of building a path: the two halves of the
   statement, side by side. */
.bv-slot { display: flex; gap: 6px; }
.bv-slot select { flex: 1 1 0; min-width: 0; }
.bv-slot select:last-child { flex: 0 0 84px; }
</style>
