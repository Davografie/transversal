<template>
  <!-- Embedded: single root for attribute inheritance -->
  <div v-if="embedded" class="sheet-embedded">
    <div v-if="loading" class="loading">Loading…</div>
    <div v-else-if="error" class="error">{{ error }}</div>
    <template v-else-if="entity">
      <div class="header">
        <div class="header-top">
          <h2>{{ activeProjection?.name || entity.name }}</h2>
          <div class="razmerit-anchor">
            <button class="razmerit-chip" :title="showRazmeritWidget ? 'Close' : 'Adjust razmerit'" @click.stop="showRazmeritWidget = !showRazmeritWidget">
              ⚡{{ entity.razmerit }}
            </button>
            <div v-if="showRazmeritWidget" class="razmerit-popover" @click.stop>
              <button v-if="!overrideEntityId" class="razmerit-btn" @click.stop="adjustRazmerit(-1)">−</button>
              <input
                v-if="editingRazmerit"
                ref="razmeritInput"
                v-model="razmeritInputValue"
                class="razmerit-input"
                type="number"
                inputmode="numeric"
                @keyup.enter="commitRazmerit"
                @keyup.escape="editingRazmerit = false"
                @blur="commitRazmerit"
              />
              <span
                v-else
                class="razmerit-value"
                :class="{ editable: !overrideEntityId }"
                @click="!overrideEntityId && startRazmeritEdit()"
              >{{ entity.razmerit }}</span>
              <button v-if="!overrideEntityId" class="razmerit-btn" @click.stop="adjustRazmerit(1)">+</button>
            </div>
          </div>
          <MediaImage v-if="sheetPortrait" :src="sheetPortrait" class="sheet-portrait" />
        </div>
        <div class="header-controls">
          <div v-if="isForeignSheet" class="rel-widget">
            <template v-if="relationship">
              <span class="rel-desc" @click.stop="showRelEditor = true" :title="'Click to edit'">{{ relationship.description || 'associated' }}</span>
              <button class="rel-btn rel-del" @click.stop="removeRelationship" title="Remove relationship">✕</button>
              <button class="rel-btn rel-send" @click.stop="openBlueBookLetter" title="Send letter">✉</button>
            </template>
            <div v-if="showRelEditor" class="rel-editor" @click.stop>
              <input ref="relInput" v-model="relDescription" placeholder="Describe relationship…" @keyup.enter="saveRelationship" @keyup.escape="showRelEditor = false" />
              <button class="rel-btn rel-save" @click="saveRelationship">✓</button>
              <button class="rel-btn rel-cancel" @click="showRelEditor = false">✕</button>
            </div>
          </div>
          <div class="sheet-pills">
            <div v-if="gmMode || !overrideEntityId">
              <button :class="['pill', { active: activeSheetView === 'profile' }]" @click="activeSheetView = 'profile'">👤</button>
              <button :class="['pill', { active: activeSheetView === 'traits' }]" @click="goToTraitSets">🎲</button>
              <button v-if="gmMode" :class="['pill', { active: showAllTraits }]" :title="showAllTraits ? 'Showing all traits' : 'Show all traits'" @click="showAllTraits = !showAllTraits">🌍</button>
              <button :class="['pill', { active: activeSheetView === 'bluebook' }]" @click="activeSheetView = 'bluebook'">📘</button>
              <button :class="['pill', { active: activeSheetView === 'lifepath' }]" @click="activeSheetView = 'lifepath'">🛤️</button>
            </div>
            <button v-if="!gmMode && !isForeignSheet" class="sheet-settings-btn" @click.stop="$emit('openSettings')" title="Player settings">↩</button>
            <button v-if="isForeignSheet && !relationship" class="sheet-settings-btn" @click.stop="createImmediateRelationship()" title="Add relationship">+</button>
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
        :viewer-id="viewerEntityId || entityId"
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
        <div class="sheet-scroll">
        <!-- Full-panel trait edit -->
        <div v-if="editingTrait && !showAddTrait" class="trait-edit-panel">
          <button class="set-back" @click="cancelEdit">← Back</button>
          <h4 class="edit-title">{{ displayName(editingTrait.name) }}</h4>

          <div class="edit-field">
            <span class="edit-label">Rating</span>
            <div class="edit-rating-type">
              <button
                v-for="rt in RATING_TYPES"
                :key="rt.id"
                type="button"
                class="rating-type-btn"
                :class="{ active: editRatingType === rt.id }"
                @click="setRatingType(rt.id)"
              >{{ rt.label }}</button>
            </div>
          </div>

          <div class="edit-field">
            <span class="edit-label">Dice</span>
            <div class="edit-dice">
              <button v-for="(d, i) in editDice" :key="i" class="die-chip die-chip-icon" :title="`Change ${d}`" @click="pickIdx = i; showDiePicker = true">
                <DieIcon :die="d" />
              </button>
              <button class="die-chip add-chip" @click="pickIdx = editDice.length; showDiePicker = true">+</button>
            </div>
            <div v-if="editRatingType === 'RESOURCE' && (editingTrait.spentDice || []).length" class="edit-spent-dice">
              <span class="edit-spent-label">Recoverable</span>
              <button
                v-for="(die, i) in editingTrait.spentDice"
                :key="'spent' + i"
                class="die-chip ghost-chip die-chip-icon"
                :title="`Recover one ${die.toLowerCase()}`"
                @click="recoverSpentDie(die)"
              ><DieIcon :die="die.toLowerCase()" /></button>
            </div>
          </div>

          <DiePicker v-if="showDiePicker" v-model="pickedDie" @update:model-value="onDiePicked" />

          <div v-if="editingTrait.possibleSfxIds?.length" class="edit-field">
            <span class="edit-label">SFX</span>
            <div class="edit-sfx">
              <button v-for="sfxId in editingTrait.possibleSfxIds" :key="sfxId" class="sfx-chip" :class="{ assigned: editSfxIds.includes(sfxId) }" @click="toggleSfx(sfxId)">
                {{ sfxId.replace('sfx-', '') }}
              </button>
            </div>
          </div>

          <div v-if="editingTrait.statement !== undefined" class="edit-field">
            <span class="edit-label">Statement</span>
            <input v-model="editStatement" class="edit-statement" placeholder="Statement…" @input="onStatementInput" @blur="splitStatement" />
          </div>

          <div v-if="editingTrait.notes !== undefined || editNotes" class="edit-field">
            <span class="edit-label">Notes</span>
            <textarea v-model="editNotes" class="edit-notes" placeholder="Notes…" @input="onStatementInput"></textarea>
          </div>

          <div class="edit-field">
            <span class="edit-label">Type</span>
            <div class="edit-flags">
              <button type="button" class="ego-toggle" :class="{ 'is-ego': editIsEgo }" @click="toggleEgo">{{ editIsEgo ? 'ego' : 'morph' }}</button>
              <button type="button" class="polarity-toggle" :class="{ 'is-positive': editPolarity === 'POSITIVE' }" @click="togglePolarity">
                {{ editPolarity === 'POSITIVE' ? 'positive' : 'negative' }}
              </button>
            </div>
            <div v-if="!editIsEgo" class="edit-projection">
              <span class="edit-projection-label">on</span>
              <button type="button" class="projection-chip" @click="toggleProjectionPicker">{{ editProjectionName }}</button>
              <div v-if="showProjectionPicker" class="projection-dropdown">
                <button
                  v-for="p in editProjectionOptions"
                  :key="p.id"
                  type="button"
                  class="projection-option"
                  :class="{ selected: p.id === editProjectionId }"
                  @click="selectProjection(p)"
                >{{ p.name || universeDisplay(p.originUniverse) }}</button>
              </div>
            </div>
          </div>

          <div class="edit-actions">
            <button class="edit-done-btn" @click="cancelEdit">Done</button>
            <button class="edit-delete-btn" :class="{ counting: deleteCountdown > 0 && deletingTraitId === editingTrait.id }" @click="onDeleteClick(editingTrait)">
              {{ deleteCountdown > 0 && deletingTraitId === editingTrait.id ? `Cancel (${deleteCountdown})` : 'Delete' }}
            </button>
          </div>
        </div>

        <!-- Traits tab: trait-set list -->
        <div v-else-if="activeSheetView === 'traits' && !activeSetName && traitSets.length && !showAddTrait" class="trait-sets">
          <div v-for="ts in traitSets" :key="ts.name" class="trait-set">
            <h4 @click="openSet(ts.name)" class="set-header">
              <span class="set-name">{{ ts.name }}</span>
              <span v-if="ts.limit" class="limit-dots">
                <span v-for="i in ts.limit" :key="i" class="limit-dot" :class="{ filled: i <= inPoolCount(ts) }">{{ i <= inPoolCount(ts) ? '●' : '○' }}</span>
              </span>
            </h4>
          </div>
        </div>

        <!-- Set detail (traits) or profile: flat trait list -->
        <div v-else-if="currentTraits.length && !showAddTrait" class="trait-list" :class="{ 'trait-list-wrap': activeSheetView === 'profile' }">
          <h4 v-if="activeSheetView === 'traits'" class="trait-list-title" @click="closeSet" title="Back to trait sets">{{ activeSetName }}</h4>
            <template v-for="t in currentTraits" :key="t.id">
              <div v-if="isKnown(t)" class="trait-row" :class="{ morph: t.ego === false, 'in-pool': isInPool(t), offered: isOffered(t), 'limit-reached': currentSetReachedLimit && !isInPool(t), negative: t.polarity === 'NEGATIVE' }" @click="onTraitClick(t)" @contextmenu.prevent="startEdit(t)" @touchstart="onTouchStart(t)" @touchend="onTouchEnd" @touchmove="onTouchEnd">
                <div class="trait-left">
                  <span class="trait-name" :class="{ disabled: phase !== 'adding' || isResourceDepleted(t) }">{{ displayName(t.name) }}</span>
                  <span v-if="t.statement" class="trait-statement">{{ t.statement }}</span>
                  <span v-if="t.notes" class="trait-notes">{{ t.notes }}</span>
                  <div v-if="t.sfxIds?.length" class="sfx-cards">
                    <div
                      v-for="sfxId in t.sfxIds"
                      :key="sfxId"
                      class="sfx-card"
                      :class="{ 'sfx-active': sfxActive(sfxId), 'sfx-used': sfxUsed(sfxId) && !sfxActive(sfxId) }"
                      :title="sfxActive(sfxId) ? `Deactivate ${sfxName(sfxId)}` : `Activate ${sfxName(sfxId)}`"
                      @click.stop.prevent="sfxAllowedInPhase(sfxId) && activateSfx(sfxId)"
                    >
                      <span class="sfx-card-name">{{ sfxName(sfxId) }}</span>
                      <span v-if="sfxDescription(sfxId)" class="sfx-card-desc">{{ sfxDescription(sfxId) }}</span>
                    </div>
                  </div>
                </div>
                <div class="trait-right">
                  <div v-if="traitDiceGroups(t).length" class="trait-die-groups">
                    <div v-for="(group, gi) in traitDiceGroups(t)" :key="gi" class="trait-die-group">
                      <DieIcon
                        v-for="(die, i) in group"
                        :key="i"
                        :die="die"
                        class="trait-die-icon"
                        :style="i ? { marginLeft: '-20px', marginTop: `${i * 4}px` } : null"
                      />
                    </div>
                  </div>
                  <div v-else-if="t.ratingType === 'RESOURCE'" class="trait-die-groups resource">
                    <div
                      v-for="(group, gi) in resourceDiceGroups(t)"
                      :key="'a' + gi"
                      class="trait-die-group clickable"
                      :title="`Add ${group[0]} to pool`"
                      @click.stop="spendResourceGroup(t, group[0])"
                    >
                      <DieIcon
                        v-for="(die, i) in group"
                        :key="i"
                        :die="die"
                        class="trait-die-icon"
                        :style="i ? { marginLeft: '-20px', marginTop: `${i * 4}px` } : null"
                      />
                    </div>
                    <div v-for="(group, gi) in resourceSpentGroups(t)" :key="'s' + gi" class="trait-die-group">
                      <DieIcon
                        v-for="(die, i) in group"
                        :key="i"
                        :die="die"
                        class="trait-die-icon ghost"
                        :style="i ? { marginLeft: '-20px', marginTop: `${i * 4}px` } : null"
                      />
                    </div>
                    <span v-if="!(t.dice || []).length && !(t.spentDice || []).length" class="trait-die depleted">depleted</span>
                  </div>
                  <span v-else class="trait-die" :class="`die-${resolvedDieType(t)}`">{{ resourceDisplay(t) }}</span>
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
            </template>
          <button
            v-if="activeSheetView === 'traits' && nextSet"
            class="next-set-btn"
            @click="goToNextSet"
          >Next: {{ nextSet.name }} →</button>
        </div> <!-- .trait-list -->
      <div v-else-if="!showAddTrait" class="empty">{{ activeSheetView === 'profile' ? 'No profile traits' : 'No traits configured' }}</div>
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
import { useEntityCache } from '../composables/entityCache.js'
import DiePicker from './DiePicker.vue'
import BlueBook from './BlueBook.vue'
import LifePathWizard from './LifePathWizard.vue'
import DieIcon from './DieIcon.vue'
import MediaImage from './MediaImage.vue'

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
  visible: { type: Boolean, default: true },
})

