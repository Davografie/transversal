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

    <div v-if="loading && rotationPlayers.length === 0" class="empty">Loading troupe…</div>
    <div v-else-if="rotationPlayers.length === 0" class="empty">No players</div>
    <div v-else class="recency-list">
      <div
        v-for="(p, i) in rotationPlayers"
        :key="p.id"
        class="recency-row"
        :class="{ 'due': i === 0 }"
      >
        <div class="recency-line">
          <span v-if="i === 0" class="due-dot" title="Most due for spotlight">◉</span>
          <span v-else class="due-dot placeholder"></span>
          <MediaImage
            v-if="p.mainEntity?.sheetPortrait"
            :src="p.mainEntity.sheetPortrait"
            class="row-portrait"
            alt=""
          />
          <span
            v-else
            class="entity-type-badge"
            :class="'type-' + (p.mainEntity?.type || 'CHARACTER')"
          >{{ typeBadge(p.mainEntity) }}</span>
          <span class="row-main">{{ p.mainEntity?.name || '—' }}</span>
          <span class="row-player">{{ p.name }}</span>
          <span class="row-state" :class="stateClass(p)">{{ stateLabel(p) }}</span>
        </div>
        <div v-if="playedSupport(p)" class="playing-support">
          ▸ playing {{ playedSupport(p).entity.name }}
          <span class="for">(for {{ playedSupport(p).main?.name || '—' }})</span>
        </div>
      </div>
    </div>
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

const { players, supportCharacters, playerBodies, loading, fetchRecency, fetchSupportCharacters, fetchPlayerBodies } = useTroupe()

const sceneLabel = computed(() => props.currentLocationName || props.currentLocationId || '')

// Spotlight rotation excludes architect identities (the GM's own logins) —
// they run scenes rather than rotate the spotlight.
const rotationPlayers = computed(() => players.value.filter((p) => p.role !== 'architect'))

// A main is "in-scene" when its current location matches the GM's scene.
function isInScene(p) {
  return !!props.currentLocationId && p.mainEntity?.currentLocation === props.currentLocationId
}

const inSceneCount = computed(() => rotationPlayers.value.filter(isInScene).length)
const scatteredCount = computed(() => rotationPlayers.value.length - inSceneCount.value)

function typeBadge(main) {
  if (!main) return '—'
  return main.type === 'GMC' ? 'GMC' : main.type === 'FACTION' ? 'FAC' : 'PC'
}

function stateLabel(p) {
  if (!p.mainEntity) return 'no main'
  return isInScene(p) ? 'in-scene' : 'scattered'
}

function stateClass(p) {
  if (!p.mainEntity) return 'scattered'
  return isInScene(p) ? 'in-scene' : 'scattered'
}

// The SC a player is currently playing (if their body is a support character).
function playedSupport(p) {
  const body = playerBodies.value.find((b) => b.playerId === p.id)
  if (!body?.entity?.id) return null
  const sc = supportCharacters.value.find((s) => s.entity?.id === body.entity.id)
  return sc ? { entity: sc.entity, main: sc.main } : null
}

onMounted(() => {
  fetchRecency()
  fetchSupportCharacters()
  fetchPlayerBodies()
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

.recency-list { display: flex; flex-direction: column; gap: 3px; }
.recency-row {
  display: flex; flex-direction: column; gap: 2px;
  padding: 5px 8px; background: rgba(255,255,255,0.04); border-radius: 6px;
  font-size: 13px; border: 1px solid transparent;
}
.recency-line { display: flex; align-items: center; gap: 6px; }
.recency-row.due { border-color: rgba(64,136,212,0.35); background: rgba(64,136,212,0.10); }
.due-dot { color: var(--accent); font-size: 12px; flex: 0 0 auto; line-height: 1; }
.due-dot.placeholder { visibility: hidden; }
.row-portrait { width: 26px; height: 26px; border-radius: 50%; object-fit: cover; flex: 0 0 auto; }
.entity-type-badge {
  flex: 0 0 auto; font-size: 9px; text-transform: uppercase; letter-spacing: 0.5px;
  padding: 1px 5px; border-radius: 3px; color: #93c5fd;
  background: rgba(64,136,212,0.16); border: 1px solid rgba(64,136,212,0.4);
}
.row-main { font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.row-player { font-size: 11px; color: var(--text-dim); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.row-state { margin-left: auto; flex: 0 0 auto; font-size: 10px; text-transform: uppercase; letter-spacing: 0.5px; }
.row-state.in-scene { color: var(--success); }
.row-state.scattered { color: var(--text-dim); }
.playing-support { font-size: 11px; color: var(--text-dim); padding-left: 22px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.playing-support .for { color: var(--text-dim); opacity: 0.7; }
.empty { font-size: 12px; color: var(--text-dim); padding: 8px 0; }
</style>
