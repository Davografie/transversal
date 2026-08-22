<template>
  <div class="sse-indicator" :class="[connected ? 'shape-circle' : 'shape-triangle', { pulse: ssePulse }]" :title="connected ? 'SSE connected' : (error || 'SSE disconnected')"></div>
  <button v-if="gmMode && playerId && !showLoginOverlay" class="settings-btn" @click="openSettings" title="Player settings">↩</button>
  <!-- Login / Settings overlay -->
  <div v-if="showLoginOverlay" class="name-entry panel" @click.self="dismissOverlay">
    <!-- Fresh login: no identity yet -->
    <template v-if="!playerId">
      <h3>Who are you?</h3>
      <p class="name-hint">Your name is your recovery key — use the same name on any device.</p>
      <div class="search-wrapper">
        <input
          v-model="playerName"
          placeholder="Your name"
          @keyup.enter="onNameEnter"
          autofocus
          :disabled="checking"
        />
        <!-- Search results dropdown -->
        <div v-if="nameSuggestions.length || showLoginCreate" class="name-suggestions">
          <button
            v-for="s in nameSuggestions" :key="s.id"
            class="suggestion-item"
            @mousedown.prevent
            @click="selectSuggestion(s)"
          >{{ s.name }}</button>
          <button
            v-if="showLoginCreate"
            class="suggestion-item suggestion-create"
            @mousedown.prevent
            @click="onNameEnter"
          >New transverser: <strong>{{ playerName.trim() }}</strong></button>
        </div>
      </div>
      <button @click="onNameEnter" :disabled="checking || !playerName.trim()">{{ checking ? 'Searching…' : 'Search' }}</button>
      <p v-if="nameStatus" class="name-status" :class="{ 'name-found': nameFound, 'name-new': !nameFound }">{{ nameStatus }}</p>
      <button v-if="nameStatus" class="continue-btn" @click="confirmPlayer">{{ nameFound ? 'Continue' : 'Begin' }}</button>
    </template>
    <!-- Settings: already logged in -->
    <template v-else>
      <p class="name-hint settings-hint">Player settings</p>

      <!-- Name: business-card style, click to edit -->
      <div class="search-wrapper settings-name-wrapper">
        <div
          v-if="!switchEditing"
          class="settings-name-static"
          @click="startSwitchEdit"
        >{{ switchName || playerName }}</div>
        <input
          v-else
          ref="switchInputRef"
          v-model="switchName"
          class="settings-name-input"
          placeholder="Your name"
          @keyup.enter="onSwitchEnter"
          @blur="onSwitchBlur"
          :disabled="switching"
        />
        <div v-if="switchEditing && (switchSuggestions.length || showSwitchCreate)" class="name-suggestions">
          <button
            v-for="s in switchSuggestions" :key="s.id"
            class="suggestion-item"
            @mousedown.prevent
            @click="selectSwitchSuggestion(s)"
          >{{ s.name }}</button>
          <button
            v-if="showSwitchCreate"
            class="suggestion-item suggestion-create"
            @mousedown.prevent
            @click="onSwitchEnter"
          >New transverser: <strong>{{ switchName.trim() }}</strong></button>
        </div>
      </div>

      <!-- Switch confirmation -->
      <p v-if="switchStatus" class="name-status" :class="{ 'name-found': switchFound, 'name-new': !switchFound }">{{ switchStatus }}</p>
      <div v-if="switchStatus && pendingPlayerEntities.length" class="settings-section">
        <label class="settings-label">Characters</label>
        <div class="char-list">
          <button
            v-for="e in pendingPlayerEntities" :key="e.id"
            class="char-item"
          >{{ e.name || e.id }}</button>
        </div>
      </div>
      <button v-if="switchStatus" class="continue-btn" @click="confirmSwitch">
        {{ switchFound ? 'Continue' : 'Begin' }}
      </button>

      <!-- Character confirmation (separate from switch) -->
      <p v-if="charStatus" class="name-status name-found">{{ charStatus }}</p>
      <button v-if="charStatus" class="continue-btn" @click="confirmChar">Continue</button>

      <!-- Mode + Characters (hidden during confirmation) -->
      <template v-if="!switchStatus && !charStatus">
        <div class="settings-section">
          <label class="settings-label">Mode</label>
          <div class="mode-toggle">
            <button :class="{ active: !gmMode }" @click="gmMode = false">🎭 Player</button>
            <button :class="{ active: gmMode }" @click="gmMode = true">🏛 Architect</button>
          </div>
        </div>

        <div class="settings-section">
          <label class="settings-label">Media quality</label>
          <div class="mode-toggle">
            <button :class="{ active: mediaQuality === 'auto' }" @click="setMediaQuality('auto')">Auto</button>
            <button :class="{ active: mediaQuality === 'low' }" @click="setMediaQuality('low')">Low</button>
            <button :class="{ active: mediaQuality === 'high' }" @click="setMediaQuality('high')">High</button>
          </div>
          <p class="quality-hint">Low uses smaller images (less data). Auto follows your connection.</p>
        </div>

        <p v-if="needsCharacterPick" class="switch-error">Pick one of your characters to play.</p>

        <div v-if="loadingPlayerEntities" class="settings-section">
          <label class="settings-label">Your characters</label>
          <div class="char-list">
            <div v-for="n in 3" :key="n" class="char-chip char-chip-skeleton" aria-hidden="true">
              <span class="char-portrait char-skeleton-pulse"></span>
              <span class="char-chip-meta">
                <span class="char-skeleton-line char-skeleton-pulse char-skeleton-line-name"></span>
                <span class="char-skeleton-line char-skeleton-pulse char-skeleton-line-location"></span>
              </span>
            </div>
          </div>
        </div>

        <div v-else-if="playerEntities.length" class="settings-section">
          <label class="settings-label">Your characters</label>
          <div class="char-list">
            <button
              v-for="e in playerEntities" :key="e.id"
              class="char-chip"
              :class="{ active: entityId === e.id }"
              @click="selectCharacter(e)"
            >
              <MediaImage v-if="e.sheetPortrait" :src="e.sheetPortrait" class="char-portrait" alt="" />
              <span v-else class="char-portrait char-portrait-fallback">{{ (e.name || e.id).charAt(0) }}</span>
              <span class="char-chip-meta">
                <span class="char-chip-name">{{ e.name || e.id }}</span>
                <span v-if="locationLabel(e)" class="char-chip-location">{{ locationLabel(e) }}</span>
              </span>
              <span class="char-release-btn" title="Relinquish agency" @click.stop="releaseCharacter(e)">✕</span>
            </button>
          </div>
          <div class="char-create-row">
            <template v-if="showNewChar">
              <input v-model="newCharName" placeholder="Name…" @keyup.enter="createCharacter" class="char-name-input" />
              <button @click="createCharacter" :disabled="!newCharName.trim() || creatingChar" class="char-create-btn">✓</button>
            </template>
            <button v-else class="new-char-toggle" @click="showNewChar = true">+ New character</button>
          </div>
          <p v-if="createCharError" class="switch-error">{{ createCharError }}</p>
        </div>

        <div v-else class="settings-section settings-empty">
          <p class="settings-empty-title">No characters yet</p>
          <p class="settings-empty-hint">Create a new character or find one below to claim agency.</p>
          <template v-if="showNewChar">
            <div class="switch-row">
              <input v-model="newCharName" placeholder="Character name…" @keyup.enter="createCharacter" />
              <button @click="createCharacter" :disabled="!newCharName.trim() || creatingChar">+</button>
            </div>
          </template>
          <button v-else class="new-char-toggle" @click="showNewChar = true">+ New character</button>
          <p v-if="createCharError" class="switch-error">{{ createCharError }}</p>
        </div>

        <div class="settings-section">
          <label class="settings-label">Find character</label>
          <div class="search-wrapper find-char-wrapper">
            <input
              v-model="charSearch"
              placeholder="Search characters…"
              class="find-char-input"
              @keyup.enter="onCharSearchEnter"
            />
            <div v-if="charSearch.trim() && (charSearching || charSearchSearched)" class="name-suggestions">
              <div v-if="charSearching" class="char-search-skeleton-list">
                <div v-for="n in 3" :key="n" class="suggestion-item char-search-result char-search-skeleton" aria-hidden="true">
                  <span class="char-search-portrait char-skeleton-pulse"></span>
                  <span class="char-search-result-meta">
                    <span class="char-skeleton-line char-skeleton-pulse char-skeleton-line-name"></span>
                    <span class="char-skeleton-line char-skeleton-pulse char-skeleton-line-location"></span>
                  </span>
                </div>
              </div>
              <template v-else>
                <button
                  v-for="e in charSearchResults" :key="e.id"
                  class="suggestion-item char-search-result"
                  @mousedown.prevent
                  @click="chooseFoundCharacter(e)"
                >
                  <MediaImage v-if="e.sheetPortrait" :src="e.sheetPortrait" class="char-search-portrait" alt="" />
                  <span v-else class="char-search-portrait char-search-portrait-fallback">{{ (e.name || e.id).charAt(0) }}</span>
                  <span class="char-search-result-meta">
                    <span class="char-search-result-name">{{ e.name || e.id }}</span>
                    <span v-if="locationLabel(e)" class="char-search-result-location">{{ locationLabel(e) }}</span>
                  </span>
                </button>
                <div v-if="!charSearchResults.length && !charSearchError" class="suggestion-item char-search-empty">No characters found</div>
              </template>
            </div>
          </div>
          <p v-if="charSearchError" class="switch-error">{{ charSearchError }}</p>
        </div>
      </template>

      <p v-if="switchError" class="switch-error">{{ switchError }}</p>
      <button class="cancel-btn" @click="dismissOverlay">Back to game</button>
    </template>
  </div>
  <LocationViewer
    v-if="!fullCanvas"
    ref="locationRef"
    :location-id="currentLocationId"
    :location-name="locationName"
    :universe="universe"
    :background-image="displayBgImage"
    :raw-background-image="locationBgImage"
    :entity-id="entityId"
    v-model:edit-zones="editZones"
    :overlay="locationOverlay"
    :gm-mode="gmMode"
    :remote-pools="remotePools"
    :remote-results="remoteResults"
    @moved="onMoved"
    @inspect-entity="onInspectEntity"
  />
  <RelationalCanvas
    v-if="fullCanvas"
    :key="fullCanvas.mode + ':' + fullCanvas.entityId"
    class="fullscreen-canvas"
    fullscreen
    :location-id="fullCanvas.mode === 'location' && fullCanvas.scope === 'focus' ? fullCanvas.entityId : (fullCanvas.mode === 'faction' || fullCanvas.mode === 'gmc-web' ? currentLocationId : '')"
    :initial-faction-id="fullCanvas.mode === 'faction' ? fullCanvas.entityId : ''"
    :initial-gmc-id="fullCanvas.mode === 'gmc-web' ? fullCanvas.entityId : ''"
    :initial-life-path="fullCanvas.mode === 'life-path' ? fullCanvas.lifePath : null"
    :initial-universe="fullCanvas.mode === 'location' && fullCanvas.scope === 'tree' ? fullCanvas.entityId : ''"
    @close-full="fullCanvas = null"
  />
  <div v-if="wrapperOpen && !gmMode" class="panel-backdrop" @click="phase !== 'picking' && closePanel()" />
  <div ref="wrapperEl" class="dice-panel-wrapper" :class="{ open: wrapperOpen }" @mouseenter="onWrapperEnter" @mouseleave="onWrapperLeave">
      <div v-if="wrapperOpen && peers.length" class="peers-bar">
        <button v-for="p in peers" :key="p.id" class="peer-chip" :class="{ active: (gmMode ? actingEntityId : viewingEntityId) === p.id || (!(gmMode ? actingEntityId : viewingEntityId) && entityId === p.id) }" @click.stop="onPeerClick(p.id)" :title="p.name">
          <img v-if="p.backgroundImage" :src="p.backgroundImage" class="peer-img" />
          <span v-else class="peer-avatar">{{ p.name.charAt(0) }}</span>
          <span class="peer-label">{{ p.name }}</span>
        </button>
      </div>
      <CharacterSheet
        v-show="sheetVisible && (phase === 'adding' || forceSheet) && (!gmMode || actingEntityId)"
        ref="sheetRef"
        class="embedded-sheet"
        :class="{ 'sheet-hidden': !sheetVisible }"
        :entity-id="entityId"
        :override-entity-id="viewingEntityId"
        :viewer-entity-id="entityId"
        :player-owned-entity-ids="ownedEntityIds"
        :universe="universe"
        :phase="phase"
        :visible="sheetVisible"
        embedded
        :gm-mode="gmMode"
        @open-settings="openSettings"
        @add-to-pool="(d) => diceRef?.addFromSheet(d)"
        @remove-from-pool="(s) => diceRef?.removeBySource(s)"
        @remove-by-ts-id="(id) => diceRef?.removeByTsId(id)"
        @split-die="(d) => diceRef?.splitDie(d)"
        @sfx-toggled="onSfxToggled"
        @sheet-view-change="onSheetViewChange"
      />
    <DiceRoller ref="diceRef" :entity-id="entityId" :universe="universe" :mode="rollerMode" :keep-count="keepCount" :effect-count="effectCount" :gm-mode="gmMode" :difficulty="currentDifficulty" :player-id="playerId" :location-id="currentLocationId" :peers="peers" :acting-entity-id="gmMode ? actingEntityId : entityId" :fallback-entity-id="selfEntityId" :remote-pools="remotePools" :remote-results="remoteResults" :sfx-choice-request="sfxChoiceRequest" @update:universe="u => universe = u" @rolled="onDiceRolled" @picked="(r) => shareRoll(r)" @difficulty="onDifficultyCommitted" @pool-change="onPoolChange" @phase-change="onPhaseChange" @panel-open="onPanelOpen" @sfx-choice-resolved="sfxChoiceRequest = null" @acting-entity-change="onActingEntityChange" />
  </div>
  <PanelStack v-if="gmMode" :root-panel="gmRootPanel" />
  <ToastBar :toasts="toasts" @dismiss="dismissToast" />
