<template>
  <div class="sse-indicator" :class="[connected ? 'shape-circle' : 'shape-triangle', { pulse: ssePulse }]" :title="connected ? 'SSE connected' : (error || 'SSE disconnected')"></div>
  <button v-if="playerId && !showLoginOverlay" class="lab-btn" @click="showResonanceLab = true" title="Resonance Lab">🧪</button>
  <button v-if="gmMode && playerId && !showLoginOverlay" class="settings-btn" @click="openSettings" title="Player settings">↩</button>
  <!-- Login / Settings overlay -->
  <div v-if="showLoginOverlay" class="name-entry panel" @click.self="dismissOverlay">
    <div class="name-entry-scroll">
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

      <!-- Character switch (loading + cancel) -->
      <div v-if="charSwitchLoading" class="settings-section char-switch-section">
        <p class="name-status name-found">Preparing {{ charPending?.name || charPending?.id }}…</p>
        <button class="char-loading-btn" @click="cancelCharacterSwitch">
          <RazmeritWaves :from="resonanceFrom" :to="resonanceTo" :done="charSwitchDone" :duration="RESONANCE.durationMs" :fan-duration="RESONANCE.fanMs" />
          <span class="char-loading-label">Harmonizing razmerit… tap to cancel</span>
        </button>
      </div>

      <!-- Mode + Characters (hidden during switch) -->
      <template v-if="!switchStatus && !charSwitchLoading">
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
                <span class="char-chip-name">{{ e.name || e.id }} <span v-if="e.main" class="main-badge">MAIN</span></span>
                <span v-if="locationLabel(e)" class="char-chip-location">{{ locationLabel(e) }}</span>
              </span>
              <span class="main-toggle" :class="{ on: e.main }" :title="e.main ? 'Unset as main' : 'Set as main'" @click.stop="toggleMain(e)">★</span>
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

        <div v-if="mySupportCharacters.length" class="settings-section">
          <label class="settings-label">Support characters</label>
          <div class="char-list support-list">
            <button
              v-for="sc in mySupportCharacters" :key="sc.entity.id"
              class="char-chip support-chip"
              :class="{ 'support-unavailable': !sc.mainActive, 'support-current': sc.entity.id === entityId }"
              :disabled="!sc.mainActive"
              @click="assumeSupport(sc)"
            >
              <MediaImage v-if="sc.entity.sheetPortrait" :src="sc.entity.sheetPortrait" class="char-portrait" alt="" />
              <span v-else class="char-portrait char-portrait-fallback">{{ (sc.entity.name || sc.entity.id).charAt(0) }}</span>
              <span class="char-chip-meta">
                <span class="char-chip-name">{{ sc.entity.name || sc.entity.id }}</span>
                <span class="char-chip-location support-main">supports {{ sc.main?.name || '—' }}</span>
              </span>
              <span v-if="sc.mainActive" class="support-available-dot" title="Available">●</span>
            </button>
          </div>
          <p v-if="!mySupportCharacters.some(sc => sc.mainActive)" class="support-hint">No support characters are available right now — their mains are inactive.</p>
        </div>

        <div v-if="!gmMode" class="settings-section">
          <label class="settings-label">Create support character</label>
          <template v-if="otherPlayersMains.length">
            <div class="other-mains-list">
              <div v-for="a in otherPlayersMains" :key="a.playerId" class="other-main-row">
                <MediaImage v-if="a.main?.sheetPortrait" :src="a.main.sheetPortrait" class="char-portrait" alt="" />
                <span v-else class="char-portrait char-portrait-fallback">{{ (a.main?.name || a.playerId).charAt(0) }}</span>
                <span class="char-chip-meta">
                  <span class="char-chip-name">{{ a.main?.name || a.playerId }}</span>
                  <span class="char-chip-location">{{ a.playerName || a.playerId }}</span>
                </span>
                <button class="support-create-btn support-create-inline" :title="'Create a support character for ' + (a.main?.name || a.playerId)" @click="openCreateSupport(a.main.id)">＋ support</button>
              </div>
            </div>
          </template>
          <p v-else class="support-hint">No other mains are active right now to support.</p>
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
      <button v-if="!charSwitchLoading" class="cancel-btn" @click="dismissOverlay">Back to game</button>
    </template>
    </div>
  </div>
  <ResonanceLab v-if="showResonanceLab" @close="showResonanceLab = false" />
  <RollTableMenu
    v-if="supportCastMenu"
    :entity-id="supportCastMenu.mainEntityId"
    :table-id="supportCastMenu.tableId"
    :title="supportCastMenu.mainName ? ('Create Support Character for ' + supportCastMenu.mainName) : 'Create Support Character'"
    :entity-razmerit="supportCastMenu.mainRazmerit"
    mode="create-support"
    :player-id="playerId"
    :main-entity-id="supportCastMenu.mainEntityId"
    @applied="onSupportCreated"
    @close="supportCastMenu = null"
  />
  <div class="stage" :class="[mobileStackActive ? 'mobile-stack' : '', mobileStackActive ? 'focus-' + mobileFocus : '']">
    <div class="loc-band">
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
      <div v-if="mobileStackActive && mobileFocus !== 'location'" class="band-tap" @click="setMobileFocus('location')"></div>
    </div>
    <div ref="wrapperEl" class="dice-panel-wrapper" :class="{ open: wrapperOpen }" @mouseenter="onWrapperEnter" @mouseleave="onWrapperLeave">
      <div v-if="(wrapperOpen || mobileStackActive) && peers.length" class="peers-bar">
        <button v-for="p in peers" :key="p.id" class="peer-chip" :class="{ active: isPeerActive(p) }" @click.stop="onPeerClick(p.id)" :title="p.name">
          <MediaImage v-if="p.sheetImage" :src="p.sheetImage" class="peer-img" alt="" />
          <span v-else class="peer-avatar">{{ p.name.charAt(0) }}</span>
          <span class="peer-label">{{ p.name }}</span>
        </button>
      </div>
      <div class="sheet-band">
        <CharacterSheet
          v-show="(mobileStackActive || (sheetVisible && (phase === 'adding' || forceSheet))) && (!gmMode || actingEntityId || viewingEntityId)"
          ref="sheetRef"
          class="embedded-sheet"
          :class="{ 'sheet-hidden': !sheetVisible && !mobileStackActive }"
          :entity-id="entityId"
          :override-entity-id="viewingEntityId"
          :viewer-entity-id="entityId"
          :player-owned-entity-ids="ownedEntityIds"
          :player-id="playerId"
          :main-entity-id="selfEntityId"
          :universe="universe"
          :phase="phase"
          :visible="sheetVisible || mobileStackActive"
          embedded
          :gm-mode="gmMode"
          @open-settings="openSettings"
          @add-to-pool="(d) => diceRef?.addFromSheet(d)"
          @remove-from-pool="(s) => diceRef?.removeBySource(s)"
          @remove-by-ts-id="(id) => diceRef?.removeByTsId(id)"
          @split-die="(d) => diceRef?.splitDie(d)"
          @sfx-toggled="onSfxToggled"
          @stamp-sfx="(d) => diceRef?.stampArmedSfx(d.tsId, d.sfxId)"
          @sheet-view-change="onSheetViewChange"
        />
        <div v-if="mobileStackActive && mobileFocus !== 'sheet'" class="band-tap" @click="setMobileFocus('sheet')"></div>
      </div>
      <div class="roller-band" :style="{ '--roller-h': rollerContentH + 'px' }">
        <DiceRoller ref="diceRef" :entity-id="entityId" :universe="universe" :mode="rollerMode" :keep-count="keepCount" :effect-count="effectCount" :gm-mode="gmMode" :difficulty="currentDifficulty" :player-id="playerId" :location-id="currentLocationId" :peers="peers" :acting-entity-id="gmMode ? actingEntityId : entityId" :fallback-entity-id="selfEntityId" :remote-pools="remotePools" :remote-results="remoteResults" :sfx-choice-request="sfxChoiceRequest" @update:universe="u => universe = u" @rolled="onDiceRolled" @picked="(r) => shareRoll(r)" @difficulty="onDifficultyCommitted" @pool-change="onPoolChange" @phase-change="onPhaseChange" @panel-open="onPanelOpen" @panel-drag-start="onPanelDragStart" @panel-drag="onPanelDrag" @panel-drag-end="onPanelDragEnd" @sfx-choice-resolved="onSfxChoiceResolved" @acting-entity-change="onActingEntityChange" @offered-change="(ids) => sheetRef?.setOfferedTraits(ids)" />
        <div v-if="mobileStackActive && mobileFocus !== 'dice'" class="band-tap" @click="setMobileFocus('dice')"></div>
      </div>
    </div>
  </div>
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
  <PanelStack v-if="gmMode" :root-panel="gmRootPanel" />
  <ToastBar :toasts="toasts" @dismiss="dismissToast" />
