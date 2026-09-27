<template>
  <div class="dice-roller panel" :class="[{ open: panelOpen }, `kind-${rollKind}`]" @touchstart="onRollerTouchStart">
    <PoolTabs
      v-if="tabEntities.length > 1"
      :groups="tabGroups"
      :active-id="activeId"
      :self-tab-id="selfTabId"
      :difficulty-tab="DIFFICULTY_TAB"
      :you-tab-blink="youTabBlink"
      :difficulty-tab-blink="difficultyTabBlink"
      @select="switchTab"
      @toggle-stakes="onGroupStakes"
    />

    <ContestResultWidget
      v-if="contestResult && (!gmMode || entityId)"
      :result="contestResult"
      :challenger-name="challengerName"
      :defendant-name="defendantName"
      :i-won="iWon"
      :is-challenger="isChallenger"
      :applied-effect-die="appliedEffectDie"
    />

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
          <option v-for="e in peers.filter(e => e.type !== 'LOCATION' && e.id !== editingEntityId && !bannedTargetIds.includes(e.id))" :key="e.id" :value="e.id">{{ e.name }}</option>
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
    <div v-if="sfxChoiceRequest && sfxChoiceRequest.length" class="sfx-choice-panel">
      <EffectTargetWizard
        :entity-id="entityId"
        :pending-choices="sfxChoiceRequest"
        title="SFX choice"
        @resolve="resolveSfxChoices"
        @run-loop="runSfxLoop"
        @cancel="clearSfxChoices"
      />
    </div>
    <div v-if="showDifficultyTarget" class="difficulty-target">
      Target difficulty: <strong>{{ difficulty }}</strong>
    </div>
    <div v-if="!gmMode && difficultyFlash" class="difficulty-flash">{{ difficultyFlash }}</div>
    <div v-if="isAdding() && mode !== 'roll_table' && gmMode && !entityId" class="difficulty-presets">
      <button
        v-for="p in difficultyPresets"
        :key="p.die"
        class="difficulty-btn"
        :class="`die-btn-${p.die}`"
        :title="`${p.label} (2${p.die})`"
        @click="setDifficulty(p.die)"
      >
        <DieIcon :die="p.die" class="difficulty-die-icon" />
        <span class="difficulty-preset-label">{{ p.label }}</span>
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
            :draggable="idx !== null"
            @dragover.prevent
            @drop="onSlotDrop('total', i, $event)"
            @dragstart="onSlotDragStart($event, 'total', i)"
            @touchstart="onSlotTouchStart($event, 'total', i)"
            @click="idx !== null ? clearSlot('total', i) : selectSlot('total', i)"
          >
            <DieIcon v-if="idx !== null" :die="result.rolls[idx].die" :result="result.rolls[idx].result" class="total-die-icon" />
            <span v-else class="empty-text"></span>
          </span>
        </template>
        <span class="sel-value">= <strong class="result-num">{{ computedTotal }}</strong></span>
      </div>
      <div class="selection-row" v-if="!gmMode || entityId">
        <span class="sel-label" @click="assignBestEffect">Effect:</span>
        <span
          v-for="(idx, i) in selection.effect" :key="'e'+i"
          class="sel-slot effect-slot"
          :class="{ empty: idx === null, filled: idx !== null, selected: selectedSlot?.type === 'effect' && selectedSlot?.index === i }"
          :draggable="idx !== null"
          @dragover.prevent
          @drop="onSlotDrop('effect', i, $event)"
          @dragstart="onSlotDragStart($event, 'effect', i)"
          @touchstart="onSlotTouchStart($event, 'effect', i)"
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
          v-for="x in poolGroups.regular"
          :key="x.i"
          class="die-chip"
          @click="removeDie(x.i)"
        >
          <DieIcon :die="x.die.die" :label="x.die.label || x.die.source" />
        </div>
        <div v-if="poolGroups.resource.length" class="resource-subset">
          <div
            v-for="x in poolGroups.resource"
            :key="x.i"
            class="die-chip"
            @click="removeDie(x.i)"
          >
            <DieIcon :die="x.die.die" :label="x.die.label || x.die.source" />
          </div>
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

      <div v-else-if="isManual()" class="manual-entry">
        <div class="manual-hint">
          Roll your dice and set each face — tap to type it, drag up or down to scroll.
        </div>
        <div class="manual-dice">
          <div
            v-for="(d, i) in manualDice"
            :key="i"
            class="manual-die"
            :class="{ set: manualFaces[i] != null, editing: manualEditing === i }"
            :title="`${d.label || d.die} · ${dieSize(d.die)} faces`"
            @pointerdown="manualDragStart($event, i)"
            @pointermove="manualDragMove"
            @pointerup="manualDragEnd"
            @pointercancel="manualDragEnd"
          >
            <!-- The die face *is* the readout: it shows the entered number, and
                 its own size (d8) until a face is set. `null`, not 0 — a 0 would
                 render as a literal zero, which no die has. -->
            <DieIcon :die="d.die" :result="manualFaces[i] ?? null" :label="d.label || d.die" />
            <!-- The box opens on tap, and until then there is nothing to fill in. -->
            <input
              v-if="manualEditing === i"
              :ref="el => setManualInput(i, el)"
              class="manual-face-input"
              type="number"
              inputmode="numeric"
              :min="1"
              :max="dieSize(d.die)"
              :value="manualFaces[i] ?? ''"
              :aria-label="`${d.label || d.die} result`"
              @pointerdown.stop
              @blur="manualEditing = null"
              @input="setManualFace(i, $event.target.value)"
            />
          </div>
        </div>
        <div class="manual-count">{{ manualSetCount }} / {{ manualDice.length }} set</div>
      </div>

      <div v-else-if="result && isPicking()" class="roll-pick">
        <div class="roll-dice">
          <div
            v-for="x in mainDice"
            :key="x.i"
            class="roll-die-wrap"
            :class="[rollClass(x.i)]"
            :draggable="!isHitch(x.i)"
            @dragstart="onDieDragStart($event, x.i)"
            @touchstart="onDieTouchStart($event, x.i)"
            @click="toggleDie(x.i)"
          >
            <DieIcon :die="x.r.die" :result="x.r.result" :is-hitch="isHitch(x.i)" :label="x.r.label || x.r.source_id || x.r.die" />
          </div>
        </div>
        <div v-if="resourceDice.length" class="resource-rolls">
          <span class="resource-label">resource</span>
          <div
            v-for="x in resourceDice"
            :key="x.i"
            class="roll-die-wrap resource-die"
            :class="[rollClass(x.i)]"
          >
            <DieIcon :die="x.r.die" :result="x.r.result" :is-hitch="isHitch(x.i)" :label="x.r.label || x.r.source_id || x.r.die" />
          </div>
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
            <span v-if="totalBreakdown.length" class="resolved-breakdown">
              <template v-for="(p, i) in totalBreakdown" :key="i">
                <span v-if="i"> + </span>
                <span :class="{ 'resource-addend': p.resource }">{{ p.value }}</span>
              </template>
              <span> = </span>
            </span>
            <strong class="resolved-total result-num">{{ computedTotal }}</strong>
            <DieIcon v-if="effectDie" :die="effectDie" class="resolved-eff-die" />
          </div>
        </template>
      </template>
    </div>

    <div class="controls" v-if="isAdding() || isPicking() || isRolling() || isManual()">
      <button v-if="(isAdding() || isRolling()) && (pool.length > 0 || loading)" @click="doRoll" :disabled="loading || isRolling()" class="roll-btn">
        {{ loading || isRolling() ? 'Rolling…' : 'Roll' }}
      </button>
      <!-- Physical play ([[B17]]): roll them yourself and type the faces in. -->
      <button v-if="isAdding() && pool.length > 0 && mode !== 'roll_table' && !loading" @click="enterManual" class="roll-btn manual-btn">
        Enter results
      </button>
      <button v-if="isManual()" @click="commitManual" :disabled="!manualComplete" class="roll-btn commit-btn">
        Use these results
      </button>
      <button v-if="isPicking()" @click="onPickCommit" class="roll-btn commit-btn">
        {{ challenged ? 'Set' : 'Done' }}
      </button>
      <button v-if="showGiveIn" @click="doGiveIn" class="roll-btn give-in-btn">Give in</button>
      <!-- The empty-pool exit ([[B118]]): a mis-started challenge is cancelled,
           not resolved. Only the initiator, and only before anything is rolled. -->
      <button v-if="canCancelContest" @click="cancelContest" class="roll-btn cancel-btn">Cancel contest</button>
    </div>

    <div class="controls" v-if="isResolved() && mode !== 'roll_table' && !challenged">
      <button @click="clearResult" class="roll-btn">Clear Pool</button>
      <button v-if="!gmMode" @click="showConsequences = !showConsequences" class="roll-btn">{{ showConsequences ? 'Hide consequences' : 'Consequences' }}</button>
    </div>

    <div class="controls" v-if="contestResult && iWon && (!gmMode || entityId)">
      <button @click="showConsequences = !showConsequences" class="roll-btn">{{ showConsequences ? 'Hide consequences' : 'Consequences' }}</button>
    </div>

    <div class="controls" v-if="contestResult && iGaveIn && (!gmMode || entityId)">
      <button @click="showConsequences = !showConsequences" class="roll-btn">{{ showConsequences ? 'Hide' : 'Take complication' }}</button>
    </div>

    <div class="controls" v-if="showPreventTakenOut">
      <button @click="doPreventTakenOut" class="roll-btn prevent-taken-out-btn">Prevent take out (1 razmerit)</button>
    </div>

    <div class="controls" v-if="isWaitingForDecision">
      <span class="waiting-state">Waiting for {{ opponentName }} to decide…</span>
    </div>

    <div class="controls" v-if="decisionPending">
      <button @click="doGiveIn" class="roll-btn give-in-btn">Give in</button>
      <button @click="doPush" class="roll-btn push-btn">Push</button>
    </div>

    <!-- What those two actions actually do ([[B14]]): the rules exist only as
         authored SFX, so without this the buttons are a bare "spend 1". -->
    <div v-if="giveInForecast" class="effect-forecast">Fires on give in: {{ giveInForecast }}</div>
    <div v-if="preventForecast" class="effect-forecast">Fires on prevent take out: {{ preventForecast }}</div>

    <div v-if="showConsequences && (isResolved() || contestResult)" class="consequence-panel">
      <ConsequenceMenu :entity-id="consequenceTargetId" :side="consequenceSide" :menu-context="consequenceMenuContext" :effect-die="consequenceEffectDie" :exclude-ids="consequenceExcludeIds" @close="showConsequences = false" />
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
          <div
            v-for="(r, i) in remoteView.rolls"
            :key="i"
            class="roll-die-wrap"
            :class="{ 'is-hitch': r.result === 1, 'is-bought': r.bought, 'is-selected': selectedHitches.includes(i) }"
            @click="toggleHitch(r, i)"
          >
            <DieIcon :die="r.die" :result="r.result" :label="r.label || r.source_id || r.die" />
          </div>
        </div>
        <div v-else class="dice-pool">
          <div v-for="x in viewPoolGroups.regular" :key="x.i" class="die-chip" :class="{ 'peer-rolling': remotePhase === 'rolling' }" :style="remotePhase === 'rolling' ? { animationDelay: (x.i * 90) + 'ms' } : null">
            <DieIcon :die="x.die.die" :label="x.die.label || x.die.source_id || x.die.die" />
          </div>
          <div v-if="viewPoolGroups.resource.length" class="resource-subset">
            <div v-for="x in viewPoolGroups.resource" :key="x.i" class="die-chip" :class="{ 'peer-rolling': remotePhase === 'rolling' }" :style="remotePhase === 'rolling' ? { animationDelay: (x.i * 90) + 'ms' } : null">
              <DieIcon :die="x.die.die" :label="x.die.label || x.die.source_id || x.die.die" />
            </div>
          </div>
          <div v-if="!viewPoolDice.length" class="empty-pool">No dice assembled</div>
        </div>
        <div v-if="remoteView?.botch" class="botch">BOTCH</div>
        <div v-if="remoteView?.hitches?.length" class="hitches">
          {{ remoteView.hitches.length }} hitch{{ remoteView.hitches.length > 1 ? 'es' : '' }}
        </div>
        <div v-if="showHitchMenu && selectedHitches.length" class="hitch-menu-panel">
          <HitchMenu :entity-id="activeId" :buyer-id="hitchBuyerId" :count="selectedHitches.length" :side="props.gmMode ? 'gm' : 'player'" @apply="applyHitchOption" @close="closeHitchMenu" />
        </div>
      </div>
    </template>
    <div v-if="buyHitchChoices.length" class="sfx-choice-panel">
      <EffectTargetWizard
        :entity-id="buyHitchTargetId"
        :pending-choices="buyHitchChoices"
        title="Buy a hitch — choose a complication"
        @resolve="resolveBuyHitch"
        @cancel="cancelBuyHitch"
      />
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch, nextTick, onMounted, onUnmounted } from 'vue'
import { useApi } from '../composables/useApi.js'
import { useEffectApplication } from '../composables/useEffectApplication.js'
import { useHitchMenu } from '../composables/useHitchMenu.js'
import { perfMark } from '../composables/perfLog.js'
import PoolTabs from './dice/PoolTabs.vue'
import ContestResultWidget from './dice/ContestResultWidget.vue'
import DieIcon from './DieIcon.vue'
import ConsequenceMenu from './gm/ConsequenceMenu.vue'
import EffectTargetWizard from './gm/EffectTargetWizard.vue'
import HitchMenu from './gm/HitchMenu.vue'

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
  locationName: { type: String, default: '' }, // current location's display name (difficulty-pool label)
  poolLocations: { type: Object, default: () => ({}) }, // entity_id → location_id (for test grouping)
  contests: { type: Array, default: () => [] }, // [{ location_id, challenger_id, defendant_id, parties }]
  sfxChoiceRequest: { type: Array, default: () => [] }, // pending {choose_*} auto-fired SFX choices
  peers: { type: Array, default: () => [] }, // [{ id, name }] other entities at the location
  entityNames: { type: Object, default: () => ({}) }, // id → name (all entities, for tab labels)
  remotePools: { type: Object, default: () => ({}) }, // entity_id → { dice, phase } from SSE
  remoteResults: { type: Object, default: () => ({}) }, // entity_id → { rolls, committed, ... } from SSE
})

