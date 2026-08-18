<template>
  <div class="dice-roller panel" :class="{ open: panelOpen }" @touchstart="onRollerTouchStart" @touchend="onRollerTouchEnd">
    <div class="pool-tabs" v-if="tabEntities.length > 1">
      <button
        v-for="e in tabEntities"
        :key="e.id"
        class="pool-tab"
        :class="{ active: activeId === e.id }"
        @click="switchTab(e.id)"
      >
        {{ e.id === entityId ? 'You' : e.name }}
      </button>
    </div>

    <template v-if="isSelf">
    <div class="dice-pool" v-if="isAdding()">
      <div
        v-for="(die, i) in pool"
        :key="i"
        class="die-chip"
        @click="removeDie(i)"
      >
        <DieIcon :die="die.die" :label="die.label || die.source" />
      </div>
    </div>

    <div v-if="isAdding() && mode !== 'roll_table' && gmMode" class="difficulty-presets">
      <button
        v-for="p in difficultyPresets"
        :key="p.die"
        class="difficulty-btn"
        :class="`die-btn-${p.die}`"
        @click="setDifficulty(p.die)"
      >
        {{ p.label }} (2{{ p.die }})
      </button>
    </div>

    <div class="add-die" v-if="isAdding() && mode !== 'roll_table'">
      <button v-for="d in dies" :key="d" class="die-btn" :class="`die-btn-${d}`" @click="addDie(d)">
        {{ d }}
      </button>
    </div>

    <div v-if="!gmMode && isAdding() && mode !== 'roll_table' && tabEntities.length > 1" class="contest-setup">
      <div class="contest-row">
        <label>Opponent</label>
        <select v-model="opponentId">
          <option value="" disabled>Choose…</option>
          <option v-for="e in tabEntities.filter(e => e.id !== entityId)" :key="e.id" :value="e.id">{{ e.name }}</option>
        </select>
        <button class="roll-btn contest-btn" :disabled="!opponentId || pool.length === 0" @click="doResolveContest">Resolve contest</button>
      </div>
      <div v-if="contestError" class="error">{{ contestError }}</div>
      <div v-if="contestResult" class="contest-result">
        <strong>{{ contestResult.winner === 'player' ? 'You win' : `${opponentName} wins` }}</strong>
        <div>You: total {{ contestResult.player_result.total ?? contestResult.player_result.highest }} · effect {{ contestResult.player_result.effect_die || '—' }}</div>
        <div>{{ opponentName }}: total {{ contestResult.opponent_result.total ?? contestResult.opponent_result.highest }} · effect {{ contestResult.opponent_result.effect_die || '—' }}</div>
        <div v-if="contestResult.stakes">Stakes: {{ contestResult.stakes }}</div>
      </div>
    </div>

    <div v-if="result" class="result panel">
      <!-- Roll-table roll: show the rolled dice + derived value -->
      <template v-if="mode === 'roll_table'">
        <div class="roll-dice">
          <div v-for="(r, i) in result.rolls" :key="i" class="roll-die-wrap">
            <DieIcon :die="r.die" :result="r.result" :label="r.label || r.source_id || r.die" />
          </div>
        </div>
        <div class="result-line">
          highest <strong>{{ rollTableHighest }}</strong>
          <span v-if="result.rolls.length > 1"> · sum <strong>{{ rollTableSum }}</strong></span>
        </div>
      </template>
      <!-- Simplified result -->
      <template v-else-if="result.pipeline === 'simplified'">
        <div class="result-line">
          {{ result.highest }} → <strong>{{ result.tier }}</strong>
          <span v-if="result.effect_die"> (effect: {{ result.effect_die }})</span>
        </div>
      </template>

      <!-- Dice Pool: picking phase (interactive) -->
      <template v-else-if="isPicking()">
        <div class="pool-result">
          <div class="roll-dice">
            <div
              v-for="(r, i) in result.rolls"
              :key="i"
              class="roll-die-wrap"
              :class="[rollClass(i)]"
              :draggable="!isHitch(i)"
              @dragstart="onDieDragStart($event, i)"
              @touchstart="onDieTouchStart($event, i)"
              @click="toggleDie(i)"
            >
              <DieIcon :die="r.die" :result="r.result" :is-hitch="isHitch(i)" :label="r.label || r.source_id || r.die" />
            </div>
          </div>
          <div class="selection-row">
            <span class="sel-label" @click="assignBestTotal">Total:</span>
            <span
              v-for="(idx, i) in selection.total" :key="'t'+i"
              class="sel-slot total-slot"
              :class="{ empty: idx === null, selected: selectedSlot?.type === 'total' && selectedSlot?.index === i }"
              @dragover.prevent
              @drop="onSlotDrop('total', i, $event)"
              @click="idx !== null ? clearSlot('total', i) : selectSlot('total', i)"
            >
              {{ idx !== null ? result.rolls[idx].result : '' }}
            </span>
            <span class="sel-value">= <strong>{{ computedTotal }}</strong></span>
          </div>
          <div class="selection-row" v-if="!gmMode">
            <span class="sel-label" @click="assignBestEffect">Effect:</span>
            <span
              v-for="(idx, i) in selection.effect" :key="'e'+i"
              class="sel-slot effect-slot"
              :class="{ empty: idx === null, filled: idx !== null, selected: selectedSlot?.type === 'effect' && selectedSlot?.index === i }"
              @dragover.prevent
              @drop="onSlotDrop('effect', i, $event)"
              @click="idx !== null ? clearSlot('effect', i) : selectSlot('effect', i)"
            >
              <DieIcon v-if="idx !== null" :die="result.rolls[idx].die" class="effect-die-icon" />
              <span v-else class="empty-text"></span>
            </span>
          </div>
        </div>
      </template>

      <!-- Dice Pool: resolved phase (read-only) -->
      <template v-else>
        <div class="resolved-result">
          <strong class="resolved-total">{{ computedTotal }}</strong>
          <DieIcon v-if="effectDie" :die="effectDie" class="resolved-eff-die" />
        </div>
      </template>

      <div v-if="oppositionValue !== null" class="opposition-result">
        vs difficulty <strong>{{ oppositionValue }}</strong>
        <span v-if="!isPicking()" :class="beatsOpposition ? 'outcome-success' : 'outcome-fail'">
          — {{ beatsOpposition ? 'Success' : 'Failure' }}
        </span>
      </div>

      <div v-if="result.botch" class="botch">BOTCH</div>
      <div v-if="result.hitches?.length" class="hitches">
        {{ result.hitches.length }} hitch{{ result.hitches.length > 1 ? 'es' : '' }}
      </div>
      <div v-if="result.challenge_result" class="challenge">
        Challenge: {{ result.challenge_result.outcome }}
      </div>
    </div>

    <div class="controls" v-if="isAdding() || isPicking()">
      <button v-if="isAdding()" @click="doRoll" :disabled="loading || pool.length === 0" class="roll-btn">
        {{ loading ? 'Rolling…' : 'Roll' }}
      </button>
      <button v-if="isPicking()" @click="commitPicks" class="roll-btn commit-btn">
        Done
      </button>
    </div>

    <div class="controls" v-if="isResolved() && mode !== 'roll_table'">
      <button @click="clearResult" class="roll-btn">New Pool</button>
      <button v-if="!gmMode" @click="showConsequences = !showConsequences" class="roll-btn">{{ showConsequences ? 'Hide consequences' : 'Consequences' }}</button>
    </div>

    <div v-if="showConsequences && isResolved()" class="consequence-panel">
      <div class="consequence-side">
        <label>Menu</label>
        <select v-model="consequenceSide">
          <option value="player">Player</option>
          <option value="gm">GM</option>
        </select>
      </div>
      <ConsequenceMenu :entity-id="entityId" :side="consequenceSide" :effect-die="consequenceEffectDie" @close="showConsequences = false" />
    </div>

    <div v-if="!gmMode && sfxChoiceRequest && sfxChoiceRequest.length" class="sfx-choice-panel">
      <EffectTargetWizard
        :entity-id="entityId"
        :pending-choices="sfxChoiceRequest"
        title="SFX choice"
        @resolve="resolveSfxChoices"
        @cancel="clearSfxChoices"
      />
    </div>

    <div v-if="error" class="error">{{ error }}</div>
    </template>

    <template v-else>
      <div class="peer-pool">
        <div class="peer-pool-title">{{ activeName }}</div>
        <div class="dice-pool">
          <div v-for="(die, i) in viewPool" :key="i" class="die-chip">
            <DieIcon :die="die.die" :label="die.label || die.source_id || die.die" />
          </div>
          <div v-if="!viewPool.length" class="empty-pool">No dice assembled</div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch, onMounted, onUnmounted } from 'vue'
