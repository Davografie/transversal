<template>
  <div class="lpd-root">
    <div class="lpd-toolbar">
      <Button class="lpd-canvas" variant="neutral" title="Open in canvas" :disabled="!path.id" @click="openFullCanvas">🗺</Button>
    </div>

    <div class="lpd-field">
      <label>Name</label>
      <input v-model="form.name" placeholder="Life path name…" />
    </div>
    <div class="lpd-field">
      <label>Universe</label>
      <GmScopePicker
        v-model="form.universe"
        :options="universeOptions"
        empty-label="Fundamental (all universes)"
        placeholder="Select universe…"
      />
    </div>
    <div class="lpd-field">
      <label>Description</label>
      <textarea v-model="form.description" rows="2" placeholder="What it is…"></textarea>
    </div>

    <!-- ── The path's own context: the names its wrapped tables read ── -->
    <div class="lpd-section">
      <span class="lpd-subtitle">Path variables</span>
      <span class="lpd-hint">
        Values this path supplies to the tables it wraps. They resolve <em>before</em>
        the step's and the table's own names, which is how one <strong>shared</strong>
        table reads <code>{sect}</code> from whichever path is walking it.
      </span>
      <BoundVariablesEditor
        v-model="form.boundVariables"
        :variables="PATH_AMBIENT_VARIABLES"
        :types="pathTypes"
        :overridable="wrappedTableNames"
        allow-override
      />
    </div>

    <!-- ── The wrapper: the tables this path walks, in order ── -->
    <div class="lpd-section">
      <span class="lpd-subtitle">Steps</span>
      <span class="lpd-hint">The roll tables this path wraps. A step's id is its own — the same table may be wrapped twice. Open a step to edit its rows and their bindings.</span>

      <div v-if="!form.steps.length" class="lpd-empty">No steps yet.</div>

      <div v-for="(step, i) in form.steps" :key="step.id || ('new-' + i)" class="lpd-step">
        <div class="lpd-step-head">
          <span class="lpd-step-index">{{ i + 1 }}</span>
          <Button
            class="lpd-step-open"
            variant="ghost"
            size="sm"
            :disabled="!step.tableId"
            :title="step.tableId
              ? 'Open ' + stepText(step) + ' — step id ' + step.id
              : 'Effects-only step ' + step.id + ' — it wraps no table to open'"
            @click="openTable(step)"
          >{{ step.id }}</Button>
          <span class="lpd-step-table">{{ stepText(step) }}</span>
          <Button variant="ghost" size="icon" title="Move up" :disabled="i === 0" @click="moveStep(i, -1)">↑</Button>
          <Button variant="ghost" size="icon" title="Move down" :disabled="i === form.steps.length - 1" @click="moveStep(i, 1)">↓</Button>
          <Button variant="danger-ghost" size="icon" title="Remove step" @click="removeStep(i)">✕</Button>
        </div>

        <div class="lpd-field">
          <label>Table</label>
          <div class="lpd-step-table-row">
            <GmScopePicker
              :model-value="step.tableId"
              :options="entryTableOptions"
              empty-label="No table — effects only"
              placeholder="Roll table…"
              @update:model-value="onPickStepTable(step, $event)"
            />
            <Button
              v-if="step.tableId"
              variant="ghost"
              size="sm"
              title="Drop the table: this step runs its own effects"
              @click="setStepTable(step, '')"
            >Effects only</Button>
          </div>
          <span v-if="!step.tableId" class="lpd-hint">
            <strong>Effects only.</strong> This step wraps no table: it runs its
            <em>Step effects</em> once and follows <em>Default next</em>. Where a player
            must choose, author a <em>choose</em> step in the effect's targeting path.
          </span>
        </div>
        <div class="lpd-field">
          <label>Label</label>
          <input v-model="step.label" placeholder="Step label…" />
        </div>
        <div class="lpd-field">
          <label>Default next</label>
          <GmScopePicker
            v-model="step.next"
            :options="stepOptions"
            empty-label="End the term"
            placeholder="Next step…"
          />
          <span class="lpd-hint">Where a row with no binding of its own goes — and, on an effects-only step, where the step itself goes.</span>
        </div>

        <!-- The step's own context: the names its wrapped table reads ([[B290]]).
             A child panel, because the step list is already table + label + next +
             effects — the same reason the effects moved out. -->
        <div class="lpd-field">
          <label>Step variables</label>
          <div class="lpd-step-vars">
            <span class="lpd-detail">{{ variableSummary(step) }}</span>
            <Button variant="secondary" size="sm" @click="openStepVariables(step)">Edit</Button>
          </div>
          <span class="lpd-hint">
            Names this step supplies to the table it wraps — or, on an effects-only
            step, to its own effects — resolved before the table's own, so a shared
            table reads the context of this step.
          </span>
        </div>

        <!-- The effects counterpart of `next`: that is this step's default *flow*,
             this is its default *behaviour*. Applied once whenever any row of this
             step resolves, after the row's own effects and the binding's — so an
             effect several rows would otherwise repeat is written once here. One
             that depends on a name only some rows expose runs on those and does
             nothing on the rest, which is the point ([[B281]]). -->
        <div class="lpd-field">
          <label>Step effects</label>
          <!-- The list stays in the step; each effect's form opens in a *child*
               panel, as the roll-table entry's and the SFX editor's do — an effect
               is a stacked builder of unbounded height, and the path's steps have to
               stay in view while one is edited. -->
          <EffectList
            :model-value="step.effects"
            :editing-index="editingStepEffect && editingStepEffect.stepId === step.id
              ? editingStepEffect.index : null"
            @update:model-value="step.effects = $event"
            @add="openStepEffectEditor(step, null)"
            @edit="(i) => openStepEffectEditor(step, i)"
          />
          <span v-if="step.tableId" class="lpd-hint">
            Runs once for <strong>any</strong> row this step resolves — after the row's
            own effects and its binding's. Consume a bound variable as a
            <em>targeting path</em> (<em>Start from → Variable → …</em>); the names
            offered are the table's and its rows', and a name only some rows expose
            resolves on those and does nothing on the rest.
          </span>
          <span v-else class="lpd-hint">
            The whole of this step: applied once, then <em>Default next</em> is taken.
            To let the player decide what an effect lands on, build the effect's target
            as a <em>targeting path</em> ending in <em>Choose</em> — the question is put
            to them when the step runs, and the step waits for the answer.
          </span>
        </div>
      </div>

      <GmScopePicker
        :model-value="newStepTableId"
        :options="entryTableOptions"
        empty-label="＋ Add a step…"
        placeholder="＋ Add a step…"
        @update:model-value="onPickNewStep"
      />
      <Button class="lpd-add-table" variant="secondary" block @click="addEffectsOnlyStep">
        ＋ Add effects-only step
      </Button>
      <!-- A brand-new table needs a saved path to belong to: it is created
           through the roll table panel with this path as its owner. -->
      <Button v-if="path.id" class="lpd-add-table" variant="secondary" block @click="addTable">＋ Add roll table</Button>
    </div>

    <div class="lpd-field">
      <label>Entry step</label>
      <GmScopePicker
        v-model="form.entryStep"
        :options="stepOptions"
        empty-label="None"
        placeholder="Select step…"
      />
      <span class="lpd-hint">The step a term begins at.</span>
    </div>

    <div class="lpd-field">
      <label>Conditions</label>
      <!-- Walkability gate — may this character *walk* the path, as opposed to
           `discovery`, which is the one-time reveal that it exists. `availableKeys`
           is an empty list on purpose: a life path is a time-less gate with no
           trigger and no source, so every condition type that reads a context key
           is greyed out with its reason ("nothing to read here") and the offered
           set is derived from the catalog rather than listed here. -->
      <ConditionEditor v-model="form.conditions" :available-keys="[]" />
      <span class="lpd-hint">A character may only walk this path while these pass.</span>
    </div>

    <div class="lpd-subsection">
      <span class="lpd-subtitle">Discovery</span>
      <span v-if="!discoveryRows.length" class="lpd-detail">None — visible to all</span>
      <table v-else class="lpd-table">
        <tbody>
          <tr v-for="(row, i) in discoveryRows" :key="i">
            <td class="lpd-key">{{ row.typeLabel }}</td>
            <td>{{ row.valueLabel }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Auto-save, so no Save button — except in **create** mode, where there is
         nothing to write onto yet. One deliberate act creates the path, and the
         auto-save arms from then on (B225's shape: a create that silently did
         nothing is the failure that rule exists to prevent). -->
    <template v-if="isNew">
      <Button class="lpd-create" variant="success" solid :loading="saving" :disabled="saving || !form.name.trim() || !form.universe.trim()" @click="save">
        {{ saving ? 'Creating…' : 'Create life path' }}
      </Button>
      <span class="lpd-hint">Name it and choose a universe. Steps and their effects appear once it exists, and save as you edit from then on.</span>
    </template>
    <div v-else class="lpd-save-state" :class="{ 'lpd-save-error': !!error }">
      <span v-if="error" class="lpd-save-msg">{{ error }}</span>
      <span v-else-if="saving" class="lpd-save-msg">Saving…</span>
      <span v-else-if="savedAt" class="lpd-save-msg lpd-saved">Saved</span>
      <span v-else class="lpd-save-msg">Edits save as you make them.</span>
    </div>

    <Button v-if="pathId" class="lpd-delete" variant="danger-ghost" size="sm" block @click="onDeleteConfirmed">Delete life path</Button>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { resolveLayer, useBoundVariableScope } from '@/composables/useBoundVariableScope.js'
import { useTargetCatalog } from '@/composables/useTargetCatalog.js'
import { ROLL_TABLE_AMBIENT_VARIABLES } from '@/composables/rollTableScope.js'
import { useApi } from '@/composables/useApi.js'
import { useLifePaths } from '@/composables/useLifePaths.js'
import { usePanel } from '@/composables/usePanel.js'
import { usePanelBus } from '@/composables/usePanelBus.js'
import Button from '@/components/ui/Button.vue'
import BoundVariablesEditor from './BoundVariablesEditor.vue'
import ConditionEditor from './ConditionEditor.vue'
import GmScopePicker from './GmScopePicker.vue'
import GmRollTableEditPanel from './GmRollTableEditPanel.vue'
import EffectList from './EffectList.vue'
import GmDraftEffectPanel from './GmDraftEffectPanel.vue'
import GmStepVariablesPanel from './GmStepVariablesPanel.vue'

// The names a **path** or **step** declaration starts from: the ambient roll-table
// facts, and nothing else ([[B290]]). A path resolves before any table exists, so
// these — plus the path's own names, for a step — are the whole base, and they are
// the same mirror `table_bindings()` binds.
const PATH_AMBIENT_VARIABLES = { ...ROLL_TABLE_AMBIENT_VARIABLES }

const panel = usePanel()
const bus = usePanelBus()
const { graphql } = useApi()
const { saveLifePath, deleteLifePath, pathsByUniverse, fetchLifePath } = useLifePaths()

const props = defineProps({
  lp: { type: Object, required: true },
})

// The *stored* copy wins over the prop we were opened with. The panel is handed
// a plain object snapshot, and saving patches the store — so reading through the
// store is what keeps the discovery display (and the canvas / delete targets)
// from going stale (B41). Falls back to the prop when the store has no bucket
// for this path, e.g. opened from the canvas or for a brand-new path.
const path = computed(() => {
  for (const list of Object.values(pathsByUniverse.value || {})) {
    const found = (list || []).find(p => p.id === props.lp.id)
    if (found) return found
  }
  return props.lp
})

// A path's or a step's declared names ([[B290]]), copied field by field so the whole
// wire shape survives: `spec` is deep-copied (the builder mutates it in place),
// `element`/`cardinality` are a reservation's type ([[B285]]), and `override` is the
// caller's "replace the wrapped table's name of this name". Dropping any of them here
// erases it on the next auto-save — `steps` replaces the stored list, and so do the
// path's own declarations.
function copyDecls(decls) {
  return (decls || []).map(d => ({
    name: d.name || '',
    spec: d.spec ? JSON.parse(JSON.stringify(d.spec)) : null,
    element: d.element || '',
    cardinality: d.cardinality || '',
    override: !!d.override,
  }))
}

// Copy the wrapper deeply: the editor mutates steps in place, and the prop is
// the panel's own `lp` object — a cancelled edit must not leak into it. A step's
// `bindings` are carried through untouched (this panel no longer edits them) but
// they must travel, because `steps` REPLACES the stored list on save: a step sent
// without them would drop every row binding the roll table panel authored.
function copySteps(steps) {
  return (steps || []).map(s => ({
    id: s.id || '',
    tableId: s.tableId || '',
    label: s.label || '',
    next: s.next || '',
    // The step's own declarations ([[B290]]). Carried for the same reason the
    // bindings are: this panel replaces the whole list.
    boundVariables: copyDecls(s.boundVariables),
    bindings: (s.bindings || []).map(b => ({
      key: b.key || '',
      next: b.next || '',
      exitKind: b.exitKind || '',
      exitPath: b.exitPath || '',
      enroll: !!b.enroll,
      effects: JSON.parse(JSON.stringify(b.effects || [])),
    })),
    // The step's own effects ([[B281]]) — this panel is now their editor, so they
    // are copied like everything else the form mutates in place.
    effects: JSON.parse(JSON.stringify(s.effects || [])),
  }))
}

// A path that does not exist yet cannot auto-save: there is nothing to write onto.
// B225's rule, and the same shape the SFX panel uses — create mode asks for one
// deliberate act, and arms the auto-save from then on.
const createdId = ref('')
const pathId = computed(() => createdId.value || props.lp.id || '')
const isNew = computed(() => !pathId.value)

// ── Auto-save: no Save button (B211's convention, the human 2026-10-13) ──
let _saveTimer = null
let _suppressEdits = false
// Has the author changed anything since the panel opened? A document fetched while
// they were typing is older than what they typed, so it must not replace it.
let _touched = false
// A stored document that arrived while an editor was open. Applied when the editor
// closes, if the author still has not edited.
let _pendingSeed = null
const savedAt = ref(null)

function scheduleSave() {
  if (_suppressEdits) return
  _touched = true
  if (isNew.value) return
  savedAt.value = null
  clearTimeout(_saveTimer)
  _saveTimer = setTimeout(() => { save() }, 700)
}

onUnmounted(() => {
  offStepEffectClose?.()
  // Flush a pending write: an edit made inside the debounce window still lands.
  if (_saveTimer) {
    clearTimeout(_saveTimer)
    _saveTimer = null
    save()
  }
})

/** Fill the form from a path. Called at setup, and again on mount when the stored
 *  copy arrives — see `onMounted`. */
function seedForm(p) {
  form.name = p.name || ''
  form.universe = p.universe || ''
  form.description = p.description || ''
  // Deprecated and no longer offered as a control — inert now that the flow is
  // declared by the steps. The stored value is carried so a save cannot blank it.
  form.entryTableId = p.entryTableId || ''
  form.entryStep = p.entryStep || ''
  form.steps = copySteps(p.steps)
  // The path's own declaration layer ([[B290]]) — copied, and carried through every
  // save for the same reason the steps are: the mutation replaces what it is sent.
  form.boundVariables = copyDecls(p.boundVariables)
  // Copied, not aliased: the editor mutates in place, and the prop is the
  // panel's own `lp` object — a cancelled edit must not leak into it.
  form.conditions = (p.conditions || []).map(c => ({ ...c }))
}

/** Re-seed from a **stored** copy. Guarded so the load is not read as an edit. */
function seedFrom(p) {
  _suppressEdits = true
  try {
    seedForm(p)
  } finally {
    _suppressEdits = false
  }
}

const form = reactive({
  name: path.value.name || '',
  universe: path.value.universe || '',
  description: path.value.description || '',
  entryTableId: path.value.entryTableId || '',
  entryStep: path.value.entryStep || '',
  boundVariables: copyDecls(path.value.boundVariables),
  steps: copySteps(path.value.steps),
  conditions: (path.value.conditions || []).map(c => ({ ...c })),
})

// The path's own declaration layer, resolved for display as the author edits it: the
// ambient facts are its base, and `pathScope` — ambient **plus** these names — is what
// a step's declarations start from. Declared after `form`, because the composable's
// watcher is `immediate` and reads `form.boundVariables` during setup (a TDZ
// `ReferenceError` otherwise, invisible to the build — pinned by `check-path-fields`).
const { scope: pathScope, types: pathTypes } = useBoundVariableScope(
  computed(() => form.boundVariables),
  computed(() => PATH_AMBIENT_VARIABLES),
)

// The watch must **follow** the declaration it watches. A getter source is run
// eagerly, at `watch()` time, to collect its dependencies — so written above
// `form`, `() => form` reads a `const` still in its temporal dead zone and throws
// out of `setup()`. The panel then never mounts, and because it is restorable a
// saved window re-throws on every load.
watch(
  () => form,
  () => scheduleSave(),
  { deep: true, flush: 'sync' },
)

const universeOptions = ref([])
const tableNames = ref({})
const entryTableOptions = ref([])
const newStepTableId = ref('')

// Table names repeat across life paths ("Learn", "Mishap", "Survival" ×2), so
// the owning path — or the shared/fundamental scope — disambiguates the label.
async function loadOptions() {
  try {
    const [tables, lps, unis] = await Promise.all([
      // A step effect draws on the wrapped table's declarations **and its rows'**:
      // "this row is India" is a *row* declaration, and it is the name a step effect
      // is written against. `entries` carries only the declarations — the row fields
      // are not needed here.
      graphql(`{ rollTables { id name universe lifePath boundVariables { name spec }
                            entries { key boundVariables { name spec } } } }`),
      graphql(`{ lifePaths { id name } }`),
      graphql(`query($type: EntityType){ entities(type: $type){ id name currentUniverse } }`, { type: 'UNIVERSE' }),
    ])
    universeOptions.value = (unis?.entities || []).map(u => ({ value: u.currentUniverse, label: u.name }))
    const pathNames = Object.fromEntries((lps?.lifePaths || []).map(l => [l.id, l.name]))
    tableNames.value = Object.fromEntries((tables?.rollTables || []).map(t => [t.id, t.name]))
    // Kept for the step-effect scope: `stepScopeFor` resolves these into the names a
    // step's effects may start a path from, once per table.
    tableDeclarations.value = Object.fromEntries(
      (tables?.rollTables || []).map(t => [t.id, t.boundVariables || []]))
    // Flattened in row order, so the precedence matches the engine's when two rows
    // declare the same name.
    rowDeclarations.value = Object.fromEntries(
      (tables?.rollTables || []).map(t => [
        t.id,
        (t.entries || []).flatMap(e => e.boundVariables || []),
      ]))
    entryTableOptions.value = (tables?.rollTables || []).map(t => ({
      value: t.id,
      label: t.name + (t.lifePath
        ? ` · ${pathNames[t.lifePath] || t.lifePath}`
        : t.universe ? ' · shared' : ' · fundamental'),
    }))
  } catch { /* leave empty */ }
}

let optionsReady = null
onMounted(async () => {
  optionsReady = loadOptions()
  // A **restored** window is handed the `lp` snapshot from when it was parked, not
  // the current path — so the form must be re-seeded from storage. Without this a
  // floating panel shows a stale document (the step effects authored since it was
  // parked are simply not in it) and, being auto-saving, would then write that
  // staleness back.
  //
  // ⚠ It must not land on top of live work. A step's effect editor is handed the
  // **step object itself** as its draft (`context.rowDraft`), so replacing
  // `form.steps` orphans whatever that child is authoring: the effect it adds goes
  // to an object the list no longer contains and the auto-save never sees, so it
  // disappears with no error. A document that arrives while an editor is open, or
  // after the author has changed something, is therefore **parked** and applied when
  // the editor closes — and dropped if the author has edited by then, because their
  // version is the newer one and this panel is what saved it.
  if (props.lp?.id) {
    try {
      const fresh = await fetchLifePath(props.lp.id)
      if (fresh) {
        if (editingStepEffect.value || _touched) _pendingSeed = fresh
        else seedFrom(fresh)
      }
    } catch { /* keep what we were opened with */ }
  }
  // The row highlight follows the open effect, and shutting the editor is the one
  // path every *close* takes (a detach is deliberately not a close).
  offStepEffectClose = panel.onChildClose(() => {
    editingStepEffect.value = null
    if (_pendingSeed && !_touched) {
      const parked = _pendingSeed
      _pendingSeed = null
      seedFrom(parked)
    }
  })
})

// ── A step's effects: one child panel per effect ────────
//
// The list lives in the step; the editor does not. Same reason as every other
// effects list here: the form is a stacked builder of unbounded height.
const editingStepEffect = ref(null)  // { stepId, index } | null
let offStepEffectClose = null

/** The names a *step's* effects may start a path from.
 *
 *  A step effect runs for **any** row of the step, so the only names guaranteed to
 *  resolve are the ambient facts, the **path's** and the **step's** own declarations
 *  ([[B290]]), and **the wrapped table's own** — a row's declarations exist on some
 *  rows and not others, which is exactly why the effect is allowed to no-op where
 *  they are missing. Offering the table's names is what makes `select variable …`
 *  authorable at all here.
 *
 *  Resolved **per open**, in the engine's layer order (`path → step → table → row`)
 *  and with the engine's refuse-a-shadow rule (`resolveLayer`). The answer now
 *  changes when the *path* or the *step* is edited and not only when the table is, so
 *  a cache keyed by table id would offer a scope the engine no longer binds.
 */
const { traceSpec } = useTargetCatalog()
const tableDeclarations = ref({})   // tableId -> [{name, spec}]  (the table's own)
const rowDeclarations = ref({})     // tableId -> [{name, spec}]  (every row's, flattened)

async function stepScopeFor(step) {
  // The table list arrives asynchronously, and a panel opened straight after mount
  // would otherwise resolve the scope before it lands and offer the ambient names
  // only — the bug that made a step effect's table names unauthorable ([[B281]]).
  await (optionsReady || Promise.resolve())
  // One layer at a time, outermost first. The table's and its rows' stay one list
  // because the table resolves before any row, and `resolveLayer` refuses the later
  // duplicate — which is exactly the engine's rule.
  const ambient = { ...ROLL_TABLE_AMBIENT_VARIABLES }
  const afterPath = (await resolveLayer(form.boundVariables, ambient, traceSpec)).scope
  const afterStep = (await resolveLayer(step.boundVariables || [], afterPath, traceSpec)).scope
  return (await resolveLayer(
    [...(tableDeclarations.value[step.tableId] || []),
     ...(rowDeclarations.value[step.tableId] || [])],
    afterStep, traceSpec)).scope
}

/** A one-line read of a step's declarations, for the step list. */
function variableSummary(step) {
  const names = (step.boundVariables || []).map(v => (v.name || '').trim()).filter(Boolean)
  if (!names.length) return 'None — the table’s own names are all it reads'
  return names.map(n => `{${n}}`).join(', ')
}

/** The names a step's wrapped table declares: a collision with one of these is the
 *  case an override changes, and the list is already loaded for `stepScopeFor`. */
function stepOverridable(step) {
  return (tableDeclarations.value[step.tableId] || [])
    .map(d => (d.name || '').trim()).filter(Boolean)
}

/** The names any table this path wraps declares — the whole set a path-level
 *  declaration could override, since a path applies to every step it holds. */
const wrappedTableNames = computed(() => {
  const out = new Set()
  for (const s of form.steps) {
    for (const n of stepOverridable(s)) out.add(n)
  }
  return [...out]
})

/** A step's declarations are edited in a **child** panel ([[B290]]): the step list is
 *  already table + label + next + effects, and the same reasoning that moved the
 *  effects out applies to a fourth stacked builder. The step itself is the draft, and
 *  the scope it starts from travels in the spec's `context` — a panel cannot
 *  `provide` to its own child panels. */
function openStepVariables(step) {
  panel.open({
    component: GmStepVariablesPanel,
    title: 'Step variables — ' + stepText(step),
    // Identity per step: `Panel.open` reuses a child with no id *in place*, which
    // would show the previous step's declarations under this step's title.
    id: 'step-vars-' + (step.id || step.tableId),
    context: {
      rowDraft: step,
      // Ambient + the path's names, snapshotted: the path panel edits those, so they
      // cannot change underneath this child.
      boundVariableBase: pathScope.value,
      boundVariableOverridable: stepOverridable(step),
    },
  })
}

async function openStepEffectEditor(step, index) {
  editingStepEffect.value = { stepId: step.id, index }
  // Resolved *before* the panel opens: the spec's `context` is a snapshot, and a
  // promise inside it would reach the child as an unresolved object.
  const scopeVariables = await stepScopeFor(step)
  panel.open({
    component: GmDraftEffectPanel,
    title: index === null ? 'Add step effect' : 'Edit step effect',
    // Identity per step: `Panel.open` reuses a child with no id *in place*, which
    // would show the previous step's effect under this step's title.
    id: 'step-effect-' + step.id,
    props: { index, universe: form.universe, lifePath: pathId.value },
    // The step itself is the draft the child writes into, and its resolved scope is
    // what the targeting wizard may start from. A panel cannot `provide` to its own
    // child panels, so both travel in the spec's context.
    context: { rowDraft: step, scopeVariables },
  })
}

// ── Step identity ────────────────────────────────────
// New steps get an id here rather than waiting for the server's `""` → `sN`:
// entry_step and `next` are *step ids*, so a step with no id could not be
// pointed at. The backend preserves ids it is given.
function nextStepId() {
  let max = 0
  for (const s of form.steps) {
    const m = /^s(\d+)$/.exec(s.id || '')
    if (m) max = Math.max(max, parseInt(m[1], 10))
  }
  return `s${max + 1}`
}

function stepText(s) {
  return s.label || tableNames.value[s.tableId] || s.id || '(untitled step)'
}

const stepOptions = computed(() => form.steps.map(s => ({ value: s.id, label: stepText(s) })))

// ── Steps ────────────────────────────────────────────
function _blankStep(overrides) {
  return {
    id: nextStepId(),
    tableId: '',
    label: '',
    next: '',
    // The step's own declarations ([[B290]]) start empty and are authored in their
    // child panel; they are the *caller's* context, so re-pointing the step at
    // another table keeps them (only the row `bindings` name the table's rows).
    boundVariables: [],
    bindings: [],
    effects: [],
    ...overrides,
  }
}

function onPickNewStep(tableId) {
  if (!tableId) return
  form.steps.push(_blankStep({ tableId, label: tableNames.value[tableId] || '' }))
  newStepTableId.value = ''
}

/** A step with **no table** ([[B314]]): it applies its own effects and follows its
 *  own `next`. What it is *for* is the authoring form the owner asked for — trigger
 *  effects directly on the step, and let the player's choice come from a `{choose}`
 *  in an effect's targeting path instead of from pre-authored rows. */
function addEffectsOnlyStep() {
  form.steps.push(_blankStep({ label: 'Effects only' }))
}

/** Point a step at no table, or back at one. Either way its row bindings go: a
 *  binding names a row of the table it wraps, and there is no table. */
function setStepTable(step, tableId) {
  if (step.tableId === tableId) return
  step.bindings = []
  step.tableId = tableId
  if (tableId && !step.label) step.label = tableNames.value[tableId] || ''
}

function onPickStepTable(step, tableId) {
  setStepTable(step, tableId)
}

function moveStep(i, delta) {
  const j = i + delta
  if (j < 0 || j >= form.steps.length) return
  const [moved] = form.steps.splice(i, 1)
  form.steps.splice(j, 0, moved)
}

// Removing a step must not leave entry_step or an edge pointing at an id the
// path no longer has — the step id is an edge target here, not a label.
function removeStep(i) {
  const gone = form.steps[i].id
  form.steps.splice(i, 1)
  if (form.entryStep === gone) form.entryStep = ''
  for (const s of form.steps) {
    if (s.next === gone) s.next = ''
    for (const b of s.bindings) if (b.next === gone) b.next = ''
  }
}

// Open the wrapped table's rows in the roll table panel. The step — not the
// table — is the identity passed on: a path may wrap the same table twice, and
// the table panel's connector column edits the one this step names.
function openTable(step) {
  if (!step.tableId) return  // an effects-only step has no rows to open ([[B314]])
  panel.open({
    component: GmRollTableEditPanel,
    title: stepText(step),
    id: step.tableId,
    badge: 'ROLL-TABLE',
    props: { tableId: step.tableId, lifePathId: path.value.id, stepId: step.id },
  })
}

function addTable() {
  panel.open({
    component: GmRollTableEditPanel,
    title: 'New Roll Table',
    badge: 'ROLL-TABLE',
    props: { tableId: '', lifePathId: path.value.id, universe: path.value.universe },
  })
}

function openFullCanvas() {
  bus.emit('canvas:open-full', { mode: 'life-path', entityId: path.value.id, lifePath: path.value })
}

async function onDeleteConfirmed() {
  await deleteLifePath(props.lp.id)
  bus.emit('lifepath-saved', { id: props.lp.id, universe: props.lp.universe })
  panel.close()
}

const discoveryRows = computed(() => {
  const rows = []
  const d = path.value.discovery
  if (!d) return rows
  for (const loc of (d.atLocation || [])) rows.push({ typeLabel: '📍 Location', valueLabel: loc })
  for (const ent of (d.knowsEntity || [])) rows.push({ typeLabel: '👤 Knows', valueLabel: ent })
  for (const trait of (d.possessesTrait || [])) rows.push({ typeLabel: '🎯 Has trait', valueLabel: trait })
  for (const [trait, die] of Object.entries(d.hasTraitRating || {})) rows.push({ typeLabel: `⭐ Rating ≥ ${die}`, valueLabel: trait })
  for (const rel of (d.hasRelationship || [])) rows.push({ typeLabel: '🔗 Relationship', valueLabel: rel })
  return rows
})

const saving = ref(false)
const error = ref('')

async function save() {
  saving.value = true
  error.value = ''
  try {
    // This panel owns the wrapper, so it always sends both `steps` and
    // `entryStep` — an explicit list replaces what is stored. Bindings are not
    // edited here, but they are part of a step and travel with it.
    const steps = form.steps.map(s => ({
      id: s.id,
      tableId: s.tableId,
      label: s.label,
      next: s.next,
      // The step's own declarations ([[B290]]), sent for **every** step: `steps`
      // replaces the stored list, so an omitted `boundVariables` is a deleted one.
      boundVariables: s.boundVariables || [],
      bindings: (s.bindings || []).map(b => ({
        key: b.key,
        next: b.next,
        // `next` and `exitKind` are one or the other (lifepath_validation), so a
        // move clears the exit the form had hidden behind it.
        exitKind: b.next ? '' : b.exitKind,
        exitPath: (!b.next && b.exitKind === 'draft') ? b.exitPath : '',
        enroll: !!b.enroll,
        effects: b.effects || [],
      })),
      // Sent for every step, not only the edited one: `steps` replaces the stored
      // list, so an omitted `effects` is a deleted one ([[B279]]'s class, and the
      // reason `bindings` travels whole too).
      effects: s.effects || [],
    }))
    const result = await saveLifePath({
      id: pathId.value,
      name: form.name,
      universe: form.universe,
      description: form.description,
      // Deprecated field, no control: passed straight through so a save cannot
      // blank it. `discovery` is likewise not edited here.
      entryTableId: form.entryTableId,
      entryStep: form.entryStep,
      steps,
      // The path's own declarations ([[B290]]) — the context its wrapped tables read.
      boundVariables: form.boundVariables,
      discovery: path.value.discovery || null,
      conditions: form.conditions,
    })
    if (result?.ok) {
      // A create becomes an edit in place: the same panel keeps the path open and
      // the auto-save arms, which is what B225 asks for rather than closing and
      // making the author find it again.
      if (result.isNew && result.id) createdId.value = result.id
      bus.emit('lifepath-saved', { id: result.id, universe: form.universe, isNew: result.isNew })
      savedAt.value = new Date()
    }
  } catch (e) {
    error.value = e?.message || 'Save failed'
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.lpd-root { padding: 0; display: flex; flex-direction: column; gap: 8px; }
.lpd-toolbar { display: flex; align-items: center; }
.lpd-canvas { margin-left: auto; }
.lpd-field { display: flex; flex-direction: column; gap: 3px; }
.lpd-field label { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.5px; }
.lpd-field input, .lpd-field textarea {
  font-size: 12px; padding: 6px 8px;
  background: var(--overlay-6); color: var(--text);
  border: 1px solid var(--overlay-10); border-radius: 6px;
  font-family: inherit; width: 100%; box-sizing: border-box;
}
.lpd-field textarea { resize: vertical; min-height: 48px; }
.lpd-hint { font-size: 9px; color: var(--text-dim); }
.lpd-error { font-size: 11px; color: var(--danger); background: var(--danger-8); padding: 6px 10px; border-radius: 4px; }
/* The auto-save readout that replaced the Save button: information, not an action,
   and the only place a failed write can appear now. */
.lpd-save-state { display: flex; align-items: center; min-height: 18px; }
.lpd-save-msg { font-size: 10px; color: var(--text-dim); }
.lpd-saved { color: var(--success); }
.lpd-save-error .lpd-save-msg {
  font-size: 11px; color: var(--danger); background: var(--danger-8);
  padding: 6px 10px; border-radius: 4px;
}

.lpd-section { display: flex; flex-direction: column; gap: 6px; margin-top: 4px; }
.lpd-subtitle { display: block; font-size: 9px; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 2px; }
.lpd-empty { font-size: 10px; color: var(--text-dim); padding: 6px 8px; background: var(--overlay-4); border-radius: 6px; }

.lpd-step { display: flex; flex-direction: column; gap: 6px; padding: 8px; background: var(--overlay-4); border: 1px solid var(--overlay-8); border-radius: 6px; }
.lpd-step-head { display: flex; align-items: center; gap: 4px; }
.lpd-step-index { font-size: 10px; font-weight: 700; color: var(--accent); min-width: 14px; }
.lpd-step-open { font-family: monospace; font-size: 10px; }
.lpd-step-table { flex: 1; font-size: 10px; color: var(--text-dim); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
/* The step's declarations: a read of what is there plus the child panel's opener —
   the builder itself is unbounded height and belongs in a panel of its own. */
.lpd-step-vars { display: flex; align-items: center; gap: 6px; }
.lpd-step-vars .lpd-detail { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
/* The table picker and the "drop the table" escape share a row, so an effects-only
   step is one click from a table and back ([[B314]]). */
.lpd-step-table-row { display: flex; align-items: center; gap: 6px; }
.lpd-step-table-row > :first-child { flex: 1; min-width: 0; }

.lpd-add-table { margin-top: 2px; }
.lpd-subsection { margin-top: 8px; }
.lpd-detail { display: block; font-size: 10px; color: var(--text-dim); line-height: 1.5; }
.lpd-table { width: 100%; border-collapse: collapse; margin: 4px 0 6px; font-size: 10px; }
.lpd-table td { padding: 2px 6px; border-bottom: 1px solid var(--overlay-2); color: var(--text); }
.lpd-key { color: var(--text-dim); width: 130px; }
.lpd-delete { margin-top: 4px; }
</style>