const emit = defineEmits(['addToPool', 'removeFromPool', 'splitDie', 'removeByTsId', 'sfxToggled', 'openSettings', 'sheetViewChange'])

function displayName(name) {
  return name
    .split('_')
    .map(w => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ')
}

const { loading, error, graphql, triggerSfx, spendResourceDie, recoverResourceDie } = useApi()
const entityCache = useEntityCache()
const entity = ref(null)
const activeProjection = computed(() => {
  const e = entity.value
  if (!e || !e.projections) return null
  return e.projections.find((p) => p.id === e.currentProjection) || null
})
const sheetPortrait = computed(() => activeProjection.value?.sheetImage || entity.value?.sheetPortrait || '')
const traitSets = ref([])
const allTraitSettings = ref([])
const effectiveSettings = ref([])
const showAllTraits = ref(false)

function groupTraitSettings(settings) {
  const sets = {}
  for (const ts of settings || []) {
    const key = ts.traitsetName || 'Other'
    if (!sets[key]) sets[key] = []
    sets[key].push(ts)
  }
  return Object.entries(sets)
    .map(([name, traits]) => ({ name, traits, order: traits[0]?.traitsetOrder ?? 99, limit: traits[0]?.traitsetLimit ?? 1 }))
    .sort((a, b) => a.order - b.order)
    .map(({ name, traits, order, limit }) => ({ name, traits, limit }))
}

function recomputeTraitSets() {
  const src = showAllTraits.value ? allTraitSettings.value : effectiveSettings.value
  const settings = src || []
  profileTraits.value = settings.filter(t => t.ratingType === 'EMPTY')
  traitSets.value = groupTraitSettings(settings.filter(t => t.ratingType !== 'EMPTY'))
}

// ── Relationship widget (foreign sheets only) ──────
const relationship = ref(null)
const showRelEditor = ref(false)
const relDescription = ref('')
const relInput = ref(null)
const blueBookRef = ref(null)


const activeSheetView = ref('traits')  // 'traits' | 'profile' | 'lifepath' | 'bluebook'
watch(activeSheetView, (v) => emit('sheetViewChange', v))

const isForeignSheet = computed(() =>
  props.overrideEntityId && props.overrideEntityId !== props.viewerEntityId
)

const ownsCharacter = computed(() => {
  const id = props.overrideEntityId || props.entityId
  if (!props.playerOwnedEntityIds?.length) return false
  return props.playerOwnedEntityIds.includes(id)
})


// Resolved human-readable names
const locationName = ref('')
const universeName = ref('')
const universeNames = ref({})  // universe key/id → display name

// Trait-set navigation — at most one set drilled into at a time.
const activeSetName = ref(null)
// Traits with an EMPTY rating type, shown flat on the profile tab.
const profileTraits = ref([])

function openSet(name) {
  activeSetName.value = name
}

function closeSet() {
  activeSetName.value = null
}

function goToTraitSets() {
  activeSheetView.value = 'traits'
  cancelEdit()
  activeSetName.value = null
}

// Collapse the drilled-in set when the sheet is hidden, so it re-opens clean.
watch(() => props.visible, (v) => {
  if (!v && activeSetName.value) activeSetName.value = null
})

const currentSet = computed(() => {
  if (!activeSetName.value) return null
  return traitSets.value.find(ts => ts.name === activeSetName.value) || null
})

const currentTraits = computed(() => {
  if (activeSheetView.value === 'profile') return profileTraits.value
  return currentSet.value?.traits || []
})

const currentSetReachedLimit = computed(() => {
  if (!currentSet.value || !currentSet.value.limit) return false
  return currentSet.value.traits.filter(t => isInPool(t)).length >= currentSet.value.limit
})

const nextSet = computed(() => {
  const idx = traitSets.value.findIndex(ts => ts.name === activeSetName.value)
  if (idx === -1) return null
  return traitSets.value[idx + 1] || null
})

function goToNextSet() {
  if (nextSet.value) activeSetName.value = nextSet.value.name
}

// SFX usage tracking — reset per dice pool cycle
const sfxActivations = ref({})
const sfxCatalog = ref({})  // sfxId → { name, description }
const SFX_PHASES = {
  'sfx-hinder': ['adding'],
  'sfx-spray-n-pray': ['adding'],
}
const poolSources = ref([])

// Trait-setting ids routed to the opponent's pool (negative traits offered
// during a contest) — highlighted in the sheet and counted toward the set limit.
const offeredTraits = ref(new Set())

// Track resource trait dice that have been spent into the pool
// { tsId: [dieType, ...] } — cleared when a die is removed from the pool
const spentResources = ref({})

// Trait editing (full-panel view)
const editingTraitId = ref(null)

const editingTrait = computed(() => {
  if (!editingTraitId.value) return null
  for (const ts of traitSets.value) {
    const t = ts.traits.find(t => t.id === editingTraitId.value)
    if (t) return t
  }
  return profileTraits.value.find(t => t.id === editingTraitId.value) || null
})

const editDice = ref([])
const editRatingType = ref('STATIC')
const editPolarity = ref(null)
const editStatement = ref('')
const editNotes = ref('')
const showDiePicker = ref(false)
const pickIdx = ref(0)
const pickedDie = ref('')
const editSfxIds = ref([])
const editIsEgo = ref(true)
const editProjectionId = ref(null)
const showProjectionPicker = ref(false)

const RATING_TYPES = [
  { id: 'STATIC', label: 'Static' },
  { id: 'RESOURCE', label: 'Resource' },
  { id: 'CHALLENGE', label: 'Challenge' },
  { id: 'EMPTY', label: 'Empty' },
]

const editProjectionOptions = computed(() => entity.value?.projections || [])
const editProjectionName = computed(() => {
  const p = editProjectionOptions.value.find((p) => p.id === editProjectionId.value)
  return p ? (p.name || universeDisplay(p.originUniverse)) : (editProjectionId.value || 'select projection')
})
let longPressTimer = null

// ── Add trait picker ────────────────────────────
const showAddTrait = ref(false)
const addPhase = ref('sets')
const availableTraitSets = ref([])
const availableTraits = ref([])
const selectedTraitSet = ref(null)

const filteredTraits = computed(() => {
  if (!selectedTraitSet.value) return []
  const assigned = new Set([
    ...traitSets.value.flatMap(ts => ts.traits.map(t => t.traitId || t.id)),
    ...profileTraits.value.map(t => t.traitId || t.id),
  ])
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

  // Resource traits: the row click spends only when the pool has a single
  // die type; mixed-type resources are spent per die group.
  if (t.ratingType === 'RESOURCE') {
    const types = [...new Set((t.dice || []).map(d => (typeof d === 'string' ? d.toLowerCase() : d)))]
    if (types.length === 1) await spendResourceGroup(t, types[0])
    return
  }

  const negative = t.polarity === 'NEGATIVE'
  const dieType = (t.dice && t.dice.length ? t.dice[0] : '').toLowerCase()

  // Multi-die static traits contribute one pool die per rating entry.
  if (t.ratingType === 'STATIC' && (t.dice || []).length > 1) {
    emit('addToPool', { dice: t.dice.map(d => d.toLowerCase()), source: t.name, label: displayName(t.name), tsId: t.id, negative })
    return
  }

  if (!dieType) return  // no die rating — nothing to add
  emit('addToPool', { die: dieType, source: t.name, label: displayName(t.name), tsId: t.id, negative })
}

async function spendResourceGroup(t, dieType) {
  // Spend one die of the chosen type from the resource and add it to the pool.
  if (props.phase !== 'adding') return
  await spendResourceDie(t.id, dieType)
  if (!spentResources.value[t.id]) spentResources.value[t.id] = []
  spentResources.value[t.id].push(dieType)
  emit('addToPool', { die: dieType, source: t.name, label: displayName(t.name), tsId: t.id, negative: t.polarity === 'NEGATIVE', resource: true })
  await fetchEntity()
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

function groupByDieType(dice) {
  // Group a dice array by type so each type forms its own little
  // staircase (e.g. 3d4 + 2d6 → [['d4','d4','d4'], ['d6','d6']]).
  const groups = []
  const byType = new Map()
  for (const d of (dice || [])) {
    const die = d.toLowerCase()
    if (!byType.has(die)) {
      const group = []
      byType.set(die, group)
      groups.push(group)
    }
    byType.get(die).push(die)
  }
  // Ascending die size: d4 → d6 → d8 → d10 → d12.
  groups.sort((a, b) => parseInt(a[0].slice(1), 10) - parseInt(b[0].slice(1), 10))
  return groups
}

function traitDiceGroups(t) {
  // Static traits render grouped dice.  Resources/empty have their own
  // rendering (resources use resourceDiceGroups/resourceSpentGroups).
  if (t.ratingType === 'RESOURCE' || t.ratingType === 'EMPTY') return []
  return groupByDieType(t.dice)
}

function resourceDiceGroups(t) {
  return groupByDieType(t.dice)
}

function resourceSpentGroups(t) {
  return groupByDieType(t.spentDice)
}

function isResourceDepleted(t) {
  if (t.ratingType !== 'RESOURCE') return false
  return (!t.dice || t.dice.length === 0)
}

async function recoverSpentDie(die) {
  // Recover one spent die back into the resource pool (editor affordance).
  // Patch local state from the REST response so both the recoverable row
  // and the available-dice chips update without a full refetch.
  const t = editingTrait.value
  if (!t) return
  const res = await recoverResourceDie(t.id, die.toLowerCase())
  if (!res) return
  const toUpper = (arr) => (arr || []).map((d) => d.toUpperCase())
  t.dice = toUpper(res.dice)
  t.spentDice = toUpper(res.spent)
  t.rating = null  // force fallback to dice display
  editDice.value = (res.dice || []).map((d) => d.toLowerCase())
}

function isInPool(t) {
  return poolSources.value.includes(t.id) || offeredTraits.value.has(t.id)
}

function isOffered(t) {
  return offeredTraits.value.has(t.id)
}

function setOfferedTraits(ids) {
  offeredTraits.value = new Set(ids || [])
}

function isKnown(t) {
  // The GM sees every trait — fog of war (knownTo) only applies to players.
  if (props.gmMode) return true
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

  // When the current set fills to its limit, advance to the next set's list.
  const sets = traitSets.value
  const idx = sets.findIndex(s => s.name === activeSetName.value)
  if (idx !== -1) {
    const count = sets[idx].traits.filter(t => poolSources.value.includes(t.id)).length
    if (sets[idx].limit && count >= sets[idx].limit) {
      activeSetName.value = sets[idx + 1] ? sets[idx + 1].name : null
    }
  }

  // Auto-recover resource dice that were removed from the pool
  // (e.g. via chip click in DiceRoller).  Only during adding phase —
  // once dice are rolled they stay spent.
  if (props.phase !== 'adding') return
  let recovered = false
  for (const tsId of Object.keys(spentResources.value)) {
    const spent = [...spentResources.value[tsId]]
    const inPool = sources.filter(s => s.tsId === tsId).map(s => s.die)
    const remaining = []
    for (const dieType of spent) {
      const at = inPool.indexOf(dieType)
      if (at !== -1) {
        inPool.splice(at, 1)
        remaining.push(dieType)
      } else {
        recoverResourceDie(tsId, dieType)
        recovered = true
      }
    }
    if (remaining.length) spentResources.value[tsId] = remaining
    else delete spentResources.value[tsId]
  }
  if (recovered) fetchEntity()
}

defineExpose({ resetSfxCounts, setPoolSources, setRazmerit, setOfferedTraits, fetchEntity })

function sfxActive(sfxId) {
  return (sfxActivations.value[sfxId] || 0) > 0
}

function sfxUsed(sfxId) {
  if (!sfxAllowedInPhase(sfxId)) return true
  if (sfxActive(sfxId)) return true
  if (sfxId === 'sfx-spray-n-pray' && !poolSources.value.includes('shooting')) return true
  return false
}

function sfxName(sfxId) {
  return sfxCatalog.value[sfxId]?.name || sfxId.replace(/^sfx-/, '').replace(/-/g, ' ')
}

function sfxDescription(sfxId) {
  return sfxCatalog.value[sfxId]?.description || ''
}

async function fetchSfxCatalog() {
  try {
    const r = await fetch('/api/v1/graphql', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query: `query { sfxs { id name description } }` }),
    })
    const json = await r.json()
    const map = {}
    for (const s of json?.data?.sfxs || []) map[s.id] = s
    sfxCatalog.value = map
  } catch (e) {
    console.error('fetchSfxCatalog', e)
  }
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
      currentProjection
      backgroundImage
      sheetPortrait
      projections {
        id originUniverse universe name sheetImage currentLocation transversalType
      }
      traitSettings {
        id
        traitId
        name
        traitsetName
        dieType
        ratingType
        rating
        ego
        fromType
        projectionId
        statement
        notes
        sfxIds
        universe
        dice
        spentDice
        polarity
        traitsetOrder
        traitsetLimit
        knownTo
        possibleSfxIds
        transferFlags
      }
      effectiveTraitSettings {
        id
        traitId
        name
        traitsetName
        dieType
        ratingType
        rating
        ego
        fromType
        projectionId
        statement
        notes
        sfxIds
        universe
        dice
        spentDice
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
  if (!id) return
  const data = await graphql(QUERY, { id })
  if (data?.entity) {
    entityCache.setSheet(id, data.entity)
    applyEntity(data.entity)
  }
}

// Render the cached sheet immediately when we have it; otherwise fetch fresh.
// Used on open/switch so re-opening a sheet doesn't re-download the whole entity.
function loadCachedEntity() {
  const id = props.overrideEntityId || props.entityId
  if (!id) return
  const cached = entityCache.getSheet(id)
  if (cached) {
    applyEntity(cached)
    return
  }
  fetchEntity()
}

function applyEntity(e) {
  entity.value = e
  resolveNames(e)
  allTraitSettings.value = e.traitSettings || []
  effectiveSettings.value = e.effectiveTraitSettings || []
  recomputeTraitSets()
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
      const map = {}
      for (const u of universes) {
        if (u.currentUniverse) map[u.currentUniverse] = u.name
        if (u.id) map[u.id] = u.name
      }
      universeNames.value = map
      const match = universes.find(u => u.currentUniverse === e.currentUniverse || u.id === e.currentUniverse)
      universeName.value = match?.name || e.currentUniverse
    } catch { universeName.value = e.currentUniverse }
  }
}

