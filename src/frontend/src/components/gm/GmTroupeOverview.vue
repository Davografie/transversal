<template>
  <div class="troupe-overview">
    <div class="troupe-header">
      <h3>Troupe</h3>
      <div v-if="sceneLabel" class="scene-line">
        <span class="scene-loc">📍 {{ sceneLabel }}</span>
        <span class="scene-counts">
          <span class="count in-scene">● {{ inSceneCount }} in-scene</span>
          <span class="count scattered">○ {{ scatteredCount }} scattered</span>
        </span>
      </div>
    </div>

    <div v-if="loading && onlineRotationPlayers.length === 0" class="empty">Loading troupe…</div>
    <div v-else-if="onlineRotationPlayers.length === 0" class="empty">No players online</div>

    <template v-else>
      <!-- Active mains (players currently on their main), with nested SCs -->
      <div v-if="activeMainGroups.length" class="active-section">
        <div class="section-label">Active</div>
        <div class="main-groups">
          <div v-for="a in activeMainGroups" :key="a.playerId" class="main-group">
            <div class="main-line" :class="{ clickable: a.main?.currentLocation }" :title="a.main?.currentLocation ? 'Go to location' : ''" @click="goTo(a.main)">
              <MediaImage v-if="a.main?.sheetPortrait" :src="a.main.sheetPortrait" class="row-portrait" alt="" />
              <span v-else class="entity-type-badge" :class="'type-' + (a.main?.type || 'CHARACTER')">{{ typeBadge(a.main) }}</span>
              <span class="row-main">{{ a.main?.name || a.playerId }}</span>
              <span class="row-player">{{ a.playerName || a.playerId }}</span>
              <span class="row-state" :class="mainStateClass(a.main)">{{ mainStateLabel(a.main) }}</span>
            </div>
            <div v-for="sc in scsFor(a.main?.id)" :key="sc.entity?.id" class="sc-line" :class="{ clickable: sc.entity?.currentLocation }" @click="goTo(sc.entity)">
              <span class="sc-name">{{ sc.entity?.name || sc.entity?.id }}</span>
              <span class="sc-status" :class="scStatusClass(sc)">{{ scStatus(sc) }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Rotation: remaining online players' primary mains, oldest-first -->
      <div v-if="remainingPlayers.length" class="rotation-section">
        <div class="section-label">Rotation</div>
        <div class="recency-list">
          <div
            v-for="(p, i) in remainingPlayers"
            :key="p.id"
            class="recency-row"
            :class="{ 'due': i === 0 }"
          >
            <div class="recency-line" :class="{ clickable: p.mainEntity?.currentLocation }" @click="goTo(p.mainEntity)">
              <span v-if="i === 0" class="due-dot" title="Most due for spotlight">◉</span>
              <span v-else class="due-dot placeholder"></span>
              <MediaImage v-if="p.mainEntity?.sheetPortrait" :src="p.mainEntity.sheetPortrait" class="row-portrait" alt="" />
              <span v-else class="entity-type-badge" :class="'type-' + (p.mainEntity?.type || 'CHARACTER')">{{ typeBadge(p.mainEntity) }}</span>
              <span class="row-main">{{ p.mainEntity?.name || '—' }}</span>
              <span class="row-player">{{ p.name }}</span>
              <span class="row-recency">{{ relTime(p.lastSpotlightAt) }}</span>
              <span class="row-state" :class="mainStateClass(p.mainEntity)">{{ mainStateLabel(p.mainEntity) }}</span>
            </div>
            <div v-if="playedBody(p)" class="playing-support">▸ playing {{ playedBody(p).name }}</div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted } from 'vue'
import MediaImage from '@/components/MediaImage.vue'
import { useTroupe } from '@/composables/useTroupe.js'

const props = defineProps({
  currentLocationId: { type: String, default: '' },
  currentLocationName: { type: String, default: '' },
})

const emit = defineEmits(['go-to-location'])

const {
  players, supportCharacters, activeMains, playerBodies, onlinePlayers,
  loading,
  fetchRecency, fetchSupportCharacters, fetchActiveMains, fetchPlayerBodies, fetchOnlinePlayers,
} = useTroupe()

const sceneLabel = computed(() => props.currentLocationName || props.currentLocationId || '')

// Online, non-architect players (the rotation).
const onlineRotationPlayers = computed(() =>
  players.value.filter((p) => p.role !== 'architect' && onlinePlayers.value.includes(p.id))
)

// Active mains: players currently controlling their main.
const activeMainGroups = computed(() =>
  activeMains.value.filter((a) => {
    const p = players.value.find((pl) => pl.id === a.playerId)
    return p && p.role !== 'architect' && onlinePlayers.value.includes(a.playerId)
  })
)

const activePlayerIds = computed(() => new Set(activeMainGroups.value.map((a) => a.playerId)))

// Remaining online players (not currently on their main), oldest-first.
const remainingPlayers = computed(() =>
  onlineRotationPlayers.value.filter((p) => !activePlayerIds.value.has(p.id))
)

function entityInScene(entity) {
  return !!props.currentLocationId && entity?.currentLocation === props.currentLocationId
}

// Navigate the GM's view to an entity's location (GM view, not a perspective
// switch — the assumed entity is left alone).
function goTo(entity) {
  if (entity?.currentLocation) emit('go-to-location', entity.currentLocation)
}

