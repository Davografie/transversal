<template>
  <div
    v-if="visible"
    class="wiz-shell"
    :class="{ 'wiz-embedded': embedded }"
    @click.self="embedded ? null : close"
  >
    <div class="wiz-panel">
      <div class="wiz-header">
        <h2>{{ title }}</h2>
        <Button variant="ghost" size="icon" title="Close" @click="close">✕</Button>
      </div>

      <div class="wiz-body">
        <!-- Choose a life path. The gate is the path's own `conditions` ([[B194]]),
             and an unwalkable path is a **visible, disabled row carrying why** — never
             a hidden one. The offering faction used to gate here and does not any more
             ([[B41]]): it could not tell whether the character may walk the path, and
             it locked 7 of 10. -->
        <template v-if="step === 'choose'">
          <p class="wiz-hint">Choose a life path to take a term in.</p>
          <ChoiceTable
            :rows="pathRows"
            :loading="busy"
            stagger
            :show-cancel="false"
            empty-text="No life paths available."
            @pick="startPath"
          />
          <p v-if="error" class="wiz-error">{{ error }}</p>
        </template>

        <!-- Active term: the current table is one step of a flow, not a list.
             The surface renders the step; the phase label, `↩ Paths` and the
             term's end states below are the driver's. -->
        <template v-else-if="step === 'term'">
          <p class="wiz-phase-label">
            {{ currentTable?.name || 'Roll Table' }}
            <span class="wiz-chip">{{ currentTable?.scheme }}</span>
            <span class="wiz-chip">{{ isTraitDice ? 'trait dice' : currentTable?.die }}</span>
          </p>

          <div v-if="isTraitDice" class="wiz-traits">
            <label class="wiz-traits-label" for="wiz-trait-pick">Choose a trait to roll:</label>
            <select
              id="wiz-trait-pick"
              v-model="selectedTraitId"
              class="wiz-trait-select"
              @change="onTraitSelect"
            >
              <option value="" disabled>— select a trait —</option>
              <optgroup v-for="(group, gName) in groupedTraits" :key="gName" :label="gName">
                <option v-for="t in group" :key="t.traitId" :value="t.traitId">{{ t.name }} ({{ traitDiceLabel(t) }})</option>
              </optgroup>
            </select>
            <div v-if="!rollableTraits.length" class="wiz-empty">No rollable traits for this table.</div>
          </div>

          <!-- A roll *finds* a row and marks it; the click is what takes it. That
               is why the 🎲 is a separate control, why it exists only on a
               weighted table (every other scheme is rolled by the dice in the
               roller), and why the surface has no confirm button. -->
          <ChoiceTable
            :rows="entries"
            :scheme="currentTable?.scheme"
            :rolled-index="rolledEntryIndex"
            :roll-token="rollToken"
            :allow-random="isWeight"
            :busy="resolving"
            :show-cancel="false"
            empty-text="This table has no entries."
            @pick="continueStep"
            @roll="(row, i) => markRolled(i)"
          >
            <template #actions>
              <Button variant="neutral" size="sm" :disabled="resolving" @click="backToChoose">↩ Paths</Button>
            </template>
          </ChoiceTable>

          <div v-if="resolving" class="wiz-loading-inline">⏳ Resolving…</div>
          <p v-if="error" class="wiz-error">{{ error }}</p>

          <div v-if="lastResult" class="wiz-result-block">
            <div class="wiz-result-label">Last step: {{ lastResult.entryLabel }}</div>
            <div v-if="lastResult.applied?.length" class="wiz-applied">
              <div v-for="(a, ai) in lastResult.applied" :key="ai" class="wiz-applied-line">{{ a }}</div>
            </div>
            <div v-if="lastResult.scheduled" class="wiz-scheduled">{{ lastResult.scheduled }} deferred effect{{ lastResult.scheduled === 1 ? '' : 's' }} queued</div>
            <div v-if="lastResult.pendingChoices?.length" class="wiz-choices">pending choice{{ lastResult.pendingChoices.length > 1 ? 's' : '' }}: {{ lastResult.pendingChoices.join(', ') }}</div>
          </div>

          <details v-if="log.length" class="wiz-log">
            <summary>History ({{ log.length }})</summary>
            <div v-for="(item, li) in log" :key="li" class="wiz-log-line">
              <span class="wiz-log-label">{{ item.entryLabel }}</span>
              <span v-if="item.applied?.length" class="wiz-log-applied">{{ item.applied.join(' · ') }}</span>
            </div>
          </details>
        </template>

        <!-- Term finished / mustered -->
        <template v-else-if="step === 'done'">
          <p class="wiz-phase-label">{{ lastResult?.mustered ? 'Mustered Out' : 'Term Complete' }}</p>
          <div v-if="lastResult?.mustered" class="wiz-result wiz-good">
            {{ lastResult.mishapMuster ? '🛑 Muster out (dishonorably)' : '🎉 Muster out (respectfully)' }}
          </div>
          <div v-if="lastResult?.applied?.length" class="wiz-applied">
            <div v-for="(a, ai) in lastResult.applied" :key="ai" class="wiz-applied-line">{{ a }}</div>
          </div>
          <div v-if="lastResult?.scheduled" class="wiz-scheduled">{{ lastResult.scheduled }} deferred effect{{ lastResult.scheduled === 1 ? '' : 's' }} queued</div>
          <div class="wiz-done-actions">
            <Button variant="secondary" block @click="startOver">Take another term</Button>
            <Button variant="success" solid block @click="close">Done</Button>
          </div>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { useApi } from '@/composables/useApi.js'
