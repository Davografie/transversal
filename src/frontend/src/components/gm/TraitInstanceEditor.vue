<template>
  <div class="trait-instance-editor">
    <div class="tie-field">
      <label>Die</label>
      <div v-if="allowVariable" class="tie-die-mode">
        <button type="button" :class="{ active: !isVariable }" @click="setVariableMode(false)">Die</button>
        <button type="button" :class="{ active: isVariable }" @click="setVariableMode(true)">Variable</button>
      </div>
      <DiePicker v-if="!isVariable" :model-value="die" @update:model-value="emit('update:die', $event)" />
      <select v-else :value="die" @change="emit('update:die', $event.target.value)">
        <option v-for="v in variableOptions" :key="v" :value="v">{{ v }}</option>
      </select>
    </div>

    <div class="tie-field">
      <label>Type</label>
      <button type="button" class="polarity-toggle" :class="{ 'is-positive': !negative }" @click="emit('update:negative', !negative)">
        {{ negative ? 'negative' : 'positive' }}
      </button>
    </div>

    <div class="tie-field">
      <label>Rating Type</label>
      <select :value="ratingType" @change="emit('update:ratingType', $event.target.value)">
        <option value="static">Static</option>
        <option value="resource">Resource</option>
        <option value="challenge">Challenge</option>
        <option value="empty">Empty</option>
      </select>
    </div>

    <div class="tie-field">
      <label>Statement</label>
      <input :value="statement" type="text" placeholder="Distinction statement…" @input="emit('update:statement', $event.target.value)" />
    </div>

    <div class="tie-field">
      <label>Notes</label>
      <textarea :value="notes" placeholder="Notes…" @input="emit('update:notes', $event.target.value)" />
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import DiePicker from '@/components/DiePicker.vue'

const props = defineProps({
  die: { type: String, default: '' },
  negative: { type: Boolean, default: false },
  ratingType: { type: String, default: 'static' },
  statement: { type: String, default: '' },
  notes: { type: String, default: '' },
  allowVariable: { type: Boolean, default: false },
  variables: { type: Array, default: () => [] },
})

const emit = defineEmits(['update:die', 'update:negative', 'update:ratingType', 'update:statement', 'update:notes'])

// Explicit mode so toggling to Variable sticks (empty die ≠ die mode).
const isVariable = ref((props.die || '').startsWith('{'))

watch(() => props.die, (d) => {
  isVariable.value = (d || '').startsWith('{')
})

const variableOptions = computed(() => {
  const opts = (props.variables || []).map(v => `{${v}}`)
  const cur = props.die
  if (cur && cur.startsWith('{') && !opts.includes(cur)) opts.push(cur)
  return opts
})

function setVariableMode(variable) {
  isVariable.value = variable
  if (variable) {
    if (!(props.die || '').startsWith('{')) emit('update:die', variableOptions.value[0] || '{effect_die}')
  } else {
    if ((props.die || '').startsWith('{')) emit('update:die', 'd6')
  }
}
</script>

<style scoped>
.trait-instance-editor {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 10px;
  border: 1px solid var(--overlay-10);
  border-radius: 8px;
}
.tie-field { display: flex; flex-direction: column; gap: 4px; }
.tie-field > label {
  font-size: 10px;
  color: var(--text-dim);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}
.tie-field input, .tie-field textarea, .tie-field select {
  width: 100%;
  padding: 6px 8px;
  background: rgba(0, 0, 0, 0.25);
  border: 1px solid var(--overlay-12);
  border-radius: 6px;
  color: var(--text);
  font-size: 12px;
}
.tie-field textarea { min-height: 48px; resize: vertical; }
.tie-die-mode { display: flex; gap: 4px; }
.tie-die-mode button {
  font-size: 10px;
  padding: 3px 9px;
  border-radius: 4px;
  background: var(--overlay-4);
  border: 1px solid var(--overlay-12);
  color: var(--text-dim);
  cursor: pointer;
}
.tie-die-mode button.active { background: var(--accent-20); border-color: var(--accent); color: var(--accent); }
.polarity-toggle {
  align-self: flex-start;
  padding: 4px 12px;
  border-radius: 999px;
  border: 1px solid var(--text-dim);
  background: transparent;
  color: var(--text-dim);
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  cursor: pointer;
}
.polarity-toggle.is-positive { border-color: var(--accent); color: var(--accent); background: var(--overlay-6); }
</style>
