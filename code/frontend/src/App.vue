<template>
  <div class="sse-indicator" :class="[connected ? 'shape-circle' : 'shape-triangle', { pulse: ssePulse }]" :title="connected ? 'SSE connected' : (error || 'SSE disconnected')"></div>
  <button v-if="playerId && !showLoginOverlay" class="settings-btn" @click="openSettings" title="Player settings">↩</button>
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

        <div v-if="playerEntities.length" class="settings-section">
          <label class="settings-label">Your characters</label>
          <div class="char-list">
            <button
              v-for="e in playerEntities" :key="e.id"
              :class="{ active: entityId === e.id }"
              @click="selectCharacter(e)"
            >{{ e.name || e.id }}</button>
          </div>
        </div>
      </template>

      <p v-if="switchError" class="switch-error">{{ switchError }}</p>
      <button class="cancel-btn" @click="showLoginOverlay = false">Back to game</button>
    </template>
  </div>
  <LocationViewer
    :location-id="currentLocationId"
    :location-name="locationName"
    :universe="universe"
    :background-image="locationBgImage"
    :entity-id="entityId"
    v-model:edit-zones="editZones"
    :overlay="locationOverlay"
    :gm-mode="gmMode"
    @moved="onMoved"
  />
  <div ref="wrapperEl" class="dice-panel-wrapper" :class="{ open: wrapperOpen }" @mouseenter="onWrapperEnter" @mouseleave="onWrapperLeave" @transitionend="onWrapperTransitionEnd">
    <Transition name="sheet-fade">
      <CharacterSheet
        v-if="sheetVisible && !gmMode"
        ref="sheetRef"
        :entity-id="entityId"
        :universe="universe"
        :phase="phase"
        embedded
        @add-to-pool="(d) => diceRef?.addFromSheet(d)"
        @remove-from-pool="(s) => diceRef?.removeBySource(s)"
        @remove-by-ts-id="(id) => diceRef?.removeByTsId(id)"
        @split-die="(d) => diceRef?.splitDie(d)"
        @sfx-toggled="onSfxToggled"
      />
    </Transition>
    <DiceRoller ref="diceRef" :entity-id="entityId" :universe="universe" :keep-count="keepCount" :effect-count="effectCount" @update:universe="u => universe = u" @rolled="(r) => { onRolled(); shareRoll(r); }" @picked="(r) => shareRoll(r)" @pool-change="(s) => { sheetRef?.setPoolSources(s); sharePool(s); }" @phase-change="onPhaseChange" @panel-open="onPanelOpen" />
  </div>
  <GmPanel v-if="gmMode" :universe="universe" :current-location-id="currentLocationId" @next-beat="onNextBeat" @start-session="onStartSession" @end-session="onEndSession" />
</template>

<script setup>
import { ref, useTemplateRef, watch, computed, nextTick } from 'vue'
import LocationViewer from './components/LocationViewer.vue'
import CharacterSheet from './components/CharacterSheet.vue'
import DiceRoller from './components/DiceRoller.vue'
import GmPanel from './components/GmPanel.vue'
import { useSSE } from './composables/useSSE.js'
import { useSessions } from './composables/useSessions.js'

const universe = ref('earth')
const currentLocationId = ref('loc-krasnoyarsk')
const locationName = ref('Krasnoyarsk-45')
const locationBgImage = ref('')
const locationOverlay = ref(null)

// Fetch entity location on mount so refreshes show the real location
async function initLocation() {
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
      locationName.value = '...'
      try {
        const r2 = await fetch(`/api/v1/locations/${currentLocationId.value}/navigate`)
        const nav = await r2.json()
        locationName.value = nav.location?.name || currentLocationId.value
      } catch (e) {
        locationName.value = 'err: ' + e.message
      }
      fetchLocationBg()
    }
  } catch (e) {
    locationName.value = 'err: ' + e.message
  }
}

async function fetchLocationBg() {
  try {
    const r = await fetch('/api/v1/graphql', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query: `query($id: ID!) { entity(id: $id) { backgroundImage overlay } }`, variables: { id: currentLocationId.value } })
    })
    const json = await r.json()
    locationBgImage.value = json.data?.entity?.backgroundImage || ''
    locationOverlay.value = json.data?.entity?.overlay || null
  } catch { locationBgImage.value = ''; locationOverlay.value = null }
}

