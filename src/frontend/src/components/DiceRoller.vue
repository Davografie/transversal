<template>
  <div class="dice-roller panel" :class="[{ open: panelOpen }, `kind-${rollKind}`]" @touchstart="onRollerTouchStart" @touchend="onRollerTouchEnd">
    <div class="pool-tabs" v-if="tabEntities.length > 1">
      <button
        v-for="e in tabEntities"
        :key="e.id"
        class="pool-tab"
        :class="{ active: activeId === e.id, self: e.id === selfTabId, blink: e.id === selfTabId && youTabBlink }"
        @click="switchTab(e.id)"
      >
        {{ e.name }}
      </button>
    </div>

    <div v-if="contestResult && (!gmMode || actingEntityId)" class="contest-result-widget">
      <div class="contest-sides">
        <div class="contest-side" :class="sideClasses('challenger')">
          <span class="side-icon">{{ sideIcon('challenger') }}</span>
          <span class="side-name">{{ challengerName }}</span>
          <span v-if="contestResult.challenger" class="side-sum"><strong class="result-num">{{ contestResult.challenger.total }}</strong></span>
          <span v-else class="side-empty">gave in</span>
          <span v-if="sideIsWinner('challenger') && appliedEffectDie" class="side-effect">
            <template v-if="steppedDown && winnerOriginalEffectDie">
              <DieIcon :die="winnerOriginalEffectDie" class="side-effect-die original" />
              <span class="step-arrow">↓</span>
            </template>
            <DieIcon :die="appliedEffectDie" class="side-effect-die" />
          </span>
          <span v-else-if="!sideIsWinner('challenger') && loserTakenOut" class="side-effect">taken out</span>
        </div>
        <div class="contest-side" :class="sideClasses('defendant')">
          <span class="side-icon">{{ sideIcon('defendant') }}</span>
          <span class="side-name">{{ defendantName }}</span>
          <span v-if="contestResult.defendant" class="side-sum"><strong class="result-num">{{ contestResult.defendant.total }}</strong></span>
          <span v-else class="side-empty">gave in</span>
          <span v-if="sideIsWinner('defendant') && appliedEffectDie" class="side-effect">
            <template v-if="steppedDown && winnerOriginalEffectDie">
              <DieIcon :die="winnerOriginalEffectDie" class="side-effect-die original" />
              <span class="step-arrow">↓</span>
            </template>
            <DieIcon :die="appliedEffectDie" class="side-effect-die" />
          </span>
          <span v-else-if="!sideIsWinner('defendant') && loserTakenOut" class="side-effect">taken out</span>
        </div>
      </div>
    </div>

    <template v-if="isEditing">
    <div class="roll-kind-row">
      <div
        v-if="rollKindLabel"
        class="roll-kind-badge"
        :class="{ 'high-stakes': highStakes, toggleable: gmMode && challenged }"
        :title="gmMode && challenged ? 'Toggle high stakes' : ''"
        @click="gmMode && challenged && toggleStakes()"
      >{{ rollKindLabel }}</div>
      <div v-if="showContest && !contestResult" class="challenge-target">
        <select v-if="!challenged" v-model="opponentId" @change="doChallenge" class="challenge-select">
          <option value="" disabled>Challenge target</option>
          <option v-for="e in peers.filter(e => e.id !== editingEntityId && !bannedTargetIds.includes(e.id))" :key="e.id" :value="e.id">{{ e.name }}</option>
        </select>
        <span v-else class="contest-status">
          ⚔️ {{ opponentName }}
          <span v-if="opponentCommitted" class="opponent-result-badge">
            <strong class="result-num">{{ opponentCommitted.total }}</strong>
            <DieIcon v-if="opponentCommitted.effect_die" :die="opponentCommitted.effect_die" class="opponent-effect-die" />
          </span>
        </span>
      </div>
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
    <div v-if="!gmMode && difficulty != null" class="difficulty-target">
      Target difficulty: <strong>{{ difficulty }}</strong>
    </div>
    <div v-if="!gmMode && difficultyFlash" class="difficulty-flash">{{ difficultyFlash }}</div>
    <div v-if="isAdding() && mode !== 'roll_table' && gmMode && !actingEntityId" class="difficulty-presets">
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

    <div class="add-die" v-if="isAdding() && mode !== 'roll_table' && showDiePicker">
      <button v-for="d in dies" :key="d" class="die-btn" :class="`die-btn-${d}`" @click="addDie(d)">
        <DieIcon :die="d" class="add-die-icon" />
      </button>
    </div>

    <div v-if="showContest" class="contest-setup">
      <div v-if="contestError" class="error">{{ contestError }}</div>
      <div v-if="contestNotice" class="contest-notice">{{ contestNotice }}</div>
    </div>

    <!-- Picking: total/effect selection slots live above the dice -->
    <div v-if="result && isPicking()" class="pool-result">
      <div class="selection-row">
        <span class="sel-label" @click="assignBestTotal">{{ sumLabel }}:</span>
        <template v-for="(idx, i) in selection.total" :key="'t'+i">
          <span v-if="i > 0" class="slot-plus">+</span>
          <span
            class="sel-slot total-slot"
            :class="{ empty: idx === null, selected: selectedSlot?.type === 'total' && selectedSlot?.index === i }"
            @dragover.prevent
            @drop="onSlotDrop('total', i, $event)"
            @click="idx !== null ? clearSlot('total', i) : selectSlot('total', i)"
          >
            {{ idx !== null ? result.rolls[idx].result : '' }}
          </span>
        </template>
        <span class="sel-value">= <strong class="result-num">{{ computedTotal }}</strong></span>
      </div>
      <div class="selection-row" v-if="!gmMode || actingEntityId">
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

    <!-- Resolved status lines live above the dice -->
    <div v-if="result" class="result-status">
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

    <!-- DICE STAGE — same slot in every phase, centered -->
    <div class="dice-stage">
      <div v-if="isAdding()" class="dice-pool">
        <div
          v-for="(die, i) in pool"
          :key="i"
          class="die-chip"
          @click="removeDie(i)"
        >
          <DieIcon :die="die.die" :label="die.label || die.source" />
        </div>
        <button
          v-if="mode !== 'roll_table'"
          class="add-die-toggle"
          :class="{ active: showDiePicker }"
          :title="showDiePicker ? 'Hide dice' : 'Add die'"
          @click="showDiePicker = !showDiePicker"
        >{{ showDiePicker ? '×' : '+' }}</button>
      </div>

      <div v-else-if="isRolling()" class="rolling-dice">
        <div v-for="(f, i) in rollingFaces" :key="i" class="rolling-die" :class="{ locked: f.locked }">
          <DieIcon :die="f.die" :result="f.face" />
        </div>
      </div>

      <div v-else-if="result && isPicking()" class="roll-dice">
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

      <template v-else-if="result && !contestResult">
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
        <template v-else-if="result.pipeline === 'simplified'">
          <div class="result-line">
            <span class="result-num">{{ result.highest }}</span> → <strong>{{ result.tier }}</strong>
            <span v-if="result.effect_die" class="effect-result">
              <span class="effect-result-label">effect</span>
              <DieIcon :die="result.effect_die" class="effect-result-icon" />
            </span>
          </div>
        </template>
        <template v-else>
          <div class="resolved-result">
            <strong class="resolved-total result-num">{{ computedTotal }}</strong>
            <DieIcon v-if="effectDie" :die="effectDie" class="resolved-eff-die" />
          </div>
        </template>
      </template>
    </div>

    <div class="controls" v-if="isAdding() || isPicking() || isRolling()">
      <button v-if="(isAdding() || isRolling()) && (pool.length > 0 || loading)" @click="doRoll" :disabled="loading || isRolling()" class="roll-btn">
        {{ loading || isRolling() ? 'Rolling…' : 'Roll' }}
      </button>
      <button v-if="isPicking()" @click="onPickCommit" class="roll-btn commit-btn">
        {{ challenged ? 'Set' : 'Done' }}
      </button>
      <button v-if="challenged && !contestResult && !contestCompare && giveInAllowed" @click="doGiveIn" class="roll-btn give-in-btn">Give in</button>
    </div>

    <div class="controls" v-if="isResolved() && mode !== 'roll_table' && !challenged">
      <button @click="clearResult" class="roll-btn">New Pool</button>
      <button v-if="!gmMode" @click="showConsequences = !showConsequences" class="roll-btn">{{ showConsequences ? 'Hide consequences' : 'Consequences' }}</button>
    </div>

    <div class="controls" v-if="contestResult && iWon && (!gmMode || actingEntityId)">
      <button @click="showConsequences = !showConsequences" class="roll-btn">{{ showConsequences ? 'Hide consequences' : 'Consequences' }}</button>
    </div>

    <div class="controls" v-if="contestResult && iGaveIn && (!gmMode || actingEntityId)">
      <button @click="showConsequences = !showConsequences" class="roll-btn">{{ showConsequences ? 'Hide' : 'Take complication' }}</button>
    </div>

    <div class="controls" v-if="isWaitingForDecision">
      <span class="waiting-state">Waiting for {{ opponentName }} to decide…</span>
    </div>

    <div class="controls" v-if="decisionPending">
      <button @click="doGiveIn" class="roll-btn give-in-btn">Give in</button>
      <button @click="doPush" class="roll-btn push-btn">Push</button>
    </div>

    <div v-if="showConsequences && (isResolved() || contestResult)" class="consequence-panel">
      <div class="consequence-side">
        <label>Menu</label>
        <select v-model="consequenceSide">
          <option value="player">Player</option>
          <option value="gm">GM</option>
        </select>
      </div>
      <ConsequenceMenu :entity-id="consequenceTargetId" :side="consequenceSide" :effect-die="consequenceEffectDie" :exclude-ids="consequenceExcludeIds" @close="showConsequences = false" />
    </div>

    <div v-if="error" class="error">{{ error }}</div>
    </template>

    <template v-else>
      <div class="peer-pool">
        <div class="peer-pool-title">{{ activeName }}</div>
        <div v-if="remoteView?.committed" class="peer-committed">
          Set: <strong class="result-num">{{ remoteView.committed.total }}</strong>
          <DieIcon v-if="remoteView.committed.effect_die" :die="remoteView.committed.effect_die" class="peer-effect-die" />
        </div>
        <div v-else-if="remoteView?.rolls?.length" class="roll-dice">
          <div v-for="(r, i) in remoteView.rolls" :key="i" class="roll-die-wrap">
            <DieIcon :die="r.die" :result="r.result" :label="r.label || r.source_id || r.die" />
          </div>
        </div>
        <div v-else class="dice-pool">
          <div v-for="(die, i) in viewPoolDice" :key="i" class="die-chip" :class="{ 'peer-rolling': remotePhase === 'rolling' }" :style="remotePhase === 'rolling' ? { animationDelay: (i * 90) + 'ms' } : null">
            <DieIcon :die="die.die" :label="die.label || die.source_id || die.die" />
          </div>
          <div v-if="!viewPoolDice.length" class="empty-pool">No dice assembled</div>
        </div>
        <div v-if="remoteView?.botch" class="botch">BOTCH</div>
        <div v-if="remoteView?.hitches?.length" class="hitches">{{ remoteView.hitches.length }} hitch{{ remoteView.hitches.length > 1 ? 'es' : '' }}</div>
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
  actingEntityId: { type: String, default: '' }, // entity being acted on (GM switchable; player = self)
  fallbackEntityId: { type: String, default: '' }, // GM's stable identity for difficulty/free-roam rolls
  remotePools: { type: Object, default: () => ({}) }, // entity_id → { dice, phase } from SSE
  remoteResults: { type: Object, default: () => ({}) }, // entity_id → { rolls, committed, ... } from SSE
})