function universeDisplay(key) {
  return universeNames.value[key] || key
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
  editDice.value = (t.dice || []).map(d => d.toLowerCase())
  editRatingType.value = t.ratingType || 'STATIC'
  editPolarity.value = t.polarity || null
  editStatement.value = t.statement || ''
  editNotes.value = t.notes || ''
  editSfxIds.value = [...(t.sfxIds || [])]
  const isMorph = t.fromType === 'projection' || t.ego === false
  editIsEgo.value = !isMorph
  editProjectionId.value =
    (t.fromType === 'projection' && t.projectionId) ||
    (isMorph ? (entity.value?.currentProjection || entity.value?.projections?.[0]?.id) : null) ||
    null
  showProjectionPicker.value = false
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

const showRazmeritWidget = ref(false)
const editingRazmerit = ref(false)
const razmeritInputValue = ref('')
const razmeritInput = ref(null)

function startRazmeritEdit() {
  editingRazmerit.value = true
  razmeritInputValue.value = String(entity.value?.razmerit ?? 0)
  nextTick(() => razmeritInput.value?.focus())
}

async function commitRazmerit() {
  if (!editingRazmerit.value) return
  editingRazmerit.value = false
  const val = parseInt(razmeritInputValue.value, 10)
  if (Number.isNaN(val)) return
  const resp = await fetch('/api/v1/graphql', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      query: 'mutation($id: ID!, $razmerit: Int) { updateEntity(input: { id: $id, razmerit: $razmerit }) { id razmerit } }',
      variables: { id: props.entityId, razmerit: val },
    }),
  })
  const data = await resp.json()
  const newVal = data?.data?.updateEntity?.razmerit
  if (newVal != null && entity.value) entity.value.razmerit = newVal
}

