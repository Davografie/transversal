<template>
  <!-- Modal overlay (non-embedded) -->
  <div v-if="visible && !embedded" class="wizard-backdrop" @click.self="$emit('close')">
    <div class="wizard-panel">
      <div class="wizard-header">
        <h2>{{ selectedPath ? selectedPath.name : 'Life Path' }}</h2>
        <button class="wiz-close" @click="closeAndClear">✕</button>
      </div>
      <div class="wiz-body">
        <template v-if="step === 'choose'">
          <p class="wiz-hint">Choose a life path to take a term in.</p>
          <div v-if="loadingPaths" class="wiz-loading">Loading…</div>
          <div v-else-if="!paths.length" class="wiz-empty">No life paths available.</div>
          <div v-else class="wiz-path-list">
            <button v-for="lp in paths" :key="lp.id" class="wiz-path-btn" @click="startPath(lp)">
              <span class="wiz-path-name">{{ lp.name }}</span>
              
              <span class="wiz-path-desc">{{ truncate(lp.description, 60) }}</span>
            </button>
          </div>
        </template>
        <template v-else-if="step === 'configure'">
          <p class="wiz-phase-label">{{ phaseLabel }}</p>
          <p v-if="!showTable" class="wiz-phase-hint">{{ phaseHint }}</p>
          <table v-if="showTable" class="wiz-table">
            <thead><tr><th>Roll</th><th>Result</th></tr></thead>
            <tbody>
              <tr v-for="row in outcomeRows" :key="row.roll" :class="{ 'wiz-row-sel': row.selected }" @click="selectRow(row)">
                <td class="wiz-td-roll">{{ row.roll }}</td><td>{{ row.name }}</td>
              </tr>
            </tbody>
          </table>
          <table v-else-if="showList && phases[phaseIdx] === 'mishap'" class="wiz-table">
            <thead><tr><th>#</th><th>Mishap</th></tr></thead>
            <tbody><tr v-for="(item, idx) in mishapItems" :key="item.label" :class="{ 'wiz-row-sel': selectedMishap === idx }" @click="selectedMishap = idx"><td class="wiz-td-roll">{{ item.label }}</td><td>{{ item.name }}<span v-if="item.mustMuster" class="wiz-mo-badge">🏁 musters out</span></td></tr></tbody>
          </table>
          <table v-else-if="showList && phases[phaseIdx] === 'event'" class="wiz-table">
            <thead><tr><th>#</th><th>Event</th></tr></thead>
            <tbody><tr v-for="(item, idx) in listItems" :key="item.label" :class="{ 'wiz-row-sel': selectedEvent === idx }" @click="selectedEvent = idx"><td class="wiz-td-roll">{{ item.label }}</td><td>{{ item.name }}</td></tr></tbody>
          </table>
          <table v-else-if="showList" class="wiz-table">
            <thead><tr><th>Trait</th><th>Effect</th></tr></thead>
            <tbody><tr v-for="(item, idx) in listItems" :key="item.label" :class="{ 'wiz-row-sel': selectedLearn === idx }" @click="selectedLearn = idx"><td>{{ item.label }}</td><td class="wiz-td-desc">{{ item.desc }}</td></tr></tbody>
          </table>
          <div class="wiz-phase-actions">
            <button v-if="showRoll" class="wiz-next wiz-roll-btn" @click="quickRoll">
              <DieIcon v-if="phaseDie" :die="phaseDie" /> <span>Roll {{ rollTraitName }}</span>
            </button>
            <button v-if="phases[phaseIdx] === 'mishap'" class="wiz-next" @click="quickRollMishap">🎲 Roll Mishap</button>
            <button v-if="manualValue !== null || !showTable" class="wiz-next" @click="nextPhase">Continue →</button>
            <button class="wiz-back" @click="prevPhase">← Back</button>
          </div>
        </template>
        <template v-else-if="step === 'results'">
          <!-- Drafted: qual failed but draft path available -->
          <template v-if="result.qualification?.drafted">
            <p class="wiz-phase-label">Qualification Failed</p>
            <div class="wiz-result wiz-bad">
              <p>❌ You did not qualify for {{ selectedPath?.name }}.</p>
              <p v-if="draftPath" class="wiz-dim">Drafted into <strong>{{ draftPath.name }}</strong> ()</p>
            </div>
            <div class="wiz-done-actions">
              <button v-if="draftPath" class="wiz-next" @click="takeDraftTerm">📋 Take Term in {{ draftPath.name }}</button>
              <button class="wiz-done-btn" @click="closeAndClear">Done</button>
            </div>
          </template>
          <!-- Normal term results -->
          <template v-else>
            <p class="wiz-phase-label">Term Complete — #{{ result.termNumber }}</p>
            <table class="wiz-table">
              <tbody>
                <tr v-if="result.qualification"><td>Qualification</td><td :class="result.qualification.success ? 'wiz-good' : 'wiz-bad'">{{ result.qualification.success ? '✅' : '❌' }}{{ result.qualification.drafted ? ' (drafted)' : '' }}</td></tr>
                <tr v-if="result.learn"><td>Learn</td><td class="wiz-good">{{ result.learn.wasSteppedUp ? '📈' : '📖' }} {{ fmtName(result.learn.traitName) }}</td></tr>
                <tr v-if="result.survive"><td>Survive</td><td :class="result.survive.success ? 'wiz-good' : 'wiz-bad'">{{ result.survive.rollSummary }}<span v-if="result.survive.mishapDescription"> 💀 {{ result.survive.mishapDescription }}</span><span v-if="result.survive.forcedMuster" class="wiz-mo-badge">🏁 mustered out</span></td></tr>
                <tr v-if="result.event"><td>Event</td><td class="wiz-good">📋 {{ result.event.description }}</td></tr>
                <tr v-if="result.advance"><td>Advance</td><td :class="result.advance.success ? 'wiz-good' : 'wiz-dim'">{{ result.advance.success ? '🏆 ' + result.advance.rankName : 'No advancement' }}</td></tr>
                <tr v-if="!result.event && !result.advance"><td colspan="2" class="wiz-dim" style="text-align:center">Event & Advance skipped</td></tr>
              </tbody>
            </table>
            <div class="wiz-done-actions">
              <button class="wiz-next" @click="resetWizard">🔄 Another Term</button>
              <button class="wiz-muster-btn" @click="doMusterOut">🏁 Muster Out</button>
              <button class="wiz-done-btn" @click="closeAndClear">Done</button>
            </div>
          </template>
        </template>
        <template v-else-if="step === 'mustered'">
          <p class="wiz-phase-label">Mustered Out</p>
          <div v-if="musterResult" class="wiz-result wiz-good">
            <p>🎉 {{ musterResult.pathName }}</p>
            <p v-if="musterResult.benefits?.length">{{ musterResult.benefits.join(', ') }}</p>
            <p>💰 +{{ musterResult.razmeritGained }} razmerit</p>
          </div>
          <button class="wiz-done-btn" @click="closeAndClear">Done</button>
        </template>
      </div>
      <div v-if="executing" class="wiz-loading-overlay">⏳</div>
    </div>
  </div>

  <!-- Embedded inside character sheet -->
  <div v-else-if="visible && embedded" class="wiz-embedded">
    <template v-if="step === 'choose'">
      <p class="wiz-hint">Choose a life path to take a term in.</p>
      <div v-if="loadingPaths" class="wiz-loading">Loading…</div>
      <div v-else-if="!paths.length" class="wiz-empty">No life paths available.</div>
      <div v-else class="wiz-path-list">
        <button v-for="lp in paths" :key="lp.id" class="wiz-path-btn" @click="startPath(lp)">
          <span class="wiz-path-name">{{ lp.name }}</span>
          
          <span class="wiz-path-desc">{{ truncate(lp.description, 60) }}</span>
        </button>
      </div>
    </template>
    <template v-else-if="step === 'configure'">
      <div class="wiz-path-banner" v-if="selectedPath">{{ selectedPath.name }} — </div>
      <p class="wiz-phase-label">{{ phaseLabel }}</p>
      <p v-if="!showTable" class="wiz-phase-hint">{{ phaseHint }}</p>
      <table v-if="showTable" class="wiz-table">
        <thead><tr><th>Roll</th><th>Result</th></tr></thead>
        <tbody>
          <tr v-for="row in outcomeRows" :key="row.roll" :class="{ 'wiz-row-sel': row.selected }" @click="selectRow(row)">
            <td class="wiz-td-roll">{{ row.roll }}</td><td>{{ row.name }}</td>
          </tr>
        </tbody>
      </table>
      <table v-else-if="showList && phases[phaseIdx] === 'mishap'" class="wiz-table">
        <thead><tr><th>#</th><th>Mishap</th></tr></thead>
        <tbody><tr v-for="(item, idx) in mishapItems" :key="item.label" :class="{ 'wiz-row-sel': selectedMishap === idx }" @click="selectedMishap = idx"><td class="wiz-td-roll">{{ item.label }}</td><td>{{ item.name }}<span v-if="item.mustMuster" class="wiz-mo-badge">🏁 musters out</span></td></tr></tbody>
      </table>
      <table v-else-if="showList && phases[phaseIdx] === 'event'" class="wiz-table">
        <thead><tr><th>#</th><th>Event</th></tr></thead>
        <tbody><tr v-for="(item, idx) in listItems" :key="item.label" :class="{ 'wiz-row-sel': selectedEvent === idx }" @click="selectedEvent = idx"><td class="wiz-td-roll">{{ item.label }}</td><td>{{ item.name }}</td></tr></tbody>
      </table>
      <table v-else-if="showList" class="wiz-table">
        <thead><tr><th>Trait</th><th>Effect</th></tr></thead>
        <tbody><tr v-for="(item, idx) in listItems" :key="item.label" :class="{ 'wiz-row-sel': selectedLearn === idx }" @click="selectedLearn = idx"><td>{{ item.label }}</td><td class="wiz-td-desc">{{ item.desc }}</td></tr></tbody>
      </table>
      <div class="wiz-phase-actions">
        <button v-if="showRoll" class="wiz-next wiz-roll-btn" @click="quickRoll">
          <DieIcon v-if="phaseDie" :die="phaseDie" /> <span>Roll {{ rollTraitName }}</span>
        </button>
        <button v-if="phases[phaseIdx] === 'mishap'" class="wiz-next" @click="quickRollMishap">🎲 Roll Mishap</button>
        <button v-if="manualValue !== null || !showTable" class="wiz-next" @click="nextPhase">Continue →</button>
        <button class="wiz-back" @click="prevPhase">← Back</button>
      </div>
    </template>
    <template v-else-if="step === 'results'">
      <!-- Drafted: qual failed but draft path available -->
      <template v-if="result.qualification?.drafted">
        <p class="wiz-phase-label">Qualification Failed</p>
        <div class="wiz-result wiz-bad">
          <p>❌ You did not qualify for {{ selectedPath?.name }}.</p>
          <p v-if="draftPath" class="wiz-dim">Drafted into <strong>{{ draftPath.name }}</strong> ()</p>
        </div>
        <div class="wiz-done-actions">
          <button v-if="draftPath" class="wiz-next" @click="takeDraftTerm">📋 Take Term in {{ draftPath.name }}</button>
          <button class="wiz-done-btn" @click="closeAndClear">Done</button>
        </div>
      </template>
      <!-- Normal term results -->
      <template v-else>
        <p class="wiz-phase-label">Term Complete — #{{ result.termNumber }}</p>
        <table class="wiz-table">
          <tbody>
            <tr v-if="result.qualification"><td>Qualification</td><td :class="result.qualification.success ? 'wiz-good' : 'wiz-bad'">{{ result.qualification.success ? '✅' : '❌' }}{{ result.qualification.drafted ? ' (drafted)' : '' }}</td></tr>
            <tr v-if="result.learn"><td>Learn</td><td class="wiz-good">{{ result.learn.wasSteppedUp ? '📈' : '📖' }} {{ fmtName(result.learn.traitName) }}</td></tr>
            <tr v-if="result.survive"><td>Survive</td><td :class="result.survive.success ? 'wiz-good' : 'wiz-bad'">{{ result.survive.rollSummary }}<span v-if="result.survive.mishapDescription"> 💀 {{ result.survive.mishapDescription }}</span><span v-if="result.survive.forcedMuster" class="wiz-mo-badge">🏁 mustered out</span></td></tr>
            <tr v-if="result.event"><td>Event</td><td class="wiz-good">📋 {{ result.event.description }}</td></tr>
            <tr v-if="result.advance"><td>Advance</td><td :class="result.advance.success ? 'wiz-good' : 'wiz-dim'">{{ result.advance.success ? '🏆 ' + result.advance.rankName : 'No advancement' }}</td></tr>
            <tr v-if="!result.event && !result.advance"><td colspan="2" class="wiz-dim" style="text-align:center">Event & Advance skipped</td></tr>
          </tbody>
        </table>
        <div class="wiz-done-actions">
          <button class="wiz-next" @click="resetWizard">🔄 Another Term</button>
          <button class="wiz-muster-btn" @click="doMusterOut">🏁 Muster Out</button>
          <button class="wiz-done-btn" @click="closeAndClear">Done</button>
        </div>
      </template>
    </template>
    <template v-else-if="step === 'mustered'">
      <p class="wiz-phase-label">Mustered Out</p>
      <div v-if="musterResult" class="wiz-result wiz-good">
        <p>🎉 {{ musterResult.pathName }}</p>
        <p v-if="musterResult.benefits?.length">{{ musterResult.benefits.join(', ') }}</p>
        <p>💰 +{{ musterResult.razmeritGained }} razmerit</p>
      </div>
      <button class="wiz-done-btn" @click="closeAndClear">Done</button>
    </template>
    <div v-if="executing" class="wiz-loading-inline">⏳ Rolling…</div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { useApi } from '../composables/useApi.js'
