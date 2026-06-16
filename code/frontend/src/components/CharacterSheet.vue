<template>
  <!-- Embedded: single root for attribute inheritance -->
  <div v-if="embedded" class="sheet-embedded">
    <div v-if="loading" class="loading">Loading…</div>
    <div v-else-if="error" class="error">{{ error }}</div>
    <template v-else-if="entity">
      <div class="header">
        <div class="header-top">
          <h2>{{ entity.name }}</h2>
          <img v-if="entity.backgroundImage" :src="entity.backgroundImage" class="sheet-portrait" />
          <button v-if="!gmMode" class="sheet-settings-btn" @click.stop="$emit('openSettings')" title="Player settings">↩</button>
        </div>
        <div v-if="gmMode" class="meta">
          <span class="location">{{ locationName || entity.currentLocation || 'Unknown' }}</span>
          <span class="universe">{{ universeName || entity.currentUniverse }}</span>
        </div>
        <div class="razmerit">
          <span class="razmerit-value">{{ entity.razmerit }}</span> razmerit
        </div>
      </div>
      <div v-if="traitSets.length" class="trait-sets">
        <div v-for="ts in traitSets" :key="ts.name" class="trait-set">
          <h4 @click="toggleSet(ts.name)" class="set-header">
            <span class="set-caret">{{ expandedSets.has(ts.name) ? '▾' : '▸' }}</span>
            {{ ts.name }}
            <span v-if="ts.limit" class="limit-dots">
              <span v-for="i in ts.limit" :key="i" class="limit-dot" :class="{ filled: i <= inPoolCount(ts) }">{{ i <= inPoolCount(ts) ? '●' : '○' }}</span>
            </span>
          </h4>
          <div v-show="expandedSets.has(ts.name)" class="set-body">
            <template v-for="t in ts.traits" :key="t.name">
              <div v-if="isKnown(t)" class="trait-row" :class="{ ego: t.ego, 'in-pool': isInPool(t), 'limit-reached': inPoolCount(ts) >= ts.limit && !isInPool(t) }" @click="onTraitClick(t)" @contextmenu.prevent="startEdit(t)" @touchstart="onTouchStart(t)" @touchend="onTouchEnd" @touchmove="onTouchEnd">
                <div class="trait-left">
                  <span class="trait-name" :class="{ disabled: phase !== 'adding' || isResourceDepleted(t) }">{{ displayName(t.name) }}</span>
                  <span v-if="t.statement" class="trait-statement">{{ t.statement }}</span>
                </div>
                <div class="trait-right">
                  <span class="trait-die" :class="`die-${resolvedDieType(t)}`">{{ resourceDisplay(t) }}</span>
                  <span v-if="t.polarity" class="polarity-badge" :class="'polarity-' + t.polarity.toLowerCase()">{{ t.polarity === 'NEGATIVE' ? '☠' : '⏳' }}</span>
                  <button
                    v-for="sfxId in t.sfxIds"
                    :key="sfxId"
                    class="sfx-btn"
                    :class="{ 'sfx-active': sfxActive(sfxId), 'sfx-used': sfxUsed(sfxId) && !sfxActive(sfxId) }"
                    :disabled="sfxUsed(sfxId) && !sfxActive(sfxId)"
                    @click.stop.prevent="sfxAllowedInPhase(sfxId) && activateSfx(sfxId)"
                    :title="sfxActive(sfxId) ? `Deactivate ${sfxId}` : `Activate ${sfxId}`"
                  >{{ sfxId.replace('sfx-', '') }}</button>
                </div>
              </div>
              <div v-else class="trait-row unknown-trait">
                <div class="trait-left">
                  <span class="trait-name unknown">???</span>
                </div>
                <div class="trait-right">
                  <span class="trait-die unknown-die">?</span>
                </div>
              </div>
              <!-- Inline trait edit panel -->
              <div v-if="editingTraitId === t.id" class="trait-edit" @click.stop>
                <div class="edit-dice">
                  <button v-for="(d, i) in editDice" :key="i" class="die-chip" @click="pickIdx = i; showDiePicker = true">{{ d }}</button>
                  <button class="die-chip add-chip" @click="pickIdx = editDice.length; showDiePicker = true">+</button>
                </div>
                <DiePicker v-if="showDiePicker" v-model="pickedDie" @update:model-value="onDiePicked" />
                <input v-if="t.statement !== undefined" v-model="editStatement" class="edit-statement" placeholder="Statement…" @input="onStatementInput" />
                <button class="edit-close" @click="cancelEdit" title="Close">×</button>
              </div>
            </template>
            </div> <!-- .set-body -->
          </div>
        </div>
      <div v-else class="empty">No traits configured</div>
    </template>
    <div v-else class="empty">No entity loaded</div>
  </div>

