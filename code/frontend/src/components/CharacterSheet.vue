<template>
  <!-- Embedded: single root for attribute inheritance -->
  <div v-if="embedded" class="sheet-embedded">
    <div v-if="loading" class="loading">Loading…</div>
    <div v-else-if="error" class="error">{{ error }}</div>
    <template v-else-if="entity">
      <div class="header">
        <h2>{{ entity.name }}</h2>
        <div class="meta">
          <span class="location">{{ entity.currentLocation || 'Unknown' }}</span>
          <span class="universe">{{ entity.currentUniverse }}</span>
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
          </h4>
          <div v-show="expandedSets.has(ts.name)" class="set-body">
            <div v-for="t in ts.traits" :key="t.name" class="trait-row" :class="{ ego: t.ego }" @click="onTraitClick(t)">
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
          </div>
        </div>
      </div>
      <div v-else class="empty">No traits configured</div>
    </template>
    <div v-else class="empty">No entity loaded</div>
  </div>

  <!-- Standalone: full panel with toggle -->
  <div v-else class="character-sheet panel" :class="{ open }">
    <button class="toggle" @click="open = !open">
      {{ open ? '×' : '☰' }}
    </button>
    <div v-if="open" class="sheet-content">
      <div v-if="loading" class="loading">Loading…</div>
      <div v-else-if="error" class="error">{{ error }}</div>
      <template v-else-if="entity">
        <div class="header">
          <h2>{{ entity.name }}</h2>
          <div class="meta">
            <span class="location">{{ entity.currentLocation || 'Unknown' }}</span>
            <span class="universe">{{ entity.currentUniverse }}</span>
          </div>
          <div class="razmerit">
            <span class="razmerit-value">{{ entity.razmerit }}</span> razmerit
          </div>
        </div>
        <div v-if="traitSets.length" class="trait-sets">
          <div v-for="ts in traitSets" :key="ts.name" class="trait-set">
            <h4>{{ ts.name }}</h4>
            <div v-for="t in ts.traits" :key="t.name" class="trait-row" :class="{ ego: t.ego }" @click="onTraitClick(t)">
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
          </div>
        </div>
        <div v-else class="empty">No traits configured</div>
      </template>
      <div v-else class="empty">No entity loaded</div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, onMounted } from 'vue'
import { useApi } from '../composables/useApi.js'

const props = defineProps({
  entityId: { type: String, required: true },
  universe: { type: String, default: 'earth' },
  phase: { type: String, default: 'adding' },
  embedded: { type: Boolean, default: false },
})

const emit = defineEmits(['addToPool', 'removeFromPool', 'splitDie', 'removeByTsId', 'sfxToggled'])

function displayName(name) {
  return name
    .split('_')
    .map(w => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ')
}

const { loading, error, graphql, triggerSfx, spendResourceDie, recoverResourceDie } = useApi()
const open = ref(false)
const entity = ref(null)
const traitSets = ref([])

// Accordion state — all collapsed by default
const expandedSets = ref(new Set())

function toggleSet(name) {
  const s = new Set(expandedSets.value)
  if (s.has(name)) s.delete(name)
  else s.add(name)
  expandedSets.value = s
}

// SFX usage tracking — reset per dice pool cycle
const sfxActivations = ref({})
const SFX_PHASES = {
  'sfx-hinder': ['adding'],
  'sfx-spray-n-pray': ['adding'],
}
const poolSources = ref(new Set())

// Track resource trait dice that have been spent into the pool
// { tsId: dieType } — cleared when the die is removed from the pool
const spentResources = ref({})

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

function sfxAllowedInPhase(sfxId) {
  const allowed = SFX_PHASES[sfxId] || ['adding']
  return allowed.includes(props.phase)
}

// Pool state tracking — called by DiceRoller via App
function setPoolSources(sources) {
  poolSources.value = new Set(sources)

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
        if (t.id === tsId && poolSources.value.has(displayName(t.name))) {
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

function closeSheet() {
  open.value = false
}

defineExpose({ resetSfxCounts, setPoolSources, fetchEntity, closeSheet })

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
      }
    }
  }
`

async function fetchEntity() {
  const data = await graphql(QUERY, { id: props.entityId })
  if (data?.entity) {
    entity.value = data.entity

    // Group trait settings by traitset, filter by universe
    const sets = {}
    for (const ts of data.entity.traitSettings || []) {
      // Show if ego, or if trait's universe matches selected universe
      if (!ts.ego && ts.universe !== props.universe) continue
      const key = ts.traitsetName || 'Other'
      if (!sets[key]) sets[key] = []
      sets[key].push(ts)
    }
    traitSets.value = Object.entries(sets).map(([name, traits]) => ({ name, traits }))
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

onMounted(fetchEntity)
watch(() => props.entityId, fetchEntity)
watch(() => props.universe, fetchEntity)
</script>

<style scoped>
.character-sheet {
  position: fixed;
  top: env(safe-area-inset-top, 16px);
  right: 12px;
  z-index: 20;
  width: 48px;
  max-width: 48px;
  height: 48px;
  transition: width 0.3s ease, max-width 0.3s ease, height 0.3s ease, padding 0.3s ease;
  overflow: hidden;
  padding: 8px;
}

.character-sheet.open {
  width: 320px;
  max-width: calc(100vw - 80px);
  height: auto;
  max-height: calc(100vh - 120px - env(safe-area-inset-top, 0px) - env(safe-area-inset-bottom, 0px));
  overflow-y: auto;
  padding: 16px;
}

.toggle {
  position: absolute;
  top: 6px;
  right: 6px;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  padding: 0;
  z-index: 1;
}

.sheet-content {
  margin-top: 24px;
}

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
