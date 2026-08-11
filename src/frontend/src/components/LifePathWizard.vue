<template>
  <div v-if="visible" class="wizard-backdrop" @click.self="$emit('close')">
    <div class="wizard-panel">
      <div class="wizard-header">
        <h2>{{ selectedPath ? selectedPath.name : 'Life Path' }}</h2>
        <button class="wiz-close" @click="$emit('close')">✕</button>
      </div>

      <!-- Step 0: Choose Path -->
      <div v-if="step === 'choose'" class="wiz-body">
        <p class="wiz-hint">Choose a life path to take a term in.</p>
        <div v-if="loadingPaths" class="wiz-loading">Loading…</div>
        <div v-else-if="!paths.length" class="wiz-empty">No life paths available in this universe.</div>
        <div v-else class="wiz-path-list">
          <button v-for="lp in paths" :key="lp.id" class="wiz-path-btn" @click="startPath(lp)">
            <span class="wiz-path-name">{{ lp.name }}</span>
            <span class="wiz-path-type">{{ lp.type }}</span>
            <span class="wiz-path-desc">{{ truncate(lp.description, 60) }}</span>
          </button>
        </div>
      </div>

      <!-- Phase steps: qual → learn → survive → event → advance -->
      <div v-else-if="phaseIdx >= 0 && phaseIdx < phases.length" class="wiz-body">
        <p class="wiz-phase-label">{{ phaseLabel }}</p>
        <p class="wiz-phase-hint">{{ phaseHint }}</p>

        <!-- Outcome table (clickable rows) -->
        <div v-if="showTable" class="wiz-table">
          <button v-for="row in outcomeRows" :key="row.label"
            class="wiz-table-row" :class="{ selected: row.selected }"
            @click="selectRow(row)">
            <span class="wiz-row-range">{{ row.label }}</span>
            <span class="wiz-row-desc">{{ row.desc }}</span>
            <span v-if="row.selected" class="wiz-row-check">✓</span>
          </button>
        </div>

        <!-- Curriculum / event list (for learn/event phases) -->
        <div v-else-if="showList" class="wiz-list">
          <div v-for="item in listItems" :key="item.label" class="wiz-list-item">
            <span>{{ item.label }}</span>
            <span class="wiz-list-desc">{{ item.desc }}</span>
          </div>
        </div>

        <div class="wiz-phase-actions">
          <button v-if="showRoll" class="wiz-next" @click="executeTerm">🎲 Roll</button>
          <button v-if="manualValue !== null || !showTable" class="wiz-next" @click="nextPhase">Continue →</button>
          <button class="wiz-back" @click="prevPhase">← Back</button>
        </div>
      </div>

      <!-- Results summary -->
      <div v-else-if="step === 'results'" class="wiz-body">
        <p class="wiz-phase-label">Term Complete — #{{ result.termNumber }}</p>
        <div v-if="result.qualification" class="wiz-result" :class="result.qualification.success ? 'wiz-good' : 'wiz-bad'">
          Qualification: {{ result.qualification.success ? '✅' : '❌' }}
          <span v-if="result.qualification.drafted">(drafted)</span>
        </div>
        <div v-if="result.learn" class="wiz-result wiz-good">
          {{ result.learn.wasSteppedUp ? '📈' : '📖' }} {{ displayName(result.learn.traitName) }}
        </div>
        <div v-if="result.survive" class="wiz-result" :class="result.survive.success ? 'wiz-good' : 'wiz-bad'">
          {{ result.survive.rollSummary }}
          <span v-if="result.survive.mishapDescription">💀 {{ result.survive.mishapDescription }}</span>
        </div>
        <div v-if="result.event" class="wiz-result wiz-good">📋 {{ result.event.description }}</div>
        <div v-if="result.advance" class="wiz-result" :class="result.advance.success ? 'wiz-good' : 'wiz-dim'">
          {{ result.advance.success ? '🏆 ' + result.advance.rankName : 'No advancement' }}
        </div>
        <div class="wiz-done-actions">
          <button class="wiz-next" @click="resetWizard">🔄 Another Term</button>
          <button class="wiz-muster-btn" @click="doMusterOut">🏁 Muster Out</button>
          <button class="wiz-done-btn" @click="$emit('close')">Done</button>
        </div>
      </div>

      <!-- Muster Out Result -->
      <div v-else-if="step === 'mustered'" class="wiz-body">
        <p class="wiz-phase-label">Mustered Out</p>
        <div v-if="musterResult" class="wiz-result wiz-good">
          <p>🎉 {{ musterResult.pathName }}</p>
          <p v-if="musterResult.benefits.length">{{ musterResult.benefits.join(', ') }}</p>
          <p>💰 +{{ musterResult.razmeritGained }} razmerit</p>
        </div>
        <button class="wiz-done-btn" @click="$emit('close')">Done</button>
      </div>

      <div v-if="executing" class="wiz-loading-overlay">⏳</div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { useApi } from '../composables/useApi.js'