</template>

<script setup>
import { ref, watch, onMounted, onUnmounted } from 'vue'
import { useApi } from '../composables/useApi.js'
import DiePicker from './DiePicker.vue'

const props = defineProps({
  entityId: { type: String, required: true },
  universe: { type: String, default: 'earth' },
  phase: { type: String, default: 'adding' },
  embedded: { type: Boolean, default: false },
  gmMode: { type: Boolean, default: false },
  externalPoolSources: { type: Array, default: null },
  overrideEntityId: { type: String, default: null },
  viewerEntityId: { type: String, default: null },
})

const emit = defineEmits(['addToPool', 'removeFromPool', 'splitDie', 'removeByTsId', 'sfxToggled', 'openSettings'])

function displayName(name) {
  return name
    .split('_')
    .map(w => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ')
}

const { loading, error, graphql, triggerSfx, spendResourceDie, recoverResourceDie } = useApi()
const entity = ref(null)
const traitSets = ref([])

// Resolved human-readable names
const locationName = ref('')
const universeName = ref('')

// Accordion state — user controls which sets are expanded
const expandedSets = ref(new Set(JSON.parse(localStorage.getItem('expandedSets') || '[]')))

function toggleSet(name) {
  const s = new Set(expandedSets.value)
  if (s.has(name)) s.delete(name)
  else s.add(name)
  expandedSets.value = s
  localStorage.setItem('expandedSets', JSON.stringify([...s]))
}

// SFX usage tracking — reset per dice pool cycle
const sfxActivations = ref({})
const SFX_PHASES = {
  'sfx-hinder': ['adding'],
  'sfx-spray-n-pray': ['adding'],
}
const poolSources = ref([])

// Track resource trait dice that have been spent into the pool
// { tsId: dieType } — cleared when the die is removed from the pool
const spentResources = ref({})

// Inline trait editing
const editingTraitId = ref(null)
const editDice = ref([])
const editStatement = ref('')
const showDiePicker = ref(false)
const pickIdx = ref(0)
const pickedDie = ref('')
let longPressTimer = null

async function onTraitClick(t) {
  if (props.phase !== 'adding') return

  let dieType = (t.dieType || 'd6').toLowerCase()

  if (t.ratingType === 'RESOURCE') {
    const dice = t.dice || []

    if (spentResources.value[t.id]) {
      // Toggle OFF: recover the die
      dieType = spentResources.value[t.id]
      delete spentResources.value[t.id]
      recoverResourceDie(t.id, dieType).catch(() => {
        spentResources.value[t.id] = dieType  // rollback
      })
    } else {
      // Toggle ON: spend a die (first available type)
      if (dice.length === 0) return  // depleted
      dieType = dice[0].toLowerCase()
      spentResources.value[t.id] = dieType
      spendResourceDie(t.id, dieType).catch(() => {
        delete spentResources.value[t.id]  // rollback
      })
    }
    fetchEntity()
  }

  emit('addToPool', { die: dieType, source: t.name, label: displayName(t.name), tsId: t.id })
}

function resolvedDieType(t) {
  // Return the die type for CSS class (determines color)
  if (t.dice && t.dice.length > 0) return t.dice[0].toLowerCase()
  return (t.dieType || 'd6').toLowerCase()
}

function resourceDisplay(t) {
  // Show available dice for resource traits, rating string for static traits
  if (t.ratingType === 'RESOURCE') {
    if (t.dice && t.dice.length === 0) return 'depleted'
    return t.rating || 'empty'
  }
  return t.rating || (t.dice ? t.dice.join(', ') : '')
}

function isResourceDepleted(t) {
  if (t.ratingType !== 'RESOURCE') return false
  return (!t.dice || t.dice.length === 0) && !spentResources.value[t.id]
}

function isInPool(t) {
  return poolSources.value.includes(displayName(t.name))
}

function isKnown(t) {
  if (!props.overrideEntityId || !props.viewerEntityId) return true
  if (props.overrideEntityId === props.entityId) return true
  return (t.knownTo || []).includes(props.viewerEntityId)
}

function inPoolCount(ts) {
  return ts.traits.filter(t => isInPool(t)).length
}

function sfxAllowedInPhase(sfxId) {
  const allowed = SFX_PHASES[sfxId] || ['adding']
  return allowed.includes(props.phase)
}

// Pool state tracking — called by DiceRoller via App
function setPoolSources(sources) {
  // sources is now [{ die, label }, ...] — extract labels
  poolSources.value = sources.map(s => s.label || s).filter(Boolean)

  // Auto-recover resource dice that were removed from the pool
  // (e.g. via chip click in DiceRoller).  Only during adding phase —
  // once dice are rolled they stay spent.
  if (props.phase !== 'adding') return
  for (const tsId of Object.keys(spentResources.value)) {
    const dieType = spentResources.value[tsId]
    // Check if this trait's die is still in the pool
    let found = false
    for (const ts of traitSets.value) {
      for (const t of ts.traits) {
        if (t.id === tsId && poolSources.value.includes(displayName(t.name))) {
          found = true
          break
        }
      }
      if (found) break
    }
    if (!found) {
      // Die was removed — recover it
      recoverResourceDie(tsId, dieType)
      delete spentResources.value[tsId]
      fetchEntity()
    }
  }
}

defineExpose({ resetSfxCounts, setPoolSources, fetchEntity })

function sfxActive(sfxId) {
  return (sfxActivations.value[sfxId] || 0) > 0
}

function sfxUsed(sfxId) {
  if (!sfxAllowedInPhase(sfxId)) return true
  if (sfxActive(sfxId)) return true
  if (sfxId === 'sfx-spray-n-pray' && !poolSources.value.has('shooting')) return true
  return false
}

function resetSfxCounts() {
  sfxActivations.value = {}
  spentResources.value = {}
}

const QUERY = `
  query($id: ID!) {
    entity(id: $id) {
      name
      razmerit
      currentUniverse
      currentLocation
      backgroundImage
      traitSettings {
        id
        name
        traitsetName
        dieType
        ratingType
        rating
        ego
        statement
        sfxIds
        universe
        dice
        polarity
        traitsetOrder
        traitsetLimit
        knownTo
      }
    }
  }
`

async function fetchEntity() {
  const id = props.overrideEntityId || props.entityId
  const data = await graphql(QUERY, { id })
  if (data?.entity) {
    entity.value = data.entity
    resolveNames(data.entity)

    // Group trait settings by traitset, filter by universe
    const sets = {}
    for (const ts of data.entity.traitSettings || []) {
      if (!ts.ego && ts.universe !== props.universe) continue
      const key = ts.traitsetName || 'Other'
      if (!sets[key]) sets[key] = []
      sets[key].push(ts)
    }
    traitSets.value = Object.entries(sets)
      .map(([name, traits]) => ({ name, traits, order: traits[0]?.traitsetOrder ?? 99, limit: traits[0]?.traitsetLimit ?? 1 }))
      .sort((a, b) => a.order - b.order)
      .map(({ name, traits, order, limit }) => ({ name, traits, limit }))
  }
}

async function resolveNames(e) {
  if (e.currentLocation) {
    try {
      const r = await fetch(`/api/v1/locations/${e.currentLocation}/navigate`)
      const nav = await r.json()
      locationName.value = nav.location?.name || e.currentLocation
    } catch { locationName.value = e.currentLocation }
  }
  if (e.currentUniverse) {
    try {
      const r = await fetch('/api/v1/graphql', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: `{ entities(type: UNIVERSE) { id name currentUniverse } }` })
      })
      const json = await r.json()
      const universes = json.data?.entities || []
      const match = universes.find(u => u.currentUniverse === e.currentUniverse || u.id === e.currentUniverse)
      universeName.value = match?.name || e.currentUniverse
    } catch { universeName.value = e.currentUniverse }
  }
}