import { useApi } from '../composables/useApi.js'
import { useEffectApplication } from '../composables/useEffectApplication.js'
import DieIcon from './DieIcon.vue'
import ConsequenceMenu from './gm/ConsequenceMenu.vue'
import EffectTargetWizard from './gm/EffectTargetWizard.vue'

const props = defineProps({
  entityId: { type: String, default: 'kael-1' },
  universe: { type: String, default: 'earth' },
  keepCount: { type: Number, default: 2 },
  effectCount: { type: Number, default: 1 },
  mode: { type: String, default: 'cortex' }, // 'cortex' | 'roll_table'
  gmMode: { type: Boolean, default: false },
  difficulty: { type: Number, default: null }, // received difficulty (player mode)
  playerId: { type: String, default: '' },
  locationId: { type: String, default: '' },
  sfxChoiceRequest: { type: Array, default: () => [] }, // pending {choose_*} auto-fired SFX choices
  peers: { type: Array, default: () => [] }, // [{ id, name }] other entities at the location
})

const emit = defineEmits(['update:universe', 'rolled', 'poolChange', 'phaseChange', 'picked', 'panelOpen', 'difficulty', 'sfx-choice-resolved'])

const { loading, error, roll: apiRoll, savePool: apiSavePool, getPool: apiGetPool, setOpposition: apiSetOpposition, resolveContest: apiResolveContest } = useApi()
const { resolveEffectTargets } = useEffectApplication()
const pool = reactive([])
const result = ref(null)
const dies = ['d4', 'd6', 'd8', 'd10', 'd12']
const difficultyPresets = [
  { label: 'Very Easy', die: 'd4' },
  { label: 'Easy', die: 'd6' },
  { label: 'Challenging', die: 'd8' },
  { label: 'Hard', die: 'd10' },
  { label: 'Very Hard', die: 'd12' },
]
const panelOpen = ref(false)
const showConsequences = ref(false)
const consequenceSide = ref('player')