const emit = defineEmits(['update:universe', 'rolled', 'poolChange', 'phaseChange', 'picked', 'panelOpen', 'difficulty', 'sfx-choice-resolved', 'actingEntityChange'])

const { loading, error, cortexRoll: apiCortexRoll, simplifiedRoll: apiSimplifiedRoll, difficultyRoll: apiDifficultyRoll, selectDice: apiSelectDice, savePool: apiSavePool, getPool: apiGetPool, setOpposition: apiSetOpposition, setResult: apiSetResult, setStakes: apiSetStakes, giveIn: apiGiveIn, push: apiPush, getTargetingBans: apiGetTargetingBans, getContest: apiGetContest } = useApi()
const { resolveEffectTargets } = useEffectApplication()
const pool = reactive([])
const result = ref(null)
const rollingFaces = ref([]) // [{ die, face }] animated faces during ROLLING
const showDiePicker = ref(false)
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
const DIFFICULTY_TAB = '__difficulty__'
const poolPurpose = ref(null) // GM mode: 'difficulty' | 'gmc' | null
const activeId = ref(props.gmMode ? DIFFICULTY_TAB : props.entityId)
const viewPool = ref([])
// Live remote view for the read-only peer tab: prefer rolled/committed state,
// then the live assembled pool, then the fetched snapshot.
const remoteView = computed(() => props.remoteResults?.[activeId.value] || null)
const remotePhase = computed(() => props.remotePools?.[activeId.value]?.phase || 'adding')
const viewPoolDice = computed(() => {
  const rp = props.remotePools?.[activeId.value]
  if (rp && Array.isArray(rp.dice)) return rp.dice
  return viewPool.value
})
const opponentId = ref('')
const contestResult = ref(null)
const contestCompare = ref(null)
const contestError = ref('')
const contestNotice = ref('')
const challenged = ref(false)
const isChallenger = ref(false)
const giveInAllowed = ref(false)
const opponentCommitted = ref(null) // { total, effect_die } once the opponent has set
const bannedTargetIds = ref([])     // entity ids the acting entity cannot currently challenge
const youTabBlink = ref(false)      // nudge: it's your turn to roll
const highStakes = ref(false)       // contest stakes (low by default)
const difficultyFlash = ref('')