</template>

<script setup>
import { ref, useTemplateRef, watch, computed, nextTick, onMounted, onUnmounted } from 'vue'
import LocationViewer from './components/LocationViewer.vue'
import CharacterSheet from './components/CharacterSheet.vue'
import DiceRoller from './components/DiceRoller.vue'
import GmPanel from './components/GmPanel.vue'
import PanelStack from './components/gm/PanelStack.vue'
import RelationalCanvas from './components/canvas/RelationalCanvas.vue'
import MediaImage from './components/MediaImage.vue'
import { useSSE } from './composables/useSSE.js'
import { useSessions } from './composables/useSessions.js'
import { useToasts } from './composables/useToasts.js'
import { useApi } from './composables/useApi.js'
import { usePanelBus } from './composables/usePanelBus.js'
import { useEntityCrud } from './composables/useEntityCrud.js'
import { useMediaQuality } from './composables/useMediaQuality.js'
import ToastBar from './components/ToastBar.vue'

const { graphql, getDifficulty: apiGetDifficulty, setDifficulty: apiSetDifficulty, nextBeat: apiNextBeat, advanceScene: apiAdvanceScene, listAllPools: apiListAllPools } = useApi()
const { fetchEntities: prefetchEntities } = useEntityCrud()
const { quality: mediaQuality, setQuality: setMediaQuality, resolveMediaUrl, isLowQuality } = useMediaQuality()
const bus = usePanelBus()