const props = defineProps({
  visible: { type: Boolean, default: false },
  entityId: { type: String, required: true },
  universe: { type: String, default: 'earth' },
})
const emit = defineEmits(['close', 'updated'])
const { graphql } = useApi()

// State
const step = ref('choose')
const loadingPaths = ref(false)
const executing = ref(false)
const paths = ref([])
const selectedPath = ref(null)
const result = ref({})
const musterResult = ref(null)
const phaseIdx = ref(0)
const manualValues = ref({})  // phase → manual result
const manualValue = ref(null)

const phases = ['qual', 'learn', 'survive', 'event', 'advance']
const phaseLabels = { qual: 'Qualification', learn: 'Learn', survive: 'Survive', event: 'Event', advance: 'Advance' }

function truncate(s, n) { return s && s.length > n ? s.slice(0, n) + '…' : s || '' }
function displayName(name) { return (name || '').split('_').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ') }

// ── Outcome tables ────────────────────────────────

const qualDifficulty = computed(() => selectedPath.value?.qualification?.difficulty || 'D4')
const surviveDifficulty = computed(() => selectedPath.value?.survival?.difficulty || 'D6')
const advanceDifficulty = computed(() => selectedPath.value?.advancement?.difficulty || 'D6')

const showTable = computed(() => ['qual', 'survive', 'advance'].includes(phases[phaseIdx.value]))
const showList = computed(() => phases[phaseIdx.value] === 'learn' || phases[phaseIdx.value] === 'event')
const showRoll = computed(() => showTable.value && manualValue.value === null)

const phaseLabel = computed(() => phaseLabels[phases[phaseIdx.value]] || '')
const phaseHint = computed(() => {
  const p = phases[phaseIdx.value]
  if (p === 'qual') return `Roll to qualify. Target: ${qualDifficulty.value}`
  if (p === 'survive') return `Roll to survive. Target: ${surviveDifficulty.value}`
  if (p === 'advance') return `Roll for promotion. Target: ${advanceDifficulty.value}`
  if (p === 'learn') return 'Gain a skill this term.'
  if (p === 'event') return 'Something happens…'
  return ''
})

const outcomeRows = computed(() => {
  const p = phases[phaseIdx.value]
  if (p === 'qual') return buildOutcomeRows('qual')
  if (p === 'survive') return buildOutcomeRows('survive')
  if (p === 'advance') return buildOutcomeRows('advance')
  return []
})

function buildOutcomeRows(phase) {
  const selected = manualValues.value[phase]
  const base = [
    { label: '1–2', value: 1, tier: 'fail', desc: '❌ Fail', selected: selected === 1 },
    { label: '3–5', value: 3, tier: 'marginal', desc: '✅ Marginal — just enough', selected: selected === 3 },
    { label: '6–8', value: 6, tier: 'success', desc: '🎉 Success', selected: selected === 6 },
    { label: '9–10', value: 9, tier: 'exceptional', desc: '🌟 Exceptional', selected: selected === 9 },
    { label: '11–12', value: 11, tier: 'perfect', desc: '💎 Perfect', selected: selected === 11 },
  ]
  if (phase === 'survive') {
    // Override descriptions for survival
    base[0].desc = '❌ Mishap — suffer consequences'
    base[1].desc = '⚠️ Barely survived'
  }
  if (phase === 'advance') {
    base[0].desc = '❌ No promotion'
    base[1].desc = '❌ No promotion'
  }
  return base
}

const listItems = computed(() => {
  if (phases[phaseIdx.value] === 'learn' && selectedPath.value?.curriculum) {
    return selectedPath.value.curriculum.map(c => ({
      label: displayName(c.traitId),
      desc: c.stepUp ? '(step up)' : `(new at ${c.createAt})`,
    }))
  }
  if (phases[phaseIdx.value] === 'event' && selectedPath.value?.events) {
    return selectedPath.value.events.map(e => ({
      label: e.description,
      desc: e.minRank ? `(rank ${e.minRank}+)` : '',
    }))
  }
  return []
})

function selectRow(row) {
  const p = phases[phaseIdx.value]
  manualValues.value[p] = row.value
  manualValue.value = row.value
}

// ── Navigation ────────────────────────────────────

function nextPhase() {
  manualValue.value = null
  if (phaseIdx.value < phases.length - 1) {
    phaseIdx.value++
  } else {
    step.value = 'results'
  }
}
function prevPhase() {
  if (phaseIdx.value > 0) {
    phaseIdx.value--
    manualValue.value = manualValues.value[phases[phaseIdx.value]] || null
  } else {
    resetWizard()
  }
}

function startPath(lp) {
  selectedPath.value = lp
  phaseIdx.value = 0
  manualValues.value = {}
  manualValue.value = null
  result.value = {}
  step.value = 'configure'
}

// ── Execute ───────────────────────────────────────

async function executeTerm() {
  // Collect manual values
  const qm = manualValues.value['qual'] ?? null
  const sm = manualValues.value['survive'] ?? null
  const am = manualValues.value['advance'] ?? null

  executing.value = true
  const query = `
    mutation($eid: ID!, $lpid: ID!, $qm: Int, $sm: Int, $am: Int) {
      takeTerm(entityId: $eid, lifePathId: $lpid, qualManual: $qm, surviveManual: $sm, advanceManual: $am) {
        qualification { success drafted draftedPathId locationBlocked }
        learn { traitGainedId traitName wasSteppedUp }
        survive { success rollSummary mishapDescription }
        event { eventIndex description }
        advance { success newRank rankName }
        termNumber razmeritChange
      }
    }
  `
  const data = await graphql(query, {
    eid: props.entityId, lpid: selectedPath.value.id,
    qm, sm, am,
  })
  result.value = data?.takeTerm || {}
  executing.value = false
  step.value = 'results'
  emit('updated')
}

async function doMusterOut() {
  executing.value = true
  const query = `mutation($eid: ID!) { musterOut(entityId: $eid) { pathId pathName termsServed finalRank benefits razmeritGained } }`
  const data = await graphql(query, { eid: props.entityId })
  musterResult.value = data?.musterOut || null
  step.value = 'mustered'
  executing.value = false
  emit('updated')
}

function resetWizard() {
  step.value = 'choose'
  phaseIdx.value = 0
  manualValues.value = {}
  manualValue.value = null
  result.value = {}
  selectedPath.value = null
  loadPaths()
}

async function loadPaths() {
  loadingPaths.value = true
  const query = `query($u: String) { lifePaths(universe: $u) { id name universe description type qualification { difficulty } } }`
  const data = await graphql(query, { u: props.universe })
  paths.value = data?.lifePaths || []
  loadingPaths.value = false
}

watch(() => props.visible, (v) => { if (v) resetWizard() }, { immediate: true })
</script>

<style scoped>
.wizard-backdrop { position: fixed; inset: 0; z-index: 100; background: rgba(0,0,0,0.6); display: flex; align-items: safe center; justify-content: center; padding: 20px; }
.wizard-panel { background: var(--bg-panel); backdrop-filter: blur(16px); border-radius: var(--radius); border: 1px solid var(--border); width: 420px; max-width: 95vw; max-height: calc(100vh - 40px); display: flex; flex-direction: column; overflow: hidden; position: relative; }
.wizard-header { display: flex; align-items: center; justify-content: space-between; padding: 12px 16px; border-bottom: 1px solid var(--border); }
.wizard-header h2 { font-size: 16px; margin: 0; }
.wiz-close { background: none; border: none; color: var(--text-dim); font-size: 16px; cursor: pointer; }
.wiz-body { padding: 16px; flex: 1; min-height: 0; overflow-y: auto; }
.wiz-hint { color: var(--text-dim); margin: 0 0 12px; font-size: 13px; }
.wiz-loading, .wiz-empty { color: var(--text-dim); font-size: 13px; padding: 20px 0; text-align: center; }
.wiz-path-list { display: flex; flex-direction: column; gap: 6px; }
.wiz-path-btn { display: flex; flex-direction: column; align-items: flex-start; background: var(--bg-input); border: 1px solid var(--border); border-radius: 6px; padding: 10px 12px; cursor: pointer; text-align: left; width: 100%; }
.wiz-path-btn:hover { border-color: var(--accent); }
.wiz-path-name { font-weight: 600; font-size: 14px; }
.wiz-path-type { font-size: 11px; color: var(--accent); text-transform: uppercase; }
.wiz-path-desc { font-size: 12px; color: var(--text-dim); margin-top: 2px; }

.wiz-phase-label { font-weight: 700; text-transform: uppercase; letter-spacing: 1px; font-size: 12px; color: var(--accent); margin-bottom: 4px; }
.wiz-phase-hint { font-size: 13px; color: var(--text-dim); margin-bottom: 12px; }

.wiz-table { display: flex; flex-direction: column; gap: 4px; margin-bottom: 12px; }
.wiz-table-row { display: flex; align-items: center; gap: 8px; background: var(--bg-input); border: 1px solid var(--border); border-radius: 6px; padding: 8px 10px; cursor: pointer; width: 100%; text-align: left; font-size: 13px; }
.wiz-table-row:hover { border-color: var(--accent); }
.wiz-table-row.selected { border-color: #4c4; background: rgba(0,200,100,0.1); }
.wiz-row-range { font-weight: 600; min-width: 36px; color: var(--accent); }
.wiz-row-desc { flex: 1; }
.wiz-row-check { color: #4c4; font-weight: 700; }

.wiz-list { display: flex; flex-direction: column; gap: 4px; margin-bottom: 12px; }
.wiz-list-item { display: flex; justify-content: space-between; background: var(--bg-input); border: 1px solid var(--border); border-radius: 6px; padding: 8px 10px; font-size: 13px; }
.wiz-list-desc { color: var(--text-dim); font-size: 12px; }

.wiz-phase-actions { display: flex; gap: 6px; }
.wiz-next, .wiz-back, .wiz-done-btn, .wiz-muster-btn { flex: 1; padding: 8px 12px; border: 1px solid var(--border); border-radius: 6px; background: var(--bg-input); color: var(--text); cursor: pointer; font-size: 13px; text-align: center; }
.wiz-next:hover, .wiz-done-btn:hover { border-color: var(--accent); }
.wiz-back { flex: 0; }
.wiz-muster-btn { background: rgba(200,150,0,0.1); border-color: #c90; color: #da0; }

.wiz-result { padding: 10px 12px; border-radius: 6px; margin-bottom: 8px; font-size: 13px; }
.wiz-good { background: rgba(0,200,100,0.1); color: #4c4; }
.wiz-bad { background: rgba(200,50,50,0.1); color: #c55; }
.wiz-dim { background: var(--bg-input); color: var(--text-dim); }

.wiz-done-actions { display: flex; flex-direction: column; gap: 4px; margin-top: 12px; }
.wiz-loading-overlay { position: absolute; inset: 0; background: rgba(0,0,0,0.5); display: flex; align-items: center; justify-content: center; font-size: 20px; z-index: 10; }
</style>
