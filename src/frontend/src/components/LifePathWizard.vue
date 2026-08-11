<template>
  <div v-if="visible" class="wizard-backdrop" @click.self="$emit('close')">
    <div class="wizard-panel">
      <div class="wizard-header">
        <h2>Life Path</h2>
        <button class="wiz-close" @click="$emit('close')">✕</button>
      </div>

      <!-- Step 0: Choose Path -->
      <div v-if="step === 'choose'" class="wiz-body">
        <p class="wiz-hint">Choose a life path to take a term in.</p>
        <div v-if="loadingPaths" class="wiz-loading">Loading…</div>
        <div v-else-if="!paths.length" class="wiz-empty">No life paths available in this universe.</div>
        <div v-else class="wiz-path-list">
          <button v-for="lp in paths" :key="lp.id" class="wiz-path-btn" @click="selectPath(lp)">
            <span class="wiz-path-name">{{ lp.name }}</span>
            <span class="wiz-path-type">{{ lp.type }}</span>
            <span class="wiz-path-desc">{{ truncate(lp.description, 60) }}</span>
          </button>
        </div>
      </div>

      <!-- Step 1: Qualification -->
      <div v-else-if="step === 'qual'" class="wiz-body">
        <p class="wiz-phase-label">Qualification</p>
        <div v-if="result.qualification" class="wiz-result">
          <div v-if="result.qualification.locationBlocked" class="wiz-bad">
            ❌ You must be at the required location to take this path.
          </div>
          <div v-else-if="result.qualification.success" class="wiz-good">✅ Qualified</div>
          <div v-else class="wiz-bad">
            ❌ Failed qualification
            <span v-if="result.qualification.drafted">— drafted to {{ result.qualification.draftedPathId }}</span>
          </div>
        </div>
        <button v-if="result.qualification?.success || result.qualification?.drafted" class="wiz-next" @click="advanceStep">Continue →</button>
        <button v-if="result.qualification?.locationBlocked" class="wiz-next" @click="step = 'choose'">← Back</button>
      </div>

      <!-- Step 2: Learn -->
      <div v-else-if="step === 'learn'" class="wiz-body">
        <p class="wiz-phase-label">Learn</p>
        <div v-if="result.learn" class="wiz-result">
          <div class="wiz-good">
            {{ result.learn.wasSteppedUp ? '📈 Stepped up' : '📖 Learned' }}
            <strong>{{ displayName(result.learn.traitName) }}</strong>
          </div>
        </div>
        <div v-else class="wiz-result wiz-dim">No new skills gained this term.</div>
        <button class="wiz-next" @click="advanceStep">Continue →</button>
      </div>

      <!-- Step 3: Survive -->
      <div v-else-if="step === 'survive'" class="wiz-body">
        <p class="wiz-phase-label">Survive</p>
        <div v-if="result.survive" class="wiz-result">
          <div v-if="result.survive.success" class="wiz-good">✅ {{ result.survive.rollSummary }}</div>
          <div v-else class="wiz-bad">⚠️ {{ result.survive.rollSummary }}</div>
          <div v-if="result.survive.mishapDescription" class="wiz-mishap">
            💀 Mishap: {{ result.survive.mishapDescription }}
          </div>
        </div>
        <div v-else class="wiz-result wiz-dim">Safe path — no survival risk.</div>
        <button class="wiz-next" @click="advanceStep">Continue →</button>
      </div>

      <!-- Step 4: Event -->
      <div v-else-if="step === 'event'" class="wiz-body">
        <p class="wiz-phase-label">Event</p>
        <div v-if="result.event" class="wiz-result wiz-good">
          📋 {{ result.event.description }}
        </div>
        <div v-else class="wiz-result wiz-dim">Nothing unusual happened.</div>
        <button class="wiz-next" @click="advanceStep">Continue →</button>
      </div>

      <!-- Step 5: Advance -->
      <div v-else-if="step === 'advance'" class="wiz-body">
        <p class="wiz-phase-label">Advance</p>
        <div v-if="result.advance" class="wiz-result">
          <div v-if="result.advance.success" class="wiz-good">
            🏆 Advanced to rank {{ result.advance.newRank }} — {{ result.advance.rankName }}
          </div>
          <div v-else class="wiz-dim">No advancement this term.</div>
        </div>
        <div v-else class="wiz-result wiz-dim">No advancement ladder.</div>
        <button class="wiz-next" @click="step = 'done'">Continue →</button>
      </div>

      <!-- Step 6: Done -->
      <div v-else-if="step === 'done'" class="wiz-body">
        <p class="wiz-phase-label">Term Complete</p>
        <p class="wiz-summary">Term #{{ result.termNumber }} in {{ selectedPath?.name }}</p>
        <div class="wiz-done-actions">
          <button class="wiz-next" @click="takeAnother">🔄 Take Another Term</button>
          <button class="wiz-muster-btn" @click="doMusterOut">🏁 Muster Out</button>
          <button class="wiz-done-btn" @click="$emit('close')">Done</button>
        </div>
      </div>

      <!-- Step: Muster Out Result -->
      <div v-else-if="step === 'mustered'" class="wiz-body">
        <p class="wiz-phase-label">Mustered Out</p>
        <div v-if="musterResult" class="wiz-result wiz-good">
          <p>🎉 {{ musterResult.pathName }} — {{ musterResult.benefits.join(', ') || 'No benefits' }}</p>
          <p>💰 +{{ musterResult.razmeritGained }} razmerit</p>
        </div>
        <button class="wiz-done-btn" @click="$emit('close')">Done</button>
      </div>

      <!-- Loading overlay -->
      <div v-if="executing" class="wiz-loading-overlay">⏳ Rolling…</div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useApi } from '../composables/useApi.js'