const tabEntities = computed(() => {
  // Difficulty/You tab always present; peers only when they have an active pool.
  const list = props.gmMode
    ? [{ id: DIFFICULTY_TAB, name: 'Difficulty' }]
    : [{ id: props.entityId, name: 'You' }]
  const seen = new Set(list.map(e => e.id))
  const pushEntity = (id) => {
    if (!id || seen.has(id)) return
    seen.add(id)
    const name = (props.peers || []).find(p => p.id === id)?.name || id
    list.push({ id, name })
  }
  if (props.actingEntityId) pushEntity(props.actingEntityId)
  if (challenged.value) pushEntity(opponentId.value)
  for (const [eid, rp] of Object.entries(props.remotePools || {})) {
    if (seen.has(eid)) continue
    const rr = props.remoteResults?.[eid]
    const hasPool = rp && Array.isArray(rp.dice) && rp.dice.length > 0
    const hasResult = rr && (rr.rolls?.length || rr.committed)
    if (!hasPool && !hasResult) continue
    pushEntity(eid)
  }
  return list
})
const editingEntityId = computed(() => props.actingEntityId || props.fallbackEntityId || props.entityId)
const decisionPending = computed(() => !!contestCompare.value && contestCompare.value.pending === editingEntityId.value)
const isWaitingForDecision = computed(() => !!contestCompare.value && contestCompare.value.pending !== editingEntityId.value)
const isEditing = computed(() => {
  if (props.gmMode) {
    return props.actingEntityId
      ? activeId.value === props.actingEntityId
      : activeId.value === DIFFICULTY_TAB
  }
  return activeId.value === props.entityId
})
const activeName = computed(() => tabEntities.value.find(e => e.id === activeId.value)?.name || activeId.value)
const selfTabId = computed(() => props.gmMode ? (props.actingEntityId || DIFFICULTY_TAB) : props.entityId)
const opponentName = computed(() =>
  (props.peers || []).find(p => p.id === opponentId.value)?.name ||
  tabEntities.value.find(e => e.id === opponentId.value)?.name ||
  opponentId.value ||
  'Opponent'
)
const myContestantName = computed(() =>
  (props.peers || []).find(p => p.id === editingEntityId.value)?.name || editingEntityId.value
)
const challengerName = computed(() => isChallenger.value ? myContestantName.value : opponentName.value)
const defendantName = computed(() => isChallenger.value ? opponentName.value : myContestantName.value)
const iWon = computed(() => {
  if (!contestResult.value) return false
  const challengerWon = contestResult.value.winner === 'player'
  return isChallenger.value ? challengerWon : !challengerWon
})
function sideIsMine(side) { return (side === 'challenger') === isChallenger.value }
function sideIcon(side) { return sideIsMine(side) ? (iWon.value ? '🏆' : '💀') : '' }
function sideClasses(side) {
  const mine = sideIsMine(side)
  return { mine, winner: mine && iWon.value, loser: mine && !iWon.value }
}
const appliedEffectDie = computed(() => contestResult.value?.effect_die || null)
const loserTakenOut = computed(() => !!contestResult.value?.taken_out)
function sideIsWinner(side) {
  if (!contestResult.value) return false
  const challengerWon = contestResult.value.winner === 'player'
  return (side === 'challenger') === challengerWon
}
const winnerOriginalEffectDie = computed(() => {
  if (!contestResult.value) return null
  const side = contestResult.value.winner === 'player' ? 'challenger' : 'defendant'
  return contestResult.value[side]?.effect_die || null
})
const steppedDown = computed(() => !!appliedEffectDie.value && !!winnerOriginalEffectDie.value && appliedEffectDie.value !== winnerOriginalEffectDie.value)
const iGaveIn = computed(() => {
  if (!contestResult.value?.gave_in) return false
  return isChallenger.value ? contestResult.value.gave_in === 'player' : contestResult.value.gave_in === 'opponent'
})
const consequenceTargetId = computed(() => {
  if (contestResult.value) return iWon.value ? opponentId.value : editingEntityId.value
  return editingEntityId.value
})
// Contest complication SFX surface as menu options (id ``sfx:<sfx-id>``).
// Show only the one that matches this end of the contest pipeline:
// winner → apply to opponent; conceder → take on self; non-contest → neither.
// On a give-in the conceder already takes their own, so the winner does not apply.
const consequenceExcludeIds = computed(() => {
  if (iWon.value && !contestResult.value?.gave_in) return ['sfx:take-complication']
  if (iGaveIn.value) return ['sfx:apply-complication']
  return ['sfx:apply-complication', 'sfx:take-complication']
})
const sumLabel = computed(() =>
  (props.gmMode && !props.actingEntityId && activeId.value === DIFFICULTY_TAB) ? 'difficulty' : 'result'
)

