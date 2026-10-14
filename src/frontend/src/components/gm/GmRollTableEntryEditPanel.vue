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
        <span class="eep-subtitle">Bound variables</span>
        <BoundVariablesEditor
          v-model="form.boundVariables"
          :variables="tableScope || {}"
          :types="declaredTypes"
          :reserved="reservedNames"
        />
        <p class="eep-hint">
          Names <em>this row</em> resolves once it has been picked — a location, a rival,
          a value no other row has. Refer to one as <code>{name}</code> in this row's
          effects and in the life path binding's effects for this row. A name the table
          already declares (or one an earlier row above already declared) is refused and
          shows in red — the existing value wins. The row's own
          <strong>conditions</strong> cannot read these: they are checked before a row is
          chosen, so they see the <em>table's</em> names instead.
        </p>
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

      <!-- No Save button (B211's convention; the human 2026-10-13). Opened from the
           table panel, this row's edits land in that panel's live draft on every
           keystroke and its own auto-save writes them. Opened on its own (a window
           restored after a reload) there is no parent to save, so this panel
           auto-saves the table itself. Either way the author never presses Save. -->
      <div class="eep-save-state" :class="{ 'eep-save-error': !!error }">
        <span v-if="error" class="eep-save-msg">{{ error }}</span>
        <span v-else-if="saving" class="eep-save-msg">Saving…</span>
        <span v-else-if="savedAt" class="eep-save-msg eep-saved">Saved</span>
        <span v-else-if="draft" class="eep-save-msg">Saves with the table.</span>
        <span v-else class="eep-save-msg">Edits save as you make them.</span>
      </div>
      <div v-if="error" class="eep-error">{{ error }}</div>
    </template>
  </div>
</template>

<script setup>
import { reactive, ref, computed, inject, onMounted, onUnmounted, watch } from 'vue'
import { useRollTables } from '@/composables/useRollTables.js'
import { usePanel } from '@/composables/usePanel.js'
import { usePanelBus } from '@/composables/usePanelBus.js'
import ConditionEditor from './ConditionEditor.vue'
import EffectList from './EffectList.vue'
import BoundVariablesEditor from './BoundVariablesEditor.vue'
import GmDraftEffectPanel from './GmDraftEffectPanel.vue'
import { useBoundVariableScope } from '@/composables/useBoundVariableScope.js'

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
// The scope this row's own declarations start from: the ambient facts plus the
// table's declarations, which the engine resolves before any row is chosen
// ([[B281]]). It arrives through the spec's `context` for the same reason the row
// does — a child panel cannot inject its parent's provide.
const tableScope = inject('tableScope', null)
// Names already bound when this row's declarations resolve — the engine refuses a
// declaration that shadows one rather than rebinding it, so the editor has to show
// the collision instead of letting the author save a name that does nothing.
const reservedNames = computed(() => Object.keys(tableScope || {}))

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
  // The names this row exposes to its own effects and to the life path binding's
  // effects for this row ([[B281]]).
  boundVariables: [],
})

// This row's layer, resolved on top of the table's by the same composable the
// table panel uses — so what the editor offers is what `table_bindings()` binds.
//
// It must stay **below** `form`: the composable's watcher is `immediate`, so it
// reads `form.boundVariables` during setup, and above the declaration that is a
// temporal-dead-zone `ReferenceError` — one the build, the check scripts and the
// API tests all pass straight through. `check-path-fields.mjs` pins the order for
// exactly that reason.
const { scope: rowScope, types: declaredTypes } = useBoundVariableScope(
  computed(() => form.boundVariables),
  computed(() => tableScope || {}),
)

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
  form.boundVariables = JSON.parse(JSON.stringify(e.boundVariables || []))
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
    _suppressEdits = true
    seedFrom(draft)
    _suppressEdits = false
    return
  }

  try {
    _suppressEdits = true
    table.value = await fetchTable(props.tableId)
    seedFrom(table.value?.entries?.[props.index])
  } catch (e) {
    error.value = e?.message || 'Failed to load entry'
  } finally {
    _suppressEdits = false
  }
})

// ── Auto-save: no Save button (B211's convention, the human 2026-10-13) ──
//
// Two contracts, one rule — the author never presses Save:
//   * **with a draft** the row is written into the table panel's live entry as it is
//     edited, and *that* panel's auto-save persists it. No debounce here: these are
//     plain field assignments into a reactive object, and the network write is the
//     parent's to schedule.
//   * **without one** (a window restored after a reload) there is no parent holding
//     this row, so this panel saves the table itself — same debounce, and the same
//     flush on close so an edit made in the last moment is not lost.
let _saveTimer = null
let _suppressEdits = false
const savedAt = ref(null)

