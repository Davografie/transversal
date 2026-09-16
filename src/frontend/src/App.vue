<template>
  <SseIndicator :connected="connected" :pulse="ssePulse" :error="error" />
  <button v-if="gmMode && playerId && !showLoginOverlay" class="settings-btn" @click="openSettings" title="Player settings">↩</button>
  <!-- Login / Settings overlay -->
  <div v-if="showLoginOverlay" class="name-entry panel" @click.self="dismissOverlay">
    <div class="name-entry-scroll">
    <!-- Fresh login: no identity yet -->
    <LoginPrompt
      v-if="!playerId"
      v-model:player-name="playerName"
      :checking="checking"
      :suggestions="nameSuggestions"
      :show-create="showLoginCreate"
      :status="nameStatus"
      :found="nameFound"
      @enter="onNameEnter"
      @select="selectSuggestion"
      @confirm="confirmPlayer"
    />
    <!-- Settings: already logged in -->
    <template v-else>
      <p class="name-hint settings-hint">Player settings</p>

      <IdentitySwitchBlock
        ref="switchBlockRef"
        v-model:switch-name="switchName"
        :player-name="playerName"
        :editing="switchEditing"
        :switching="switching"
        :suggestions="switchSuggestions"
        :show-create="showSwitchCreate"
        :status="switchStatus"
        :found="switchFound"
        :pending-entities="pendingPlayerEntities"
        @start-edit="startSwitchEdit"
        @enter="onSwitchEnter"
        @blur="onSwitchBlur"
        @select="selectSwitchSuggestion"
        @confirm="confirmSwitch"
      />

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
        <AppearanceBlock :mode="colorMode" @update:mode="colorMode = $event" />

        <ModeAndMediaBlock
          v-model:gm-mode="gmMode"
          :media-quality="mediaQuality"
          @set-media-quality="setMediaQuality"
        />

        <p v-if="needsCharacterPick" class="switch-error">Pick one of your characters to play.</p>

        <CharacterListBlock
          :entities="playerEntities"
          :loading="loadingPlayerEntities"
          :active-id="entityId"
          :revealed-release-id="revealedReleaseId"
          :location-label="locationLabel"
          v-model:show-new-char="showNewChar"
          v-model:new-char-name="newCharName"
          :creating="creatingChar"
          :error="createCharError"
          @select="onCharChipClick"
          @reveal="revealRelease"
          @release="releaseCharacter"
          @toggle-main="toggleMain"
          @touch-start="onReleaseTouchStart"
          @touch-cancel="onReleaseTouchCancel"
          @touch-end="onReleaseTouchEnd"
          @create="createCharacter"
        />
        <SupportBlock
          :support-characters="mySupportCharacters"
          :other-mains="otherPlayersMains"
          :active-id="entityId"
          :gm-mode="gmMode"
          @assume="assumeSupport"
          @create-support="openCreateSupport"
        />

        <FindCharacterBlock
          v-model:search="charSearch"
          :results="charSearchResults"
          :searching="charSearching"
          :searched="charSearchSearched"
          :error="charSearchError"
          :location-label="locationLabel"
          @enter="onCharSearchEnter"
          @choose="chooseFoundCharacter"
        />
      <div v-if="gmMode" class="settings-section settings-lab">
          <button class="settings-lab-toggle" @click="showLab = !showLab">
            <span>🧪 Resonance Lab</span>
            <span class="settings-lab-caret">{{ showLab ? '▾' : '▸' }}</span>
          </button>
          <ResonanceLab v-if="showLab" embedded />
        </div>
      </template>

      <p v-if="switchError" class="switch-error">{{ switchError }}</p>
      <button v-if="!charSwitchLoading" class="cancel-btn" @click="dismissOverlay">Back to game</button>
    </template>
    </div>
  </div>
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
  <div class="stage" :style="{ '--roller-h': rollerContentH + 'px' }" :class="[mobileStackActive ? 'mobile-stack' : '', mobileStackActive ? 'focus-' + mobileFocus : '', mobileStackActive && sheetEmpty ? 'sheet-empty' : '']">
    <ArmedSfxRail
      v-if="playerId && !showLoginOverlay && !fullCanvas"
      :entity-id="entityId"
      :phase="phase"
      :refresh-key="armedSfxRefresh"
    />
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
        :viewing-entity-id="viewingEntityId"
        :controlled-entity-ids="controlledEntityIds"
        v-model:edit-zones="editZones"
        :overlay="locationOverlay"
        :gm-mode="gmMode"
        :remote-pools="remotePools"
        :remote-results="remoteResults"
        @moved="onMoved"
        @inspect-entity="onInspectEntity"
        @dragging="occupantDragging = $event"
      />
      <div v-if="mobileStackActive && mobileFocus !== 'location'" class="band-tap" @touchstart="onBandDragStart($event, 'location')" @click="tapBand('location')"></div>
    </div>
    <div ref="wrapperEl" class="dice-panel-wrapper" :class="{ open: wrapperOpen, dragging: occupantDragging && !isMobile }" @mouseenter="onWrapperEnter" @mouseleave="onWrapperLeave">
      <PeersBar
        v-if="(wrapperOpen || mobileStackActive) && peers.length"
        :peers="peers"
        :assumed-id="entityId"
        :viewed-id="viewingEntityId"
        @select="onPeerClick"
      />
      <div class="sheet-band">
        <CharacterSheet
          v-show="(mobileStackActive || (sheetVisible && (phase === 'adding' || forceSheet))) && (!gmMode || entityId || viewingEntityId)"
          ref="sheetRef"
          class="embedded-sheet"
          :class="{ 'sheet-hidden': !sheetVisible && !mobileStackActive }"
          :entity-id="entityId"
          :override-entity-id="viewingEntityId"
          :viewer-entity-id="entityId"
          :player-owned-entity-ids="ownedEntityIds"
          :player-id="playerId"
          :main-entity-id="ownMainId"
          :universe="universe"
          :phase="phase"
          :visible="sheetVisible || mobileStackActive"
          embedded
          :gm-mode="gmMode"
          @open-settings="openSettings"
          @add-to-pool="(d) => diceRef?.addFromSheet(d)"
          @remove-from-pool="(s) => diceRef?.removeBySource(s)"
          @remove-by-ts-id="(id) => diceRef?.removeByTsId(id)"
          @retract-negative="(p) => diceRef?.retractNegative(p)"
          @split-die="(d) => diceRef?.splitDie(d)"
          @sfx-toggled="onSfxToggled"
          @stamp-sfx="(d) => diceRef?.stampArmedSfx(d.tsId, d.sfxId)"
          @sheet-view-change="onSheetViewChange"
        />
        <div v-if="mobileStackActive && !sheetEmpty && mobileFocus !== 'sheet'" class="band-tap" @touchstart="onBandDragStart($event, 'sheet')" @click="tapBand('sheet')"></div>
      </div>
      <div class="roller-band">
        <DiceRoller ref="diceRef" :entity-id="entityId" :universe="universe" :mode="rollerMode" :keep-count="keepCount" :effect-count="effectCount" :gm-mode="gmMode" :difficulty="currentDifficulty" :player-id="playerId" :location-id="currentLocationId" :location-name="locationName" :pool-locations="poolLocations" :contests="contests" :peers="peers" :entity-names="entityNames" :remote-pools="remotePools" :remote-results="remoteResults" :sfx-choice-request="sfxChoiceRequest" @update:universe="u => universe = u" @rolled="onDiceRolled" @picked="(r) => { mirrorOwnResult({ result: r }); shareRoll(r) }" @difficulty="onDifficultyCommitted" @pool-change="onPoolChange" @pool-saved="onPoolSaved" @phase-change="onPhaseChange" @panel-open="onPanelOpen" @panel-drag-start="onPanelDragStart" @panel-drag="onPanelDrag" @panel-drag-end="onPanelDragEnd" @sfx-choice-resolved="onSfxChoiceResolved" @acting-entity-change="onActingEntityChange" @offered-change="(ids) => sheetRef?.setOfferedTraits(ids)" />
        <div v-if="mobileStackActive && mobileFocus !== 'dice'" class="band-tap" @touchstart="onBandDragStart($event, 'dice')" @click="tapBand('dice')"></div>
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
import { ref, reactive, useTemplateRef, watch, computed, nextTick, onMounted, onUnmounted, provide } from 'vue'
import LocationViewer from './components/LocationViewer.vue'
import CharacterSheet from './components/CharacterSheet.vue'
import DiceRoller from './components/DiceRoller.vue'
import ArmedSfxRail from './components/ArmedSfxRail.vue'
import GmPanel from './components/GmPanel.vue'
import PanelStack from './components/gm/PanelStack.vue'
import RelationalCanvas from './components/canvas/RelationalCanvas.vue'
import { usePeers } from '@/composables/usePeers.js'
import { usePlayerCharacters } from '@/composables/usePlayerCharacters.js'
import { usePlayerIdentity } from '@/composables/usePlayerIdentity.js'
import { useCharacterFinder } from '@/composables/useCharacterFinder.js'
import { useCharacterSwitch } from '@/composables/useCharacterSwitch.js'
import { useMobileBands } from '@/composables/useMobileBands.js'
import { useThemeMode } from '@/composables/useThemeMode.js'
import SseIndicator from '@/components/app/SseIndicator.vue'
import LoginPrompt from '@/components/app/LoginPrompt.vue'
import IdentitySwitchBlock from '@/components/app/IdentitySwitchBlock.vue'
import FindCharacterBlock from '@/components/app/FindCharacterBlock.vue'
import ModeAndMediaBlock from '@/components/app/ModeAndMediaBlock.vue'
import AppearanceBlock from '@/components/app/AppearanceBlock.vue'
import CharacterListBlock from '@/components/app/CharacterListBlock.vue'
import SupportBlock from '@/components/app/SupportBlock.vue'
import PeersBar from '@/components/app/PeersBar.vue'
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

