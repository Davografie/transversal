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
        <!-- The notation, not a fixed list: the ladder's dice plus any dN a table
             wants (d20, d100, …). A datalist keeps the common ones one click away
             without forbidding the rest. -->
        <input v-model="form.die" list="rte-dice" placeholder="d6" spellcheck="false" />
        <datalist id="rte-dice">
          <option v-for="d in TABLE_DICE" :key="d" :value="d" />
        </datalist>
      </div>
      <div class="rte-field" v-else>
        <label>Trait dice count</label>
        <input v-model.number="form.traitDiceCount" type="number" min="1" />
      </div>
    </div>

    <p v-if="form.rollSource === 'FIXED_DIE'" class="rte-detail">
      A <strong>repeated digit</strong> reads dice as digits rather than one wide die:
      a <strong>d66</strong> is two d6 — 11–66, never 7 or 17 — and a <strong>d88</strong>
      is two d8, 11–88. Write a Range table's entries against that spread (11–88), not 1–88.
    </p>

    <p v-if="form.rollSource === 'TRAIT_DICE'" class="rte-detail">
      The player picks trait{{ form.traitDiceCount === 1 ? '' : 's' }} they have; their roll selects the entry.
      Applies to Range, Tier, and Index tables.
    </p>

    <!-- Values the table is about, named *before* a row's conditions run, and
         resolved into the scope that row's conditions and effects use. Placed
         with the scheme/die fields, above the entries, because it is a property
         of the table rather than of any one row. -->
    <div class="rte-subsection">
      <span class="rte-subtitle">Bound variables</span>
      <BoundVariablesEditor
        v-model="form.boundVariables"
        :variables="ambientVariables"
        :types="declaredTypes"
      />
      <p class="rte-detail">
        Names this table resolves for itself, once per roll, in order, before a row's
        conditions. Refer to one as <code>{name}</code>; a later row may start from an
        earlier one. A path may also read the table's own facts: the faction the table
        is about starts a path, while <code>{roll}</code>, <code>{entry_tier}</code>,
        <code>{entry_effect_die}</code> and the entry's band are values a filter can
        compare against. Not <em>select source</em> — a table's bindings are resolved
        before any source exists.
      </p>
    </div>

    <div class="rte-subsection">
      <span class="rte-subtitle">Entries</span>
      <!-- Why a connector column is (or is not) shown: the table was opened
           without a path, the path does not wrap it, or — wrapping it twice —
           which of the steps is being edited. -->
      <p v-if="pathHint" class="rte-detail rte-connector-hint">{{ pathHint }}</p>
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
              <!-- The row body is all inputs and a drag handle, so the entry
                   editor opens from a button rather than a row click. -->
              <Button class="rte-edit" variant="neutral" size="sm" title="Edit entry details, conditions and effects" @click.stop="openEntry(i)">✎</Button>
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

            <!-- The life-path connector: everything this row means to the path
                 that wraps the table — its binding (a move, an exit, or the term
                 ending), whether taking it enrols, and the delta it applies on
                 top of the row's own effects. Absent unless the panel was opened
                 with a path that wraps this table. -->
            <div v-if="connectorEnabled" class="rte-connector">
              <template v-if="bindingFor(i)">
                <div class="rte-connector-read">
                  <span class="rte-connector-label">Binding</span>
                  <span class="rte-connector-dest">{{ connectorTextFor(i) }}</span>
                </div>

                <div class="rte-row">
                  <div class="rte-field">
                    <label>Next</label>
                    <GmScopePicker
                      v-model="bindingFor(i).next"
                      :options="stepOptions"
                      empty-label="Leave the path"
                      placeholder="Next step…"
                    />
                  </div>
                  <!-- `next` and `exitKind` are one or the other: a move needs no
                       exit, and an exit is only what leaving means. -->
                  <template v-if="!bindingFor(i).next">
                    <div class="rte-field">
                      <label>Exit</label>
                      <select v-model="bindingFor(i).exitKind" @change="onExitKind(bindingFor(i))">
                        <option value="">Simply ends</option>
                        <option value="muster">Muster</option>
                        <option value="force_muster">Force muster</option>
                        <option value="draft">Draft</option>
                      </select>
                    </div>
                    <div v-if="bindingFor(i).exitKind === 'draft'" class="rte-field">
                      <label>Draft to</label>
                      <GmScopePicker
                        v-model="bindingFor(i).exitPath"
                        :options="lifePathOptions"
                        empty-label="Select path…"
                        placeholder="Life path…"
                      />
                    </div>
                  </template>
                </div>

                <label class="rte-enroll">
                  <input type="checkbox" v-model="bindingFor(i).enroll" />
                  Taking this row enrols the character in the path
                </label>

                <div class="rte-binding-effects">
                  <span class="rte-subtitle">Binding effects</span>
                  <span class="rte-detail">Applied after the row's own effects.</span>
                  <!-- The scope a binding effect may start a path from: the table's
                       names (ambient + its declarations), plus **this row's** own
                       declarations — which is what lets a path consume the names
                       the row exposes ([[B281]]). Resolved inside the editor, per
                       row, in the engine's own order. -->
                  <EffectEditor
                    v-model="bindingFor(i).effects"
                    :universe="bindingUniverse"
                    :life-path="bindingLifePath"
                    :scope-variables="tableScope"
                    :scope-declarations="(form.entries[i] || {}).boundVariables || []"
                  />
                </div>

                <Button variant="danger-ghost" size="sm" @click="removeBinding(i)">Remove binding</Button>
              </template>

              <div v-else class="rte-row-pass">
                <span class="rte-detail">Passes through to the step's default.</span>
                <Button variant="secondary" size="sm" @click="addBinding(i)">Bind row</Button>
              </div>
            </div>

            <!-- What the row does, folded in from the read-only panel it
                 replaced: conditions and effects are edited in the entry editor
                 (the ✎ above), so the list shows a summary of them rather than
                 a second copy of the forms. -->
            <div v-if="e.conditions?.length || e.effects?.length" class="rte-entry-summary">
              <span v-for="(eff, ei) in e.effects" :key="ei" class="rte-effect">{{ effectSummary(eff) }}</span>
              <span v-for="(c, ci) in e.conditions" :key="'c' + ci" class="rte-cond">if {{ conditionSummary(c) }}</span>
            </div>
          </div>
        </template>
      </GmList>
      <Button class="rte-add" variant="secondary" @click="addEntry">＋ Add entry</Button>
    </div>

    <!-- No Save button: every edit persists on its own (B211's convention, the
         human 2026-10-13). What replaces it is the *feedback* — the SFX panel's
         button doubled as this readout, and with the button gone the author needs
         somewhere to see that the write landed, and that it failed if it did. -->
    <div class="rte-save-state" :class="{ 'rte-save-error': !!error }">
      <span v-if="error" class="rte-save-msg">{{ error }}</span>
      <span v-else-if="saving" class="rte-save-msg">Saving…</span>
      <span v-else-if="savedAt" class="rte-save-msg rte-saved">Saved</span>
      <span v-else class="rte-save-msg">Edits save as you make them.</span>
    </div>
  </div>
