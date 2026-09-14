<template>
  <!-- Embedded: single root for attribute inheritance -->
  <div v-if="embedded" class="sheet-embedded" :class="{ 'transparent-portrait': sheetPortraitTransparent }">
    <div v-if="loading" class="loading">Loading…</div>
    <div v-else-if="error" class="error">{{ error }}</div>
    <template v-else-if="entity">
      <div class="header">
        <div class="header-top">
          <div class="header-title">
            <!-- A named body takes over the title; the character's name shrinks
                 to an overline above it. Unnamed: the character keeps the title
                 and the naming action sits underneath. The edit input always
                 swaps into the slot of the level it edits, so the header
                 doesn't reflow when you click. -->
            <div v-if="projectionSubtitle" class="name-overline">{{ entity.name }}</div>

            <template v-if="projectionSubtitle">
              <input
                v-if="editingProjectionName"
                ref="projectionNameInput"
                v-model="projectionNameValue"
                class="projection-name-input is-primary"
                placeholder="Name this projection…"
                @keyup.enter="commitProjectionName"
                @keyup.escape="editingProjectionName = false"
                @blur="commitProjectionName"
              />
              <h2 v-else class="name-primary">
                <Button
                  v-if="canEditProjectionName"
                  variant="link"
                  class="name-primary-btn"
                  title="Rename this projection"
                  @click.stop="startProjectionNameEdit"
                >{{ projectionSubtitle }}</Button>
                <span v-else>{{ projectionSubtitle }}</span>
              </h2>
            </template>

            <template v-else>
              <h2 class="name-primary">{{ entity.name }}</h2>
              <div v-if="canEditProjectionName" class="name-secondary">
                <input
                  v-if="editingProjectionName"
                  ref="projectionNameInput"
                  v-model="projectionNameValue"
                  class="projection-name-input"
                  placeholder="Name this projection…"
                  @keyup.enter="commitProjectionName"
                  @keyup.escape="editingProjectionName = false"
                  @blur="commitProjectionName"
                />
                <Button
                  v-else
                  variant="link"
                  class="projection-name-btn unset"
                  title="Name this projection"
                  @click.stop="startProjectionNameEdit"
                >＋ Name this projection</Button>
              </div>
            </template>
          </div>
          <div class="razmerit-anchor">
            <button class="razmerit-chip" :title="showRazmeritWidget ? 'Close' : 'Adjust razmerit'" @click.stop="showRazmeritWidget = !showRazmeritWidget">
              ⚡{{ entity.razmerit }}
            </button>
            <div v-if="showRazmeritWidget" class="razmerit-popover" @click.stop>
              <Button v-if="!overrideEntityId" variant="ghost" size="icon" title="Decrease razmerit" @click.stop="adjustRazmerit(-1)">−</Button>
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
              <Button v-if="!overrideEntityId" variant="ghost" size="icon" title="Increase razmerit" @click.stop="adjustRazmerit(1)">+</Button>
            </div>
          </div>
          <MediaImage v-if="sheetPortrait" :src="sheetPortrait" class="sheet-portrait" :class="{ transparent: sheetPortraitTransparent }" />
        </div>
        <div class="header-controls">
          <div v-if="isForeignSheet" class="rel-widget">
            <template v-if="relationship">
              <span class="rel-desc" @click.stop="showRelEditor = true" :title="'Click to edit'">{{ relationship.description || 'related' }}</span>
              <Button variant="danger-ghost" size="sm" title="Remove relationship" @click.stop="removeRelationship">✕</Button>
              <Button variant="ghost" size="icon" title="Send letter" @click.stop="openBlueBookLetter">✉</Button>
            </template>
            <div v-if="showRelEditor" class="rel-editor" @click.stop>
              <input ref="relInput" v-model="relDescription" placeholder="Describe relationship…" @keyup.enter="saveRelationship" @keyup.escape="showRelEditor = false" />
              <Button variant="primary" size="icon" title="Save relationship" @click="saveRelationship">✓</Button>
              <Button variant="ghost" size="icon" title="Cancel" @click="showRelEditor = false">✕</Button>
            </div>
          </div>
          <div class="sheet-pills">
            <div v-if="gmMode || !overrideEntityId || showRelationTab">
              <button
                v-if="showRelationTab"
                :class="['pill', { active: activeSheetView === 'relation' }]"
                :title="`What you hold about ${entity.name}`"
                @click="activeSheetView = 'relation'"
              >🤝</button>
              <template v-if="gmMode || !overrideEntityId">
                <button :class="['pill', { active: activeSheetView === 'profile' }]" @click="activeSheetView = 'profile'">👤</button>
                <button :class="['pill', { active: activeSheetView === 'traits' }]" @click="goToTraitSets">🎲</button>
                <button v-if="gmMode" :class="['pill', { active: showAllTraits }]" :title="showAllTraits ? 'Showing all traits' : 'Show all traits'" @click="showAllTraits = !showAllTraits">🌍</button>
                <button :class="['pill', { active: activeSheetView === 'bluebook' }]" @click="activeSheetView = 'bluebook'">📘</button>
                <button :class="['pill', { active: activeSheetView === 'lifepath' }]" @click="activeSheetView = 'lifepath'">🛤️</button>
              </template>
            </div>
            <Button v-if="!gmMode && !isForeignSheet" variant="ghost" size="icon" title="Player settings" @click.stop="$emit('openSettings')">↩</Button>
            <Button v-if="isForeignSheet && !relationship" variant="ghost" size="icon" title="Add relationship" @click.stop="createImmediateRelationship()">+</Button>
          </div>
        </div>
        <div v-if="entitySfxIds.length || projectionSfxIds.length" class="entity-sfx-cards">
          <SfxCard v-for="sfxId in entitySfxIds" :key="'e-' + sfxId" v-bind="sfxCardModel(sfxId)"
                   @activate="activateSfx(sfxId, entity.id)" />
          <SfxCard v-for="sfxId in projectionSfxIds" :key="'p-' + sfxId" v-bind="sfxCardModel(sfxId)"
                   @activate="activateSfx(sfxId, activeProjection.id)" />
        </div>
        <!-- Rules lent by the place you are standing in. Not attached to you:
             they reach you because you're here, and leave when you do. -->
        <div v-if="placeRuleGroups.length" class="place-sfx-rules">
          <div v-for="g in placeRuleGroups" :key="g.locationId" class="place-sfx-group">
            <span class="place-sfx-label">From {{ g.locationName }}</span>
            <div class="entity-sfx-cards">
              <SfxCard v-for="sfxId in g.sfxIds" :key="g.locationId + ':' + sfxId"
                       v-bind="placeCardModel(sfxId)"
                       @activate="activateSfx(sfxId, g.locationId)" />
            </div>
          </div>
        </div>
        <div v-if="gmMode" class="meta">
          <span class="location">{{ locationName || entity.currentLocation || 'Unknown' }}</span>
          <span class="universe">{{ universeName || entity.currentUniverse }}</span>
          <span v-if="entityTimerLabel" class="active-effects" :title="'Timed effects pending: ' + entityTimerLabel">⏳ {{ entityTimerLabel }}</span>
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
        <TraitEditPanel
          v-if="editingTrait && !showAddTrait"
          :trait="editingTrait"
          :dice="editDice"
          :capacity="editCapacity"
          :rating-type="editRatingType"
          :polarity="editPolarity"
          :statement="editStatement"
          :notes="editNotes"
          :sfx-ids="editSfxIds"
          :acquirable-sfx-ids="acquirableSfxIds"
          :tags="editTags"
          :inherit-tags="editingTrait?.registryTags || []"
          :tag-suggestions="tagSuggestions"
          :is-ego="editIsEgo"
          :projection-id="editProjectionId"
          :projection-name="editProjectionName"
          :projection-options="projectionChoices"
          :subtraits="availableSubtraits"
          :show-projection-picker="showProjectionPicker"
          :delete-countdown="deleteCountdown"
          :deleting-trait-id="deletingTraitId"
          @update:dice="editDice = $event"
          @update:capacity="editCapacity = $event"
          @update:statement="editStatement = $event"
          @update:notes="editNotes = $event"
          @update:tags="editTags = $event"
          @rating-type="onEditorRatingType"
          @change="onEditorChange"
          @field-blur="onEditorFieldBlur"
          @recover-die="recoverSpentDie"
          @back="cancelEdit"
          @delete="onDeleteClick"
          @toggle-sfx="toggleSfx"
          @toggle-ego="toggleEgo"
          @toggle-polarity="togglePolarity"
          @toggle-projection-picker="toggleProjectionPicker"
          @select-projection="selectProjection"
          @add-subtrait="addSubTrait"
          @remove-subtrait="removeSubTrait"
        />

        <!-- Trait detail (read-only) — the row's "elsewhere" click zone.
             Right-click on the row, or the header's Edit, opens the editor. -->
        <TraitDetailPanel
          v-else-if="detailTrait && !showAddTrait"
          :trait="detailTrait"
          :api="detailApi"
          @back="closeTraitDetail"
          @edit="startEdit"
        />

        <!-- Traits tab: trait-set list -->
        <div v-else-if="activeSheetView === 'traits' && !activeSetName && traitSets.length && !showAddTrait" class="trait-sets">
          <div v-for="ts in traitSets" :key="ts.name" class="trait-set">
            <h4 @click="openSet(ts.name)" class="set-header">
              <span class="set-name">{{ ts.name }}</span>
              <span v-if="ts.limit" class="limit-dots">
                <span v-for="i in ts.limit" :key="i" class="limit-dot" :class="{ filled: i <= inPoolCount(ts) }">{{ i <= inPoolCount(ts) ? '●' : '○' }}</span>
              </span>
            </h4>
            <div v-if="traitsetSfxIds(ts).length" class="sfx-cards">
              <SfxCard v-for="sfxId in traitsetSfxIds(ts)" :key="'ts-' + sfxId" v-bind="sfxCardModel(sfxId)"
                       @activate="activateSfx(sfxId, traitsetSettingSourceId(ts))" />
            </div>
          </div>
        </div>

        <!-- Set detail (traits) or profile: flat trait list -->
        <div v-else-if="currentTraits.length && !showAddTrait" class="trait-list" :class="{ 'trait-list-wrap': activeSheetView === 'profile' }">
          <h4 v-if="activeSheetView === 'traits'" class="trait-list-title" @click="closeSet" title="Back to trait sets">← {{ activeSetName }}</h4>
            <TraitRow
              v-for="t in currentTraits"
              :key="t.id"
              :trait="t"
              :api="traitRowApi"
              :phase="phase"
              :limit-reached="currentSetReachedLimit"
              :wrap="activeSheetView === 'profile'"
            />
          <div v-if="activeSheetView === 'traits' && (prevSet || nextSet)" class="set-nav">
            <Button
              v-if="prevSet"
              class="set-nav-prev"
              variant="neutral"
              @click="goToPrevSet"
            >← Previous: {{ prevSet.name }}</Button>
            <Button
              v-if="nextSet"
              class="set-nav-next"
              variant="neutral"
              @click="goToNextSet"
            >Next: {{ nextSet.name }} →</Button>
          </div>
        </div> <!-- .trait-list -->
      <div v-else-if="!showAddTrait" class="empty">{{ activeSheetView === 'profile' ? 'No profile traits' : 'No traits configured' }}</div>
      <Button v-if="(!overrideEntityId || gmMode) && !showAddTrait" class="add-trait-btn" variant="secondary" block @click="openAddTrait">+ Add Trait</Button>
      <Button v-if="isForeignSheet && !showAddTrait" class="add-trait-btn" variant="secondary" block @click="openAddRelationshipTrait">+ Add relationship trait</Button>
      <!-- 2-phase trait picker -->
      <div v-if="showAddTrait" class="trait-picker">
        <template v-if="addPhase === 'sets'">
          <h4>Pick a trait set</h4>
          <button v-for="ts in availableTraitSets" :key="ts.id" class="picker-item" @click="selectSet(ts)">{{ ts.name }}</button>
        </template>
        <template v-if="addPhase === 'traits'">
          <Button class="picker-back" variant="link" @click="addPhase = 'sets'">← {{ selectedTraitSet?.name }}</Button>
          <button v-for="t in filteredTraits" :key="t.id" class="picker-item" @click="addTrait(t)">
            {{ t.name }}
            <span v-if="t.defaultRatingType !== 'EMPTY'" class="picker-die">{{ t.defaultDieType }}</span>
          </button>
          <div v-if="!filteredTraits.length" class="empty">{{ emptySetMessage }}</div>
        </template>
        <Button class="picker-cancel" variant="neutral" block @click="showAddTrait = false">Cancel</Button>
      </div>
      </div> <!-- .sheet-scroll -->
      </template>
    </template>
    <div v-else class="empty empty-no-entity">
      <span>No entity loaded</span>
      <Button
        v-if="!gmMode && !isForeignSheet"
        variant="neutral"
        @click="$emit('openSettings')"
        title="Choose a character"
      >↩ Player settings</Button>
    </div>

    <Teleport to="body">
      <RollTableMenu
        v-if="rollTableMenu"
        :entity-id="entity.id"
        :table-id="rollTableMenu.tableId"
        :title="rollTableMenu.name"
        :entity-razmerit="entity.razmerit ?? 0"
        :mode="rollTableMenu.mode || 'apply'"
        :player-id="playerId"
        :main-entity-id="mainEntityId"
        @close="rollTableMenu = null"
      />
    </Teleport>
  </div>