const emit = defineEmits(['update:universe', 'rolled', 'poolChange', 'phaseChange', 'picked', 'panelOpen', 'panelDragStart', 'panelDrag', 'panelDragEnd', 'difficulty', 'sfx-choice-answer', 'sfx-choice-cancel', 'sfx-choice-loop', 'actingEntityChange', 'offered-change', 'poolSaved'])

const { loading, error, graphql, cortexRoll: apiCortexRoll, simplifiedRoll: apiSimplifiedRoll, difficultyRoll: apiDifficultyRoll, selectDice: apiSelectDice, resolvePool: apiResolvePool, markHitchesBought: apiMarkHitchesBought, savePool: apiSavePool, offerNegative: apiOfferNegative, getPool: apiGetPool, setOpposition: apiSetOpposition, setResult: apiSetResult, setStakes: apiSetStakes, giveIn: apiGiveIn, preventTakenOut: apiPreventTakenOut, push: apiPush, getTargetingBans: apiGetTargetingBans, getContest: apiGetContest, cancelContest: apiCancelContest, getPendingContestEffects: apiPendingEffects, manualRoll: apiManualRoll } = useApi()
const { resolveEffectTargets } = useEffectApplication()  // buy-a-hitch resolves locally
const { applyOption: applyHitchEffect } = useHitchMenu()
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
// Which set of consequence options to offer is not a choice to put to the user:
// a resolved context plus the role looking at it already decides. The switch
// that used to be here let a player read the GM's menu and the reverse, which
// is never a real situation ([[B118]]).
const consequenceSide = computed(() => (props.gmMode ? 'gm' : 'player'))
const buyHitchChoices = ref([])
const buyHitchTargetId = ref('')
const selectedHitches = ref([]) // roll indices the GM has toggled
const showHitchMenu = ref(false)

// ── GM roll purpose + per-entity pool tabs ───────────
const DIFFICULTY_TAB = '__difficulty__'
const poolPurpose = ref(null) // GM mode: 'difficulty' | 'gmc' | null
const activeId = ref(props.gmMode ? DIFFICULTY_TAB : props.entityId)
// The entity on whose behalf a hitch is being bought (GM acts as another entity).
const hitchBuyerId = computed(() => props.entityId || '')
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
// Split a dice pool into regular and resource subsets (keeping original
// indices so the caller can still remove/sync by index).
const poolGroups = computed(() => {
  const regular = []
  const resource = []
  pool.forEach((die, i) => (die.resource ? resource : regular).push({ die, i }))
  return { regular, resource }
})
const viewPoolGroups = computed(() => {
  const regular = []
  const resource = []
  viewPoolDice.value.forEach((die, i) => (die.resource ? resource : regular).push({ die, i }))
  return { regular, resource }
})
const opponentId = ref('')
const offeredTraitIds = ref([])  // trait-setting ids routed to the opponent's pool
const offeredTargets = ref({})   // tsId → the pool key it was routed to (for retraction)
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
const difficultyTabBlink = ref(false)  // nudge: difficulty pool changed while not looking
const highStakes = ref(false)       // contest stakes (low by default)
const difficultyFlash = ref('')

const tabEntities = computed(() => {
  // Difficulty/You tab always present; peers only when they have an active pool.
  const list = props.gmMode
    ? [{ id: DIFFICULTY_TAB, name: props.locationName || 'Difficulty' }]
    : [{ id: props.entityId, name: 'You' }]
  const seen = new Set(list.map(e => e.id))
  const pushEntity = (id) => {
    if (!id || seen.has(id)) return
    seen.add(id)
    const name = props.entityNames?.[id] || (props.peers || []).find(p => p.id === id)?.name || id
    list.push({ id, name })
  }
  if (props.entityId) pushEntity(props.entityId)
  if (challenged.value) pushEntity(opponentId.value)
  for (const [eid, rp] of Object.entries(props.remotePools || {})) {
    // The GM difficulty pool is keyed by the location id; it already has its
    // own Difficulty tab, so don't surface it again as a peer/location tab.
    if (props.gmMode && eid === props.locationId) continue
    if (seen.has(eid)) continue
    const rr = props.remoteResults?.[eid]
    const hasPool = rp && Array.isArray(rp.dice) && rp.dice.length > 0
    const hasResult = rr && (rr.rolls?.length || rr.committed)
    if (!hasPool && !hasResult) continue
    pushEntity(eid)
  }
  // An active contest is activity even before either side has rolled ([[B15]]):
  // a just-declared challenge is exactly what the GM's view is for, and it would
  // otherwise stay invisible until someone assembled dice. GM only — a player
  // has no business getting tabs for other people's contests.
  if (props.gmMode) {
    for (const c of (props.contests || [])) {
      for (const p of (c.parties || [c.challenger_id, c.defendant_id])) pushEntity(p)
    }
  }
  return list
})

