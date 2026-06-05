<template>
  <div class="sse-indicator" :class="[connected ? 'shape-circle' : 'shape-triangle', { pulse: ssePulse }]" :title="connected ? 'SSE connected' : (error || 'SSE disconnected')"></div>
  <div class="entity-switcher">
    <div v-for="c in characters" :key="c" class="entity-pill">
      <button
        :class="{ active: entityId === c }"
        @click="entityId = c"
      >{{ c === 'kael-1' ? 'Kael' : 'Elena' }}</button>
      <!-- Adding: show dice types -->
      <div v-if="remotePools[c] && remotePools[c].phase === 'adding'" class="entity-pool">
        <span v-for="(d, i) in remotePools[c].dice" :key="i" class="pool-chip">{{ d }}</span>
      </div>
      <!-- Picking/rolling: show raw rolled values as die icons -->
      <div v-if="remotePools[c] && (remotePools[c].phase === 'picking' || remotePools[c].phase === 'rolling')" class="entity-pool">
        <template v-if="remoteResults[c] && remoteResults[c].pipeline === 'pool' && remoteResults[c].rolls.length">
          <DieIcon v-for="(r, i) in remoteResults[c].rolls" :key="i" :die="r.die" :result="r.result" :is-hitch="r.result === 1" class="entity-die" />
        </template>
        <template v-else>
          <span v-for="(d, i) in remotePools[c].dice" :key="i" class="pool-chip">{{ d }}</span>
        </template>
      </div>
      <!-- Resolved: total + effect -->
      <div v-if="remoteResults[c] && remotePools[c]?.phase === 'resolved'" class="entity-result">
        <div class="result-pill">
          <template v-if="remoteResults[c].pipeline === 'simplified'">
            <span class="result-pill-total">{{ remoteResults[c].total }}</span>
            <span class="result-pill-tier">{{ remoteResults[c].tier }}</span>
          </template>
          <template v-else>
            <span class="result-pill-total">{{ remoteResults[c].total }}</span>
            <DieIcon v-if="remoteResults[c].effect_die" :die="remoteResults[c].effect_die" class="result-pill-die" />
          </template>
          <span v-if="remoteResults[c].botch" class="result-pill-botch">!</span>
        </div>
      </div>
    </div>
  </div>
  <div v-if="!playerId" class="name-entry panel">
    <h3>Who are you?</h3>
    <p class="name-hint">Your name is your recovery key — use the same name on any device.</p>
    <input v-model="playerName" placeholder="Your name" @keyup.enter="submitPlayerName" autofocus :disabled="checking" />
    <button @click="submitPlayerName" :disabled="checking || !playerName.trim()">{{ checking ? 'Checking…' : 'Enter' }}</button>
    <p v-if="nameStatus" class="name-status" :class="{ 'name-found': nameFound, 'name-new': !nameFound }">{{ nameStatus }}</p>
    <button v-if="nameStatus" class="continue-btn" @click="confirmPlayer">{{ nameFound ? 'Continue' : 'Begin' }}</button>
  </div>
  <LocationViewer
    :location-id="currentLocationId"
    :location-name="locationName"
    :universe="universe"
    :background-image="locationBgImage"
    :entity-id="entityId"
    :edit-zones="editZones"
    @moved="onMoved"
  />
  <CharacterSheet ref="sheetRef" :entity-id="entityId" :universe="universe" :phase="phase" @add-to-pool="(d) => diceRef?.addFromSheet(d)" @remove-from-pool="(s) => diceRef?.removeBySource(s)" @remove-by-ts-id="(id) => diceRef?.removeByTsId(id)" @split-die="(d) => diceRef?.splitDie(d)" @sfx-toggled="onSfxToggled" />
  <DiceRoller ref="diceRef" :entity-id="entityId" :universe="universe" :keep-count="keepCount" :effect-count="effectCount" @update:universe="u => universe = u" @rolled="(r) => { onRolled(); shareRoll(r); }" @picked="(r) => shareRoll(r)" @pool-change="(s) => { sheetRef?.setPoolSources(s); sharePool(s); }" @phase-change="onPhaseChange" />
  <GmPanel :universe="universe" v-model:edit-zones="editZones" />
</template>

<script setup>
import { ref, useTemplateRef, watch } from 'vue'
import LocationViewer from './components/LocationViewer.vue'
import DieIcon from './components/DieIcon.vue'
import CharacterSheet from './components/CharacterSheet.vue'
import DiceRoller from './components/DiceRoller.vue'
import GmPanel from './components/GmPanel.vue'
import { useSSE } from './composables/useSSE.js'
import { useSessions } from './composables/useSessions.js'

const universe = ref('earth')
const currentLocationId = ref('loc-krasnoyarsk')
const locationName = ref('Krasnoyarsk-45')
const locationBgImage = ref('')

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
      body: JSON.stringify({ query: `query($id: ID!) { entity(id: $id) { backgroundImage } }`, variables: { id: currentLocationId.value } })
    })
    const json = await r.json()
    locationBgImage.value = json.data?.entity?.backgroundImage || ''
  } catch { locationBgImage.value = '' }
}

function onMoved(data) {
  locationName.value = data.location
  if (data.universe) universe.value = data.universe
  currentLocationId.value = data.location_id || data.location
  sheetRef.value?.closeSheet()
  fetchLocationBg()
}
const entityId = ref('kael-1')
const characters = ['kael-1', 'elena-1']
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
const showNameEntry = ref(false)
const checking = ref(false)
const nameStatus = ref('')
const nameFound = ref(false)
const pendingPlayer = ref(null)

async function findOrCreatePlayer(name) {
  try {
    const r = await fetch('/api/v1/players', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name }) })
    return await r.json()
  } catch { return null }
}

async function ensurePlayer() {
  if (playerId.value) {
    // Already have ID — claim current entity
    fetch(`/api/v1/players/${playerId.value}/claim/${entityId.value}`, { method: 'POST' }).catch(() => {})
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
  showNameEntry.value = true
}

async function submitPlayerName() {
  const name = playerName.value.trim()
  if (!name) return
  checking.value = true
  const p = await findOrCreatePlayer(name)
  checking.value = false
  if (!p) return
  pendingPlayer.value = p
  localStorage.setItem('playerName', name)
  if (p.found) {
    nameStatus.value = `Welcome back, ${name}!`
    nameFound.value = true
  } else {
    nameStatus.value = `New traveler — welcome, ${name}!`
    nameFound.value = false
  }
}

function confirmPlayer() {
  if (!pendingPlayer.value) return
  playerId.value = pendingPlayer.value.id
  localStorage.setItem('playerId', pendingPlayer.value.id)
  nameStatus.value = ''
  pendingPlayer.value = null
  fetch(`/api/v1/players/${playerId.value}/claim/${entityId.value}`, { method: 'POST' }).catch(() => {})
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

function onRolled() {
  sheetRef.value?.resetSfxCounts()
}

function onSfxToggled(e) {
  if (e.sfxId === 'sfx-spray-n-pray') {
    effectCount.value = e.active ? 2 : 1
  }
}
</script>