</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { useApi } from '../composables/useApi.js'
import { useEntityCache } from '../composables/entityCache.js'
import { perfMark } from '../composables/perfLog.js'
import { useScheduledEvents } from '../composables/useScheduledEvents.js'
import { usePersistedRef } from '../composables/usePersistedState.js'
import { useTraitEditor } from '../composables/useTraitEditor.js'
import { useDragDrop } from '../composables/useDragDrop.js'
import TraitEditPanel from './sheet/TraitEditPanel.vue'
import SfxCard from './sheet/SfxCard.vue'
import TraitDetailPanel from './sheet/TraitDetailPanel.vue'
import TraitRow from './sheet/TraitRow.vue'
import DiePicker from './DiePicker.vue'
import BlueBook from './BlueBook.vue'
import LifePathWizard from './LifePathWizard.vue'
import MediaImage from './MediaImage.vue'
import Button from '@/components/ui/Button.vue'
import TraitInstanceEditor from '@/components/ui/TraitInstanceEditor.vue'
import RollTableMenu from './gm/RollTableMenu.vue'
import { ancestorsOf, canPickUp, carriedNegatives, challengeRemaining, childrenOf, countDescendants, countSetPicks, descendantsOf, hasContents, isContainer, isOpenContainer, rootAnchor, sortSetTraits, subtreeContains } from '../utils/traitTree.js'
import { splitRefunds } from '../utils/poolSpends.js'

const props = defineProps({
  entityId: { type: String, default: null },  // null = GM free-roam (B95); guards at use sites
  universe: { type: String, default: 'earth' },
  phase: { type: String, default: 'adding' },
  embedded: { type: Boolean, default: false },
  gmMode: { type: Boolean, default: false },
  externalPoolSources: { type: Array, default: null },
  overrideEntityId: { type: String, default: null },
  viewerEntityId: { type: String, default: null },
  playerOwnedEntityIds: { type: Array, default: () => [] },
  visible: { type: Boolean, default: true },
  playerId: { type: String, default: '' },
  mainEntityId: { type: String, default: '' },
})

const emit = defineEmits(['addToPool', 'removeFromPool', 'splitDie', 'removeByTsId', 'retractNegative', 'sfxToggled', 'stampSfx', 'openSettings', 'sheetViewChange'])