</template>

<script setup>
import { reactive, ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useApi } from '@/composables/useApi.js'
import { useRollTables } from '@/composables/useRollTables.js'
import { useLifePaths } from '@/composables/useLifePaths.js'
import { useTraitsConfig } from '@/composables/useTraitsConfig.js'
import { useEffectActions } from '@/composables/useEffectActions.js'
import { useBoundVariableScope } from '@/composables/useBoundVariableScope.js'
import { ROLL_TABLE_AMBIENT_VARIABLES } from '@/composables/rollTableScope.js'
import { usePanel } from '@/composables/usePanel.js'
import { usePanelBus } from '@/composables/usePanelBus.js'
import { rowKey, connectorText } from '@/composables/lifePathConnector.js'
import GmList from '@/components/ui/GmList.vue'
import Button from '@/components/ui/Button.vue'
import GmScopePicker from './GmScopePicker.vue'
import EffectEditor from './EffectEditor.vue'
import BoundVariablesEditor from './BoundVariablesEditor.vue'
import GmRollTableEntryEditPanel from './GmRollTableEntryEditPanel.vue'

const panel = usePanel()
const bus = usePanelBus()
const { graphql } = useApi()
const { fetchTable, saveRollTable, allTableNames, fetchAllTableNames } = useRollTables()
const { fetchLifePath, saveLifePath } = useLifePaths()

const props = defineProps({
  tableId: { type: String, default: '' },
  lifePathId: { type: String, default: '' },
  // The step wrapping this table — a path may wrap the same table twice, so the
  // opener passes the one it means. Absent, the first match is edited and the
  // panel says which.
  stepId: { type: String, default: '' },
  universe: { type: String, default: '' },
})