import { useEffectActions } from '@/composables/useEffectActions.js'
import { usePanelBus } from '@/composables/usePanelBus.js'
import ChoiceTable from '@/components/ui/ChoiceTable.vue'
import Button from '@/components/ui/Button.vue'

// The life path: a *checkpointed flow* of roll tables, rendered one step at a
// time on [[UI-UX Design#Choice table]].
//
// What the surface does NOT know, and this driver owns: the flow's position
// (`pendingTerm`), that `Back` means "return through `return_map`" rather than a
// navigation stack, the term's end states (`muster` / `force_muster`), and that a
// shared table has more than one valid way out. What it does know is what a row
// *is* — its scheme's key, its conditions, its effects, its cost — and that a
// roll finds a row while `Continue` takes it.
//
// Name resolution is the shared one (`useLabelResolver`). This file used to
// carry its own trait map read from `traitsByUniverse(props.universe)`, which
// silently rendered raw ids — `trait-rel-tenure` is stamped `universes: ["earth"]`
// and does not resolve in a `three_realms` path — for the two traits the
// life-path ladder is built from.
const props = defineProps({
  visible: { type: Boolean, default: false },
  embedded: { type: Boolean, default: false },
  entityId: { type: String, required: true },
  universe: { type: String, default: 'earth' },
})
const emit = defineEmits(['close', 'updated'])
const { graphql } = useApi()
const { load: loadEffectActions } = useEffectActions()
const bus = usePanelBus()

const step = ref('choose') // 'choose' | 'term' | 'done'
const busy = ref(false)
const resolving = ref(false)
const error = ref('')
const paths = ref([])
const selectedPath = ref(null)
const pendingTerm = ref(null)
const currentTable = ref(null)
const lastResult = ref(null)
const log = ref([])
const traits = ref([])          // entity traitSettings — the rollable pool
const selectedTraitId = ref('')
const rolledEntryIndex = ref(null)
const rollToken = ref(0)

const title = computed(() => {
  if (step.value === 'choose') return 'Life Path'
  if (step.value === 'done') return lastResult.value?.mustered ? 'Mustered Out' : 'Term Complete'
  return selectedPath.value?.name || 'Life Path'
})
const entries = computed(() => currentTable.value?.entries || [])
const isTraitDice = computed(() => currentTable.value?.rollSource === 'TRAIT_DICE')
const isWeight = computed(() => currentTable.value?.scheme === 'WEIGHT')
const tableMax = computed(() => {
  const t = currentTable.value
  if (!t) return 0
  if (t.scheme === 'INDEX') return (t.entries || []).length
  if (t.scheme === 'RANGE') return Math.max(0, ...(t.entries || []).map(e => e.maxValue ?? 0))
  if (t.scheme === 'TIER') return 12
  return 0
})
// Only traits available in the character's current universe; out-of-range
// rolls are handled by the MOD wrap in resolveIndex().
const rollableTraits = computed(() => traits.value.filter(t => t.universe === props.universe))

/** The path list as rows: the **conditions** gate carries its reason, not a lockout.
 *
 *  The gate used to be the offering faction — a path no faction offered was disabled
 *  with *"no offering faction"* — which locked 7 of 10 live paths and gated nothing
 *  about whether the character *could* walk them ([[B41]]). Walkability is the path's
 *  own `conditions` ([[B194]]); the offering faction is now only an input to *starting*
 *  a term, never a gate. An unwalkable path stays **visible and disabled, carrying the
 *  reason** (the human, 2026-09-25), and `walkable === null` means not evaluated —
 *  which this query never is, because it always passes the entity. */
