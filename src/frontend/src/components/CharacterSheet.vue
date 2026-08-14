<template>
  <!-- Embedded: single root for attribute inheritance -->
  <div v-if="embedded" class="sheet-embedded">
    <div v-if="loading" class="loading">Loading…</div>
    <div v-else-if="error" class="error">{{ error }}</div>
    <template v-else-if="entity">
      <div class="header">
        <div class="header-top">
          <h2>{{ entity.name }}</h2>
          <video v-if="entity.sheetPortrait && isSheetVideo" :src="entity.sheetPortrait" class="sheet-portrait-video" autoplay loop muted playsinline />
          <img v-else-if="entity.sheetPortrait" :src="entity.sheetPortrait" class="sheet-portrait" />
          <div v-if="isForeignSheet" class="rel-widget">
            <template v-if="relationship">
              <span class="rel-desc" @click.stop="showRelEditor = true" :title="'Click to edit'">{{ relationship.description || 'associated' }}</span>
              <button class="rel-btn rel-del" @click.stop="removeRelationship" title="Remove relationship">✕</button>
              <button class="rel-btn rel-send" @click.stop="openBlueBookLetter" title="Send letter">✉</button>
            </template>
            <template v-else-if="showRelTypePicker">
              <div class="rel-type-picker" @click.stop>
                <select v-model="newRelType" class="rel-type-select">
                  <option v-for="rt in relationTypes" :key="rt.id" :value="rt.id">{{ rt.name }}</option>
                </select>
                <select v-model="newRelRating" class="rel-rating-select">
                  <option v-for="d in ['d4','d6','d8','d10','d12']" :key="d" :value="d">{{ d }}</option>
                </select>
                <input ref="relInput" v-model="relDescription" placeholder="Describe…" @keyup.enter="saveRatedRelationship" @keyup.escape="showRelTypePicker = false" />
                <button class="rel-btn rel-save" @click="saveRatedRelationship">✓</button>
                <button class="rel-btn rel-cancel" @click="showRelTypePicker = false">✕</button>
              </div>
            </template>
            <button v-else class="rel-btn rel-add" @click.stop="showRelTypePicker = true" title="Add rated relationship">+</button>
            <div v-if="showRelEditor" class="rel-editor" @click.stop>
              <input ref="relInput" v-model="relDescription" placeholder="Describe relationship…" @keyup.enter="saveRelationship" @keyup.escape="showRelEditor = false" />
              <button class="rel-btn rel-save" @click="saveRelationship">✓</button>
              <button class="rel-btn rel-cancel" @click="showRelEditor = false">✕</button>
            </div>
          </div>
          <div v-if="!gmMode" class="sheet-pills">
            <div v-if="ownsCharacter && !overrideEntityId">
              <button :class="['pill', { active: activeSheetView === 'traits' }]" @click="activeSheetView = 'traits'">🎲</button>
              <button :class="['pill', { active: activeSheetView === 'lifepath' }]" @click="activeSheetView = 'lifepath'">🛤️</button>
              <button :class="['pill', { active: activeSheetView === 'bluebook' }]" @click="activeSheetView = 'bluebook'">📘</button>
            </div>
            <button class="sheet-settings-btn" @click.stop="$emit('openSettings')" title="Player settings">↩</button>
          </div>
        </div>
        <div v-if="gmMode" class="meta">
          <span class="location">{{ locationName || entity.currentLocation || 'Unknown' }}</span>
          <span class="universe">{{ universeName || entity.currentUniverse }}</span>
        </div>
      </div>
      <BlueBook
        v-if="activeSheetView === 'bluebook'"
        :entity-id="overrideEntityId || entityId"
        ref="blueBookRef"
        :entity-name="entity?.name || ''"
        :visible="true"
        embedded
      />
      <LifePathWizard
        v-else-if="activeSheetView === 'lifepath'"
        :visible="activeSheetView === 'lifepath'"
        :entity-id="overrideEntityId || entityId"
        :universe="entity?.currentUniverse || 'earth'"
        embedded
        @close="activeSheetView = 'traits'"
        @updated="fetchEntity"
      />
      <template v-else>
        <div class="razmerit">
          <button v-if="!overrideEntityId" class="razmerit-btn" @click.stop="adjustRazmerit(-1)">−</button>
          <span class="razmerit-value">{{ entity.razmerit }}</span>
          razmerit
          <button v-if="!overrideEntityId" class="razmerit-btn" @click.stop="adjustRazmerit(1)">+</button>
        </div>
        <div class="sheet-scroll">
        <div v-if="traitSets.length && !showAddTrait" class="trait-sets">
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
                  <button v-if="!isForeignSheet && ownsCharacter && t.transferFlags?.teachable"
                    class="transfer-btn teach-btn" @click.stop="showTeachPicker(t)"
                    title="Teach this trait">🎓</button>
                  <button v-if="!isForeignSheet && ownsCharacter && t.transferFlags?.giftable"
                    class="transfer-btn gift-btn" @click.stop="giftTraitAction(t)"
                    title="Gift this trait">🎁</button>
                  <button v-if="isForeignSheet && t.transferFlags?.takable"
                    class="transfer-btn take-btn" @click.stop="takeTraitAction(t)"
                    title="Take this trait">🫳</button>
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
                <div v-if="t.possibleSfxIds?.length" class="edit-sfx">
                  <span class="edit-sfx-label">SFX</span>
                  <button v-for="sfxId in t.possibleSfxIds" :key="sfxId" class="sfx-chip" :class="{ assigned: editSfxIds.includes(sfxId) }" @click="toggleSfx(sfxId)">
                    {{ sfxId.replace('sfx-', '') }}
                  </button>
                </div>
                <input v-if="t.statement !== undefined" v-model="editStatement" class="edit-statement" placeholder="Statement…" @input="onStatementInput" />
                <div class="edit-actions">
                  <button class="edit-done-btn" @click="cancelEdit">Done</button>
                  <button class="edit-delete-btn" :class="{ counting: deleteCountdown > 0 && deletingTraitId === t.id }" @click="onDeleteClick(t)">
                    {{ deleteCountdown > 0 && deletingTraitId === t.id ? `Cancel (${deleteCountdown})` : 'Delete' }}
                  </button>
                </div>
              </div>
            </template>
            </div> <!-- .set-body -->
          </div>
        </div>
      <div v-else-if="!showAddTrait" class="empty">No traits configured</div>
      <button v-if="!overrideEntityId && !showAddTrait" class="add-trait-btn" @click="openAddTrait">+ Add Trait</button>
      <!-- 2-phase trait picker -->
      <div v-if="showAddTrait" class="trait-picker">
        <template v-if="addPhase === 'sets'">
          <h4>Pick a trait set</h4>
          <button v-for="ts in availableTraitSets" :key="ts.id" class="picker-item" @click="selectSet(ts)">{{ ts.name }}</button>
        </template>
        <template v-if="addPhase === 'traits'">
          <button class="picker-back" @click="addPhase = 'sets'">← {{ selectedTraitSet?.name }}</button>
          <button v-for="t in filteredTraits" :key="t.id" class="picker-item" @click="addTrait(t)">
            {{ t.name }}
            <span class="picker-die">{{ t.defaultDieType }}</span>
          </button>
          <div v-if="!filteredTraits.length" class="empty">{{ emptySetMessage }}</div>
        </template>
        <button class="picker-cancel" @click="showAddTrait = false">Cancel</button>
      </div>
      </div> <!-- .sheet-scroll -->
      </template>
    </template>
    <div v-else class="empty">No entity loaded</div>
  </div>

