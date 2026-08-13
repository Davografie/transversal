<template>
  <div class="eep-root">
    <div v-if="!table" class="eep-loading">Loading entry…</div>
    <template v-else>
      <div class="eep-field">
        <label>Label</label>
        <input v-model="form.label" placeholder="Entry label" />
      </div>
      <div class="eep-field">
        <label>Description</label>
        <input v-model="form.description" placeholder="Optional flavor" />
      </div>

      <div class="eep-row">
        <template v-if="table.scheme === 'RANGE'">
          <div class="eep-field"><label>Min</label><input v-model.number="form.minValue" type="number" /></div>
          <div class="eep-field"><label>Max</label><input v-model.number="form.maxValue" type="number" /></div>
        </template>
        <template v-else-if="table.scheme === 'WEIGHT'">
          <div class="eep-field"><label>Weight</label><input v-model.number="form.weight" type="number" /></div>
        </template>
        <template v-else-if="table.scheme === 'TIER'">
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
        <EffectEditor v-model="form.effects" :universe="table?.universe" />
      </div>

      <button class="eep-save" :disabled="saving" @click="save">{{ saving ? 'Saving…' : 'Save entry' }}</button>
      <div v-if="error" class="eep-error">{{ error }}</div>
    </template>
  </div>
</template>

<script setup>
import { reactive, ref, onMounted } from 'vue'
import { useApi } from '@/composables/useApi.js'
import { usePanel } from '@/composables/usePanel.js'
import { usePanelBus } from '@/composables/usePanelBus.js'
import ConditionEditor from './ConditionEditor.vue'
import EffectEditor from './EffectEditor.vue'

const panel = usePanel()
const bus = usePanelBus()
const { graphql } = useApi()

const props = defineProps({
  tableId: { type: String, required: true },
  index: { type: Number, required: true },
})

const table = ref(null)
const saving = ref(false)
const error = ref('')

const form = reactive({
  label: '',
  description: '',
  minValue: null,
  maxValue: null,
  weight: null,
  tier: '',
  conditions: [],
  effects: [],
})

onMounted(async () => {
  try {
    const data = await graphql(`query($id:ID!){rollTable(id:$id){id name universe lifePath scheme die check{traitIds difficulty freeChoice} entries{label description minValue maxValue weight tier conditions{type target value narrative} effects{timing type action target result targetScope context}}}}`, { id: props.tableId })
    table.value = data?.rollTable || null
    const e = table.value?.entries?.[props.index]
    if (e) {
      form.label = e.label || ''
      form.description = e.description || ''
      form.minValue = e.minValue ?? null
      form.maxValue = e.maxValue ?? null
      form.weight = e.weight ?? null
      form.tier = e.tier || ''
      form.conditions = JSON.parse(JSON.stringify(e.conditions || []))
      form.effects = JSON.parse(JSON.stringify(e.effects || []))
    }
  } catch (e) {
    error.value = e?.message || 'Failed to load entry'
  }
})

async function save() {
  if (!table.value) return
  saving.value = true
  error.value = ''
  try {
    const updatedEntry = {
      label: form.label,
      description: form.description,
      minValue: form.minValue ?? null,
      maxValue: form.maxValue ?? null,
      weight: form.weight ?? null,
      tier: form.tier || null,
      conditions: form.conditions,
      effects: form.effects,
    }
    const entries = [...table.value.entries]
    entries[props.index] = updatedEntry

    const input = {
      id: table.value.id,
      name: table.value.name,
      universe: table.value.universe,
      lifePath: table.value.lifePath || null,
      scheme: table.value.scheme,
      die: table.value.die,
      check: table.value.check
        ? { traitIds: table.value.check.traitIds || [], difficulty: table.value.check.difficulty, freeChoice: table.value.check.freeChoice }
        : null,
      entries: entries.map(e => ({
        label: e.label,
        description: e.description,
        minValue: e.minValue ?? null,
        maxValue: e.maxValue ?? null,
        weight: e.weight ?? null,
        tier: e.tier || null,
        conditions: e.conditions || [],
        effects: e.effects || [],
      })),
    }

    const data = await graphql(`mutation($input:RollTableInput!){saveRollTable(input:$input){id}}`, { input })
    if (data?.saveRollTable?.id) {
      bus.emit('lifepath-saved', { id: table.value.lifePath })
      panel.close()
    } else {
      error.value = 'Save failed'
    }
  } catch (e) {
    error.value = e?.message || 'Save failed'
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.eep-root { padding: 0; display: flex; flex-direction: column; gap: 8px; }
.eep-loading { font-size: 11px; color: var(--text-dim); padding: 12px 0; text-align: center; }
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
.eep-save { background: var(--success); color: #0a0a0f; font-weight: 600; padding: 7px 12px; border-radius: 6px; border: none; cursor: pointer; font-size: 12px; }
.eep-save:disabled { opacity: 0.5; cursor: default; }
.eep-error { font-size: 11px; color: var(--danger); background: rgba(212,64,64,0.08); padding: 6px 10px; border-radius: 4px; }
</style>