// Find the traitsetting ID that owns a given SFX
function findTsIdForSfx(sfxId) {
  for (const ts of traitSets.value) {
    for (const t of ts.traits) {
      if ((t.sfxIds || []).includes(sfxId)) return t.id
    }
  }
  return null
}

async function activateSfx(sfxId) {
  const active = sfxActive(sfxId)

  if (!active) {
    // Activate
    await triggerSfx(props.entityId, sfxId, props.universe)
    sfxActivations.value[sfxId] = 1
    await fetchEntity()

    if (sfxId === 'sfx-hinder') {
      const tsId = findTsIdForSfx('sfx-hinder')
      emit('removeByTsId', tsId)
      emit('addToPool', { die: 'd4', source: 'hinder', label: 'Hinder d4', tsId })
    }
    if (sfxId === 'sfx-spray-n-pray') {
      emit('splitDie', { source: 'shooting', label: 'Spray' })
    }
    emit('sfxToggled', { sfxId, active: true })
  } else {
    // Deactivate (reverse)
    sfxActivations.value[sfxId] = 0

    if (sfxId === 'sfx-hinder') {
      const tsId = findTsIdForSfx('sfx-hinder')
      emit('removeByTsId', tsId)
      // Reverse razmerit: spend 1
      await triggerSfx(props.entityId, 'sfx-hinder', props.universe, { reverse: true })
    }
    if (sfxId === 'sfx-spray-n-pray') {
      emit('removeFromPool', 'shooting-a')
      emit('removeFromPool', 'shooting-b')
      await triggerSfx(props.entityId, 'sfx-spray-n-pray', props.universe, { reverse: true })
    }
    emit('sfxToggled', { sfxId, active: false })
    await fetchEntity()
  }
}