// ── Roll kind (P2.11: visual pool styling per roll kind) ───────────
const ROLL_KIND_LABELS = {
  'simple-test': 'Simple Test',
  'cortex-test': 'Cortex Test',
  'challenger-contest': 'Challenger',
  'defendant-contest': 'Defendant',
  'roll-table': 'Roll Table',
  'difficulty': 'Difficulty',
  'empty-pool': 'Empty Dicepool',
}
const rollKind = computed(() => {
  if (props.mode === 'roll_table') return 'roll-table'
  if (challenged.value) return isChallenger.value ? 'challenger-contest' : 'defendant-contest'
  if (props.gmMode && !props.actingEntityId && activeId.value === DIFFICULTY_TAB) return 'difficulty'
  if (isAdding() && pool.length === 0) return 'empty-pool'
  // Test: use the rolled pipeline when known, else predict from assembled size
  // (the resolver routes ≤2 dice to simplified, 3+ to pool).
  const pipeline = result.value?.pipeline ?? (pool.length > 2 ? 'pool' : 'simplified')
  return pipeline === 'pool' ? 'cortex-test' : 'simple-test'
})
const rollKindLabel = computed(() => ROLL_KIND_LABELS[rollKind.value] || '')

// Contest UI is relevant for players (or a GM acting as an entity) at a
// location with at least one peer, during assembly/picking or once challenged.
const showContest = computed(() => (!props.gmMode || props.actingEntityId) && props.mode !== 'roll_table' && props.peers.length > 1 && (challenged.value || isAdding() || isPicking()))

function markPurpose(kind) {
  if (pool.length === 0) poolPurpose.value = kind
}

function ensureSelfTab() {
  if (props.mode === 'roll_table') return
  const selfId = props.gmMode ? (props.actingEntityId || DIFFICULTY_TAB) : props.entityId
  if (activeId.value !== selfId) activeId.value = selfId
}

async function switchTab(id) {
  activeId.value = id
  if (props.gmMode) {
    // GM: tabs are a pool viewer only — never switch the acting entity.
    // Perspective switching stays on the scene overview / peers bar.
    if (id === DIFFICULTY_TAB) return
    viewPool.value = []
    if (!props.locationId) return
    const res = await apiGetPool(props.locationId, id)
    viewPool.value = res?.dice || []
    return
  }
  // Player: only self is editable; peers are read-only.
  if (id === props.entityId) return
  viewPool.value = []
  if (!props.locationId) return
  const res = await apiGetPool(props.locationId, id)
  console.log('[diag] switchTab fetched pool', { id, locationId: props.locationId, diceCount: res?.dice?.length || 0 })
  viewPool.value = res?.dice || []
}

watch(() => props.entityId, (id) => {
  if (!props.gmMode) activeId.value = id
})

watch(() => props.actingEntityId, async (id) => {
  if (!props.gmMode) return
  if (id) {
    activeId.value = id
    await loadPoolIntoEditor(id)
    await syncContestState()
    await loadTargetingBans()
  } else {
    activeId.value = DIFFICULTY_TAB
    resetEditor()
  }
})

watch(() => props.difficulty, (v) => {
  if (v == null) return
  difficultyFlash.value = `Difficulty set: ${v}`
  setTimeout(() => {
    if (difficultyFlash.value === `Difficulty set: ${v}`) difficultyFlash.value = ''
  }, 3000)
})

async function doChallenge() {
  if (!opponentId.value || !props.locationId) return
  contestError.value = ''
  contestNotice.value = ''
  contestResult.value = null
  contestCompare.value = null
  giveInAllowed.value = false
  showConsequences.value = false
  opponentCommitted.value = null
  const res = await apiSetOpposition(props.locationId, editingEntityId.value, opponentId.value, props.universe)
  if (res && res.status === 'blocked') {
    contestError.value = res.reason || "You can't target that entity yet"
    return
  }
  challenged.value = true
  isChallenger.value = true
}

function onChallenged(challengerId) {
  challenged.value = true
  opponentId.value = challengerId
  isChallenger.value = false
  contestResult.value = null
  contestCompare.value = null
  contestError.value = ''
  contestNotice.value = ''
  giveInAllowed.value = false
  opponentCommitted.value = null
}

function setContestOutcome(outcome) {
  contestResult.value = outcome
  contestCompare.value = null
  contestError.value = ''
  contestNotice.value = ''
  challenged.value = true
  giveInAllowed.value = false
  // Self-describing outcome: reconcile which side we are from the payload
  // instead of trusting possibly-stale local challenge state.
  const me = editingEntityId.value
  if (outcome?.challenger_id && outcome?.defendant_id && me) {
    isChallenger.value = outcome.challenger_id === me
    opponentId.value = isChallenger.value ? outcome.defendant_id : outcome.challenger_id
  }
}