watch(
  () => form,
  () => {
    if (_suppressEdits) return
    if (draft) { writeIntoDraft(); return }
    if (!table.value) return
    savedAt.value = null
    clearTimeout(_saveTimer)
    _saveTimer = setTimeout(() => { save() }, 700)
  },
  { deep: true, flush: 'sync' },
)

onUnmounted(() => {
  offChildClose?.()
  if (_saveTimer) {
    clearTimeout(_saveTimer)
    _saveTimer = null
    save()
  }
})

// ── Effect editor (child panel) ──
// The row's effects are edited by a *child* panel, as the SFX editor's are: an
// effect is a stacked builder of unbounded height, and the list has to stay in
// view while one is edited.
function openEffectEditor(index) {
  editingEffectIndex.value = index
  panel.open({
    component: GmDraftEffectPanel,
    title: index === null ? 'Add effect' : 'Edit effect',
    props: {
      index,
      universe: universe.value,
      lifePath: lifePath.value,
    },
    // The row draft, as a live reference, through the spec's `context` — a panel
    // cannot `provide` to its own child panels. The child writes effects back
    // into this row; the table panel's auto-save is what persists it. The resolved
    // scope travels too, so this row's effects may start a path from the names it
    // exposes and from the table's ([[B281]]); it is a snapshot taken when the
    // panel opens, which is correct because declarations are edited *here*, not
    // in the child.
    context: { rowDraft: form, scopeVariables: rowScope.value },
  })
}

/** Copy the edited row into the table panel's live entry.
 *
 *  A plain assignment per field, not a spread: `draft` is the row object the table
 *  panel holds, and replacing it would detach the reference the parent is watching. */
function writeIntoDraft() {
  if (!draft) return
  draft.key = form.key || ''
  draft.costEffects = form.costEffects || []
  draft.boundVariables = form.boundVariables || []
  draft.label = form.label
  draft.description = form.description
  draft.minValue = form.minValue ?? null
  draft.maxValue = form.maxValue ?? null
  draft.weight = form.weight ?? null
  draft.tier = form.tier || ''
  draft.conditions = form.conditions
  draft.effects = form.effects
}

async function save() {
  // Draft path (opened from the unified roll-table panel): write the local form
  // back into the injected row. Nothing is persisted *here* — the table panel's own
  // auto-save writes the whole table, including this row.
  if (draft) {
    writeIntoDraft()
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
      // The row's exposed names ([[B281]]). Carried here rather than dropped for the
      // same reason `key` and `costEffects` are: the entries map below is a full
      // replace, so anything missing from this object is erased on save.
      boundVariables: form.boundVariables || [],
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
      // The table's own declarations, carried through untouched: this panel does
      // not edit them, and `RollTableInput` replaces the whole document, so
      // omitting them would erase what the fetch just read ([[B279]]). The
      // injected-draft path above writes only the *row* into the parent's live
      // entry, so the parent's own save carries these instead.
      subjectKind: table.value.subjectKind || '',
      boundVariables: (table.value.boundVariables || []).map(bv => ({
        name: bv.name || '',
        spec: bv.spec || null,
        // A **reservation** ([[B285]]) — a name with a type and no value — has to be
        // sent back by this writer too, or its whole-document save erases one it
        // never authored ([[B279]]).
        element: bv.element || '',
        cardinality: bv.cardinality || '',
      })),
      scheme: table.value.scheme,
      die: table.value.die,
      check: table.value.check
        ? { traitIds: table.value.check.traitIds || [], difficulty: table.value.check.difficulty, freeChoice: table.value.check.freeChoice }
        : null,
      entries: entries.map(e => ({
        key: e.key || '',
        costEffects: e.costEffects || [],
        boundVariables: e.boundVariables || [],
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
      // No `panel.close()`: this is an auto-save now, not a commit-and-dismiss.
      savedAt.value = new Date()
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
/* The auto-save readout that replaced the Save button: information, not an action —
   and the only place a failed write can appear now. */
.eep-save-state { display: flex; align-items: center; min-height: 18px; }
.eep-save-msg { font-size: 10px; color: var(--text-dim); }
.eep-saved { color: var(--success); }
.eep-save-error .eep-save-msg {
  font-size: 11px; color: var(--danger); background: var(--danger-8);
  padding: 6px 10px; border-radius: 4px;
}
.eep-hint { margin: 4px 0 0; font-size: 10px; line-height: 1.45; color: var(--text-dim); }
.eep-hint code { font-size: 10px; color: var(--accent-pale); }
.eep-subtitle { display: block; font-size: 9px; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 4px; }
.eep-error { font-size: 11px; color: var(--danger); background: var(--danger-8); padding: 6px 10px; border-radius: 4px; }
</style>
