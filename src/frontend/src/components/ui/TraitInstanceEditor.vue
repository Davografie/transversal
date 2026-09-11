<template>
  <div class="trait-instance-editor" :class="variant === 'box' ? 'is-box' : 'is-panel'">
    <!-- Rating type -->
    <div v-if="showRatingType" class="te-field">
      <span class="te-label">Rating</span>
      <div class="te-rating-type">
        <button
          v-for="rt in RATING_TYPES"
          :key="rt.id"
          type="button"
          class="rating-type-btn"
          :class="{ active: ratingType === rt.id }"
          @click="setRatingType(rt.id)"
        >{{ rt.label }}</button>
      </div>
    </div>

    <!-- Dice — array mode: a row of chips, the popup picker edits one slot -->
    <div v-if="showDice && mode === 'array' && ratingType !== 'EMPTY'" class="te-field">
      <span class="te-label">Dice</span>
      <div class="te-dice">
        <button
          v-for="(d, i) in dice"
          :key="i"
          class="die-chip die-chip-icon"
          :title="`Change ${d}`"
          @click="openPicker(i)"
        ><DieIcon :die="d" /></button>
        <button class="die-chip add-chip" @click="openPicker(dice.length)">+</button>
      </div>
      <div v-if="ratingType === 'RESOURCE' && spentDice.length" class="te-spent-dice">
        <span class="te-spent-label">Recoverable</span>
        <button
          v-for="(die, i) in spentDice"
          :key="'spent' + i"
          class="die-chip ghost-chip die-chip-icon"
          :title="`Recover one ${die.toLowerCase()}`"
          @click="$emit('recover-die', die)"
        ><DieIcon :die="die.toLowerCase()" /></button>
      </div>
      <DiePicker v-if="showPicker" v-model="pickedDie" @update:model-value="onPicked" />
    </div>

    <!-- Dice — single mode: one inline picker, optionally a variable placeholder -->
    <div v-else-if="showDice && mode === 'single'" class="te-field">
      <span class="te-label">Die</span>
      <div v-if="allowVariable" class="te-die-mode">
        <Button type="button" :active="!isVariable" variant="neutral" @click="setVariableMode(false)">Die</Button>
        <Button type="button" :active="isVariable" variant="neutral" @click="setVariableMode(true)">Variable</Button>
      </div>
      <DiePicker v-if="!isVariable" :model-value="die" @update:model-value="emitDie" />
      <select v-else :value="die" @change="emitDie($event.target.value)">
        <option v-for="v in variableOptions" :key="v" :value="v">{{ v }}</option>
      </select>
    </div>

    <!-- Capacity — challenge traits rate their track separately -->
    <div v-if="showCapacity && ratingType === 'CHALLENGE'" class="te-field">
      <span class="te-label">Capacity</span>
      <div class="te-dice">
        <button
          v-for="(d, i) in capacity"
          :key="'cap' + i"
          class="die-chip die-chip-icon"
          :title="`Change ${d}`"
          @click="openCapacityPicker(i)"
        ><DieIcon :die="d" /></button>
        <button class="die-chip add-chip" @click="openCapacityPicker(capacity.length)">+</button>
      </div>
      <DiePicker v-if="showCapacityPicker" v-model="pickedCapacityDie" @update:model-value="onCapacityPicked" />
    </div>

    <!-- Polarity -->
    <div v-if="showPolarity" class="te-field">
      <span class="te-label">Type</span>
      <Button
        type="button"
        class="polarity-toggle"
        :class="{ 'is-positive': polarity === 'POSITIVE' }"
        :active="polarity === 'NEGATIVE'"
        variant="neutral"
        @click="togglePolarity"
      >
        {{ polarity === 'POSITIVE' ? 'positive' : 'negative' }}
      </Button>
    </div>

    <!-- Host extras that belong beside the rating (SFX chips, …) -->
    <slot name="after-dice" />

    <div v-if="showStatement" class="te-field">
      <span class="te-label">Statement</span>
      <input
        v-model="statementModel"
        class="te-statement"
        placeholder="Statement…"
        @blur="$emit('field-blur', 'statement')"
      />
    </div>

    <div v-if="showNotes" class="te-field">
      <span class="te-label">Notes</span>
      <textarea
        v-model="notesModel"
        class="te-notes"
        placeholder="Notes…"
        @blur="$emit('field-blur', 'notes')"
      ></textarea>
    </div>

    <!-- Host extras that belong after the text fields (morph/projection, sub-traits, …) -->
    <slot name="after-fields" />

    <slot name="actions" />
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import DieIcon from '@/components/DieIcon.vue'
import DiePicker from '@/components/DiePicker.vue'
import Button from '@/components/ui/Button.vue'

