<template>
  <div class="lpe-root">
    <div class="lpe-field">
      <label>Name</label>
      <input v-model="form.name" placeholder="Life path name…" />
    </div>
    <div class="lpe-field">
      <label>Universe</label>
      <GmScopePicker
        v-model="form.universe"
        :options="universeOptions"
        empty-label="Fundamental (all universes)"
        placeholder="Select universe…"
      />
    </div>
    <div class="lpe-field">
      <label>Description</label>
      <textarea v-model="form.description" rows="2" placeholder="What it is…"></textarea>
    </div>
    <div class="lpe-field">
      <label>Entry table</label>
      <GmScopePicker
        v-model="form.entryTableId"
        :options="entryTableOptions"
        empty-label="None"
        placeholder="Select entry table…"
      />
      <span class="lpe-hint">Deprecated — the pre-wrapper entry point. The flow is declared by the steps below.</span>
    </div>

    <!-- ── The wrapper: the tables this path walks, in order ── -->
    <div class="lpe-section">
      <span class="lpe-subtitle">Steps</span>
      <span class="lpe-hint">The roll tables this path wraps. A step's id is its own — the same table may be wrapped twice.</span>

      <div v-if="!form.steps.length" class="lpe-empty">No steps yet.</div>

      <div v-for="(step, i) in form.steps" :key="step.id || ('new-' + i)" class="lpe-step">
        <div class="lpe-step-head">
          <span class="lpe-step-index">{{ i + 1 }}</span>
          <span class="lpe-step-id" :title="'step id: ' + step.id">{{ step.id }}</span>
          <Button variant="ghost" size="icon" title="Move up" :disabled="i === 0" @click="moveStep(i, -1)">↑</Button>
          <Button variant="ghost" size="icon" title="Move down" :disabled="i === form.steps.length - 1" @click="moveStep(i, 1)">↓</Button>
          <Button variant="danger-ghost" size="icon" title="Remove step" @click="removeStep(i)">✕</Button>
        </div>

        <div class="lpe-field">
          <label>Table</label>
          <GmScopePicker
            :model-value="step.tableId"
            :options="entryTableOptions"
            empty-label="Select table…"
            placeholder="Roll table…"
            @update:model-value="onPickStepTable(step, $event)"
          />
        </div>
        <div class="lpe-field">
          <label>Label</label>
          <input v-model="step.label" placeholder="Step label…" />
        </div>
        <div class="lpe-field">
          <label>Default next</label>
          <GmScopePicker
            v-model="step.next"
            :options="stepOptions"
            empty-label="End the term"
            placeholder="Next step…"
          />
          <span class="lpe-hint">Where a row with no binding of its own goes.</span>
        </div>

        <div class="lpe-rows">
          <span class="lpe-subtitle">Rows</span>
          <div v-if="!step.tableId" class="lpe-hint">Pick a table to bind its rows.</div>
          <div v-else-if="!rowsByStep[i].length" class="lpe-hint">This table has no rows.</div>

          <div v-for="row in rowsByStep[i]" :key="row.key" class="lpe-row">
            <div class="lpe-row-head">
              <span class="lpe-row-label">{{ row.label }}</span>
              <span v-if="row.band" class="lpe-row-band">{{ row.band }}</span>
              <span class="lpe-row-key">{{ row.key }}</span>
            </div>

            <template v-if="row.binding">
              <div class="lpe-row-grid">
                <div class="lpe-field">
                  <label>Next</label>
                  <GmScopePicker
                    v-model="row.binding.next"
                    :options="stepOptions"
                    empty-label="Leave the path"
                    placeholder="Next step…"
                  />
                </div>
                <!-- `next` and `exitKind` are one or the other: a move needs no
                     exit, and an exit is only what leaving means. -->
                <template v-if="!row.binding.next">
                  <div class="lpe-field">
                    <label>Exit</label>
                    <select v-model="row.binding.exitKind" @change="onExitKind(row.binding)">
                      <option value="">Simply ends</option>
                      <option value="muster">Muster</option>
                      <option value="force_muster">Force muster</option>
                      <option value="draft">Draft</option>
                    </select>
                  </div>
                  <div v-if="row.binding.exitKind === 'draft'" class="lpe-field">
                    <label>Draft to</label>
                    <GmScopePicker
                      v-model="row.binding.exitPath"
                      :options="lifePathOptions"
                      empty-label="Select path…"
                      placeholder="Life path…"
                    />
                  </div>
                </template>
              </div>

              <label class="lpe-check">
                <input type="checkbox" v-model="row.binding.enroll" />
                Taking this row enrols the character in the path
              </label>

              <div class="lpe-effects">
                <span class="lpe-subtitle">Binding effects</span>
                <span class="lpe-hint">Applied after the row's own effects.</span>
                <EffectEditor v-model="row.binding.effects" :universe="form.universe" :life-path="props.lp.id || ''" />
              </div>

              <Button variant="danger-ghost" size="sm" @click="removeBinding(step, row.key)">Remove binding</Button>
            </template>

            <div v-else class="lpe-row-pass">
              <span class="lpe-hint">Passes through to the step's default.</span>
              <Button variant="secondary" size="sm" @click="addBinding(step, row.key)">Bind row</Button>
            </div>
          </div>
        </div>
      </div>

      <GmScopePicker
        :model-value="newStepTableId"
        :options="entryTableOptions"
        empty-label="＋ Add a step…"
        placeholder="＋ Add a step…"
        @update:model-value="onPickNewStep"
      />
    </div>

    <div class="lpe-field">
      <label>Entry step</label>
      <GmScopePicker
        v-model="form.entryStep"
        :options="stepOptions"
        empty-label="None"
        placeholder="Select step…"
      />
      <span class="lpe-hint">The step a term begins at.</span>
    </div>

    <div class="lpe-field">
      <label>Conditions</label>
      <!-- Walkability gate — may this character *walk* the path, as opposed to
           `discovery`, which is the one-time reveal that it exists. `availableKeys`
           is an empty list on purpose: a life path is a time-less gate with no
           trigger and no source, so every condition type that reads a context key
           is greyed out with its reason ("nothing to read here") and the offered
           set is derived from the catalog rather than listed here. -->
      <ConditionEditor v-model="form.conditions" :available-keys="[]" />
      <span class="lpe-hint">A character may only walk this path while these pass.</span>
    </div>

    <Button class="lpe-save" variant="success" solid :loading="saving" :disabled="saving" @click="save">{{ saving ? 'Saving…' : 'Save life path' }}</Button>
    <div v-if="error" class="lpe-error">{{ error }}</div>
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
import EffectEditor from './EffectEditor.vue'
import GmScopePicker from './GmScopePicker.vue'