// ── Diagnostic logger (must be first — used throughout setup) ──
const DIAG = {
  marks: [],
  mark(label, detail) {
    const entry = { label, time: performance.now().toFixed(1), detail }
    this.marks.push(entry)
    console.log(`[diag] ${label}`, detail !== undefined ? detail : '')
  },
  dump() {
    console.table(this.marks.map(m => ({ label: m.label, ms: m.time, detail: typeof m.detail === 'object' ? JSON.stringify(m.detail) : String(m.detail ?? '') })))
  }
}

DIAG.mark('app-setup-start', { entityId: localStorage.getItem('entityId'), playerId: localStorage.getItem('playerId'), playerName: localStorage.getItem('playerName'), architectMode: localStorage.getItem('architectMode') })

// ── GM panel root spec for PanelStack ──
const gmRootPanel = computed(() => ({
  component: GmPanel,
  props: {
    universe: universe.value,
    currentLocationId: currentLocationId.value,
    currentEntityId: actingEntityId.value,
  },
  listeners: {
    'next-beat': () => onNextBeat(),
    'advance-scene': () => onAdvanceScene(),
    'start-session': () => onStartSession(),
    'end-session': () => onEndSession(),
    'add-to-pool': (d) => diceRef?.addFromSheet(d),
  },
}))

const universe = ref('earth')
const currentLocationId = ref(localStorage.getItem('currentLocationId') || 'loc-krasnoyarsk')
watch(currentLocationId, (v) => { if (v) localStorage.setItem('currentLocationId', v) })
const fullCanvas = ref(null) // { mode: 'location'|'faction', entityId } or null
const locationName = ref('Krasnoyarsk-45')
const locationBgImage = ref('')
// Displayed background: quality preference applied reactively so the toggle takes
// effect immediately. Cache-aware — prefers the already-cached original in low mode.
const displayBgImage = ref('')
let bgResolveSeq = 0
watch(
  [locationBgImage, isLowQuality],
  async ([raw]) => {
    const seq = ++bgResolveSeq
    const resolved = await resolveMediaUrl(raw)
    if (seq === bgResolveSeq) displayBgImage.value = resolved
  },
  { immediate: true }
)
const locationOverlay = ref(null)

// Fetch entity location on mount so refreshes show the real location
async function initLocation() {
  DIAG.mark('initLocation-start', { entityId: entityId.value })
  locationName.value = 'LOADING...'
  try {
    const r = await fetch('/api/v1/graphql', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query: `query($id: ID!) { entity(id: $id) { currentLocation currentUniverse } }`, variables: { id: entityId.value } })
    })
    const json = await r.json()
    const data = json.data
    if (data?.entity) {
      currentLocationId.value = data.entity.currentLocation || 'loc-krasnoyarsk'
      universe.value = data.entity.currentUniverse || 'earth'
      DIAG.mark('initLocation-entity-fetched', { currentLocation: currentLocationId.value, universe: universe.value })
      locationName.value = '...'
      try {
        const r2 = await fetch(`/api/v1/locations/${currentLocationId.value}/navigate`)
        const nav = await r2.json()
        locationName.value = nav.location?.name || currentLocationId.value
      } catch (e) {
        DIAG.mark('initLocation-navigate-err', { error: e.message })
        locationName.value = 'err: ' + e.message
      }
      fetchLocationBg()
      fetchPeers()
    } else {
      DIAG.mark('initLocation-no-entity', { graphqlResponse: json })
      locationName.value = 'no entity'
    }
  } catch (e) {
    DIAG.mark('initLocation-err', { error: e.message })
    locationName.value = 'err: ' + e.message
  }
  DIAG.mark('initLocation-done', { locationName: locationName.value })
}

async function fetchLocationBg() {
  try {
    const r = await fetch('/api/v1/graphql', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query: `query($id: ID!) { entity(id: $id) { image(role: "background") overlay } }`, variables: { id: currentLocationId.value } })
    })
    DIAG.mark('fetchLocationBg-fetched', { ok: r.ok, status: r.status })
    const json = await r.json()
    const hasBg = !!json.data?.entity?.image
    locationBgImage.value = json.data?.entity?.image || ''
    locationOverlay.value = json.data?.entity?.overlay || null
    DIAG.mark('fetchLocationBg-done', { hasBackgroundImage: hasBg, imageLength: locationBgImage.value.length })
  } catch (e) {
    DIAG.mark('fetchLocationBg-err', { error: e.message })
    locationBgImage.value = ''; locationOverlay.value = null
  }
}

async function fetchPeers() {
  DIAG.mark('fetchPeers-start', { currentLocationId: currentLocationId.value })
  const data = await graphql(`query {
    entities { id type name backgroundImage currentLocation }
  }`)
  if (data?.entities) {
    const TYPE_ORDER = { CHARACTER: 0, GMC: 1, ASSET: 2, LOCATION: 3 }
    peers.value = data.entities
      .filter(e => e.currentLocation === currentLocationId.value)
      .sort((a, b) => {
        if (a.id === entityId.value) return -1
        if (b.id === entityId.value) return 1
        return (TYPE_ORDER[a.type] ?? 9) - (TYPE_ORDER[b.type] ?? 9)
      })
    DIAG.mark('fetchPeers-done', { total: data.entities.length, atLocation: peers.value.length })
  } else {
    DIAG.mark('fetchPeers-no-data')
  }
}

function onMoved(data) {
  locationName.value = data.location
  if (data.universe) universe.value = data.universe
  currentLocationId.value = data.location_id || data.location
  fetchLocationBg()
  fetchPeers()
}

const selfEntityId = ref(localStorage.getItem('entityId') || 'kael-1')  // stable identity (SSE/login); for GM this is not a "main" entity
const entityId = ref(selfEntityId.value)  // perspective entity; null = GM free-roam view
const editZones = ref(false)

// When switching entities, update location (players only — for GM, entityId
// is a freely-switchable perspective and must not re-init location or persist).
watch(entityId, () => {
  if (!entityId.value || gmMode.value) return
  localStorage.setItem('entityId', entityId.value)
  initLocation()
})
const keepCount = ref(2)
const effectCount = ref(1)
const phase = ref('adding')
const rollerMode = ref('cortex') // 'cortex' | 'roll_table' (driven by CharacterSheet tab)
const currentDifficulty = ref(null) // GM-set test difficulty (ephemeral, session-scoped)
const sfxChoiceRequest = ref(null) // pending {choose_*} auto-fired SFX choices for this player

// Player identity
const playerId = ref(localStorage.getItem('playerId') || '')
const playerName = ref(localStorage.getItem('playerName') || '')
const showLoginOverlay = ref(!playerId.value)
const checking = ref(false)
const nameStatus = ref('')
const nameFound = ref(false)
const pendingPlayer = ref(null)

// Settings panel
const gmMode = ref(localStorage.getItem('architectMode') === 'true')
const switchName = ref('')
const switchEditing = ref(false)
const switching = ref(false)
const switchError = ref('')
const switchPending = ref(null)
const switchStatus = ref('')
const switchFound = ref(false)
const charPending = ref(null)
const charStatus = ref('')
const pendingPlayerEntities = ref([])
const playerEntities = ref([])
const loadingPlayerEntities = ref(false)