// ── Inline trait editing ──────────────────────────

function startEdit(t) {
  editingTraitId.value = t.id
  editDice.value = (t.dice && t.dice.length ? [...t.dice] : [t.dieType || 'd6']).map(d => d.toLowerCase())
  editStatement.value = t.statement || ''
  showDiePicker.value = false
}

function cancelEdit() {
  editingTraitId.value = null
}

async function doSave() {
  if (!editingTraitId.value) return
  await graphql(`mutation($id: ID!, $dice: [DieType!], $statement: String) {
    updateTraitSetting(id: $id, input: { dice: $dice, statement: $statement }) { id }
  }`, {
    id: editingTraitId.value,
    dice: editDice.value.map(d => d.toUpperCase()),
    statement: editStatement.value || null,
  })
  fetchEntity()
}

let statementDebounce = null
function onStatementInput() {
  clearTimeout(statementDebounce)
  statementDebounce = setTimeout(doSave, 500)
}

function onDiePicked(die) {
  if (!die) {
    editDice.value.splice(pickIdx.value, 1)
  } else if (pickIdx.value >= editDice.value.length) {
    editDice.value.push(die)
  } else {
    editDice.value.splice(pickIdx.value, 1, die)
  }
  showDiePicker.value = false
  doSave()
}

// Long-press detection for touchscreens
function onTouchStart(t) {
  longPressTimer = setTimeout(() => startEdit(t), 600)
}

