<template>
  <div class="rte-root">
    <div class="rte-field">
      <label>Name</label>
      <input v-model="form.name" placeholder="Table name…" />
    </div>

    <div class="rte-row">
      <div class="rte-field">
        <label>Scheme</label>
        <select v-model="form.scheme">
          <option value="RANGE">Range (min–max)</option>
          <option value="WEIGHT">Weight</option>
          <option value="TIER">Tier</option>
          <option value="INDEX">Index (ordered)</option>
        </select>
      </div>
      <div class="rte-field">
        <label>Roll source</label>
        <select v-model="form.rollSource">
          <option value="FIXED_DIE">Fixed die</option>
          <option value="TRAIT_DICE">Trait dice</option>
        </select>
      </div>
    </div>

    <div class="rte-row">
      <div class="rte-field" v-if="form.rollSource === 'FIXED_DIE'">
        <label>Die</label>
        <select v-model="form.die">
          <option v-for="d in ['D4','D6','D8','D10','D12']" :key="d" :value="d">{{ d }}</option>
        </select>
      </div>
      <div class="rte-field" v-else>
        <label>Trait dice count</label>
        <input v-model.number="form.traitDiceCount" type="number" min="1" />
      </div>
    </div>

    <p v-if="form.rollSource === 'TRAIT_DICE'" class="rte-detail">
      The player picks trait{{ form.traitDiceCount === 1 ? '' : 's' }} they have; their roll selects the entry.
      Applies to Range, Tier, and Index tables.
    </p>

    <div class="rte-subsection">
      <span class="rte-subtitle">Entries</span>
      <div v-if="!form.entries.length" class="rte-detail">No entries</div>
      <div v-for="(e, i) in form.entries" :key="i" class="rte-entry">
        <div class="rte-entry-head">
          <span class="rte-entry-index">#{{ i + 1 }}</span>
          <span class="rte-spacer"></span>
          <button class="rte-mini" :disabled="i === 0" @click="move(i, -1)">↑</button>
          <button class="rte-mini" :disabled="i === form.entries.length - 1" @click="move(i, 1)">↓</button>
          <button class="rte-mini rte-del" @click="removeEntry(i)">✕</button>
        </div>
        <input v-model="e.label" placeholder="Entry label" />
        <div class="rte-row">
          <template v-if="form.scheme === 'RANGE'">
            <input v-model.number="e.minValue" type="number" placeholder="min" class="rte-num" />
            <input v-model.number="e.maxValue" type="number" placeholder="max" class="rte-num" />
          </template>
          <template v-else-if="form.scheme === 'WEIGHT'">
            <input v-model.number="e.weight" type="number" placeholder="weight" class="rte-num" />
          </template>
          <template v-else-if="form.scheme === 'TIER'">
            <select v-model="e.tier">
              <option value="">— tier —</option>
              <option value="FAIL">Fail</option>
              <option value="MARGINAL">Marginal</option>
              <option value="SUCCESS">Success</option>
              <option value="EXCEPTIONAL">Exceptional</option>
              <option value="PERFECT">Perfect</option>
            </select>
          </template>
        </div>
      </div>
      <button class="rte-add" @click="addEntry">＋ Add entry</button>
    </div>

    <button class="rte-save" :disabled="saving" @click="save">{{ saving ? 'Saving…' : 'Save roll table' }}</button>
    <div v-if="error" class="rte-error">{{ error }}</div>
  </div>
</template>

<script setup>
import { reactive, ref, onMounted } from 'vue'
import { useRollTables } from '@/composables/useRollTables.js'
import { usePanel } from '@/composables/usePanel.js'
import { usePanelBus } from '@/composables/usePanelBus.js'

const panel = usePanel()
const bus = usePanelBus()
const { fetchTable, saveRollTable } = useRollTables()

const props = defineProps({
  tableId: { type: String, default: '' },
  lifePathId: { type: String, default: '' },
  universe: { type: String, default: '' },
})

const form = reactive({
  id: props.tableId || '',
  name: '',
  universe: props.universe || '',
  lifePath: props.lifePathId || '',
  scheme: 'INDEX',
  rollSource: 'FIXED_DIE',
  traitDiceCount: 1,
  die: 'D6',
  entries: [],
})