function displayName(name) {
  return name
    .split('_')
    .map(w => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ')
}

const { loading, error, graphql, triggerSfx, endSfx, spendResourceDie, recoverResourceDie, spendChallengeDie, recoverChallengeDie } = useApi()
const entityCache = useEntityCache()
const { fetchFor: fetchScheduledEvents, formatTimers } = useScheduledEvents()
const entity = ref(null)
const activeProjection = computed(() => {
  const e = entity.value
  if (!e || !e.projections) return null
  return e.projections.find((p) => p.id === e.currentProjection) || null
})
const sheetPortrait = computed(() => activeProjection.value?.sheetImage || entity.value?.sheetPortrait || '')
// Mirror sheetPortrait's resolution chain: the projection's sheet image when
// present, else the entity's resolved sheet portrait.
const sheetPortraitTransparent = computed(() => {
  if (activeProjection.value?.sheetImage) return !!activeProjection.value.sheetImageTransparent
  return !!entity.value?.sheetPortraitTransparent
})

// SFX owned at three surfaces beyond the per-trait cards:
//   - entity-level (entity.sfxIds)
//   - active projection (projection.sfxIds)
//   - trait-set-as-unit (traitSetSettings[].sfxIds)
const entitySfxIds = computed(() => entity.value?.sfxIds || [])
const projectionSfxIds = computed(() => activeProjection.value?.sfxIds || [])
// traitsetId → [{ id, sfxIds }] for the trait-set-as-unit grants.
const traitSetSettingsByTraitsetId = computed(() => {
  const m = {}
  for (const tss of (entity.value?.traitSetSettings || [])) {
    m[tss.traitsetId] = tss
  }
  return m
})

function traitsetSfxIds(ts) {
  const tss = traitSetSettingsByTraitsetId.value[ts.traitsetId]
  return (tss && tss.sfxIds) || []
}

function traitsetSettingSourceId(ts) {
  const tss = traitSetSettingsByTraitsetId.value[ts.traitsetId]
  return (tss && tss.id) || null
}
const traitSets = ref([])
const allTraitSettings = ref([])
const effectiveSettings = ref([])
const showAllTraits = ref(false)

// Running centrally-scheduled timers, reconnected to their owners for display.
const entityTimers = ref([])
const traitSettingTimers = ref([])

const timersByTraitId = computed(() => {
  const m = {}
  for (const ev of traitSettingTimers.value) {
    if (!m[ev.targetId]) m[ev.targetId] = []
    m[ev.targetId].push(ev)
  }
  return m
})

const entityTimerLabel = computed(() => {
  if (!entityTimers.value.length) return ''
  return entityTimers.value
    .map((ev) => formatTimers(ev.timers, ev.combine))
    .filter(Boolean)
    .join(' · ')
})

function traitTimerLabel(t) {
  const evs = timersByTraitId.value[t.id]
  if (!evs || !evs.length) return ''
  return evs
    .map((ev) => formatTimers(ev.timers, ev.combine))
    .filter(Boolean)
    .join(' · ')
}

async function fetchTimers() {
  const eid = props.overrideEntityId || props.entityId
  if (!eid) return
  const tsIds = (allTraitSettings.value || []).map((t) => t.id)
  const [ent, ts] = await Promise.all([
    fetchScheduledEvents('entity', eid),
    tsIds.length ? fetchScheduledEvents('trait_setting', null, tsIds) : Promise.resolve([]),
  ])
  entityTimers.value = ent || []
  traitSettingTimers.value = ts || []
}

function groupTraitSettings(settings) {
  const sets = {}
  for (const ts of settings || []) {
    const key = ts.traitsetName || 'Other'
    if (!sets[key]) sets[key] = []
    sets[key].push(ts)
  }
  return Object.entries(sets)
    .map(([name, traits]) => ({
      name,
      traits,
      traitsetId: traits[0]?.traitsetId ?? null,
      order: traits[0]?.traitsetOrder ?? 99,
      limit: traits[0]?.traitsetLimit ?? 1,
    }))
    .sort((a, b) => a.order - b.order)
    .map(({ name, traits, traitsetId, order, limit }) => ({ name, traits: sortSetTraits(traits), traitsetId, limit }))
}

function recomputeTraitSets(reason = 'unspecified') {
  const src = showAllTraits.value ? allTraitSettings.value : effectiveSettings.value
  const settings = src || []
  // Which tab a trait belongs on is the trait *set's* decision now, not the
  // rating's: a container trait carries no rating either, so `ratingType` could
  // never tell it apart from a genuinely descriptive trait.
  const onProfile = (t) => t.traitsetTab === 'PROFILE'
  profileTraits.value = settings.filter(onProfile)
  traitSets.value = groupTraitSettings(settings.filter(t => !onProfile(t)))
  // Every rebuild is a fresh array of set objects, so the list re-renders even
  // when the membership is identical — worth seeing while chasing the reload.
  perfMark('trait-sets-rebuilt', { reason, sets: traitSets.value.length })
}

// ── Relationship widget (foreign sheets only) ──────
const relationship = ref(null)
const showRelEditor = ref(false)
const relDescription = ref('')
const relInput = ref(null)
const blueBookRef = ref(null)


const activeSheetView = usePersistedRef('sheet.activeView', 'traits')  // 'traits' | 'profile' | 'lifepath' | 'bluebook' | 'relation'
watch(activeSheetView, (v) => emit('sheetViewChange', v))

const isForeignSheet = computed(() =>
  props.overrideEntityId && props.overrideEntityId !== props.viewerEntityId
)

// ── Relation tab (foreign sheets) ───────────────────────────────
// Traits hanging off *our* outgoing edge to the sheet we're looking at — what we
// hold about them (`_from == viewerEntityId`, `_to == overrideEntityId`). The tab
// only exists when such an edge carries traits; a bare edge isn't worth a tab.
const relationTraits = computed(() => relationship.value?.relationTraits || [])
const showRelationTab = computed(() => !!isForeignSheet.value && relationTraits.value.length > 0)
// `activeSheetView` is persisted, so 'relation' can outlive the edge that
// justified it (refresh, relationship removed, sheet switched). Fall back
// whenever the tab isn't available — immediate, so a stale value is caught on
// mount too. Defined after `activeSheetView`/`isForeignSheet` so the immediate
// run has both.
watch(showRelationTab, (has) => {
  if (!has && activeSheetView.value === 'relation') activeSheetView.value = 'traits'
}, { immediate: true })

const ownsCharacter = computed(() => {
  const id = props.overrideEntityId || props.entityId
  if (!props.playerOwnedEntityIds?.length) return false
  return props.playerOwnedEntityIds.includes(id)
})

// ── Projection (body) name — the sheet's undertitle ──────────────
// The title is always the character's name; the body they're currently in is
// named underneath it. Only your own sheet edits it — on a foreign sheet the
// name is read-only (the GM panel owns projection editing).
const editingProjectionName = ref(false)
const projectionNameValue = ref('')
const projectionNameInput = ref(null)
const savingProjectionName = ref(false)
const projectionSubtitle = computed(() => (activeProjection.value?.name || '').trim())
const canEditProjectionName = computed(() => !isForeignSheet.value && !!activeProjection.value)

function startProjectionNameEdit() {
  projectionNameValue.value = projectionSubtitle.value
  editingProjectionName.value = true
  nextTick(() => projectionNameInput.value?.focus())
}

async function commitProjectionName() {
  if (!editingProjectionName.value) return
  editingProjectionName.value = false          // also guards double-commit on blur+enter
  const projection = activeProjection.value
  if (!projection || savingProjectionName.value) return
  const name = projectionNameValue.value.trim()
  if (name === projectionSubtitle.value) return
  savingProjectionName.value = true
  try {
    await graphql(
      `mutation($id: ID!, $name: String) { updateProjection(projectionId: $id, name: $name) { id name } }`,
      { id: projection.id, name },
    )
    await fetchEntity('projection-name-save')
  } catch (e) {
    console.error('updateProjection failed:', e)
    alert('Could not rename this projection.')
  } finally {
    savingProjectionName.value = false
  }
}


// Resolved human-readable names
const locationName = ref('')
const universeName = ref('')
const universeNames = ref({})  // universe key/id → display name

// Trait-set navigation — at most one set drilled into at a time.
const activeSetName = ref(null)
// Traits with an EMPTY rating type, shown flat on the profile tab.
const profileTraits = ref([])

// ── Containers ────────────────────────────────────────────────────
// A container collapses until it is opened. The open set is persisted like the
// sheet's other state because the sheet refetches constantly (SSE, mutations);
// a container that snapped shut on every refetch would be unusable.
const expandedContainers = usePersistedRef('sheet.expandedContainers', [])
function isExpanded(t) {
  return expandedContainers.value.includes(t.id)
}
function toggleExpand(t) {
  expandedContainers.value = isExpanded(t)
    ? expandedContainers.value.filter((id) => id !== t.id)
    : [...expandedContainers.value, t.id]
}
function containerCount(t) {
  return countDescendants(t)
}

// ── Drag a trait into a container ────────────────────────────────
// Direct manipulation, and the reason no authoring is needed first: nothing on
// the write path checks a container against the registry's nominations, so any
// trait can go into any container.
//
// Which ROOT rows carry a grip: only while some open container can receive them
// (see isOpenContainer), so grips never clutter an ordinary sheet, and a
// container is never draggable into itself or into its own descendants.
const draggableRowIds = computed(() => {
  const roots = currentSet.value?.traits || []
  const open = []
  const collect = (list) => {
    for (const t of list || []) {
      if (isOpenContainer(t, isExpanded(t))) open.push(t)
      collect(childrenOf(t))
    }
  }
  collect(roots)
  const ids = new Set()
  for (const t of roots) {
    if (open.some((c) => c.id !== t.id && !subtreeContains(t, c.id))) ids.add(t.id)
  }
  return ids
})

// Depth decides too — see canPickUp: a nested row is pickable only when it sits
// directly inside a container, never deeper.
function canDrag(t, depth = 0, insideContainer = false) {
  return canPickUp({ depth, insideContainer, rootHasDestination: draggableRowIds.value.has(t.id) })
}

function dragPayload(t) {
  return { id: t.id, nested: t.fromType === 'traitsetting', parent: t.parentTraitsettingId || null }
}

const { dragging, source, over, touchStart, dragStart, dragOver, dragLeave, drop, dragEnd } = useDragDrop({
  // A container row takes the trait. Any OTHER row means "out of its container"
  // — back to the top level of the set. Using every non-container row as that
  // zone is deliberate: on touch the target has to be forgiving, and the row you
  // drag past on the way out of an indented list is exactly the one above the
  // container.
  resolveTarget: (el) => {
    const row = el && el.closest ? el.closest('[data-ts-id]') : null
    if (!row) return null
    return row.dataset.dropContainer ? { id: row.dataset.dropContainer } : { id: null }
  },
  ghostSource: (el) => (el && el.closest ? el.closest('[data-ts-id]') : el),
  onCommit: ({ from, to }) => {
    suppressClicks()
    if (to.id) {
      if (to.id !== from.parent) moveTraitInto(from.id, to.id)
    } else if (from.nested) {
      moveTraitOut(from.id)
    }
  },
})

async function moveTraitInto(traitSettingId, containerId) {
  if (!traitSettingId || !containerId || traitSettingId === containerId) return
  perfMark('trait-move-start', { traitSettingId, containerId })
  const result = await graphql(`mutation($id: ID!, $input: TraitSettingUpdateInput!) {
    updateTraitSetting(id: $id, input: $input) { id fromType parentTraitsettingId }
  }`, {
    id: traitSettingId,
    input: { fromType: 'traitsetting', parentTraitsettingId: containerId },
  })
  // graphql() returns null on error rather than throwing; the message is already
  // in `error`, and moving on would refetch a sheet that did not change.
  if (!result) return
  // Show where it went: open the container so the trait that just landed in it
  // is visible instead of appearing to have vanished.
  if (!expandedContainers.value.includes(containerId)) {
    expandedContainers.value = [...expandedContainers.value, containerId]
  }
  await fetchEntity('trait-move-in')
}

async function moveTraitOut(traitSettingId) {
  // Come out as whatever anchors the chain: a child of a morph container returns
  // to morph on the same body rather than silently becoming ego. Mirrors how
  // nesting inherits its anchor.
  const anchor = rootAnchor(currentSet.value?.traits || [], traitSettingId)
  const input = anchor && anchor.fromType === 'projection' && anchor.projectionId
    ? { fromType: 'projection', projectionId: anchor.projectionId }
    : { fromType: 'entity' }
  perfMark('trait-move-out-start', { traitSettingId, to: input.fromType })
  const result = await graphql(`mutation($id: ID!, $input: TraitSettingUpdateInput!) {
    updateTraitSetting(id: $id, input: $input) { id fromType parentTraitsettingId }
  }`, { id: traitSettingId, input })
  if (!result) return
  await fetchEntity('trait-move-out')
}

function onTraitDragStart(e, t) { dragStart(e, dragPayload(t)) }
function onGripTouchStart(e, t) { touchStart(e, dragPayload(t), { instant: true }) }
function onTraitDragOver(e) { dragOver(e) }
function onTraitDragLeave() { dragLeave() }
function onTraitDrop(e) { drop(e) }
function onTraitDragEnd() { dragEnd() }
function isDragOver(t) { return over.value?.id === t.id }
function isDragging(t) { return dragging.value && source.value?.id === t.id }

// A drop lands on the row under the pointer and the browser then fires a click
// there, which would toggle the container we just dropped into. Swallow it.
let suppressClickUntil = 0
function clickSuppressed() { return Date.now() < suppressClickUntil }
function suppressClicks() { suppressClickUntil = Date.now() + 200 }

function openSet(name) {
  activeSetName.value = name
  // Containers start closed every time a set is opened: their contents are
  // something you look into deliberately, not state carried over from last time.
  expandedContainers.value = []
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
  if (activeSheetView.value === 'relation') return relationTraits.value
  if (activeSheetView.value === 'profile') return profileTraits.value
  return currentSet.value?.traits || []
})