// ── GM roll purpose + per-entity pool tabs ───────────
const poolPurpose = ref(null) // GM mode: 'difficulty' | 'gmc' | null
const activeId = ref(props.entityId)
const viewPool = ref([])
const opponentId = ref('')
const contestResult = ref(null)
const contestError = ref('')

const tabEntities = computed(() => {
  const seen = new Set([props.entityId])
  const list = [{ id: props.entityId, name: 'You' }]
  for (const p of (props.peers || [])) {
    if (p && p.id && !seen.has(p.id)) {
      seen.add(p.id)
      list.push({ id: p.id, name: p.name || p.id })
    }
  }
  return list
})
const isSelf = computed(() => activeId.value === props.entityId)
const activeName = computed(() => tabEntities.value.find(e => e.id === activeId.value)?.name || activeId.value)
const opponentName = computed(() => tabEntities.value.find(e => e.id === opponentId.value)?.name || 'Opponent')

function markPurpose(kind) {
  if (pool.length === 0) poolPurpose.value = kind
}

async function switchTab(id) {
  activeId.value = id
  if (id === props.entityId) return
  viewPool.value = []
  if (!props.locationId) return
  const res = await apiGetPool(props.locationId, id)
  viewPool.value = res?.dice || []
}

watch(() => props.entityId, (id) => {
  activeId.value = id
})

async function doResolveContest() {
  if (!opponentId.value) return
  contestError.value = ''
  contestResult.value = null
  if (!props.locationId) return
  await apiSetOpposition(props.locationId, props.entityId, opponentId.value, props.universe)
  const res = await apiResolveContest(props.locationId, props.entityId)
  if (res?.error) {
    contestError.value = res.error
    return
  }
  contestResult.value = res
}

async function resolveSfxChoices(resolutions) {
  await resolveEffectTargets(props.entityId, resolutions)
  emit('sfx-choice-resolved')
}
function clearSfxChoices() {
  emit('sfx-choice-resolved')
}
watch(panelOpen, (v) => emit('panelOpen', v))

let rollerTouchY = 0
function onRollerTouchStart(e) {
  rollerTouchY = e.touches[0].clientY
}
function onRollerTouchEnd(e) {
  const dy = e.changedTouches[0].clientY - rollerTouchY
  if (dy > 40 && panelOpen.value && phase.value !== Phase.PICKING) {
    panelOpen.value = false        // swipe down → close (disabled during picking)
  } else if (dy < -40 && !panelOpen.value) {
    panelOpen.value = true         // swipe up → open
  }
}

// ── Phases ──────────────────────────────────────────
const Phase = { ADDING: 'adding', ROLLING: 'rolling', PICKING: 'picking', RESOLVED: 'resolved' }
const phase = ref(Phase.ADDING)

function setPhase(p) {
  phase.value = p
  emit('phaseChange', p)
  if (p !== Phase.ADDING) panelOpen.value = true  // show results
}

function isAdding()  { return phase.value === Phase.ADDING }
function isRolling() { return phase.value === Phase.ROLLING }
function isPicking() { return phase.value === Phase.PICKING }
function isResolved(){ return phase.value === Phase.RESOLVED }

// Dice pool die selection (only used for pool pipeline)
const selection = reactive({ total: [], effect: [] })

function ensureSlots() {
  while (selection.total.length < props.keepCount) selection.total.push(null)
  while (selection.total.length > props.keepCount) selection.total.pop()
  while (selection.effect.length < props.effectCount) selection.effect.push(null)
  while (selection.effect.length > props.effectCount) selection.effect.pop()
}

watch([() => props.keepCount, () => props.effectCount], () => {
  if (result.value?.pipeline === 'pool') ensureSlots()
})

function setUniverse(u) {
  emit('update:universe', u)
}

function persistPool() {
  if (props.gmMode || !props.entityId || !props.locationId) return
  const dice = pool.map(d => ({
    die: d.die,
    source_kind: d.sourceKind || 'manual',
    source_id: d.tsId || d.source || '',
    label: d.label || d.source || d.die,
    ts_id: d.tsId || null,
  }))
  apiSavePool(props.locationId, props.entityId, dice)
}

function notifyPool() {
  persistPool()
  emit('poolChange', pool.map(d => ({ die: d.die, label: d.label || d.source || d.die, tsId: d.tsId })).filter(d => d.label))
}

function addDie(die) {
  markPurpose('difficulty')
  pool.push({ die, source: '', label: die, sourceKind: 'manual' })
  notifyPool()
  panelOpen.value = true
}

function removeDie(i) {
  pool.splice(i, 1)
  notifyPool()
}

