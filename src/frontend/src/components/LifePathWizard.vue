<template>
  <!-- Modal overlay (non-embedded) -->
  <div v-if="visible && !embedded" class="wizard-backdrop" @click.self="$emit('close')">
    <div class="wizard-panel">
      <div class="wizard-header">
        <h2>{{ selectedPath ? selectedPath.name : 'Life Path' }}</h2>
        <button class="wiz-close" @click="$emit('close')">✕</button>
      </div>
      <div class="wiz-body">
        <template v-if="step === 'choose'">
          <p class="wiz-hint">Choose a life path to take a term in.</p>
          <div v-if="loadingPaths" class="wiz-loading">Loading…</div>
          <div v-else-if="!paths.length" class="wiz-empty">No life paths available.</div>
          <div v-else class="wiz-path-list">
            <button v-for="lp in paths" :key="lp.id" class="wiz-path-btn" @click="startPath(lp)">
              <span class="wiz-path-name">{{ lp.name }}</span>
              <span class="wiz-path-type">{{ lp.type }}</span>
              <span class="wiz-path-desc">{{ truncate(lp.description, 60) }}</span>
            </button>
          </div>
        </template>
        <template v-else-if="step === 'configure'">
          <p class="wiz-phase-label">{{ phaseLabel }}</p>
          <p class="wiz-phase-hint">{{ phaseHint }}</p>
          <table v-if="showTable" class="wiz-table">
            <thead><tr><th>Roll</th><th>Result</th></tr></thead>
            <tbody>
              <tr v-for="row in outcomeRows" :key="row.roll" :class="{ 'wiz-row-sel': row.selected }" @click="selectRow(row)">
                <td class="wiz-td-roll">{{ row.roll }}</td><td>{{ row.name }}</td>
              </tr>
            </tbody>
          </table>
          <table v-else-if="showList && phases[phaseIdx] === 'event'" class="wiz-table">
            <thead><tr><th>#</th><th>Event</th></tr></thead>
            <tbody><tr v-for="item in listItems" :key="item.label"><td class="wiz-td-roll">{{ item.label }}</td><td>{{ item.name }}</td></tr></tbody>
          </table>
          <table v-else-if="showList" class="wiz-table">
            <thead><tr><th>Trait</th><th>Effect</th></tr></thead>
            <tbody><tr v-for="item in listItems" :key="item.label"><td>{{ item.label }}</td><td class="wiz-td-desc">{{ item.desc }}</td></tr></tbody>
          </table>
          <div class="wiz-phase-actions">
            <button v-if="showRoll" class="wiz-next" @click="executeTerm">🎲 Roll</button>
            <button v-if="manualValue !== null || !showTable" class="wiz-next" @click="nextPhase">Continue →</button>
            <button class="wiz-back" @click="prevPhase">← Back</button>
          </div>
        </template>
        <template v-else-if="step === 'results'">
          <p class="wiz-phase-label">Term Complete — #{{ result.termNumber }}</p>
          <table class="wiz-table">
            <tbody>
              <tr v-if="result.qualification"><td>Qualification</td><td :class="result.qualification.success ? 'wiz-good' : 'wiz-bad'">{{ result.qualification.success ? '✅' : '❌' }}{{ result.qualification.drafted ? ' (drafted)' : '' }}</td></tr>
              <tr v-if="result.learn"><td>Learn</td><td class="wiz-good">{{ result.learn.wasSteppedUp ? '📈' : '📖' }} {{ displayName(result.learn.traitName) }}</td></tr>
              <tr v-if="result.survive"><td>Survive</td><td :class="result.survive.success ? 'wiz-good' : 'wiz-bad'">{{ result.survive.rollSummary }}<span v-if="result.survive.mishapDescription"> 💀 {{ result.survive.mishapDescription }}</span></td></tr>
              <tr v-if="result.event"><td>Event</td><td class="wiz-good">📋 {{ result.event.description }}</td></tr>
              <tr v-if="result.advance"><td>Advance</td><td :class="result.advance.success ? 'wiz-good' : 'wiz-dim'">{{ result.advance.success ? '🏆 ' + result.advance.rankName : 'No advancement' }}</td></tr>
            </tbody>
          </table>
          <div class="wiz-done-actions">
            <button class="wiz-next" @click="resetWizard">🔄 Another Term</button>
            <button class="wiz-muster-btn" @click="doMusterOut">🏁 Muster Out</button>
            <button class="wiz-done-btn" @click="$emit('close')">Done</button>
          </div>
        </template>
        <template v-else-if="step === 'mustered'">
          <p class="wiz-phase-label">Mustered Out</p>
          <div v-if="musterResult" class="wiz-result wiz-good">
            <p>🎉 {{ musterResult.pathName }}</p>
            <p v-if="musterResult.benefits?.length">{{ musterResult.benefits.join(', ') }}</p>
            <p>💰 +{{ musterResult.razmeritGained }} razmerit</p>
          </div>
          <button class="wiz-done-btn" @click="$emit('close')">Done</button>
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
          <span class="wiz-path-type">{{ lp.type }}</span>
          <span class="wiz-path-desc">{{ truncate(lp.description, 60) }}</span>
        </button>
      </div>
    </template>
    <template v-else-if="step === 'configure'">
      <p class="wiz-phase-label">{{ phaseLabel }}</p>
      <p class="wiz-phase-hint">{{ phaseHint }}</p>
      <table v-if="showTable" class="wiz-table">
        <thead><tr><th>Roll</th><th>Result</th></tr></thead>
        <tbody>
          <tr v-for="row in outcomeRows" :key="row.roll" :class="{ 'wiz-row-sel': row.selected }" @click="selectRow(row)">
            <td class="wiz-td-roll">{{ row.roll }}</td><td>{{ row.name }}</td>
          </tr>
        </tbody>
      </table>
      <table v-else-if="showList && phases[phaseIdx] === 'event'" class="wiz-table">
        <thead><tr><th>#</th><th>Event</th></tr></thead>
        <tbody><tr v-for="item in listItems" :key="item.label"><td class="wiz-td-roll">{{ item.label }}</td><td>{{ item.name }}</td></tr></tbody>
      </table>
      <table v-else-if="showList" class="wiz-table">
        <thead><tr><th>Trait</th><th>Effect</th></tr></thead>
        <tbody><tr v-for="item in listItems" :key="item.label"><td>{{ item.label }}</td><td class="wiz-td-desc">{{ item.desc }}</td></tr></tbody>
      </table>
      <div class="wiz-phase-actions">
        <button v-if="showRoll" class="wiz-next" @click="executeTerm">🎲 Roll</button>
        <button v-if="manualValue !== null || !showTable" class="wiz-next" @click="nextPhase">Continue →</button>
        <button class="wiz-back" @click="prevPhase">← Back</button>
      </div>
    </template>
    <template v-else-if="step === 'results'">
      <p class="wiz-phase-label">Term Complete — #{{ result.termNumber }}</p>
      <table class="wiz-table">
        <tbody>
          <tr v-if="result.qualification"><td>Qualification</td><td :class="result.qualification.success ? 'wiz-good' : 'wiz-bad'">{{ result.qualification.success ? '✅' : '❌' }}{{ result.qualification.drafted ? ' (drafted)' : '' }}</td></tr>
          <tr v-if="result.learn"><td>Learn</td><td class="wiz-good">{{ result.learn.wasSteppedUp ? '📈' : '📖' }} {{ displayName(result.learn.traitName) }}</td></tr>
          <tr v-if="result.survive"><td>Survive</td><td :class="result.survive.success ? 'wiz-good' : 'wiz-bad'">{{ result.survive.rollSummary }}<span v-if="result.survive.mishapDescription"> 💀 {{ result.survive.mishapDescription }}</span></td></tr>
          <tr v-if="result.event"><td>Event</td><td class="wiz-good">📋 {{ result.event.description }}</td></tr>
          <tr v-if="result.advance"><td>Advance</td><td :class="result.advance.success ? 'wiz-good' : 'wiz-dim'">{{ result.advance.success ? '🏆 ' + result.advance.rankName : 'No advancement' }}</td></tr>
        </tbody>
      </table>
      <div class="wiz-done-actions">
        <button class="wiz-next" @click="resetWizard">🔄 Another Term</button>
        <button class="wiz-muster-btn" @click="doMusterOut">🏁 Muster Out</button>
        <button class="wiz-done-btn" @click="$emit('close')">Done</button>
      </div>
    </template>
    <template v-else-if="step === 'mustered'">
      <p class="wiz-phase-label">Mustered Out</p>
      <div v-if="musterResult" class="wiz-result wiz-good">
        <p>🎉 {{ musterResult.pathName }}</p>
        <p v-if="musterResult.benefits?.length">{{ musterResult.benefits.join(', ') }}</p>
        <p>💰 +{{ musterResult.razmeritGained }} razmerit</p>
      </div>
      <button class="wiz-done-btn" @click="$emit('close')">Done</button>
    </template>
    <div v-if="executing" class="wiz-loading-inline">⏳ Rolling…</div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { useApi } from '../composables/useApi.js'