async function adjustRazmerit(delta) {
  const mutation = delta < 0 ? 'spendRazmerit' : 'earnRazmerit'
  const resp = await fetch('/api/v1/graphql', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      query: 'mutation($eid: ID!, $amt: Int!) { ' + mutation + '(entityId: $eid, amount: $amt) { fromBalance toBalance } }',
      variables: { eid: props.entityId, amt: Math.abs(delta) },
    }),
  })
  const data = await resp.json()
  const result = data?.data?.[mutation]
  const balance = mutation === 'earnRazmerit' ? result?.toBalance : result?.fromBalance
  if (balance != null) entity.value.razmerit = balance
}

function setRazmerit(balance, entityId) {
  // Live-patch the sheet when the SSE razmerit_changed event arrives for the
  // entity this sheet is currently showing (could be an override/peer).
  if (entity.value && balance != null && entity.value.id === (entityId ?? props.entityId)) {
    entity.value.razmerit = balance
  }
}

async function deleteTrait(t) {
  await fetch('/api/v1/graphql', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query: `mutation($id: ID!) { removeTraitSetting(id: $id) }`, variables: { id: t.id } }),
  })
  editingTraitId.value = null
  // Remove from local traitSets / profileTraits — no full re-render
  let removed = false
  for (const ts of traitSets.value) {
    const idx = ts.traits.findIndex(tr => tr.id === t.id)
    if (idx !== -1) {
      ts.traits.splice(idx, 1)
      if (ts.traits.length === 0) {
        traitSets.value = traitSets.value.filter(s => s.name !== ts.name)
      }
      removed = true
      break
    }
  }
  if (!removed) {
    const idx = profileTraits.value.findIndex(tr => tr.id === t.id)
    if (idx !== -1) profileTraits.value.splice(idx, 1)
  }
}