const inSceneCount = computed(() => onlineRotationPlayers.value.filter((p) => entityInScene(p.mainEntity)).length)
const scatteredCount = computed(() => onlineRotationPlayers.value.length - inSceneCount.value)

function typeBadge(main) {
  if (!main) return '—'
  return main.type === 'GMC' ? 'GMC' : main.type === 'FACTION' ? 'FAC' : 'PC'
}

function mainStateLabel(main) {
  if (!main) return 'no main'
  return entityInScene(main) ? 'in-scene' : 'scattered'
}

function mainStateClass(main) {
  return entityInScene(main) ? 'in-scene' : 'scattered'
}

function scsFor(mainId) {
  return supportCharacters.value.filter((sc) => sc.main?.id === mainId)
}

function playedBy(scId) {
  return playerBodies.value.find((b) => b.entity?.id === scId) || null
}

function scStatus(sc) {
  const b = playedBy(sc.entity?.id)
  if (b) return 'played by ' + (b.playerName || b.playerId)
  if (onlinePlayers.value.includes(sc.ownerId)) return 'available'
  return '—'
}

function scStatusClass(sc) {
  if (playedBy(sc.entity?.id)) return 'played'
  if (onlinePlayers.value.includes(sc.ownerId)) return 'available'
  return 'idle'
}

// The body a player is currently controlling, if it isn't their main.
function playedBody(p) {
  const body = playerBodies.value.find((b) => b.playerId === p.id)
  if (!body?.entity) return null
  if (body.entity.id === p.mainEntity?.id) return null
  return body.entity
}

function relTime(iso) {
  if (!iso) return 'never'
  const ms = Date.now() - new Date(iso).getTime()
  if (ms < 60_000) return 'just now'
  const m = Math.floor(ms / 60_000)
  if (m < 60) return `${m}m ago`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}h ago`
  const d = Math.floor(h / 24)
  return `${d}d ago`
}

onMounted(() => {
  fetchRecency()
  fetchSupportCharacters()
  fetchActiveMains()
  fetchPlayerBodies()
  fetchOnlinePlayers()
})
</script>

<style scoped>
.troupe-overview { margin-bottom: 10px; }
.troupe-header { margin-bottom: 6px; }
.troupe-header h3 {
  font-size: 12px; color: var(--text-dim); margin: 0 0 4px;
  text-transform: uppercase; letter-spacing: 1px;
}
.scene-line { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.scene-loc { font-size: 12px; color: var(--text); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.scene-counts { display: flex; gap: 10px; flex: 0 0 auto; font-size: 11px; }
.count.in-scene { color: var(--success); }
.count.scattered { color: var(--text-dim); }

.section-label { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: 1px; margin: 8px 0 4px; }

.active-section, .rotation-section { display: flex; flex-direction: column; gap: 3px; }
.main-groups { display: flex; flex-direction: column; gap: 3px; }
.main-group {
  display: flex; flex-direction: column; gap: 2px;
  padding: 5px 8px; background: var(--accent-12); border: 1px solid var(--accent-32); border-radius: 6px;
}
.main-line { display: flex; align-items: center; gap: 6px; font-size: 13px; }
.main-line.clickable, .sc-line.clickable, .recency-line.clickable { cursor: pointer; }
.main-line.clickable:hover { background: var(--overlay-6); border-radius: 4px; }
.sc-line { display: flex; align-items: center; gap: 6px; padding-left: 22px; font-size: 11px; color: var(--text-dim); }
.sc-line.clickable:hover { color: var(--text); background: var(--overlay-6); border-radius: 4px; }
.sc-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.sc-status { margin-left: auto; flex: 0 0 auto; font-size: 10px; text-transform: uppercase; letter-spacing: 0.5px; }
.sc-status.played { color: var(--text); }
.sc-status.available { color: var(--success); }
.sc-status.idle { color: var(--text-dim); opacity: 0.6; }

.recency-list { display: flex; flex-direction: column; gap: 3px; }
.recency-row {
  display: flex; flex-direction: column; gap: 2px;
  padding: 5px 8px; background: var(--overlay-4); border-radius: 6px;
  font-size: 13px; border: 1px solid transparent;
}
.recency-line { display: flex; align-items: center; gap: 6px; }
.recency-line.clickable:hover { background: var(--overlay-6); border-radius: 4px; }
.recency-row.due { border-color: var(--accent-32); background: var(--accent-12); }
.due-dot { color: var(--accent); font-size: 12px; flex: 0 0 auto; line-height: 1; }
.due-dot.placeholder { visibility: hidden; }
.row-portrait { width: 26px; height: 26px; border-radius: 50%; object-fit: cover; flex: 0 0 auto; }
.entity-type-badge {
  flex: 0 0 auto; font-size: 9px; text-transform: uppercase; letter-spacing: 0.5px;
  padding: 1px 5px; border-radius: 3px; color: var(--accent-pale);
  background: var(--accent-16); border: 1px solid var(--accent-45);
}
.row-main { font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.row-player { font-size: 11px; color: var(--text-dim); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.row-recency { font-size: 11px; color: var(--text-dim); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.row-state { margin-left: auto; flex: 0 0 auto; font-size: 10px; text-transform: uppercase; letter-spacing: 0.5px; }
.row-state.in-scene { color: var(--success); }
.row-state.scattered { color: var(--text-dim); }
.playing-support { font-size: 11px; color: var(--text-dim); padding-left: 22px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.empty { font-size: 12px; color: var(--text-dim); padding: 8px 0; }
</style>