const currentSetReachedLimit = computed(() => {
  if (!currentSet.value || !currentSet.value.limit) return false
  // Counts *picks*, not settings: a sub-trait rides its parent, while a
  // container contributes its children instead of itself.
  return countSetPicks(currentSet.value.traits, isInPool) >= currentSet.value.limit
})

const nextSet = computed(() => {
  const idx = traitSets.value.findIndex(ts => ts.name === activeSetName.value)
  if (idx === -1) return null
  return traitSets.value[idx + 1] || null
})

const prevSet = computed(() => {
  const idx = traitSets.value.findIndex(ts => ts.name === activeSetName.value)
  return idx > 0 ? traitSets.value[idx - 1] : null
})

// Both directions land the same way: the set becomes active and its containers
// start closed, so a set you step into reads the same however you got there.
function goToSet(ts) {
  if (!ts) return
  activeSetName.value = ts.name
  expandedContainers.value = []
}

function goToNextSet() { goToSet(nextSet.value) }
function goToPrevSet() { goToSet(prevSet.value) }

// SFX usage tracking — reset per dice pool cycle
const sfxActivations = ref({})
const seededInFlight = ref(new Set())  // what the server last reported as in flight
const sfxCatalog = ref({})  // sfxId → { name, description }
const availableSfxIds = ref(null)  // null = not loaded; else the conditions-filtered id list
// The rules the place you're standing in lends you: [{ locationId, locationName,
// sfxIds }]. Nothing is attached to the entity — this is where the place's own
// rules get a button to be pressed, which attached-only strips never gave them.
const placeRuleGroups = ref([])
const rollTableMenu = ref(null)  // { sfxId, tableId, name } | null
const SFX_PHASES = {
  'sfx-hinder': ['adding'],
  'sfx-spray-n-pray': ['adding'],
}
const poolSources = ref([])

// Trait-setting ids routed to the opponent's pool (negative traits offered
// during a contest) — highlighted in the sheet and counted toward the set limit.
const offeredTraits = ref(new Set())

// Dice spent out of a trait into the pool, kept so they can be refunded if the
// pool drops them before rolling. { tsId: [{ die, kind }, ...] } — `kind` picks
// the recover path ('resource' → spent ledger, 'challenge' → outright refund).
const refundableSpends = ref({})


const RATING_TYPES = [
  { id: 'STATIC', label: 'Static' },
  { id: 'RESOURCE', label: 'Resource' },
  { id: 'CHALLENGE', label: 'Challenge' },
  { id: 'EMPTY', label: 'Empty' },
]

let longPressTimer = null

// ── Add trait picker ────────────────────────────
const showAddTrait = ref(false)
const addPhase = ref('sets')
const addMode = ref('trait')  // 'trait' | 'relationship'
const availableTraitSets = ref([])
const availableTraits = ref([])
const selectedTraitSet = ref(null)

