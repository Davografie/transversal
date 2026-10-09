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

            <!-- The life-path connector: what this row means to the path that
                 wraps the table (a move, an exit, or the term ending). Absent
                 unless the panel was opened with a path that wraps this table. -->
            <div v-if="connectorEnabled" class="rte-connector">
              <div class="rte-connector-read">
                <span class="rte-connector-label">Next</span>
                <span class="rte-connector-dest">{{ connectorTextFor(i) }}</span>
              </div>
              <select :value="connectorTokenFor(i)" @change="onConnectorChange(i, $event.target.value)">
                <option value="follow">Follows the step's default</option>
                <option v-for="s in stepOptions" :key="s.value" :value="s.value">{{ s.label }}</option>
                <option v-if="danglingNextFor(i)" :value="danglingNextFor(i)">Unknown step ({{ danglingNextFor(i) }})</option>
                <option value="end">Ends the term</option>
                <option value="muster">Muster out</option>
                <option value="force_muster">Muster out (dishonourably)</option>
                <option value="draft">Draft to another path…</option>
              </select>
              <GmScopePicker
                v-if="connectorTokenFor(i) === 'draft'"
                :model-value="(bindingFor(i) || {}).exitPath || ''"
                :options="lifePathOptions"
                empty-label="Select path…"
                placeholder="Life path…"
                @update:model-value="setDraftPath(i, $event)"
              />
              <label v-if="bindingFor(i)" class="rte-enroll">
                <input type="checkbox" v-model="bindingFor(i).enroll" />
                Enrols in this path
              </label>
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
import { reactive, ref, computed, onMounted, watch } from 'vue'
import { useApi } from '@/composables/useApi.js'
import { useRollTables } from '@/composables/useRollTables.js'
import { useLifePaths } from '@/composables/useLifePaths.js'
import { usePanel } from '@/composables/usePanel.js'
import { usePanelBus } from '@/composables/usePanelBus.js'
import { rowKey, connectorToken, connectorText } from '@/composables/lifePathConnector.js'
import GmList from '@/components/ui/GmList.vue'
import Button from '@/components/ui/Button.vue'
import GmScopePicker from './GmScopePicker.vue'

const panel = usePanel()
const bus = usePanelBus()
const { graphql } = useApi()
const { fetchTable, saveRollTable } = useRollTables()
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
  scheme: 'INDEX',
  rollSource: 'FIXED_DIE',
  traitDiceCount: 1,
  die: 'd6',
  entries: [],
})

const saving = ref(false)
const error = ref('')
const universeOptions = ref([])
const lifePathOptions = ref([])

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

function connectorTokenFor(i) { return connectorToken(bindingFor(i)) }

function connectorTextFor(i) {
  return connectorText(bindingFor(i), { stepById: stepById.value, pathNameOf: lifePathName })
}

// A `next` the path no longer has: keep an option for it so the select shows the
// stored destination instead of silently landing on the first option.
function danglingNextFor(i) {
  const b = bindingFor(i)
  if (!b || !b.next || stepById.value.has(b.next)) return ''
  return b.next
}

function setDraftPath(i, value) {
  const b = bindingFor(i)
  if (b) b.exitPath = value
}

// The select writes one of the four connector meanings. The existing binding is
// always spread and only the connector fields (`next`, `exitKind`, `exitPath`)
// are touched: `enroll` and `effects` (the delta applied after the row's own)
// are not shown here, and dropping them would be data loss.
function onConnectorChange(i, token) {
  const e = form.entries[i]
  if (!e) return
  const key = rowKey(e, i)
  const index = stepBindings.value.findIndex(b => b.key === key)
  const prev = index >= 0 ? stepBindings.value[index] : null

  // `follow` is the *absence* of a binding — this is how one is removed.
  if (token === 'follow') {
    if (index >= 0) stepBindings.value.splice(index, 1)
    return
  }

  const binding = prev
    ? { ...prev }
    : { key, next: '', exitKind: '', exitPath: '', enroll: false, effects: [] }
  binding.key = key
  binding.next = ''
  binding.exitKind = ''
  binding.exitPath = ''
  if (token === 'muster' || token === 'force_muster') {
    binding.exitKind = token
  } else if (token === 'draft') {
    binding.exitKind = 'draft'
    binding.exitPath = (prev && prev.exitKind === 'draft' && prev.exitPath) || ''
  } else if (token !== 'end') {
    binding.next = token
  }

  // A row authored before keys existed has only a derived key, which changes
  // with its band. Pin it when a binding is made so the binding cannot move out
  // from under itself.
  if (!e.key) e.key = key

  if (index >= 0) stepBindings.value.splice(index, 1, binding)
  else stepBindings.value.push(binding)
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
  if (!props.tableId) return
  try {
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
    form.entries = (t.entries || []).map(e => ({
      // `key` is the row's stable identity and a life-path binding names it, so
      // it must survive the round trip. An empty one is filled by the API on
      // save. `costEffects` is preserved for the same reason: this panel does
      // not edit them and the entries map in save() is a full replace.
      key: e.key || '',
      costEffects: e.costEffects || [],
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
  await loadPathContext()
})

function addEntry() {
  form.entries.push({ key: '', costEffects: [], label: '', description: '', minValue: null, maxValue: null, weight: null, tier: '', conditions: [], effects: [] })
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
      scheme: form.scheme,
      rollSource: form.rollSource,
      traitDiceCount: form.traitDiceCount ?? 1,
      die: form.die,
      check: null,
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
    panel.close()
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
.rte-error { font-size: 11px; color: var(--danger); background: var(--danger-8); padding: 6px 10px; border-radius: 4px; }
</style>