const locationNames = ref({})
let locationNamesLoaded = false

const ownedEntityIds = computed(() => playerEntities.value.map(e => e.id))
// True when playing as a non-GM but the current perspective entity isn't one
// the player owns — the settings overlay must stay open until they pick one.
const needsCharacterPick = computed(() =>
  !gmMode.value && !!playerId.value && !ownedEntityIds.value.includes(entityId.value)
)

const newCharName = ref('')
const creatingChar = ref(false)
const createCharError = ref('')
const showNewChar = ref(false)

// Find character
const charSearch = ref('')
const charSearchResults = ref([])
const charSearching = ref(false)
const charSearchSearched = ref(false)
const charSearchError = ref('')
let charSearchDebounce = null
let allCharactersCache = null

// Name search
const nameSuggestions = ref([])
const switchSuggestions = ref([])
const loginHasExactMatch = ref(false)
const switchHasExactMatch = ref(false)
let nameDebounce = null
let switchDebounce = null

const showLoginCreate = computed(() => playerName.value.trim() && !loginHasExactMatch.value)
const showSwitchCreate = computed(() => switchName.value.trim() && !switchHasExactMatch.value)

async function searchPlayers(q) {
  if (!q || q.length < 1) { nameSuggestions.value = []; return }
  try {
    const r = await fetch(`/api/v1/players?q=${encodeURIComponent(q)}`)
    const data = await r.json()
    nameSuggestions.value = data
  } catch (e) {
    nameSuggestions.value = []
  }
}

// Watch playerName for live search suggestions in login flow
watch(playerName, (val) => {
  if (playerId.value) return  // only in login flow
  if (nameDebounce) clearTimeout(nameDebounce)
  const q = val.trim()
  nameDebounce = setTimeout(async () => {
    await searchPlayers(q)
    const exact = nameSuggestions.value.some(s => s.name.toLowerCase() === q.toLowerCase())
    loginHasExactMatch.value = exact
    if (exact) nameSuggestions.value = []
  }, 150)
})

async function onNameEnter() {
  if (nameDebounce) clearTimeout(nameDebounce)
  const name = playerName.value.trim()
  if (!name) return
  checking.value = true
  nameSuggestions.value = []
  try {
    await searchPlayers(name)
    const p = await findOrCreatePlayer(name)
    if (p) {
      pendingPlayer.value = p
      localStorage.setItem('playerName', name)
      if (p.found) {
        nameStatus.value = `You've transversed before, ${name}.`
        nameFound.value = true
      } else {
        nameStatus.value = `New transverser detected. Welcome, ${name}.`
        nameFound.value = false
      }
    }
  } finally {
    checking.value = false
  }
}

function selectSuggestion(s) {
  playerName.value = s.name
  nameSuggestions.value = []
  localStorage.setItem('playerName', s.name)
  pendingPlayer.value = { id: s.id, name: s.name, found: true }
  nameStatus.value = `You've transversed before, ${s.name}.`
  nameFound.value = true
}

async function searchSwitchPlayers(q) {
  if (!q || q.length < 1) { switchSuggestions.value = []; return }
  try {
    const r = await fetch(`/api/v1/players?q=${encodeURIComponent(q)}`)
    switchSuggestions.value = await r.json()
  } catch { switchSuggestions.value = [] }
}

// Watch switchName for live suggestions in settings panel
watch(switchName, (val) => {
  if (switchDebounce) clearTimeout(switchDebounce)
  const q = val.trim()
  switchError.value = ''
  switchDebounce = setTimeout(async () => {
    await searchSwitchPlayers(q)
    const exact = switchSuggestions.value.some(s => s.name.toLowerCase() === q.toLowerCase())
    switchHasExactMatch.value = exact
    if (exact) switchSuggestions.value = []
  }, 150)
})

function selectSwitchSuggestion(s) {
  switchName.value = s.name
  switchSuggestions.value = []
  switchPending.value = { id: s.id, name: s.name, found: true }
  switchStatus.value = `You've transversed before, ${s.name}.`
  switchFound.value = true
  switchError.value = ''
  pendingPlayerEntities.value = []
  fetchEntitiesFor(s.id).then(e => { pendingPlayerEntities.value = e })
  switchEditing.value = false
}

async function findOrCreatePlayer(name) {
  try {
    const r = await fetch('/api/v1/players', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name }) })
    return await r.json()
  } catch { return null }
}

async function fetchPlayer(pid) {
  if (!pid) return null
  try {
    const r = await fetch(`/api/v1/players/${pid}`)
    if (!r.ok) return null
    return (await r.json()) || null
  } catch {
    return null
  }
}

async function ensurePlayer() {
  DIAG.mark('ensurePlayer-start', { playerId: playerId.value, playerName: playerName.value })
  if (playerId.value) {
    const p = await fetchPlayer(playerId.value)
    if (p) {
      DIAG.mark('ensurePlayer-have-id', { playerId: playerId.value, entityIds: p.entity_ids })
      if (Array.isArray(p.entity_ids) && p.entity_ids.includes(entityId.value)) {
        fetch(`/api/v1/players/${playerId.value}/claim/${entityId.value}`, { method: 'POST' }).catch(() => {})
      }
      loadPlayerRole()
      return
    }
    DIAG.mark('ensurePlayer-stale-id', { playerId: playerId.value })
    playerId.value = ''
    playerName.value = ''
    localStorage.removeItem('playerId')
    localStorage.removeItem('playerName')
  }

  if (playerName.value) {
    // Have name but no ID — try to recover
    const p = await findOrCreatePlayer(playerName.value)
    DIAG.mark('ensurePlayer-recover-result', { found: !!p, id: p?.id })
    if (p) {
      playerId.value = p.id
      localStorage.setItem('playerId', p.id)
      fetch(`/api/v1/players/${playerId.value}/claim/${entityId.value}`, { method: 'POST' }).catch(() => {})
      return
    }
  }

  // No name or ID — show entry
  DIAG.mark('ensurePlayer-no-identity', 'showing login overlay')
  showLoginOverlay.value = true
}

function confirmPlayer() {
  if (!pendingPlayer.value) return
  playerId.value = pendingPlayer.value.id
  localStorage.setItem('playerId', pendingPlayer.value.id)
  localStorage.setItem('playerName', playerName.value.trim())
  nameStatus.value = ''
  pendingPlayer.value = null
  showLoginOverlay.value = false
  fetch(`/api/v1/players/${playerId.value}/claim/${entityId.value}`, { method: 'POST' }).catch(() => {})
  loadPlayerRole()
}
ensurePlayer()

// Session management
const { sessions, currentSession, listSessions, createSession, joinSession, publishEvent } = useSessions()
const sessionId = ref('session-default')

async function initSession() {
  DIAG.mark('initSession-start')
  await listSessions()
  DIAG.mark('initSession-listed', { count: sessions.value.length, ids: sessions.value.map(s => s.id) })
  if (sessions.value.length > 0) {
    const s = sessions.value[0]
    sessionId.value = s.id
    await joinSession(s.id, entityId.value, playerId.value)
    DIAG.mark('initSession-joined', { sessionId: sessionId.value })
  } else {
    const s = await createSession('Default Session', 'earth')
    if (s) {
      sessionId.value = s.id
      await joinSession(s.id, entityId.value, playerId.value)
      DIAG.mark('initSession-created', { sessionId: sessionId.value })
    } else {
      DIAG.mark('initSession-FAILED', { error: 'createSession returned null' })
    }
  }
}
DIAG.mark('initSession-called')
initSession()
DIAG.mark('initLocation-called')
const peers = ref([])
initLocation()