const filteredTraits = computed(() => {
  if (!selectedTraitSet.value) return []
  // A set with allow_duplicates can hold several instances of the same trait
  // definition (e.g. two weapons, distinguished by statement), so don't drop
  // already-assigned traits there. Otherwise a trait may be assigned once.
  if (selectedTraitSet.value.allowDuplicates) {
    return availableTraits.value.filter(t => t.traitsetId === selectedTraitSet.value.id)
  }
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
  addMode.value = 'trait'
  addPhase.value = 'sets'
  selectedTraitSet.value = null
  // Trait sets come from the entity being viewed (a foreign location may live
  // in a different universe than the acting character).
  const u = entity.value?.currentUniverse || props.universe
  const [tsData, trData] = await Promise.all([
    graphql(`query($u: String!) { traitsetsByUniverse(universe: $u) { id name order limit entityTypes allowDuplicates } }`, { u }),
    graphql(`query($u: String!) { traitsByUniverse(universe: $u) { id name traitsetId defaultDieType defaultRatingType } }`, { u }),
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
  // If already drilled into a trait set, preselect it and jump straight to its traits.
  if (activeSetName.value) {
    const current = availableTraitSets.value.find(ts => ts.id === currentSet.value?.traitsetId)
    if (current) selectSet(current)
  }
  showAddTrait.value = true
}

async function openAddRelationshipTrait() {
  addMode.value = 'relationship'
  addPhase.value = 'sets'
  selectedTraitSet.value = null
  // Relationship traits are universe-agnostic: offer every trait set that is
  // usable on the 'relation' entity type.
  const tsData = await graphql(`query { traitsets { id name order limit entityTypes allowDuplicates } }`)
  const relationSets = (tsData?.traitsets || [])
    .filter(ts => (ts.entityTypes || []).includes('RELATION'))
    .sort((a, b) => (a.order ?? 99) - (b.order ?? 99))
  availableTraitSets.value = relationSets
  const ids = relationSets.map(ts => ts.id)
  if (ids.length) {
    const trData = await graphql(
      `query($ids: [ID!]!) { traitsByTraitsets(traitsetIds: $ids) { id name traitsetId defaultDieType defaultRatingType } }`,
      { ids },
    )
    availableTraits.value = trData?.traitsByTraitsets || []
  } else {
    availableTraits.value = []
  }
  showAddTrait.value = true
}

function selectSet(ts) {
  selectedTraitSet.value = ts
  addPhase.value = 'traits'
}

async function addTrait(trait) {
  if (addMode.value === 'relationship') {
    const result = await graphql(`mutation($from: ID!, $to: ID!, $traitId: ID!, $die: DieType!) {
      addRelationshipTrait(fromEntityId: $from, toEntityId: $to, traitId: $traitId, die: $die) { id }
    }`, {
      from: props.viewerEntityId,
      to: props.overrideEntityId,
      traitId: trait.id,
      die: (trait.defaultDieType || 'd6').toUpperCase(),
    })
    if (!result?.addRelationshipTrait) {
      console.error('addRelationshipTrait failed:', error.value || 'unknown error')
      return
    }
    showAddTrait.value = false
    addPhase.value = 'sets'
    selectedTraitSet.value = null
    // A relationship trait hangs off *our* outgoing edge to this sheet, so it
    // arrives through the relationship query — the entity refresh the other path
    // uses would load the other side's settings and never show it (the relation
    // tab's rows are `relationTraits`, not the viewed entity's).
    const newRelationshipId = result.addRelationshipTrait.id
    try {
      await fetchRelationship()
      openEditorForNewTrait(newRelationshipId, { relation: true })
    } catch (e) {
      console.error('[sheet] add: refreshed but could not open the editor', e)
    }
    return
  }

  const result = await graphql(`mutation($eid: ID!, $input: TraitSettingInput!) {
    addTraitSetting(entityId: $eid, input: $input) { id name traitsetName }
  }`, {
    eid: props.overrideEntityId || props.entityId,
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
  // Land on the trait with its editor open — the whole point of adding one from
  // the sheet is that you then set it up (dice, rating, statement), so send the
  // player straight there instead of leaving them on whatever set was showing.
  const newSettingId = result.addTraitSetting.id
  try {
    await fetchEntity('add-trait')
    openEditorForNewTrait(newSettingId)
  } catch (e) {
    // The trait is added either way — only the landing failed, so say that
    // rather than letting the editor's absence read as a broken add.
    console.error('[sheet] add: refreshed but could not open the editor', e)
  }
}

/**
 * Open the full-panel editor on a just-added trait, from wherever it landed.
 *
 * `editingTrait` resolves its id out of the lists the sheet is rendering, so
 * this must run *after* the refetch — and it is why the editor cannot be opened
 * optimistically against a setting the client has not seen yet.
 *
 * A trait whose set the universe gate excludes is added but has no row to open;
 * the console says so rather than the click looking like it did nothing.
 */
function openEditorForNewTrait(id, { relation = false } = {}) {
  if (!id) return
  const source = relation
    ? (relationTraits.value || [])
    : ((showAllTraits.value ? allTraitSettings.value : effectiveSettings.value) || [])
  const setting = source.find(t => t.id === id)
  if (!setting) {
    console.warn('[sheet] added trait is not in the visible trait lists:', id)
    return
  }
  if (relation) {
    // Where it was added from, and where its rows live.
    activeSheetView.value = 'relation'
  } else if (setting.traitsetTab === 'PROFILE') {
    activeSheetView.value = 'profile'
  } else {
    activeSheetView.value = 'traits'
    const target = traitSets.value.find(s => s.name === setting.traitsetName)
    // Same landing as the set nav: the set becomes active, its containers closed.
    if (target) goToSet(target)
    else activeSetName.value = setting.traitsetName
  }
  startEdit(setting)
}

// ── Trait detail (read-only) ────────────────────────────────────
// The row's third click zone. Playing the trait moved to the rating zone; the
// name / statement / empty space of the row now opens the trait read-only, with
// its full SFX, notes and tags. `contextmenu` still opens the editor.
const detailTrait = ref(null)

// Projection options with their display names resolved, for the editor's chip.
const projectionChoices = computed(() =>
  (entity.value?.projections || []).map(p => ({ id: p.id, name: p.name || universeDisplay(p.originUniverse) }))
)

// Helpers the read-only trait detail needs; functions only, so the child can
// take them as one object without any unwrapping.
const detailApi = {
  canPlayTrait, playTrait, ratingTypeLabel, challengeProgressLabel, challengeRemainingGroups, detailContext,
  displayName, sfxCardModel, activateSfx,
}

// The inline trait editor's draft state + actions (see composables/useTraitEditor.js).
const {
  editingTraitId, editingTrait, availableSubtraits,
  editDice, editRatingType, editPolarity, editCapacity, editStatement, editNotes,
  editSfxIds, editIsEgo, editProjectionId, showProjectionPicker, acquirableSfxIds,
  editTags, tagSuggestions,
  editProjectionOptions, editProjectionName,
  deleteCountdown, deletingTraitId,
  startEdit, cancelEdit, onDeleteClick, doSave,
  toggleEgo, togglePolarity, toggleProjectionPicker, selectProjection, toggleSfx,
  onEditorRatingType, onEditorChange, onEditorFieldBlur,
  addSubTrait, removeSubTrait, onStatementInput, splitStatement, recoverSpentDie,
} = useTraitEditor({
  props, entity, traitSets, profileTraits, relationTraits, detailTrait, graphql,
  fetchEntity, recomputeTraitSets, recoverResourceDie, universeDisplay,
})

// Helpers the list rows call; functions only, like detailApi. It sits below the
// useTraitEditor destructure on purpose — it closes over `startEdit` (a const,
// so creating the object earlier would hit the TDZ).
const traitRowApi = {
  isKnown, isInPool, isOffered, displayName, traitTimerLabel, isResourceDepleted,
  traitDiceGroups, resourceDiceGroups, resourceSpentGroups, challengeRemainingGroups,
  spendResourceGroup, spendChallengeGroup, challengeProgressLabel,
  resolvedDieType, resourceDisplay, sfxCardModel, activateSfx,
  openTraitDetail, startEdit, playTrait, onTouchStart, onTouchEnd,
  isContainer, isExpanded, toggleExpand, containerCount, hasContents,
  onTraitDragStart, onGripTouchStart, onTraitDragOver, onTraitDragLeave, onTraitDrop, onTraitDragEnd,
  isDragOver, isDragging, clickSuppressed, canDrag,
}

function openTraitDetail(t) {
  // A touch long-press fires startEdit on touchstart and the click on release,
  // so the editor can already be open by the time this runs — don't stack the
  // detail panel behind it.
  if (editingTraitId.value) return
  detailTrait.value = t
}

function closeTraitDetail() {
  detailTrait.value = null
}

// The detail panel sits ahead of the tab branches in the render chain, so a tab
// change would otherwise leave it covering the newly chosen view.
watch(activeSheetView, () => { detailTrait.value = null })

function ratingTypeLabel(t) {
  return RATING_TYPES.find(rt => rt.id === t.ratingType)?.label || t.ratingType || ''
}

// Same gates playTrait() applies — the detail only offers the play affordance
// when playing would actually do something. An EMPTY (profile) or depleted
// trait has no die to play, so it gets no hint and no sub-trait play button.
function canPlayTrait(t) {
  if (props.phase !== 'adding' || t.enabled === false) return false
  if (t.ratingType === 'EMPTY') return false
  return (t.dice || []).length > 0
}

// Rows for the detail's CONTEXT block. Only what actually applies is returned,
// so the block collapses entirely for a plain static trait.
function detailContext(t) {
  const rows = []
  if (t.ego === false) {
    rows.push({ label: 'body', value: t.universe ? `projection · ${universeDisplay(t.universe)}` : 'projection' })
  }
  if (t.relationshipContactName) rows.push({ label: 'toward', value: t.relationshipContactName })
  if (t.knownTo?.length) {
    rows.push({ label: 'known to', value: `${t.knownTo.length} ${t.knownTo.length === 1 ? 'entity' : 'entities'}` })
  }
  const timer = traitTimerLabel(t)
  if (timer) rows.push({ label: 're-enables', value: timer })
  return rows
}

// ── Playing a trait (rating zone) ───────────────────

// A trait and its sub-traits are ONE pool pick: `countSetPicks` counts the
// subtree once, so the set limit is satisfied by whichever member you touch.
// The old app completed the group from either end and this keeps that:
//
//   - playing a **sub-trait** pulls its ancestor chain in, so the pick is whole
//     (`click_subtrait` → `play_trait()` on the parent);
//   - playing a trait also pushes the **negative** sub-traits it carries — in a
//     contest those route to the opposition (`DiceRoller.addFromSheet`);
//   - removing a trait clears its whole subtree, so no orphan dice linger
//     (the old `remove_traitsetting_dice` loop over subtraits).
//
// Only **static** negative children ride along automatically: a resource or
// challenge sub-trait is *spent*, and spending is the player's deliberate act,
// not a side effect of playing its parent.
// The graph walks (`ancestorsOf` / `descendantsOf` / `carriedNegatives`) live in
// utils/traitTree.js with the rest of the group semantics.
function settingSearchSpace() {
  return [...(effectiveSettings.value || []), ...(allTraitSettings.value || [])]
}

// The negative sub-traits a trait carries when it is played. `skipId` is the
// trait whose own dice `playTrait` is about to push: without it, playing a
// negative sub-trait would push it once here and once there, and the dice
// layer's toggle would add then immediately remove it.
function playBaggage(t, skipId = null) {
  for (const child of carriedNegatives(t)) {
    if (child.id === skipId) continue
    if (child.enabled === false || isInPool(child)) continue
    emitTraitDice(child)
  }
}

// The related members of `t`'s group. The clicked trait's own dice are handled
// by `playTrait`; this only completes (or dismantles) the group around it.
function cascadeGroup(t) {
  if (isInPool(t)) {
    // Removing a trait takes its subtree out of the pool, and the group's
    // negative baggage back out of whatever pool it was routed to. A
    // complication must not outlive the trait that carried it.
    for (const child of descendantsOf(t)) {
      if (isInPool(child)) emit('removeByTsId', child.id)
    }
    for (const member of [t, ...descendantsOf(t)]) {
      for (const carried of carriedNegatives(member)) {
        if (!isOffered(carried)) continue
        emit('retractNegative', {
          tsId: carried.id, source: carried.name, label: displayName(carried.name),
        })
      }
    }
    return
  }
  // Playing a sub-trait completes its pick: bring the ancestors in first.
  // A resource or challenge ancestor is *spent*, not played, so it is left
  // alone — its own row click owns that decision.
  for (const ancestor of ancestorsOf(t, settingSearchSpace())) {
    if (ancestor.ratingType === 'RESOURCE' || ancestor.ratingType === 'CHALLENGE') continue
    if (isInPool(ancestor) || !canPlayTrait(ancestor)) continue
    emitTraitDice(ancestor)
    playBaggage(ancestor, t.id)
  }
  playBaggage(t, t.id)
}

// Push one trait's rating into the pool. Negativity rides the payload so the
// dice layer can route it (opposition during a contest).
function emitTraitDice(t) {
  const dice = (t.dice || []).map(d => (typeof d === 'string' ? d.toLowerCase() : d))
  if (!dice.length) return  // no die rating — nothing to add
  const payload = {
    source: t.name,
    label: displayName(t.name),
    tsId: t.id,
    negative: t.polarity === 'NEGATIVE',
    armedSfxIds: armedSfxIdsForTrait(t),
  }
  // Multi-die traits contribute one pool die per rating entry.
  if (dice.length > 1) emit('addToPool', { ...payload, dice })
  else emit('addToPool', { ...payload, die: dice[0] })
}

async function playTrait(t) {
  if (props.phase !== 'adding') return
  if (t.enabled === false) return  // disabled trait contributes no dice

  // Complete (or dismantle) the group before the clicked trait's own dice.
  cascadeGroup(t)

  // Resource traits: the row click spends only when the pool has a single
  // die type; mixed-type resources are spent per die group.
  if (t.ratingType === 'RESOURCE') {
    const types = [...new Set((t.dice || []).map(d => (typeof d === 'string' ? d.toLowerCase() : d)))]
    if (types.length === 1) await spendResourceGroup(t, types[0])
    return
  }

  // Challenge traits: same single-vs-mixed-type split as resources. The row
  // click spends one die; mixed-type pools are spent per die group.
  if (t.ratingType === 'CHALLENGE') {
    const types = [...new Set((t.dice || []).map(d => (typeof d === 'string' ? d.toLowerCase() : d)))]
    if (types.length === 1) await spendChallengeGroup(t, types[0])
    return
  }

  emitTraitDice(t)
}

async function spendResourceGroup(t, dieType) {
  // Spend one die of the chosen type from the resource and add it to the pool.
  if (props.phase !== 'adding') return
  if (t.enabled === false) return
  await spendResourceDie(t.id, dieType)
  if (!refundableSpends.value[t.id]) refundableSpends.value[t.id] = []
  refundableSpends.value[t.id].push({ die: dieType, kind: 'resource' })
  emit('addToPool', { die: dieType, source: t.name, label: displayName(t.name), tsId: t.id, negative: t.polarity === 'NEGATIVE', resource: true, armedSfxIds: armedSfxIdsForTrait(t) })
  await fetchEntity('resource-spend')
}

async function spendChallengeGroup(t, dieType) {
  // Spend one die from a challenge pool and route it per polarity:
  // negative (doom) → destination "opposition" (plain die, routes to opposition);
  // positive (progress) → destination "pool" (flagged resource, joins own pool).
  if (props.phase !== 'adding') return
  if (t.enabled === false) return
  const destination = t.polarity === 'NEGATIVE' ? 'opposition' : 'pool'
  const res = await spendChallengeDie(t.id, dieType, destination)
  if (!res) return
  t.dice = (res.dice || []).map(d => d.toUpperCase())
  // Only a die that lands in an editable pool can be pulled back out again —
  // a doom die routed to the opposition/difficulty pool is tracked by nobody
  // here, and treating it as "missing from my own pool" would refund it while
  // it is legitimately sitting in the difficulty pool.
  if (res.resource) {
    if (!refundableSpends.value[t.id]) refundableSpends.value[t.id] = []
    refundableSpends.value[t.id].push({ die: res.die.toLowerCase(), kind: 'challenge' })
  }
  emit('addToPool', {
    die: res.die.toLowerCase(),
    source: t.name,
    label: displayName(t.name),
    tsId: t.id,
    negative: t.polarity === 'NEGATIVE',
    resource: res.resource,
    armedSfxIds: armedSfxIdsForTrait(t),
  })
  await fetchEntity('challenge-spend')
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

function challengeProgressLabel(t) {
  // Progress/ceiling indicator for challenge pools when a capacity is set:
  // positive → "n/m" progress toward target; negative → "n/m" against ceiling.
  if (t.ratingType !== 'CHALLENGE') return ''
  const cap = (t.capacity || []).length
  if (!cap) return ''
  return `${(t.dice || []).length}/${cap}`
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
  // Static traits render grouped dice.  Resources/challenge/empty have their
  // own rendering (resources use resourceDiceGroups/resourceSpentGroups,
  // challenge uses its own die-stack branch).
  if (t.ratingType === 'RESOURCE' || t.ratingType === 'EMPTY' || t.ratingType === 'CHALLENGE') return []
  return groupByDieType(t.dice)
}

function resourceDiceGroups(t) {
  return groupByDieType(t.dice)
}

function resourceSpentGroups(t) {
  return groupByDieType(t.spentDice)
}

// A challenge pool's unfilled capacity, rendered as ghost dice beside the dice
// that have filled it (see challengeRemaining in utils/traitTree.js).
function challengeRemainingGroups(t) {
  return groupByDieType(challengeRemaining(t))
}

function isResourceDepleted(t) {
  // Resources and challenge pools show a dimmed "depleted/empty" state when
  // their spendable dice ledger is empty.
  if (t.ratingType !== 'RESOURCE' && t.ratingType !== 'CHALLENGE') return false
  if ((t.dice || []).length) return false
  // An unfilled challenge track is not depleted — it is *waiting*, and its
  // ghost dice say so. Only a challenge with no track at all reads as depleted;
  // for a resource, an empty ledger is exactly what depleted means.
  if (t.ratingType === 'CHALLENGE') return !(t.capacity || []).length
  return true
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
  // Must agree with `currentSetReachedLimit`: a sub-trait rides its parent, so
  // the subtree counts once however many of its members are in the pool.
  return countSetPicks(ts.traits, isInPool)
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
  // Same count as the limit dots and the gate (countSetPicks): a sub-trait
  // rides its parent, so the subtree is one pick.
  const sets = traitSets.value
  const idx = sets.findIndex(s => s.name === activeSetName.value)
  if (idx !== -1) {
    const count = countSetPicks(sets[idx].traits, isInPool)
    if (sets[idx].limit && count >= sets[idx].limit) {
      const to = sets[idx + 1] ? sets[idx + 1].name : null
      // The jump the player actually sees — put it on the same timeline as the
      // fetches, so "the next set appeared, then it reloaded" is one sequence.
      if (to !== activeSetName.value) {
        perfMark('set-advanced', { from: activeSetName.value, to, picks: count, limit: sets[idx].limit })
      }
      activeSetName.value = to
    }
  }

  // Auto-recover dice that were removed from the pool before rolling
  // (e.g. via chip click in DiceRoller).  Only during adding phase —
  // once dice are rolled they stay spent.  A resource die returns through its
  // spent ledger; a challenge die is refunded outright (no ledger).
  if (props.phase !== 'adding') return
  let recovered = false
  for (const tsId of Object.keys(refundableSpends.value)) {
    const poolDice = sources.filter(s => s.tsId === tsId).map(s => s.die)
    const { keep, refunds } = splitRefunds(refundableSpends.value[tsId], poolDice)
    for (const entry of refunds) {
      if (entry.kind === 'challenge') recoverChallengeDie(tsId, entry.die)
      else recoverResourceDie(tsId, entry.die)
      recovered = true
    }
    if (keep.length) refundableSpends.value[tsId] = keep
    else delete refundableSpends.value[tsId]
  }
  if (recovered) fetchEntity('pool-dice-refunded')
}

defineExpose({ resetSfxCounts, setPoolSources, setRazmerit, setOfferedTraits, fetchEntity, fetchInFlightSfxIds, refreshBlueBook: () => blueBookRef.value?.refresh() })

function sfxActive(sfxId) {
  return (sfxActivations.value[sfxId] || 0) > 0
}

function armedSfxIdsForTrait(t) {
  // SFX attached to this trait that the player has armed (activated) this roll.
  return (t.sfxIds || []).filter(sfxId => sfxActive(sfxId))
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

// The derived natural-language rules text ("Activated: spend 1 razmerit."), as
// opposed to `description`, which is the author's flavour lead-in. Cards show
// both; the compact row cards keep to the flavour line.
function sfxCardText(sfxId) {
  return sfxCatalog.value[sfxId]?.cardText || ''
}

// A roll-table-as-menu SFX carries a single roll_table/menu effect whose
// ``target`` is the table id. Clicking it opens the picker instead of firing.
function rollTableMenuEffect(sfxId) {
  const sfx = sfxCatalog.value[sfxId]
  if (!sfx) return null
  return (sfx.effects || []).find(e => e.type === 'roll_table' && e.action === 'menu') || null
}

// A condition-blocked SFX is owned (it appears on the sheet) but its static
// conditions (e.g. source_rating, entity_type) fail at this moment, so it can't
// fire. ``null`` means availability hasn't loaded yet (don't block optimistically).
function sfxConditionBlocked(sfxId) {
  if (availableSfxIds.value == null) return false
  return !availableSfxIds.value.includes(sfxId)
}

function sfxTitle(sfxId) {
  if (sfxConditionBlocked(sfxId)) return `${sfxName(sfxId)} (conditions not met)`
  return sfxActive(sfxId) ? `Deactivate ${sfxName(sfxId)}` : `Activate ${sfxName(sfxId)}`
}

// Everything one SFX card needs, resolved once for all five strips (entity,
// projection, trait row, detail, trait-set). `disabled` reproduces the old
// inline guard so the card does not fire when the phase or a condition blocks.
// One SFX in a card strip. Where the card sits decides how much it earns:
//   'chip' — the trait teaser: the name, nothing else;
//   'card' — the entity / projection / trait-set strips: name + description;
//   'full' — the trait detail clickthrough: + the natural-language rules text
//            (the "translation" belongs in the drill-in, not in the teaser).
function sfxCardModel(sfxId, variant = 'card') {
  const blocked = sfxConditionBlocked(sfxId)
  return {
    name: sfxName(sfxId),
    description: variant === 'chip' ? '' : sfxDescription(sfxId),
    rules: variant === 'full' ? sfxCardText(sfxId) : '',
    title: sfxTitle(sfxId),
    active: sfxActive(sfxId),
    used: sfxUsed(sfxId),
    blocked,
    disabled: blocked || !sfxAllowedInPhase(sfxId),
  }
}

async function fetchAvailableSfxIds() {
  const id = props.overrideEntityId || props.entityId
  if (!id) { availableSfxIds.value = null; return }
  try {
    const data = await graphql(
      `query($id: ID!, $u: String!) { availableSfxIds(entityId: $id, universe: $u) }`,
      { id, u: props.universe },
    )
    availableSfxIds.value = (data?.availableSfxIds || []).map(String)
  } catch (e) {
    console.error('fetchAvailableSfxIds', e)
    availableSfxIds.value = null
  }
}

/**
 * Rules this entity has activated and not yet committed — the server's truth for
 * the chips' take-back state, so it survives a reload (a client-side flag would
 * forget, and the next press would re-apply instead of ending). A rule the
 * server no longer lists has ended — taken back, or its cost left the pool — so
 * its optimistic flag is cleared here rather than left to lie.
 *
 * The same round trip reads the balance: a pool save is exactly the moment a
 * rule's cost can leave, and the refund lands on the server as part of handling
 * that save — so the sheet refreshes the ledger from the server at that moment
 * instead of waiting on a push.
 */
async function fetchInFlightSfxIds(reason = 'unspecified') {
  const id = props.overrideEntityId || props.entityId
  if (!id) return
  _stampFetch('in-flight-sfx-fetch', reason)
  try {
    const data = await graphql(
      `query($id: ID!) { inFlightSfxIds(entityId: $id) entity(id: $id) { razmerit } }`,
      { id },
    )
    const ids = (data?.inFlightSfxIds || []).map(String)
    for (const sfxId of seededInFlight.value) {
      if (!ids.includes(sfxId)) sfxActivations.value[sfxId] = 0
    }
    for (const sfxId of ids) {
      sfxActivations.value[sfxId] = 1
    }
    seededInFlight.value = new Set(ids)
    const balance = data?.entity?.razmerit
    if (balance != null) setRazmerit(balance, id)
  } catch (e) {
    console.error('fetchInFlightSfxIds', e)
  }
}

async function fetchPlaceSfxRules() {
  const id = props.overrideEntityId || props.entityId
  if (!id) { placeRuleGroups.value = []; return }
  try {
    const data = await graphql(
      `query($id: ID!, $u: String!) { placeSfxRules(entityId: $id, universe: $u) { locationId locationName sfxIds } }`,
      { id, u: props.universe },
    )
    placeRuleGroups.value = data?.placeSfxRules || []
  } catch (e) {
    console.error('fetchPlaceSfxRules', e)
    placeRuleGroups.value = []
  }
}

// A place's rule wears the same card as the entity's own, with one difference:
// a rule that fires on its own when the world moves isn't something you press,
// so it reads its rules line and stays inert instead of looking like a button.
function placeCardModel(sfxId) {
  const model = sfxCardModel(sfxId)
  const trigger = sfxCatalog.value[sfxId]?.trigger
  if (trigger && trigger !== 'manual') {
    return { ...sfxCardModel(sfxId, 'full'), disabled: true, blocked: true, title: 'Fires by itself.' }
  }
  return model
}

async function fetchSfxCatalog() {
  try {
    const r = await fetch('/api/v1/graphql', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query: `query { sfxs { id name description trigger cardText effects { timing type action target entity result } } }` }),
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
  refundableSpends.value = {}
}

const QUERY = `
  # Every trait-setting field, shared by all levels of the tree. A nested trait
  # opens the same detail panel and the same editor as a top-level one, and can
  # itself be a container — so it needs the same field set, not a subset.
  fragment TraitNode on TraitSetting {
    id
    traitId
    traitsetId
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
    capacity
    polarity
    enabled
    traitsetOrder
    traitsetLimit
    traitsetTab
    knownTo
    possibleSfxIds
    tags
    registryTags
    relationshipContactId
    relationshipContactName
    relationshipContactType
    relationshipType
    possibleSubtraitIds
    parentTraitsettingId
  }
  # GraphQL requires every nesting level spelled out, so the chain is linear and
  # each link adds exactly one level: Depth2 = 2 levels, Depth3 = 3. The sheet
  # asks for QUERY_DEPTH (4) in total — a top-level trait plus three. Keep this
  # in step with QUERY_DEPTH in utils/traitTree.js.
  fragment TraitNodeDepth2 on TraitSetting {
    ...TraitNode
    subTraitSettings { ...TraitNode }
  }
  fragment TraitNodeDepth3 on TraitSetting {
    ...TraitNode
    subTraitSettings { ...TraitNodeDepth2 }
  }

  query($id: ID!) {
    entity(id: $id) {
      id
      type
      name
      razmerit
      currentUniverse
      currentLocation
      currentProjection
      backgroundImage
      sheetPortrait
      sheetPortraitTransparent
      sfxIds
      projections {
        id originUniverse universe name sheetImage sheetImageTransparent currentLocation transversalType sfxIds
      }
      traitSetSettings {
        id traitsetId sfxIds
      }
      traitSettings {
        ...TraitNode
        subTraitSettings { ...TraitNodeDepth3 }
      }
      effectiveTraitSettings {
        ...TraitNode
        subTraitSettings { ...TraitNodeDepth3 }
      }
    }
  }
`

// ── Fetch attribution (temporary diagnostic) ─────────────────────────────
// Symptom under investigation: adding a trait to the pool makes the *next* set
// appear to reload. useApi already logs every GraphQL call, but not *why* it
// fired — so each fetch is stamped with the caller that asked for it, numbered
// per kind, and flagged when a second one lands inside the same interaction.
// Console-only; strip this block and the reason arguments once the cause is
// fixed and the paths are quiet again.
const _fetchLog = {}
function _stampFetch(kind, reason) {
  const now = performance.now()
  const s = _fetchLog[kind] || (_fetchLog[kind] = { n: 0, lastAt: 0 })
  const gap = s.lastAt ? Math.round(now - s.lastAt) : null
  s.n += 1
  s.lastAt = now
  const repeat = gap !== null && gap < 1500
  console.log(`[diag] ${kind} #${s.n} reason=${reason}${gap === null ? '' : ` gap=${gap}ms`}${repeat ? '   <<< fires again inside one interaction' : ''}`)
  if (repeat) {
    const chain = (new Error().stack || '').split('\n').slice(2, 6).map(l => l.trim()).join('  <-  ')
    console.log(`[diag] ${kind} #${s.n} caller chain: ${chain}`)
  }
  perfMark(kind, { reason, n: s.n, gap })
}

async function fetchEntity(reason = 'unspecified') {
  const id = props.overrideEntityId || props.entityId
  if (!id) return
  _stampFetch('entity-fetch', reason)
  const data = await graphql(QUERY, { id })
  if (data?.entity) {
    entityCache.setSheet(id, data.entity)
    applyEntity(data.entity)
    perfMark('sheet-loaded', { id, cached: false })
  }
}

// Render the cached sheet immediately when we have it; otherwise fetch fresh.
// Used on open/switch so re-opening a sheet doesn't re-download the whole entity.
let inflightLoad = null // { id, promise } — dedupe concurrent cache-miss loads

function loadCachedEntity() {
  const id = props.overrideEntityId || props.entityId
  if (!id) return
  const cached = entityCache.getSheet(id)
  if (cached) {
    applyEntity(cached)
    perfMark('sheet-loaded', { id, cached: true })
    return
  }
  // Dedupe: a concurrent load for the same entity (e.g. the universe watcher
  // refiring while the first fetch is still in flight) shares the in-flight
  // request instead of starting a second full fetch.
  if (inflightLoad && inflightLoad.id === id) {
    return
  }
  const promise = fetchEntity('cache-miss')
  inflightLoad = { id, promise }
  promise.finally(() => {
    if (inflightLoad && inflightLoad.id === id) inflightLoad = null
  })
}

function applyEntity(e) {
  entity.value = e
  resolveNames(e)
  allTraitSettings.value = e.traitSettings || []
  effectiveSettings.value = e.effectiveTraitSettings || []
  recomputeTraitSets('entity-applied')
  fetchTimers()
  fetchAvailableSfxIds()
  fetchInFlightSfxIds()
  fetchPlaceSfxRules()
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

async function activateSfx(sfxId, sourceId = null) {
  const menu = rollTableMenuEffect(sfxId)
  if (menu && menu.target) {
    const isSupportCast = sfxId === 'sfx-roll-support-cast'
    let tableId = menu.target
    if (isSupportCast) {
      // B65 — support-cast tables are universe-scoped: resolve from the main's
      // current universe (falling back to the generic table) before opening.
      const mainId = props.mainEntityId || props.entityId
      const data = await graphql(
        `query($id: ID!) { supportCastTableId(entityId: $id) }`,
        { id: mainId },
      )
      tableId = data?.supportCastTableId || null
      if (!tableId) return
    }
    rollTableMenu.value = {
      sfxId, tableId, name: sfxName(sfxId),
      mode: isSupportCast && props.playerId && props.mainEntityId
        ? 'create-support' : 'apply',
    }
    return
  }

  const active = sfxActive(sfxId)

  if (!active) {
    // Activate. If the SFX declares a source kind, pass the surface it was
    // clicked from (the trait instance id) as ``source_id`` so the backend
    // binds it to the declared ``{variable}``.
    await triggerSfx(props.entityId, sfxId, props.universe, { phase: props.phase, ...(sourceId ? { source_id: sourceId } : {}) })
    sfxActivations.value[sfxId] = 1
    // Re-stamp dice already in the pool (armed after adding).
    const tsId = findTsIdForSfx(sfxId)
    if (tsId) emit('stampSfx', { tsId, sfxId })
    await fetchEntity('sfx-activate')

    if (sfxId === 'sfx-hinder') {
      const tsId = findTsIdForSfx('sfx-hinder')
      emit('removeByTsId', tsId)
      // Stamp the die with the rule that put it there: the pool is the ledger, so
      // taking this die back out is how the Hinder is taken back.
      emit('addToPool', { die: 'd4', source: 'hinder', label: 'Hinder d4', tsId, armedSfxIds: [sfxId] })
    }
    if (sfxId === 'sfx-spray-n-pray') {
      emit('splitDie', { source: 'shooting', label: 'Spray' })
    }
    emit('sfxToggled', { sfxId, active: true })
  } else {
    // Deactivate (reverse)
    sfxActivations.value[sfxId] = 0

    // Take back the activation: every undo it still owes is applied now (the
    // razmerit it earned, the die it added), and what was still waiting on a
    // roll is dropped. A rule with nothing in flight is a no-op here.
    await endSfx(props.entityId, sfxId)

    // The take-back above (`endSfx`) already refunded what this rule earned or
    // spent — the legacy `{reverse: true}` call would have reversed the same
    // money a second time. What is left here is the pool edit.
    if (sfxId === 'sfx-hinder') {
      emit('removeByTsId', findTsIdForSfx('sfx-hinder'))
    }
    if (sfxId === 'sfx-spray-n-pray') {
      emit('removeFromPool', 'shooting-a')
      emit('removeFromPool', 'shooting-b')
    }
    emit('sfxToggled', { sfxId, active: false })
    await fetchEntity('sfx-end')
  }
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
    return true
  }
  return false
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
watch(showAllTraits, () => recomputeTraitSets('show-all-toggled'))

// ── Relationship fetch ─────────────────────────────
async function fetchRelationship() {
  if (!props.viewerEntityId || !props.overrideEntityId) {
    relationship.value = null
    return
  }
  const query = `
    query($viewer: ID!, $target: ID!) {
      relationship(fromEntityId: $viewer, toEntityId: $target) {
        id
        description
        relationTraits {
          id
          traitId
          traitsetId
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
          capacity
          polarity
          enabled
          traitsetOrder
          traitsetLimit
          traitsetTab
          knownTo
          possibleSfxIds
        tags
        registryTags
          relationshipContactId
          relationshipContactName
          relationshipContactType
          relationshipType
          possibleSubtraitIds
        }
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

watch(() => props.overrideEntityId, () => {
  if (isForeignSheet.value) fetchRelationship()
  if (!ownsCharacter.value && activeSheetView.value === 'bluebook') activeSheetView.value = 'traits'
  // The relation view belongs to one specific edge — don't carry it across sheets.
  if (activeSheetView.value === 'relation') activeSheetView.value = 'traits'
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
  position: relative;
  min-height: 0;
}

/* Transparent (background-removed) sheet portraits: no circular crop — the
   character cutout pops out over the sheet's top edge. Bottom-only border +
   radius anchor it to the sheet; the top stays open and uncropped. */
.sheet-embedded.transparent-portrait {
  --portrait-size: 76px;
  --portrait-lift: 34px;
  --portrait-bottom-radius: 14px;
}
.sheet-embedded.transparent-portrait .header-top,
.sheet-embedded.transparent-portrait .header-controls {
  padding-right: calc(var(--portrait-size) + 8px);
}
.sheet-portrait.transparent {
  width: var(--portrait-size);
  height: auto;
  object-fit: contain;
  position: absolute;
  top: calc(-1 * var(--portrait-lift));
  right: 16px;
  border: none;
  border-bottom: 1px solid var(--overlay-12);
  border-radius: 0 0 var(--portrait-bottom-radius) var(--portrait-bottom-radius);
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
  .set-back { align-self: flex-start;
    margin-bottom: 6px; }
  /* Previous hugs the left edge, Next the right. `align-self: stretch` is what
     makes the row span the list — right-aligned, the two buttons could only ever
     huddle together. The auto margin (not justify-content) keeps a *lone* Next on
     the right, the way the single button always sat, while a lone Previous sits
     left. */
  .set-nav { align-self: stretch;
    margin-top: 6px;
    display: flex;
    flex-wrap: wrap;
    gap: 6px; }
  .set-nav-next { margin-left: auto; }

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

  .add-trait-btn { margin-top: 8px; }

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
  background: var(--overlay-4);
  border: 1px solid var(--overlay-6);
  border-radius: 6px;
  color: var(--text);
  cursor: pointer;
  margin-bottom: 4px;
  transition: background 0.15s, border-color 0.15s;
}
.picker-item:hover {
  background: var(--overlay-8);
  border-color: var(--overlay-12);
}
.picker-die {
  font-weight: 700;
  font-size: 12px;
  color: var(--text-dim);
}
  .picker-back { margin-bottom: 6px; }
  .picker-cancel { margin-top: 6px; }

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
  border: 1px solid var(--overlay-12);
  flex-shrink: 0;
  order: 1;
}
.sheet-portrait-video {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  object-fit: cover;
  border: 1px solid var(--overlay-12);
  flex-shrink: 0;
  order: 1;
}
.header-top h2 {
  flex: 1;
}

.header {
  margin-bottom: 16px;
}
.header h2 {
  font-size: 20px;
  font-weight: 700;
  margin-bottom: 4px;
}
/* Title + projection name. The character name stays the title until the body
   is named; then the body name takes the title and the character name shrinks
   to an overline above it. */
.header-title { flex: 1; min-width: 0; }
.header-title h2 { margin-bottom: 2px; }
.name-overline {
  font-size: 11px;
  line-height: 1.3;
  margin-bottom: 1px;
  color: var(--text-dim);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.name-primary { font-size: 20px; font-weight: 700; }
.name-secondary { display: flex; align-items: center; min-height: 17px; }
/* These overrides must beat the primitive's .btn-md/.btn-link rules from the
   child stylesheet, hence the .header-title descendant prefix. */
.header-title .name-primary-btn {
  padding: 0;
  font-size: 20px;
  font-weight: 700;
  line-height: 1.2;
  text-align: left;
  color: var(--text);
}
.header-title .projection-name-btn { padding: 0; font-size: 12px; font-weight: 400; }
.header-title .projection-name-btn.unset { color: var(--text-dim); }
.header-title .projection-name-btn.unset:hover { color: var(--accent); }
.projection-name-input {
  font: inherit;
  font-size: 12px;
  color: var(--text);
  background: var(--overlay-8);
  border: 1px solid var(--accent);
  border-radius: 4px;
  padding: 1px 6px;
  width: 100%;
  max-width: 220px;
}
.projection-name-input.is-primary { font-size: 20px; font-weight: 700; padding: 2px 8px; }
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
.active-effects {
  color: var(--accent, #d9b45a);
  font-size: 11px;
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
  border: 1px solid var(--overlay-12);
  border-radius: 999px;
  padding: 5px 10px;
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s;
}
.razmerit-chip:hover {
  border-color: var(--accent-dim);
  background: var(--accent-8);
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
  border: 1px solid var(--overlay-12);
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
  background: var(--overlay-4);
  border: 1px solid var(--accent-dim);
  border-radius: 6px;
  padding: 2px 4px;
  text-align: center;
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
  border-bottom: 1px solid var(--overlay-6);
}

.loading, .error, .empty {
  font-size: 13px;
  color: var(--text-dim);
  text-align: center;
  padding: 16px 0;
}
.error { color: var(--danger); }
.empty-no-entity {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
}

.sfx-card {
  display: flex;
  flex-direction: column;
  gap: 1px;
  align-self: flex-start;
  max-width: 100%;
  padding: 4px 8px;
  border-radius: 6px;
  border: 1px solid var(--overlay-8);
  background: var(--overlay-2);
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s;
}
.sfx-card:hover {
  border-color: var(--overlay-20);
}
.sfx-card.sfx-active {
  border-color: var(--accent);
  background: var(--accent-12);
}
.sfx-card.sfx-used {
  opacity: 0.35;
  pointer-events: none;
}
.sfx-card.sfx-blocked {
  opacity: 0.45;
  cursor: not-allowed;
  border-style: dashed;
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

.entity-sfx-cards {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  padding: 4px 0;
}

/* Rules the current place lends the entity (see Place-Owned Rules). Quiet by
   design: it belongs to the room, not to you, so it sits under your own cards
   and names where it comes from. */
.place-sfx-rules {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-top: 4px;
  padding-top: 6px;
  border-top: 1px dashed var(--overlay-8);
}
.place-sfx-group {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.place-sfx-label {
  font-size: 10px;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--text-dim);
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
.sheet-pills { display: flex; gap: 0; margin-bottom: 10px; border-radius: 20px; overflow: hidden; border: 1px solid var(--overlay-8); }
.pill { padding: 5px 14px; font-size: 11px; border: none; cursor: pointer; background: var(--overlay-2); color: var(--text-dim); transition: background 0.15s, color 0.15s; }
.pill + .pill { border-left: 1px solid var(--overlay-6); }
.pill:hover { background: var(--overlay-4); color: var(--text); }
.pill.active { background: var(--accent-dim); color: var(--text); font-weight: 600; }
/* ── Trait detail (read-only) ────────────────────────
   A drill-in that replaces the trait list. Layout priority top-down: the
   mechanical cores (rating, SFX) above the narrative tail. */

/* Descendant-prefixed so these beat the primitive's .btn-md/.btn-link rules. */



/* The rating band is the play target, mirroring the trait row's rating zone. */


/* Rendered only when it has rows, so a plain static trait ends at Notes. */


/* The derived natural-language rules line inside a detail SFX card. Brighter
   than the flavour lead-in above it — this is the text that tells you what the
   SFX actually does. */
</style>