</template>

<script setup>
import { ref, reactive, useTemplateRef, watch, computed, nextTick, onMounted, onUnmounted } from 'vue'
import LocationViewer from './components/LocationViewer.vue'
import CharacterSheet from './components/CharacterSheet.vue'
import DiceRoller from './components/DiceRoller.vue'
import GmPanel from './components/GmPanel.vue'
import PanelStack from './components/gm/PanelStack.vue'
import RelationalCanvas from './components/canvas/RelationalCanvas.vue'
import MediaImage from './components/MediaImage.vue'
import RazmeritWaves from './components/RazmeritWaves.vue'
import ResonanceLab from './components/ResonanceLab.vue'
import { signatureOf, RESONANCE } from './composables/resonance.js'
import { useSSE } from './composables/useSSE.js'
import { useSessions } from './composables/useSessions.js'
import { useToasts } from './composables/useToasts.js'
import { useApi } from './composables/useApi.js'
import { usePanelBus } from './composables/usePanelBus.js'
import { useEntityCrud } from './composables/useEntityCrud.js'
import { useMediaQuality } from './composables/useMediaQuality.js'
import { useEntityCache } from './composables/entityCache.js'
import { perfMark } from './composables/perfLog.js'
import { useTroupe } from './composables/useTroupe.js'
import ToastBar from './components/ToastBar.vue'
import RollTableMenu from './components/gm/RollTableMenu.vue'

const { graphql, getDifficulty: apiGetDifficulty, setDifficulty: apiSetDifficulty, nextBeat: apiNextBeat, advanceScene: apiAdvanceScene, listAllPools: apiListAllPools } = useApi()
const { fetchEntities: prefetchEntities } = useEntityCrud()
const { quality: mediaQuality, setQuality: setMediaQuality, resolveMediaUrl, isLowQuality } = useMediaQuality()
const entityCache = useEntityCache()
const bus = usePanelBus()
const { supportCharacters, activeMains, onlinePlayers, fetchSupportCharacters, fetchActiveMains, fetchSupportCastTableId, fetchRecency, fetchPlayerBodies, fetchOnlinePlayers } = useTroupe()

// ── Diagnostic logger (must be first — used throughout setup) ──
const DIAG = {
  marks: [],
  mark(label, detail) {
    const entry = { label, time: performance.now().toFixed(1), detail }
    this.marks.push(entry)
    perfMark(label, detail)
  },
  dump() {
    const lines = this.marks.map(m => {
      const d = m.detail !== undefined && m.detail !== null
        ? (typeof m.detail === 'object' ? JSON.stringify(m.detail) : String(m.detail))
        : ''
      return `  +${m.time}ms ${m.label}${d ? ' ' + d : ''}`
    })
    console.log('[perf] --- timeline summary ---\n' + lines.join('\n'))
  }
}

DIAG.mark('app-setup-start', { entityId: localStorage.getItem('entityId'), playerId: localStorage.getItem('playerId'), playerName: localStorage.getItem('playerName'), architectMode: localStorage.getItem('architectMode') })