</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { useApi } from '../composables/useApi.js'
import DiePicker from './DiePicker.vue'
import BlueBook from './BlueBook.vue'
import LifePathWizard from './LifePathWizard.vue'

const props = defineProps({
  entityId: { type: String, required: true },
  universe: { type: String, default: 'earth' },
  phase: { type: String, default: 'adding' },
  embedded: { type: Boolean, default: false },
  gmMode: { type: Boolean, default: false },
  externalPoolSources: { type: Array, default: null },
  overrideEntityId: { type: String, default: null },
  viewerEntityId: { type: String, default: null },
  playerOwnedEntityIds: { type: Array, default: () => [] },
})

const emit = defineEmits(['addToPool', 'removeFromPool', 'splitDie', 'removeByTsId', 'sfxToggled', 'openSettings', 'sheetViewChange'])

function displayName(name) {
  return name
    .split('_')
    .map(w => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ')
}

const { loading, error, graphql, triggerSfx, spendResourceDie, recoverResourceDie } = useApi()
const entity = ref(null)
const traitSets = ref([])

// ── Relationship widget (foreign sheets only) ──────
const relationship = ref(null)
const showRelEditor = ref(false)
const relDescription = ref('')
const relInput = ref(null)
const blueBookRef = ref(null)

// Rated relationship creation
const showRelTypePicker = ref(false)
const newRelType = ref('trait-relation-trust')
const newRelRating = ref('d6')
const relationTypes = [
  { id: 'trait-relation-trust', name: 'Trust' },
  { id: 'trait-relation-debt', name: 'Debt' },
  { id: 'trait-relation-rivalry', name: 'Rivalry' },
  { id: 'trait-relation-loyalty', name: 'Loyalty' },
  { id: 'trait-relation-fear', name: 'Fear' },
  { id: 'trait-relation-love', name: 'Love' },
  { id: 'trait-relation-duty', name: 'Duty' },
]

const activeSheetView = ref('traits')  // 'traits' | 'lifepath' | 'bluebook'
watch(activeSheetView, (v) => emit('sheetViewChange', v))

const isForeignSheet = computed(() =>
  props.overrideEntityId && props.overrideEntityId !== props.viewerEntityId
)

const ownsCharacter = computed(() => {
  const id = props.overrideEntityId || props.entityId
  if (!props.playerOwnedEntityIds?.length) return false
  return props.playerOwnedEntityIds.includes(id)
})

const isSheetVideo = computed(() => entity.value?.sheetPortrait && /\.(webm|mp4)(\?|$)/i.test(entity.value.sheetPortrait))

// Resolved human-readable names
const locationName = ref('')
const universeName = ref('')

// Accordion state — user controls which sets are expanded
const expandedSets = ref(new Set(JSON.parse(localStorage.getItem('expandedSets') || '[]')))

function toggleSet(name) {
  const s = new Set(expandedSets.value)
  if (s.has(name)) {
    s.delete(name)  // close if already open
  } else {
    s.clear()
    s.add(name)     // open only this one
  }
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
const editSfxIds = ref([])
let longPressTimer = null

// ── Add trait picker ────────────────────────────
const showAddTrait = ref(false)
const addPhase = ref('sets')
const availableTraitSets = ref([])
const availableTraits = ref([])
const selectedTraitSet = ref(null)

const filteredTraits = computed(() => {
  if (!selectedTraitSet.value) return []
  const assigned = new Set(
    traitSets.value.flatMap(ts => ts.traits.map(t => t.traitId || t.id))
  )
  return availableTraits.value.filter(t =>
    t.traitsetId === selectedTraitSet.value.id && !assigned.has(t.id)
  )
})

const totalInSet = computed(() => {
  if (!selectedTraitSet.value) return 0
  return availableTraits.value.filter(t => t.traitsetId === selectedTraitSet.value.id).length
})

const emptySetMessage = computed(() => {
  if (!selectedTraitSet.value) return ''
  if (totalInSet.value === 0) return 'No traits available in this set'
  return 'All traits in this set are already assigned'
})

async function openAddTrait() {
  addPhase.value = 'sets'
  selectedTraitSet.value = null
  const [tsData, trData] = await Promise.all([
    graphql(`query($u: String!) { traitsetsByUniverse(universe: $u) { id name order limit entityTypes } }`, { u: props.universe }),
    graphql(`query($u: String!) { traitsByUniverse(universe: $u) { id name traitsetId defaultDieType defaultRatingType } }`, { u: props.universe }),
  ])
  const etype = entity.value?.type || ''
  if (tsData?.traitsetsByUniverse) {
    availableTraitSets.value = tsData.traitsetsByUniverse
      .filter(ts => !ts.entityTypes || ts.entityTypes.length === 0 || ts.entityTypes.includes(etype))
      .sort((a, b) => (a.order ?? 99) - (b.order ?? 99))
  }
  if (trData?.traitsByUniverse) {
    availableTraits.value = trData.traitsByUniverse
  }
  showAddTrait.value = true
}

function selectSet(ts) {
  selectedTraitSet.value = ts
  addPhase.value = 'traits'
}

async function addTrait(trait) {
  const result = await graphql(`mutation($eid: ID!, $input: TraitSettingInput!) {
    addTraitSetting(entityId: $eid, input: $input) { id name traitsetName }
  }`, {
    eid: props.entityId,
    input: {
      traitId: trait.id,
      traitsetId: selectedTraitSet.value.id,
      dice: [(trait.defaultDieType || 'd6').toUpperCase()],
      ratingType: (trait.defaultRatingType || 'STATIC').toUpperCase(),
    },
  })
  if (!result?.addTraitSetting) {
    console.error('addTrait failed:', error.value || 'unknown error')
    return
  }
  showAddTrait.value = false
  addPhase.value = 'sets'
  selectedTraitSet.value = null
  fetchEntity()
}

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
  if (t.ratingType === 'EMPTY') return ''
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
  return poolSources.value.includes(t.id)
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
  // sources is now [{ die, label, tsId }, ...] — track by tsId
  poolSources.value = sources.map(s => s.tsId).filter(Boolean)

  // Auto-expand next set when current hits limit
  const sets = traitSets.value
  for (let i = 0; i < sets.length; i++) {
    if (expandedSets.value.has(sets[i].name)) {
      const count = sets[i].traits.filter(t => poolSources.value.includes(t.id)).length
      console.log('setPoolSources check:', { set: sets[i].name, count, limit: sets[i].limit, willHit: count >= sets[i].limit })
      if (count >= sets[i].limit) {
        const next = sets[i + 1]
        if (next) {
          console.log('auto-expanding:', next.name)
          expandedSets.value = new Set([next.name])
          localStorage.setItem('expandedSets', JSON.stringify([next.name]))
        }
      }
      break
    }
  }

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
        if (t.id === tsId && poolSources.value.includes(t.id)) {
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
  if (sfxId === 'sfx-spray-n-pray' && !poolSources.value.includes('shooting')) return true
  return false
}

function resetSfxCounts() {
  sfxActivations.value = {}
  spentResources.value = {}
}

const QUERY = `
  query($id: ID!) {
    entity(id: $id) {
      type
      name
      razmerit
      currentUniverse
      currentLocation
      backgroundImage
      sheetPortrait
      traitSettings {
        id
        traitId
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
        possibleSfxIds
        transferFlags
      }
    }
  }
`

async function fetchEntity() {
  const id = props.overrideEntityId || props.entityId
  console.log('[diag] CharacterSheet QUERY has sheetPortrait:', QUERY.includes('sheetPortrait'))
  const data = await graphql(QUERY, { id })
  console.log('[diag] CharacterSheet response — sheetPortrait:', data?.entity?.sheetPortrait, 'backgroundImage:', data?.entity?.backgroundImage)
  if (data?.entity) {
    entity.value = data.entity
    resolveNames(data.entity)

    // Group trait settings by traitset, filter by universe
    const sets = {}
    for (const ts of data.entity.traitSettings || []) {
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
  if (deleteCountdown.value > 0) {
    clearInterval(deleteTimer)
    deleteCountdown.value = 0
    const targetId = deletingTraitId.value
    deletingTraitId.value = null
    deleteTrait({ id: targetId })
  }
  editingTraitId.value = t.id
  editDice.value = (t.dice && t.dice.length ? [...t.dice] : [t.dieType || 'd6']).map(d => d.toLowerCase())
  editStatement.value = t.statement || ''
  editSfxIds.value = [...(t.sfxIds || [])]
  showDiePicker.value = false
}

function cancelEdit() {
  if (deleteCountdown.value > 0) {
    clearInterval(deleteTimer)
    deleteCountdown.value = 0
    const targetId = deletingTraitId.value
    deletingTraitId.value = null
    deleteTrait({ id: targetId })
  } else {
    editingTraitId.value = null
  }
}

const deleteCountdown = ref(0)
const deletingTraitId = ref(null)
let deleteTimer = null

function onDeleteClick(t) {
  if (deleteCountdown.value > 0) {
    clearInterval(deleteTimer)
    deleteCountdown.value = 0
    deletingTraitId.value = null
    return
  }
  deleteCountdown.value = 3
  deletingTraitId.value = t.id
  deleteTimer = setInterval(() => {
    deleteCountdown.value--
    if (deleteCountdown.value <= 0) {
      clearInterval(deleteTimer)
      deletingTraitId.value = null
      deleteTrait(t)
    }
  }, 1000)
}

async function adjustRazmerit(delta) {
  const mutation = delta < 0 ? 'spendRazmerit' : 'earnRazmerit'
  const resp = await fetch('/api/v1/graphql', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      query: 'mutation($eid: ID!, $amt: Int!) { ' + mutation + '(entityId: $eid, amount: $amt) { fromBalance } }',
      variables: { eid: props.entityId, amt: Math.abs(delta) },
    }),
  })
  const data = await resp.json()
  const balance = data?.data?.[mutation]?.fromBalance
  if (balance != null) entity.value.razmerit = balance
}

async function deleteTrait(t) {
  await fetch('/api/v1/graphql', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query: `mutation($id: ID!) { removeTraitSetting(id: $id) }`, variables: { id: t.id } }),
  })
  editingTraitId.value = null
  // Remove from local traitSets — no full re-render
  for (const ts of traitSets.value) {
    const idx = ts.traits.findIndex(tr => tr.id === t.id)
    if (idx !== -1) {
      ts.traits.splice(idx, 1)
      if (ts.traits.length === 0) {
        traitSets.value = traitSets.value.filter(s => s.name !== ts.name)
      }
      break
    }
  }
}