function ensureEditProjection() {
  if (!editIsEgo.value && !editProjectionId.value) {
    editProjectionId.value = entity.value?.currentProjection || entity.value?.projections?.[0]?.id || null
  }
}

async function doSave() {
  if (!editingTraitId.value) return
  ensureEditProjection()
  const newDice = editDice.value.map(d => d.toUpperCase())
  const query = `mutation($id: ID!, $dice: [DieType!], $ratingType: RatingType, $polarity: Polarity, $statement: String, $notes: String, $sfxIds: [ID!], $fromType: String, $projectionId: ID) {
    updateTraitSetting(id: $id, input: { dice: $dice, ratingType: $ratingType, polarity: $polarity, statement: $statement, notes: $notes, sfxIds: $sfxIds, fromType: $fromType, projectionId: $projectionId }) { id }
  }`
  const variables = {
    id: editingTraitId.value,
    dice: newDice,
    ratingType: editRatingType.value,
    polarity: editPolarity.value,
    statement: editStatement.value ?? null,
    notes: editNotes.value ?? null,
    sfxIds: editSfxIds.value,
    fromType: editIsEgo.value ? 'entity' : 'projection',
    projectionId: editIsEgo.value ? null : editProjectionId.value,
  }
  await fetch('/api/v1/graphql', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query, variables }),
  })
  // Patch local data — no full re-render
  const patchTrait = (t) => {
    t.dice = newDice
    t.ratingType = editRatingType.value
    t.polarity = editPolarity.value
    t.rating = null  // force fallback to dice display
    t.sfxIds = [...editSfxIds.value]
    t.statement = editStatement.value
    t.notes = editNotes.value
    t.ego = editIsEgo.value
    t.fromType = editIsEgo.value ? 'entity' : 'projection'
    t.projectionId = editIsEgo.value ? null : editProjectionId.value
  }
  for (const ts of traitSets.value) {
    const t = ts.traits.find(t => t.id === editingTraitId.value)
    if (t) { patchTrait(t); break }
  }
  const pt = profileTraits.value.find(t => t.id === editingTraitId.value)
  if (pt) patchTrait(pt)
}