function setDifficulty(die) {
  // GM difficulty: replace the two difficulty dice, keep any trait dice.
  poolPurpose.value = 'difficulty'
  const traitDice = pool.filter(d => d.source !== 'difficulty')
  pool.splice(0, pool.length)
  pool.push(
    { die, source: 'difficulty', label: `${die} difficulty`, sourceKind: 'difficulty' },
    { die, source: 'difficulty', label: `${die} difficulty`, sourceKind: 'difficulty' },
    ...traitDice,
  )
  panelOpen.value = true
  notifyPool()
}

function addFromSheet({ die, source, label, tsId }) {
  // Toggle: if the trait is in the pool, remove it; otherwise add it
  const idx = pool.findIndex(d => d.tsId && d.tsId === tsId)
  if (idx !== -1) {
    pool.splice(idx, 1)
  } else {
    markPurpose('gmc')
    pool.push({ die, source, label: label || source, tsId: tsId || null, sourceKind: 'trait' })
    panelOpen.value = true
  }
  notifyPool()
}

function removeBySource(source) {
  const idx = pool.findIndex(d => d.source === source)
  if (idx !== -1) { pool.splice(idx, 1); notifyPool() }
}

function removeByTsId(tsId) {
  if (!tsId) return
  const idx = pool.findIndex(d => d.tsId === tsId)
  if (idx !== -1) { pool.splice(idx, 1); notifyPool() }
}

const DIE_STEP = { d12: 'd10', d10: 'd8', d8: 'd6', d6: 'd4', d4: null }

function splitDie({ source, label }) {
  const idx = pool.findIndex(d => d.source === source)
  if (idx === -1) return
  const die = pool[idx].die
  const tsId = pool[idx].tsId
  const smaller = DIE_STEP[die]
  if (!smaller) return
  pool.splice(idx, 1)
  pool.push({ die: smaller, source: `${source}-a`, label: `${label} A`, tsId, sourceKind: 'trait' })
  pool.push({ die: smaller, source: `${source}-b`, label: `${label} B`, tsId, sourceKind: 'trait' })
  notifyPool()
}

defineExpose({ addFromSheet, removeBySource, removeByTsId, splitDie, clearPool, panelOpen })

function isHitch(idx) {
  if (!result.value) return false
  const r = result.value.rolls[idx]
  return r ? r.result === 1 : false
}

function toggleDie(idx) {
  if (!result.value || result.value.pipeline !== 'pool') return
  if (isHitch(idx)) return
  ensureSlots()

  // If die is already placed, remove it
  const tIdx = selection.total.indexOf(idx)
  if (tIdx !== -1) { selection.total[tIdx] = null; selectedSlot.value = null; return }
  const eIdx = selection.effect.indexOf(idx)
  if (eIdx !== -1) { selection.effect[eIdx] = null; selectedSlot.value = null; return }

  // If a slot is selected, place die there
  if (selectedSlot.value) {
    const { type, index } = selectedSlot.value
    if (selection[type][index] === null) {
      selection[type][index] = idx
      selectedSlot.value = null
      return
    }
  }

  // Fallback: auto-assign to first empty total, then effect
  const emptyTotal = selection.total.indexOf(null)
  if (emptyTotal !== -1) { selection.total[emptyTotal] = idx }
  else {
    const emptyEffect = selection.effect.indexOf(null)
    if (emptyEffect !== -1) { selection.effect[emptyEffect] = idx }
  }
}

function clearSlot(type, i) {
  if (type === 'total') selection.total[i] = null
  else selection.effect[i] = null
}

// ── Slot selection ─────────────────────────────────

const selectedSlot = ref(null)  // { type: 'total'|'effect', index: number }

function selectSlot(type, i) {
  if (selectedSlot.value?.type === type && selectedSlot.value?.index === i) {
    selectedSlot.value = null
  } else {
    selectedSlot.value = { type, index: i }
  }
}

// ── Drag-and-drop (mouse + touch) ──────────────────

const dragDieIndex = ref(null)
const touchDrag = ref(null)  // { dieIdx, el, startX, startY, ghost }
const ghostEl = ref(null)

function onDieDragStart(e, idx) {
  dragDieIndex.value = idx
  e.dataTransfer.effectAllowed = 'move'
  e.dataTransfer.setData('text/plain', String(idx))
}

function onDieTouchStart(e, idx) {
  if (isHitch(idx)) return
  e.preventDefault()
  const touch = e.touches[0]
  const el = e.currentTarget
  const rect = el.getBoundingClientRect()

  // Create ghost clone
  const ghost = el.cloneNode(true)
  ghost.style.position = 'fixed'
  ghost.style.left = (touch.clientX - rect.width / 2) + 'px'
  ghost.style.top = (touch.clientY - rect.height / 2) + 'px'
  ghost.style.zIndex = '100'
  ghost.style.pointerEvents = 'none'
  ghost.style.opacity = '0.85'
  ghost.style.transform = 'scale(1.2)'
  document.body.appendChild(ghost)

  touchDrag.value = { dieIdx: idx, el, ghost, startX: touch.clientX, startY: touch.clientY }
  el.style.opacity = '0.3'
}