const panel = usePanel()
const bus = usePanelBus()
const { graphql } = useApi()
const { saveLifePath } = useLifePaths()

const props = defineProps({
  lp: { type: Object, required: true },
})

// Copy the wrapper deeply: the editor mutates bindings in place, and the prop is
// the panel's own `lp` object — a cancelled edit must not leak into it.
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
  name: props.lp.name || '',
  universe: props.lp.universe || '',
  description: props.lp.description || '',
  entryTableId: props.lp.entryTableId || '',
  entryStep: props.lp.entryStep || '',
  steps: copySteps(props.lp.steps),
  // Copied, not aliased: the editor mutates in place, and the prop is the
  // panel's own `lp` object — a cancelled edit must not leak into it.
  conditions: (props.lp.conditions || []).map(c => ({ ...c })),
})

const entryTableOptions = ref([])
const universeOptions = ref([])
const lifePathOptions = ref([])
const tableNames = ref({})
const tableData = ref({})      // table id → { id name entries } for the wrapped steps
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
    lifePathOptions.value = (lps?.lifePaths || []).map(l => ({ value: l.id, label: l.name }))
    tableNames.value = Object.fromEntries((tables?.rollTables || []).map(t => [t.id, t.name]))
    entryTableOptions.value = (tables?.rollTables || []).map(t => ({
      value: t.id,
      label: t.name + (t.lifePath
        ? ` · ${pathNames[t.lifePath] || t.lifePath}`
        : t.universe ? ' · shared' : ' · fundamental'),
    }))
  } catch { /* leave empty */ }
}

// The rows of every table this path wraps, so a binding can be edited per row.
// Fetched directly rather than through useRollTables: the editor only needs the
// labels and keys, and must not reshuffle that store's per-path buckets.
async function loadStepTables() {
  const ids = [...new Set(form.steps.map(s => s.tableId).filter(Boolean))]
  await Promise.all(ids.map(async (id) => {
    if (tableData.value[id]) return
    try {
      const data = await graphql(
        `query($id:ID!){ rollTable(id:$id){ id name entries { key label minValue maxValue weight tier } } }`,
        { id },
      )
      if (data?.rollTable) tableData.value = { ...tableData.value, [id]: data.rollTable }
    } catch { /* leave the step's rows unloaded */ }
  }))
}

onMounted(async () => {
  await loadOptions()
  await loadStepTables()
})

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

// ── Rows of each step, each with its binding (or none) ──
// Mirrors the backend's `row_key` fallback so a row authored before keys existed
// still binds to what the executor will look up.
function rowKey(entry, index) {
  if (entry.key) return entry.key
  if (entry.minValue != null || entry.maxValue != null) {
    return `${entry.minValue ?? ''}\u2013${entry.maxValue ?? ''}`
  }
  if (entry.weight != null) return `w${entry.weight}`
  if (entry.tier) return entry.tier
  return String(index)
}