async function doSave() {
  if (!editingTraitId.value) return
  const newDice = editDice.value.map(d => d.toUpperCase())
  const query = `mutation($id: ID!, $dice: [DieType!], $statement: String, $sfxIds: [ID!]) {
    updateTraitSetting(id: $id, input: { dice: $dice, statement: $statement, sfxIds: $sfxIds }) { id }
  }`
  await fetch('/api/v1/graphql', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      query,
      variables: {
        id: editingTraitId.value,
        dice: newDice,
        statement: editStatement.value ?? null,
        sfxIds: editSfxIds.value,
      },
    }),
  })
  // Patch local data — no full re-render
  for (const ts of traitSets.value) {
    const t = ts.traits.find(t => t.id === editingTraitId.value)
    if (t) {
      t.dice = newDice
      t.rating = null  // force fallback to dice display
      t.sfxIds = [...editSfxIds.value]
      t.statement = editStatement.value
      break
    }
  }
}

function toggleSfx(sfxId) {
  const idx = editSfxIds.value.indexOf(sfxId)
  if (idx === -1) editSfxIds.value.push(sfxId)
  else editSfxIds.value.splice(idx, 1)
  doSave()
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

onMounted(() => {
  console.log('[diag] CharacterSheet mounted', { entityId: props.entityId, universe: props.universe, embedded: props.embedded })
  document.addEventListener('keydown', onKeydown)
})
onUnmounted(() => document.removeEventListener('keydown', onKeydown))

onMounted(() => {
  console.log('[diag] CharacterSheet fetchEntity mounted', { entityId: props.entityId })
  fetchEntity()
})
watch(() => props.entityId, fetchEntity)
watch(() => props.universe, fetchEntity)
watch(() => props.overrideEntityId, fetchEntity)

// ── Relationship fetch ─────────────────────────────
async function fetchRelationship() {
  if (!props.viewerEntityId || !props.overrideEntityId) {
    relationship.value = null
    return
  }
  const query = `
    query($viewer: ID!, $target: ID!) {
      relationship(fromEntityId: $viewer, toEntityId: $target) {
        description
      }
    }
  `
  const data = await graphql(query, {
    viewer: props.viewerEntityId,
    target: props.overrideEntityId,
  })
  relationship.value = data?.relationship || null
}

async function saveRelationship() {
  if (!props.viewerEntityId || !props.overrideEntityId) return
  const query = `
    mutation($from: ID!, $to: ID!, $desc: String!) {
      createRelationship(input: { fromEntityId: $from, toEntityId: $to, description: $desc }) {
        description
      }
    }
  `
  await graphql(query, {
    from: props.viewerEntityId,
    to: props.overrideEntityId,
    desc: relDescription.value,
  })
  showRelEditor.value = false
  await fetchRelationship()
}

async function createImmediateRelationship() {
  if (!props.viewerEntityId || !props.overrideEntityId) return
  const query = `
    mutation($from: ID!, $to: ID!) {
      createRelationship(input: { fromEntityId: $from, toEntityId: $to }) {
        description
      }
    }
  `
  await graphql(query, {
    from: props.viewerEntityId,
    to: props.overrideEntityId,
  })
  await fetchRelationship()
}

async function saveRatedRelationship() {
  if (!props.viewerEntityId || !props.overrideEntityId) return
  const dmap = { d4: 'D4', d6: 'D6', d8: 'D8', d10: 'D10', d12: 'D12' }
  const query = `
    mutation($from: ID!, $to: ID!, $relType: String!, $traitId: ID!, $die: DieType!) {
      createRelationship(input: { fromEntityId: $from, toEntityId: $to, description: $desc }) { description }
      addRelationshipTrait(fromEntityId: $from, toEntityId: $to, relType: $relType, traitId: $traitId, die: $die) { id dice }
    }
  `
  try {
    await graphql(query, {
      from: props.viewerEntityId,
      to: props.overrideEntityId,
      relType: 'relation',
      traitId: newRelType.value,
      die: dmap[newRelRating.value],
      desc: relDescription.value || '',
    })
  } catch (e) {
    console.error('saveRatedRelationship:', e)
  }
  showRelTypePicker.value = false
  relDescription.value = ''
  await fetchRelationship()
}

function openBlueBookLetter() {
  activeSheetView.value = 'bluebook'
  nextTick(() => {
    blueBookRef.value?.openCompose('new', {
      id: props.overrideEntityId || props.entityId,
      name: entity.value?.name || ''
    })
  })
}

async function removeRelationship() {
  if (!props.viewerEntityId || !props.overrideEntityId) return
  const query = `
    mutation($from: ID!, $to: ID!) {
      deleteRelationship(input: { fromEntityId: $from, toEntityId: $to })
    }
  `
  await graphql(query, {
    from: props.viewerEntityId,
    to: props.overrideEntityId,
  })
  relationship.value = null
  showRelEditor.value = false
}

// ── Trait Transfer ─────────────────────────────────

const showTransferPicker = ref(false)
const transferTargetId = ref('')
const transferTrait = ref(null)
const transferMode = ref('') // 'teach' | 'gift' | 'take'
const relatedForTransfer = ref([])

async function loadRelatedForTransfer() {
  const id = props.overrideEntityId || props.entityId
  const query = `
    query($id: ID!, $q: String!) {
      relatedEntities(entityId: $id, query: $q) { id name }
    }
  `
  const data = await graphql(query, { id, q: '' })
  relatedForTransfer.value = data?.relatedEntities || []
}

function showTeachPicker(t) {
  transferTrait.value = t
  transferMode.value = 'teach'
  transferTargetId.value = ''
  loadRelatedForTransfer()
  showTransferPicker.value = true
}

async function giftTraitAction(t) {
  const targetId = prompt('Enter recipient entity ID to gift this trait to:')
  if (!targetId || targetId === props.entityId) return
  const query = `
    mutation($giver: ID!, $recipient: ID!, $tsId: ID!) {
      giftTrait(giverId: $giver, recipientId: $recipient, traitSettingId: $tsId) {
        transferredTraitId
      }
    }
  `
  try {
    await graphql(query, {
      giver: props.entityId,
      recipient: targetId,
      tsId: t.id,
    })
    await fetchEntity()
  } catch (e) {
    console.error('giftTrait failed:', e)
    alert('Gift failed. Both characters must be in the same location.')
  }
}

async function takeTraitAction(t) {
  const method = prompt('Take method? (stealth, combat, social, technical)', 'stealth') || 'stealth'
  const query = `
    mutation($taker: ID!, $victim: ID!, $tsId: ID!, $method: String!) {
      takeTrait(takerId: $taker, victimId: $victim, traitSettingId: $tsId, method: $method) {
        success contestSummary transferredTraitId
      }
    }
  `
  try {
    const data = await graphql(query, {
      taker: props.viewerEntityId,
      victim: props.overrideEntityId,
      tsId: t.id,
      method,
    })
    const result = data?.takeTrait
    if (result?.success) {
      alert(`Taken! ${result.contestSummary}`)
      await fetchEntity()
    } else {
      alert(`Failed! ${result?.contestSummary}`)
    }
  } catch (e) {
    console.error('takeTrait failed:', e)
  }
}

async function confirmTransfer() {
  if (!transferTargetId.value || !transferTrait.value) return
  if (transferMode.value === 'teach') {
    const query = `
      mutation($teacher: ID!, $student: ID!, $tsId: ID!) {
        teachTrait(teacherId: $teacher, studentId: $student, traitSettingId: $tsId) {
          studentTraitSettingId razmeritCost
        }
      }
    `
    try {
      await graphql(query, {
        teacher: props.entityId,
        student: transferTargetId.value,
        tsId: transferTrait.value.id,
      })
      await fetchEntity()
    } catch (e) {
      console.error('teachTrait failed:', e)
      alert('Teach failed. Both characters must be in the same location.')
    }
  }
  showTransferPicker.value = false
  transferTrait.value = null
}

watch(() => props.overrideEntityId, () => {
  if (isForeignSheet.value) fetchRelationship()
  if (!ownsCharacter.value && activeSheetView.value === 'bluebook') activeSheetView.value = 'traits'
})
watch(() => props.viewerEntityId, () => {
  if (isForeignSheet.value) fetchRelationship()
})

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
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.sheet-scroll {
  flex: 1;
  overflow-y: auto; overflow-x: hidden;
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
  padding: 8px 8px 8px 12px;
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
.edit-sfx {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-bottom: 6px;
  align-items: center;
}
.edit-sfx-label {
  font-size: 10px;
  color: var(--text-dim);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-right: 4px;
}
.sfx-chip {
  font-size: 10px;
  padding: 3px 8px;
  border-radius: 4px;
  border: 1px solid rgba(255,255,255,0.1);
  background: rgba(255,255,255,0.04);
  color: var(--text-dim);
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s, color 0.15s;
}
.sfx-chip:hover {
  border-color: rgba(255,255,255,0.2);
  color: var(--text);
}
.sfx-chip.assigned {
  background: var(--accent-dim);
  border-color: var(--accent);
  color: var(--accent);
}

.edit-statement {
  font-size: 12px;
  padding: 5px 8px;
  width: 100%;
  box-sizing: border-box;
}
.edit-actions {
  display: flex;
  gap: 6px;
  margin-top: 6px;
}
.edit-done-btn {
  flex: 1;
  font-size: 12px;
  padding: 6px;
  background: var(--accent);
  color: #fff;
  border: none;
  border-radius: 6px;
  cursor: pointer;
}
.edit-delete-btn {
  flex: 1;
  font-size: 12px;
  padding: 6px;
  background: rgba(212,64,64,0.12);
  color: var(--danger);
  border: 1px solid rgba(212,64,64,0.25);
  border-radius: 6px;
  cursor: pointer;
  transition: background 0.15s;
}
.edit-delete-btn:hover {
  background: rgba(212,64,64,0.25);
}
.edit-delete-btn.counting {
  background: rgba(212,64,64,0.35);
  color: #fff;
  animation: deletePulse 1s ease-in-out infinite;
}
@keyframes deletePulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.7; }
}