//: Suggestions for the die field — the Cortex ladder plus the dice tables
//: actually reach for. Any `dN` (or repeated-digit read) is valid; this is a
//: shortcut, not the rule.
const TABLE_DICE = ['d4', 'd6', 'd8', 'd10', 'd12', 'd20', 'd66', 'd88', 'd100']

const form = reactive({
  id: props.tableId || '',
  name: '',
  universe: props.universe || '',
  lifePath: props.lifePathId || '',
  // The table's declared subject kind — what it may be rolled *for*
  // ([[B269]]). No UI authors it yet, but it is table-level, so the round trip
  // must carry it or a save from here blanks it ([[B279]]).
  subjectKind: '',
  scheme: 'INDEX',
  rollSource: 'FIXED_DIE',
  traitDiceCount: 1,
  die: 'd6',
  // A TIER table's dice-pool check (trait ids / difficulty / free choice). It has
  // no editor here, but it is part of the document: `check: null` on save would
  // wipe it, which is the same erasure as `boundVariables` below ([[B279]]) --
  // and two live tables (`rt-verdant-survive`, `rt-ironroots-test`) carry one.
  check: null,
  // The names the table resolves for itself, before a row's conditions. Read
  // back and sent as `{ name, spec }`, the same shape an SFX uses.
  boundVariables: [],
  entries: [],
})

const saving = ref(false)
const error = ref('')
const universeOptions = ref([])
const lifePathOptions = ref([])

// ── Row summaries ─────────────────────────────────────
// Conditions and effects are edited in the entry editor (the ✎ beside a row);
// the list shows a one-line summary so a row's behaviour is visible without
// opening it. Folded in from the read-only roll-table panel this replaced.
const { traitNameMap, fetchTraitsConfig } = useTraitsConfig()
const { load: loadEffectActions, summarize: summarizeEffect } = useEffectActions()

function resolveTarget(t) { return t ? (traitNameMap.value[t] || allTableNames.value[t] || t) : t }
function effectSummary(eff) { return summarizeEffect(eff, resolveTarget) }
function conditionSummary(c) {
  const parts = [c.type]
  if (c.target) parts.push(c.target)
  if (c.value) parts.push(c.value)
  if (c.narrative) parts.push(`"${c.narrative}"`)
  return parts.join(' ')
}

// ── Bound variables: the scope their paths start from ────────────────
// A table's activation scope is not an SFX's. `table_bindings()` binds the
// ambient facts (the paths'/term's faction, the table, the roll, the entry) and
// *then* the table's own declarations, in order — so a declaration may start
// from an ambient name or an earlier declaration. The ambient half is mirrored
// in `rollTableScope.js`; the declared half is traced by the shared composable,
// which a *row's* layer uses too ([[B281]]).
//
// No `source-element` is passed to the editor on purpose: `table_bindings()`
// resolves the declarations against a `TargetContext` with no source, so a
// `select source` step would error and resolve nothing. Offering it would
// promise a value the engine cannot bind.
const ambientVariables = { ...ROLL_TABLE_AMBIENT_VARIABLES }
// Ambient + the table's declarations, in resolution order. This is the scope a
// **row's** own declarations start from and may not shadow, and it is what the
// entry editor is handed so it can offer the table's names ([[B281]]).
const { scope: tableScope, types: declaredTypes } = useBoundVariableScope(
  computed(() => form.boundVariables),
  computed(() => ROLL_TABLE_AMBIENT_VARIABLES),
)

// ── Life-path connector context ──────────────────────
// The connector is a property of the *path*, not the table: it lives in the
// wrapping step's `bindings`. So the panel reads the path fresh and writes its
// `steps` back on save. All three stay null/empty when the table was opened
// without a path context, and then no column is shown at all.
const lp = ref(null)
const step = ref(null)
const stepBindings = ref([])
const pathHint = ref('')

const connectorEnabled = computed(() => !!step.value)
const stepById = computed(() => new Map((lp.value?.steps || []).map(s => [s.id, s])))
const stepOptions = computed(() => (lp.value?.steps || []).map(s => ({
  value: s.id,
  label: s.label || s.id || '(untitled step)',
})))

