<template>
  <div class="ee-rating">
    <div class="ee-result-mode">
      <button type="button" :class="{ active: mode === 'die' }" @click="pick('die')">Dice</button>
      <!-- Offered only when there is something to name. A mode that opens on an
           empty list is a dead end, and "the rating the source already has" is a
           *list* of dice — `rating_die`, `many` — which is the **Path**'s job, not
           this one's ([[B307]]). A stored `{name}` keeps the mode visible, so a
           value the author already chose is never stranded. -->
      <button v-if="variableChoices.length" type="button" :class="{ active: mode === 'variable' }"
              @click="pick('variable')">Variable</button>
      <!-- A die can also be a *fact in the world* — a challenge's next capacity
           slot, or the rating the rule's own source already has — which no literal
           names. Then it is a path, and a path takes **every** die it resolves
           ([[B307]]). -->
      <button type="button" :class="{ active: mode === 'spec' }" @click="pick('spec')">Path</button>
    </div>
    <!-- A rating is a row of dice, not one die: a resource holds several and a
         challenge usually three. `context.dice` is the row and `result` carries
         its first die, which is what every single-die reader already understands
         ([[B307]]). An action that takes one die keeps the plain dropdown. -->
    <DiePicker
      v-if="mode === 'die' && canRow"
      multiple
      :model-value="row"
      @update:model-value="$emit('update:row', $event)"
    />
    <select
      v-else-if="mode === 'die'"
      :value="result"
      @change="$emit('update:result', $event.target.value)"
    >
      <option v-for="o in (field?.options || [])" :key="o" :value="o">{{ o }}</option>
    </select>
    <select
      v-else-if="mode === 'variable'"
      :value="result"
      @change="$emit('update:result', $event.target.value)"
    >
      <option value="">— variable —</option>
      <option v-for="v in variableChoices" :key="v" :value="v">{{ v }}</option>
    </select>
    <PathField
      v-else
      :model-value="spec"
      :destination="DESTINATION"
      :source-element="sourceElement"
      :variables="outputVariables"
      title="Die from a path"
      @update:model-value="$emit('update:spec', $event)"
    />
  </div>
</template>

<script setup>
/**
 * The **rating** a die-valued effect asks for, in its three modes — a row of dice,
 * one named die, or a path ([[B307]]).
 *
 * One component for two hosts on purpose. An action's own `result` field renders it
 * (every die action), and a trait-creating verb renders it *inside* the trait
 * instance editor, where the instance it describes is being authored — the rating
 * type and the dice belong in one box, not one inside and one below. It lived only
 * in the field for a day, and "where did the rating go" was the answer.
 */
import { computed } from 'vue'
import DiePicker from '@/components/DiePicker.vue'
import PathField from './PathField.vue'

const props = defineProps({
  /** The action's `result` field definition — its `options` are the literal dice. */
  field: { type: Object, default: null },
  /** `'die'` | `'variable'` | `'spec'` — the host owns it, because it saves it. */
  mode: { type: String, default: 'die' },
  /** The rating row, when this action creates a whole one. */
  row: { type: Array, default: () => [] },
  /** Whether a row applies at all (the action declares one). */
  canRow: { type: Boolean, default: false },
  /** The stored `result` — one die, or a `{variable}`. */
  result: { type: String, default: '' },
  /** The `result_spec` draft. */
  spec: { type: Object, default: () => ({ steps: [] }) },
  sourceElement: { type: String, default: '' },
  outputVariables: { type: Object, default: null },
  /**
   * Rating-capable names in scope, as `{name, cardinality}`. The component filters
   * them by `canRow` — see `variableChoices`.
   */
  variables: { type: Array, default: () => [] },
})

const emit = defineEmits(['update:mode', 'update:row', 'update:result', 'update:spec'])

// A die named by a path resolves to a *die* — either a slot of a challenge's
// capacity (the ceiling) or a die of a trait instance's rating (what it holds).
// Both carry a die size, so both are offered, and nothing else is.
const DESTINATION = { elements: ['capacity_die', 'rating_die'] }

// Switching mode must not leave the other mode's value behind, or the effect would
// carry both and the row would win silently at fire time. The host clears its own
// half; this reports the intent.
function pick(mode) {
  emit('update:mode', mode)
}

// The named ratings this field may read, plus whatever is stored — an editor never
// rewrites a value it cannot represent (the rule the placement and arming-scope
// selects follow).
//
// How much of the list is usable depends on the action, and that is the whole
// difference between the two hosts: an action that creates a trait at a whole
// **rating** can read a name that *holds* one (`many`), because the engine resolves
// it into the row; one that takes a single **die** can only read a name whose value
// *is* a die. Offering a list to the second would offer something its handler
// refuses ([[B306]], [[B307]]).
const variableChoices = computed(() => {
  const out = (props.variables || [])
    .map((v) => (typeof v === 'string' ? { name: v, cardinality: 'one' } : v))
    .filter((v) => props.canRow || (v.cardinality || 'one') !== 'many')
    .map((v) => `{${v.name}}`)
  const current = String(props.result || '')
  if (current.startsWith('{') && !out.includes(current)) out.push(current)
  return out
})
</script>

<style scoped>
.ee-rating { display: flex; flex-direction: column; gap: 6px; }
/* The same mode row the field rendered before it moved — one look, both hosts. */
.ee-result-mode { display: flex; gap: 4px; }
.ee-result-mode button { font-size: 9px; padding: 2px 7px; border-radius: 4px; background: var(--overlay-6); border: 1px solid var(--overlay-10); color: var(--text-dim); cursor: pointer; }
.ee-result-mode button.active { background: var(--accent-20); border-color: var(--accent-dim); color: var(--accent); }
.ee-rating select { width: 100%; }
</style>