async function toggleEgo() {
  editIsEgo.value = !editIsEgo.value
  if (!editIsEgo.value) {
    editProjectionId.value = entity.value?.currentProjection || entity.value?.projections?.[0]?.id || null
  }
  showProjectionPicker.value = false
  await doSave()
  await fetchEntity()
}

function togglePolarity() {
  editPolarity.value = editPolarity.value === 'POSITIVE' ? 'NEGATIVE' : 'POSITIVE'
  doSave()
}

function toggleProjectionPicker() {
  showProjectionPicker.value = !showProjectionPicker.value
}

async function selectProjection(p) {
  editProjectionId.value = p.id
  showProjectionPicker.value = false
  await doSave()
  await fetchEntity()
}

function toggleSfx(sfxId) {
  const idx = editSfxIds.value.indexOf(sfxId)
  if (idx === -1) editSfxIds.value.push(sfxId)
  else editSfxIds.value.splice(idx, 1)
  doSave()
}

async function setRatingType(rt) {
  if (editRatingType.value === rt) return
  editRatingType.value = rt
  // EMPTY traits carry no dice rating — clear them.
  if (rt === 'EMPTY') editDice.value = []
  await doSave()
  // Re-split so the trait moves between the rated list and the profile tab.
  recomputeTraitSets()
}

let statementDebounce = null
function onStatementInput() {
  clearTimeout(statementDebounce)
  statementDebounce = setTimeout(doSave, 500)
}