function lifePathName(id) {
  return (lifePathOptions.value.find(o => o.value === id) || {}).label || ''
}

// The row's binding for the entry at `i`, or null when it follows the step's
// default. Looked up by the row's stable key, which mirrors the API's
// `row_key()` fallback (see lifePathConnector.js).
function bindingFor(i) {
  const e = form.entries[i]
  if (!e) return null
  return stepBindings.value.find(b => b.key === rowKey(e, i)) || null
}

function connectorTextFor(i) {
  return connectorText(bindingFor(i), { stepById: stepById.value, pathNameOf: lifePathName })
}

// A binding's effects are the *path's* data, so they are scoped like the path:
// its universe, and its id as the owning life path.
const bindingUniverse = computed(() => lp.value?.universe || '')
const bindingLifePath = computed(() => lp.value?.id || props.lifePathId || '')

// ── Row binding edits ────────────────────────────────
// A binding lives in the wrapping step (`step.bindings`), keyed by the row's
// stable key. This panel holds a copy and writes the whole path back on save.

function addBinding(i) {
  const e = form.entries[i]
  if (!e) return
  const key = rowKey(e, i)
  if (stepBindings.value.some(b => b.key === key)) return
  // A row authored before keys existed has only a derived key, which changes
  // with its band. Pin it when a binding is made so the binding cannot move out
  // from under itself.
  if (!e.key) e.key = key
  stepBindings.value.push({ key, next: '', exitKind: '', exitPath: '', enroll: false, effects: [] })
}

function removeBinding(i) {
  const e = form.entries[i]
  if (!e) return
  const key = rowKey(e, i)
  stepBindings.value = stepBindings.value.filter(b => b.key !== key)
}

function onExitKind(binding) {
  if (binding.exitKind !== 'draft') binding.exitPath = ''
}

// Read the wrapping path fresh (the table's deprecated `lifePath` field says
// nothing about the wrapper) and resolve the step this panel edits.
async function loadPathContext() {
  if (!props.lifePathId || !form.id) return
  try {
    const p = await fetchLifePath(props.lifePathId)
    if (!p) { pathHint.value = 'Life path not found — no connector column.'; return }
    lp.value = p
    const wrappers = (p.steps || []).filter(s => s.tableId === form.id)
    if (!wrappers.length) {
      pathHint.value = 'This path has no step wrapping this table — no connector column.'
      return
    }
    const match = (props.stepId && wrappers.find(s => s.id === props.stepId)) || wrappers[0]
    step.value = match
    // Copy the bindings: this panel mutates them in place and save writes the
    // whole array back, so the loaded path must not be edited before Save.
    stepBindings.value = (match.bindings || []).map(b => ({
      key: b.key || '',
      next: b.next || '',
      exitKind: b.exitKind || '',
      exitPath: b.exitPath || '',
      enroll: !!b.enroll,
      effects: JSON.parse(JSON.stringify(b.effects || [])),
    }))
    // A path may wrap the same table twice; say which step is being edited.
    if (wrappers.length > 1) {
      pathHint.value = `This path wraps this table at ${wrappers.length} steps — editing “${match.label || match.id}”.`
    }
    // A row authored before keys existed has only a scheme-derived key, which
    // changes with its band. A binding already names it, so pin that key now —
    // otherwise editing the band (or reordering) would move the row out from
    // under its own binding on the next save.
    form.entries.forEach((e, i) => {
      if (e.key) return
      const key = rowKey(e, i)
      if (stepBindings.value.some(b => b.key === key)) e.key = key
    })
  } catch { /* no path context: no column */ }
}

