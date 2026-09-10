<template>
  <div class="rte-root">
    <div class="rte-field">
      <label>Name</label>
      <input v-model="form.name" placeholder="Table name…" />
    </div>

    <div class="rte-row">
      <div class="rte-field">
        <label>Universe</label>
        <GmScopePicker
          v-model="form.universe"
          :options="universeOptions"
          empty-label="Fundamental (all universes)"
          placeholder="Select universe…"
        />
      </div>
      <div class="rte-field">
        <label>Life path</label>
        <GmScopePicker
          v-model="form.lifePath"
          :options="lifePathOptions"
          empty-label="Shared (no path)"
          placeholder="Select life path…"
        />
      </div>
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
      <GmList
        :items="form.entries"
        reorderable
        drag-handle
        empty-text="No entries"
        @reorder="onReorderEntry"
      >
        <template #item="{ item: e, index: i }">
          <div class="rte-entry-body">
            <div class="rte-entry-head">
              <span class="rte-entry-index">#{{ i + 1 }}</span>
              <span class="rte-spacer"></span>
              <Button class="rte-mini rte-del" variant="danger-ghost" size="sm" @click.stop="removeEntry(i)">✕</Button>
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
        </template>
      </GmList>
      <Button class="rte-add" variant="secondary" @click="addEntry">＋ Add entry</Button>
    </div>

    <Button class="rte-save" variant="success" solid :loading="saving" :disabled="saving" @click="save">{{ saving ? 'Saving…' : 'Save roll table' }}</Button>
    <div v-if="error" class="rte-error">{{ error }}</div>
  </div>
</template>

<script setup>
import { reactive, ref, onMounted } from 'vue'
import { useApi } from '@/composables/useApi.js'
import { useRollTables } from '@/composables/useRollTables.js'
import { usePanel } from '@/composables/usePanel.js'
import { usePanelBus } from '@/composables/usePanelBus.js'
import GmList from '@/components/ui/GmList.vue'
import Button from '@/components/ui/Button.vue'
import GmScopePicker from './GmScopePicker.vue'

const panel = usePanel()
const bus = usePanelBus()
const { graphql } = useApi()
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
const universeOptions = ref([])
const lifePathOptions = ref([])

async function loadScopeOptions() {
  try {
    const [unis, lps] = await Promise.all([
      graphql(`query($type: EntityType){ entities(type: $type){ id name currentUniverse } }`, { type: 'UNIVERSE' }),
      graphql(`{ lifePaths { id name } }`),
    ])
    universeOptions.value = (unis?.entities || []).map(u => ({ value: u.currentUniverse, label: u.name }))
    lifePathOptions.value = (lps?.lifePaths || []).map(lp => ({ value: lp.id, label: lp.name }))
  } catch { /* leave empty */ }
}

onMounted(async () => {
  loadScopeOptions()
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

function onReorderEntry(from, to) {
  const [moved] = form.entries.splice(from, 1)
  form.entries.splice(to, 0, moved)
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
.rte-field input, .rte-field select, .rte-entry-body input, .rte-entry-body select {
  font-size: 12px; padding: 6px 8px;
  background: var(--overlay-6); color: var(--text);
  border: 1px solid var(--overlay-10); border-radius: 6px;
  font-family: inherit; width: 100%; box-sizing: border-box;
}
.rte-row { display: flex; gap: 8px; }
.rte-check { background: var(--overlay-4); border: 1px solid var(--overlay-8); border-radius: 6px; padding: 8px; display: flex; flex-direction: column; gap: 6px; }
.rte-check-toggle { font-size: 11px; color: var(--text); display: flex; align-items: center; gap: 6px; cursor: pointer; }
.rte-subsection { margin-top: 4px; }
.rte-subtitle { display: block; font-size: 9px; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 4px; }
.rte-detail { font-size: 10px; color: var(--text-dim); }
.rte-entry-body { flex: 1; display: flex; flex-direction: column; gap: 5px; min-width: 0; }
.rte-entry-head { display: flex; align-items: center; gap: 4px; }
.rte-entry-index { font-size: 9px; color: var(--text-dim); }
.rte-spacer { flex: 1; }
.rte-num { width: 70px; }
.rte-error { font-size: 11px; color: var(--danger); background: var(--danger-8); padding: 6px 10px; border-radius: 4px; }
</style>