const props = defineProps({
  visible: { type: Boolean, default: false },
  entityId: { type: String, required: true },
  universe: { type: String, default: 'earth' },
})

const emit = defineEmits(['close', 'updated'])

const { graphql } = useApi()

const step = ref('choose')
const loadingPaths = ref(false)
const executing = ref(false)
const paths = ref([])
const selectedPath = ref(null)
const result = ref({})
const musterResult = ref(null)

const phases = ['qual', 'learn', 'survive', 'event', 'advance']

function truncate(s, n) { return s && s.length > n ? s.slice(0, n) + '…' : s || '' }
function displayName(name) { return (name || '').split('_').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ') }

async function loadPaths() {
  loadingPaths.value = true
  const query = `
    query($u: String) {
      lifePaths(universe: $u) { id name universe description type }
    }
  `
  const data = await graphql(query, { u: props.universe })
  paths.value = data?.lifePaths || []
  loadingPaths.value = false
}

async function selectPath(lp) {
  selectedPath.value = lp
  step.value = 'qual'
  executing.value = true
  const query = `
    mutation($eid: ID!, $lpid: ID!) {
      takeTerm(entityId: $eid, lifePathId: $lpid) {
        qualification { success drafted draftedPathId locationBlocked }
        learn { traitGainedId traitName wasSteppedUp }
        survive { success rollSummary mishapDescription }
        event { eventIndex description }
        advance { success newRank rankName }
        termNumber razmeritChange
      }
    }
  `
  const data = await graphql(query, { eid: props.entityId, lpid: lp.id })
  result.value = data?.takeTerm || {}
  executing.value = false
}

function advanceStep() {
  const idx = phases.indexOf(step.value)
  if (idx >= 0 && idx < phases.length - 1) {
    step.value = phases[idx + 1]
  } else {
    step.value = 'done'
  }
}

function takeAnother() {
  step.value = 'choose'
  result.value = {}
  selectedPath.value = null
  loadPaths()
}

async function doMusterOut() {
  executing.value = true
  const query = `
    mutation($eid: ID!) {
      musterOut(entityId: $eid) {
        pathId pathName termsServed finalRank benefits razmeritGained
      }
    }
  `
  const data = await graphql(query, { eid: props.entityId })
  musterResult.value = data?.musterOut || null
  step.value = 'mustered'
  executing.value = false
  emit('updated')
}

// Load paths when opened
import { watch } from 'vue'
watch(() => props.visible, (v) => {
  if (v) {
    step.value = 'choose'
    result.value = {}
    musterResult.value = null
    selectedPath.value = null
    loadPaths()
  }
})
</script>

<style scoped>
.wizard-backdrop { position: fixed; inset: 0; z-index: 100; background: rgba(0,0,0,0.6); display: flex; align-items: center; justify-content: center; }
.wizard-panel { background: var(--bg-panel); backdrop-filter: blur(16px); border-radius: var(--radius); border: 1px solid var(--border); width: 420px; max-width: 95vw; max-height: 85vh; display: flex; flex-direction: column; overflow: hidden; position: relative; }
.wizard-header { display: flex; align-items: center; justify-content: space-between; padding: 12px 16px; border-bottom: 1px solid var(--border); }
.wizard-header h2 { font-size: 16px; margin: 0; }
.wiz-close { background: none; border: none; color: var(--text-dim); font-size: 16px; cursor: pointer; }
.wiz-body { padding: 16px; flex: 1; overflow-y: auto; }
.wiz-hint { color: var(--text-dim); margin: 0 0 12px; font-size: 13px; }
.wiz-loading, .wiz-empty { color: var(--text-dim); font-size: 13px; padding: 20px 0; text-align: center; }
.wiz-path-list { display: flex; flex-direction: column; gap: 6px; }
.wiz-path-btn { display: flex; flex-direction: column; align-items: flex-start; background: var(--bg-input); border: 1px solid var(--border); border-radius: 6px; padding: 10px 12px; cursor: pointer; text-align: left; width: 100%; }
.wiz-path-btn:hover { border-color: var(--accent); }
.wiz-path-name { font-weight: 600; font-size: 14px; }
.wiz-path-type { font-size: 11px; color: var(--accent); text-transform: uppercase; }
.wiz-path-desc { font-size: 12px; color: var(--text-dim); margin-top: 2px; }
.wiz-phase-label { font-weight: 700; text-transform: uppercase; letter-spacing: 1px; font-size: 12px; color: var(--accent); margin-bottom: 8px; }
.wiz-result { padding: 10px 12px; border-radius: 6px; margin-bottom: 8px; font-size: 13px; }
.wiz-good { background: rgba(0,200,100,0.1); color: #4c4; }
.wiz-bad { background: rgba(200,50,50,0.1); color: #c55; }
.wiz-dim { background: var(--bg-input); color: var(--text-dim); }
.wiz-mishap { margin-top: 6px; font-size: 12px; color: #c55; }
.wiz-summary { font-size: 14px; margin: 8px 0 16px; }
.wiz-next, .wiz-done-btn, .wiz-muster-btn { display: block; width: 100%; padding: 8px 12px; margin-top: 8px; border: 1px solid var(--border); border-radius: 6px; background: var(--bg-input); color: var(--text); cursor: pointer; font-size: 13px; text-align: center; }
.wiz-next:hover, .wiz-done-btn:hover { border-color: var(--accent); }
.wiz-muster-btn { background: rgba(200,150,0,0.1); border-color: #c90; color: #da0; }
.wiz-muster-btn:hover { background: rgba(200,150,0,0.2); }
.wiz-done-actions { display: flex; flex-direction: column; gap: 4px; }
.wiz-loading-overlay { position: absolute; inset: 0; background: rgba(0,0,0,0.5); display: flex; align-items: center; justify-content: center; font-size: 20px; z-index: 10; }
</style>
