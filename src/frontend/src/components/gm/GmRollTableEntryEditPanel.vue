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
        <!-- The list stays in the row; each effect's form opens in a *child*
             panel (as the SFX editor's does), because an effect is a stacked
             builder of unbounded height and the list has to stay in view. -->
        <EffectList
          :model-value="form.effects"
          :editing-index="editingEffectIndex"
          @update:model-value="form.effects = $event"
          @add="openEffectEditor(null)"
          @edit="openEffectEditor"
        />
      </div>

      <Button class="eep-save" variant="success" solid :loading="saving" :disabled="saving" @click="save">{{ saving ? 'Saving…' : 'Save entry' }}</Button>
      <div v-if="error" class="eep-error">{{ error }}</div>
    </template>
  </div>
</template>

<script setup>
import { reactive, ref, onMounted, onUnmounted } from 'vue'
import { useRollTables } from '@/composables/useRollTables.js'
import { usePanel } from '@/composables/usePanel.js'
import { usePanelBus } from '@/composables/usePanelBus.js'
import ConditionEditor from './ConditionEditor.vue'
import EffectList from './EffectList.vue'
import GmRollTableEntryEffectPanel from './GmRollTableEntryEffectPanel.vue'
import Button from '@/components/ui/Button.vue'

const panel = usePanel()
const bus = usePanelBus()
const { fetchTable, saveRollTable } = useRollTables()

const props = defineProps({
  tableId: { type: String, required: true },
  index: { type: Number, required: true },
})

const table = ref(null)
const saving = ref(false)
const error = ref('')
const editingEffectIndex = ref(null)
let offChildClose = null

const form = reactive({
  key: '',
  label: '',
  description: '',
  minValue: null,
  maxValue: null,
  weight: null,
  tier: '',
  conditions: [],
  costEffects: [],
  effects: [],
})

onMounted(async () => {
  // The row highlight follows the open effect. `onChildClose` is the one path
  // every *close* takes, and a detach is deliberately not a close, so a detached
  // effect panel keeps its row lit (P7.18's rule).
  offChildClose = panel.onChildClose(() => { editingEffectIndex.value = null })
  try {
    table.value = await fetchTable(props.tableId)
    const e = table.value?.entries?.[props.index]
    if (e) {
      form.key = e.key || ''
      form.label = e.label || ''
      form.description = e.description || ''
      form.minValue = e.minValue ?? null
      form.maxValue = e.maxValue ?? null
      form.weight = e.weight ?? null
      form.tier = e.tier || ''
      form.conditions = JSON.parse(JSON.stringify(e.conditions || []))
      form.effects = JSON.parse(JSON.stringify(e.effects || []))
      form.costEffects = JSON.parse(JSON.stringify(e.costEffects || []))
    }
  } catch (e) {
    error.value = e?.message || 'Failed to load entry'
  }
})

onUnmounted(() => { offChildClose?.() })

// ── Effect editor (child panel) ──
// The row's effects are edited by a *child* panel, as the SFX editor's are: an
// effect is a stacked builder of unbounded height, and the list has to stay in
// view while one is edited.
function openEffectEditor(index) {
  editingEffectIndex.value = index
  panel.open({
    component: GmRollTableEntryEffectPanel,
    title: index === null ? 'Add effect' : 'Edit effect',
    props: {
      index,
      universe: table.value?.universe || '',
      lifePath: table.value?.lifePath || '',
    },
    // The row draft, as a live reference, through the spec's `context` — a panel
    // cannot `provide` to its own child panels. The child writes effects back
    // into this row; nothing is persisted until the row's own Save.
    context: { rowDraft: form },
  })
}

async function save() {
  if (!table.value) return
  saving.value = true
  error.value = ''
  try {
    const updatedEntry = {
      // The row's identity travels through the editor untouched: a binding names
      // it, so dropping it here would orphan every life path bound to this row.
      // `costEffects` is preserved for the same reason -- this panel does not
      // edit them, and the entries map below is a full replace.
      key: form.key || '',
      costEffects: form.costEffects || [],
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
        key: e.key || '',
        costEffects: e.costEffects || [],
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
  background: var(--overlay-6); color: var(--text);
  border: 1px solid var(--overlay-10); border-radius: 6px;
  font-family: inherit; width: 100%; box-sizing: border-box;
}
.eep-row { display: flex; gap: 8px; }
.eep-subsection { margin-top: 2px; }
.eep-subtitle { display: block; font-size: 9px; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 4px; }
.eep-error { font-size: 11px; color: var(--danger); background: var(--danger-8); padding: 6px 10px; border-radius: 4px; }
</style>