const pathRows = computed(() => paths.value.map(lp => ({
  id: lp.id,
  factionIds: lp.factionIds,
  label: lp.name,
  description: lp.description,
  locked: lp.walkable === false,
  why: (lp.unwalkableReasons || []).join('; '),
})))

const groupedTraits = computed(() => {
  const groups = {}
  for (const t of rollableTraits.value) {
    const key = t.traitsetName || 'Other'
    if (!groups[key]) groups[key] = []
    groups[key].push(t)
  }
  return groups
})

function traitDiceLabel(t) {
  const dice = (t.dice && t.dice.length) ? t.dice : [t.dieType || 'd6']
  return dice.map(d => String(d).toLowerCase()).join(' ')
}

function resolveIndex(n) {
  const t = currentTable.value
  const list = t?.entries || []
  if (!list.length) return null
  if (t.scheme === 'INDEX') {
    const len = list.length
    return ((n - 1) % len + len) % len
  }
  if (t.scheme === 'RANGE') {
    const max = tableMax.value
    const m = max > 0 ? ((n - 1) % max) + 1 : n
    const idx = list.findIndex(e => e.minValue != null && e.maxValue != null && e.minValue <= m && m <= e.maxValue)
    return idx >= 0 ? idx : null
  }
  if (t.scheme === 'TIER') {
    const tier = n <= 2 ? 'FAIL' : n <= 5 ? 'MARGINAL' : n <= 8 ? 'SUCCESS' : n <= 11 ? 'EXCEPTIONAL' : 'PERFECT'
    const idx = list.findIndex(e => e.tier === tier)
    return idx >= 0 ? idx : null
  }
  return null
}

async function loadPaths() {
  busy.value = true
  try {
    // `entityId` is what makes `walkable` an answer at all ([[B194]]): without it the
    // field is null, because a gate nobody asked about has no answer — and defaulting
    // it true would offer every path to everyone, which is the bug this replaces.
    const data = await graphql(
      `query($u:String,$eid:ID){ lifePaths(universe:$u, entityId:$eid){
         id name universe description entryTableId factionIds walkable unwalkableReasons } }`,
      { u: props.universe, eid: props.entityId },
    )
    paths.value = data?.lifePaths || []
  } finally {
    busy.value = false
  }
}

async function loadTable(tableId) {
  const data = await graphql(
    `query($id:ID!){rollTable(id:$id){id name universe lifePath scheme rollSource traitDiceCount die entries{label description minValue maxValue weight tier conditions{type subject target targets value operator narrative} costEffects{timing type action target result negative context} effects{timing type action target result negative context}}}}`,
    { id: tableId },
  )
  currentTable.value = data?.rollTable || null
  rolledEntryIndex.value = null
  selectedTraitId.value = ''
}

async function loadTraits() {
  try {
    const data = await graphql(
      `query($id:ID!){ entity(id:$id){ traitSettings{ traitId name dieType ratingType dice rating universe traitsetName } } }`,
      { id: props.entityId },
    )
    traits.value = data?.entity?.traitSettings || []
  } catch { traits.value = [] }
}

async function loadPendingTerm() {
  const data = await graphql(
    `query($id:ID!){ entity(id:$id){ pendingTerm{ factionId pathId currentTableId continuation } } }`,
    { id: props.entityId },
  )
  return data?.entity?.pendingTerm || null
}

async function startPath(lp) {
  // The faction is **not** a gate any more ([[B41]]): the checkpoint is a cursor, so a
  // path nobody offers can begin. Pass the offering faction when there is one — it is
  // the caller saying whose sect this term serves, and it wins — and otherwise omit it;
  // an enrolling row then resolves the faction from the path's own `{sect}` ([[B290]]).
  const factionId = lp?.factionIds?.[0] || null
  selectedPath.value = lp
  error.value = ''
  resolving.value = true
  try {
    const data = await graphql(
      `mutation($eid:ID!,$fid:ID,$pid:ID!){ startTerm(entityId:$eid, factionId:$fid, pathId:$pid){ factionId pathId currentTableId continuation } }`,
      { eid: props.entityId, fid: factionId, pid: lp.id },
    )
    const pt = data?.startTerm
    if (!pt) { error.value = 'Could not start term.'; return }
    pendingTerm.value = pt
    log.value = []
    lastResult.value = null
    await loadTable(pt.currentTableId)
    step.value = 'term'
    await nextTick()
    await loadTraits()
    setupRoller()
    emit('updated')
  } finally {
    resolving.value = false
  }
}