function setContestCompare(compare) {
  contestCompare.value = compare
  contestError.value = ''
  challenged.value = true
  const me = editingEntityId.value
  if (compare?.challenger_id && compare?.defendant_id && me) {
    isChallenger.value = compare.challenger_id === me
    opponentId.value = isChallenger.value ? compare.defendant_id : compare.challenger_id
  }
  giveInAllowed.value = false
  if (compare?.pending === me) {
    contestNotice.value = "You're behind — give in or push"
  } else {
    contestNotice.value = `${opponentName.value} must give in or push`
  }
}

function onContestCompare(data) {
  if (!challenged.value || !data) return
  setContestCompare(data)
}

function onContestPush(data) {
  if (!challenged.value || !data) return
  if (data.entity_id === opponentId.value) {
    contestCompare.value = null
    contestNotice.value = `${opponentName.value} is pushing…`
  }
}

function onOpponentCommitted(data) {
  if (!challenged.value || !data) return
  if (data.entity_id === opponentId.value) {
    opponentCommitted.value = { total: data.total, effect_die: data.effect_die }
    if (!isChallenger.value) {
      giveInAllowed.value = true  // initiator has now committed
      youTabBlink.value = true
      contestNotice.value = `Your turn — roll to beat ${opponentName.value}`
    }
  }
}

function onOpponentGiveIn(data) {
  if (!challenged.value || !data) return
  if (data.entity_id === opponentId.value) {
    contestNotice.value = `${opponentName.value} gave in — you win`
  }
}

function committedResult() {
  const r = result.value
  if (!r) return null
  if (r.pipeline === 'pool') {
    const total = selection.total.reduce((sum, idx) => sum + (idx !== null ? r.rolls[idx].result : 0), 0)
    const effIdx = selection.effect[0]
    const effectDie = effIdx !== null ? r.rolls[effIdx].die : 'd4'
    return { total, effect_die: effectDie, pipeline: 'pool' }
  }
  return { total: r.highest, effect_die: r.effect_die || null, tier: r.tier || null, pipeline: 'simplified' }
}

async function doSetResult() {
  const committed = committedResult()
  if (!committed || !props.locationId) return
  setPhase(Phase.RESOLVED)
  contestError.value = ''
  const res = await apiSetResult(props.locationId, editingEntityId.value, committed)
  if (res && res.status === 'compare') {
    setContestCompare(res)
  } else if (res && res.winner) {
    contestResult.value = res
    contestCompare.value = null
    giveInAllowed.value = false
  } else if (res && res.status === 'waiting') {
    if (isChallenger.value) giveInAllowed.value = true  // challenger may still give in early
    contestError.value = 'Waiting for opponent…'
  }
}

async function doGiveIn() {
  if (!props.locationId) return
  contestError.value = ''
  const res = await apiGiveIn(props.locationId, editingEntityId.value)
  if (res && res.winner) {
    contestResult.value = res
    contestCompare.value = null
    giveInAllowed.value = false
    await loadTargetingBans()
  } else if (res && res.status === 'not_ready') {
    contestError.value = 'Initiator must set their result first'
  }
}