const saving = ref(false)
const error = ref('')

onMounted(async () => {
  if (!props.tableId) return
  try {
    const t = await fetchTable(props.tableId)
    if (!t) return
    form.id = t.id
    form.name = t.name
    form.universe = t.universe
    form.lifePath = t.lifePath || props.lifePathId || ''
    form.scheme = t.scheme
    form.rollSource = t.rollSource || 'FIXED_DIE'
    form.traitDiceCount = t.traitDiceCount ?? 1
    form.die = t.die
    form.entries = (t.entries || []).map(e => ({
      label: e.label,
      description: e.description,
      minValue: e.minValue,
      maxValue: e.maxValue,
      weight: e.weight,
      tier: e.tier || '',
      conditions: e.conditions || [],
      effects: e.effects || [],
    }))
  } catch {}
})

function addEntry() {
  form.entries.push({ label: '', description: '', minValue: null, maxValue: null, weight: null, tier: '', conditions: [], effects: [] })
}

function removeEntry(i) {
  form.entries.splice(i, 1)
}

function move(i, dir) {
  const j = i + dir
  if (j < 0 || j >= form.entries.length) return
  const list = [...form.entries]
  ;[list[i], list[j]] = [list[j], list[i]]
  form.entries = list
}

async function save() {
  saving.value = true
  error.value = ''
  try {
    const input = {
      id: form.id,
      name: form.name,
      universe: form.universe,
      lifePath: form.lifePath || null,
      scheme: form.scheme,
      rollSource: form.rollSource,
      traitDiceCount: form.traitDiceCount ?? 1,
      die: form.die,
      check: null,
      entries: form.entries.map(e => ({
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
    const result = await saveRollTable(input)
    if (result?.id) {
      bus.emit('lifepath-saved', { id: form.lifePath })
      panel.close()
    }
  } catch (e) {
    error.value = e?.message || 'Save failed'
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.rte-root { padding: 0; display: flex; flex-direction: column; gap: 8px; }
.rte-field { display: flex; flex-direction: column; gap: 3px; flex: 1; }
.rte-field label { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.5px; }
.rte-field input, .rte-field select, .rte-entry input, .rte-entry select {
  font-size: 12px; padding: 6px 8px;
  background: rgba(255,255,255,0.06); color: var(--text);
  border: 1px solid rgba(255,255,255,0.1); border-radius: 6px;
  font-family: inherit; width: 100%; box-sizing: border-box;
}
.rte-row { display: flex; gap: 8px; }
.rte-check { background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.08); border-radius: 6px; padding: 8px; display: flex; flex-direction: column; gap: 6px; }
.rte-check-toggle { font-size: 11px; color: var(--text); display: flex; align-items: center; gap: 6px; cursor: pointer; }
.rte-subsection { margin-top: 4px; }
.rte-subtitle { display: block; font-size: 9px; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 4px; }
.rte-detail { font-size: 10px; color: var(--text-dim); }
.rte-entry { background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.08); border-radius: 6px; padding: 6px; margin-bottom: 6px; display: flex; flex-direction: column; gap: 5px; }
.rte-entry-head { display: flex; align-items: center; gap: 4px; }
.rte-entry-index { font-size: 9px; color: var(--text-dim); }
.rte-spacer { flex: 1; }
.rte-mini { background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.1); color: var(--text); border-radius: 4px; cursor: pointer; font-size: 10px; padding: 2px 6px; }
.rte-mini:disabled { opacity: 0.3; cursor: default; }
.rte-del { color: var(--danger); }
.rte-num { width: 70px; }
.rte-add { font-size: 11px; padding: 5px 10px; background: rgba(0,200,150,0.08); border: 1px dashed rgba(0,200,150,0.25); border-radius: 4px; color: var(--accent); cursor: pointer; }
.rte-save { background: var(--success); color: #0a0a0f; font-weight: 600; padding: 7px 12px; border-radius: 6px; border: none; cursor: pointer; font-size: 12px; }
.rte-save:disabled { opacity: 0.5; cursor: default; }
.rte-error { font-size: 11px; color: var(--danger); background: rgba(212,64,64,0.08); padding: 6px 10px; border-radius: 4px; }
</style>
