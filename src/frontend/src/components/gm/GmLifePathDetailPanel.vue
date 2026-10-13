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
            :title="'Open ' + stepText(step) + ' — step id ' + step.id"
            @click="openTable(step)"
          >{{ step.id }}</Button>
          <span class="lpd-step-table">{{ stepText(step) }}</span>
          <Button variant="ghost" size="icon" title="Move up" :disabled="i === 0" @click="moveStep(i, -1)">↑</Button>
          <Button variant="ghost" size="icon" title="Move down" :disabled="i === form.steps.length - 1" @click="moveStep(i, 1)">↓</Button>
          <Button variant="danger-ghost" size="icon" title="Remove step" @click="removeStep(i)">✕</Button>
        </div>

        <div class="lpd-field">
          <label>Table</label>
          <GmScopePicker
            :model-value="step.tableId"
            :options="entryTableOptions"
            empty-label="Select table…"
            placeholder="Roll table…"
            @update:model-value="onPickStepTable(step, $event)"
          />
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
          <span class="lpd-hint">Where a row with no binding of its own goes.</span>
        </div>
      </div>

      <GmScopePicker
        :model-value="newStepTableId"
        :options="entryTableOptions"
        empty-label="＋ Add a step…"
        placeholder="＋ Add a step…"
        @update:model-value="onPickNewStep"
      />
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

    <Button class="lpd-save" variant="success" solid :loading="saving" :disabled="saving" @click="save">{{ saving ? 'Saving…' : 'Save life path' }}</Button>
    <div v-if="error" class="lpd-error">{{ error }}</div>

    <Button v-if="path.id" class="lpd-delete" variant="danger-ghost" size="sm" block @click="onDeleteConfirmed">Delete life path</Button>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useApi } from '@/composables/useApi.js'
import { useLifePaths } from '@/composables/useLifePaths.js'
import { usePanel } from '@/composables/usePanel.js'
import { usePanelBus } from '@/composables/usePanelBus.js'
import Button from '@/components/ui/Button.vue'
import ConditionEditor from './ConditionEditor.vue'
import GmScopePicker from './GmScopePicker.vue'
import GmRollTableEditPanel from './GmRollTableEditPanel.vue'

const panel = usePanel()
const bus = usePanelBus()
const { graphql } = useApi()
const { saveLifePath, deleteLifePath, pathsByUniverse } = useLifePaths()

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
    bindings: (s.bindings || []).map(b => ({
      key: b.key || '',
      next: b.next || '',
      exitKind: b.exitKind || '',
      exitPath: b.exitPath || '',
      enroll: !!b.enroll,
      effects: JSON.parse(JSON.stringify(b.effects || [])),
    })),
  }))
}

const form = reactive({
  name: path.value.name || '',
  universe: path.value.universe || '',
  description: path.value.description || '',
  // Deprecated and no longer offered as a control — inert now that the flow is
  // declared by the steps. The stored value is carried so a save cannot blank it.
  entryTableId: path.value.entryTableId || '',
  entryStep: path.value.entryStep || '',
  steps: copySteps(path.value.steps),
  // Copied, not aliased: the editor mutates in place, and the prop is the
  // panel's own `lp` object — a cancelled edit must not leak into it.
  conditions: (path.value.conditions || []).map(c => ({ ...c })),
})

const universeOptions = ref([])
const tableNames = ref({})
const entryTableOptions = ref([])
const newStepTableId = ref('')

// Table names repeat across life paths ("Learn", "Mishap", "Survival" ×2), so
// the owning path — or the shared/fundamental scope — disambiguates the label.
async function loadOptions() {
  try {
    const [tables, lps, unis] = await Promise.all([
      graphql(`{ rollTables { id name universe lifePath } }`),
      graphql(`{ lifePaths { id name } }`),
      graphql(`query($type: EntityType){ entities(type: $type){ id name currentUniverse } }`, { type: 'UNIVERSE' }),
    ])
    universeOptions.value = (unis?.entities || []).map(u => ({ value: u.currentUniverse, label: u.name }))
    const pathNames = Object.fromEntries((lps?.lifePaths || []).map(l => [l.id, l.name]))
    tableNames.value = Object.fromEntries((tables?.rollTables || []).map(t => [t.id, t.name]))
    entryTableOptions.value = (tables?.rollTables || []).map(t => ({
      value: t.id,
      label: t.name + (t.lifePath
        ? ` · ${pathNames[t.lifePath] || t.lifePath}`
        : t.universe ? ' · shared' : ' · fundamental'),
    }))
  } catch { /* leave empty */ }
}

onMounted(loadOptions)

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
function onPickNewStep(tableId) {
  if (!tableId) return
  form.steps.push({
    id: nextStepId(),
    tableId,
    label: tableNames.value[tableId] || '',
    next: '',
    bindings: [],
  })
  newStepTableId.value = ''
}

function onPickStepTable(step, tableId) {
  // A binding names a row of *this step's* table, so pointing the step at a
  // different table invalidates every one of them — keep them and they would be
  // keys the new table does not have.
  if (step.tableId !== tableId) step.bindings = []
  step.tableId = tableId
  if (!step.label) step.label = tableNames.value[tableId] || ''
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
    }))
    const result = await saveLifePath({
      id: props.lp.id || '',
      name: form.name,
      universe: form.universe,
      description: form.description,
      // Deprecated field, no control: passed straight through so a save cannot
      // blank it. `discovery` is likewise not edited here.
      entryTableId: form.entryTableId,
      entryStep: form.entryStep,
      steps,
      discovery: path.value.discovery || null,
      conditions: form.conditions,
    })
    if (result?.ok) {
      bus.emit('lifepath-saved', { id: result.id, universe: form.universe, isNew: result.isNew })
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

.lpd-section { display: flex; flex-direction: column; gap: 6px; margin-top: 4px; }
.lpd-subtitle { display: block; font-size: 9px; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 2px; }
.lpd-empty { font-size: 10px; color: var(--text-dim); padding: 6px 8px; background: var(--overlay-4); border-radius: 6px; }

.lpd-step { display: flex; flex-direction: column; gap: 6px; padding: 8px; background: var(--overlay-4); border: 1px solid var(--overlay-8); border-radius: 6px; }
.lpd-step-head { display: flex; align-items: center; gap: 4px; }
.lpd-step-index { font-size: 10px; font-weight: 700; color: var(--accent); min-width: 14px; }
.lpd-step-open { font-family: monospace; font-size: 10px; }
.lpd-step-table { flex: 1; font-size: 10px; color: var(--text-dim); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.lpd-add-table { margin-top: 2px; }
.lpd-subsection { margin-top: 8px; }
.lpd-detail { display: block; font-size: 10px; color: var(--text-dim); line-height: 1.5; }
.lpd-table { width: 100%; border-collapse: collapse; margin: 4px 0 6px; font-size: 10px; }
.lpd-table td { padding: 2px 6px; border-bottom: 1px solid var(--overlay-2); color: var(--text); }
.lpd-key { color: var(--text-dim); width: 130px; }
.lpd-delete { margin-top: 4px; }
</style>