async function resolveStep({ index = null, roll = null } = {}) {
  resolving.value = true
  error.value = ''
  try {
    const vars = { eid: props.entityId }
    if (index != null) vars.index = index
    else if (roll != null) vars.roll = roll
    const data = await graphql(
      `mutation($eid:ID!,$roll:Int,$index:Int){ resolveStep(entityId:$eid, roll:$roll, index:$index){ done applied pendingChoices mustered mishapMuster pendingTerm{factionId pathId currentTableId continuation} scheduled error tableId entryLabel } }`,
      vars,
    )
    const r = data?.resolveStep
    if (!r) { const msg = 'No response from resolveStep.'; console.warn('[LifePathWizard]', msg); error.value = msg; return }
    if (r.error) { console.warn('[LifePathWizard] resolveStep error', r.error); error.value = r.error; return }
    lastResult.value = r
    log.value.push({ entryLabel: r.entryLabel, applied: r.applied, scheduled: r.scheduled, pendingChoices: r.pendingChoices })
    emit('updated')
    if (r.done || r.mustered) {
      pendingTerm.value = null
      currentTable.value = null
      step.value = 'done'
      bus.emit('roll-table:prepare', { dice: [] })
      return
    }
    pendingTerm.value = r.pendingTerm
    if (r.pendingTerm?.currentTableId) {
      await loadTable(r.pendingTerm.currentTableId)
      await nextTick()
      await loadTraits()
      setupRoller()
    } else {
      step.value = 'done'
    }
  } finally {
    resolving.value = false
  }
}

function setupRoller() {
  if (isWeight.value) {
    bus.emit('roll-table:prepare', { dice: [] })
    return
  }
  const dice = []
  if (isTraitDice.value) {
    const t = traits.value.find(x => x.traitId === selectedTraitId.value)
    if (t) {
      const ds = (t.dice && t.dice.length) ? t.dice : [t.dieType || 'd6']
      for (const d of ds) dice.push({ die: String(d).toLowerCase(), source: t.traitId, label: t.name || t.traitId })
    }
  } else {
    const d = String(currentTable.value?.die || 'd6').toLowerCase()
    dice.push({ die: d, source: 'table', label: 'table' })
  }
  bus.emit('roll-table:prepare', { dice, tableId: currentTable.value?.id })
}

function onTraitSelect() {
  rolledEntryIndex.value = null
  setupRoller()
}

/**
 * The dice in the roller rolled this step. The number selects a row through the
 * scheme's own rule (with the MOD wrap), and the row is *flashed* rather than
 * applied: the player still presses Continue, which is what makes a roll and a
 * pick two different acts in the UI rather than two buttons that do the same
 * thing.
 */
/**
 * Mark the row a roll found — and only mark it.
 *
 * The dice in the roller rolled this step, or the surface's own 🎲 did (a
 * weighted table). Either way the number selects a row through the scheme's own
 * rule and the row is **marked, never applied**: the player still clicks it, or
 * clicks a different one, and *that* is the pick. So "a roll and a pick are
 * different acts" is a property of the surface rather than a rule this file has
 * to remember.
 */
function markRolled(idx) {
  if (idx === null || idx === undefined) return
  rolledEntryIndex.value = idx
  rollToken.value += 1
  bus.emit('roll-table:resolved', {
    lifePathName: selectedPath.value?.name,
    tableName: currentTable.value?.name,
    entryLabel: entries.value[idx]?.label,
  })
}

function onRolled(result) {
  if (!result?.rolls?.length) return
  const faces = result.rolls.map(r => r.result)
  let n
  if (isTraitDice.value) {
    const t = traits.value.find(x => x.traitId === selectedTraitId.value)
    n = t?.ratingType === 'RESOURCE' ? faces.reduce((s, x) => s + x, 0) : Math.max(...faces)
  } else {
    n = faces[0]
  }
  markRolled(resolveIndex(n))
}

/** The click is the pick: `resolveStep` takes the row the player actually chose. */
function continueStep(row, i) {
  if (i === null || i === undefined) return
  resolveStep({ index: i + 1 })
}