function onTouchEnd() {
  clearTimeout(longPressTimer)
}

// Close edit on Escape
function onKeydown(e) {
  if (e.key === 'Escape' && editingTraitId.value) cancelEdit()
}

onMounted(() => document.addEventListener('keydown', onKeydown))
onUnmounted(() => document.removeEventListener('keydown', onKeydown))

onMounted(fetchEntity)
watch(() => props.entityId, fetchEntity)
watch(() => props.universe, fetchEntity)
watch(() => props.overrideEntityId, fetchEntity)

// Sync external pool sources (for GM panel)
watch(() => props.externalPoolSources, (sources) => {
  if (sources !== null) poolSources.value = [...sources]
}, { immediate: true })
</script>

<style scoped>
.sheet-embedded {
  background: var(--bg-panel);
  backdrop-filter: blur(12px);
  border-radius: var(--radius);
  padding: 12px 16px;
}

.set-header {
  cursor: pointer;
  user-select: none;
  display: flex;
  align-items: center;
  gap: 4px;
  margin: 8px 0 4px;
  font-size: 13px;
  text-transform: uppercase;
  letter-spacing: 1px;
  color: var(--text-dim);
  transition: color 0.15s;
}
.set-header:hover {
  color: var(--text);
}
.set-caret {
  font-size: 10px;
  width: 12px;
}
.set-body {
  padding-left: 4px;
}

.limit-dots {
  font-size: 10px;
  margin-left: auto;
  letter-spacing: 1px;
  vertical-align: middle;
  flex-shrink: 0;
}
.limit-dot {
  opacity: 0.35;
  transition: opacity 0.15s;
}
.limit-dot.filled {
  opacity: 1;
  color: var(--accent);
}

.trait-row.in-pool {
  background: rgba(64, 136, 212, 0.12);
  box-shadow: inset 2px 0 0 var(--accent);
}
.trait-row.limit-reached {
  opacity: 0.3;
  cursor: default;
  pointer-events: none;
}

.unknown-trait {
  cursor: default;
  opacity: 0.4;
}
.trait-name.unknown {
  font-style: italic;
  letter-spacing: 2px;
}
.unknown-die {
  font-weight: 700;
  font-size: 14px;
  color: var(--text-dim);
}

.trait-edit {
  position: relative;
  padding: 8px 22px 8px 12px;
  margin: 2px 0 6px 8px;
  background: rgba(255,255,255,0.03);
  border-radius: 6px;
  border: 1px solid rgba(255,255,255,0.08);
  border-left: 2px solid var(--accent-dim);
}
.edit-dice {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
  margin-bottom: 6px;
}
.edit-dice .die-chip {
  font-size: 14px;
  font-weight: 700;
  padding: 3px 10px;
  border-radius: 6px;
  border: 2px solid rgba(255,255,255,0.1);
  background: rgba(255,255,255,0.06);
  color: var(--text);
  cursor: pointer;
  transition: border-color 0.15s;
}
.edit-dice .die-chip:hover {
  border-color: var(--accent);
}
.edit-dice .add-chip {
  color: var(--accent);
  border-color: var(--accent-dim);
  font-size: 16px;
  font-weight: 400;
  padding: 3px 8px;
}
.edit-dice .add-chip:hover {
  border-color: var(--accent);
  background: rgba(64,136,212,0.1);
}
.edit-statement {
  font-size: 12px;
  padding: 5px 8px;
  width: 100%;
  box-sizing: border-box;
}
.edit-close {
  position: absolute;
  top: 4px;
  right: 4px;
  width: 22px;
  height: 22px;
  font-size: 14px;
  line-height: 1;
  padding: 0;
  background: transparent;
  color: var(--text-dim);
  border: none;
  border-radius: 50%;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
}
.edit-close:hover {
  background: rgba(255,255,255,0.08);
  color: var(--text);
}

