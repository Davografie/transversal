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
        <button class="wiz-close" @click="close">✕</button>
      </div>

      <div class="wiz-body">
        <!-- Choose a life path -->
        <template v-if="step === 'choose'">
          <p class="wiz-hint">Choose a life path to take a term in.</p>
          <div v-if="busy" class="wiz-loading">Loading…</div>
          <div v-else-if="!paths.length" class="wiz-empty">No life paths available.</div>
          <div v-else class="wiz-path-list">
            <button
              v-for="lp in paths"
              :key="lp.id"
              class="wiz-path-btn"
              :disabled="!lp.factionIds?.length"
              @click="startPath(lp)"
            >
              <span class="wiz-path-name">{{ lp.name }}</span>
              <span v-if="!lp.factionIds?.length" class="wiz-path-nofac">no offering faction</span>
              <span class="wiz-path-desc">{{ truncate(lp.description, 70) }}</span>
            </button>
          </div>
          <p v-if="error" class="wiz-error">{{ error }}</p>
        </template>

        <!-- Active term: current roll table -->
        <template v-else-if="step === 'term'">
          <p class="wiz-phase-label">
            {{ currentTable?.name || 'Roll Table' }}
            <span class="wiz-chip">{{ currentTable?.scheme }}</span>
            <span v-if="!isCheckTable" class="wiz-chip">{{ currentTable?.die }}</span>
          </p>

          <p v-if="currentTable?.check" class="wiz-check">
            roll {{ checkTraits }} vs {{ currentTable.check.difficulty }}
            <template v-if="currentTable.check.freeChoice"> · free choice</template>
          </p>

          <table v-if="entries.length" class="wiz-table">
            <thead>
              <tr><th>Key</th><th>Result</th></tr>
            </thead>
            <tbody>
              <tr v-for="(e, i) in entries" :key="i" class="wiz-row" @click="selectEntry(i + 1)">
                <td class="wiz-td-key">{{ entryKey(e, i) }}</td>
                <td>
                  <div class="wiz-entry-label">{{ e.label }}</div>
                  <div v-if="e.description" class="wiz-entry-desc">{{ e.description }}</div>
                  <div v-if="e.conditions?.length" class="wiz-conds">
                    <span v-for="(c, ci) in e.conditions" :key="ci" class="wiz-cond">if {{ conditionSummary(c) }}</span>
                  </div>
                  <div v-for="(eff, ei) in e.effects" :key="ei" class="wiz-effect">{{ effectSummary(eff) }}</div>
                </td>
              </tr>
            </tbody>
          </table>

          <div class="wiz-actions">
            <button v-if="isCheckTable" class="wiz-next" :disabled="resolving" @click="rollCheck">🎲 Roll Check</button>
            <button v-else class="wiz-next" :disabled="resolving" @click="rollTable">🎲 Roll {{ currentTable?.die }}</button>
            <button class="wiz-back" :disabled="resolving" @click="backToChoose">↩ Paths</button>
          </div>

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
            <button class="wiz-next" @click="startOver">Take another term</button>
            <button class="wiz-done-btn" @click="close">Done</button>
          </div>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useApi } from '@/composables/useApi.js'
import { useEffectActions } from '@/composables/useEffectActions.js'

const props = defineProps({
  visible: { type: Boolean, default: false },
  embedded: { type: Boolean, default: false },
  entityId: { type: String, required: true },
  universe: { type: String, default: 'earth' },
})
const emit = defineEmits(['close', 'updated'])
const { graphql } = useApi()
const { load: loadEffectActions, summarize: summarizeEffect } = useEffectActions()

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
const rollNames = ref({})
const traitNames = ref({})

const title = computed(() => {
  if (step.value === 'choose') return 'Life Path'
  if (step.value === 'done') return lastResult.value?.mustered ? 'Mustered Out' : 'Term Complete'
  return selectedPath.value?.name || 'Life Path'
})
const entries = computed(() => currentTable.value?.entries || [])
const isCheckTable = computed(() => currentTable.value?.check != null)
const checkTraits = computed(() => {
  const ids = currentTable.value?.check?.traitIds || []
  return ids.length ? ids.map(traitName).join(', ') : '(untrained)'
})
const dieMax = computed(() => {
  const d = String(currentTable.value?.die || 'D6').replace(/^D/i, '')
  const n = parseInt(d, 10)
  return Number.isFinite(n) ? n : 6
})

function truncate(s, n) { return s && s.length > n ? s.slice(0, n) + '…' : s || '' }
function nameFor(map, id) { return id && map[id] ? map[id] : id }
function traitName(id) { return nameFor(traitNames.value, id) }
function resolveTarget(t) { return t ? (traitNames.value[t] || rollNames.value[t] || t) : t }
function effectSummary(eff) { return summarizeEffect(eff, resolveTarget) }

function entryKey(e, i) {
  if (e.minValue != null || e.maxValue != null) return `${e.minValue ?? ''}–${e.maxValue ?? ''}`
  if (e.weight != null) return `w${e.weight}`
  if (e.tier) return e.tier
  return String(i + 1)
}