function backToChoose() { step.value = 'choose'; error.value = ''; bus.emit('roll-table:prepare', { dice: [] }) }
function startOver() {
  selectedPath.value = null
  pendingTerm.value = null
  currentTable.value = null
  lastResult.value = null
  log.value = []
  selectedTraitId.value = ''
  rolledEntryIndex.value = null
  step.value = 'choose'
  bus.emit('roll-table:prepare', { dice: [] })
}
function close() { emit('close') }

async function init() {
  if (!props.visible) return
  error.value = ''
  await Promise.all([loadPaths(), loadEffectActions(), loadTraits()])
  const pt = await loadPendingTerm()
  if (pt?.currentTableId) {
    selectedPath.value = paths.value.find(p => p.id === pt.pathId) || null
    pendingTerm.value = pt
    await loadTable(pt.currentTableId)
    step.value = 'term'
    await nextTick()
    setupRoller()
  } else {
    step.value = 'choose'
  }
}

onMounted(() => {
  bus.on('roll-table:rolled', onRolled)
  init()
})
onUnmounted(() => {
  bus.off('roll-table:rolled', onRolled)
})
watch(() => props.visible, (v) => { if (v) init() })
</script>

<style scoped>
.wiz-shell{position:fixed;inset:0;z-index:100;background:var(--scrim);display:flex;align-items:center;justify-content:center;padding:20px}
.wiz-shell.wiz-embedded{position:static;inset:auto;background:transparent;display:flex;flex-direction:column;padding:0;z-index:auto;flex:1;min-height:0;overflow:hidden}
.wiz-panel{background:var(--bg-panel);border-radius:var(--radius);border:1px solid var(--border);width:min(560px,96vw);max-height:calc(100vh - 40px);display:flex;flex-direction:column;overflow:hidden}
.wiz-embedded .wiz-panel{width:100%;max-width:none;max-height:none;border:0;border-radius:0;background:transparent;flex:1;min-height:0}
.wiz-header{display:flex;align-items:center;justify-content:space-between;padding:12px 16px;border-bottom:1px solid var(--border);flex-shrink:0}
.wiz-header h2{font-size:15px;margin:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.wiz-body{padding:16px;flex:1;min-height:0;overflow-y:auto}
.wiz-hint{color:var(--text-dim);margin:0 0 12px;font-size:13px}
.wiz-empty{color:var(--text-dim);font-size:13px;padding:20px 0;text-align:center}
.wiz-phase-label{font-weight:700;text-transform:uppercase;letter-spacing:1px;font-size:12px;color:var(--accent);margin:0 0 8px;display:flex;align-items:center;gap:6px}
.wiz-chip{font-size:9px;color:var(--text-dim);background:var(--overlay-6);padding:1px 5px;border-radius:3px;text-transform:uppercase;font-weight:400}
.wiz-error{color: var(--danger-dim);font-size:12px;margin:8px 0 0}
.wiz-loading-inline{padding:10px;text-align:center;color:var(--text-dim);font-size:13px}
.wiz-result-block{margin-top:12px;padding:10px 12px;border:1px solid var(--border);border-radius:6px;background:var(--overlay-2)}
.wiz-result-label{font-size:11px;color:var(--text-dim);text-transform:uppercase;letter-spacing:0.5px;margin-bottom:4px}
.wiz-applied{display:flex;flex-direction:column;gap:3px}
.wiz-applied-line{font-size:12px}
.wiz-scheduled{font-size:11px;color:var(--text-dim);margin-top:4px}
.wiz-choices{font-size:11px;color: var(--warn-yellow);margin-top:4px}
.wiz-log{margin-top:12px;font-size:11px;color:var(--text-dim)}
.wiz-log summary{cursor:pointer}
.wiz-log-line{padding:2px 0;border-bottom:1px solid var(--overlay-2)}
.wiz-log-label{color:var(--text);margin-right:6px}
.wiz-log-applied{color:var(--text-dim)}
.wiz-result{padding:10px 12px;border-radius:6px;margin-bottom:8px;font-size:13px}
.wiz-good{color: var(--success-bright)}
.wiz-done-actions{display:flex;flex-direction:column;gap:4px;margin-top:12px}
.wiz-traits{display:flex;flex-direction:column;gap:4px;margin-bottom:10px}
.wiz-traits-label{font-size:11px;color:var(--text-dim);text-transform:uppercase;letter-spacing:0.5px}
.wiz-trait-select{font-size:12px;padding:6px 8px;background:var(--bg-input);color:var(--text);border:1px solid var(--border);border-radius:6px;font-family:inherit;width:100%}
.dice-roller{margin:8px 0}
</style>