function onMoved(data) {
  locationName.value = data.location
  if (data.universe) universe.value = data.universe
  currentLocationId.value = data.location_id || data.location
  sheetRef.value?.closeSheet()
  fetchLocationBg()
}
const entityId = ref('kael-1')
const editZones = ref(false)

// When switching entities, update location
watch(entityId, () => {
  if (entityId.value) initLocation()
})
const keepCount = ref(2)
const effectCount = ref(1)
const phase = ref('adding')

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

async function ensurePlayer() {
  if (playerId.value) {
    fetch(`/api/v1/players/${playerId.value}/claim/${entityId.value}`, { method: 'POST' }).catch(() => {})
    loadPlayerRole()
    return
  }

  if (playerName.value) {
    // Have name but no ID — try to recover
    const p = await findOrCreatePlayer(playerName.value)
    if (p) {
      playerId.value = p.id
      localStorage.setItem('playerId', p.id)
      fetch(`/api/v1/players/${playerId.value}/claim/${entityId.value}`, { method: 'POST' }).catch(() => {})
      return
    }
  }

  // No name or ID — show entry
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
const { sessions, currentSession, listSessions, joinSession, publishEvent } = useSessions()
const sessionId = ref('session-default')

async function initSession() {
  await listSessions()
  if (sessions.value.length > 0) {
    const s = sessions.value[0]
    sessionId.value = s.id
    await joinSession(s.id, entityId.value, playerId.value)
  }
}
initSession()
initLocation()

const shareCount = ref(0)
const lastSent = ref('')
const lastEvtDebug = ref('')

function sharePool(sources) {
  if (sessionId.value === 'session-default') return
  shareCount.value++
  lastSent.value = JSON.stringify(sources)
  publishEvent(sessionId.value, 'pool_updated', { player_id: playerId.value, entity_id: entityId.value, dice: sources, phase: phase.value })
}

function sharePhase() {
  if (sessionId.value === 'session-default') return
  lastSent.value = `phase:${phase.value}`
  publishEvent(sessionId.value, 'pool_updated', { player_id: playerId.value, entity_id: entityId.value, dice: [], phase: phase.value })
}
function shareRoll(result) {
  if (sessionId.value !== 'session-default') {
    publishEvent(sessionId.value, 'roll_result', { player_id: playerId.value, entity_id: entityId.value, result, phase: 'resolved' })
  }
}

// SSE — live state sync
const { connected, lastEvent, error } = useSSE(sessionId, entityId)

const remotePools = ref({})  // entity_id → { dice: [...], player_id, phase }
const remoteResults = ref({})  // entity_id → { result, rolls, kept, total, effect_die }

const ssePulse = ref(false)
watch(lastEvent, (evt) => {
  if (!evt) return
  ssePulse.value = true
  setTimeout(() => { ssePulse.value = false }, 300)

  const pid = evt.data?.player_id
  const eid = evt.data?.entity_id

  switch (evt.type) {
    case 'razmerit_changed':
      if (eid === entityId.value) sheetRef.value?.fetchEntity()
      break
    case 'trait_updated':
      if (eid === entityId.value) sheetRef.value?.fetchEntity()
      break
    case 'location_changed':
      if (eid === entityId.value && evt.data?.to) locationName.value = evt.data.to
      break
    case 'entity_updated':
      if (eid === currentLocationId.value) fetchLocationBg()
      break
    case 'scene_change':
      if (evt.data?.to_location) locationName.value = evt.data.to_location
      break
    case 'pool_updated':
      lastEvtDebug.value = `pid=${pid} eid=${eid} phase=${evt.data.phase} dice=${JSON.stringify(evt.data.dice)} mypid=${playerId.value}`
      if (pid !== playerId.value && eid) {
        const phase = evt.data.phase || 'adding'
        remotePools.value = { ...remotePools.value, [eid]: { dice: evt.data.dice || [], player_id: pid, phase } }
        if (phase === 'adding' && (!evt.data.dice || evt.data.dice.length === 0)) {
          const { [eid]: _, ...rest } = remoteResults.value
          remoteResults.value = rest
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
          rolls: (res.rolls && res.rolls.length) ? res.rolls : (existing.rolls || []),
        }}
      }
      break
  }
})

