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
          <!-- Opened for one path ([[B303]]): the rule named it, so say so rather
               than dropping the player into a one-row list with no explanation. -->
          <p v-if="showingPathId" class="wiz-hint">
            A path has been offered to you. Taking a term is your choice — nothing
            starts until you pick it.
          </p>
          <p v-else class="wiz-hint">Choose a life path to take a term in.</p>
          <ChoiceTable
            :rows="pathRows"
            :loading="busy"
            stagger
            :show-cancel="false"
            empty-text="No life paths available."
            @pick="startPath"
          />
          <button v-if="showingPathId" type="button" class="wiz-show-all" @click="showAllPaths">
            Show all paths
          </button>
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

          <!-- A step's effect reached a `{choose}` ([[B314]]): the question replaces
               the table, because the step is not finished until it is answered — and
               picking another row would re-resolve *this* step and apply it twice. -->
          <EffectTargetWizard
            v-if="pendingStructured.length"
            :entity-id="entityId"
            :pending-choices="pendingStructured"
            embedded
            title="Choose"
            @resolve="answerChoices"
            @cancel="pendingStructured = []"
          />

          <template v-else>
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
          </template>

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

        <!-- A step that wraps **no table** ([[B314]]): it runs its own effects.
             There is nothing to roll, so the surface is the step and one button —
             and the effects are not run until it is pressed, exactly as a row is
             not taken until it is clicked. -->
        <template v-else-if="step === 'effect'">
          <p class="wiz-phase-label">
            {{ currentStepLabel || 'Life Path Step' }}
            <span class="wiz-chip">effects</span>
          </p>

          <EffectTargetWizard
            v-if="pendingStructured.length"
            :entity-id="entityId"
            :pending-choices="pendingStructured"
            embedded
            title="Choose"
            @resolve="answerChoices"
            @cancel="pendingStructured = []"
          />

          <template v-else>
            <p class="wiz-hint">This step runs its own effects — there is nothing to roll.</p>
            <div class="wiz-done-actions">
              <Button variant="secondary" block :disabled="resolving" @click="backToChoose">↩ Paths</Button>
              <Button variant="success" solid block :disabled="resolving" @click="runEffectsStep">
                {{ resolving ? 'Applying…' : 'Continue' }}
              </Button>
            </div>
          </template>

          <p v-if="error" class="wiz-error">{{ error }}</p>

          <div v-if="lastResult && !pendingStructured.length" class="wiz-result-block">
            <div v-if="lastResult.applied?.length" class="wiz-applied">
              <div v-for="(a, ai) in lastResult.applied" :key="ai" class="wiz-applied-line">{{ a }}</div>
            </div>
            <div v-if="lastResult.scheduled" class="wiz-scheduled">{{ lastResult.scheduled }} deferred effect{{ lastResult.scheduled === 1 ? '' : 's' }} queued</div>
          </div>
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
import EffectTargetWizard from '@/components/gm/EffectTargetWizard.vue'

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
  /**
   * Open the wizard **on one path** rather than on the whole catalogue
   * ([[B303]]). A rule that shows a life path names it, and the chooser then
   * carries that path alone with a way back to the rest.
   *
   * It narrows the *view* only: nothing is started until the player picks the
   * row, exactly as when the full list is shown. `show_life_path` is a display
   * effect — granting the path is `life_path/discover`, a different action.
   */
  initialPathId: { type: String, default: '' },
})
const emit = defineEmits(['close', 'updated'])
const { graphql } = useApi()
const { load: loadEffectActions } = useEffectActions()
const bus = usePanelBus()

const step = ref('choose') // 'choose' | 'term' | 'effect' | 'done'
// The one path the chooser is narrowed to, when the wizard was opened for a
// named path ([[B303]]). Empty = the whole catalogue.
const showingPathId = ref('')
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
// The step the term is standing on when it wraps no table, and the unanswered
// `{choose}` questions it is holding ([[B314]]). A question is not a result: while
// one is pending the step has *not* been taken, so the surface shows the picker.
const currentStepLabel = ref('')
const pendingStructured = ref([])

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
const pathRows = computed(() => paths.value
  .filter(lp => !showingPathId.value || lp.id === showingPathId.value)
  .map(lp => ({
    id: lp.id,
    factionIds: lp.factionIds,
    label: lp.name,
    description: lp.description,
    locked: lp.walkable === false,
    why: (lp.unwalkableReasons || []).join('; '),
  })))