const shareCount = ref(0)
const lastSent = ref('')
const lastEvtDebug = ref('')

function sharePhase() {
  if (sessionId.value === 'session-default') return
  lastSent.value = `phase:${phase.value}`
  publishEvent(sessionId.value, 'pool_updated', { player_id: playerId.value, entity_id: entityId.value, phase: phase.value })
}
function shareRoll(result) {
  if (sessionId.value !== 'session-default') {
    publishEvent(sessionId.value, 'roll_result', { player_id: playerId.value, entity_id: entityId.value, result, phase: 'resolved' })
  }
}

function onDifficultyCommitted(difficulty) {
  if (sessionId.value === 'session-default') return
  apiSetDifficulty(currentLocationId.value, difficulty)
}

async function refreshDifficulty() {
  if (!currentLocationId.value) return
  const res = await apiGetDifficulty(currentLocationId.value)
  currentDifficulty.value = res?.difficulty ?? null
}

async function seedRemotePools() {
  // Tabs are global — seed every active pool across all locations.
  const res = await apiListAllPools()
  const pools = res?.pools || {}
  for (const [eid, dice] of Object.entries(pools)) {
    if (eid !== entityId.value && dice && dice.length) {
      remotePools.value = { ...remotePools.value, [eid]: { dice, player_id: eid, phase: 'adding' } }
    }
  }
}

watch(currentLocationId, refreshDifficulty, { immediate: true })
watch(currentLocationId, seedRemotePools, { immediate: true })

// ── Roll-table wiring (shared roller driven by LifePathWizard via bus) ──
function onPoolChange(s) {
  if (rollerMode.value === 'roll_table') return
  const labels = s.map(d => d.label || '').filter(Boolean)
  currentPoolSources.value = labels
  sheetRef.value?.setPoolSources(s)
}

async function switchPerspective(id) {
  if (!id) return
  let targetLoc = null
  try {
    const data = await graphql(`query($id: ID!) { entity(id: $id) { currentLocation } }`, { id })
    targetLoc = data?.entity?.currentLocation || null
  } catch {}
  const sameLocation = targetLoc != null && targetLoc === currentLocationId.value
  entityId.value = id
  actingEntityId.value = id
  if (!sameLocation) await initLocation()
}

async function setViewLocation(locId) {
  if (!locId) return
  currentLocationId.value = locId
  locationName.value = locId
  try {
    const r = await fetch(`/api/v1/locations/${locId}/navigate`)
    const nav = await r.json()
    locationName.value = nav.location?.name || locId
  } catch {}
  fetchLocationBg()
  fetchPeers()
}

async function switchViewLocation(locId) {
  if (!locId) return
  entityId.value = null
  actingEntityId.value = null
  await setViewLocation(locId)
}

function returnToSelf() {
  entityId.value = selfEntityId.value
  actingEntityId.value = null
}

function onInspectEntity(id) {
  if (gmMode.value) {
    switchPerspective(id)
  } else {
    viewingEntityId.value = id
  }
  forceSheet.value = true
  sheetVisible.value = true
}

function onPeerClick(id) {
  if (gmMode.value) {
    if (actingEntityId.value === id) returnToSelf()
    else switchPerspective(id)
  } else {
    // Clicking our own character returns to self-view (no override), keeping the header tabs visible.
    viewingEntityId.value = (id === entityId.value || id === selfEntityId.value)
      ? null
      : (viewingEntityId.value === id ? null : id)
  }
  forceSheet.value = true
}

function onActingEntityChange(id) {
  if (!gmMode.value) return
  if (id) switchPerspective(id)
  else returnToSelf()
}

function onDiceRolled(result) {
  if (rollerMode.value === 'roll_table') {
    bus.emit('roll-table:rolled', result)
    return
  }
  onRolled()
  shareRoll(result)
}

function onSheetViewChange(view) {
  const next = view === 'lifepath' ? 'roll_table' : 'cortex'
  if (rollerMode.value !== next) {
    rollerMode.value = next
    diceRef.value?.clearPool()
  }
}

function onRollTablePrepare({ dice = [] } = {}) {
  rollerMode.value = 'roll_table'
  const roller = diceRef.value
  if (!roller) return
  roller.clearPool()
  for (const d of dice) roller.addFromSheet(d)
}

function onRollTableResolved(outcome) {
  if (sessionId.value === 'session-default') return
  publishEvent(sessionId.value, 'roll_table_roll', {
    player_id: playerId.value,
    entity_id: entityId.value,
    ...outcome,
  })
}

let offRollTablePrepare = null
let offRollTableResolved = null
let offCanvasOpenFull = null
let offSwitchPerspective = null
let offSwitchViewLocation = null

// SSE — live state sync (subscribe with the stable identity; free-roam has no perspective entity)
const { connected, lastEvent, error } = useSSE(sessionId, computed(() => entityId.value || selfEntityId.value))

// Architect toast notifications
const { toasts, addToast, dismissToast } = useToasts()
const nameCache = ref({})  // entity_id → name

function entName(eid) {
  if (!eid) return 'someone'
  if (nameCache.value[eid]) return nameCache.value[eid]
  // Try peers list first (already fetched for current location)
  const p = peers.value.find(e => e.id === eid)
  if (p?.name) {
    nameCache.value[eid] = p.name
    return p.name
  }
  return eid.slice(0, 8)
}
// Refresh name cache whenever peers change
watch(peers, (p) => {
  for (const e of p) {
    if (e.id && e.name) nameCache.value[e.id] = e.name
  }
}, { deep: true })

const remotePools = ref({})  // entity_id → { dice: [...], player_id, phase }
const remoteResults = ref({})  // entity_id → { result, rolls, kept, total, effect_die }