function conditionSummary(c) {
  const parts = [c.type]
  if (c.target) parts.push(c.target)
  if (c.value) parts.push(c.value)
  if (c.narrative) parts.push(`"${c.narrative}"`)
  return parts.join(' ')
}

async function loadPaths() {
  busy.value = true
  try {
    const data = await graphql(
      `query($u:String){ lifePaths(universe:$u){ id name universe description entryTableId factionIds } }`,
      { u: props.universe },
    )
    paths.value = data?.lifePaths || []
  } finally {
    busy.value = false
  }
}

async function loadNameMaps() {
  try {
    const [names, traits] = await Promise.all([
      graphql(`{ rollTables { id name } }`),
      graphql(`query($u:String!){ traitsByUniverse(universe:$u){ id name } }`, { u: props.universe }),
    ])
    for (const t of names?.rollTables || []) rollNames.value[t.id] = t.name
    for (const t of traits?.traitsByUniverse || []) traitNames.value[t.id] = t.name
  } catch {}
}

async function loadTable(tableId) {
  const data = await graphql(
    `query($id:ID!){rollTable(id:$id){id name universe lifePath scheme die check{traitIds difficulty freeChoice} entries{label description minValue maxValue weight tier conditions{type target value narrative} effects{timing type action target result targetScope context}}}}`,
    { id: tableId },
  )
  currentTable.value = data?.rollTable || null
}

async function loadPendingTerm() {
  const data = await graphql(
    `query($id:ID!){ entity(id:$id){ pendingTerm{ factionId pathId currentTableId continuation } } }`,
    { id: props.entityId },
  )
  return data?.entity?.pendingTerm || null
}

async function startPath(lp) {
  const factionId = lp?.factionIds?.[0]
  if (!factionId) { error.value = 'This path has no offering faction yet.'; return }
  selectedPath.value = lp
  error.value = ''
  resolving.value = true
  try {
    const data = await graphql(
      `mutation($eid:ID!,$fid:ID!,$pid:ID!){ startTerm(entityId:$eid, factionId:$fid, pathId:$pid){ factionId pathId currentTableId continuation } }`,
      { eid: props.entityId, fid: factionId, pid: lp.id },
    )
    const pt = data?.startTerm
    if (!pt) { error.value = 'Could not start term.'; return }
    pendingTerm.value = pt
    log.value = []
    lastResult.value = null
    await loadTable(pt.currentTableId)
    step.value = 'term'
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
    console.log('[LifePathWizard] resolveStep', {
      tableId: r.tableId, entryLabel: r.entryLabel, applied: r.applied,
      scheduled: r.scheduled, pendingChoices: r.pendingChoices,
      done: r.done, mustered: r.mustered, mishapMuster: r.mishapMuster,
      pendingTerm: r.pendingTerm,
    })
    lastResult.value = r
    log.value.push({ entryLabel: r.entryLabel, applied: r.applied, scheduled: r.scheduled, pendingChoices: r.pendingChoices })
    emit('updated')
    if (r.done || r.mustered) {
      pendingTerm.value = null
      currentTable.value = null
      step.value = 'done'
      return
    }
    pendingTerm.value = r.pendingTerm
    if (r.pendingTerm?.currentTableId) {
      await loadTable(r.pendingTerm.currentTableId)
    } else {
      step.value = 'done'
    }
  } finally {
    resolving.value = false
  }
}

function selectEntry(index) { resolveStep({ index }) }
function rollTable() {
  if (currentTable.value?.scheme === 'INDEX') {
    resolveStep({ roll: 1 + Math.floor(Math.random() * entries.value.length) })
  } else {
    resolveStep({ roll: 1 + Math.floor(Math.random() * dieMax.value) })
  }
}
function rollCheck() { resolveStep({}) }

function backToChoose() { step.value = 'choose'; error.value = '' }
function startOver() {
  selectedPath.value = null
  pendingTerm.value = null
  currentTable.value = null
  lastResult.value = null
  log.value = []
  step.value = 'choose'
}
function close() { emit('close') }

async function init() {
  if (!props.visible) return
  error.value = ''
  await Promise.all([loadPaths(), loadNameMaps(), loadEffectActions()])
  const pt = await loadPendingTerm()
  if (pt?.currentTableId) {
    selectedPath.value = paths.value.find(p => p.id === pt.pathId) || null
    pendingTerm.value = pt
    await loadTable(pt.currentTableId)
    step.value = 'term'
  } else {
    step.value = 'choose'
  }
}

onMounted(init)
watch(() => props.visible, (v) => { if (v) init() })
</script>