const RATING_TYPES = [
  { id: 'STATIC', label: 'Static' },
  { id: 'RESOURCE', label: 'Resource' },
  { id: 'CHALLENGE', label: 'Challenge' },
  { id: 'EMPTY', label: 'Empty' },
]

const props = defineProps({
  /** Canonical uppercase rating type: STATIC | RESOURCE | CHALLENGE | EMPTY. */
  ratingType: { type: String, default: 'STATIC' },
  /** Die faces for array mode, lowercase (e.g. ['d6', 'd8']). */
  dice: { type: Array, default: () => [] },
  /** Capacity faces, lowercase — challenge traits only. */
  capacity: { type: Array, default: () => [] },
  /** Single-die value for `mode: 'single'`, lowercase or a `{variable}`. */
  die: { type: String, default: '' },
  /** 'POSITIVE' | 'NEGATIVE' | null */
  polarity: { type: String, default: null },
  statement: { type: String, default: '' },
  notes: { type: String, default: '' },
  /** Spent-but-recoverable resource dice, lowercase. */
  spentDice: { type: Array, default: () => [] },
  /** 'array' edits a row of dice; 'single' edits one die. */
  mode: { type: String, default: 'array' },
  variant: { type: String, default: 'panel' }, // 'panel' (bare sections) | 'box' (bordered)
  showRatingType: { type: Boolean, default: true },
  showDice: { type: Boolean, default: true },
  showCapacity: { type: Boolean, default: true },
  showPolarity: { type: Boolean, default: true },
  showStatement: { type: Boolean, default: true },
  showNotes: { type: Boolean, default: true },
  allowVariable: { type: Boolean, default: false },
  variables: { type: Array, default: () => [] },
})

const emit = defineEmits([
  'update:ratingType', 'update:dice', 'update:capacity', 'update:die',
  'update:polarity', 'update:statement', 'update:notes',
  'recover-die', 'change', 'field-blur',
])

// --- text fields (pass through, host debounces its own saves) ---
const statementModel = computed({
  get: () => props.statement || '',
  set: (v) => { emit('update:statement', v); emit('change', 'statement') },
})
const notesModel = computed({
  get: () => props.notes || '',
  set: (v) => { emit('update:notes', v); emit('change', 'notes') },
})

// --- rating type ---
function setRatingType(id) {
  if (props.ratingType === id) return
  emit('update:ratingType', id)
  emit('change', 'ratingType')
}

// --- dice row (array mode) ---
const showPicker = ref(false)
const pickIdx = ref(0)
const pickedDie = ref('')

function openPicker(i) {
  pickIdx.value = i
  pickedDie.value = props.dice[i] || ''
  showPicker.value = true
}

function onPicked(die) {
  const next = [...props.dice]
  if (!die) next.splice(pickIdx.value, 1)
  else if (pickIdx.value >= next.length) next.push(die)
  else next.splice(pickIdx.value, 1, die)
  showPicker.value = false
  emit('update:dice', next)
  emit('change', 'dice')
}

// --- capacity row ---
const showCapacityPicker = ref(false)
const capacityPickIdx = ref(0)
const pickedCapacityDie = ref('')

function openCapacityPicker(i) {
  capacityPickIdx.value = i
  pickedCapacityDie.value = props.capacity[i] || ''
  showCapacityPicker.value = true
}

function onCapacityPicked(die) {
  const next = [...props.capacity]
  if (!die) next.splice(capacityPickIdx.value, 1)
  else if (capacityPickIdx.value >= next.length) next.push(die)
  else next.splice(capacityPickIdx.value, 1, die)
  showCapacityPicker.value = false
  emit('update:capacity', next)
  emit('change', 'capacity')
}

// --- single-die mode ---
const isVariable = ref((props.die || '').startsWith('{'))
watch(() => props.die, (d) => { isVariable.value = (d || '').startsWith('{') })

const variableOptions = computed(() => {
  const opts = (props.variables || []).map(v => `{${v}}`)
  const cur = props.die
  if (cur && cur.startsWith('{') && !opts.includes(cur)) opts.push(cur)
  return opts
})