const ssePulse = ref(false)
watch(lastEvent, (evt) => {
  if (!evt) return
  ssePulse.value = true
  setTimeout(() => { ssePulse.value = false }, 300)

  const pid = evt.data?.player_id
  const eid = evt.data?.entity_id
  const foreign = pid !== playerId.value  // event from another player
  const name = entName(eid)

  switch (evt.type) {
    case 'razmerit_changed':
      if (evt.data?.new_balance != null) {
        sheetRef.value?.setRazmerit(evt.data.new_balance, evt.data.entity_id)
      }
      break
    case 'beat_end':
      diceRef.value?.clearPool()
      remotePools.value = {}
      remoteResults.value = {}
      currentDifficulty.value = null
      if (gmMode.value) addToast('Beat ended', 'dice')
      break
    case 'trait_updated':
      // local patch handles display; SSE sync deferred
      if (evt.data?.entity_id === entityId.value && evt.data?.trait_setting_id) {
        diceRef.value?.resyncTraitDie(evt.data.trait_setting_id, evt.data.new_dice ?? [evt.data.new_rating])
      }
      if (gmMode.value && foreign) {
        const tName = evt.data?.trait_name || evt.data?.name || 'a trait'
        addToast(`${name} updated ${tName}`, 'trait')
      }
      break
    case 'location_changed':
      if (eid === entityId.value && evt.data?.to) {
        currentLocationId.value = evt.data.to
        if (evt.data?.universe) universe.value = evt.data.universe
        fetchLocationBg()
        fetchPeers()
        fetch(`/api/v1/locations/${evt.data.to}/navigate`)
          .then(r => r.json())
          .then(nav => { locationName.value = nav.location?.name || evt.data.to })
          .catch(() => { locationName.value = evt.data.to })
      } else {
        locationRef.value?.fetchNav()
      }
      if (gmMode.value && foreign && evt.data?.to) {
        nameCache.value[eid] = evt.data.to_name || eid
        addToast(`${name} moved to ${evt.data.to}`, 'move')
      }
      break
    case 'entity_updated':
      if (eid === currentLocationId.value) fetchLocationBg()
      locationRef.value?.fetchNavWithLerp()
      break
    case 'entity_moved':
      // Position-only change (map drag/reposition): re-sync nav dots, no toast.
      if (evt.data?.current_location === currentLocationId.value) {
        locationRef.value?.fetchNavWithLerp()
      }
      break
    case 'scene_change':
      if (evt.data?.to_location) locationName.value = evt.data.to_location
      if (gmMode.value) {
        addToast(evt.data?.to_location ? `Scene: ${evt.data.to_location}` : 'Scene advanced', 'scene')
      }
      diceRef.value?.clearPool()
      remotePools.value = {}
      remoteResults.value = {}
      diceRef.value?.loadTargetingBans()
      break
    case 'pool_updated':
      lastEvtDebug.value = `pid=${pid} eid=${eid} phase=${evt.data.phase} dice=${JSON.stringify(evt.data.dice)} mypid=${playerId.value}`
      if (eid && eid !== entityId.value) {
        const phase = evt.data.phase || 'adding'
        const hasDice = Array.isArray(evt.data.dice)
        remotePools.value = { ...remotePools.value, [eid]: {
          dice: hasDice ? evt.data.dice : (remotePools.value[eid]?.dice || []),
          player_id: pid, phase,
        }}
        // Reflect backend 'bought' flags into the resolved-rolls view (hitch menu).
        const rolls = remoteResults.value[eid]?.rolls
        if (hasDice && Array.isArray(rolls)) {
          const merged = rolls.map((r, i) => ({ ...r, bought: evt.data.dice[i]?.bought ?? r.bought }))
          remoteResults.value = { ...remoteResults.value, [eid]: { ...remoteResults.value[eid], rolls: merged } }
        }
        if (phase === 'adding' && hasDice && evt.data.dice.length === 0) {
          const { [eid]: _, ...rest } = remoteResults.value
          remoteResults.value = rest
        }
      }
      if (gmMode.value && eid && eid !== entityId.value) {
        const phase = evt.data.phase || 'adding'
        const dice = evt.data.dice || []
        if (phase === 'adding') {
          if (dice.length) {
            addToast(`${name} added ${dice.length} die${dice.length > 1 ? '' : ''} to pool`, 'dice')
          }
        } else if (phase === 'rolled') {
          // pool was submitted for rolling
        } else if (phase === 'resolved') {
          // already covered by roll_result
        }
      }
      break
    case 'roll_result':
      if (pid !== playerId.value && eid) {
        const res = evt.data.result
        const existing = remoteResults.value[eid] || {}
        remoteResults.value = { ...remoteResults.value, [eid]: {
          ...existing,
          total: res.total || res.highest || existing.total,
          effect_die: res.effect_die || existing.effect_die,
          tier: res.tier || existing.tier,
          botch: res.botch ?? existing.botch,
          pipeline: res.pipeline || existing.pipeline,
          hitches: res.hitches || existing.hitches || [],
          rolls: (res.rolls && res.rolls.length) ? res.rolls : (existing.rolls || []),
        }}
      }
      if (gmMode.value && foreign && eid) {
        const res = evt.data.result
        const total = res.total ?? res.highest ?? '?'
        const tier = res.tier ? ` (${res.tier})` : ''
        const eff = res.effect_die ? ` · d${res.effect_die}` : ''
        addToast(`${name} rolled ${total}${tier}${eff}`, 'roll')
      }
      break
    case 'roll_table_roll':
      if (gmMode.value && foreign && eid) {
        const table = evt.data?.table_name || 'a roll table'
        const entry = evt.data?.entry_label ? `: ${evt.data.entry_label}` : ''
        addToast(`${name} rolled on ${table}${entry}`, 'roll')
      }
      break
    case 'difficulty_set':
      if (evt.data?.difficulty != null) {
        currentDifficulty.value = evt.data.difficulty
        if (!gmMode.value) {
          addToast(`Difficulty set: ${evt.data.difficulty}`, 'roll')
        }
      }
      break
    case 'contest_challenged':
      if (gmMode.value) addToast(`${entName(evt.data?.challenger_id)} challenged ${entName(evt.data?.opponent_id)}`, 'dice')
      if (evt.data?.opponent_id === entityId.value) {
        diceRef.value?.onChallenged(evt.data.challenger_id)
        if (!gmMode.value) addToast(`You've been challenged by ${entName(evt.data?.challenger_id)}`, 'dice')
      }
      break
    case 'contest_set':
      if (eid && eid !== entityId.value) {
        const existing = remoteResults.value[eid] || {}
        remoteResults.value = { ...remoteResults.value, [eid]: {
          ...existing,
          committed: { total: evt.data?.total, effect_die: evt.data?.effect_die, tier: evt.data?.tier, pipeline: evt.data?.pipeline },
        }}
        diceRef.value?.onOpponentCommitted(evt.data)
      }
      if (gmMode.value) {
        addToast(`${name} set their result (${evt.data?.total})`, 'roll')
      }
      break
    case 'contest_give_in':
      if (gmMode.value) {
        addToast(`${name} gave in`, 'roll')
      }
      if (eid && eid !== entityId.value) {
        diceRef.value?.onOpponentGiveIn(evt.data)
      }
      break
    case 'contest_compare':
      diceRef.value?.onContestCompare(evt.data)
      break
    case 'contest_push':
      if (gmMode.value && eid) addToast(`${name} is pushing`, 'dice')
      if (eid && eid !== entityId.value) diceRef.value?.onContestPush(evt.data)
      break
    case 'contest_stakes':
      diceRef.value?.setHighStakes(evt.data?.high_stakes)
      break
    case 'contest_resolved':
      diceRef.value?.setContestOutcome(evt.data)
      addToast('Contest resolved', 'roll')
      break
    case 'traits_revealed':
      if ((evt.data?.learner_ids || []).includes(entityId.value)) {
        sheetRef.value?.fetchEntity()
      }
      break
    case 'sfx_triggered':
      if (evt.data?.entity_id === entityId.value) {
        addToast(`SFX: ${evt.data?.sfx_name || evt.data?.sfx_id}`, 'sfx')
      }
      break
    case 'sfx_choice_required':
      if (evt.data?.entity_id === entityId.value) {
        sfxChoiceRequest.value = (evt.data.choices || []).map((c, i) => ({ ...c, index: i }))
      }
      break
  }
})

function onPhaseChange(p) {
  if (rollerMode.value === 'roll_table') return
  phase.value = p
  if (p !== 'adding') forceSheet.value = false
  if (p === 'adding') {
    keepCount.value = 2
    effectCount.value = 1
    sheetRef.value?.resetSfxCounts()
  }
  sharePhase()
}
const diceRef = useTemplateRef('diceRef')
const sheetRef = useTemplateRef('sheetRef')
const locationRef = useTemplateRef('locationRef')
const switchInputRef = useTemplateRef('switchInputRef')

const hoverOpen = ref(false)
const sheetVisible = ref(false)
let sheetTimer = null
let closeTimer = null

const currentPoolSources = ref([])
const viewingEntityId = ref(null)
const actingEntityId = ref(null)  // GM: entity being acted as (null = difficulty/free-roam)
const forceSheet = ref(false)

const wrapperEl = useTemplateRef('wrapperEl')
const wrapperOpen = computed(() => hoverOpen.value || sheetVisible.value)
const documentDragging = ref(false)