<style scoped>
.wiz-shell{position:fixed;inset:0;z-index:100;background:rgba(0,0,0,0.6);display:flex;align-items:center;justify-content:center;padding:20px}
.wiz-shell.wiz-embedded{position:static;inset:auto;background:transparent;display:block;padding:0;z-index:auto}
.wiz-panel{background:var(--bg-panel);border-radius:var(--radius);border:1px solid var(--border);width:460px;max-width:95vw;max-height:calc(100vh - 40px);display:flex;flex-direction:column;overflow:hidden}
.wiz-embedded .wiz-panel{width:100%;max-width:none;max-height:none;border:0;border-radius:0;background:transparent}
.wiz-header{display:flex;align-items:center;justify-content:space-between;padding:12px 16px;border-bottom:1px solid var(--border);flex-shrink:0}
.wiz-header h2{font-size:15px;margin:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.wiz-close{background:none;border:none;color:var(--text-dim);font-size:16px;cursor:pointer}
.wiz-body{padding:16px;flex:1;min-height:0;overflow-y:auto}
.wiz-hint{color:var(--text-dim);margin:0 0 12px;font-size:13px}
.wiz-loading,.wiz-empty{color:var(--text-dim);font-size:13px;padding:20px 0;text-align:center}
.wiz-path-list{display:flex;flex-direction:column;gap:6px}
.wiz-path-btn{display:flex;flex-direction:column;align-items:flex-start;background:var(--bg-input);border:1px solid var(--border);border-radius:6px;padding:10px 12px;cursor:pointer;text-align:left;width:100%}
.wiz-path-btn:hover:not(:disabled){border-color:var(--accent)}
.wiz-path-btn:disabled{opacity:0.5;cursor:not-allowed}
.wiz-path-name{font-weight:600;font-size:14px}
.wiz-path-nofac{font-size:10px;color:var(--text-dim);text-transform:uppercase;letter-spacing:0.5px;margin-top:1px}
.wiz-path-desc{font-size:12px;color:var(--text-dim);margin-top:2px}
.wiz-phase-label{font-weight:700;text-transform:uppercase;letter-spacing:1px;font-size:12px;color:var(--accent);margin:0 0 8px;display:flex;align-items:center;gap:6px}
.wiz-chip{font-size:9px;color:var(--text-dim);background:rgba(255,255,255,0.06);padding:1px 5px;border-radius:3px;text-transform:uppercase;font-weight:400}
.wiz-check{font-size:12px;color:var(--text-dim);margin:0 0 10px}
.wiz-table{width:100%;border-collapse:collapse;margin-bottom:12px;font-size:12px}
.wiz-table th{text-align:left;padding:5px 8px;border-bottom:1px solid var(--border);color:var(--text-dim);font-size:10px;text-transform:uppercase}
.wiz-table td{padding:5px 8px;border-bottom:1px solid rgba(255,255,255,0.05);vertical-align:top}
.wiz-table tbody tr{cursor:pointer}
.wiz-table tbody tr:hover{background:rgba(255,255,255,0.03)}
.wiz-td-key{font-weight:600;color:var(--accent);width:50px;white-space:nowrap}
.wiz-entry-label{font-weight:500}
.wiz-entry-desc{font-size:11px;color:var(--text-dim)}
.wiz-conds{margin-top:2px;display:flex;flex-direction:column;gap:1px}
.wiz-cond{font-size:10px;color:var(--accent)}
.wiz-effect{font-family:monospace;font-size:10px;color:var(--text);background:rgba(255,255,255,0.06);border:1px solid rgba(255,255,255,0.1);border-radius:4px;padding:3px 6px;margin:2px 0;line-height:1.4;word-break:break-word}
.wiz-actions{display:flex;gap:6px}
.wiz-next,.wiz-back,.wiz-done-btn{flex:1;padding:8px 12px;border:1px solid var(--border);border-radius:6px;background:var(--bg-input);color:var(--text);cursor:pointer;font-size:13px;text-align:center}
.wiz-next:hover:not(:disabled),.wiz-done-btn:hover{border-color:var(--accent)}
.wiz-next:disabled,.wiz-back:disabled{opacity:0.5;cursor:not-allowed}
.wiz-back{flex:0}
.wiz-error{color:#c55;font-size:12px;margin:8px 0 0}
.wiz-loading-inline{padding:10px;text-align:center;color:var(--text-dim);font-size:13px}
.wiz-result-block{margin-top:12px;padding:10px 12px;border:1px solid var(--border);border-radius:6px;background:rgba(255,255,255,0.02)}
.wiz-result-label{font-size:11px;color:var(--text-dim);text-transform:uppercase;letter-spacing:0.5px;margin-bottom:4px}
.wiz-applied{display:flex;flex-direction:column;gap:3px}
.wiz-applied-line{font-size:12px}
.wiz-scheduled{font-size:11px;color:var(--text-dim);margin-top:4px}
.wiz-choices{font-size:11px;color:#da0;margin-top:4px}
.wiz-log{margin-top:12px;font-size:11px;color:var(--text-dim)}
.wiz-log summary{cursor:pointer}
.wiz-log-line{padding:2px 0;border-bottom:1px solid rgba(255,255,255,0.03)}
.wiz-log-label{color:var(--text);margin-right:6px}
.wiz-log-applied{color:var(--text-dim)}
.wiz-result{padding:10px 12px;border-radius:6px;margin-bottom:8px;font-size:13px}
.wiz-good{color:#4c4}
.wiz-done-actions{display:flex;flex-direction:column;gap:4px;margin-top:12px}
</style>