import DieIcon from './DieIcon.vue'

const props = defineProps({
  visible: { type: Boolean, default: false },
  embedded: { type: Boolean, default: false },
  entityId: { type: String, required: true },
  universe: { type: String, default: 'earth' },
  traitSettings: { type: Array, default: () => [] },  // { id, traitId, name, dice }[]
  currentLifePathId: { type: String, default: null },
  termsServed: { type: Number, default: 0 },
})
const emit = defineEmits(['close', 'updated'])
const { graphql } = useApi()

const step = ref('choose')
const loadingPaths = ref(false)
const executing = ref(false)
const STORAGE_KEY = computed(() => `lp_result_${props.entityId}`)
// ⚠ Track whether wizard was closed by user (not remount) to clear storage
let _wizClosedByUser = false
const paths = ref([])
const selectedPath = ref(null)
const result = ref({})
const musterResult = ref(null)
const phaseIdx = ref(0)
const manualValues = ref({})
const manualValue = ref(null)
const selectedEvent = ref(null)
const selectedLearn = ref(null)
const selectedMishap = ref(null)
const phases = ['qual', 'learn', 'survive', 'event', 'advance', 'mishap']

function fmtName(id) {
  if (!id) return '—'
  // Check traitNameMap first (from entity traitSettings)
  const m = traitNameMap.value
  if (m[id]) return m[id]
  // Fallback: strip trait- prefix and humanize
  return id.replace(/^trait-/, '').replace(/[-_]\w{4}$/, '').replace(/[-_]/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
}
function truncate(s,n) { return s&&s.length>n?s.slice(0,n)+'…':s||'' }
function dieNum(dieType) { return String(dieType||'').replace(/^D/i,'') }

const traitNameMap = computed(() => {
  const m = {}
  for (const ts of props.traitSettings) if (ts.traitId && ts.name) m[ts.traitId] = ts.name
  return m
})
const traitDieMap = computed(() => {
  const m = {}
  for (const ts of props.traitSettings) if (ts.traitId && ts.dice?.length) m[ts.traitId] = String(ts.dice[0]).toLowerCase()
  return m
})
const surviveTraitIds = computed(() => selectedPath.value?.survival?.traitIds || [])
const advanceTraitIds = computed(() => selectedPath.value?.advancement?.traitIds || [])
const phaseDie = computed(() => {
  if (phases[phaseIdx.value]==='qual') return traitDieMap.value[qualTraitId.value] || null
  if (phases[phaseIdx.value]==='survive') { for (const tid of surviveTraitIds.value) { const d = traitDieMap.value[tid]; if (d) return d } return null }
  if (phases[phaseIdx.value]==='advance') { for (const tid of advanceTraitIds.value) { const d = traitDieMap.value[tid]; if (d) return d } return null }
  return null
})
const phaseDieLabel = computed(() => phaseDie.value ? String(phaseDie.value) : '')

const phaseLabel = computed(() => ({qual:'Qualification',learn:'Learn',survive:'Survive',event:'Event',advance:'Advance'})[phases[phaseIdx.value]]||'')
const qualTraitId = computed(() => selectedPath.value?.qualification?.traitId)
const qualDifficulty = computed(() => dieNum(selectedPath.value?.qualification?.difficulty||'D4'))
const surviveDifficulty = computed(() => dieNum(selectedPath.value?.survival?.difficulty||'D6'))
const survivePenalties = computed(() => {
  const sp = selectedPath.value
  if (!sp?.survival) return { effective: dieNum('D6'), perPath: 0, global: 0, info: '' }
  let steps = 0
  const parts = []
  // Per-path penalty
  const tpa = sp.survival.termPenaltyAfter
  const isContinuing = props.currentLifePathId === sp.id
  if (tpa && isContinuing) {
    steps++
    parts.push(`+1 step (per-path: ${tpa} terms)`)
  }
  // Global penalty: every 7 total terms
  const gp = Math.floor((props.termsServed || 0) / 7)
  if (gp > 0) {
    steps += gp
    parts.push(`+${gp} step${gp>1?'s':''} (global: ${props.termsServed} total terms)`)
  }
  const baseDie = parseInt(dieNum(sp.survival.difficulty), 10)
  const dieSizes = [4, 6, 8, 10, 12]
  const baseIdx = dieSizes.indexOf(baseDie)
  const effIdx = Math.min(baseIdx + steps, dieSizes.length - 1)
  return {
    effective: String(dieSizes[effIdx]),
    perPath: tpa || 0,
    global: gp,
    info: parts.length ? parts.join(', ') : 'no penalties',
    steps,
  }
})
const advanceDifficulty = computed(() => dieNum(selectedPath.value?.advancement?.difficulty||'D6'))
const qualTraitName = computed(() => fmtName(qualTraitId.value))
const rollTraitName = computed(() => {
  const p = phases[phaseIdx.value]
  if (p === 'qual') return qualTraitName.value
  if (p === 'survive') return surviveTraitIds.value.map(fmtName).join(', ') || 'Survival'
  if (p === 'advance') return advanceTraitIds.value.map(fmtName).join(', ') || 'Advancement'
  return ''
})
const showTable = computed(() => ['qual','survive','advance'].includes(phases[phaseIdx.value]))
const showList = computed(() => ['learn','mishap','event'].includes(phases[phaseIdx.value]))
const showRoll = computed(() => showTable.value && manualValue.value === null)
const phaseHint = computed(() => {
  const p=phases[phaseIdx.value]
  const sp = selectedPath.value
  if(p==='qual') return `Roll ${qualTraitName.value} vs ${qualDifficulty.value}`
  if(p==='survive'){
    const mc = sp?.survival?.mishaps?.length || 0
    return `Roll to survive vs ${surviveDifficulty.value}${mc ? ` | ${mc} mishap${mc>1?'s':''} possible` : ''}`
  }
  if(p==='advance') return `Roll for promotion vs ${advanceDifficulty.value}`
  if(p==='learn') return `Train a trait this term${sp?.curriculum?.length ? ` (${sp.curriculum.length} option${sp.curriculum.length>1?'s':''})` : ''}`
  if(p==='mishap') return 'A mishap has occurred — select one from the table below.'
  if(p==='event'){
    const ec = sp?.events?.length || 0
    return ec ? `${ec} possible event${ec>1?'s':''}` : 'No events'
  }
  return ''
})
const outcomeRows = computed(() => {
  const p=phases[phaseIdx.value]
  if(['qual','survive','advance'].includes(p)){
    const s=manualValues.value[p]
    const r=[
      {roll:'1–2',val:1,name:p==='survive'?'❌ Mishap':p==='advance'?'❌ No promotion':'❌ Fail',selected:s===1},
      {roll:'3–5',val:3,name:p==='survive'?'⚠️ Barely survived':p==='advance'?'❌ No promotion':'✅ Marginal',selected:s===3},
      {roll:'6–8',val:6,name:'🎉 Success',selected:s===6},
      {roll:'9–10',val:9,name:'🌟 Exceptional',selected:s===9},
      {roll:'11–12',val:11,name:'💎 Perfect',selected:s===11},
    ]
    return r
  }
  return []
})
const draftPath = computed(() => {
  const did = result.value?.qualification?.draftedPathId
  if (!did) return null
  return paths.value.find(p => p.id === did) || null
})
const mishapItems = computed(() => {
  if (phases[phaseIdx.value] === 'mishap' && selectedPath.value?.survival?.mishaps) {
    return selectedPath.value.survival.mishaps.map((m, i) => ({
      label: `#${i+1}`,
      name: m.description || m,
      mustMuster: m.must_muster_out,
    }))
  }
  return []
})
const listItems = computed(() => {
  if(phases[phaseIdx.value]==='learn'&&selectedPath.value?.curriculum){
    return selectedPath.value.curriculum.map(c=>({label:fmtName(c.traitId),desc:c.stepUp?'(step up)':`(new at ${c.createAt})`}))
  }
  if(phases[phaseIdx.value]==='event'&&selectedPath.value?.events){
    return selectedPath.value.events.map((e,i)=>({label:`#${i+1}`,name:e.description}))
  }
  return []
})
function log(label, detail) { console.log(`[WIZ] ${label}`, detail) }
function logPhase() {
  const p = phases[phaseIdx.value]
  const mv = manualValues.value
  log('phase', `${step.value} → ${p}  path=${selectedPath.value?.name||'?'}  qual=${mv.qual??'?'}  learn=done  surv=${mv.survive??'?'}  adv=${mv.advance??'?'}`)
}
function selectRow(row){ manualValues.value[phases[phaseIdx.value]]=row.val; manualValue.value=row.val; log('select', `${phases[phaseIdx.value]} ← ${row.roll} (val=${row.val})`) }
function quickRollMishap(){
  const items = mishapItems.value
  if (items.length) {
    const pick = Math.floor(Math.random() * items.length)
    selectedMishap.value = pick
    log('quickRollMishap', `selected mishap #${pick+1}: ${items[pick].name}`)
  }
}
async function quickRoll(){
  const die = phaseDie.value
  log('quickRoll/enter', `phaseDie=${die} rollTraitName=${rollTraitName.value} traitDieMap-keys=${Object.keys(traitDieMap.value).join(',')}`)
  if (!die) { log('quickRoll/skip', 'phaseDie is null, skipping roll'); nextPhase(); return }
  const { roll } = useApi()
  try {
    const data = await roll(props.entityId, props.universe, [[die, rollTraitName.value]])
    if (data?.highest) {
      // Map roll result to outcome row value: 1-2→1, 3-5→3, 6-8→6, 9-10→9, 11-12→11
      const r = data.highest
      let val = 1
      if (r >= 11) val = 11
      else if (r >= 9) val = 9
      else if (r >= 6) val = 6
      else if (r >= 3) val = 3
      // Find the matching outcome row and select it
      const outcomes = outcomeRows.value
      const match = outcomes.find(o => o.val === val)
      if (match) selectRow(match)
    }
  } catch (e) {
    log('quickRoll/error', e.message)
    // Fallback: random selection
    const outcomes = outcomeRows.value
    if (outcomes.length) {
      const pick = outcomes[Math.floor(Math.random() * outcomes.length)]
      selectRow(pick)
    }
  }
}
const showExecute = computed(() => {
  // Show "Execute Term" when all roll phases have values and we're on the last phase
  return manualValues.value['qual'] !== undefined &&
    manualValues.value['survive'] !== undefined &&
    manualValues.value['advance'] !== undefined &&
    phaseIdx.value === phases.length - 1
})
function nextPhase(){
  log('nextPhase/click', `showRoll=${showRoll.value} showTable=${showTable.value} manualValue=${manualValue.value} phaseDie=${phaseDie.value} traitDieMap-size=${Object.keys(traitDieMap.value).length}`)
  manualValue.value=null
  const fromPhase = phases[phaseIdx.value]
  if (phaseIdx.value === 0) {
    const qv = manualValues.value['qual']
    const isContinuing = props.currentLifePathId === selectedPath.value?.id
    const hasDraft = selectedPath.value?.qualification?.draft
    if (qv !== undefined && qv < 3) {
      if (isContinuing) log('nextPhase', `${fromPhase} → learn (continuing term, qual skipped)`)
      else if (hasDraft) log('nextPhase', `${fromPhase} → learn (qual fail, draft available — will apply on execute)`)
      else log('nextPhase', `${fromPhase} → learn (qual fail, no draft)`)
    }
  }
  // Survive → if failed with mishaps: jump to mishap at the end, skipping event+advance
  const svFailed = manualValues.value['survive'] !== undefined && manualValues.value['survive'] < 3
  const hasMishaps = selectedPath.value?.survival?.mishaps?.length
  if (phaseIdx.value === 2) {
    if (svFailed && hasMishaps) {
      phaseIdx.value = 5  // jump to mishap (last phase)
      log('nextPhase', `${fromPhase} → mishap (survive failed, skipping event+advance)`)
    } else {
      phaseIdx.value = 3  // event
      log('nextPhase', `${fromPhase} → event`)
    }
  }
  // Advance → if survive failed, go to mishap; otherwise execute term
  else if (phaseIdx.value === 4) {
    if (svFailed && hasMishaps) {
      phaseIdx.value = 5  // go to mishap
      log('nextPhase', `advance → mishap`)
    } else {
      executeTerm()
      return
    }
  }
  // Mishap → execute term
  else if (phaseIdx.value === 5) {
    executeTerm()
    return
  }
  else if(phaseIdx.value<phases.length-1) phaseIdx.value++
  else if (manualValues.value['qual'] !== undefined) executeTerm()
  else step.value='results'
  const toPhase = phases[phaseIdx.value]
  log('nextPhase', `${fromPhase} → ${toPhase}`)
}
function prevPhase(){ if(phaseIdx.value>0){phaseIdx.value--;manualValue.value=manualValues.value[phases[phaseIdx.value]]||null}else resetWizard() }
function startPath(lp){
  selectedPath.value=lp; manualValues.value={}; manualValue.value=null; result.value={}; step.value='configure'
  const hasQual = lp.qualification && lp.qualification.traitId
  if (!hasQual) {
    // No qualification check — auto-succeed and skip to learn phase
    manualValues.value['qual'] = 7
    phaseIdx.value = 1
    log('startPath', `choose → learn (qual auto-success)  path=${lp.name}`)
  } else {
    phaseIdx.value = 0
    log('startPath', `choose → configure  path=${lp.name}  qualTraitId=${lp.qualification?.traitId}  qualDie=${traitDieMap.value[lp.qualification?.traitId]||'none'}`)
  }
}
async function executeTerm(){
  const qm=manualValues.value['qual']??null, sm=manualValues.value['survive']??null, am=manualValues.value['advance']??null
  const li = selectedLearn.value
  const mi = selectedMishap.value
  log('executeTerm', `path=${selectedPath.value?.name}  qual=${qm}  surv=${sm}  adv=${am}  learnIdx=${li}  mishapIdx=${mi}`)
  executing.value=true
  const data=await graphql(`mutation($eid:ID!, $lpid:ID!, $qm:Int, $sm:Int, $am:Int, $li:Int, $mi:Int){takeTerm(entityId:$eid,lifePathId:$lpid,qualManual:$qm,surviveManual:$sm,advanceManual:$am,learnIndex:$li,mishapIndex:$mi){qualification{success drafted draftedPathId locationBlocked}learn{traitGainedId traitName wasSteppedUp}survive{success rollSummary mishapDescription forcedMuster}event{eventIndex description}advance{success newRank rankName}termNumber}}`,{eid:props.entityId,lpid:selectedPath.value.id,qm,sm,am,li,mi})
  result.value=data?.takeTerm||{}; executing.value=false; step.value='results'; emit('updated')
  const r = result.value
  log('executeTerm/result', `qual=${r.qualification?.success?'pass':'fail'} draft=${r.qualification?.drafted||false} learn=${r.learn?.wasSteppedUp?'stepUp':'new'} surv=${r.survive?.success?'pass':'fail'} mishap=${r.survive?.mishapDescription||'none'} forcedMuster=${r.survive?.forcedMuster||false} event=${r.event?.description||'none'} adv=${r.advance?.success?'pass':'fail'} step→results`)
  // Persist results so they survive a component remount (CharacterSheet re-render)
  try { sessionStorage.setItem(STORAGE_KEY.value, JSON.stringify({ step: 'results', result: result.value, selectedPathId: selectedPath.value?.id, musterResult: null })) } catch {}
}
async function takeDraftTerm(){
  const dp = draftPath.value
  if (!dp) return
  executing.value=true
  const data=await graphql(`mutation($eid:ID!, $lpid:ID!){takeTerm(entityId:$eid,lifePathId:$lpid){qualification{success drafted}learn{traitGainedId traitName wasSteppedUp}survive{success rollSummary mishapDescription forcedMuster}event{eventIndex description}advance{success newRank rankName}termNumber}}`,{eid:props.entityId,lpid:dp.id})
  selectedPath.value=dp
  result.value=data?.takeTerm||{}; executing.value=false; step.value='results'; emit('updated')
  try { sessionStorage.setItem(STORAGE_KEY.value, JSON.stringify({ step: 'results', result: result.value, selectedPathId: dp.id, musterResult: null })) } catch {}
}
async function doMusterOut(){
  executing.value=true
  const data=await graphql(`mutation($eid:ID!){musterOut(entityId:$eid){pathId pathName termsServed finalRank benefits razmeritGained}}`,{eid:props.entityId})
  musterResult.value=data?.musterOut||null; step.value='mustered'; executing.value=false; emit('updated')
  try { sessionStorage.setItem(STORAGE_KEY.value, JSON.stringify({ step: 'mustered', result: result.value, selectedPathId: selectedPath.value?.id, musterResult: musterResult.value })) } catch {}
}
function resetWizard(){ log('resetWizard', `from step=${step.value} called_by=${new Error().stack?.split('\n')[2]?.trim()||'?'}`); step.value='choose'; phaseIdx.value=0; manualValues.value={}; manualValue.value=null; result.value={}; selectedPath.value=null; try { sessionStorage.removeItem(STORAGE_KEY.value) } catch {}; loadPaths() }
function closeAndClear(){ try { sessionStorage.removeItem(STORAGE_KEY.value) } catch {}; emit('close') }
async function loadPaths(){
  loadingPaths.value=true
  const data=await graphql(`query($u:String){lifePaths(universe:$u){id name universe description type qualification{traitId difficulty mustBeAtLocation draft}curriculum{traitId createAt stepUp minRank}survival{traitIds difficulty termPenaltyAfter mishaps}events{description minRank}advancement{traitIds difficulty ranks{number name benefits}}musterOut{perTermBenefits}}}`,{u:props.universe})
  paths.value=data?.lifePaths||[]; loadingPaths.value=false
}
watch(()=>props.visible,async (v)=>{
  if (!v) { _wizClosedByUser = true; try { sessionStorage.removeItem(STORAGE_KEY.value) } catch {}; return }
  // Always load paths first (needed for restore lookups or fresh start)
  await loadPaths()
  // Restore persisted results from a remount
  if (step.value==='choose') {
    try {
      const stored = sessionStorage.getItem(STORAGE_KEY.value)
      if (stored && !_wizClosedByUser) {
        const s = JSON.parse(stored)
        if (s.step && s.step !== 'mustered' && s.result) {
          step.value = s.step
          result.value = s.result
          musterResult.value = s.musterResult || null
          if (s.selectedPathId) selectedPath.value = paths.value.find(p => p.id === s.selectedPathId) || null
          _wizClosedByUser = false
          log('resetWizard/skip', `restored from storage step=${s.step} path=${s.selectedPathId}`)
          return
        }
      }
    } catch {}
    resetWizard()
  }
  _wizClosedByUser = false
},{immediate:true})
</script>

<style scoped>
.wizard-backdrop{position:fixed;inset:0;z-index:100;background:rgba(0,0,0,0.6);display:flex;align-items:safe center;justify-content:center;padding:20px}
.wizard-panel{background:var(--bg-panel);backdrop-filter:blur(16px);border-radius:var(--radius);border:1px solid var(--border);width:420px;max-width:95vw;max-height:calc(100vh - 40px);display:flex;flex-direction:column;overflow:hidden;position:relative}
.wizard-header{display:flex;align-items:center;justify-content:space-between;padding:12px 16px;border-bottom:1px solid var(--border);flex-shrink:0}
.wizard-header h2{font-size:16px;margin:0}
.wiz-close{background:none;border:none;color:var(--text-dim);font-size:16px;cursor:pointer}
.wiz-body{padding:16px;flex:1;min-height:0;overflow-y:auto}
.wiz-embedded{padding:0 0 12px 0}
.wiz-hint{color:var(--text-dim);margin:0 0 12px;font-size:13px}
.wiz-loading,.wiz-empty{color:var(--text-dim);font-size:13px;padding:20px 0;text-align:center}
.wiz-path-list{display:flex;flex-direction:column;gap:6px}
.wiz-path-btn{display:flex;flex-direction:column;align-items:flex-start;background:var(--bg-input);border:1px solid var(--border);border-radius:6px;padding:10px 12px;cursor:pointer;text-align:left;width:100%}
.wiz-path-btn:hover{border-color:var(--accent)}
.wiz-path-name{font-weight:600;font-size:14px}
.wiz-path-type{font-size:11px;color:var(--accent);text-transform:uppercase}
.wiz-path-desc{font-size:12px;color:var(--text-dim);margin-top:2px}
.wiz-phase-label{font-weight:700;text-transform:uppercase;letter-spacing:1px;font-size:12px;color:var(--accent);margin-bottom:4px}
.wiz-phase-hint{font-size:13px;color:var(--text-dim);margin-bottom:12px}
.wiz-table{width:100%;border-collapse:collapse;margin-bottom:12px;font-size:13px}
.wiz-table th{text-align:left;padding:6px 8px;border-bottom:1px solid var(--border);color:var(--text-dim);font-size:11px;text-transform:uppercase}
.wiz-table td{padding:6px 8px;border-bottom:1px solid rgba(255,255,255,0.05)}
.wiz-table tbody tr{cursor:pointer}
.wiz-table tbody tr:hover{background:rgba(255,255,255,0.03)}
.wiz-row-sel{background:rgba(0,200,100,0.1)!important;color:#4c4}
.wiz-row-sel td{border-color:rgba(0,200,100,0.2)}
.wiz-td-roll{font-weight:600;color:var(--accent);width:50px}
.wiz-td-desc{color:var(--text-dim);font-size:12px}
.wiz-phase-actions{display:flex;gap:6px}
.wiz-next,.wiz-back,.wiz-done-btn,.wiz-muster-btn{flex:1;padding:8px 12px;border:1px solid var(--border);border-radius:6px;background:var(--bg-input);color:var(--text);cursor:pointer;font-size:13px;text-align:center}
.wiz-next:hover,.wiz-done-btn:hover{border-color:var(--accent)}
.wiz-back{flex:0}
.wiz-muster-btn{background:rgba(200,150,0,0.1);border-color:#c90;color:#da0}
.wiz-result{padding:10px 12px;border-radius:6px;margin-bottom:8px;font-size:13px}
.wiz-good{color:#4c4}
.wiz-bad{color:#c55}
.wiz-dim{color:var(--text-dim)}
.wiz-done-actions{display:flex;flex-direction:column;gap:4px;margin-top:12px}
.wiz-loading-overlay{position:absolute;inset:0;background:rgba(0,0,0,0.5);display:flex;align-items:center;justify-content:center;font-size:20px;z-index:10}
.wiz-loading-inline{padding:12px;text-align:center;color:var(--text-dim);font-size:14px}
.wiz-preview{margin-top:4px}
.wiz-preview-label{display:block;font-size:9px;color:var(--text-dim);text-transform:uppercase;letter-spacing:0.5px;margin-bottom:2px}
.wiz-mo-badge{display:inline-block;margin-left:6px;font-size:9px;background:rgba(200,150,0,0.15);color:#da0;padding:1px 4px;border-radius:3px}
.wiz-roll-btn{display:inline-flex;align-items:center;justify-content:center;gap:6px}
.wiz-roll-btn :deep(.die-icon){width:22px;height:24px;flex-shrink:0}
</style>