async function doPush() {
  if (!props.locationId) return
  contestError.value = ''
  const res = await apiPush(props.locationId, editingEntityId.value)
  if (res && res.status === 'pushed') {
    contestResult.value = null
    contestCompare.value = null
    contestNotice.value = 'Push! Build a new pool and roll again.'
    giveInAllowed.value = false
    result.value = null
    selection.total = []
    selection.effect = []
    poolPurpose.value = null
    showDiePicker.value = false
    pool.splice(0, pool.length)
    notifyPool()
    setPhase(Phase.ADDING)
  } else if (res && res.status === 'not_allowed') {
    contestError.value = 'Push unavailable (already pushed or not your turn)'
  } else {
    contestError.value = 'Push unavailable'
  }
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

function poolEntityKey() {
  // Entity pools use the acting entity; the GM difficulty pool uses the
  // location id as its key (unified pool concept).
  if (props.gmMode && !props.actingEntityId) return props.locationId
  return editingEntityId.value
}

function persistPool() {
  if (!props.locationId) return
  const key = poolEntityKey()
  if (!key) return
  const dice = pool.map(d => ({
    die: d.die,
    source_kind: d.sourceKind || 'manual',
    source_id: d.tsId || d.source || '',
    label: d.label || d.source || d.die,
    ts_id: d.tsId || null,
  }))
  apiSavePool(props.locationId, key, dice)
}

function notifyPool() {
  persistPool()
  emit('poolChange', pool.map(d => ({ die: d.die, label: d.label || d.source || d.die, tsId: d.tsId })).filter(d => d.label))
}

function addDie(die) {
  ensureSelfTab()
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

function addFromSheet(payload) {
  ensureSelfTab()
  // Accept a single-die { die } payload or a multi-die { dice: [...] } payload.
  const { source, label, tsId } = payload || {}
  const dice = Array.isArray(payload?.dice) ? payload.dice : (payload?.die ? [payload.die] : [])
  if (!dice.length) return
  // Toggle: if the trait is already in the pool, remove all of its dice.
  if (tsId != null && pool.some(d => d.tsId === tsId)) {
    removeByTsId(tsId)
    return
  }
  markPurpose('gmc')
  for (const die of dice) {
    pool.push({ die, source, label: label || source, tsId: tsId ?? null, sourceKind: 'trait' })
  }
  panelOpen.value = true
  notifyPool()
}

function removeBySource(source) {
  const idx = pool.findIndex(d => d.source === source)
  if (idx !== -1) { pool.splice(idx, 1); notifyPool() }
}

function removeByTsId(tsId) {
  if (!tsId) return
  let removed = false
  for (let i = pool.length - 1; i >= 0; i--) {
    if (pool[i].tsId === tsId) {
      pool.splice(i, 1)
      removed = true
    }
  }
  if (removed) notifyPool()
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

defineExpose({ addFromSheet, removeBySource, removeByTsId, splitDie, clearPool, resyncTraitDie, onChallenged, setContestOutcome, onContestCompare, onContestPush, onOpponentCommitted, onOpponentGiveIn, loadTargetingBans, setHighStakes, panelOpen })

function isHitch(idx) {
  if (!result.value) return false
  // When the GM is rolling to set difficulty, a 1 is an ordinary die —
  // hitches only apply to actual rolls, not difficulty determination.
  if (props.gmMode && !props.actingEntityId && poolPurpose.value === 'difficulty') return false
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
  if (contestResult.value) return appliedEffectDie.value || ''
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

const FIRST_LOCK_MS = 900
const LOCK_STAGGER_MS = 1000
const FINAL_HOLD_MS = 300

function rollFace(die) {
  const sides = Number(die.replace(/^d/, '')) || 6
  return Math.floor(Math.random() * sides) + 1
}

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms))
}

function startRollAnimation(dice) {
  rollingFaces.value = dice.map(d => ({ die: d.die, face: rollFace(d.die), locked: false }))
  return setInterval(() => {
    for (const f of rollingFaces.value) {
      if (!f.locked) f.face = rollFace(f.die)
    }
  }, 70)
}

function lockDie(i, result_) {
  const f = rollingFaces.value[i]
  if (!f) return
  f.locked = true
  const rolled = result_?.rolls?.[i]
  f.face = rolled ? rolled.result : rollFace(f.die)
}

async function doRoll() {
  youTabBlink.value = false
  setPhase(Phase.ROLLING)
  const dice = pool.map(d => ({
    die: d.die,
    source_kind: d.sourceKind || 'manual',
    source_id: d.tsId || d.source || '',
    label: d.label || d.source || d.die,
    ts_id: d.tsId || null,
  }))
  const isDifficulty = props.gmMode && !props.actingEntityId && poolPurpose.value === 'difficulty'
  const key = poolEntityKey()

  // Persist the assembled pool (entity or difficulty) before the server rolls it.
  if (props.locationId && key) {
    await apiSavePool(props.locationId, key, dice)
  }

  // Blink random faces while the request is in flight, then lock each die
  // left-to-right so the player can see the numbers fall into place.
  const t0 = Date.now()
  const anim = startRollAnimation(dice)
  const result_ = isDifficulty
    ? await apiDifficultyRoll(props.locationId, key)
    : dice.length <= 2
      ? await apiSimplifiedRoll(props.locationId, key)
      : await apiCortexRoll(props.locationId, key)

  await sleep(Math.max(0, FIRST_LOCK_MS - (Date.now() - t0)))
  for (let i = 0; i < rollingFaces.value.length; i++) {
    lockDie(i, result_)
    if (i < rollingFaces.value.length - 1) await sleep(LOCK_STAGGER_MS)
  }
  await sleep(FINAL_HOLD_MS)

  clearInterval(anim)
  rollingFaces.value = []

  result.value = result_
  pool.length = 0
  emit('poolChange', [])  // clear sheet sources; the enriched pool stays on the server
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
  if (props.gmMode && !props.actingEntityId) {
    // GM difficulty roll: the picked total is the difficulty.
    emit('difficulty', computedTotal.value)
    return
  }
  // Player (or GM acting as an entity): emit final picked result for sharing
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

async function flagSelection() {
  // Record which dice are the result/effect dice on the stored pool.
  const total = selection.total.filter(i => i !== null)
  const effect = selection.effect.find(i => i !== null)
  const isDifficulty = props.gmMode && !props.actingEntityId
  const key = poolEntityKey()
  if (!props.locationId || !key || !total.length) return
  await apiSelectDice(props.locationId, key, total, isDifficulty ? null : (effect ?? null))
}

async function onPickCommit() {
  await flagSelection()
  if (challenged.value) {
    doSetResult()
  } else {
    commitPicks()
  }
}

function clearResult() {
  resetEditor()
  setPhase(Phase.ADDING)
}

function resetEditor() {
  result.value = null
  selection.total = []
  selection.effect = []
  poolPurpose.value = null
  contestResult.value = null
  contestCompare.value = null
  contestError.value = ''
  contestNotice.value = ''
  challenged.value = false
  isChallenger.value = false
  opponentId.value = ''
  giveInAllowed.value = false
  youTabBlink.value = false
  highStakes.value = false
  showConsequences.value = false
  opponentCommitted.value = null
  showDiePicker.value = false
}

function clearPool() {
  pool.splice(0, pool.length)
  resetEditor()
  setPhase(Phase.ADDING)
  notifyPool()
}

function resyncTraitDie(traitSettingId, newDice) {
  // After a trait step up/down, re-sync any open pool dice that reference it.
  // Server is authoritative; this keeps the client's local pool in lockstep.
  // `newDice` is the full post-change die array, mapped positionally so a
  // multi-die static trait (e.g. [d10, d10]) re-syncs every matching die.
  const dice = (Array.isArray(newDice) ? newDice : [newDice]).filter(d => /^d(4|6|8|10|12)$/.test(d || ''))
  if (!dice.length) return
  let changed = false
  let idx = 0
  for (const d of pool) {
    if (d.tsId && d.tsId === traitSettingId) {
      if (idx < dice.length && d.die !== dice[idx]) {
        d.die = dice[idx]
        changed = true
      }
      idx++
    }
  }
  if (changed) notifyPool()
}

async function loadPoolIntoEditor(id) {
  if (!props.locationId || !id) return
  const res = await apiGetPool(props.locationId, id)
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
  resetEditor()
  setPhase(Phase.ADDING)
  notifyPool()
  if (dice.length) panelOpen.value = true
}

async function syncContestState() {
  // Re-sync contest role after the GM takes over a contested entity.
  if (!props.locationId || !editingEntityId.value) return
  const res = await apiGetContest(props.locationId, editingEntityId.value)
  if (!res || res.status !== 'active' || !res.challenger_id || !res.defendant_id) return
  const me = editingEntityId.value
  challenged.value = true
  isChallenger.value = res.challenger_id === me
  opponentId.value = isChallenger.value ? res.defendant_id : res.challenger_id
  giveInAllowed.value = !!res.challenger_result && !res.pending  // early decline only
  highStakes.value = !!res.high_stakes
  const opp = isChallenger.value ? res.defendant_result : res.challenger_result
  opponentCommitted.value = opp ? { total: opp.total, effect_die: opp.effect_die } : null
  if (res.pending) {
    contestCompare.value = {
      status: 'compare',
      pending: res.pending,
      initiative: res.initiative,
      challenger_id: res.challenger_id,
      defendant_id: res.defendant_id,
      challenger: res.challenger_result,
      defendant: res.defendant_result,
      margin: 0,
    }
    if (res.pending === me) contestNotice.value = "You're behind — give in or push"
    else contestNotice.value = `${opponentName.value} must give in or push`
  } else {
    contestCompare.value = null
  }
}

async function loadTargetingBans() {
  const res = await apiGetTargetingBans(editingEntityId.value)
  bannedTargetIds.value = (res?.bans || []).map(b => b.target_id)
}

function setHighStakes(v) {
  highStakes.value = !!v
}

async function toggleStakes() {
  if (!props.gmMode || !props.locationId) return
  highStakes.value = !highStakes.value
  await apiSetStakes(props.locationId, editingEntityId.value, highStakes.value)
}

async function restorePool() {
  if (props.gmMode && !props.actingEntityId) return  // GM difficulty mode: transient
  await loadPoolIntoEditor(editingEntityId.value)
  await syncContestState()
  await loadTargetingBans()
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
  border-top: 3px solid var(--kind-accent, transparent);
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

.dice-pool { display: flex; justify-content: center; flex-wrap: wrap; gap: 6px; min-height: 28px; }
.dice-stage { display: flex; flex-direction: column; gap: var(--gap); min-height: 48px; }

.pool-tabs { display: flex; gap: 6px; flex-wrap: wrap; justify-content: center; }
.pool-tab {
  padding: 6px 10px; font-size: 12px; font-weight: 600; border-radius: 8px;
  cursor: pointer; border: 1px solid transparent; background: rgba(255,255,255,0.06);
  color: var(--text-dim);
}
.pool-tab.active { background: var(--accent, #7aa2f7); color: #0a0a0f; }
.pool-tab.self { border-color: var(--accent, #7aa2f7); }
.pool-tab.self:not(.active) { color: var(--text); background: rgba(64,136,212,0.12); }
.pool-tab.blink { animation: tab-blink 0.9s ease-in-out infinite; }
@keyframes tab-blink { 0%, 100% { box-shadow: 0 0 0 rgba(64,136,212,0); } 50% { box-shadow: 0 0 10px 2px rgba(64,136,212,0.9); } }

.difficulty-target {
  text-align: center; font-size: 13px; color: var(--text-dim);
}
.difficulty-target strong { color: var(--text); font-size: 15px; }
.difficulty-flash {
  text-align: center; font-size: 12px; color: var(--accent, #7aa2f7);
}

.contest-setup { margin-top: 4px; display: flex; flex-direction: column; gap: 6px; }
.contest-status { font-size: 12px; color: var(--text-dim); display: flex; align-items: center; gap: 6px; }
.opponent-result-badge {
  display: inline-flex; align-items: center; gap: 4px;
  padding: 1px 6px; border-radius: 6px;
  background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.12);
}
.opponent-result-badge .result-num { font-size: 16px; color: var(--text); }
.opponent-effect-die { width: 20px; height: 22px; }
.contest-notice { font-size: 12px; color: var(--accent, #7aa2f7); }
.contest-result { font-size: 13px; display: flex; flex-direction: column; gap: 2px; }

.contest-result-widget {
  margin-top: 6px;
  padding: 10px 12px;
  border-radius: 10px;
  background: rgba(255,255,255,0.04);
  border: 1px solid rgba(255,255,255,0.12);
  display: flex; flex-direction: column; gap: 8px;
}
.contest-sides { display: flex; gap: 8px; }
.contest-side {
  flex: 1; padding: 8px; border-radius: 8px;
  background: rgba(0,0,0,0.2); border: 1px solid transparent;
  display: flex; flex-direction: column; gap: 2px; font-size: 12px;
}
.contest-side.mine.winner { border-color: var(--success, #40b860); background: rgba(64,184,96,0.12); }
.contest-side.mine.loser { border-color: var(--danger, #d44040); background: rgba(212,64,64,0.12); }
.side-icon { font-size: 16px; line-height: 1; }
.side-name { font-weight: 600; color: var(--text); }
.side-sum { color: var(--text); }
.side-sum .result-num { font-size: 22px; }
.contest-side.mine.winner .side-sum .result-num { color: var(--success, #40b860); }
.contest-side.mine.loser .side-sum .result-num { color: var(--danger, #d44040); }
.side-effect { color: var(--text-dim); display: flex; align-items: center; gap: 4px; }
.side-effect-die { width: 26px; height: 30px; }
.side-effect-die.original { opacity: 0.35; filter: grayscale(0.6); }
.step-arrow { font-weight: 700; color: var(--text-dim); }
.side-empty { color: var(--text-dim); font-style: italic; }

.peer-pool { display: flex; flex-direction: column; gap: 8px; }
.peer-pool-title { font-size: 12px; text-transform: uppercase; letter-spacing: 1px; color: var(--text-dim); }
.peer-committed { font-size: 14px; display: flex; align-items: center; justify-content: center; gap: 8px; }
.peer-effect-die { width: 32px; height: 36px; }
.empty-pool { font-size: 12px; color: var(--text-dim); opacity: 0.7; }

.die-chip {
  cursor: pointer; transition: opacity 0.2s;
}
.die-chip:hover { opacity: 0.7; }
.die-chip.peer-rolling { animation: die-pulse 0.7s ease-in-out infinite; }
@keyframes die-pulse { 0%, 100% { transform: scale(1); filter: brightness(1); } 50% { transform: scale(1.12); filter: brightness(1.5); } }

.add-die-toggle {
  width: 36px;
  height: 40px;
  border-radius: 8px;
  border: 2px dashed rgba(255,255,255,0.2);
  background: rgba(255,255,255,0.04);
  color: var(--text-dim);
  font-size: 22px;
  font-weight: 700;
  line-height: 1;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.15s;
}
.add-die-toggle:hover,
.add-die-toggle.active {
  border-color: var(--accent);
  color: var(--accent);
  background: rgba(64,136,212,0.12);
}

.add-die { display: flex; gap: 6px; justify-content: center; }
.die-btn {
  flex: 1; padding: 4px;
  border-radius: 8px; cursor: pointer; transition: all 0.15s;
  border: 2px solid transparent; background: rgba(255,255,255,0.02);
  color: var(--text);
  display: flex; align-items: center; justify-content: center;
}
.add-die-icon {
  width: 40px;
  height: 44px;
}
.die-btn:hover { background: rgba(255,255,255,0.12); border-color: var(--accent-dim); }
.die-btn-d4  { color: #e88830; }
.die-btn-d6  { color: #e0e0e0; }
.die-btn-d8  { color: #d44040; }
.die-btn-d10 { color: #4088d4; }
.die-btn-d12 { color: #40b860; }

.controls { display: flex; gap: 8px; }
.waiting-state { flex: 1; text-align: center; font-size: 14px; color: var(--text-dim); padding: 10px; }
.consequence-panel { display: flex; flex-direction: column; gap: 6px; margin-top: 8px; }
.sfx-choice-panel { margin-top: 8px; }
.consequence-side { display: flex; align-items: center; gap: 6px; font-size: 10px; color: var(--text-dim); }
.consequence-side select { font-size: 11px; padding: 3px 6px; background: rgba(255,255,255,0.06); color: var(--text); border: 1px solid rgba(255,255,255,0.12); border-radius: 4px; }
.roll-btn { width: 100%; font-size: 18px; font-weight: 700; padding: 10px; }

.result { text-align: center; }
.result-status { text-align: center; }
.result-line { font-size: 16px; display: flex; align-items: center; justify-content: center; gap: 6px; }
.result-line strong { font-size: 24px; color: var(--accent); }
.result-eff-icon { width: 28px; height: 32px; }
.effect-result { display: flex; align-items: center; gap: 4px; }
.effect-result-label { font-size: 11px; color: var(--text-dim); }
.effect-result-icon { width: 32px; height: 36px; }

.resolved-result {
  display: flex; align-items: center; justify-content: center; gap: 16px; padding: 8px 0;
}
.resolved-total {
  font-size: 48px; font-weight: 800; color: var(--accent);
  text-shadow: 0 2px 8px rgba(64,136,212,0.3);
  line-height: 1;
}
.result-num {
  font-family: Georgia, 'Times New Roman', 'Playfair Display', serif;
  font-weight: 800;
  font-variant-numeric: lining-nums;
  letter-spacing: 0.4px;
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
  display: flex; align-items: center; justify-content: center; flex-wrap: wrap; gap: 6px; font-size: 13px;
}
.sel-label { color: var(--text-dim); min-width: 42px; cursor: pointer; }
.sel-label:hover { color: var(--accent); }
.slot-plus { color: var(--text-dim); font-weight: 700; }
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

/* ── Roll kind styling (P2.11) ─────────────────────── */
.kind-simple-test { --kind-accent: #e0e0e0; }
.kind-cortex-test { --kind-accent: #4088d4; }
.kind-challenger-contest { --kind-accent: #e88830; }
.kind-defendant-contest { --kind-accent: #d44040; }
.kind-roll-table { --kind-accent: #40b860; }
.kind-difficulty { --kind-accent: #b080d4; }

.roll-kind-badge {
  font-size: 10px; font-weight: 700;
  text-transform: uppercase; letter-spacing: 1.5px;
  padding: 3px 10px; border-radius: 999px;
  color: var(--kind-accent);
  border: 1px solid var(--kind-accent);
  background: rgba(255,255,255,0.04);
}
.roll-kind-badge.toggleable { cursor: pointer; }
.roll-kind-badge.high-stakes {
  color: #ff8a3d;
  border-color: #ff5a1f;
  background: linear-gradient(135deg, rgba(255,90,31,0.28), rgba(255,180,40,0.16));
  text-shadow: 0 0 6px rgba(255,120,40,0.85);
  animation: stakes-flicker 1.15s ease-in-out infinite;
}
@keyframes stakes-flicker {
  0%, 100% { box-shadow: 0 0 4px rgba(255,90,31,0.35); }
  50% { box-shadow: 0 0 13px 3px rgba(255,150,40,0.85); transform: scale(1.04); }
}

.roll-kind-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.challenge-target {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}
.challenge-select {
  padding: 4px 10px;
  font-size: 12px;
  border-radius: 999px;
  background: rgba(255,255,255,0.06);
  color: var(--text);
  border: 1px solid rgba(255,255,255,0.15);
  max-width: 180px;
}

.give-in-btn {
  color: var(--danger);
  border: 1px solid var(--danger);
  background: rgba(216,64,64,0.08);
}
.give-in-btn:hover {
  background: rgba(216,64,64,0.2);
  color: var(--danger);
}

.rolling-dice {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  justify-content: center;
  align-items: center;
  min-height: 48px;
}
.rolling-die {
  cursor: default;
  animation: roll-pop 0.09s ease-in-out;
}
@keyframes roll-pop {
  0% { transform: scale(0.92); }
  50% { transform: scale(1.04); }
  100% { transform: scale(1); }
}
.rolling-die.locked {
  animation: die-lock 0.2s ease-out;
}
@keyframes die-lock {
  0% { transform: scale(1.18); }
  100% { transform: scale(1); }
}
</style>