// Tabs grouped by event for the GM activity view: each location with activity
// is a "test" event (labeled by its location name — the location is what rolls
// the difficulty), and each contest is a group of its competing parties. Only
// surfaces group headers when there is more than one event; a single event
// stays a flat list.
const tabGroups = computed(() => {
  const members = tabEntities.value
  if (!members.length || !props.gmMode) {
    return [{ key: 'flat', label: '', members }]
  }
  const nameOf = (id) => props.entityNames?.[id] || (props.peers || []).find(p => p.id === id)?.name || id

  // Contest party → its contest, so we can group the parties together.
  const partyContest = new Map()
  const contestByKey = new Map()
  for (const c of (props.contests || [])) {
    const key = `${c.location_id}:${c.challenger_id}`
    contestByKey.set(key, c)
    for (const p of (c.parties || [c.challenger_id, c.defendant_id])) {
      partyContest.set(p, key)
    }
  }

  // What the GM can actually see about a contest, in the author's vocabulary
  // ([[B15]]): dice not assembled, a roll in flight, sides committed, a side
  // owing a give-in/push, or both in. A side's phase comes from its own client
  // for the entity this panel drives, and from the pool feed for everyone else.
  const phaseOf = (id) => (id === editingEntityId.value ? phase.value : (props.remotePools?.[id]?.phase || 'adding'))
  const committedOf = (id) => (
    id === editingEntityId.value
      ? phase.value === 'resolved' || !!contestResult.value
      : !!props.remoteResults?.[id]?.committed
  )
  const contestMeta = (c) => {
    if (!c) return {}
    const parties = c.parties || [c.challenger_id, c.defendant_id]
    const phases = parties.map(phaseOf)
    let status
    if (c.pending) status = `waiting on ${nameOf(c.pending)}`
    else if (parties.every(committedOf)) status = 'resolving'
    else if (phases.includes('rolling') || phases.includes('manual')) status = 'rolling'
    else if (phases.some(p => p === 'rolled' || p === 'selected' || p === 'resolved')) status = 'setting'
    else status = 'adding'
    return {
      status,
      stakes: c.high_stakes ? 'high' : 'low',
      locationId: c.location_id,
      // `set_stakes` addresses either party; the challenger always has state.
      partyId: c.challenger_id,
      parties,
    }
  }

  const groups = new Map()
  const order = []
  const groupOf = (key, label, extra = {}) => {
    if (!groups.has(key)) { groups.set(key, { key, label, members: [], ...extra }); order.push(key) }
    return groups.get(key)
  }

  for (const m of members) {
    let key, label, extra = {}
    if (m.id === DIFFICULTY_TAB) {
      // The difficulty pool is the current location's own test event.
      key = `loc:${props.locationId}`
      label = props.locationName || 'Difficulty'
    } else {
      const contestKey = partyContest.get(m.id)
      if (contestKey) {
        const c = contestByKey.get(contestKey)
        key = `contest:${contestKey}`
        label = `${nameOf(c?.challenger_id)} vs ${nameOf(c?.defendant_id)}`
        extra = contestMeta(c)
      } else {
        const loc = props.poolLocations?.[m.id] || props.locationId
        key = `loc:${loc}`
        label = nameOf(loc)
      }
    }
    groupOf(key, label, extra).members.push(m)
  }
  return order.map((k) => groups.get(k))
})
const editingEntityId = computed(() => props.entityId)
const decisionPending = computed(() => !!contestCompare.value && contestCompare.value.pending === editingEntityId.value)
const isWaitingForDecision = computed(() => !!contestCompare.value && contestCompare.value.pending !== editingEntityId.value)
const isEditing = computed(() => {
  if (props.gmMode) {
    return props.entityId
      ? activeId.value === props.entityId
      : activeId.value === DIFFICULTY_TAB
  }
  return activeId.value === props.entityId
})
const activeName = computed(() => tabEntities.value.find(e => e.id === activeId.value)?.name || activeId.value)
const selfTabId = computed(() => props.gmMode ? (props.entityId || DIFFICULTY_TAB) : props.entityId)
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
const appliedEffectDie = computed(() => contestResult.value?.effect_die || null)
const iAmTakenOut = computed(() => !!contestResult.value?.taken_out && !iWon.value)

const razmerit = ref(null)  // acting entity's razmerit (fetched when a takeout happens)

watch(iAmTakenOut, async (taken) => {
  if (!taken || !editingEntityId.value) return
  const data = await graphql(`query($id: ID!) { entity(id: $id) { razmerit } }`, { id: editingEntityId.value })
  razmerit.value = data?.entity?.razmerit ?? 0
})

// The two "leave the contest" actions, in one place each: the buttons and their
// effect forecasts ([[B14]]) must agree about when they apply.
const showGiveIn = computed(() =>
  challenged.value && !contestResult.value && !contestCompare.value && giveInAllowed.value
)
const showPreventTakenOut = computed(() =>
  iAmTakenOut.value && (razmerit.value || 0) >= 1 && (!props.gmMode || !!props.entityId)
)
// Names of the authored rules that will fire, fetched from the SFX owner.
const effectForecast = ref({ give_in: [], prevent_taken_out: [] })
const giveInForecast = computed(() =>
  showGiveIn.value ? effectForecast.value.give_in.map(s => s.name).join(' · ') : ''
)
const preventForecast = computed(() =>
  showPreventTakenOut.value ? effectForecast.value.prevent_taken_out.map(s => s.name).join(' · ') : ''
)

async function loadEffectForecast() {
  if (!props.locationId || !editingEntityId.value) return
  const res = await apiPendingEffects(props.locationId, editingEntityId.value)
  if (res) {
    effectForecast.value = {
      give_in: res.give_in || [],
      prevent_taken_out: res.prevent_taken_out || [],
    }
  }
}

// Only asked for when one of the two actions is on screen — and re-asked when the
// acting entity changes, since availability is per entity ([[B14]]).
watch([showGiveIn, showPreventTakenOut, () => editingEntityId.value, () => props.locationId], () => {
  if (showGiveIn.value || showPreventTakenOut.value) loadEffectForecast()
})
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
// Menu context passed to the consequence menu so contest SFX gate on the right
// outcome: winner → contest_win, conceder → contest_give_in, else test_success.
const consequenceMenuContext = computed(() => {
  if (iWon.value && !contestResult.value?.gave_in) return 'contest_win'
  if (iGaveIn.value) return 'contest_give_in'
  return 'test_success'
})
const sumLabel = computed(() =>
  (props.gmMode && !props.entityId && activeId.value === DIFFICULTY_TAB) ? 'difficulty' : 'result'
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
  if (props.gmMode && !props.entityId && activeId.value === DIFFICULTY_TAB) return 'difficulty'
  if (isAdding() && pool.length === 0) return 'empty-pool'
  // Test: use the rolled pipeline when known, else predict from assembled size.
  // A resource die or a set test difficulty forces the Cortex pipeline even for
  // a 2-die pool (contests are handled above).
  const forcePool = pool.length > 2 || pool.some(d => d.resource) || props.difficulty != null
  const pipeline = result.value?.pipeline ?? (forcePool ? 'pool' : 'simplified')
  return pipeline === 'pool' ? 'cortex-test' : 'simple-test'
})
const rollKindLabel = computed(() => ROLL_KIND_LABELS[rollKind.value] || '')

// The set test difficulty is the target for any entity roll (player or GM
// acting as an entity); it is not shown while the GM is setting it.
const showDifficultyTarget = computed(() =>
  props.difficulty != null && !(props.gmMode && !props.entityId)
)

// Contest UI is relevant for players (or a GM acting as an entity) at a
// location with at least one peer, during assembly/picking or once challenged.
const showContest = computed(() => (!props.gmMode || props.entityId) && props.mode !== 'roll_table' && props.peers.length > 1 && (challenged.value || isAdding() || isPicking()))

// Who may cancel: the side that started it, before anything is on the table
// ([[B118]]). Once a roll exists the contest is a thing to resolve, and give-in
// is how a side leaves that one.
const canCancelContest = computed(() =>
  challenged.value && isChallenger.value && !contestResult.value && !contestCompare.value
  && !result.value && pool.length === 0
)

function markPurpose(kind) {
  if (pool.length === 0) poolPurpose.value = kind
}

function ensureSelfTab() {
  if (props.mode === 'roll_table') return
  const selfId = props.gmMode ? (props.entityId || DIFFICULTY_TAB) : props.entityId
  if (activeId.value !== selfId) activeId.value = selfId
}