// ── GM panel root spec for PanelStack ──
const gmRootPanel = computed(() => ({
  component: GmPanel,
  props: {
    universe: universe.value,
    currentLocationId: currentLocationId.value,
    currentLocationName: locationName.value,
    currentEntityId: actingEntityId.value,
  },
  listeners: {
    'next-beat': () => onNextBeat(),
    'advance-scene': () => onAdvanceScene(),
    'start-session': () => onStartSession(),
    'end-session': () => onEndSession(),
    'add-to-pool': (d) => diceRef?.addFromSheet(d),
    'stamp-sfx': (d) => diceRef?.stampArmedSfx(d.tsId, d.sfxId),
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
      fetchPeers(true)
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

// The full entity list (with sheet images) is location-independent, so we cache
// it and only re-fetch when the data itself may have changed (SSE / location
// events pass force=true). Panel-open refreshes reuse the cache.
let peersCache = null  // { entities, at }
const PEERS_TTL_MS = 30_000

function applyPeers(entities) {
  const TYPE_ORDER = { CHARACTER: 0, GMC: 1, ASSET: 2, LOCATION: 3 }
  const atLocation = entities
    .filter(e => e.currentLocation === currentLocationId.value)
    .filter(e => gmMode.value || !e.unpublished)
  const here = entities.find(e => e.id === currentLocationId.value)
  const combined = here && !atLocation.some(e => e.id === here.id)
    ? [here, ...atLocation]
    : atLocation
  peers.value = combined.sort((a, b) => {
    if (a.id === entityId.value) return -1
    if (b.id === entityId.value) return 1
    return (TYPE_ORDER[a.type] ?? 9) - (TYPE_ORDER[b.type] ?? 9)
  })
}

async function fetchPeers(force = false) {
  if (!force && peersCache && Date.now() - peersCache.at < PEERS_TTL_MS) {
    applyPeers(peersCache.entities)
    resolvePeerSheetImages()
    return
  }
  DIAG.mark('fetchPeers-start', { currentLocationId: currentLocationId.value })
  const data = await graphql(`query {
    entities { id type name currentLocation unpublished }
  }`)
  if (data?.entities) {
    peersCache = { entities: data.entities, at: Date.now() }
    applyPeers(data.entities)
    resolvePeerSheetImages()
    DIAG.mark('fetchPeers-done', { total: data.entities.length, atLocation: peers.value.length })
  } else {
    DIAG.mark('fetchPeers-no-data')
  }
}

async function resolvePeerSheetImages() {
  const ids = peers.value.map((p) => p.id).filter(Boolean)
  if (!ids.length) return
  const qs = new URLSearchParams({ role: 'sheet', ids: ids.join(',') })
  const r = await fetch(`/api/v1/entities/images?${qs}`)
  if (!r.ok) return
  const data = await r.json()
  const images = data?.images || {}
  peers.value = peers.value.map((p) => ({ ...p, sheetImage: images[p.id] || '' }))
}

function onMoved(data) {
  locationName.value = data.location
  if (data.universe) universe.value = data.universe
  currentLocationId.value = data.location_id || data.location
  fetchLocationBg()
  fetchPeers(true)
}

const selfEntityId = ref(localStorage.getItem('entityId') || 'kael-1')  // stable identity (SSE/login); for GM this is not a "main" entity
const entityId = ref(selfEntityId.value)  // perspective entity; null = GM free-roam view
const editZones = ref(false)

let locationInitPromise = null

// When switching entities, update location (players only — for GM, entityId
// is a freely-switchable perspective and must not re-init location or persist).
watch(entityId, () => {
  if (!entityId.value || gmMode.value) return
  localStorage.setItem('entityId', entityId.value)
  locationInitPromise = initLocation()
  refreshDiceBonuses()
}, { flush: 'sync' })
const diceBonuses = reactive({ total: 0, effect: 0 })  // persisted deltas from modify_dice_limit effects
const sprayNprayActive = ref(false)  // local override: +1 effect die while sfx-spray-n-pray is armed
const keepCount = computed(() => Math.max(1, 2 + diceBonuses.total))
const effectCount = computed(() => Math.max(0, 1 + diceBonuses.effect + (sprayNprayActive.value ? 1 : 0)))

async function refreshDiceBonuses() {
  const id = entityId.value
  if (!id || gmMode.value) return
  const data = await graphql(`query($id: ID!) { entity(id: $id) { totalDiceBonus effectDiceBonus } }`, { id })
  if (data?.entity) {
    diceBonuses.total = data.entity.totalDiceBonus ?? 0
    diceBonuses.effect = data.entity.effectDiceBonus ?? 0
  }
}
const phase = ref('adding')
const rollerMode = ref('cortex') // 'cortex' | 'roll_table' (driven by CharacterSheet tab)
const currentDifficulty = ref(null) // GM-set test difficulty (ephemeral, session-scoped)
const sfxChoiceRequest = ref(null) // pending {choose_*} auto-fired SFX choices for this player

// Player identity
const playerId = ref(localStorage.getItem('playerId') || '')
const playerName = ref(localStorage.getItem('playerName') || '')
const showLoginOverlay = ref(!playerId.value)
const showResonanceLab = ref(false)
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
const charSwitchLoading = ref(false)
const charSwitchDone = ref(false)
const resonanceFrom = ref([])
const resonanceTo = ref([])
let charSwitchToken = 0
let charSwitchPreviousEntityId = null
const pendingPlayerEntities = ref([])
const playerEntities = ref([])
const loadingPlayerEntities = ref(false)

const locationNames = ref({})
let locationNamesLoaded = false

const ownedEntityIds = computed(() => playerEntities.value.map(e => e.id))
// Support characters the player has agency over (owned) — not every player's
// SCs. Assumed-but-unowned SCs are intentionally excluded from this list.
const mySupportCharacters = computed(() =>
  supportCharacters.value.filter((sc) => sc.ownerId === playerId.value)
)

// The support character currently being played (if any), for the assume/return
// affordance (B57).
const currentSupport = computed(() =>
  supportCharacters.value.find((sc) => sc.entity?.id === entityId.value) || null
)
// True when playing as a non-GM but the current perspective entity isn't one
// the player owns — the settings overlay must stay open until they pick one.
// Assumed support characters are exempt: they are intentionally unowned.
const needsCharacterPick = computed(() =>
  !gmMode.value && !!playerId.value &&
  !ownedEntityIds.value.includes(entityId.value) &&
  !currentSupport.value
)

// B66 — create-support targets another player's active main (not your own).
// `activeMains` is one entry per active main: { playerId, playerName, main }.
const otherPlayersMains = computed(() =>
  activeMains.value.filter((a) => a.playerId !== playerId.value)
)

function mainName(id) {
  if (!id) return ''
  const active = activeMains.value.find((a) => a.main?.id === id)
  if (active?.main?.name) return active.main.name
  return playerEntities.value.find((e) => e.id === id)?.name || id
}

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
  loadPlayerRole()
}
ensurePlayer()

// Session management
const { sessions, currentSession, listSessions, createSession, joinSession, publishEvent, startSession, endSession } = useSessions()
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
const initSessionPromise = initSession()
DIAG.mark('initLocation-called')
const peers = ref([])
const initLocationPromise = initLocation()

// Mark play-ready once the initial pipeline (session + location + background +
// peers) settles. The sheet and pool log their own completion marks.
Promise.allSettled([initSessionPromise, initLocationPromise]).then(() => {
  DIAG.mark('app-ready', {
    location: currentLocationId.value,
    peers: peers.value.length,
    session: sessionId.value,
  })
})

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
  // The difficulty is location-scoped server state, not session state — persist
  // it even in solo play (session-default) so the same-device GM can switch to a
  // character and roll against it. Set the local ref too, so the target shows
  // without waiting for the SSE round-trip.
  currentDifficulty.value = difficulty
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
  viewingEntityId.value = null  // clear any read-only location inspect
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
  fetchPeers(true)
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
  viewingEntityId.value = null  // clear any read-only location inspect
}

function onInspectEntity(id) {
  if (gmMode.value) {
    onPeerClick(id)
    sheetVisible.value = true
    return
  }
  // Map-dot semantics (deliberately NOT the peer-chip toggle):
  //   self dot    → own sheet
  //   foreign dot → open if closed/different; close if already open & showing it
  const isSelf = id === entityId.value || id === selfEntityId.value
  if (isSelf) {
    viewingEntityId.value = null
    forceSheet.value = true
    sheetVisible.value = true
    return
  }
  const alreadyShowing = viewingEntityId.value === id
  const sheetOpen = sheetVisible.value
  if (alreadyShowing && sheetOpen) {
    viewingEntityId.value = null
    closePanel()
  } else {
    viewingEntityId.value = id
    forceSheet.value = true
    sheetVisible.value = true
  }
}

function isPeerActive(p) {
  const viewed = viewingEntityId.value
  const acted = gmMode.value ? actingEntityId.value : null
  if (viewed && viewed === p.id) return true
  if (acted && acted === p.id) return true
  if (!viewed && !acted && entityId.value === p.id) return true
  return false
}

function onPeerClick(id) {
  if (gmMode.value) {
    const isLocation = peers.value.find(p => p.id === id)?.type === 'LOCATION'
    if (isLocation) {
      // View the location's read-only sheet instead of assuming it.
      viewingEntityId.value = viewingEntityId.value === id ? null : id
      forceSheet.value = true
      return
    }
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
const { connected, lastEvent, error } = useSSE(sessionId, computed(() => entityId.value || selfEntityId.value), playerId)

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

// A GMC is a GM-controlled character (no player owner) — the target the GM
// must switch to when a player challenges it.
function isGmcEntity(id) {
  if (!id) return false
  const atLocation = peers.value.find(e => e.id === id)
  if (atLocation) return atLocation.type === 'GMC'
  return (peersCache?.entities || []).some(e => e.id === id && e.type === 'GMC')
}

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
      entityCache.invalidateSheet(evt.data?.entity_id)
      if (evt.data?.new_balance != null) {
        sheetRef.value?.setRazmerit(evt.data.new_balance, evt.data.entity_id)
      }
      break
    case 'dice_limits_changed':
      if (evt.data?.entity_id === entityId.value) {
        diceBonuses.total = evt.data.total_dice_bonus ?? 0
        diceBonuses.effect = evt.data.effect_dice_bonus ?? 0
      }
      break
    case 'beat_end':
      diceRef.value?.clearPool()
      remotePools.value = {}
      remoteResults.value = {}
      currentDifficulty.value = null
      if (gmMode.value) addToast('Beat ended', 'dice')
      break
    case 'session_started':
      addToast('Session started', 'session')
      break
    case 'session_ended':
      addToast('Session ended', 'session')
      break
    case 'main_active':
      // A main became active/inactive — refresh support-character availability,
      // active mains, current bodies, and the GM troupe overview recency.
      fetchSupportCharacters(true)
      fetchActiveMains(true)
      fetchRecency(true)
      fetchPlayerBodies(true)
      break
    case 'presence_changed':
      fetchOnlinePlayers(true)
      break
    case 'trait_updated':
      entityCache.invalidateSheet(evt.data?.entity_id)
      if (evt.data?.entity_id === entityId.value) {
        if (evt.data?.trait_setting_id) {
          diceRef.value?.resyncTraitDie(evt.data.trait_setting_id, evt.data.new_dice ?? [evt.data.new_rating])
        }
        sheetRef.value?.fetchEntity()
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
        fetchPeers(true)
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
      entityCache.invalidateSheet(eid)
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
      const actor = evt.data.actor_id ?? evt.data.player_id ?? eid
      if (eid === entityId.value && actor !== entityId.value && Array.isArray(evt.data.dice)) {
        // Another entity changed my pool (e.g. offered a negative trait) — sync it.
        diceRef.value?.syncPool(evt.data.dice)
      } else if (eid && eid !== entityId.value) {
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
      if (gmMode.value) {
        addToast(`${entName(evt.data?.challenger_id)} challenged ${entName(evt.data?.opponent_id)}`, 'dice')
        // Auto-switch to a challenged GMC so the GM can roll its side at once.
        const oppId = evt.data?.opponent_id
        if (oppId && isGmcEntity(oppId) && actingEntityId.value !== oppId) {
          switchPerspective(oppId)
        }
      }
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
      // Show for the viewer's own entity, or for any entity in GM mode.
      if (evt.data?.entity_id === entityId.value || gmMode.value) {
        const sfxLabel = evt.data?.sfx_name || evt.data?.sfx_id
        const who = evt.data?.entity_id === entityId.value ? '' : ` (${name})`
        addToast(`SFX: ${sfxLabel}${who}`, 'sfx')
      }
      break
    case 'sfx_choice_required':
      if (evt.data?.entity_id === entityId.value || gmMode.value) {
        sfxChoiceRequest.value = (evt.data.choices || []).map((c, i) => ({
          ...c, index: i, entity_id: evt.data.entity_id,
        }))
      }
      break
  }
})

function onSfxChoiceResolved(pendingChoices) {
  sfxChoiceRequest.value = (pendingChoices && pendingChoices.length)
    ? pendingChoices.map((c, i) => ({ ...c, index: i }))
    : null
}

function onPhaseChange(p) {
  if (rollerMode.value === 'roll_table') return
  phase.value = p
  if (p !== 'adding') forceSheet.value = false
  if (p === 'adding') {
    sprayNprayActive.value = false
    refreshDiceBonuses()
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
let panelResizeObserver = null
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

// ── Panel drag-to-open/close (touch) ───────────────
// The DiceRoller emits panelDragStart / panelDrag / panelDragEnd with raw
// deltas; here we move the wrapper 1:1 with the finger and settle by
// threshold + velocity. Tune these constants to adjust feel.
const PANEL_CLOSED_PEEK = 56       // px of the panel left visible when closed
const PANEL_DRAG_DISTANCE = 72     // px: slow-drag distance that triggers open/close
const PANEL_DRAG_VELOCITY = 0.5    // px/ms: flick speed that triggers open/close

const panelDragState = { active: false, wasOpen: false, startOffset: 0 }

function syncClosedPosition() {
  if (mobileStackActive.value || !wrapperEl.value) return
  const h = wrapperEl.value.offsetHeight
  wrapperEl.value.style.transform = `translateX(-50%) translateY(${h - PANEL_CLOSED_PEEK}px)`
}

function onPanelDragStart() {
  if (mobileStackActive.value) return
  const el = wrapperEl.value
  if (!el) return
  panelDragState.wasOpen = wrapperOpen.value
  panelDragState.startOffset = panelDragState.wasOpen ? 0 : Math.max(0, el.offsetHeight - PANEL_CLOSED_PEEK)
  panelDragState.active = true
  el.style.transition = 'none'
}

function onPanelDrag(dy) {
  const el = wrapperEl.value
  if (!el || !panelDragState.active) return
  const closedOffset = Math.max(0, el.offsetHeight - PANEL_CLOSED_PEEK)
  const offset = Math.max(0, Math.min(closedOffset, panelDragState.startOffset + dy))
  el.style.transform = `translateX(-50%) translateY(${offset}px)`
}

function onPanelDragEnd({ dy, velocity }) {
  const el = wrapperEl.value
  if (!el || !panelDragState.active) return
  panelDragState.active = false

  let open
  if (velocity <= -PANEL_DRAG_VELOCITY) open = true        // fast flick up → open
  else if (velocity >= PANEL_DRAG_VELOCITY) open = false   // fast flick down → close
  else if (dy <= -PANEL_DRAG_DISTANCE) open = true         // dragged up enough → open
  else if (dy >= PANEL_DRAG_DISTANCE) open = false         // dragged down enough → close
  else open = panelDragState.wasOpen                       // revert to previous state

  el.style.transition = ''  // re-enable the CSS transition, then settle
  logPanelGeometry('drag-end')
  if (open) {
    if (diceRef.value) diceRef.value.panelOpen = true
    openPanel()
  } else {
    closePanel()
  }
}

// ── Mobile focus stack ───────────────────────────────
// Player phones get three first-class bands (location / sheet / dice)
// instead of the desktop bottom sheet. The focused band grows; tapping a
// teaser band expands it (the .band-tap capture layers above). Breakpoint
// mirrors the @media block in styles.css.
const MOBILE_MAX_WIDTH = 820
const isMobile = ref(false)
const mobileFocus = ref('location')  // 'location' | 'sheet' | 'dice'

const mobileMq = window.matchMedia(`(max-width: ${MOBILE_MAX_WIDTH}px)`)
function syncIsMobile() { isMobile.value = mobileMq.matches }
syncIsMobile()
mobileMq.addEventListener('change', syncIsMobile)
onUnmounted(() => mobileMq.removeEventListener('change', syncIsMobile))

const mobileStackActive = computed(() => isMobile.value && !gmMode.value)

function setMobileFocus(f) {
  if (f === 'location' || f === 'sheet' || f === 'dice') mobileFocus.value = f
}

// Focus is tap-driven only — no auto-focus on phase changes. (An earlier
// phase watcher yanked focus around rolls, which read as panel jumps.)

// The mobile dice-focus band sizes to the roller's CONTENT as a concrete
// length (keyword flex-basis: auto doesn't interpolate, which made entering /
// leaving dice focus jump). --roller-h feeds the clamp() in styles.css.
const rollerContentH = ref(148)
function syncRollerContentH() {
  const roller = wrapperEl.value?.querySelector('.dice-roller')
  if (roller) rollerContentH.value = Math.max(0, roller.scrollHeight)
}
watch(mobileFocus, () => nextTick(syncRollerContentH))
watch(isMobile, () => nextTick(syncRollerContentH))
onMounted(() => {
  const roller = wrapperEl.value?.querySelector('.dice-roller')
  if (!roller) return
  syncRollerContentH()
  const mo = new MutationObserver(syncRollerContentH)
  mo.observe(roller, { subtree: true, childList: true, attributes: true, characterData: true })
  window.addEventListener('resize', syncRollerContentH)
  onUnmounted(() => {
    mo.disconnect()
    window.removeEventListener('resize', syncRollerContentH)
  })
})

// ── Panel geometry diagnostics ─────────────────────
// The wrapper is position:fixed;bottom:0 and slides via an inline translateY
// (closed = `translateY(offsetHeight - PANEL_CLOSED_PEEK)`). When it ends up
// off-screen / half-hidden, these numbers tell us whether it's a stale height,
// a visual-vs-layout viewport offset, or a stuck transform. Exposed as
// `window.__panelDebug()` for copy-paste from devtools.
function panelGeometry() {
  const el = wrapperEl.value
  const roller = el?.querySelector('.dice-roller')
  const sheet = el?.querySelector('.embedded-sheet')
  const vv = window.visualViewport
  const vh = vv?.height ?? window.innerHeight
  const rect = el?.getBoundingClientRect()
  const rollerRect = roller?.getBoundingClientRect()
  const sheetRect = sheet?.getBoundingClientRect()
  return {
    viewport: {
      innerW: window.innerWidth,
      innerH: window.innerHeight,
      visualW: vv?.width ?? null,
      visualH: vv?.height ?? null,
      visualOffsetTop: vv?.offsetTop ?? null,
      scale: vv?.scale ?? null,
    },
    wrapper: {
      top: rect ? Math.round(rect.top) : null,
      bottom: rect ? Math.round(rect.bottom) : null,
      height: rect ? Math.round(rect.height) : null,
      offsetHeight: el?.offsetHeight ?? null,
      scrollHeight: el?.scrollHeight ?? null,
      inlineTransform: el?.style.transform || '(none)',
      computedTransform: el ? getComputedStyle(el).transform : null,
      open: wrapperOpen.value,
    },
    sheet: sheetRect ? { top: Math.round(sheetRect.top), bottom: Math.round(sheetRect.bottom), height: Math.round(sheetRect.height), display: getComputedStyle(sheet).display } : null,
    roller: rollerRect ? { top: Math.round(rollerRect.top), bottom: Math.round(rollerRect.bottom), height: Math.round(rollerRect.height) } : null,
    state: {
      hoverOpen: hoverOpen.value,
      sheetVisible: sheetVisible.value,
      forceSheet: forceSheet.value,
      phase: phase.value,
      gmMode: gmMode.value,
      closedOffset: el ? Math.max(0, el.offsetHeight - PANEL_CLOSED_PEEK) : null,
    },
    flags: {
      wrapperBelowViewport: rect ? rect.bottom > vh + 1 : null,
      rollerBelowViewport: rollerRect ? rollerRect.bottom > vh + 1 : null,
      wrapperAboveViewport: rect ? rect.top < -1 : null,
      visualViewportShorter: vv ? vv.height < window.innerHeight : false,
    },
  }
}

function logPanelGeometry(label) {
  const g = panelGeometry()
  const w = g.wrapper, r = g.roller ?? {}, v = g.viewport
  console.log(
    `%c[panel] ${label}`,
    'font-weight:bold; color:#8ecae6',
    `wrapper top=${w.top} bottom=${w.bottom} h=${w.height} open=${w.open} inline="${w.inlineTransform}"`,
    `roller top=${r.top ?? '-'} bottom=${r.bottom ?? '-'}`,
    `viewport innerH=${v.innerH} visualH=${v.visualH} vOffsetTop=${v.visualOffsetTop} scale=${v.scale}`,
    `state hoverOpen=${g.state.hoverOpen} sheetVisible=${g.state.sheetVisible} phase=${g.state.phase} closedOffset=${g.state.closedOffset}`,
    `flags belowViewport=${g.flags.wrapperBelowViewport} rollerBelow=${g.flags.rollerBelowViewport} aboveViewport=${g.flags.wrapperAboveViewport} visualShorter=${g.flags.visualViewportShorter}`,
  )
  return g
}

function onViewportResize() {
  // Viewport changes (orientation, keyboard, URL-bar collapse) can leave a
  // fixed-position panel drifted. Re-sync the closed position, and log so the
  // human can correlate a mis-position with the resize.
  if (!wrapperOpen.value) nextTick(() => syncClosedPosition())
  logPanelGeometry('viewport-resize')
}

function onPanelOpen(v) {
  if (gmMode.value || mobileStackActive.value) return
  if (v) openPanel()
  else closePanel()
}

// Click inside the dice roller pins the panel open briefly, so the mouse can
// leave without the hover-close firing. Tune HOVER_HOLD_MS to adjust feel.
const HOVER_HOLD_MS = 2500
const hoverHoldUntil = ref(0)

function armHoverHold() {
  hoverHoldUntil.value = Date.now() + HOVER_HOLD_MS
}

function onWrapperEnter() {
  if (closeTimer) { clearTimeout(closeTimer); closeTimer = null }
  openPanel()
}

function onWrapperLeave() {
  if (phase.value === 'picking') return  // don't close during dice drag-and-drop
  if (documentDragging.value) return    // don't close during HTML5 drag-and-drop
  if (Date.now() < hoverHoldUntil.value) return  // pinned open by a recent roller click
  closeTimer = setTimeout(() => {
    closeTimer = null
    closePanel()
  }, 1000)
}

// Tap outside the panel closes it — without a full-screen overlay, so the
// location map behind stays interactive. Capture phase so it also fires on
// map dots (whose own @click stops bubbling). Occupant/self dots are excluded:
// they open/close the sheet themselves via onInspectEntity.
function onDocumentClick(e) {
  // A click inside the dice roller pins the panel open briefly.
  if (e.target.closest && e.target.closest('.dice-roller')) {
    armHoverHold()
  }
  if (gmMode.value) return
  if (!wrapperOpen.value) return
  if (phase.value === 'picking') return
  const el = wrapperEl.value
  if (el && el.contains(e.target)) return
  if (e.target.closest && e.target.closest('.occ-dot')) return
  closePanel()
}

let presencePollTimer = null

onMounted(() => {
  syncClosedPosition()
  // Panel diagnostics — run window.__panelDebug() in devtools to dump geometry.
  if (typeof window !== 'undefined') {
    window.__panelDebug = () => {
      const g = logPanelGeometry('manual')
      console.log('%c[panel] geometry (copy this)', 'font-weight:bold', JSON.stringify(g, null, 2))
      return g
    }
    window.addEventListener('resize', onViewportResize)
    window.addEventListener('orientationchange', onViewportResize)
    if (window.visualViewport) window.visualViewport.addEventListener('resize', onViewportResize)
    if (typeof ResizeObserver !== 'undefined' && wrapperEl.value) {
      panelResizeObserver = new ResizeObserver(() => {
        if (!wrapperOpen.value) nextTick(() => syncClosedPosition())
      })
      panelResizeObserver.observe(wrapperEl.value)
    }
  }
  document.addEventListener('dragstart', () => { documentDragging.value = true })
  document.addEventListener('dragend', () => { documentDragging.value = false })
  document.addEventListener('click', onDocumentClick, true)  // capture: outside-tap closes panel
  if (playerId.value) fetchPlayerEntities()
  if (playerId.value) fetchSupportCharacters()
  if (playerId.value) fetchActiveMains()
  // Periodically re-fetch presence so grace-window expiry (a player whose device
  // slept past the 10-minute grace) drops them from the online list.
  presencePollTimer = setInterval(() => { if (playerId.value) fetchOnlinePlayers(true) }, 60_000)
  if (gmMode.value) prefetchEntities()  // warm scene-overview cache before panel opens
  refreshDiceBonuses()
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
  document.removeEventListener('click', onDocumentClick, true)
  window.removeEventListener('resize', onViewportResize)
  window.removeEventListener('orientationchange', onViewportResize)
  if (window.visualViewport) window.visualViewport.removeEventListener('resize', onViewportResize)
  if (panelResizeObserver) panelResizeObserver.disconnect()
  if (offRollTablePrepare) offRollTablePrepare()
  if (offRollTableResolved) offRollTableResolved()
  if (offCanvasOpenFull) offCanvasOpenFull()
  if (offSwitchPerspective) offSwitchPerspective()
  if (offSwitchViewLocation) offSwitchViewLocation()
  if (presencePollTimer) clearInterval(presencePollTimer)
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
    sprayNprayActive.value = e.active
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
  if (sessionId.value && sessionId.value !== 'session-default') {
    startSession(sessionId.value)
  }
}

function onEndSession() {
  remotePools.value = {}
  remoteResults.value = {}
  if (sessionId.value && sessionId.value !== 'session-default') {
    endSession(sessionId.value)
  }
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
  charSwitchLoading.value = false
  charSwitchDone.value = false
  charSwitchToken++
  charPending.value = null
  charSwitchPreviousEntityId = null
  resonanceFrom.value = []
  resonanceTo.value = []
  switchError.value = ''
  newCharName.value = ''
  createCharError.value = ''
  showNewChar.value = false
  charSearch.value = ''
  charSearchResults.value = []
  charSearching.value = false
  charSearchSearched.value = false
  charSearchError.value = ''
  fetchPlayerEntities()
  fetchSupportCharacters()
  fetchActiveMains()
  showLoginOverlay.value = true
}

function dismissOverlay() {
  if (playerId.value) {
    if (needsCharacterPick.value) return  // must pick an owned character first
    switchEditing.value = false
    switchStatus.value = ''
    switchPending.value = null
    pendingPlayerEntities.value = []
    charSwitchLoading.value = false
    charSwitchDone.value = false
    charSwitchToken++
    charPending.value = null
    charSwitchPreviousEntityId = null
    resonanceFrom.value = []
    resonanceTo.value = []
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
    if (p && p.entity_ids?.length) {
      const r2 = await fetch('/api/v1/graphql', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query: `query($ids: [ID!]!) { entities(ids: $ids) { id name type sheetPortrait currentLocation currentUniverse } }`,
          variables: { ids: p.entity_ids }
        })
      })
      const json = await r2.json()
      const results = json.data?.entities || []
      const mains = await fetchPlayerMains(pid)
      for (const e of results) {
        e.main = mains.has(e.id)
        entityCache.setEntity(e.id, e)
      }
      return results
    }
  } catch {}
  return []
}

async function fetchPlayerMains(pid) {
  // The agency `main` flag lives on the player→entity edge, not the entity doc.
  try {
    const data = await graphql(`query($id: ID!) { player(id: $id) { agency { entityId main } } }`, { id: pid })
    return new Set((data?.player?.agency || []).filter((a) => a.main).map((a) => a.entityId))
  } catch { return new Set() }
}

async function toggleMain(e) {
  if (!playerId.value || !e?.id) return
  const next = !e.main
  await fetch(`/api/v1/players/${playerId.value}/main/${e.id}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ main: next }),
  }).catch(() => {})
  // Marking the currently-controlled body as main should stamp spotlight now
  // (the control endpoint writes last_spotlight_at/last_main_entity_id).
  if (next && entityId.value === e.id) {
    await fetch(`/api/v1/players/${playerId.value}/control/${e.id}`, { method: 'POST' }).catch(() => {})
  }
  await fetchPlayerEntities()
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
  fetchPlayerEntities()
  initLocation()
  loadPlayerRole()
}

function selectCharacter(e) {
  beginCharacterSwitch(e)
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

async function assumeSupport(sc) {
  if (!playerId.value || !sc?.entity?.id) return
  const scId = sc.entity.id
  // Take control without claiming (it's a peer's SC): record_control stamps
  // nothing but broadcasts my own main as inactive. The perspective switch
  // below re-inits location via the entityId watcher.
  await fetch(`/api/v1/players/${playerId.value}/control/${scId}`, { method: 'POST' }).catch(() => {})
  entityId.value = scId
  fetchSupportCharacters(true)
  showLoginOverlay.value = false
}

// B59 — create-from-scratch support cast (SFX → roll table → pick → pay → gain).
const supportCastMenu = ref(null)  // { tableId, mainEntityId, mainName, mainRazmerit } | null

async function openCreateSupport(mainId) {
  if (!playerId.value || !mainId) return
  const tableId = await fetchSupportCastTableId(mainId)
  if (!tableId) return
  const data = await graphql(`query($id: ID!) { entity(id: $id) { razmerit } }`, { id: mainId })
  supportCastMenu.value = {
    tableId,
    mainEntityId: mainId,
    mainName: mainName(mainId),
    mainRazmerit: data?.entity?.razmerit ?? 0,
  }
}

function onSupportCreated() {
  // Refresh the character + support lists so the new SC shows up immediately;
  // the menu stays open so the player sees the "Created X" confirmation and
  // closes it via Done.
  fetchPlayerEntities()
  fetchSupportCharacters(true)
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
  beginCharacterSwitch(e)
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
        variables: { input: { name, type: 'CHARACTER', universe: 'earth' } }
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

async function fetchCharacterSignature(id) {
  if (!id) return []
  try {
    const r = await fetch('/api/v1/graphql', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        query: `query($id: ID!) { character(id: $id) { entity { id razmerit effectiveTraitSettings { id traitId traitsetId dice polarity fromType projectionId } } } }`,
        variables: { id }
      })
    })
    const json = await r.json()
    const c = json.data?.character
    if (!c) return []
    return signatureOf(c.entity?.effectiveTraitSettings || [], c.entity?.razmerit || 0, RESONANCE.egoBoost)
  } catch {
    return []
  }
}

function beginCharacterSwitch(e) {
  if (!e?.id || charSwitchLoading.value) return
  const token = ++charSwitchToken
  charPending.value = e
  charSwitchLoading.value = true
  charSwitchDone.value = false
  charSwitchPreviousEntityId = entityId.value

  const aId = entityId.value
  const bId = e.id
  resonanceFrom.value = []
  resonanceTo.value = []
  const sigAP = fetchCharacterSignature(aId).then(s => { if (token === charSwitchToken) resonanceFrom.value = s })
  const sigBP = fetchCharacterSignature(bId).then(s => { if (token === charSwitchToken) resonanceTo.value = s })

  // Commit the perspective and load everything in the background.
  locationInitPromise = null
  entityId.value = bId
  const claimP = playerId.value
    ? fetch(`/api/v1/players/${playerId.value}/claim/${bId}`, { method: 'POST' }).catch(() => {})
    : Promise.resolve()
  const controlP = playerId.value
    ? fetch(`/api/v1/players/${playerId.value}/control/${bId}`, { method: 'POST' }).catch(() => {})
    : Promise.resolve()
  const entitiesP = fetchPlayerEntities()
  const locationP = locationInitPromise || Promise.resolve()
  const minDelayP = new Promise(resolve => setTimeout(resolve, RESONANCE.durationMs))

  Promise.all([claimP, controlP, entitiesP, locationP, minDelayP, sigAP, sigBP]).then(() => {
    if (token !== charSwitchToken) return
    charSwitchDone.value = true
    // Let the final fan-out read for a beat before closing.
    setTimeout(() => {
      if (token !== charSwitchToken) return
      charSwitchLoading.value = false
      charPending.value = null
      charSwitchPreviousEntityId = null
      resonanceFrom.value = []
      resonanceTo.value = []
      showLoginOverlay.value = false
    }, RESONANCE.fanMs)
  })
}

function cancelCharacterSwitch() {
  charSwitchToken++
  if (charSwitchPreviousEntityId != null && entityId.value !== charSwitchPreviousEntityId) {
    entityId.value = charSwitchPreviousEntityId
  }
  charSwitchPreviousEntityId = null
  charSwitchLoading.value = false
  charSwitchDone.value = false
  charPending.value = null
  resonanceFrom.value = []
  resonanceTo.value = []
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

.support-chip.support-unavailable { opacity: 0.45; cursor: not-allowed; }
.support-chip.support-current { border-color: var(--accent); }
.support-main { font-size: 10px; }
.support-available-dot { margin-left: auto; color: var(--success); font-size: 10px; }
.support-hint { font-size: 11px; color: var(--text-dim); margin: 6px 0 0; }
.support-create-btn { width: 100%; font-size: 12px; padding: 8px; background: var(--accent-dim); color: var(--text); border: none; border-radius: 6px; cursor: pointer; }
.support-create-btn:hover { background: var(--accent); }
.support-create-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.other-mains-list { display: flex; flex-wrap: wrap; justify-content: center; gap: 6px; }
.other-main-row { flex: 0 1 200px; display: flex; align-items: center; gap: 8px; padding: 6px 8px; border-radius: 8px; background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.08); }
.support-create-inline { width: auto; flex: 0 0 auto; font-size: 11px; padding: 5px 10px; }
.main-badge { font-size: 9px; text-transform: uppercase; letter-spacing: 0.5px; padding: 1px 5px; border-radius: 3px; color: #0a0a0f; background: var(--accent); font-weight: 600; margin-left: 4px; }
.main-toggle { flex-shrink: 0; cursor: pointer; font-size: 14px; color: var(--text-dim); opacity: 0.45; transition: color 0.15s, opacity 0.15s; line-height: 1; }
.main-toggle.on { color: var(--accent); opacity: 1; }
.main-toggle:hover { opacity: 1; }
</style>