function onDocTouchMove(e) {
  if (!touchDrag.value) return
  e.preventDefault()
  const touch = e.touches[0]
  const ghost = touchDrag.value.ghost
  ghost.style.left = (touch.clientX - 18) + 'px'
  ghost.style.top = (touch.clientY - 20) + 'px'
}

function onDocTouchEnd(e) {
  if (!touchDrag.value) return
  const { dieIdx, el, ghost } = touchDrag.value
  touchDrag.value = null
  el.style.opacity = ''
  ghost.remove()

  // Find which slot the touch ended on
  const touch = e.changedTouches[0]
  const target = document.elementFromPoint(touch.clientX, touch.clientY)
  const slot = target?.closest('.sel-slot')
  if (!slot) return

  const type = slot.classList.contains('total-slot') ? 'total' : 'effect'
  const slots = Array.from(slot.parentElement.querySelectorAll('.sel-slot'))
  const slotIndex = slots.indexOf(slot)
  if (slotIndex < 0 || slotIndex >= selection[type].length) return  // out of bounds

  // Remove die from any existing slot
  const tIdx = selection.total.indexOf(dieIdx)
  if (tIdx !== -1) selection.total[tIdx] = null
  const eIdx = selection.effect.indexOf(dieIdx)
  if (eIdx !== -1) selection.effect[eIdx] = null

  // Swap if target slot occupied
  const existing = selection[type][slotIndex]
  if (existing !== null) {
    selection[type][slotIndex] = null
  }

  selection[type][slotIndex] = dieIdx
}

function onSlotDrop(type, slotIndex, e) {
  const dieIdx = dragDieIndex.value
  dragDieIndex.value = null
  if (dieIdx === null || dieIdx === undefined) return

  // Remove die from any existing slot
  const tIdx = selection.total.indexOf(dieIdx)
  if (tIdx !== -1) selection.total[tIdx] = null
  const eIdx = selection.effect.indexOf(dieIdx)
  if (eIdx !== -1) selection.effect[eIdx] = null

  // If target slot has a die, swap it back to unpicked
  const existing = selection[type][slotIndex]
  if (existing !== null) {
    selection[type][slotIndex] = null
  }

  // Place die in target slot
  selection[type][slotIndex] = dieIdx
}

// ── Auto-assign ────────────────────────────────────

const dieRank = { d4: 1, d6: 2, d8: 3, d10: 4, d12: 5 }

/** Generate all combinations of size k from array arr. */
function* combinations(arr, k) {
  if (k === 0) { yield []; return }
  for (let i = 0; i <= arr.length - k; i++) {
    for (const tail of combinations(arr.slice(i + 1), k - 1)) {
      yield [arr[i], ...tail]
    }
  }
}

/** Score an effect combo: (die rank sum, negative sum of results) — higher is better.
 *  Ties on die type go to the combo whose effect dice have lower results
 *  (so higher results stay in the total). */
function effectScore(effectIndices, rolls) {
  let rankSum = 0, negResultSum = 0
  for (const i of effectIndices) {
    rankSum += dieRank[rolls[i].die] || 0
    negResultSum -= rolls[i].result
  }
  return [rankSum, negResultSum]
}

/**
 * Best Total: maximize total first, then maximize effect quality.
 * Among all combos achieving the same max total, pick the one
 * whose effect dice are largest (and within same type, the lower-rolling ones
 * so better results stay in the total).
 */
function assignBestTotal() {
  if (!result.value || result.value.pipeline !== 'pool') return
  clearAllSlots()
  const r = result.value.rolls
  const valid = r.map((roll, i) => isHitch(i) ? -1 : i).filter(i => i !== -1)
  const K = Math.min(props.keepCount, valid.length)
  const E = Math.min(props.effectCount, valid.length - K)
  if (K === 0) return

  let bestTotal = -1
  let bestEffScore = null
  let bestTotalCombo = null
  let bestEffCombo = null

  for (const totalCombo of combinations(valid, K)) {
    const total = totalCombo.reduce((s, i) => s + r[i].result, 0)
    const used = new Set(totalCombo)
    const remaining = valid.filter(i => !used.has(i))
    if (E === 0) {
      if (total > bestTotal) {
        bestTotal = total; bestTotalCombo = totalCombo; bestEffCombo = []
      }
      continue
    }
    for (const effCombo of combinations(remaining, E)) {
      const effSc = effectScore(effCombo, r)
      const cmp = total !== bestTotal ? total - bestTotal
        : bestEffScore ? (effSc[0] !== bestEffScore[0] ? effSc[0] - bestEffScore[0] : effSc[1] - bestEffScore[1])
        : 1
      if (cmp > 0 || bestTotal === -1) {
        bestTotal = total
        bestEffScore = effSc
        bestTotalCombo = totalCombo
        bestEffCombo = effCombo
      }
    }
  }

  // Single-effect: re-sort by die type desc, result asc for the case
  // where we already have best total, just need best single effect
  if (E > 0 && bestTotalCombo) {
    for (let i = 0; i < bestTotalCombo.length; i++) selection.total[i] = bestTotalCombo[i]
    for (let i = 0; i < bestEffCombo.length; i++) selection.effect[i] = bestEffCombo[i]
  } else if (bestTotalCombo) {
    for (let i = 0; i < bestTotalCombo.length; i++) selection.total[i] = bestTotalCombo[i]
  }
}