.add-trait-btn {
  width: 100%;
  padding: 8px;
  margin-top: 8px;
  font-size: 13px;
  background: transparent;
  color: var(--text-dim);
  border: 1px dashed rgba(255,255,255,0.12);
  border-radius: 6px;
  cursor: pointer;
  transition: border-color 0.15s, color 0.15s;
}
.add-trait-btn:hover {
  border-color: var(--accent-dim);
  color: var(--accent);
}

.trait-picker {
  margin-top: 8px;
  padding: 8px 0;
  max-height: calc(100vh - 320px);
  overflow-y: auto; overflow-x: hidden;
}
.trait-picker h4 {
  font-size: 12px;
  color: var(--text-dim);
  text-transform: uppercase;
  letter-spacing: 1px;
  margin-bottom: 6px;
}
.picker-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
  padding: 6px 10px;
  font-size: 13px;
  background: rgba(255,255,255,0.04);
  border: 1px solid rgba(255,255,255,0.06);
  border-radius: 6px;
  color: var(--text);
  cursor: pointer;
  margin-bottom: 4px;
  transition: background 0.15s, border-color 0.15s;
}
.picker-item:hover {
  background: rgba(255,255,255,0.08);
  border-color: rgba(255,255,255,0.12);
}
.picker-die {
  font-weight: 700;
  font-size: 12px;
  color: var(--text-dim);
}
.picker-back {
  font-size: 12px;
  padding: 4px 0;
  margin-bottom: 6px;
  background: none;
  border: none;
  color: var(--accent);
  cursor: pointer;
}
.picker-cancel {
  width: 100%;
  margin-top: 6px;
  padding: 6px;
  font-size: 12px;
  background: transparent;
  color: var(--text-dim);
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: 6px;
  cursor: pointer;
}
.picker-cancel:hover {
  color: var(--text);
  border-color: rgba(255,255,255,0.15);
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
.sheet-portrait-video {
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
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 8px;
  font-size: 13px;
  color: var(--text-dim);
}
.razmerit-value {
  font-size: 24px;
  font-weight: 700;
  color: var(--accent);
}
.razmerit-btn {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  border: 1px solid rgba(255,255,255,0.12);
  background: transparent;
  color: var(--text-dim);
  font-size: 18px;
  line-height: 1;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  transition: border-color 0.15s, color 0.15s;
}
.razmerit-btn:hover {
  border-color: var(--accent-dim);
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

/* ── Relationship widget ──────────────────────── */
.rel-widget {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  margin-left: 4px;
  position: relative;
  flex-shrink: 0;
}
.rel-desc {
  font-size: 11px;
  color: var(--text-dim);
  font-style: italic;
  cursor: pointer;
  padding: 2px 6px;
  border-radius: 4px;
  transition: color 0.15s, background 0.15s;
}
.rel-desc:hover {
  color: var(--text);
  background: var(--bg-hover);
}
.rel-btn {
  font-size: 12px;
  width: 22px;
  height: 22px;
  border: none;
  border-radius: 50%;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  line-height: 1;
  transition: background 0.15s, color 0.15s;
}
.rel-add {
  background: var(--bg-hover);
  color: var(--text-dim);
}
.rel-add:hover {
  background: var(--accent);
  color: #fff;
}
.rel-del {
  background: transparent;
  color: var(--text-dim);
  font-size: 10px;
}
.rel-del:hover {
  background: var(--danger);
  color: #fff;
}
.rel-send {
  background: transparent;
  color: var(--accent);
  font-size: 12px;
}
.rel-send:hover {
  background: var(--accent);
  color: #fff;
}
.rel-editor {
  position: absolute;
  top: 100%;
  left: 0;
  z-index: 10;
  display: flex;
  gap: 4px;
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 6px;
  box-shadow: 0 4px 12px rgba(0,0,0,0.4);
}
.rel-editor input {
  width: 180px;
  padding: 4px 8px;
  border: 1px solid var(--border);
  border-radius: 4px;
  background: var(--bg-input);
  color: var(--text);
  font-size: 12px;
  font-style: italic;
  outline: none;
}
.rel-editor input:focus {
  border-color: var(--accent);
}
.rel-save {
  background: var(--accent);
  color: #fff;
}
.rel-save:hover {
  opacity: 0.8;
}
.rel-cancel {
  background: var(--bg-hover);
  color: var(--text-dim);
}
.rel-cancel:hover {
  color: var(--text);
}
.sheet-pills { display: flex; gap: 0; margin-bottom: 10px; border-radius: 20px; overflow: hidden; border: 1px solid rgba(255,255,255,0.08); }
.pill { padding: 5px 14px; font-size: 11px; border: none; cursor: pointer; background: rgba(255,255,255,0.02); color: var(--text-dim); transition: background 0.15s, color 0.15s; }
.pill + .pill { border-left: 1px solid rgba(255,255,255,0.06); }
.pill:hover { background: rgba(255,255,255,0.05); color: var(--text); }
.pill.active { background: var(--accent-dim); color: var(--text); font-weight: 600; }
</style>