function openPanel() {
  hoverOpen.value = true
  // Clear inline transform so .open class translateY(0) takes over
  if (wrapperEl.value) wrapperEl.value.style.transform = ''
  if (sheetTimer) clearTimeout(sheetTimer)
  sheetTimer = setTimeout(() => { sheetVisible.value = true }, 300)
}

function closePanel() {
  hoverOpen.value = false
  sheetVisible.value = false
  forceSheet.value = false
  if (diceRef.value) diceRef.value.panelOpen = false
  if (sheetTimer) { clearTimeout(sheetTimer); sheetTimer = null }
  if (closeTimer) { clearTimeout(closeTimer); closeTimer = null }
  // Set peek position after DOM updates
  nextTick(() => syncClosedPosition())
}

function syncClosedPosition() {
  if (!wrapperEl.value) return
  const h = wrapperEl.value.offsetHeight
  wrapperEl.value.style.transform = `translateX(-50%) translateY(${h - 56}px)`
}

function onPanelOpen(v) {
  if (gmMode.value) return
  if (v) openPanel()
  else closePanel()
}

function onWrapperEnter() {
  if (closeTimer) { clearTimeout(closeTimer); closeTimer = null }
  openPanel()
}

function onWrapperLeave() {
  if (phase.value === 'picking') return  // don't close during dice drag-and-drop
  if (documentDragging.value) return    // don't close during HTML5 drag-and-drop
  closeTimer = setTimeout(() => {
    closeTimer = null
    closePanel()
  }, 1000)
}

onMounted(() => {
  syncClosedPosition()
  document.addEventListener('dragstart', () => { documentDragging.value = true })
  document.addEventListener('dragend', () => { documentDragging.value = false })
  if (playerId.value) fetchPlayerEntities()
  if (gmMode.value) prefetchEntities()  // warm scene-overview cache before panel opens
  offRollTablePrepare = bus.on('roll-table:prepare', onRollTablePrepare)
  offRollTableResolved = bus.on('roll-table:resolved', onRollTableResolved)
  offCanvasOpenFull = bus.on('canvas:open-full', (payload) => { fullCanvas.value = payload })
  offSwitchPerspective = bus.on('switch-perspective', (id) => switchPerspective(id))
  offSwitchViewLocation = bus.on('switch-view-location', (locId) => switchViewLocation(locId))
  DIAG.mark('onMounted', { showLoginOverlay: showLoginOverlay.value, playerId: playerId.value, entityId: entityId.value, sessionId: sessionId.value, gmMode: gmMode.value })
  // Dump full diagnostic timeline after init settles
  setTimeout(() => {
    DIAG.mark('diag-dump', '--- DIAGNOSTIC SUMMARY ---')
    console.log('%c[diag] STATE SNAPSHOT', 'font-weight:bold', {
      showLoginOverlay: showLoginOverlay.value, playerId: playerId.value, entityId: entityId.value,
      sessionId: sessionId.value, gmMode: gmMode.value, connected: connected.value,
      locationName: locationName.value, bgImageLen: locationBgImage.value.length, peersCount: peers.value.length
    })
    DIAG.dump()
  }, 3000)
})

onUnmounted(() => {
  if (offRollTablePrepare) offRollTablePrepare()
  if (offRollTableResolved) offRollTableResolved()
  if (offCanvasOpenFull) offCanvasOpenFull()
  if (offSwitchPerspective) offSwitchPerspective()
  if (offSwitchViewLocation) offSwitchViewLocation()
})

// Re-sync closed position when sheet visibility changes while wrapper is closed
watch(sheetVisible, () => {
  if (!wrapperOpen.value) nextTick(() => syncClosedPosition())
})

// Refresh the peer bar whenever the dice wrapper opens.
watch(wrapperOpen, (open) => {
  if (open) fetchPeers()
})

function onRolled() {
  sheetRef.value?.resetSfxCounts()
}

function onSfxToggled(e) {
  if (e.sfxId === 'sfx-spray-n-pray') {
    effectCount.value = e.active ? 2 : 1
  }
}

// ── GM shortcuts ─────────────────────────────────

async function onNextBeat() {
  // Clear local pool
  diceRef.value?.clearPool()
  // Clear remote pools and results
  remotePools.value = {}
  remoteResults.value = {}
  currentDifficulty.value = null
  // Clear every pool + difficulty at the location server-side (broadcasts beat_end to all)
  if (currentLocationId.value) {
    await apiNextBeat(currentLocationId.value)
  }
}

async function onAdvanceScene() {
  await apiAdvanceScene()
}

function onStartSession() {
  // Placeholder — could call session creation API
}

function onEndSession() {
  remotePools.value = {}
  remoteResults.value = {}
}


// ── Settings panel ────────────────────────────

function openSettings() {
  console.log('openSettings: playerName =', playerName.value, 'playerId =', playerId.value)
  switchName.value = playerName.value
  switchEditing.value = false
  switchSuggestions.value = []
  switchStatus.value = ''
  switchPending.value = null
  pendingPlayerEntities.value = []
  charStatus.value = ''
  charPending.value = null
  switchError.value = ''
  newCharName.value = ''
  createCharError.value = ''
  showNewChar.value = false
  charSearch.value = ''
  charSearchResults.value = []
  charSearching.value = false
  charSearchSearched.value = false
  charSearchError.value = ''
  allCharactersCache = null
  locationNamesLoaded = false
  fetchPlayerEntities()
  showLoginOverlay.value = true
}

function dismissOverlay() {
  if (playerId.value) {
    if (needsCharacterPick.value) return  // must pick an owned character first
    switchEditing.value = false
    switchStatus.value = ''
    switchPending.value = null
    pendingPlayerEntities.value = []
    charStatus.value = ''
    charPending.value = null
    showLoginOverlay.value = false
  }
}

async function startSwitchEdit() {
  switchEditing.value = true
  await nextTick()
  switchInputRef.value?.focus()
}

function onSwitchBlur() {
  console.log('onSwitchBlur: switchStatus =', switchStatus.value, 'switching =', switching.value, 'playerName =', playerName.value)
  if (!switchStatus.value && !switching.value) {
    console.log('onSwitchBlur: reverting switchName to', playerName.value)
    switchEditing.value = false
    switchName.value = playerName.value
    switchSuggestions.value = []
  }
}

async function fetchPlayerEntities() {
  if (!playerId.value) return
  loadingPlayerEntities.value = true
  try {
    playerEntities.value = await fetchEntitiesFor(playerId.value)
  } finally {
    loadingPlayerEntities.value = false
  }
}

async function fetchLocationNames() {
  if (locationNamesLoaded) return
  try {
    const r = await fetch('/api/v1/locations/tree')
    const tree = await r.json()
    const map = {}
    const walk = (nodes) => {
      for (const n of nodes || []) {
        if (n.id && n.name) map[n.id] = n.name
        if (n.children) walk(n.children)
      }
    }
    walk(tree)
    locationNames.value = map
    locationNamesLoaded = true
  } catch {
    locationNames.value = {}
  }
}

function locationLabel(e) {
  const lid = e?.currentLocation
  if (lid) return locationNames.value[lid] || lid
  return e?.currentUniverse || ''
}

async function fetchEntitiesFor(pid) {
  fetchLocationNames()
  try {
    const r = await fetch(`/api/v1/players/${pid}`)
    const p = await r.json()
    if (p && p.entity_ids) {
      const results = []
      for (const eid of p.entity_ids) {
        try {
          const r2 = await fetch('/api/v1/graphql', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query: `query($id: ID!) { entity(id: $id) { id name type sheetPortrait currentLocation currentUniverse } }`, variables: { id: eid } })
          })
          const json = await r2.json()
          if (json.data?.entity) results.push(json.data.entity)
        } catch {}
      }
      return results
    }
  } catch {}
  return []
}

