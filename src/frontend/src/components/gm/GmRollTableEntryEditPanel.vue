<template>
  <div class="eep-root">
    <div class="eep-field">
      <label>Label</label>
      <input v-model="form.label" placeholder="Entry label" />
    </div>
    <div class="eep-field">
      <label>Description</label>
      <input v-model="form.description" placeholder="Optional flavor" />
    </div>

    <div class="eep-row">
      <template v-if="scheme === 'RANGE'">
        <div class="eep-field"><label>Min</label><input v-model.number="form.minValue" type="number" /></div>
        <div class="eep-field"><label>Max</label><input v-model.number="form.maxValue" type="number" /></div>
      </template>
      <template v-else-if="scheme === 'WEIGHT'">
        <div class="eep-field"><label>Weight</label><input v-model.number="form.weight" type="number" /></div>
      </template>
      <template v-else-if="scheme === 'TIER'">
        <div class="eep-field">
          <label>Tier</label>
          <select v-model="form.tier">
            <option value="">— tier —</option>
            <option value="FAIL">Fail</option>
            <option value="MARGINAL">Marginal</option>
            <option value="SUCCESS">Success</option>
            <option value="EXCEPTIONAL">Exceptional</option>
            <option value="PERFECT">Perfect</option>
          </select>
        </div>
      </template>
    </div>

    <div class="eep-subsection">
      <span class="eep-subtitle">Conditions</span>
      <ConditionEditor v-model="form.conditions" />
    </div>

    <div class="eep-subsection">
      <span class="eep-subtitle">Effects</span>
      <EffectEditor v-model="form.effects" />
    </div>

    <button class="eep-done" @click="done">Done</button>
  </div>
</template>

<script setup>
import { reactive } from 'vue'
import { usePanel } from '@/composables/usePanel.js'
import { usePanelBus } from '@/composables/usePanelBus.js'
import ConditionEditor from './ConditionEditor.vue'
import EffectEditor from './EffectEditor.vue'

const panel = usePanel()
const bus = usePanelBus()

const props = defineProps({
  tableId: { type: String, required: true },
  index: { type: Number, required: true },
  scheme: { type: String, default: 'INDEX' },
  entry: { type: Object, default: () => ({}) },
})

const form = reactive({
  label: props.entry.label || '',
  description: props.entry.description || '',
  minValue: props.entry.minValue ?? null,
  maxValue: props.entry.maxValue ?? null,
  weight: props.entry.weight ?? null,
  tier: props.entry.tier || '',
  conditions: JSON.parse(JSON.stringify(props.entry.conditions || [])),
  effects: JSON.parse(JSON.stringify(props.entry.effects || [])),
})

function done() {
  bus.emit('entry-edited', {
    tableId: props.tableId,
    index: props.index,
    entry: {
      label: form.label,
      description: form.description,
      minValue: form.minValue ?? null,
      maxValue: form.maxValue ?? null,
      weight: form.weight ?? null,
      tier: form.tier || null,
      conditions: form.conditions,
      effects: form.effects,
    },
  })
  panel.close()
}
</script>

<style scoped>
.eep-root { padding: 0; display: flex; flex-direction: column; gap: 8px; }
.eep-field { display: flex; flex-direction: column; gap: 3px; flex: 1; }
.eep-field label { font-size: 9px; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.5px; }
.eep-field input, .eep-field select {
  font-size: 12px; padding: 6px 8px;
  background: rgba(255,255,255,0.06); color: var(--text);
  border: 1px solid rgba(255,255,255,0.1); border-radius: 6px;
  font-family: inherit; width: 100%; box-sizing: border-box;
}
.eep-row { display: flex; gap: 8px; }
.eep-subsection { margin-top: 2px; }
.eep-subtitle { display: block; font-size: 9px; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 4px; }
.eep-done { background: var(--success); color: #0a0a0f; font-weight: 600; padding: 7px 12px; border-radius: 6px; border: none; cursor: pointer; font-size: 12px; }
</style>