const props = defineProps({
  visible: { type: Boolean, default: false },
  embedded: { type: Boolean, default: false },
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
const phaseIdx = ref(0)
const manualValues = ref({})
const manualValue = ref(null)
const phases = ['qual', 'learn', 'survive', 'event', 'advance']

function displayName(name) { return (name||'').split('_').map(w=>w.charAt(0).toUpperCase()+w.slice(1)).join(' ') }
function truncate(s,n) { return s&&s.length>n?s.slice(0,n)+'…':s||'' }

const phaseLabel = computed(() => ({qual:'Qualification',learn:'Learn',survive:'Survive',event:'Event',advance:'Advance'})[phases[phaseIdx.value]]||'')
const qualDifficulty = computed(() => selectedPath.value?.qualification?.difficulty||'D4')
const surviveDifficulty = computed(() => selectedPath.value?.survival?.difficulty||'D6')
const advanceDifficulty = computed(() => selectedPath.value?.advancement?.difficulty||'D6')
const showTable = computed(() => ['qual','survive','advance'].includes(phases[phaseIdx.value]))
const showList = computed(() => ['learn','event'].includes(phases[phaseIdx.value]))
const showRoll = computed(() => showTable.value && manualValue.value === null)
const phaseHint = computed(() => {
  const p=phases[phaseIdx.value]
  if(p==='qual') return `Roll to qualify. Target: ${qualDifficulty.value}`
  if(p==='survive') return `Roll to survive. Target: ${surviveDifficulty.value}`
  if(p==='advance') return `Roll for promotion. Target: ${advanceDifficulty.value}`
  if(p==='learn') return 'Train a trait this term.'
  if(p==='event') return 'Something happens…'
  return ''
})
const outcomeRows = computed(() => {
  const p=phases[phaseIdx.value]
  if(['qual','survive','advance'].includes(p)){
    const s=manualValues.value[p]
    const r=[{roll:'1–2',name:p==='survive'?'❌ Mishap':p==='advance'?'❌ No promotion':'❌ Fail',selected:s===1},{roll:'3–5',name:p==='survive'?'⚠️ Barely survived':p==='advance'?'❌ No promotion':'✅ Marginal',selected:s===3},{roll:'6–8',name:'🎉 Success',selected:s===6},{roll:'9–10',name:'🌟 Exceptional',selected:s===9},{roll:'11–12',name:'💎 Perfect',selected:s===11}]
    return r
  }
  return []
})
const listItems = computed(() => {
  if(phases[phaseIdx.value]==='learn'&&selectedPath.value?.curriculum){
    return selectedPath.value.curriculum.map(c=>({label:displayName(c.traitId),desc:c.stepUp?'(step up)':`(new at ${c.createAt})`}))
  }
  if(phases[phaseIdx.value]==='event'&&selectedPath.value?.events){
    return selectedPath.value.events.map((e,i)=>({label:`#${i+1}`,name:e.description}))
  }
  return []
})
function selectRow(row){ manualValues.value[phases[phaseIdx.value]]=1; manualValue.value=1 }
function nextPhase(){ manualValue.value=null; if(phaseIdx.value<phases.length-1) phaseIdx.value++; else step.value='results' }
function prevPhase(){ if(phaseIdx.value>0){phaseIdx.value--;manualValue.value=manualValues.value[phases[phaseIdx.value]]||null}else resetWizard() }
function startPath(lp){ selectedPath.value=lp; phaseIdx.value=0; manualValues.value={}; manualValue.value=null; result.value={}; step.value='configure' }
async function executeTerm(){
  const qm=manualValues.value['qual']??null, sm=manualValues.value['survive']??null, am=manualValues.value['advance']??null
  executing.value=true
  const data=await graphql(`mutation($eid:ID!, $lpid:ID!, $qm:Int, $sm:Int, $am:Int){takeTerm(entityId:$eid,lifePathId:$lpid,qualManual:$qm,surviveManual:$sm,advanceManual:$am){qualification{success drafted locationBlocked}learn{traitGainedId traitName wasSteppedUp}survive{success rollSummary mishapDescription}event{eventIndex description}advance{success newRank rankName}termNumber}}`,{eid:props.entityId,lpid:selectedPath.value.id,qm,sm,am})
  result.value=data?.takeTerm||{}; executing.value=false; step.value='results'; emit('updated')
}
async function doMusterOut(){
  executing.value=true
  const data=await graphql(`mutation($eid:ID!){musterOut(entityId:$eid){pathId pathName termsServed finalRank benefits razmeritGained}}`,{eid:props.entityId})
  musterResult.value=data?.musterOut||null; step.value='mustered'; executing.value=false; emit('updated')
}
function resetWizard(){ step.value='choose'; phaseIdx.value=0; manualValues.value={}; manualValue.value=null; result.value={}; selectedPath.value=null; loadPaths() }
async function loadPaths(){
  loadingPaths.value=true
  const data=await graphql(`query($u:String){lifePaths(universe:$u){id name universe description type qualification{difficulty}}}`,{u:props.universe})
  paths.value=data?.lifePaths||[]; loadingPaths.value=false
}
watch(()=>props.visible,(v)=>{if(v)resetWizard()},{immediate:true})
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
</style>