function bandText(entry) {
  if (entry.minValue != null || entry.maxValue != null) return `${entry.minValue ?? '?'}–${entry.maxValue ?? '?'}`
  if (entry.weight != null) return `w${entry.weight}`
  if (entry.tier) return entry.tier
  return ''
}

const rowsByStep = computed(() => form.steps.map(step => {
  const entries = tableData.value[step.tableId]?.entries || []
  return entries.map((e, i) => {
    const key = rowKey(e, i)
    return {
      key,
      label: e.label || '(untitled row)',
      band: bandText(e),
      binding: step.bindings.find(b => b.key === key) || null,
    }
  })
}))

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
  loadStepTables()
}

function onPickStepTable(step, tableId) {
  // A binding names a row of *this step's* table, so pointing the step at a
  // different table invalidates every one of them — keep them and they would be
  // keys the new table does not have.
  if (step.tableId !== tableId) step.bindings = []
  step.tableId = tableId
  if (!step.label) step.label = tableNames.value[tableId] || ''
  loadStepTables()
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

// ── Bindings ─────────────────────────────────────────
function addBinding(step, key) {
  if (step.bindings.some(b => b.key === key)) return
  step.bindings.push({ key, next: '', exitKind: '', exitPath: '', enroll: false, effects: [] })
}

function removeBinding(step, key) {
  step.bindings = step.bindings.filter(b => b.key !== key)
}

function onExitKind(binding) {
  if (binding.exitKind !== 'draft') binding.exitPath = ''
}

const saving = ref(false)
const error = ref('')

async function save() {
  saving.value = true
  error.value = ''
  try {
    // The editor is the caller that *does* own the wrapper, so it always sends
    // both `steps` and `entryStep` — an explicit list replaces what is stored.
    const steps = form.steps.map(s => ({
      id: s.id,
      tableId: s.tableId,
      label: s.label,
      next: s.next,
      bindings: s.bindings.map(b => ({
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
      entryTableId: form.entryTableId,
      entryStep: form.entryStep,
      steps,
      discovery: props.lp.discovery || null,
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
.lpe-root { padding: 0; display: flex; flex-direction: column; gap: 8px; }
.lpe-field { display: flex; flex-direction: column; gap: 3px; }
.lpe-field label { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.5px; }
.lpe-field input, .lpe-field textarea, .lpe-field select {
  font-size: 12px; padding: 6px 8px;
  background: var(--overlay-6); color: var(--text);
  border: 1px solid var(--overlay-10); border-radius: 6px;
  font-family: inherit; width: 100%; box-sizing: border-box;
}
.lpe-field textarea { resize: vertical; min-height: 48px; }
.lpe-hint { font-size: 9px; color: var(--text-dim); }
.lpe-error { font-size: 11px; color: var(--danger); background: var(--danger-8); padding: 6px 10px; border-radius: 4px; }

.lpe-section { display: flex; flex-direction: column; gap: 6px; margin-top: 4px; }
.lpe-subtitle { display: block; font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.5px; }
.lpe-empty { font-size: 10px; color: var(--text-dim); padding: 6px 8px; background: var(--overlay-4); border-radius: 6px; }

.lpe-step { display: flex; flex-direction: column; gap: 6px; padding: 8px; background: var(--overlay-4); border: 1px solid var(--overlay-8); border-radius: 6px; }
.lpe-step-head { display: flex; align-items: center; gap: 4px; }
.lpe-step-index { font-size: 10px; font-weight: 700; color: var(--accent); min-width: 14px; }
.lpe-step-id { flex: 1; font-family: monospace; font-size: 10px; color: var(--text-dim); }

.lpe-rows { display: flex; flex-direction: column; gap: 4px; border-top: 1px solid var(--overlay-8); padding-top: 6px; }
.lpe-row { display: flex; flex-direction: column; gap: 4px; padding: 6px; background: var(--overlay-2); border-radius: 4px; }
.lpe-row-head { display: flex; align-items: baseline; gap: 6px; }
.lpe-row-label { flex: 1; font-size: 11px; color: var(--text); }
.lpe-row-band { font-size: 9px; color: var(--text-dim); }
.lpe-row-key { font-family: monospace; font-size: 9px; color: var(--text-dim); }
.lpe-row-grid { display: flex; gap: 6px; align-items: flex-end; }
.lpe-row-grid > .lpe-field { flex: 1; }
.lpe-row-pass { display: flex; align-items: center; gap: 6px; }
.lpe-row-pass .lpe-hint { flex: 1; }
.lpe-check { display: flex; align-items: center; gap: 5px; font-size: 10px; color: var(--text-dim); }
.lpe-check input { width: auto; }
.lpe-effects { display: flex; flex-direction: column; gap: 3px; }
</style>