// A panel opened for the same table is *reused* when the same component+id is
// opened again (Panel.openChild), so a second step wrapping this table would
// otherwise leave the first step's bindings on screen. Re-resolve on a context
// change rather than silently editing the wrong step.
watch(() => [props.lifePathId, props.stepId], ([lpId, id], [oldLp, oldId]) => {
  if (lpId === oldLp && id === oldId) return
  step.value = null
  stepBindings.value = []
  pathHint.value = ''
  loadPathContext()
})

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
  // The row summaries resolve effect targets and trait ids, as the read-only
  // panel did.
  loadEffectActions()
  fetchAllTableNames()
  if (!Object.keys(traitNameMap.value).length) fetchTraitsConfig()
  if (!props.tableId) return
  try {
    // Loading a document is not an edit: without this the assignments below wake
    // the auto-save and write back what was just read.
    _suppressEdits = true
    const t = await fetchTable(props.tableId)
    if (!t) return
    form.id = t.id
    form.name = t.name
    form.universe = t.universe
    // Ownership, not the wrapping context: a path that *wraps* a table need not
    // own it (a shared table's `lifePath` is null), and `props.lifePathId` is now
    // the wrapping path — seeding this with it would claim the table on save.
    form.lifePath = t.lifePath || ''
    form.scheme = t.scheme
    form.rollSource = t.rollSource || 'FIXED_DIE'
    form.traitDiceCount = t.traitDiceCount ?? 1
    // The wire value is the notation (`d6`, `d20`, `d66`); normalise so a table
    // saved before the field was a string still lands on a known value.
    form.die = String(t.die || 'd6').toLowerCase()
    // The table's own declarations, read back so a save can send them: an
    // omitted field is a deleted one on a whole-document replace ([[B279]]).
    form.subjectKind = t.subjectKind || ''
    // Carried, not edited: this panel has no check UI, so the only safe thing to
    // do with it is send back what was read. The entry panel already does this.
    form.check = t.check
      ? { traitIds: t.check.traitIds || [], difficulty: t.check.difficulty,
          freeChoice: t.check.freeChoice }
      : null
    form.boundVariables = (t.boundVariables || []).map(bv => ({
      name: bv.name || '',
      spec: bv.spec || { steps: [] },
    }))
    form.entries = (t.entries || []).map(e => ({
      // `key` is the row's stable identity and a life-path binding names it, so
      // it must survive the round trip. An empty one is filled by the API on
      // save. `costEffects` is preserved for the same reason: this panel does
      // not edit them and the entries map in save() is a full replace.
      key: e.key || '',
      costEffects: e.costEffects || [],
      // The row's own names ([[B281]]). This map is the *other half* of the save
      // map below, and it too builds a fresh object per row — so a field missing
      // here is dropped on **read** and then written back empty. That is exactly
      // how an author's declaration vanished: the save side had it and this side
      // did not. `check-path-fields.mjs` now compares the two maps' field sets
      // rather than trusting either half on its own.
      boundVariables: (e.boundVariables || []).map(bv => ({
        name: bv.name || '',
        spec: bv.spec || null,
      })),
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
  finally {
    // `loadPathContext` reads the path and its step's bindings — more loading, so it
    // happens inside the guard, and the guard is lifted in a `finally` because the
    // early return above would otherwise leave editing suppressed forever.
    await loadPathContext()
    _suppressEdits = false
  }
})

// ── Auto-save: the panels have no Save button (B211's convention) ─────
//
// The human: *"Saves should always, everywhere be automatic. So I don't want to see
// a save-button in the roll table GM panels."* Every edit persists on its own.
//
// The **whole draft** is watched rather than a list of its field names. A list is a
// promise to keep in step with the document, and the SFX panel's version had already
// fallen behind twice — a newly added field simply never saved, which reads as
// "auto-save is broken" rather than as a missing name in a list.
//
// Three things this has to get right, all of them learned elsewhere:
//   * loading is not an edit (`_suppressEdits`);
//   * a queued write is dropped on load, or it fires against the state it was
//     queued from and overwrites what was just read;
//   * a pending write is **flushed on close**. The SFX panel can leave that to its
//     Save button; with the button gone, closing inside the debounce window would
//     silently drop the last edit — which is the trap this whole change is about.
let _saveTimer = null
let _suppressEdits = false
const savedAt = ref(null)

function scheduleSave() {
  if (_suppressEdits) return
  if (!form.id) return
  savedAt.value = null
  clearTimeout(_saveTimer)
  _saveTimer = setTimeout(() => { save() }, 700)
}

watch(
  () => [form, stepBindings.value, step.value, lp.value],
  scheduleSave,
  { deep: true, flush: 'sync' },
)

onUnmounted(() => {
  // The flush: an edit made in the last 700ms still reaches the server.
  if (_saveTimer) {
    clearTimeout(_saveTimer)
    _saveTimer = null
    save()
  }
})

function addEntry() {
  form.entries.push({ key: '', costEffects: [], label: '', description: '', minValue: null, maxValue: null, weight: null, tier: '', conditions: [], effects: [], boundVariables: [] })
}

// The row's full editor (label, description, band, conditions, effects). The row
// object is handed across as a live draft in the spec's `context` and injected
// by the entry panel as `rowDraft`, so its edits land in `form` — this panel's
// Save is still the only commit point, and the stored table is never rewritten
// underneath the unsaved edits held here.
function openEntry(i) {
  panel.open({
    component: GmRollTableEntryEditPanel,
    title: 'Edit entry #' + (i + 1),
    // Identity per row: without it the panel would be *reused in place* for a
    // second row (same component, no id), leaving the first row's values on
    // screen under the second row's title.
    id: 'entry-' + i,
    props: {
      tableId: form.id,
      index: i,
      scheme: form.scheme,
      universe: form.universe,
      lifePath: form.lifePath,
    },
    context: {
      rowDraft: form.entries[i],
      // The scope the row's own declarations resolve against — ambient facts plus
      // the table's declarations, which the engine resolves *before* any row is
      // chosen ([[B281]]). The child needs it for two things: a row's name may
      // start from a table-level one, and a name that collides is refused, so the
      // editor has to show the collision rather than let it fail silently.
      tableScope: tableScope.value,
    },
  })
}

function removeEntry(i) {
  form.entries.splice(i, 1)
}

function onReorderEntry(from, to) {
  const [moved] = form.entries.splice(from, 1)
  form.entries.splice(to, 0, moved)
}

// A step as the mutation takes it. `next` and `exitKind` are one or the other
// (lifepath_validation), so a move clears the exit, and an exit is only what
// leaving means. `effects` and `enroll` travel untouched.
function stepToInput(s, bindings) {
  return {
    id: s.id,
    tableId: s.tableId,
    label: s.label || '',
    next: s.next || '',
    // The step's own effects travel untouched: this panel does not edit them, and
    // `steps` REPLACES the stored list — so omitting the field here erases every
    // effect the path panel authored (the same rule as a binding's, and the reason
    // `check-path-fields.mjs` compares this map's fields against what it read).
    effects: s.effects || [],
    bindings: (bindings || []).map(b => ({
      key: b.key,
      next: b.next || '',
      exitKind: b.next ? '' : (b.exitKind || ''),
      exitPath: (!b.next && b.exitKind === 'draft') ? (b.exitPath || '') : '',
      enroll: !!b.enroll,
      effects: b.effects || [],
    })),
  }
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
      // Table-level declarations travel back untouched (except the bound
      // variables this panel authors). `RollTableInput` replaces the whole
      // document, so omitting either would erase what the read just fetched —
      // the bug this round trip is the last writer of ([[B279]]).
      subjectKind: form.subjectKind || '',
      boundVariables: (form.boundVariables || []).map(bv => ({
        name: bv.name || '',
        spec: bv.spec || null,
      })),
      scheme: form.scheme,
      rollSource: form.rollSource,
      traitDiceCount: form.traitDiceCount ?? 1,
      die: form.die,
      // Read back and returned untouched -- see the form's `check`. Hardcoding
      // null here erased a TIER table's check on every save from this panel.
      check: form.check,
      entries: form.entries.map(e => ({
        // Carried through untouched: the API fills an empty one on save, and a
        // binding names a row by it. The map is a full replace, so dropping it
        // would orphan every binding written against these rows.
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
        // The row's own declared names ([[B281]]). This map is a full replace, so
        // omitting them erases every name a row exposes — the same class of loss as
        // `key` and `costEffects` above, and the reason `check-path-fields.mjs`
        // pins all three.
        boundVariables: (e.boundVariables || []).map(bv => ({
          name: bv.name || '',
          spec: bv.spec || null,
        })),
      })),
    }
    const result = await saveRollTable(input)
    if (!result?.id) {
      error.value = 'Roll table save failed'
      return
    }

    // The connector belongs to the *path*, so write the wrapper too. `steps`
    // REPLACES the stored list, so every step travels — only the edited step's
    // bindings differ — and the path's other fields travel with it: saveLifePath
    // always writes name/universe/description/entryTableId/discovery/conditions,
    // so omitting one (the walkability gate above all) would blank it.
    let connectorError = ''
    if (connectorEnabled.value && lp.value) {
      try {
        const steps = (lp.value.steps || []).map(s =>
          s.id === step.value.id ? stepToInput(s, stepBindings.value) : stepToInput(s, s.bindings))
        const pathResult = await saveLifePath({
          id: lp.value.id,
          name: lp.value.name,
          universe: lp.value.universe,
          description: lp.value.description,
          entryTableId: lp.value.entryTableId,
          entryStep: lp.value.entryStep,
          steps,
          discovery: lp.value.discovery || null,
          conditions: lp.value.conditions || [],
        })
        if (!pathResult?.ok) connectorError = 'the life path save was rejected.'
      } catch (e) {
        connectorError = e?.message || 'the life path save failed.'
      }
    }

    if (connectorError) {
      // The table landed but the connector did not. Leave the panel open and say
      // exactly what happened — closing would hide a partial write.
      error.value = `Roll table saved, but ${connectorError}`
      return
    }

    bus.emit('lifepath-saved', { id: lp.value?.id || form.lifePath, universe: lp.value?.universe })
    // No `panel.close()`: this runs on every edit now, and the panel is the
    // author's surface until they close it themselves.
    savedAt.value = new Date()
  } catch (e) {
    error.value = e?.message || 'Save failed'
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
/* Intrinsic floor for the content. The panel shell is content-driven and its
   own floor is 260px, which is too narrow for an entry row — a full-width label
   input, a min/max pair and the connector select. The shell keeps owning the
   cap; this only stops *this* panel from sitting at the floor. 360px is the
   low end of the range the row needs: wide enough for the connector's longest
   option ("Muster out (dishonourably)") and the band inputs side by side, and
   within the shell's 440px cap (minus its 16px padding and the body's 10px, so
   386px of content). The `min()` mirrors the shell's own viewport clamp — the
   shell's cap is `100vw - 46px`, less 54px of chrome — so a very narrow
   viewport scrolls the panel body instead of forcing content past the cap. */
.rte-root { padding: 0; display: flex; flex-direction: column; gap: 8px; min-width: min(360px, calc(100vw - 100px)); }
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
.rte-detail code { font-family: monospace; font-size: 10px; color: var(--accent-pale); }
.rte-entry-body { flex: 1; display: flex; flex-direction: column; gap: 5px; min-width: 0; }
.rte-entry-head { display: flex; align-items: center; gap: 4px; }
.rte-entry-index { font-size: 9px; color: var(--text-dim); }
.rte-spacer { flex: 1; }
.rte-num { width: 70px; }
.rte-entry-summary { display: flex; flex-direction: column; gap: 2px; }
.rte-effect {
  font-family: monospace;
  font-size: 10px;
  color: var(--text);
  background: var(--overlay-6);
  border: 1px solid var(--overlay-10);
  border-radius: 4px;
  padding: 3px 6px;
  line-height: 1.4;
  word-break: break-word;
}
.rte-cond { font-size: 9px; color: var(--accent); }
.rte-connector-hint { margin: 0 0 4px 0; }
.rte-connector {
  display: flex; flex-direction: column; gap: 4px;
  padding: 5px 6px;
  background: var(--overlay-4);
  border: 1px solid var(--overlay-8);
  border-radius: 6px;
}
.rte-connector-read { display: flex; align-items: baseline; gap: 6px; }
.rte-connector-label { font-size: 9px; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.5px; }
.rte-connector-dest { font-size: 11px; color: var(--accent); }
.rte-enroll { display: flex; align-items: center; gap: 5px; font-size: 10px; color: var(--text-dim); }
.rte-enroll input { width: auto; }
.rte-row-pass { display: flex; align-items: center; gap: 6px; }
.rte-row-pass .rte-detail { flex: 1; margin: 0; }
.rte-binding-effects { display: flex; flex-direction: column; gap: 3px; }
.rte-binding-effects .rte-subtitle { margin-bottom: 0; }
.rte-binding-effects .rte-detail { margin: 0; }
.rte-error { font-size: 11px; color: var(--danger); background: var(--danger-8); padding: 6px 10px; border-radius: 4px; }
/* The auto-save readout that replaced the Save button. Quiet by default — it is
   information, not an action — and it becomes the error surface when a write fails,
   because the failure has nowhere else to appear now. */
.rte-save-state { display: flex; align-items: center; min-height: 18px; }
.rte-save-msg { font-size: 10px; color: var(--text-dim); }
.rte-saved { color: var(--success); }
.rte-save-error .rte-save-msg {
  font-size: 11px; color: var(--danger); background: var(--danger-8);
  padding: 6px 10px; border-radius: 4px;
}
</style>