function setVariableMode(variable) {
  isVariable.value = variable
  if (variable) {
    if (!(props.die || '').startsWith('{')) emitDie(variableOptions.value[0] || '{effect_die}')
  } else if ((props.die || '').startsWith('{')) {
    emitDie('d6')
  }
}

function emitDie(die) {
  emit('update:die', die)
  emit('change', 'die')
}

// --- polarity ---
function togglePolarity() {
  const next = props.polarity === 'POSITIVE' ? 'NEGATIVE' : 'POSITIVE'
  emit('update:polarity', next)
  emit('change', 'polarity')
}
</script>

<style scoped>
.trait-instance-editor {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.te-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.te-label {
  font-size: 10px;
  font-weight: 600;
  color: var(--text-dim);
  text-transform: uppercase;
  letter-spacing: 0.6px;
}
.te-rating-type {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  align-items: center;
}
.rating-type-btn {
  padding: 4px 10px;
  border-radius: 999px;
  border: 1px solid var(--overlay-12);
  background: transparent;
  color: var(--text-dim);
  font-size: 11px;
  cursor: pointer;
  transition: border-color 0.15s, color 0.15s, background 0.15s;
}
.rating-type-btn.active {
  border-color: var(--accent);
  color: var(--accent);
  background: var(--accent-12);
}
.te-dice {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
}
.te-dice .die-chip {
  font-size: 14px;
  font-weight: 700;
  padding: 3px 10px;
  border-radius: 6px;
  border: 2px solid var(--overlay-10);
  background: var(--overlay-6);
  color: var(--text);
  cursor: pointer;
  transition: border-color 0.15s;
}
.te-dice .die-chip:hover {
  border-color: var(--accent);
}
.te-dice .add-chip {
  color: var(--accent);
  border-color: var(--accent-dim);
  font-size: 16px;
  font-weight: 400;
  padding: 3px 8px;
}
.te-dice .add-chip:hover {
  border-color: var(--accent);
  background: var(--accent-12);
}
.te-spent-dice {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}
.te-spent-label {
  font-size: 12px;
  color: var(--text-dim);
}
.te-spent-dice .die-chip {
  font-size: 13px;
  font-weight: 700;
  padding: 2px 9px;
  border-radius: 6px;
  border: 2px dashed var(--overlay-25);
  background: var(--overlay-4);
  color: var(--text-dim);
  cursor: pointer;
  transition: border-color 0.15s, color 0.15s;
}
.te-spent-dice .die-chip:hover {
  border-color: var(--accent);
  color: var(--text);
}
.te-dice .die-chip.die-chip-icon,
.te-spent-dice .die-chip.die-chip-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 2px;
  line-height: 0;
}
.te-dice .die-chip.die-chip-icon .die-icon,
.te-spent-dice .die-chip.die-chip-icon .die-icon {
  width: 28px;
  height: 30px;
}
.te-spent-dice .die-chip.die-chip-icon .die-icon {
  opacity: 0.45;
}
.te-statement,
.te-notes {
  width: 100%;
  box-sizing: border-box;
  background: var(--overlay-4);
  border: 1px solid var(--overlay-12);
  border-radius: 6px;
  color: var(--text);
  font-size: 12px;
  font-family: inherit;
  padding: 6px 8px;
  transition: border-color 0.15s;
}
.te-statement:focus,
.te-notes:focus {
  outline: none;
  border-color: var(--accent);
}
.te-notes {
  min-height: 56px;
  resize: vertical;
}
.te-die-mode {
  display: flex;
  gap: 4px;
}
/* Polarity toggle: typography/layout only — the primitive owns the chrome and
   the neutral/active fills. The positive skin (accent outline) carries the
   positive/negative meaning. */
.te-field .polarity-toggle {
  align-self: flex-start;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}
.te-field .polarity-toggle.is-positive {
  border-color: var(--accent);
  color: var(--accent);
  background: var(--overlay-6);
}

/* Box variant — the compact chrome used inside editor forms (SFX effect form). */
.trait-instance-editor.is-box {
  gap: 10px;
  padding: 10px;
  border: 1px solid var(--overlay-10);
  border-radius: 8px;
}
.is-box .te-label {
  font-weight: 400;
  letter-spacing: 0.5px;
}
.is-box .te-notes { min-height: 48px; }
.is-box select,
.is-box input.te-statement,
.is-box textarea.te-notes {
  background: rgba(0, 0, 0, 0.25);
}
</style>