const { graphql, getDifficulty: apiGetDifficulty, setDifficulty: apiSetDifficulty, nextBeat: apiNextBeat, advanceScene: apiAdvanceScene, listAllPools: apiListAllPools, getActivity: apiGetActivity } = useApi()
const { fetchEntities: prefetchEntities } = useEntityCrud()
const { quality: mediaQuality, setQuality: setMediaQuality, resolveMediaUrl, isLowQuality } = useMediaQuality()
const entityCache = useEntityCache()
const bus = usePanelBus()
const { supportCharacters, activeMains, playerBodies, onlinePlayers, fetchSupportCharacters, fetchActiveMains, fetchSupportCastTableId, fetchRecency, fetchPlayerBodies, fetchOnlinePlayers } = useTroupe()

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
  // The GM panel pins its own chrome (tools, filter, tabs) and scrolls only
  // the browsing zone — see Panel's `bodyScroll`.
  bodyScroll: false,
  props: {
    universe: universe.value,
    currentLocationId: currentLocationId.value,
    currentLocationName: locationName.value,
    entityId: entityId.value,
    inSession: inSession.value,
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

// The GM's current location, live for the panels. It must be provided here:
// PanelStack is mounted by App, so a provider inside GmPanel reaches only its
// own slot content — not the panels the stack renders (the entity panel's
// Import to Location reads this).
provide('gmCurrentLocationId', computed(() => currentLocationId.value))
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
  // A free-roaming GM has no entity to resolve a location from — and a null id
  // fails this query's non-null `$id`. currentLocationId is persisted on the
  // device though, so still resolve the label + background + peers for it;
  // otherwise a refresh in free-roam shows no background image (and "no entity"
  // as the location name).
  if (!entityId.value) {
    DIAG.mark('initLocation-no-entity', { reason: 'no entityId (GM free-roam)' })
    locationName.value = currentLocationId.value
    try {
      const r2 = await fetch(`/api/v1/locations/${currentLocationId.value}/navigate`)
      const nav = await r2.json()
      locationName.value = nav.location?.name || currentLocationId.value
    } catch (e) {
      DIAG.mark('initLocation-free-roam-nav-err', { error: e.message })
    }
    fetchLocationBg()
    fetchPeers(true)
    DIAG.mark('initLocation-done', { locationName: locationName.value, freeRoam: true })
    return
  }
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

function onMoved(data) {
  locationName.value = data.location
  if (data.universe) universe.value = data.universe
  currentLocationId.value = data.location_id || data.location
  fetchLocationBg()
  fetchPeers(true)
  // The scene roster reads the entity list's currentLocation.
  prefetchEntities()
}

// One persisted perspective: `entityId` = who you are (player: main/assumed SC;
// GM: acting entity, null = free-roam). "Self" is derived — the player's own
// main from troupe data, free-roam for the GM. See [[Perspective Model]].
const entityId = ref(localStorage.getItem('entityId') || null)  // perspective entity; null = GM free-roam
const editZones = ref(false)

// The player's own main entity (perspective-neutral). GM has no main: they
// return to free-roam instead.
const ownMainId = computed(() => {
  if (gmMode.value) return entityId.value || ''
  const mine = activeMains.value.find((m) => m.playerId === playerId.value)
  return mine?.main?.id || ''
})

let locationInitPromise = null

// entityId persists in every mode (refresh restores the GM's perspective too);
// only the player flow re-inits location/bonuses on switch — the GM switch
// path (switchPerspective) handles its own location load.
watch(entityId, () => {
  if (entityId.value) localStorage.setItem('entityId', entityId.value)
  else localStorage.removeItem('entityId')
  if (gmMode.value || !entityId.value) return
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
const armedSfxRefresh = ref(0)  // bump to re-query armed SFX (trigger/roll lifecycle)
const rollerMode = ref('cortex') // 'cortex' | 'roll_table' (driven by CharacterSheet tab)
const currentDifficulty = ref(null) // GM-set test difficulty (ephemeral, session-scoped)
const sfxChoiceRequest = ref(null) // pending {choose_*} auto-fired SFX choices for this player

// Player identity
const showLab = ref(false)

// Settings panel
const gmMode = ref(localStorage.getItem('architectMode') === 'true')

// Player identity + login/switch logic (see composables/usePlayerIdentity.js).
// The three refs are created here because other composables share them.
const playerId = ref(localStorage.getItem('playerId') || '')
const switchBlockRef = useTemplateRef('switchBlockRef')   // settings name field focus
const playerName = ref(localStorage.getItem('playerName') || '')
const showLoginOverlay = ref(!playerId.value)

// Owned characters + their actions (see composables/usePlayerCharacters.js).
const {
  playerEntities, pendingPlayerEntities, loadingPlayerEntities,
  revealedReleaseId,
  fetchPlayerEntities, fetchEntitiesFor, fetchPlayerMains,
  fetchLocationNames, locationLabel, toggleMain, releaseCharacter, revealRelease,
  onReleaseTouchStart, onReleaseTouchCancel, onReleaseTouchEnd,
  isReleaseSuppressed, clearReleaseReveal,
} = usePlayerCharacters({ playerId, entityId, graphql })

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

const {
  checking, nameStatus, nameFound, pendingPlayer,
  nameSuggestions, showLoginCreate, loginHasExactMatch,
  switchName, switchEditing, switching, switchError, switchPending, switchStatus, switchFound,
  switchSuggestions, showSwitchCreate,
  searchPlayers, onNameEnter, selectSuggestion,
  searchSwitchPlayers, selectSwitchSuggestion,
  findOrCreatePlayer, fetchPlayer, ensurePlayer, confirmPlayer,
  startSwitchEdit, onSwitchBlur, onSwitchEnter, confirmSwitch, resetSwitch,
} = usePlayerIdentity({
  playerId, playerName, showLoginOverlay,
  entityId, needsCharacterPick,
  loadPlayerRole, initLocation,
  fetchPlayerEntities, fetchSupportCharacters, fetchActiveMains, fetchEntitiesFor,
  pendingPlayerEntities,
  focusSwitchInput: () => nextTick(() => switchBlockRef.value?.focusName()),
  diag: (label, detail) => DIAG.mark(label, detail),
})

// Switching which character you play (see composables/useCharacterSwitch.js).
const {
  charPending, charSwitchLoading, charSwitchDone, resonanceFrom, resonanceTo,
  beginCharacterSwitch, cancelCharacterSwitch, resetSwitchAnimation,
} = useCharacterSwitch({
  entityId, playerId, showLoginOverlay, fetchPlayerEntities,
  locationInit: {
    reset: () => { locationInitPromise = null },
    current: () => locationInitPromise,
  },
})

// Find/create a character in the settings overlay (see useCharacterFinder.js).
const {
  charSearch, charSearchResults, charSearching, charSearchSearched, charSearchError,
  newCharName, creatingChar, createCharError, showNewChar,
  onCharSearchEnter, chooseFoundCharacter, createCharacter, resetFinder,
} = useCharacterFinder({
  playerId, playerEntities, fetchPlayerEntities, fetchLocationNames,
  onChoose: (e) => beginCharacterSwitch(e),
})

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


// Find character

// Name search


ensurePlayer()

// Session management
const { sessions, currentSession, listSessions, createSession, joinSession, publishEvent, startSession, endSession } = useSessions()
const sessionId = ref('session-default')
// Session truth for the GM panel's [Session] button: the session dict
// (`in_session`) at join, plus the session_started/session_ended SSE
// broadcasts — so a refresh or another device converges on the same state.
const inSession = ref(false)

async function initSession() {
  DIAG.mark('initSession-start')
  await listSessions()
  DIAG.mark('initSession-listed', { count: sessions.value.length, ids: sessions.value.map(s => s.id) })
  if (sessions.value.length > 0) {
    const s = sessions.value[0]
    sessionId.value = s.id
    const joined = await joinSession(s.id, entityId.value || playerId.value, playerId.value)
    inSession.value = !!joined?.in_session
    DIAG.mark('initSession-joined', { sessionId: sessionId.value, inSession: inSession.value })
  } else {
    const s = await createSession('Default Session', 'earth')
    if (s) {
      sessionId.value = s.id
      const joined = await joinSession(s.id, entityId.value || playerId.value, playerId.value)
      inSession.value = !!joined?.in_session
      DIAG.mark('initSession-created', { sessionId: sessionId.value, inSession: inSession.value })
    } else {
      DIAG.mark('initSession-FAILED', { error: 'createSession returned null' })
    }
  }
}
DIAG.mark('initSession-called')
const initSessionPromise = initSession()
DIAG.mark('initLocation-called')
const entityNames = ref({})  // id → name for every entity (all locations, for tab labels)
const { peers, fetchPeers, isEntityType } = usePeers({
  graphql, currentLocationId, entityId, gmMode, entityNames,
  diag: (label, detail) => DIAG.mark(label, detail),   // DIAG.mark uses `this`
})
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
  // Mirror locally too: the ring around your own dot reads the same phase (and
  // pool) the roller has. Solo play has no SSE at all, and in a session the
  // `pool_updated` echo deliberately skips the acting entity — so without this
  // the dot you are rolling from would never animate.
  if (entityId.value) {
    const prev = remotePools.value[entityId.value] || {}
    remotePools.value = {
      ...remotePools.value,
      [entityId.value]: { ...prev, player_id: playerId.value, phase: phase.value },
    }
  }
  if (sessionId.value === 'session-default') return
  lastSent.value = `phase:${phase.value}`
  publishEvent(sessionId.value, 'pool_updated', { player_id: playerId.value, entity_id: entityId.value, phase: phase.value })
}

// The same shape the SSE handler builds for remote entities, applied to our own
// roll — so our own dot's ring shows the results too (see `sharePhase` for why).
function mirrorOwnResult(result) {
  if (!entityId.value || !result) return
  const res = result.result || result
  const existing = remoteResults.value[entityId.value] || {}
  remoteResults.value = {
    ...remoteResults.value,
    [entityId.value]: {
      ...existing,
      total: res.total || res.highest || existing.total,
      effect_die: res.effect_die || existing.effect_die,
      tier: res.tier || existing.tier,
      botch: res.botch ?? existing.botch,
      pipeline: res.pipeline || existing.pipeline,
      hitches: res.hitches || existing.hitches || [],
      rolls: (res.rolls && res.rolls.length) ? res.rolls : (existing.rolls || []),
    },
  }
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
  // Tabs are global — seed every active pool across all locations, plus the
  // activity grouping metadata (per-pool location + active contests).
  const act = await apiGetActivity()
  if (act) {
    for (const [locId, entityPools] of Object.entries(act.pools || {})) {
      for (const [eid, dice] of Object.entries(entityPools)) {
        poolLocations.value = { ...poolLocations.value, [eid]: locId }
        if (eid !== entityId.value && dice && dice.length) {
          remotePools.value = { ...remotePools.value, [eid]: { dice, player_id: eid, phase: 'adding' } }
        }
      }
    }
    contests.value = act.contests || []
    return
  }
  // Fallback (older backend without /activity): flat list, no location.
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

function onPoolSaved({ key, locationId, dice }) {
  // The DiceRoller saved its own pool (GM editing an entity's pool directly).
  // Record it so the entity keeps a tab after the GM switches away — self-edits
  // don't reach remotePools via the SSE echo, and solo play has no SSE at all.
  if (!key) return
  remotePools.value = { ...remotePools.value, [key]: { dice: dice || [], player_id: key, phase: 'adding' } }
  poolLocations.value = { ...poolLocations.value, [key]: locationId || currentLocationId.value }
  // NOTE: this handler deliberately does NOT refresh the sheet (B120). A pool
  // save is a hot path — the roller saves on every pool edit, and the wizard's
  // prepare clears then adds, so each save is two writes. Refreshing the sheet
  // here re-rendered the component tree, remounted LifePathWizard, which
  // re-prepared the roller, which saved again: an endless loop. In-flight SFX
  // state is kept truthful by the `sfx_ended` SSE push (and `applyEntity` still
  // refreshes it on real entity changes), so no per-save round trip is needed.
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
  viewingEntityId.value = null  // clear any read-only location inspect
  // Presence only: other clients size up the dot of whatever this client is
  // driving. stamp=false keeps a GM's possession out of spotlight recency.
  if (playerId.value) {
    fetch(`/api/v1/players/${playerId.value}/control/${id}?stamp=false`, { method: 'POST' }).catch(() => {})
  }
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
  await setViewLocation(locId)
}

function returnToSelf() {
  entityId.value = gmMode.value ? null : ownMainId.value
  viewingEntityId.value = null  // clear any read-only location inspect
  // A GM going to free-roam drives nothing: drop the recorded body, or the last
  // possessed dot stays sized up. (Players are still driving their main.)
  if (gmMode.value && playerId.value) {
    fetch(`/api/v1/players/${playerId.value}/control`, { method: 'DELETE' }).catch(() => {})
  }
}

function onInspectEntity(id) {
  if (gmMode.value) {
    // A map-dot click never opens the panel (only the rail does that), but it
    // still selects: `forceSheet` + `viewingEntityId` mean the sheet shows the
    // clicked character as a foreign sheet whenever the panel is open.
    onPeerClick(id, { fromMap: true })
    return
  }
  // Map-dot semantics (deliberately NOT the peer-chip toggle):
  //   self dot    → own sheet
  //   foreign dot → open if closed/different; close if already open & showing it
  const isSelf = id === entityId.value || id === ownMainId.value
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

// Peer-chip styling states, deliberately distinct:
//   assumed — you ARE this entity (entityId) → solid fill
//   viewing — you are peeking at it (viewingEntityId) → outlined

async function onPeerClick(id, { fromMap = false } = {}) {
  // `fromMap` = the click came from a map dot. It changes exactly one thing:
  // the mobile stack is not yanked to the sheet. Everything else matches a rail
  // click, including `forceSheet` — so a map click *selects the sheet content*
  // (the viewed entity) without opening anything: only `sheetVisible` opens the
  // panel, and a map click never sets it.
  if (gmMode.value) {
    const isLocation = peers.value.find(p => p.id === id)?.type === 'LOCATION'
    if (isLocation) {
      // Locations are never assumed — view their read-only sheet (toggle).
      viewingEntityId.value = viewingEntityId.value === id ? null : id
      forceSheet.value = true
      if (!fromMap && mobileStackActive.value && viewingEntityId.value) setMobileFocus('sheet')
      return
    }
    // Clicking the entity you already act as: if you were viewing another
    // character, this resets the view back to this one (stop peeking, keep
    // acting). Only a click with nothing being viewed exits to free-roam.
    if (entityId.value === id) {
      if (viewingEntityId.value) {
        viewingEntityId.value = null
        forceSheet.value = true
        if (!fromMap && mobileStackActive.value) setMobileFocus('sheet')
        return
      }
      returnToSelf(); forceSheet.value = true; return
    }
    // Second click on the peer you are viewing → assume it.
    if (viewingEntityId.value === id) {
      await switchPerspective(id)   // clears viewingEntityId
      forceSheet.value = true
      if (!fromMap && mobileStackActive.value && entityId.value === id) setMobileFocus('sheet')
      return
    }
    // First click → view only (inspect), don't assume.
    viewingEntityId.value = id
    forceSheet.value = true
    if (!fromMap && mobileStackActive.value) setMobileFocus('sheet')
    return
  }
  // Clicking our own character returns to self-view (no override), keeping the header tabs visible.
  viewingEntityId.value = (id === entityId.value || id === ownMainId.value)
    ? null
    : (viewingEntityId.value === id ? null : id)
  if (mobileStackActive.value && viewingEntityId.value) setMobileFocus('sheet')
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
  mirrorOwnResult(result)
  shareRoll(result)
  // The roll endpoint ticks every ``rolls`` timer for this entity before it
  // answers, and publishes nothing when it does — so both countdown surfaces
  // (the sheet's ⏳ line and the Active rail) are stale the moment dice land.
  sheetRef.value?.fetchTimers?.()
  armedSfxRefresh.value++
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
  // Idempotent (B120): the wizard re-emits `prepare` whenever it remounts, and
  // clearing + re-adding wrote the pool twice each time — those writes fed the
  // sheet refresh that caused the remount. If the pool already holds exactly
  // these dice, there is nothing to do.
  if (roller.poolMatchesRollTableDice?.(dice)) return
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
// The SSE stream is session-wide server-side (entity_id is a legacy log-only
// param); a free-roaming GM keeps the connection alive on their playerId.
const { connected, lastEvent, error, drainSseEvents } = useSSE(sessionId, computed(() => entityId.value || playerId.value), playerId)

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
  return isEntityType(id, 'GMC')
}

const remotePools = ref({})  // entity_id → { dice: [...], player_id, phase }
const remoteResults = ref({})  // entity_id → { result, rolls, kept, total, effect_die }
const poolLocations = ref({})  // entity_id → location_id (for the grouped activity view)
const contests = ref([])       // [{ location_id, challenger_id, defendant_id, parties }]

const ssePulse = ref(false)
watch(lastEvent, (evt) => {
  if (!evt) return
  // A burst of events can arrive in one network chunk, and the browser dispatches
  // them all in the same task — so a single-slot `lastEvent` only ever surfaces
  // the *last* one to this watcher. Drain the queue and handle every event, in
  // order: a take-back publishes `razmerit_changed` and then `sfx_ended`, and the
  // balance update was the one being thrown away.
  for (const queued of drainSseEvents()) handleSseEvent(queued)
})

function handleSseEvent(evt) {
  ssePulse.value = true
  setTimeout(() => { ssePulse.value = false }, 300)

  const pid = evt.data?.player_id
  const eid = evt.data?.entity_id
  const foreign = pid !== playerId.value  // event from another player
  const name = entName(eid)

  switch (evt.type) {
    case 'razmerit_changed': {
      const targetId = evt.data?.entity_id
      const applied = sheetRef.value?.setRazmerit?.(evt.data?.new_balance, targetId)
      console.log('[SSE] razmerit_changed', targetId, '\u2192', evt.data?.new_balance,
                  '| sheet applied:', applied)
      entityCache.invalidateSheet(targetId)
      break
    }
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
      poolLocations.value = {}
      contests.value = []
      currentDifficulty.value = null
      if (gmMode.value) addToast('Beat ended', 'dice')
      break
    case 'session_started':
      inSession.value = evt.data?.in_session !== false
      addToast('Session started', 'session')
      break
    case 'session_ended':
      inSession.value = false
      addToast('Session ended', 'session')
      armedSfxRefresh.value++  // session end drops the globally-armed passives
      break
    case 'main_active':
      // A main became active/inactive — refresh support-character availability,
      // active mains, current bodies, and the GM troupe overview recency.
      fetchSupportCharacters(true)
      fetchActiveMains(true)
      fetchRecency(true)
      fetchPlayerBodies(true)
      break
    case 'body_changed':
      // A client changed the body it is driving (a player switch, or the GM
      // taking a GMC) — the map sizes those dots, so refresh the body list.
      fetchPlayerBodies(true)
      break
    case 'presence_changed':
      fetchOnlinePlayers(true)
      break
    case 'trait_updated':
      entityCache.invalidateSheet(evt.data?.entity_id)
      if (evt.data?.entity_id === entityId.value) {
        perfMark('sse-trait-updated', { trait: evt.data?.trait_id, ts: evt.data?.trait_setting_id })
        if (evt.data?.trait_setting_id) {
          diceRef.value?.resyncTraitDie(evt.data.trait_setting_id, evt.data.new_dice ?? [evt.data.new_rating])
        }
        sheetRef.value?.fetchEntity('sse-trait-updated')
      }
      if (gmMode.value && foreign) {
        const tName = evt.data?.trait_name || evt.data?.name || 'a trait'
        addToast(`${name} updated ${tName}`, 'trait')
      }
      break
    case 'location_changed':
      // Whoever moved, the entity list's currentLocation is now stale — the GM
      // panel's scene roster reads it, exactly as the LocationViewer refreshes
      // itself below. Refresh it for our own travel and for everyone else's.
      prefetchEntities()
      if (eid === entityId.value && evt.data?.to) {
        currentLocationId.value = evt.data.to
        if (evt.data?.universe) universe.value = evt.data.universe
        fetchLocationBg()
        fetchPeers(true)
        fetch(`/api/v1/locations/${evt.data.to}/navigate`)
          .then(r => r.json())
          .then(nav => { locationName.value = nav.location?.name || evt.data.to })
          .catch(() => { locationName.value = evt.data.to })
        sheetRef.value?.refreshBlueBook()
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
        // Hand over the position so the viewer can tell its own write from a
        // foreign one: the server echoes this event back to the mover too, and
        // their own drag must land instantly rather than smooth into place.
        locationRef.value?.fetchNavWithLerp({ id: eid, x: evt.data?.map_x, y: evt.data?.map_y })
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
      poolLocations.value = {}
      contests.value = []
      diceRef.value?.loadTargetingBans()
      break
    case 'pool_updated':
      lastEvtDebug.value = `pid=${pid} eid=${eid} phase=${evt.data.phase} dice=${JSON.stringify(evt.data.dice)} mypid=${playerId.value}`
      const actor = evt.data.actor_id ?? evt.data.player_id ?? eid
      if (eid === entityId.value && actor !== entityId.value && Array.isArray(evt.data.dice)) {
        // Another entity changed my pool (e.g. offered a negative trait) — sync it.
        diceRef.value?.syncPool(evt.data.dice)
      } else if (eid === entityId.value && Array.isArray(evt.data.dice)) {
        // The server's own broadcast for *my* pool. Its roll endpoints send the
        // enriched dice the moment the roll resolves — before the roller has run
        // its settle animation — so recording them here is what lets my own dot's
        // ring settle in step with the panel instead of a full cycle behind it.
        // (Phase-only publishes from `sharePhase` carry no dice and are ignored.)
        remotePools.value = { ...remotePools.value, [eid]: {
          dice: evt.data.dice,
          player_id: pid,
          phase: evt.data.phase || 'adding',
        }}
        if (evt.data.location_id) {
          poolLocations.value = { ...poolLocations.value, [eid]: evt.data.location_id }
        }
      } else if (eid && eid !== entityId.value) {
        const phase = evt.data.phase || 'adding'
        const hasDice = Array.isArray(evt.data.dice)
        remotePools.value = { ...remotePools.value, [eid]: {
          dice: hasDice ? evt.data.dice : (remotePools.value[eid]?.dice || []),
          player_id: pid, phase,
        }}
        if (evt.data.location_id) {
          poolLocations.value = { ...poolLocations.value, [eid]: evt.data.location_id }
        }
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
      if (evt.data?.challenger_id && evt.data?.opponent_id) {
        const c = {
          location_id: evt.data?.location_id || currentLocationId.value,
          challenger_id: evt.data.challenger_id,
          defendant_id: evt.data.opponent_id,
          parties: [evt.data.challenger_id, evt.data.opponent_id],
        }
        contests.value = [
          ...contests.value.filter(x => !(x.challenger_id === c.challenger_id && x.defendant_id === c.defendant_id)),
          c,
        ]
      }
      if (gmMode.value) {
        addToast(`${entName(evt.data?.challenger_id)} challenged ${entName(evt.data?.opponent_id)}`, 'dice')
        // Auto-switch to a challenged GMC so the GM can roll its side at once.
        const oppId = evt.data?.opponent_id
        if (oppId && isGmcEntity(oppId) && entityId.value !== oppId) {
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
      if (evt.data?.challenger_id && evt.data?.defendant_id) {
        contests.value = contests.value.filter(c =>
          !(c.challenger_id === evt.data.challenger_id && c.defendant_id === evt.data.defendant_id))
      }
      addToast('Contest resolved', 'roll')
      break
    case 'traits_revealed':
      if ((evt.data?.learner_ids || []).includes(entityId.value)) {
        // The heavy one: fog-of-war reveal pulls the whole entity back down.
        // Stamped so the console shows event -> fetch -> list rebuild as one
        // sequence (see the fetch attribution in CharacterSheet.vue).
        perfMark('sse-traits-revealed', {
          owner: evt.data?.owner_id,
          changed: (evt.data?.trait_setting_ids || []).length,
          learners: (evt.data?.learner_ids || []).length,
        })
        sheetRef.value?.fetchEntity('sse-traits-revealed')
      }
      break
    case 'sfx_triggered':
      // Show for the viewer's own entity, or for any entity in GM mode.
      if (evt.data?.entity_id === entityId.value || gmMode.value) {
        const sfxLabel = evt.data?.sfx_name || evt.data?.sfx_id
        const who = evt.data?.entity_id === entityId.value ? '' : ` (${name})`
        addToast(`SFX: ${sfxLabel}${who}`, 'sfx')
      }
      armedSfxRefresh.value++  // an SFX just (de)activated → refresh the armed rail
      sheetRef.value?.fetchTimers?.()  // a durationed effect may have started a timer
      break
    case 'sfx_ended':
      // The rule was taken back — or its cost left the pool before it committed,
      // and the rule went with it. Either way the chip must stop reading active.
      if (evt.data?.entity_id === entityId.value || gmMode.value) {
        const endedLabel = evt.data?.sfx_name || evt.data?.sfx_id || ''
        addToast(`SFX ended: ${endedLabel}`, 'sfx')
      }
      sheetRef.value?.fetchInFlightSfxIds?.('sse-sfx-ended')
      sheetRef.value?.fetchTimers?.()  // an ended activation drops its timer early
      armedSfxRefresh.value++
      break
    case 'sfx_armed':
      // A passive armed at session start never "fires" at that moment, so this is
      // the only notice the table gets (One Trick). Global scope covers every
      // entity, so — unlike `sfx_triggered` — it is not gated on the viewer's.
      addToast(`SFX armed: ${evt.data?.sfx_name || evt.data?.sfx_id}`, 'sfx')
      armedSfxRefresh.value++  // it belongs in the Active rail now
      break
    case 'sfx_choice_required':
      if (evt.data?.entity_id === entityId.value || gmMode.value) {
        sfxChoiceRequest.value = (evt.data.choices || []).map((c, i) => ({
          ...c, index: i, entity_id: evt.data.entity_id,
        }))
      }
      break
  }
}

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
    armedSfxRefresh.value++  // roll/contest resolved → re-query armed SFX
  }
  sharePhase()
}
const diceRef = useTemplateRef('diceRef')
const sheetRef = useTemplateRef('sheetRef')
const locationRef = useTemplateRef('locationRef')

const hoverOpen = ref(false)
const sheetVisible = ref(false)
const occupantDragging = ref(false)  // LocationViewer is mid-occupant-drag
let sheetTimer = null
let closeTimer = null

const currentPoolSources = ref([])
const viewingEntityId = ref(null)

// Entities some client is actively driving right now — every player's current
// body (server truth via `playerBodies`, refreshed on the `main_active` SSE
// event) plus our own perspective, which is local and immediate. The map sizes
// these dots up; see LocationViewer's `controlledEntityIds` prop.
const controlledEntityIds = computed(() => {
  const ids = new Set()
  for (const body of playerBodies.value) {
    // Our *own* entry is a server echo: it arrives late (over SSE) and, when no
    // session is streaming, may never arrive at all — leaving the body we just
    // left stuck in the sized-up state. Our own body is `entityId`, which is
    // local and immediate, so it is added below and never read back.
    if (body?.playerId === playerId.value) continue
    if (body?.entity?.id) ids.add(body.entity.id)
  }
  if (entityId.value) ids.add(entityId.value)
  return [...ids]
})
// When the GM switches which entity they're acting as, re-seed the pool tabs
// from the server so entities acted as earlier (with dice still saved) keep a
// tab — the GM's own pool edits don't reach remotePools via the SSE echo.
watch(entityId, seedRemotePools)
const forceSheet = ref(false)

const wrapperEl = useTemplateRef('wrapperEl')
const wrapperOpen = computed(() => hoverOpen.value || sheetVisible.value)
let panelResizeObserver = null
const documentDragging = ref(false)

function openPanel() {
  hoverOpen.value = true
  // Drop any inline transform left by a drag so the .open class takes over
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
  // Drop the drag transform, then re-measure the closed offset after layout
  if (wrapperEl.value) wrapperEl.value.style.transform = ''
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
  // The closed offset lives in a custom property: the `.open` class sets
  // `transform` itself, so opening always wins over a stale closed offset.
  wrapperEl.value.style.setProperty('--panel-closed-y', `${h - PANEL_CLOSED_PEEK}px`)
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
  // Inline on purpose: a live drag must beat both the class and the variable.
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
// ── Theme (light/dark) — see composables/useThemeMode.js
const { colorMode } = useThemeMode()

const { isMobile, mobileFocus, mobileStackActive, sheetEmpty, setMobileFocus, rollerContentH, onBandDragStart, tapBand } = useMobileBands({
  wrapperEl, gmMode, entityId, viewingEntityId,
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
  if (playerId.value) fetchPlayerBodies()  // who is driving whom (dot sizing)
  // Periodically re-fetch presence so grace-window expiry (a player whose device
  // slept past the 10-minute grace) drops them from the online list.
  // `playerBodies` rides along: it is how the map knows which occupants are being
  // driven, and a missed `body_changed` would otherwise leave a dot sized up
  // until something else refreshed it.
  presencePollTimer = setInterval(() => {
    if (playerId.value) { fetchOnlinePlayers(true); fetchPlayerBodies(true) }
  }, 60_000)
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
  poolLocations.value = {}
  contests.value = []
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
    startSession(sessionId.value).then((res) => {
      if (res?.in_session) inSession.value = true
    })
  }
}

async function onEndSession() {
  remotePools.value = {}
  remoteResults.value = {}
  poolLocations.value = {}
  contests.value = []
  if (sessionId.value && sessionId.value !== 'session-default') {
    const res = await endSession(sessionId.value)
    if (res && res.in_session === false) inSession.value = false
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
  resetSwitchAnimation()
  switchError.value = ''
  resetFinder()
  fetchPlayerEntities()
  fetchSupportCharacters()
  fetchActiveMains()
  showLoginOverlay.value = true
}

function dismissOverlay() {
  if (playerId.value) {
    if (needsCharacterPick.value) return  // must pick an owned character first
    resetSwitch()
    resetSwitchAnimation()
    showLoginOverlay.value = false
  }
}

function onCharChipClick(e) {
  if (isReleaseSuppressed()) return
  clearReleaseReveal()
  selectCharacter(e)
}

function selectCharacter(e) {
  beginCharacterSwitch(e)
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
.main-badge { font-size: 9px; text-transform: uppercase; letter-spacing: 0.5px; padding: 1px 5px; border-radius: 3px; color: var(--text-invert); background: var(--accent); font-weight: 600; margin-left: 4px; }
.main-toggle {
  flex-shrink: 0;
  width: 32px;
  height: 32px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  cursor: pointer;
  font-size: 16px;
  line-height: 1;
  color: var(--text-dim);
  opacity: 0.45;
  transition: color 0.15s, opacity 0.15s, background 0.15s;
}
.main-toggle.on { color: var(--accent); opacity: 1; }
.main-toggle:hover { opacity: 1; background: var(--overlay-8); }
</style>