/** Back to the whole catalogue, from a wizard that was opened on one path. */
function showAllPaths() { showingPathId.value = '' }

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
         id name universe description entryTableId factionIds walkable unwalkableReasons
         steps { id tableId label } } }`,
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
    `query($id:ID!){ entity(id:$id){ pendingTerm{ factionId pathId currentStepId currentTableId continuation } } }`,
    { id: props.entityId },
  )
  return data?.entity?.pendingTerm || null
}

/** The step the term is standing on, found on the path the chooser already loaded.
 *
 *  Why look it up rather than infer from `currentTableId`: a step with **no table**
 *  ([[B314]]) is a legal position, so "no table id" cannot mean "no step" — and the
 *  surface needs the step's label either way. `currentStepId` is the checkpoint;
 *  `currentTableId` is only a fallback for a pre-wrapper term, which names a table. */
function stepFor(pt) {
  const lp = paths.value.find(p => p.id === (pt?.pathId || ''))
  const sid = pt?.currentStepId || pt?.currentTableId || ''
  return (lp?.steps || []).find(s => s.id === sid) || null
}

/** Render wherever the term now stands — a wrapped table, or an effects-only step. */
async function showPosition(pt) {
  pendingTerm.value = pt || null
  pendingStructured.value = []
  const s = stepFor(pt)
  if (s && !s.tableId) {
    currentStepLabel.value = s.label || s.id
    currentTable.value = null
    rolledEntryIndex.value = null
    step.value = 'effect'
    return
  }
  currentStepLabel.value = ''
  if (!pt?.currentTableId) { step.value = 'done'; return }
  await loadTable(pt.currentTableId)
  step.value = 'term'
  await nextTick()
  await loadTraits()
  setupRoller()
}

/** Run an effects-only step: apply its effects, then move on. */
function runEffectsStep() { resolveStep() }

/** Answer the step's `{choose}`. The wizard echoes the effect and the answer, and
 *  the server re-resolves **only** the effects that asked, so nothing applies twice;
 *  the step advances once nothing is pending. */
function answerChoices(resolutions) {
  if (!resolutions?.length) return
  resolveStep({ resolutions })
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
    log.value = []
    lastResult.value = null
    await showPosition(pt)
    emit('updated')
  } finally {
    resolving.value = false
  }
}

async function resolveStep({ index = null, roll = null, resolutions = null } = {}) {
  resolving.value = true
  error.value = ''
  try {
    const vars = { eid: props.entityId }
    if (resolutions) {
      // The answer to a pending `{choose}`. The step's position is unchanged and the
      // server re-resolves from it, so `index`/`roll` need not be replayed.
      vars.resolutions = resolutions
    } else if (index != null) vars.index = index
    else if (roll != null) vars.roll = roll
    const data = await graphql(
      `mutation($eid:ID!,$roll:Int,$index:Int,$resolutions:[EffectTargetResolutionInput!]){
         resolveStep(entityId:$eid, roll:$roll, index:$index, resolutions:$resolutions){
           done applied pendingChoices structuredChoices mustered mishapMuster
           pendingTerm{factionId pathId currentStepId currentTableId continuation}
           scheduled error tableId entryLabel } }`,
      vars,
    )
    const r = data?.resolveStep
    if (!r) { const msg = 'No response from resolveStep.'; console.warn('[LifePathWizard]', msg); error.value = msg; return }
    if (r.error) { console.warn('[LifePathWizard] resolveStep error', r.error); error.value = r.error; return }
    lastResult.value = r
    log.value.push({ entryLabel: r.entryLabel, applied: r.applied, scheduled: r.scheduled, pendingChoices: r.pendingChoices })

    // The step asked something. It has **not** advanced — `done` is false and the
    // pending term still points at it — so the question is shown in place and the
    // step is finished only when it is answered.
    const structured = (r.structuredChoices || []).map((c, i) => ({ ...c, index: i, entity_id: props.entityId }))
    if (structured.length) {
      pendingStructured.value = structured
      emit('updated')
      return
    }
    pendingStructured.value = []

    emit('updated')
    if (r.done || r.mustered) {
      pendingTerm.value = null
      currentTable.value = null
      step.value = 'done'
      bus.emit('roll-table:prepare', { dice: [] })
      return
    }
    await showPosition(r.pendingTerm)
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

function backToChoose() {
  step.value = 'choose'
  error.value = ''
  // Leave the question unanswered rather than carry it into the chooser: the term
  // still holds its position, so reopening the wizard asks it again.
  pendingStructured.value = []
  bus.emit('roll-table:prepare', { dice: [] })
}
function startOver() {
  selectedPath.value = null
  pendingTerm.value = null
  currentTable.value = null
  lastResult.value = null
  log.value = []
  selectedTraitId.value = ''
  rolledEntryIndex.value = null
  currentStepLabel.value = ''
  pendingStructured.value = []
  step.value = 'choose'
  bus.emit('roll-table:prepare', { dice: [] })
}
function close() { emit('close') }

/** Narrow the chooser to the offered path, or to the whole catalogue.
 *
 * Called after the paths load and again whenever `initialPathId` changes: reading
 * it only at mount is not enough, because a host can hand it over late — and a
 * host that does that would get the full chooser, which is exactly what the first
 * cut did. An id nobody has falls back to the full list rather than to an empty
 * screen.
 */
function applyInitialPath() {
  showingPathId.value = (props.initialPathId && paths.value.some(p => p.id === props.initialPathId))
    ? props.initialPathId
    : ''
}

async function init() {
  if (!props.visible) return
  error.value = ''
  showingPathId.value = ''
  await Promise.all([loadPaths(), loadEffectActions(), loadTraits()])
  const pt = await loadPendingTerm()
  if (pt && (pt.currentStepId || pt.currentTableId)) {
    selectedPath.value = paths.value.find(p => p.id === pt.pathId) || null
    await showPosition(pt)
  } else {
    applyInitialPath()
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
// A host may hand the path over after the wizard has mounted (the settings panel
// does: the intro can land a tick later). Re-apply rather than keep the chooser.
watch(() => props.initialPathId, () => { if (props.visible && step.value === 'choose') applyInitialPath() })
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
/* Shown only when the wizard was opened for one path ([[B303]]) — the way back to
   the rest of the catalogue. Quiet on purpose: the offered path is the point. */
.wiz-show-all{margin-top:10px;background:none;border:0;padding:0;cursor:pointer;font:inherit;font-size:12px;color:var(--text-dim);text-decoration:underline}
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
