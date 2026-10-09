<template>
  <div class="eep-root">
    <div v-if="!ready" class="eep-loading">Loading entry…</div>
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
import { reactive, ref, computed, inject, onMounted, onUnmounted } from 'vue'
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
  // Scheme / scope for the row's fields. When a draft is injected the stored
  // table is not fetched, so the opener (the unified roll-table panel) supplies
  // these; without a draft they are read off the fetched table instead.
  scheme: { type: String, default: '' },
  universe: { type: String, default: '' },
  lifePath: { type: String, default: '' },
})

// The row, handed across by the unified roll-table panel in the spec's
// `context` (a child panel cannot inject its parent's provide — see
// PanelScope). When present, this panel edits that live draft in place and
// persists nothing itself; the table panel's own Save is the commit point.
// Without it (e.g. a window restored after a reload) it falls back to the
// stored table and its whole-table save.
const draft = inject('rowDraft', null)

const table = ref(null)
const ready = computed(() => !!draft || !!table.value)
const scheme = computed(() => table.value?.scheme || props.scheme)
const universe = computed(() => table.value?.universe || props.universe)
const lifePath = computed(() => table.value?.lifePath || props.lifePath)

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

// One place the local form is seeded from a row, whether the row came from the
// injected draft (the unified panel's live entry) or the fetched table.
function seedFrom(e) {
  if (!e) return
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

onMounted(async () => {
  // The row highlight follows the open effect. `onChildClose` is the one path
  // every *close* takes, and a detach is deliberately not a close, so a detached
  // effect panel keeps its row lit (P7.18's rule).
  offChildClose = panel.onChildClose(() => { editingEffectIndex.value = null })

  // Opened from the unified roll-table panel: the row arrives as a live draft.
  // Edit it in place and never touch the stored table — fetching it and saving
  // it back would clobber the sibling rows that panel is still holding unsaved.
  if (draft) {
    seedFrom(draft)
    return
  }

  try {
    table.value = await fetchTable(props.tableId)
    seedFrom(table.value?.entries?.[props.index])
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
      universe: universe.value,
      lifePath: lifePath.value,
    },
    // The row draft, as a live reference, through the spec's `context` — a panel
    // cannot `provide` to its own child panels. The child writes effects back
    // into this row; nothing is persisted until the row's own Save.
    context: { rowDraft: form },
  })
}

async function save() {
  // Draft path (opened from the unified roll-table panel): write the local form
  // back into the injected row and close. Nothing is persisted here — the table
  // panel's own Save writes the whole table, including this row.
  if (draft) {
    draft.key = form.key || ''
    draft.costEffects = form.costEffects || []
    draft.label = form.label
    draft.description = form.description
    draft.minValue = form.minValue ?? null
    draft.maxValue = form.maxValue ?? null
    draft.weight = form.weight ?? null
    draft.tier = form.tier || ''
    draft.conditions = form.conditions
    draft.effects = form.effects
    panel.close()
    return
  }

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