async function switchTab(id) {
  activeId.value = id
  if (props.gmMode) {
    // Clicking Difficulty while acting as an entity relieves the GM of it,
    // so they can roll the difficulty dice.
    if (id === DIFFICULTY_TAB) {
      difficultyTabBlink.value = false
      if (props.entityId) emit('actingEntityChange', null)
      return
    }
    // Otherwise, GM tabs are a pool viewer only — never switch the acting entity.
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

watch(() => props.entityId, async (id) => {
  if (props.gmMode) {
    if (id) {
      activeId.value = id
      await loadPoolIntoEditor(id)
      await syncContestState()
      await loadTargetingBans()
    } else {
      activeId.value = DIFFICULTY_TAB
      // The GM difficulty pool is keyed by the location id (unified pool
      // concept); load it so dice added by SFX (e.g. sfx-heal) show up here.
      await loadPoolIntoEditor(props.locationId)
    }
  } else {
    activeId.value = id
  }
})

watch(() => props.difficulty, (v) => {
  if (v == null) return
  difficultyFlash.value = `Difficulty set: ${v}`
  setTimeout(() => {
    if (difficultyFlash.value === `Difficulty set: ${v}`) difficultyFlash.value = ''
  }, 3000)
})

// Blink the Difficulty tab when its pool changes while the GM is on a
// different tab (e.g. an SFX added dice to the GM difficulty pool).
const difficultyPoolSignature = computed(() => {
  const rp = props.remotePools?.[props.locationId]
  if (!rp || !Array.isArray(rp.dice)) return ''
  return rp.dice.map((d) => `${d.die}|${d.ts_id || d.source_id || ''}`).join(',')
})
watch(difficultyPoolSignature, (sig, old) => {
  if (!sig || sig === old) return
  if (activeId.value === DIFFICULTY_TAB) return
  difficultyTabBlink.value = true
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

/** Drop this client's contest state. `clearDice` is the canceller's own pool —
 *  the opponent keeps theirs, which is why the server only cleared one side. */
function resetContest({ clearDice = false, notice = '' } = {}) {
  challenged.value = false
  isChallenger.value = false
  opponentId.value = ''
  contestResult.value = null
  contestCompare.value = null
  contestError.value = ''
  contestNotice.value = notice
  giveInAllowed.value = false
  opponentCommitted.value = null
  showConsequences.value = false
  if (clearDice) {
    pool.splice(0, pool.length)
    resetEditor()
    setPhase(Phase.ADDING)
  }
}

async function cancelContest() {
  if (!props.locationId) return
  const res = await apiCancelContest(props.locationId, editingEntityId.value)
  if (!res || res.status !== 'cancelled') {
    contestError.value = res?.reason || 'Could not cancel the contest'
    return
  }
  resetContest({ clearDice: true })
}

/** The other side (or the GM watching) is told the contest is off. */
function onContestCancelled(data) {
  if (!challenged.value) return
  const byMe = data?.entity_id === editingEntityId.value
  resetContest({ notice: byMe ? '' : `${opponentName.value} cancelled the contest` })
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
    const total = selection.total.reduce((sum, idx) => sum + (idx !== null ? r.rolls[idx].result : 0), 0) + resourceKeptResult.value
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

async function doPreventTakenOut() {
  if (!props.locationId) return
  contestError.value = ''
  const res = await apiPreventTakenOut(props.locationId, editingEntityId.value, contestResult.value?.effect_die)
  if (res && res.prevented) {
    contestResult.value = { ...contestResult.value, taken_out: false }
    razmerit.value = Math.max(0, (razmerit.value || 0) - 1)
    contestNotice.value = 'You prevented being taken out'
  } else {
    contestError.value = res?.reason || 'Cannot prevent take out'
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
    contestError.value = 'Push unavailable (not your turn)'
  } else {
    contestError.value = 'Push unavailable'
  }
}

// The SFX choice table is one of **three hosts** now, and the app shell owns the
// answer: it knows where the table was raised and carries the origin across
// follow-ups, so a question asked on a sheet does not reopen in the roller. This
// panel renders the `roll` (and, until [[ui-ux]]'s floating host exists, `auto`)
// questions and hands the answer up.
function resolveSfxChoices(resolutions) {
  emit('sfx-choice-answer', resolutions)
}
function clearSfxChoices() {
  emit('sfx-choice-cancel')
}

// "Run it again" on a loop prompt. The round's own consequences come back as
// `structured` — including the next loop prompt when the rule recursed — so the
// panel keeps showing whatever still needs an answer.
function runSfxLoop(choice) {
  emit('sfx-choice-loop', choice)
}

// ── Buy-hitch / opportunity (hitch menu) ────────────
function toggleHitch(r, i) {
  if (r.result !== 1 || r.bought) return
  selectedHitches.value = selectedHitches.value.includes(i)
    ? selectedHitches.value.filter((x) => x !== i)
    : [...selectedHitches.value, i]
  showHitchMenu.value = selectedHitches.value.length > 0
}

function closeHitchMenu() {
  showHitchMenu.value = false
  selectedHitches.value = []
}

async function applyHitchOption(opt) {
  const rollerId = activeId.value
  if (!rollerId || rollerId === DIFFICULTY_TAB) return
  buyHitchTargetId.value = rollerId
  try {
    const vars = {
      number_of_hitches: selectedHitches.value.length,
      hitch_entity: rollerId,
      buying_entity: props.gmMode
        ? (props.entityId || '')
        : (props.entityId || ''),
    }
    const result = await applyHitchEffect(rollerId, opt, vars)
    if (result?.pendingChoices?.length) {
      buyHitchChoices.value = result.pendingChoices
      showHitchMenu.value = false
    }
  } catch (e) {
    console.error('[hitch-menu] apply failed', e)
  }
}

async function resolveBuyHitch(resolutions) {
  const rollerId = buyHitchTargetId.value
  await resolveEffectTargets(rollerId, resolutions)
  if (selectedHitches.value.length) {
    await apiMarkHitchesBought(props.locationId, rollerId, [...selectedHitches.value])
  }
  buyHitchChoices.value = []
  buyHitchTargetId.value = ''
  selectedHitches.value = []
  showHitchMenu.value = false
}

function cancelBuyHitch() {
  buyHitchChoices.value = []
  buyHitchTargetId.value = ''
  selectedHitches.value = []
  showHitchMenu.value = false
}
watch(panelOpen, (v) => emit('panelOpen', v))

// ── Panel drag-to-open/close gesture ───────────────
// The whole roller is the drag handle; touches on dice/slots are skipped
// (they use the dice drag-and-drop path). We emit raw deltas up so App can
// move the wrapper 1:1 with the finger, then settle by threshold/velocity.
const PANEL_DRAG_SLOP = 8  // px: ignore tiny movements so taps on buttons still work

let panelDrag = null  // { startY, lastY, lastT, velocity, started }

function onRollerTouchStart(e) {
  if (touchDrag.value) return                 // a die/slot drag is in progress
  if (phase.value === Phase.PICKING) return   // don't disturb dice selection
  const y = e.touches[0].clientY
  panelDrag = { startY: y, lastY: y, lastT: performance.now(), velocity: 0, started: false }
  emit('panelDragStart')
}

function onPanelTouchMove(e) {
  if (!panelDrag) return
  const y = e.touches[0].clientY
  const dy = y - panelDrag.startY
  if (!panelDrag.started) {
    if (Math.abs(dy) < PANEL_DRAG_SLOP) return  // wait for the finger to commit
    panelDrag.started = true
  }
  e.preventDefault()
  const now = performance.now()
  const dt = now - panelDrag.lastT
  if (dt > 0) {
    const inst = (y - panelDrag.lastY) / dt
    panelDrag.velocity = panelDrag.velocity * 0.75 + inst * 0.25
  }
  panelDrag.lastY = y
  panelDrag.lastT = now
  emit('panelDrag', dy)
}

function onPanelTouchEnd(e) {
  if (!panelDrag) return
  const y = e.changedTouches[0].clientY
  const dy = y - panelDrag.startY
  const velocity = panelDrag.velocity
  panelDrag = null
  emit('panelDragEnd', { dy, velocity })
}

// ── Phases ──────────────────────────────────────────
const Phase = { ADDING: 'adding', ROLLING: 'rolling', MANUAL: 'manual', PICKING: 'picking', RESOLVED: 'resolved' }
const phase = ref(Phase.ADDING)

function setPhase(p) {
  phase.value = p
  emit('phaseChange', p)
  if (p !== Phase.ADDING) panelOpen.value = true  // show results
}

function isAdding()  { return phase.value === Phase.ADDING }
function isRolling() { return phase.value === Phase.ROLLING }
// Physical play ([[B17]]): the dice are rolled away from the screen and the
// player enters each face, so there is no roll in flight to animate.
function isManual()  { return phase.value === Phase.MANUAL }
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
  if (props.gmMode && !props.entityId) return props.locationId
  return editingEntityId.value
}

function buildPoolDice() {
  return pool.map(d => ({
    die: d.die,
    source_kind: d.sourceKind || 'manual',
    source_id: d.tsId || d.source || '',
    label: d.label || d.source || d.die,
    ts_id: d.tsId || null,
    armed_sfx_ids: d.armedSfxIds || [],
  }))
}

function persistPool() {
  if (!props.locationId) return
  const key = poolEntityKey()
  if (!key) return
  apiSavePool(props.locationId, key, buildPoolDice())
}

function notifyPool() {
  persistPool()
  emit('poolChange', pool.map(d => ({ die: d.die, label: d.label || d.source || d.die, tsId: d.tsId })).filter(d => d.label))
  // Mirror the saved pool into the App's tab registry so the acting entity's
  // tab persists after the GM switches away (self-edits don't reach the SSE
  // echo, and solo play has no SSE broadcast at all).
  const key = poolEntityKey()
  if (key) emit('poolSaved', { key, locationId: props.locationId, dice: buildPoolDice() })
}

// Is the pool already exactly the roll-table dice being prepared? The wizard's
// `setupRoller` re-emits on every mount, and a parent re-render can remount it
// (B120); without this check each remount re-cleared and re-added, and every
// write emitted `poolSaved` — the loop. Comparing the live pool lets a repeated
// prepare be a no-op, while a genuinely cleared pool still gets its die back.
function poolMatchesRollTableDice(dice = []) {
  if (pool.length !== dice.length) return false
  return dice.every((d, i) => {
    const p = pool[i]
    if (!p) return false
    return String(p.die).toLowerCase() === String(d.die).toLowerCase()
      && (p.label || p.source || '') === (d.label || d.source || '')
  })
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
  const { source, label, tsId, negative, resource, armedSfxIds } = payload || {}
  const dice = Array.isArray(payload?.dice) ? payload.dice : (payload?.die ? [payload.die] : [])
  if (!dice.length) return
  // A negative trait never sits in its owner's own pool — it is the other
  // side's ammunition. In a contest that is the opponent; with no contest the
  // difficulty (location) pool is the opposition. GM free-roam already writes
  // to the location pool below, so it keeps the plain path.
  // Only a contest offer earns the `on_trait_offered` reward — the difficulty
  // destination must not, or the seeded +1 razmerit becomes farmable.
  if (negative && poolEntityKey() !== props.locationId) {
    const contestTarget = (challenged.value && opponentId.value) ? opponentId.value : null
    addToOpponentPool(dice, source, label, tsId, contestTarget || props.locationId, !!contestTarget)
    return
  }
  // Toggle: if a non-resource trait is already in the pool, remove its dice.
  // Resource dice stack — each click spends another die of the chosen type.
  if (!resource && tsId != null && pool.some(d => d.tsId === tsId)) {
    removeByTsId(tsId)
    return
  }
  // A die added from a sheet in GM free-roam joins the location-keyed
  // difficulty pool (so it rolls as a difficulty, no hitches); otherwise it
  // joins the acting entity's pool.
  markPurpose(props.gmMode && !props.entityId ? 'difficulty' : 'gmc')
  for (const die of dice) {
    pool.push({ die, source, label: label || source, tsId: tsId ?? null, sourceKind: 'trait', resource: !!resource, armedSfxIds: armedSfxIds || [] })
  }
  panelOpen.value = true
  notifyPool()
}

async function addToOpponentPool(dice, source, label, tsId, targetId = null, award = true, removeOnly = false) {
  // `targetId` defaults to where this trait was routed before (so a retraction
  // reaches the pool it actually went to, even if the contest has since ended),
  // then to the contest opponent. The difficulty pool passes the location id.
  const target = targetId || offeredTargets.value[tsId] || opponentId.value
  if (!props.locationId || !target) return
  // Server-authoritative toggle + reveal + reward (on_trait_offered).
  const res = await apiOfferNegative(
    props.locationId,
    editingEntityId.value,
    target,
    tsId,
    dice,
    label || source || '',
    award,
    removeOnly,
  )
  if (res) {
    if (res.removed) {
      offeredTraitIds.value = offeredTraitIds.value.filter(id => id !== tsId)
      const { [tsId]: _retracted, ...rest } = offeredTargets.value
      offeredTargets.value = rest
    } else if (res.offered && tsId && !offeredTraitIds.value.includes(tsId)) {
      offeredTraitIds.value = [...offeredTraitIds.value, tsId]
      offeredTargets.value = { ...offeredTargets.value, [tsId]: target }
    }
    emit('offered-change', offeredTraitIds.value)
  }
  panelOpen.value = true
}

// Take a trait group's negative baggage back out of the pool it was routed to.
// Called when the group leaves its owner's pool — the negative must not outlive
// the trait that carried it. Idempotent server-side (`remove_only`), so a stale
// client view cannot turn this into a fresh offer.
function retractNegative({ tsId, source, label } = {}) {
  if (!tsId || !offeredTraitIds.value.includes(tsId)) return
  addToOpponentPool([], source, label, tsId, offeredTargets.value[tsId] || null, false, true)
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

function stampArmedSfx(tsId, sfxId) {
  // Re-stamp dice already in the pool when the SFX is armed after adding.
  let changed = false
  for (const d of pool) {
    if (d.tsId === tsId && !(d.armedSfxIds || []).includes(sfxId)) {
      d.armedSfxIds = [...(d.armedSfxIds || []), sfxId]
      changed = true
    }
  }
  if (changed) notifyPool()
}

defineExpose({ addFromSheet, removeBySource, removeByTsId, retractNegative, splitDie, clearPool, syncPool, resyncTraitDie, onChallenged, onContestCancelled, setContestOutcome, onContestCompare, onContestPush, onOpponentCommitted, onOpponentGiveIn, loadTargetingBans, setHighStakes, stampArmedSfx, panelOpen, poolMatchesRollTableDice })

function isHitch(idx) {
  if (!result.value) return false
  // When the GM is rolling to set difficulty, a 1 is an ordinary die —
  // hitches only apply to actual rolls, not difficulty determination.
  if (props.gmMode && !props.entityId && poolPurpose.value === 'difficulty') return false
  const r = result.value.rolls[idx]
  return r ? r.result === 1 : false
}

function toggleDie(idx) {
  if (!result.value || result.value.pipeline !== 'pool') return
  if (isHitch(idx)) return
  if (result.value.rolls[idx].resource) return  // resource dice auto-pick
  ensureSlots()

  // If die is already placed, remove it
  const tIdx = selection.total.indexOf(idx)
  if (tIdx !== -1) { selection.total[tIdx] = null; selectedSlot.value = null; syncSelection(); return }
  const eIdx = selection.effect.indexOf(idx)
  if (eIdx !== -1) { selection.effect[eIdx] = null; selectedSlot.value = null; syncSelection(); return }

  // If a slot is selected, place die there
  if (selectedSlot.value) {
    const { type, index } = selectedSlot.value
    if (selection[type][index] === null) {
      selection[type][index] = idx
      selectedSlot.value = null
      syncSelection()
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
  syncSelection()
}

function clearSlot(type, i) {
  if (type === 'total') selection.total[i] = null
  else selection.effect[i] = null
  syncSelection()
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

// Source of an in-flight drag: where the die is coming from (a slot, or the pool).
// { dieIdx: number, type: 'total'|'effect'|null, index: number|null }
const dragSource = ref(null)
const touchDrag = ref(null)  // { dieIdx, type, index, el, startX, startY, ghost }

function onDieDragStart(e, idx) {
  dragSource.value = { dieIdx: idx, type: null, index: null }
  e.dataTransfer.effectAllowed = 'move'
  e.dataTransfer.setData('text/plain', String(idx))
}

function onSlotDragStart(e, type, i) {
  const dieIdx = selection[type][i]
  if (dieIdx === null || dieIdx === undefined) return
  dragSource.value = { dieIdx, type, index: i }
  e.dataTransfer.effectAllowed = 'move'
  e.dataTransfer.setData('text/plain', String(dieIdx))
}

function startTouchDrag(e, dieIdx, type, index) {
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

  touchDrag.value = { dieIdx, type, index, el, ghost, startX: touch.clientX, startY: touch.clientY }
  el.style.opacity = '0.3'
}

function onDieTouchStart(e, idx) {
  if (isHitch(idx)) return
  startTouchDrag(e, idx, null, null)
}

function onSlotTouchStart(e, type, i) {
  const dieIdx = selection[type][i]
  if (dieIdx === null || dieIdx === undefined) return
  startTouchDrag(e, dieIdx, type, i)
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
  const { dieIdx, type, index, el, ghost } = touchDrag.value
  touchDrag.value = null
  el.style.opacity = ''
  ghost.remove()

  // Find which slot the touch ended on
  const touch = e.changedTouches[0]
  const target = document.elementFromPoint(touch.clientX, touch.clientY)
  const slot = target?.closest('.sel-slot')
  if (!slot) return

  const slotType = slot.classList.contains('total-slot') ? 'total' : 'effect'
  const slots = Array.from(slot.parentElement.querySelectorAll('.sel-slot'))
  const slotIndex = slots.indexOf(slot)
  if (slotIndex < 0 || slotIndex >= selection[slotType].length) return  // out of bounds

  placeDraggedDie({ dieIdx, type, index }, slotType, slotIndex)
}

function onSlotDrop(type, slotIndex, e) {
  const source = dragSource.value
  dragSource.value = null
  if (!source) return
  placeDraggedDie(source, type, slotIndex)
}

/** The slot a die currently occupies, or null. A die is unassigned, a result, or
 *  an effect — never more than one of them. */
function slotOf(dieIdx) {
  const t = selection.total.indexOf(dieIdx)
  if (t !== -1) return { type: 'total', index: t }
  const e = selection.effect.indexOf(dieIdx)
  if (e !== -1) return { type: 'effect', index: e }
  return null
}

// Move the dragged die into the target slot. If the target is occupied, the
// displaced die swaps into the slot the dragged die came from (or returns to the
// pool when the drag started on an unassigned pool die).
function placeDraggedDie(source, type, slotIndex) {
  const { dieIdx } = source

  // A drag from a slot names where it started; a drag from the *pool* does not,
  // because the pool tile stays draggable after the die has been picked. Resolve
  // the die's actual slot, or a second drag from the pool leaves it in both.
  const from = source.type ? { type: source.type, index: source.index } : slotOf(dieIdx)

  // Lift the dragged die out of the slot it was in, if any.
  if (from) selection[from.type][from.index] = null

  const existing = selection[type][slotIndex]
  // Swap: the displaced die takes the slot the dragged die came from (a pool
  // source leaves it unpicked, so the displaced die just returns to the pool).
  if (existing !== null && from) {
    selection[from.type][from.index] = existing
  }

  selection[type][slotIndex] = dieIdx

  selectedSlot.value = null
  syncSelection()
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
  const valid = r.map((roll, i) => (isHitch(i) || roll.resource) ? -1 : i).filter(i => i !== -1)
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
  syncSelection()
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
  const valid = r.map((roll, i) => (isHitch(i) || roll.resource) ? -1 : i).filter(i => i !== -1)
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
  syncSelection()
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

// Resource dice roll as a separate pool — the highest one auto-applies.
const resourceIndices = computed(() => {
  if (!result.value) return []
  return result.value.rolls.map((r, i) => (r.resource ? i : -1)).filter(i => i !== -1)
})

const resourceKeptIndex = computed(() => {
  const idxs = resourceIndices.value
  const r = result.value?.rolls
  if (!idxs.length || !r) return null
  // Hitches (1s) don't count toward the total — exclude them from the pick.
  const eligible = idxs.filter(i => !isHitch(i))
  if (!eligible.length) return null
  return eligible.reduce((a, b) => (r[b].result > r[a].result ? b : a), eligible[0])
})

const resourceKeptResult = computed(() => {
  const i = resourceKeptIndex.value
  if (i == null || !result.value) return 0
  return result.value.rolls[i].result
})

// Display helpers: main dice vs resource dice, and the total breakdown.
const mainDice = computed(() => {
  if (!result.value) return []
  return result.value.rolls.map((r, i) => ({ r, i })).filter(x => !x.r.resource)
})

const resourceDice = computed(() => {
  if (!result.value) return []
  return result.value.rolls.map((r, i) => ({ r, i })).filter(x => x.r.resource)
})

const totalBreakdown = computed(() => {
  if (!result.value || result.value.pipeline !== 'pool') return []
  const r = result.value.rolls
  const parts = selection.total.filter(i => i !== null).map(i => ({ value: r[i].result, resource: false }))
  if (resourceKeptIndex.value != null) parts.push({ value: r[resourceKeptIndex.value].result, resource: true })
  return parts
})

function rollClass(idx) {
  if (selection.total.includes(idx)) return 'selected-total'
  if (selection.effect.includes(idx)) return 'selected-effect'
  if (resourceKeptIndex.value === idx) return 'resource-kept'
  if (resourceIndices.value.includes(idx)) return 'resource-other'
  return ''
}

const computedTotal = computed(() => {
  if (!result.value || result.value.pipeline !== 'pool') return 0
  const r = result.value.rolls
  return selection.total.reduce((sum, idx) => sum + (idx !== null ? r[idx].result : 0), 0) + resourceKeptResult.value
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
  // No leftover die to serve as the effect die → it defaults to a d4.
  return idx !== undefined && idx !== null ? result.value.rolls[idx].die : 'd4'
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
// Physical-play face entry ([[B17]]): how far a drag must travel before it counts
// as scrolling rather than a tap, and how much travel is one face.
const DRAG_THRESHOLD_PX = 8
const DRAG_STEP_PX = 16

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
  const prep = await prepareRollPool()
  if (!prep) return
  setPhase(Phase.ROLLING)
  const { dice, key, isDifficulty, useCortex } = prep

  // Blink random faces while the request is in flight, then lock each die
  // left-to-right so the player can see the numbers fall into place.
  const t0 = Date.now()
  const anim = startRollAnimation(dice)
  const result_ = isDifficulty
    ? await apiDifficultyRoll(props.locationId, key)
    : useCortex
      ? await apiCortexRoll(props.locationId, key)
      : await apiSimplifiedRoll(props.locationId, key)

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

/** Assemble the wire dice for a roll and persist the pool.
 *
 * Shared by the server roll and the manual entry ([[B17]]) so both address the
 * *same* stored pool, in the same order — the manual results are positional, and
 * a padded or reordered pool would put a face on the wrong die.
 */
async function prepareRollPool() {
  const dice = pool.map(d => {
    const spec = {
      die: d.die,
      source_kind: d.sourceKind || 'manual',
      source_id: d.tsId || d.source || '',
      label: d.label || d.source || d.die,
      ts_id: d.tsId || null,
      armed_sfx_ids: d.armedSfxIds || [],
    }
    if (d.resource) spec.resource = true
    return spec
  })
  const hasResource = dice.some(d => d.resource)
  const isDifficulty = props.gmMode && !props.entityId && poolPurpose.value === 'difficulty'
  // A set test difficulty (player or GM-as-entity) or an active contest must
  // resolve as a full Cortex test (keep-2 + effect die), never the simplified
  // 1-2 die pipeline.
  const hasTestDifficulty = props.difficulty != null && !isDifficulty
  const inContest = challenged.value
  const useCortex = hasResource || hasTestDifficulty || inContest || dice.length > 2
  // A Cortex test always needs at least 3 dice (2 to keep + 1 effect); pad
  // short pools with d4s. The GM difficulty roll keeps its exact dice.
  if (useCortex && !isDifficulty && dice.length < 3) {
    while (dice.length < 3) {
      dice.push({ die: 'd4', source_kind: 'manual', source_id: '', label: 'd4', ts_id: null })
    }
  }
  const key = poolEntityKey()

  // Persist the assembled pool (entity or difficulty) before it is rolled.
  if (props.locationId && key) {
    await apiSavePool(props.locationId, key, dice)
  }
  return { dice, key, isDifficulty, useCortex }
}

// ── Physical play: the player's own dice ([[B17]]) ───────────────────
// No roll is sent; each face is entered. Tapping a die focuses its number box,
// and dragging up/down scrolls the face within the die's own size.
const manualDice = ref([])      // the specs, in the order the pool was saved
const manualFaces = ref([])     // null = not entered yet
// Which die is being typed into. The face box exists only while it is open —
// the author's spec is that *tapping a die* gives you the input, and a screenful
// of empty boxes reads as UI you have to fill before you can start.
const manualEditing = ref(null)
const manualInputs = []
let manualDrag = null

const manualSetCount = computed(() => manualFaces.value.filter(v => v !== null && v !== undefined).length)
const manualComplete = computed(() =>
  manualDice.value.length > 0 && manualSetCount.value === manualDice.value.length
)
function dieSize(die) {
  return parseInt(String(die || 'd6').slice(1), 10) || 6
}
function setManualInput(i, el) { manualInputs[i] = el }

function setManualFace(i, raw) {
  if (raw === '' || raw === null || raw === undefined) { manualFaces.value[i] = null; return }
  const n = parseInt(raw, 10)
  if (Number.isNaN(n)) { manualFaces.value[i] = null; return }
  manualFaces.value[i] = Math.max(1, Math.min(dieSize(manualDice.value[i]?.die), n))
}

function manualDragStart(e, i) {
  // Both matter on a touch screen: `preventDefault` stops the browser firing the
  // compatibility click *after* the tap, which moved focus off the box we just
  // opened — the keyboard appeared and vanished in the same gesture.
  e.preventDefault()
  manualDrag = { i, y: e.clientY, moved: false, start: manualFaces.value[i] ?? 1 }
  try { e.currentTarget?.setPointerCapture?.(e.pointerId) } catch { /* not capturable */ }
}
function manualDragMove(e) {
  if (!manualDrag) return
  const dy = manualDrag.y - e.clientY  // up = higher
  if (!manualDrag.moved && Math.abs(dy) < DRAG_THRESHOLD_PX) return
  manualDrag.moved = true
  const step = Math.trunc(dy / DRAG_STEP_PX)
  const size = dieSize(manualDice.value[manualDrag.i]?.die)
  manualFaces.value[manualDrag.i] = Math.max(1, Math.min(size, manualDrag.start + step))
}
function manualDragEnd(e) {
  if (!manualDrag) return
  const { i, moved } = manualDrag
  manualDrag = null
  try { e?.currentTarget?.releasePointerCapture?.(e.pointerId) } catch { /* already gone */ }
  // A tap (no movement) means "I want to type this one" — open the box, then
  // focus it in the same gesture so the on-screen keyboard stays up.
  if (!moved) {
    manualEditing.value = i
    nextTick(() => manualInputs[i]?.focus?.({ preventScroll: true }))
  }
}

async function enterManual() {
  if (props.mode === 'roll_table') return
  const prep = await prepareRollPool()
  if (!prep) return
  // Nothing from a previous roll belongs on this screen: the result slots and
  // the resolved status lines are both driven off `result`, and picking is the
  // *next* phase — the entry screen should be dice and nothing else.
  result.value = null
  showConsequences.value = false
  youTabBlink.value = false
  manualDice.value = prep.dice
  manualFaces.value = prep.dice.map(() => null)
  manualEditing.value = null
  setPhase(Phase.MANUAL)
}

async function commitManual() {
  if (!manualComplete.value || !props.locationId) return
  const key = poolEntityKey()
  const res = await apiManualRoll(
    props.locationId,
    key,
    manualFaces.value.map(v => Number(v)),
    { hitches: !(props.gmMode && !props.entityId && poolPurpose.value === 'difficulty') },
  )
  if (!res) {
    // The API helper already surfaced the server's reason (an out-of-range face
    // reads as such); only fall back when it said nothing.
    if (!error.value) error.value = 'Could not record those results'
    return
  }
  result.value = res
  pool.length = 0
  emit('poolChange', [])
  if (res.pipeline === 'pool' && props.mode !== 'roll_table') {
    setPhase(Phase.PICKING)
    ensureSlots()
  } else {
    setPhase(Phase.RESOLVED)
  }
  emit('rolled', res)
  manualDice.value = []
  manualFaces.value = []
  manualEditing.value = null
}

function commitPicks() {
  setPhase(Phase.RESOLVED)
  if (props.gmMode && !props.entityId) {
    // GM difficulty roll: the picked total is the difficulty.
    emit('difficulty', computedTotal.value)
    return
  }
  // Player (or GM acting as an entity): emit final picked result for sharing
  if (result.value?.pipeline === 'pool') {
    const r = result.value.rolls
    const total = selection.total.reduce((sum, idx) => sum + (idx !== null ? r[idx].result : 0), 0) + resourceKeptResult.value
    const effIdx = selection.effect[0]
    const effDie = effIdx !== null ? r[effIdx].die : 'd4'
    emit('picked', { total, effect_die: effDie, pipeline: 'pool', botch: result.value.botch })
  } else if (result.value) {
    emit('picked', result.value)
  }
}

// Push the current result/effect selection to the stored pool. Called after
// every selection change (drag/drop/swap/click/auto-assign) so the server and
// peers stay in sync; also the authoritative first step of committing a pick.
async function syncSelection() {
  if (result.value?.pipeline !== 'pool') return
  if (props.mode === 'roll_table') return
  const key = poolEntityKey()
  if (!props.locationId || !key) return
  const total = selection.total.filter(i => i !== null)
  const effect = selection.effect.find(i => i !== null)
  const isDifficulty = props.gmMode && !props.entityId
  await apiSelectDice(props.locationId, key, total, isDifficulty ? null : (effect ?? null))
}

async function onPickCommit() {
  await syncSelection()
  if (challenged.value) {
    doSetResult()
  } else {
    await apiResolvePool(props.locationId, poolEntityKey())
    commitPicks()
  }
}

function clearResult() {
  clearPool()
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
  if (offeredTraitIds.value.length) {
    offeredTraitIds.value = []
    offeredTargets.value = {}
    emit('offered-change', [])
  }
}

function syncPool(dice, { notify = true } = {}) {
  // Replace the local pool with the server's authoritative dice (e.g. when
  // another entity offers a negative trait into this entity's pool, or when an
  // effect played one of my traits at another size).
  //
  // `notify: false` is for a broadcast the server sent about a change it made
  // itself: the panel must show it, but re-saving it would be an echo.
  if (phase.value !== Phase.ADDING) return
  if (!Array.isArray(dice)) return
  pool.splice(0, pool.length)
  for (const d of dice) {
    pool.push({
      die: d.die,
      source: d.source_id || d.source || '',
      label: d.label || d.die,
      tsId: d.ts_id || null,
      sourceKind: d.source_kind || 'manual',
      resource: !!d.resource,
    })
  }
  panelOpen.value = true
  if (notify) notifyPool()
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

function restoreRolledResult(dice, phase = '') {
  // Reconstruct the rolled result + selection from the stateful pool dice.
  const hitches = dice.filter(d => d.hitch)
  const botch = dice.length > 0 && dice.every(d => d.hitch)
  const hasResource = dice.some(d => d.resource)
  if (dice.length <= 2 && !hasResource) {
    // Simplified rolls resolve immediately (no picking phase).
    const highest = Math.max(...dice.map(d => d.result))
    const tier = highest <= 2 ? 'FAIL' : highest <= 5 ? 'MARGINAL' : highest <= 8 ? 'SUCCESS' : highest <= 11 ? 'EXCEPTIONAL' : 'PERFECT'
    const effect = { FAIL: null, MARGINAL: 'd4', SUCCESS: 'd6', EXCEPTIONAL: 'd8', PERFECT: 'd10' }[tier]
    result.value = { pipeline: 'simplified', rolls: dice, hitches, botch, highest, tier, effect_die: effect }
    setPhase(Phase.RESOLVED)
  } else {
    result.value = { pipeline: 'pool', rolls: dice, hitches, botch }
    selection.total = dice.map((d, i) => d.role === 'total' ? i : null).filter(i => i !== null)
    selection.effect = dice.map((d, i) => d.role === 'effect' ? i : null).filter(i => i !== null)
    ensureSlots()
    setPhase(phase === 'resolved' ? Phase.RESOLVED : Phase.PICKING)
  }
  panelOpen.value = true
}

async function loadPoolIntoEditor(id) {
  if (!props.locationId || !id) return
  const res = await apiGetPool(props.locationId, id)
  const dice = res?.dice || []
  const phase = res?.phase || 'adding'
  pool.splice(0, pool.length)
  if (dice.some(d => d.result != null)) {
    // Already rolled — restore the rolled result instead of treating it as unrolled.
    restoreRolledResult(dice, phase)
    return
  }
  for (const d of dice) {
    pool.push({
      die: d.die,
      source: d.source_id || d.source || '',
      label: d.label || d.die,
      tsId: d.ts_id || null,
      sourceKind: d.source_kind || 'manual',
      resource: !!d.resource,
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
    // In a compare/pending state there is nothing to roll or pick — show the
    // decision UI (Give in / Push) rather than the unrolled pool.
    setPhase(Phase.RESOLVED)
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

/** Stakes for a contest the GM is *not* the one driving ([[B15]]): addressed to
 *  a party of that contest, from the tab group's own row. The server broadcasts
 *  `contest_stakes`, and App folds it back into the contest list, so the row
 *  reflects the change without an optimistic guess here. */
async function onGroupStakes(group) {
  if (!group?.locationId || !group?.partyId) return
  const res = await apiSetStakes(group.locationId, group.partyId, group.stakes !== 'high')
  if (!res || res.status === 'no_contest') contestError.value = 'That contest is no longer active'
}

async function restorePool() {
  if (props.gmMode && !props.entityId) {
    // GM difficulty mode: load the location-keyed difficulty pool.
    await loadPoolIntoEditor(props.locationId)
    return
  }
  await loadPoolIntoEditor(editingEntityId.value)
  await syncContestState()
  await loadTargetingBans()
}

onMounted(() => {
  console.log('[diag] DiceRoller mounted', { entityId: props.entityId, universe: props.universe })
  document.addEventListener('touchmove', onDocTouchMove, { passive: false })
  document.addEventListener('touchend', onDocTouchEnd)
  document.addEventListener('touchmove', onPanelTouchMove, { passive: false })
  document.addEventListener('touchend', onPanelTouchEnd)
  restorePool().then(() => perfMark('pool-restored'))
})

watch([() => props.entityId, () => props.locationId], restorePool)
onUnmounted(() => {
  document.removeEventListener('touchmove', onDocTouchMove)
  document.removeEventListener('touchend', onDocTouchEnd)
  document.removeEventListener('touchmove', onPanelTouchMove)
  document.removeEventListener('touchend', onPanelTouchEnd)
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
  cursor: grab; padding: 10px 0; border-top: 2px solid var(--overlay-10);
  min-height: 44px; display: flex; align-items: center; justify-content: center;
  -webkit-tap-highlight-color: transparent;
  touch-action: none;
  user-select: none;
  flex-shrink: 0;
}
.phase-label {
  font-size: 10px; text-transform: uppercase; letter-spacing: 2px;
  color: var(--text-dim); background: var(--overlay-4);
  padding: 2px 12px; border-radius: 4px;
}

h3 { font-size: 14px; color: var(--text-dim); margin-bottom: 4px; }

.commit-btn { background: var(--success) !important; color: var(--text-invert) !important; }

.dice-pool { display: flex; justify-content: center; flex-wrap: wrap; gap: 6px; min-height: 28px; }
.dice-stage { display: flex; flex-direction: column; gap: var(--gap); min-height: 48px; }

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
  background: var(--overlay-6); border: 1px solid var(--overlay-12);
}
.opponent-result-badge .result-num { font-size: 16px; color: var(--text); }
.opponent-effect-die { width: 20px; height: 22px; }
.contest-notice { font-size: 12px; color: var(--accent, #7aa2f7); }
.contest-result { font-size: 13px; display: flex; flex-direction: column; gap: 2px; }

.peer-pool { display: flex; flex-direction: column; gap: 8px; }
.peer-pool-title { font-size: 12px; text-transform: uppercase; letter-spacing: 1px; color: var(--text-dim); }
.peer-committed { font-size: 14px; display: flex; align-items: center; justify-content: center; gap: 8px; }
.peer-effect-die { width: 32px; height: 36px; }
.empty-pool { font-size: 12px; color: var(--text-dim); opacity: 0.7; }

.die-chip {
  cursor: pointer; transition: opacity 0.2s;
}
.die-chip:hover { opacity: 0.7; }

.resource-subset {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 2px 4px;
  border-radius: 8px;
  background: var(--resource-12);
}
.die-chip.peer-rolling { animation: die-pulse 0.7s ease-in-out infinite; }
@keyframes die-pulse { 0%, 100% { transform: scale(1); filter: brightness(1); } 50% { transform: scale(1.12); filter: brightness(1.5); } }

.add-die-toggle {
  width: 36px;
  height: 40px;
  border-radius: 8px;
  border: 2px dashed var(--overlay-20);
  background: var(--overlay-4);
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
  background: var(--accent-12);
}

.add-die { display: flex; gap: 6px; justify-content: center; }
.die-btn {
  flex: 1; padding: 4px;
  border-radius: 8px; cursor: pointer; transition: all 0.15s;
  border: 2px solid transparent; background: var(--overlay-2);
  color: var(--text);
  display: flex; align-items: center; justify-content: center;
}
.add-die-icon {
  width: 40px;
  height: 44px;
}
.die-btn:hover { background: var(--overlay-12); border-color: var(--accent-dim); }
.die-btn-d4  { color: var(--die-d4); }
.die-btn-d6  { color: var(--die-d6); }
.die-btn-d8  { color: var(--die-d8); }
.die-btn-d10 { color: var(--die-d10); }
.die-btn-d12 { color: var(--die-d12); }

.controls { display: flex; gap: 8px; }
.waiting-state { flex: 1; text-align: center; font-size: 14px; color: var(--text-dim); padding: 10px; }
.consequence-panel { display: flex; flex-direction: column; gap: 6px; margin-top: 8px; }
.effect-forecast { font-size: 11px; color: var(--text-dim); text-align: center; margin-top: 4px; }
.sfx-choice-panel { margin-top: 8px; }
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
  text-shadow: 0 2px 8px var(--accent-32);
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
.resolved-breakdown {
  font-size: 18px; color: var(--text-dim);
  font-family: Georgia, 'Times New Roman', serif;
  font-variant-numeric: lining-nums;
}
.resolved-breakdown .resource-addend {
  color: var(--resource); font-weight: 700;
}

.botch {
  color: var(--danger); font-size: 20px; font-weight: 800;
  text-transform: uppercase; letter-spacing: 4px; margin-top: 6px;
}

.hitches { color: var(--warn); font-size: 13px; }
.hitch-menu-panel { margin-top: 6px; }
.roll-die-wrap.is-hitch { cursor: pointer; }
.roll-die-wrap.is-bought { opacity: 0.35; cursor: not-allowed; }
.roll-die-wrap.is-selected { border-color: var(--warn); background: var(--warn-12); }
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
.roll-die-wrap.selected-total { border-color: var(--accent); background: var(--accent-12); }
.roll-die-wrap.selected-effect { border-color: var(--success); background: var(--success-8); }
.roll-die-wrap.unused { opacity: 0.3; }

.roll-pick {
  display: flex; flex-direction: column; gap: 8px; align-items: center;
}
/* Physical play ([[B17]]): each die carries its own face box. `touch-action:
   none` is what lets a vertical drag scroll the face instead of the panel. */
.manual-entry { display: flex; flex-direction: column; gap: 6px; align-items: center; margin-bottom: 4px; }
.manual-hint { font-size: 11px; color: var(--text-dim); text-align: center; }
.manual-dice { display: flex; flex-wrap: wrap; gap: 8px; justify-content: center; }
.manual-die {
  display: flex; flex-direction: column; align-items: center; gap: 2px;
  cursor: ns-resize; touch-action: none; user-select: none;
  padding: 2px 4px; border-radius: 8px; border: 1px solid transparent;
}
.manual-die.editing { border-color: var(--accent-dim); background: var(--overlay-6); }
/* A die with no face yet shows its size instead of a number; dimming it is what
   says "still to do" now that there is no separate readout under it. */
.manual-die:not(.set) :deep(.die-icon) { opacity: 0.5; }
.manual-face-input {
  width: 46px; text-align: center; font-size: 16px; font-weight: 700; padding: 3px;
  border-radius: 6px; border: 1px solid var(--overlay-12);
  background: var(--bg-input); color: var(--text);
}
.manual-count { font-size: 11px; color: var(--text-dim); }
.manual-btn { color: var(--text-dim); }
.resource-rolls {
  display: flex; align-items: center; justify-content: center; gap: 6px;
  flex-wrap: wrap; padding-top: 6px;
  border-top: 1px dashed var(--overlay-12);
}
.resource-label {
  font-size: 10px; text-transform: uppercase; letter-spacing: 0.5px; color: var(--text-dim);
}
.roll-die-wrap.resource-die { cursor: default; }
.roll-die-wrap.resource-kept { border-color: var(--resource); background: var(--resource-12); }
.roll-die-wrap.resource-other { opacity: 0.35; }

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
  border: 1px solid var(--overlay-12); background: var(--overlay-4);
  touch-action: none; user-select: none; -webkit-user-select: none;
}
.sel-slot:not(.empty) { cursor: grab; border-color: transparent; background: transparent; }
.total-slot { border-color: var(--accent-dim); min-width: 44px; min-height: 40px; }
.effect-slot { border-color: var(--success); min-width: 44px; min-height: 40px; display: flex; align-items: center; justify-content: center; }
.effect-slot.filled { border-color: transparent; background: transparent; }
.sel-slot.empty { border-style: dashed; opacity: 0.5; }
.sel-slot.empty .empty-text { font-size: 10px; color: var(--text-dim); }
.sel-slot.next { border-style: solid; opacity: 0.8; animation: pulse-slot 1.5s ease-in-out infinite; }
.sel-slot.selected { border-style: solid; opacity: 1; border-color: var(--accent); background: var(--accent-20); box-shadow: 0 0 6px var(--accent-32); }
.effect-die-icon { width: 44px; height: 48px; }
.total-die-icon { width: 44px; height: 48px; }
@keyframes pulse-slot { 0%, 100% { border-color: var(--accent); } 50% { border-color: var(--accent-dim); } }
.sel-value { color: var(--text-dim); }
.sel-value strong { color: var(--accent); font-size: 28px; }

.difficulty-presets { display: flex; flex-wrap: wrap; gap: 6px; }
.difficulty-btn { flex: 1; min-width: 56px; padding: 6px 4px; font-size: 11px; font-weight: 700; border-radius: 6px; cursor: pointer; border: 2px solid transparent; background: var(--overlay-6); color: var(--text); display: flex; flex-direction: column; align-items: center; gap: 2px; }
.difficulty-die-icon { width: 32px; height: 36px; }
.difficulty-preset-label { font-size: 10px; line-height: 1; }
.difficulty-btn:hover { background: var(--overlay-12); border-color: var(--accent-dim); }
.opposition-result { font-size: 14px; color: var(--text-dim); margin-top: 4px; }
.opposition-result strong { color: var(--text); }
.outcome-success { color: var(--success); font-weight: 700; }
.outcome-fail { color: var(--danger); font-weight: 700; }

/* ── Roll kind styling (P2.11) ─────────────────────── */
.kind-simple-test { --kind-accent: var(--text); }
.kind-cortex-test { --kind-accent: var(--accent); }
.kind-challenger-contest { --kind-accent: var(--warn); }
.kind-defendant-contest { --kind-accent: var(--danger); }
.kind-roll-table { --kind-accent: var(--success); }
.kind-difficulty { --kind-accent: var(--purple); }

.roll-kind-badge {
  font-size: 10px; font-weight: 700;
  text-transform: uppercase; letter-spacing: 1.5px;
  padding: 3px 10px; border-radius: 999px;
  color: var(--kind-accent);
  border: 1px solid var(--kind-accent);
  background: var(--overlay-4);
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
  background: var(--overlay-6);
  color: var(--text);
  border: 1px solid var(--overlay-15);
  max-width: 180px;
}

.give-in-btn {
  color: var(--danger);
  border: 1px solid var(--danger);
  background: var(--danger-8);
}
/* Cancel is the quiet exit next to give-in's loud one: an undone mis-start, not
   a loss ([[B118]]). */
.cancel-btn {
  color: var(--text-dim);
  border: 1px solid var(--overlay-12);
  background: transparent;
}
.cancel-btn:hover { color: var(--text); background: var(--overlay-6); }
.give-in-btn:hover {
  background: var(--danger-20);
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