function onPhaseChange(p) {
  phase.value = p
  if (p === 'adding') {
    keepCount.value = 2
    effectCount.value = 1
    sheetRef.value?.resetSfxCounts()
  }
  sharePhase()
}
const diceRef = useTemplateRef('diceRef')
const sheetRef = useTemplateRef('sheetRef')
const switchInputRef = useTemplateRef('switchInputRef')

const hoverOpen = ref(false)
const sheetVisible = ref(false)
let sheetTimer = null

const wrapperEl = useTemplateRef('wrapperEl')
const wrapperOpen = computed(() => hoverOpen.value || sheetVisible.value)

function onPanelOpen(v) {
  // Dice panel opened by add-die or swipe — show sheet after slide-up
  if (v) {
    hoverOpen.value = true
    // sheetVisible will be set by onWrapperTransitionEnd when slide completes
  } else {
    hoverOpen.value = false
    sheetVisible.value = false
  }
}

function onWrapperTransitionEnd(e) {
  // Only react to transform transitions on the wrapper itself
  if (e.target !== wrapperEl.value || e.propertyName !== 'transform') return
  if (wrapperOpen.value) {
    // Slide-up complete — show the sheet
    sheetVisible.value = true
  }
}

function onWrapperEnter() {
  hoverOpen.value = true
  // sheetVisible set by transitionend
}

function onWrapperLeave() {
  hoverOpen.value = false
  sheetVisible.value = false
  if (sheetTimer) { clearTimeout(sheetTimer); sheetTimer = null }
}

function onRolled() {
  sheetRef.value?.resetSfxCounts()
}

function onSfxToggled(e) {
  if (e.sfxId === 'sfx-spray-n-pray') {
    effectCount.value = e.active ? 2 : 1
  }
}

// ── GM shortcuts ─────────────────────────────────

function onNextBeat() {
  // Clear local pool
  diceRef.value?.clearPool()
  // Clear remote pools and results
  remotePools.value = {}
  remoteResults.value = {}
  // Broadcast empty pool to session
  if (sessionId.value !== 'session-default') {
    publishEvent(sessionId.value, 'pool_updated', { player_id: playerId.value, entity_id: entityId.value, dice: [], phase: 'adding' })
  }
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
  fetchPlayerEntities()
  showLoginOverlay.value = true
}

function dismissOverlay() {
  if (playerId.value) {
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
  playerEntities.value = await fetchEntitiesFor(playerId.value)
}

async function fetchEntitiesFor(pid) {
  try {
    const r = await fetch(`/api/v1/players/${pid}`)
    const p = await r.json()
    if (p && p.entity_ids) {
      const results = []
      for (const eid of p.entity_ids) {
        try {
          const r2 = await fetch('/api/v1/graphql', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query: `query($id: ID!) { entity(id: $id) { id name type } }`, variables: { id: eid } })
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
  initLocation()
  loadPlayerRole()
}

function selectCharacter(e) {
  charPending.value = e
  charStatus.value = `Assume the form of ${e.name || e.id}?`
}

async function loadPlayerRole() {
  if (!playerId.value) return
  try {
    const r = await fetch(`/api/v1/players/${playerId.value}`)
    const p = await r.json()
    if (p && p.role) {
      const isArchitect = p.role === 'architect'
      gmMode.value = isArchitect
      localStorage.setItem('architectMode', isArchitect ? 'true' : 'false')
    }
  } catch {}
}

function confirmChar() {
  if (!charPending.value) return
  entityId.value = charPending.value.id
  charStatus.value = ''
  charPending.value = null
  showLoginOverlay.value = false
}

watch(gmMode, (v) => {
  const role = v ? 'architect' : 'player'
  localStorage.setItem('architectMode', v ? 'true' : 'false')
  if (playerId.value) {
    fetch(`/api/v1/players/${playerId.value}/role`, {
      method: 'PATCH', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ role })
    }).catch(() => {})
  }
})
</script>