function splitStatement() {
  const words = (editStatement.value || '').trim().split(/\s+/).filter(Boolean)
  if (words.length > 7) {
    const moved = editStatement.value.trim()
    editNotes.value = editNotes.value ? editNotes.value + '\n' + moved : moved
    editStatement.value = ''
  }
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

// Close the razmerit popover when clicking outside its anchor.
function onDocumentClick(e) {
  if (showRazmeritWidget.value && !e.target.closest('.razmerit-anchor')) {
    showRazmeritWidget.value = false
  }
}

onMounted(() => {
  console.log('[diag] CharacterSheet mounted', { entityId: props.entityId, universe: props.universe, embedded: props.embedded })
  document.addEventListener('keydown', onKeydown)
  document.addEventListener('click', onDocumentClick)
})
onUnmounted(() => {
  document.removeEventListener('keydown', onKeydown)
  document.removeEventListener('click', onDocumentClick)
})

onMounted(() => {
  console.log('[diag] CharacterSheet fetchEntity mounted', { entityId: props.entityId })
  loadCachedEntity()
  fetchSfxCatalog()
})
watch(() => props.entityId, loadCachedEntity)
watch(() => props.universe, loadCachedEntity)
watch(() => props.overrideEntityId, loadCachedEntity)
watch(() => [props.entityId, props.overrideEntityId], () => { activeSetName.value = null })
watch(showAllTraits, recomputeTraitSets)

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
.trait-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.trait-list-title {
  align-self: flex-start;
  cursor: pointer;
  user-select: none;
  margin: 0 0 8px;
  font-size: 13px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 1px;
  color: var(--text);
  transition: color 0.15s;
}
.trait-list-title:hover {
  color: var(--accent);
}
.trait-list-wrap {
  flex-direction: row;
  flex-wrap: wrap;
  gap: 6px;
}
.trait-list-wrap .trait-row {
  margin: 0;
  flex: 0 0 auto;
  max-width: 100%;
  background: rgba(255,255,255,0.02);
}
.trait-list-wrap .trait-left {
  flex: 0 1 auto;
}
.set-back {
  align-self: flex-start;
  background: transparent;
  border: none;
  color: var(--accent);
  cursor: pointer;
  font-size: 12px;
  padding: 4px 0;
  margin-bottom: 6px;
}
.set-back:hover {
  text-decoration: underline;
}
.next-set-btn {
  align-self: flex-end;
  background: transparent;
  border: 1px dashed rgba(255,255,255,0.12);
  color: var(--text-dim);
  cursor: pointer;
  font-size: 12px;
  padding: 6px 10px;
  margin-top: 6px;
  border-radius: 6px;
  transition: border-color 0.15s, color 0.15s;
}
.next-set-btn:hover {
  border-color: var(--accent-dim);
  color: var(--accent);
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
.trait-row.offered {
  background: rgba(242, 144, 138, 0.14);
  box-shadow: inset 2px 0 0 var(--offered);
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

.trait-edit-panel {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 4px 0 8px;
}
.edit-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.edit-label {
  font-size: 10px;
  font-weight: 600;
  color: var(--text-dim);
  text-transform: uppercase;
  letter-spacing: 0.6px;
}
.edit-flags {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  align-items: center;
}
.edit-title {
  margin: 0 0 2px;
  font-size: 14px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 1px;
  color: var(--text);
}
.edit-dice {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
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
.edit-spent-dice {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}
.edit-spent-label {
  font-size: 12px;
  color: var(--text-dim);
}
.edit-spent-dice .die-chip {
  font-size: 13px;
  font-weight: 700;
  padding: 2px 9px;
  border-radius: 6px;
  border: 2px dashed rgba(255,255,255,0.25);
  background: rgba(255,255,255,0.04);
  color: var(--text-dim);
  cursor: pointer;
  transition: border-color 0.15s, color 0.15s;
}
.edit-spent-dice .die-chip:hover {
  border-color: var(--accent);
  color: var(--text);
}
.edit-dice .die-chip.die-chip-icon,
.edit-spent-dice .die-chip.die-chip-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 2px;
  line-height: 0;
}
.edit-dice .die-chip.die-chip-icon .die-icon,
.edit-spent-dice .die-chip.die-chip-icon .die-icon {
  width: 28px;
  height: 30px;
}
.edit-spent-dice .die-chip.die-chip-icon .die-icon {
  opacity: 0.45;
}
.edit-rating-type {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  align-items: center;
}
.rating-type-btn {
  padding: 4px 10px;
  border-radius: 999px;
  border: 1px solid rgba(255,255,255,0.12);
  background: transparent;
  color: var(--text-dim);
  font-size: 11px;
  cursor: pointer;
  transition: border-color 0.15s, color 0.15s, background 0.15s;
}
.rating-type-btn.active {
  border-color: var(--accent);
  color: var(--accent);
  background: rgba(64, 136, 212, 0.12);
}
.edit-sfx {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  align-items: center;
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

.edit-statement,
.edit-notes {
  width: 100%;
  box-sizing: border-box;
  background: rgba(255,255,255,0.05);
  border: 1px solid rgba(255,255,255,0.12);
  border-radius: 6px;
  color: var(--text);
  font-size: 12px;
  font-family: inherit;
  padding: 6px 8px;
  transition: border-color 0.15s;
}
.edit-statement:focus,
.edit-notes:focus {
  outline: none;
  border-color: var(--accent-dim);
}
.edit-notes {
  min-height: 56px;
  resize: vertical;
}
.edit-actions {
  display: flex;
  gap: 6px;
  margin-top: 4px;
  padding-top: 12px;
  border-top: 1px solid rgba(255,255,255,0.08);
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
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.header-controls {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 8px;
  flex-wrap: wrap;
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
.ego-toggle {
  padding: 3px 12px;
  border-radius: 999px;
  border: 1px solid var(--text-dim);
  background: transparent;
  color: var(--text-dim);
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  cursor: pointer;
}
.ego-toggle.is-ego {
  border-color: var(--accent);
  color: var(--accent);
  background: rgba(255, 255, 255, 0.06);
}
.polarity-toggle {
  padding: 3px 12px;
  border-radius: 999px;
  border: 1px solid var(--text-dim);
  background: transparent;
  color: var(--text-dim);
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  cursor: pointer;
}
.polarity-toggle.is-positive {
  border-color: var(--accent);
  color: var(--accent);
  background: rgba(255, 255, 255, 0.06);
}
.edit-projection {
  display: flex;
  align-items: center;
  gap: 6px;
  position: relative;
}
.edit-projection-label {
  font-size: 10px;
  color: var(--text-dim);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}
.projection-chip {
  padding: 3px 10px;
  border-radius: 999px;
  border: 1px solid var(--accent-dim);
  background: rgba(64, 136, 212, 0.12);
  color: var(--accent);
  font-size: 11px;
  cursor: pointer;
}
.projection-chip:hover {
  border-color: var(--accent);
}
.projection-dropdown {
  position: absolute;
  top: 100%;
  left: 0;
  z-index: 20;
  margin-top: 4px;
  min-width: 160px;
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: 6px;
  box-shadow: 0 4px 12px rgba(0,0,0,0.4);
  overflow: hidden;
}
.projection-option {
  display: block;
  width: 100%;
  padding: 6px 10px;
  background: transparent;
  border: none;
  color: var(--text);
  font-size: 12px;
  text-align: left;
  cursor: pointer;
}
.projection-option:hover {
  background: var(--bg-hover);
}
.projection-option.selected {
  color: var(--accent);
  background: rgba(64, 136, 212, 0.12);
}
.razmerit-anchor {
  position: relative;
  flex-shrink: 0;
}
.razmerit-chip {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  font-size: 11px;
  font-weight: 600;
  color: var(--accent);
  background: transparent;
  border: 1px solid rgba(255,255,255,0.12);
  border-radius: 999px;
  padding: 5px 10px;
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s;
}
.razmerit-chip:hover {
  border-color: var(--accent-dim);
  background: rgba(64,136,212,0.08);
}
.razmerit-popover {
  position: absolute;
  top: calc(100% + 8px);
  left: 50%;
  transform: translateX(-50%);
  z-index: 30;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: var(--bg-panel);
  border: 1px solid rgba(255,255,255,0.12);
  border-radius: 10px;
  box-shadow: 0 6px 20px rgba(0,0,0,0.4);
  white-space: nowrap;
}
.razmerit-value {
  font-size: 24px;
  font-weight: 700;
  color: var(--accent);
}
.razmerit-value.editable {
  cursor: pointer;
}
.razmerit-input {
  width: 64px;
  font-size: 24px;
  font-weight: 700;
  color: var(--accent);
  background: rgba(255,255,255,0.04);
  border: 1px solid var(--accent-dim);
  border-radius: 6px;
  padding: 2px 4px;
  text-align: center;
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
  /* margin: 0 -8px; */
  border-radius: 6px;
  font-size: 13px;
  cursor: pointer;
  transition: background 0.1s;
}
.trait-row:hover {
  background: rgba(255,255,255,0.04);
}
.trait-row.morph {
  background: rgba(64, 136, 212, 0.08);
  border-left: 2px solid var(--accent);
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
.trait-notes {
  font-size: 10px;
  color: var(--text-dim);
  line-height: 1.3;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.trait-die {
  font-weight: 700;
  font-size: 14px;
}
.die-d4  { color: var(--die-d4); }
.die-d6  { color: var(--die-d6); }
.die-d8  { color: var(--die-d8); }
.die-d10 { color: var(--die-d10); }
.die-d12 { color: var(--die-d12); }

.trait-die-groups {
  display: flex;
  align-items: flex-start;
  gap: 12px;
}
.trait-die-group {
  display: flex;
  align-items: flex-start;
}
.trait-die-group.clickable { cursor: pointer; }
.trait-die-group.clickable:hover .trait-die-icon { filter: brightness(1.25); }
.trait-die-icon {
  width: 32px;
  height: 34px;
}
.trait-die-icon.ghost {
  opacity: 0.32;
}
.trait-die.depleted {
  color: var(--text-dim);
  font-style: italic;
}

.trait-row.negative {
  --die-d4: var(--die-d4-neg);
  --die-d6: var(--die-d6-neg);
  --die-d8: var(--die-d8-neg);
  --die-d10: var(--die-d10-neg);
  --die-d12: var(--die-d12-neg);
  background: rgba(122, 31, 31, 0.10);
}
.trait-row.negative.morph {
  background: rgba(122, 31, 31, 0.14);
  border-left: 2px solid #7a1f1f;
}

.loading, .error, .empty {
  font-size: 13px;
  color: var(--text-dim);
  text-align: center;
  padding: 16px 0;
}
.error { color: var(--danger); }

.sfx-cards {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-top: 4px;
}
.sfx-card {
  display: flex;
  flex-direction: column;
  gap: 1px;
  align-self: flex-start;
  max-width: 100%;
  padding: 4px 8px;
  border-radius: 6px;
  border: 1px solid rgba(255,255,255,0.08);
  background: rgba(255,255,255,0.03);
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s;
}
.sfx-card:hover {
  border-color: rgba(255,255,255,0.2);
}
.sfx-card.sfx-active {
  border-color: var(--accent);
  background: rgba(64, 136, 212, 0.12);
}
.sfx-card.sfx-used {
  opacity: 0.35;
  pointer-events: none;
}
.sfx-card-name {
  font-size: 11px;
  font-weight: 600;
  color: var(--text);
}
.sfx-card-desc {
  font-size: 10px;
  color: var(--text-dim);
  line-height: 1.3;
}

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