/**
 * Best Effect: maximize effect quality first, then maximize total.
 * Prefers largest die types for effect; within same type, prefers
 * the lower-rolling die so better results stay in the total.
 */
function assignBestEffect() {
  if (!result.value || result.value.pipeline !== 'pool') return
  clearAllSlots()
  const r = result.value.rolls
  const valid = r.map((roll, i) => isHitch(i) ? -1 : i).filter(i => i !== -1)
  const E = Math.min(props.effectCount, valid.length)
  const K = Math.min(props.keepCount, valid.length - E)
  if (E === 0) return

  let bestEffScore = null
  let bestTotal = -1
  let bestEffCombo = null
  let bestTotalCombo = null

  for (const effCombo of combinations(valid, E)) {
    const effSc = effectScore(effCombo, r)
    const used = new Set(effCombo)
    const remaining = valid.filter(i => !used.has(i))
    if (K === 0) {
      if (!bestEffScore || effSc[0] > bestEffScore[0] || (effSc[0] === bestEffScore[0] && effSc[1] > bestEffScore[1])) {
        bestEffScore = effSc; bestEffCombo = effCombo; bestTotalCombo = []
      }
      continue
    }
    for (const totalCombo of combinations(remaining, K)) {
      const total = totalCombo.reduce((s, i) => s + r[i].result, 0)
      const cmp = !bestEffScore ? 1
        : effSc[0] !== bestEffScore[0] ? effSc[0] - bestEffScore[0]
        : effSc[1] !== bestEffScore[1] ? effSc[1] - bestEffScore[1]
        : total - bestTotal
      if (cmp > 0) {
        bestEffScore = effSc
        bestTotal = total
        bestEffCombo = effCombo
        bestTotalCombo = totalCombo
      }
    }
  }

  if (bestEffCombo) {
    for (let i = 0; i < bestEffCombo.length; i++) selection.effect[i] = bestEffCombo[i]
    for (let i = 0; i < bestTotalCombo.length; i++) selection.total[i] = bestTotalCombo[i]
  }
}

function clearAllSlots() {
  for (let i = 0; i < selection.total.length; i++) selection.total[i] = null
  for (let i = 0; i < selection.effect.length; i++) selection.effect[i] = null
}

const nextSlot = computed(() => {
  if (selection.total.includes(null)) return 'total'
  if (selection.effect.includes(null)) return 'effect'
  return ''
})

function rollClass(idx) {
  if (selection.total.includes(idx)) return 'selected-total'
  if (selection.effect.includes(idx)) return 'selected-effect'
  return ''
}

const computedTotal = computed(() => {
  if (!result.value || result.value.pipeline !== 'pool') return 0
  const r = result.value.rolls
  return selection.total.reduce((sum, idx) => sum + (idx !== null ? r[idx].result : 0), 0)
})

const rollTableHighest = computed(() => {
  const r = result.value?.rolls || []
  return r.length ? Math.max(...r.map(x => x.result)) : 0
})

const rollTableSum = computed(() => {
  const r = result.value?.rolls || []
  return r.reduce((s, x) => s + x.result, 0)
})

const effectDie = computed(() => {
  if (!result.value || result.value.pipeline !== 'pool') return null
  const idx = selection.effect.find(i => i !== null)
  return idx !== undefined && idx !== null ? result.value.rolls[idx].die : null
})

// Effect die for the consequence menu: pool uses the picked die, simplified
// uses the resolver's effect_die.
const consequenceEffectDie = computed(() => {
  if (!result.value) return ''
  if (result.value.pipeline === 'pool') return effectDie.value || ''
  return result.value.effect_die || ''
})

const oppositionValue = computed(() => {
  const r = result.value
  if (!r) return null
  if (r.opposition_total != null) return r.opposition_total
  if (r.opposition_roll && r.opposition_roll.result != null) return r.opposition_roll.result
  return null
})

const rollTotal = computed(() => {
  if (!result.value) return 0
  if (result.value.pipeline === 'pool') return computedTotal.value
  return result.value.highest ?? 0
})

const beatsOpposition = computed(() => {
  if (oppositionValue.value == null) return null
  return rollTotal.value > oppositionValue.value
})

async function doRoll() {
  setPhase(Phase.ROLLING)
  const dice = pool.map(d => ({
    die: d.die,
    source_kind: d.sourceKind || 'manual',
    source_id: d.tsId || d.source || '',
    label: d.label || d.source || d.die,
    ts_id: d.tsId || null,
  }))
  const opp = (!props.gmMode && props.difficulty != null)
    ? { type: 'static_difficulty', static_difficulty: props.difficulty }
    : null
  const pipeline = (props.gmMode && poolPurpose.value === 'difficulty') ? 'pool' : null
  result.value = await apiRoll(props.entityId, props.universe, dice, opp, pipeline)
  pool.length = 0
  notifyPool()
  if (result.value?.pipeline === 'pool' && props.mode !== 'roll_table') {
    setPhase(Phase.PICKING)
    ensureSlots()
  } else {
    setPhase(Phase.RESOLVED)
  }
  emit('rolled', result.value)
}