.header-top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
}
.sheet-portrait {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  object-fit: cover;
  border: 1px solid rgba(255,255,255,0.12);
  flex-shrink: 0;
  order: 1;
}
.header-top h2 {
  flex: 1;
}
.sheet-settings-btn {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: transparent;
  border: 1px solid rgba(255,255,255,0.1);
  color: var(--text-dim);
  font-size: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  padding: 0;
  flex-shrink: 0;
  transition: all 0.2s;
}
.sheet-settings-btn:hover {
  background: var(--accent);
  color: #fff;
  border-color: var(--accent);
}

.header {
  margin-bottom: 16px;
}
.header h2 {
  font-size: 20px;
  font-weight: 700;
  margin-bottom: 4px;
}
.meta {
  display: flex;
  gap: 8px;
  font-size: 12px;
  color: var(--text-dim);
}
.universe {
  text-transform: uppercase;
  letter-spacing: 1px;
}
.razmerit {
  margin-top: 8px;
  font-size: 13px;
  color: var(--text-dim);
}
.razmerit-value {
  font-size: 24px;
  font-weight: 700;
  color: var(--accent);
}

.trait-sets {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.trait-set h4 {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 2px;
  color: var(--text-dim);
  margin-bottom: 6px;
  padding-bottom: 4px;
  border-bottom: 1px solid rgba(255,255,255,0.06);
}

.trait-row {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 8px;
  padding: 6px 8px;
  margin: 0 -8px;
  border-radius: 6px;
  font-size: 13px;
  cursor: pointer;
  transition: background 0.1s;
}
.trait-row:hover {
  background: rgba(255,255,255,0.04);
}
.trait-row.ego {
  border-left: 2px solid var(--accent);
  padding-left: 8px;
}

.trait-left {
  display: flex;
  flex-direction: column;
  gap: 2px;
  flex: 1;
  min-width: 0;
}

.trait-right {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 4px;
  flex-shrink: 0;
}

.trait-name {
  cursor: pointer;
  transition: color 0.15s;
  font-weight: 500;
}
.trait-name:hover {
  color: var(--accent);
}
.trait-name.disabled {
  cursor: default;
  opacity: 0.5;
}
.trait-name.disabled:hover {
  color: inherit;
}

.trait-statement {
  font-size: 10px;
  color: var(--text-dim);
  font-style: italic;
  line-height: 1.3;
}

.trait-die {
  font-weight: 700;
  font-size: 14px;
}
.die-d4  { color: #e88830; }
.die-d6  { color: #e0e0e0; }
.die-d8  { color: #d44040; }
.die-d10 { color: #4088d4; }
.die-d12 { color: #40b860; }

.polarity-badge {
  font-size: 10px;
  margin-left: 4px;
  opacity: 0.7;
}
.polarity-negative { color: #d44040; }
.polarity-positive { color: #40b860; }

.loading, .error, .empty {
  font-size: 13px;
  color: var(--text-dim);
  text-align: center;
  padding: 16px 0;
}
.error { color: var(--danger); }

.sfx-btn {
  font-size: 9px; text-transform: uppercase; letter-spacing: 1px;
  padding: 2px 8px; border-radius: 4px; cursor: pointer;
  background: var(--warn); color: #0a0a0f; font-weight: 700;
  border: none; transition: opacity 0.15s;
}
.sfx-btn:hover { opacity: 0.8; }
.sfx-btn:disabled, .sfx-btn.sfx-used { opacity: 0.3; cursor: default; }
.sfx-btn.sfx-active { background: var(--accent); color: #fff; opacity: 1; }
</style>