async function onSwitchEnter() {
  if (switchDebounce) clearTimeout(switchDebounce)
  const name = switchName.value.trim()
  if (!name) return
  switching.value = true
  switchSuggestions.value = []
  switchError.value = ''
  try {
    await searchSwitchPlayers(name)
    const p = await findOrCreatePlayer(name)
    if (!p) { switchError.value = 'Could not reach server'; return }
    switchPending.value = p
    if (p.found) {
      switchStatus.value = `You've transversed before, ${name}.`
      switchFound.value = true
    } else {
      switchStatus.value = `New transverser detected. Welcome, ${name}.`
      switchFound.value = false
    }
    pendingPlayerEntities.value = []
    if (p.found) fetchEntitiesFor(p.id).then(e => { pendingPlayerEntities.value = e })
    switchEditing.value = false
  } catch (e) {
    switchError.value = e.message
  } finally {
    switching.value = false
  }
}

function confirmSwitch() {
  if (!switchPending.value) { console.log('confirmSwitch: no pending'); return }
  const p = switchPending.value
  console.log('confirmSwitch:', p.name, '→ playerName, playerId:', p.id)
  playerId.value = p.id
  playerName.value = p.name
  localStorage.setItem('playerId', p.id)
  localStorage.setItem('playerName', p.name)
  switchStatus.value = ''
  switchPending.value = null
  pendingPlayerEntities.value = []
  switchName.value = ''
  showLoginOverlay.value = false
  playerEntities.value = []
  fetch(`/api/v1/players/${p.id}/claim/${entityId.value}`, { method: 'POST' }).catch(() => {})
  fetchPlayerEntities()
  initLocation()
  loadPlayerRole()
}

function selectCharacter(e) {
  charPending.value = e
  charStatus.value = `Assume the form of ${e.name || e.id}?`
}

async function releaseCharacter(e) {
  if (!playerId.value || !e?.id) return
  try {
    await fetch(`/api/v1/players/${playerId.value}/release/${e.id}`, { method: 'POST' })
  } catch {}
  const wasActive = entityId.value === e.id
  await fetchPlayerEntities()
  if (wasActive && playerEntities.value.length) {
    entityId.value = playerEntities.value[0].id
  }
}

async function fetchAllCharacters() {
  if (allCharactersCache) return allCharactersCache
  fetchLocationNames()
  const r = await fetch('/api/v1/graphql', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query: `query { entities(type: CHARACTER) { id name type sheetPortrait currentLocation currentUniverse } }` })
  })
  const json = await r.json()
  allCharactersCache = json.data?.entities || []
  return allCharactersCache
}

function onCharSearchEnter() {
  if (charSearchDebounce) clearTimeout(charSearchDebounce)
  doCharSearch()
}

// Watch charSearch for live suggestions in settings panel
watch(charSearch, (val) => {
  charSearchError.value = ''
  charSearchSearched.value = false
  if (charSearchDebounce) clearTimeout(charSearchDebounce)
  const q = val.trim()
  if (!q) {
    charSearchResults.value = []
    return
  }
  charSearchDebounce = setTimeout(() => { doCharSearch() }, 200)
})

async function doCharSearch() {
  const q = charSearch.value.trim()
  if (!q) {
    charSearchResults.value = []
    charSearchSearched.value = false
    return
  }
  charSearching.value = true
  charSearchError.value = ''
  try {
    const all = await fetchAllCharacters()
    const owned = new Set(playerEntities.value.map(e => e.id))
    charSearchResults.value = all
      .filter(e => String(e.name || '').toLowerCase().includes(q.toLowerCase()))
      .filter(e => !owned.has(e.id))
      .slice(0, 20)
  } catch (e) {
    charSearchError.value = e.message
    charSearchResults.value = []
  } finally {
    charSearching.value = false
    charSearchSearched.value = true
  }
}

function chooseFoundCharacter(e) {
  charSearch.value = ''
  charSearchResults.value = []
  charSearchSearched.value = false
  charSearchError.value = ''
  charPending.value = e
  charStatus.value = `Assume the form of ${e.name || e.id}?`
}

async function createCharacter() {
  const name = newCharName.value.trim()
  if (!name || creatingChar.value) return
  creatingChar.value = true
  createCharError.value = ''
  try {
    const r = await fetch('/api/v1/graphql', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        query: `mutation($input: CreateEntityInput!) { createEntity(input: $input) { id name type } }`,
        variables: { input: { name, type: 'CHARACTER', universe: universe.value } }
      })
    })
    const json = await r.json()
    const eid = json.data?.createEntity?.id
    if (eid) {
      await fetch(`/api/v1/players/${playerId.value}/claim/${eid}`, { method: 'POST' })
      newCharName.value = ''
      showNewChar.value = false
      allCharactersCache = null
      fetchPlayerEntities()
    } else {
      createCharError.value = 'Failed to create character'
    }
  } catch (e) {
    createCharError.value = e.message
  } finally {
    creatingChar.value = false
  }
}

async function loadPlayerRole() {
  if (!playerId.value) return
  try {
    const r = await fetch(`/api/v1/players/${playerId.value}`)
    DIAG.mark('loadPlayerRole-fetched', { ok: r.ok, status: r.status })
    const p = await r.json()
    if (p && p.role) {
      const isArchitect = p.role === 'architect'
      gmMode.value = isArchitect
      localStorage.setItem('architectMode', isArchitect ? 'true' : 'false')
      DIAG.mark('loadPlayerRole-done', { role: p.role, isArchitect })
    } else {
      DIAG.mark('loadPlayerRole-no-role', { player: p })
    }
  } catch (e) {
    DIAG.mark('loadPlayerRole-err', { error: e.message })
  }
}

function confirmChar() {
  if (!charPending.value) return
  const e = charPending.value
  entityId.value = e.id
  charStatus.value = ''
  charPending.value = null
  showLoginOverlay.value = false
  if (playerId.value) {
    fetch(`/api/v1/players/${playerId.value}/claim/${e.id}`, { method: 'POST' }).catch(() => {})
    fetchPlayerEntities()
  }
}

watch(gmMode, (v) => {
  const role = v ? 'architect' : 'player'
  localStorage.setItem('architectMode', v ? 'true' : 'false')
  if (v) prefetchEntities()  // warm scene-overview cache when entering GM mode
  if (playerId.value) {
    fetch(`/api/v1/players/${playerId.value}/role`, {
      method: 'PATCH', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ role })
    }).catch(() => {})
  }
})
</script>

<style scoped>
.peers-bar {
  display: flex;
  gap: 6px;
  overflow-x: auto;
  padding: 4px 8px;
  scrollbar-width: none;
}
.peers-bar::-webkit-scrollbar { display: none; }
.peer-chip {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
  padding: 3px 10px 3px 4px;
  border-radius: 16px;
  background: var(--bg-panel);
  border: 1px solid rgba(255,255,255,0.08);
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s;
}
.peer-chip:hover { border-color: rgba(255,255,255,0.2); }
.peer-chip.active {
  border-color: var(--accent);
  background: var(--bg-panel);
}
.peer-img, .peer-avatar {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  object-fit: cover;
  flex-shrink: 0;
}
.peer-avatar {
  background: var(--accent-dim);
  color: var(--accent);
  font-size: 10px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
}
.peer-label {
  font-size: 12px;
  white-space: nowrap;
  color: var(--text-dim);
}
.peer-chip.active .peer-label { color: var(--text); }
</style>