function commitPicks() {
  setPhase(Phase.RESOLVED)
  if (props.gmMode) {
    // GM difficulty roll: the picked total is the difficulty.
    emit('difficulty', computedTotal.value)
    return
  }
  // Player: emit final picked result for sharing
  if (result.value?.pipeline === 'pool') {
    const r = result.value.rolls
    const total = selection.total.reduce((sum, idx) => sum + (idx !== null ? r[idx].result : 0), 0)
    const effIdx = selection.effect[0]
    const effDie = effIdx !== null ? r[effIdx].die : 'd4'
    emit('picked', { total, effect_die: effDie, pipeline: 'pool', botch: result.value.botch })
  } else if (result.value) {
    emit('picked', result.value)
  }
}

function clearResult() {
  result.value = null
  selection.total = []
  selection.effect = []
  setPhase(Phase.ADDING)
}

function clearPool() {
  pool.splice(0, pool.length)
  result.value = null
  selection.total = []
  selection.effect = []
  poolPurpose.value = null
  contestResult.value = null
  contestError.value = ''
  setPhase(Phase.ADDING)
  notifyPool()
}

async function restorePool() {
  if (props.gmMode || !props.entityId || !props.locationId) return
  const res = await apiGetPool(props.locationId, props.entityId)
  const dice = res?.dice || []
  pool.splice(0, pool.length)
  for (const d of dice) {
    pool.push({
      die: d.die,
      source: d.source_id || d.source || '',
      label: d.label || d.die,
      tsId: d.ts_id || null,
      sourceKind: d.source_kind || 'manual',
    })
  }
  notifyPool()
  if (dice.length) panelOpen.value = true
}

onMounted(() => {
  console.log('[diag] DiceRoller mounted', { entityId: props.entityId, universe: props.universe })
  document.addEventListener('touchmove', onDocTouchMove, { passive: false })
  document.addEventListener('touchend', onDocTouchEnd)
  restorePool()
})

watch([() => props.entityId, () => props.locationId], restorePool)
onUnmounted(() => {
  document.removeEventListener('touchmove', onDocTouchMove)
  document.removeEventListener('touchend', onDocTouchEnd)
})
</script>

<style scoped>
.dice-roller {
  position: relative;
  width: 100%;
  z-index: 10;
  display: flex;
  flex-direction: column;
  gap: var(--gap);
}

.phase-bar {
  text-align: center; margin-top: 4px;
}
.drag-handle {
  cursor: grab; padding: 10px 0; border-top: 2px solid rgba(255,255,255,0.1);
  min-height: 44px; display: flex; align-items: center; justify-content: center;
  -webkit-tap-highlight-color: transparent;
  touch-action: none;
  user-select: none;
  flex-shrink: 0;
}
.phase-label {
  font-size: 10px; text-transform: uppercase; letter-spacing: 2px;
  color: var(--text-dim); background: rgba(255,255,255,0.05);
  padding: 2px 12px; border-radius: 4px;
}

h3 { font-size: 14px; color: var(--text-dim); margin-bottom: 4px; }

.commit-btn { background: var(--success) !important; color: #0a0a0f !important; }

.dice-pool { display: flex; flex-wrap: wrap; gap: 6px; min-height: 28px; }

.pool-tabs { display: flex; gap: 6px; flex-wrap: wrap; justify-content: center; }
.pool-tab {
  padding: 6px 10px; font-size: 12px; font-weight: 600; border-radius: 8px;
  cursor: pointer; border: 1px solid transparent; background: rgba(255,255,255,0.06);
  color: var(--text-dim);
}
.pool-tab.active { background: var(--accent, #7aa2f7); color: #0a0a0f; }

.contest-setup { margin-top: 4px; display: flex; flex-direction: column; gap: 6px; }
.contest-row { display: flex; gap: 6px; align-items: center; }
.contest-row label { font-size: 12px; color: var(--text-dim); white-space: nowrap; }
.contest-row select { flex: 1; padding: 6px; border-radius: 6px; background: rgba(255,255,255,0.06); color: var(--text); border: 1px solid rgba(255,255,255,0.15); }
.contest-btn { flex: 0 0 auto; padding: 6px 10px; font-size: 12px; }
.contest-result { font-size: 13px; display: flex; flex-direction: column; gap: 2px; }

.peer-pool { display: flex; flex-direction: column; gap: 8px; }
.peer-pool-title { font-size: 12px; text-transform: uppercase; letter-spacing: 1px; color: var(--text-dim); }
.empty-pool { font-size: 12px; color: var(--text-dim); opacity: 0.7; }

.die-chip {
  cursor: pointer; transition: opacity 0.2s;
}
.die-chip:hover { opacity: 0.7; }

.add-die { display: flex; gap: 6px; justify-content: center; }
.die-btn {
  flex: 1; padding: 8px 4px; font-size: 14px; font-weight: 700;
  border-radius: 8px; cursor: pointer; transition: all 0.15s;
  border: 2px solid transparent; background: rgba(255,255,255,0.06);
  color: var(--text);
}
.die-btn:hover { background: rgba(255,255,255,0.12); border-color: var(--accent-dim); }
.die-btn-d4  { color: #e88830; }
.die-btn-d6  { color: #e0e0e0; }
.die-btn-d8  { color: #d44040; }
.die-btn-d10 { color: #4088d4; }
.die-btn-d12 { color: #40b860; }

.controls { display: flex; gap: 8px; }
.consequence-panel { display: flex; flex-direction: column; gap: 6px; margin-top: 8px; }
.sfx-choice-panel { margin-top: 8px; }
.consequence-side { display: flex; align-items: center; gap: 6px; font-size: 10px; color: var(--text-dim); }
.consequence-side select { font-size: 11px; padding: 3px 6px; background: rgba(255,255,255,0.06); color: var(--text); border: 1px solid rgba(255,255,255,0.12); border-radius: 4px; }
.roll-btn { width: 100%; font-size: 18px; font-weight: 700; padding: 10px; }

.result { text-align: center; }
.result-line { font-size: 16px; display: flex; align-items: center; justify-content: center; gap: 6px; }
.result-line strong { font-size: 24px; color: var(--accent); }
.result-eff-icon { width: 28px; height: 32px; }

.resolved-result {
  display: flex; align-items: center; justify-content: center; gap: 16px; padding: 8px 0;
}
.resolved-total {
  font-size: 48px; font-weight: 800; color: var(--accent);
  text-shadow: 0 2px 8px rgba(64,136,212,0.3);
  line-height: 1;
}
.resolved-eff-die {
  width: 72px; height: 80px;
}

.botch {
  color: var(--danger); font-size: 20px; font-weight: 800;
  text-transform: uppercase; letter-spacing: 4px; margin-top: 6px;
}

.hitches { color: var(--warn); font-size: 13px; }
.challenge { color: var(--text-dim); font-size: 13px; margin-top: 4px; }
.error { color: var(--danger); font-size: 13px; }

/* Pool result with die selection */
.pool-result {
  display: flex; flex-direction: column; gap: 6px;
}

.roll-dice {
  display: flex; flex-wrap: wrap; gap: 6px; justify-content: center;
}

.roll-die-wrap {
  cursor: grab; transition: all 0.15s;
  border-radius: 8px; border: 2px solid transparent;
  padding: 2px;
  user-select: none;
  -webkit-user-select: none;
  -webkit-user-drag: element;
  touch-action: none;
}
.roll-die-wrap:hover { border-color: var(--accent-dim); }
.roll-die-wrap.selected-total { border-color: var(--accent); background: rgba(64,136,212,0.1); }
.roll-die-wrap.selected-effect { border-color: var(--success); background: rgba(64,184,96,0.1); }
.roll-die-wrap.unused { opacity: 0.3; }

.selection-row {
  display: flex; align-items: center; gap: 6px; font-size: 13px;
}
.sel-label { color: var(--text-dim); min-width: 42px; cursor: pointer; }
.sel-label:hover { color: var(--accent); }
.sel-slot {
  width: 36px; height: 28px; border-radius: 6px; cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  font-weight: 700; font-size: 16px;
  border: 1px solid rgba(255,255,255,0.12); background: rgba(255,255,255,0.04);
}
.total-slot { border-color: var(--accent-dim); }
.effect-slot { border-color: var(--success); min-width: 44px; min-height: 40px; display: flex; align-items: center; justify-content: center; }
.effect-slot.filled { border-color: transparent; background: transparent; }
.sel-slot.empty { border-style: dashed; opacity: 0.5; }
.sel-slot.empty .empty-text { font-size: 10px; color: var(--text-dim); }
.sel-slot.next { border-style: solid; opacity: 0.8; animation: pulse-slot 1.5s ease-in-out infinite; }
.sel-slot.selected { border-style: solid; opacity: 1; border-color: var(--accent); background: rgba(64,136,212,0.25); box-shadow: 0 0 6px rgba(64,136,212,0.3); }
.effect-die-icon { width: 44px; height: 48px; }
@keyframes pulse-slot { 0%, 100% { border-color: var(--accent); } 50% { border-color: var(--accent-dim); } }
.sel-value { color: var(--text-dim); }
.sel-value strong { color: var(--accent); font-size: 20px; }

.difficulty-presets { display: flex; flex-wrap: wrap; gap: 6px; }
.difficulty-btn { flex: 1; min-width: 56px; padding: 6px 4px; font-size: 11px; font-weight: 700; border-radius: 6px; cursor: pointer; border: 2px solid transparent; background: rgba(255,255,255,0.06); color: var(--text); }
.difficulty-btn:hover { background: rgba(255,255,255,0.12); border-color: var(--accent-dim); }
.opposition-result { font-size: 14px; color: var(--text-dim); margin-top: 4px; }
.opposition-result strong { color: var(--text); }
.outcome-success { color: var(--success); font-weight: 700; }
.outcome-fail { color: var(--danger); font-weight: 700; }
</style>
