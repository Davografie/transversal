<template>
  <div class="location-viewer-panel panel" :class="{ open }">
    <button class="toggle" @click="open = !open">{{ open ? '×' : '📍' }}</button>

    <div v-if="open" class="nav-content">
      <div v-if="loading" class="loading">Loading…</div>
      <div v-else-if="error" class="error">{{ error }}</div>

      <template v-else-if="nav">
        <h4>{{ nav.location?.name || locationId }}</h4>

        <!-- Up -->
        <div v-if="nav.parent" class="nav-section">
          <span class="nav-label">▲ Up</span>
          <button class="nav-btn" @click="moveTo(nav.parent._key, nav.parent.current_universe)">{{ nav.parent.name }}</button>
        </div>

        <!-- Down (children) -->
        <div v-if="nav.children?.length" class="nav-section">
          <span class="nav-label">▼ Areas</span>
          <button v-for="c in nav.children" :key="c._key" class="nav-btn" @click="moveTo(c._key, c.current_universe)">{{ c.name }}</button>
        </div>

        <!-- Lateral (transversal) -->
        <div v-if="nav.transversal?.length" class="nav-section">
          <span class="nav-label">↔ Travel</span>
          <button v-for="t in nav.transversal" :key="t._key" class="nav-btn link-btn" @click="moveTo(t._key, t.current_universe)">{{ t.name }}</button>
        </div>

        <!-- Occupants -->
        <div v-if="nav.occupants?.length" class="nav-section">
          <span class="nav-label">● Present</span>
          <div v-for="o in nav.occupants" :key="o.id" class="occupant-row">
            <span class="occupant-type" :class="'occ-' + o.type">{{ o.type === 'character' ? 'PC' : 'GMC' }}</span>
            <span class="occupant-name">{{ o.name }}</span>
          </div>
        </div>

        <div v-if="!nav.parent && !nav.children?.length && !nav.transversal?.length && !nav.occupants?.length" class="empty">
          No navigation options from here.
        </div>
      </template>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, onMounted } from 'vue'
import { useApi } from '../composables/useApi.js'

const props = defineProps({
  locationId: { type: String, required: true },
  entityId: { type: String, required: true }
})

const emit = defineEmits(['moved'])

const { loading, error, roll } = useApi()
const open = ref(false)
const nav = ref(null)

async function fetchNav() {
  loading.value = true
  try {
    const r = await fetch(`/api/v1/locations/${props.locationId}/navigate`)
    nav.value = await r.json()
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

async function moveTo(locationId, universe) {
  try {
    const r = await fetch(`/api/v1/entities/${props.entityId}/move`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ location: locationId, universe })
    })
    const data = await r.json()
    emit('moved', data)
    open.value = false
  } catch (e) {
    error.value = e.message
  }
}

onMounted(fetchNav)
watch(() => props.locationId, fetchNav)
</script>

<style scoped>
.location-viewer-panel {
  position: fixed;
  top: env(safe-area-inset-top, 60px);
  left: 12px;
  z-index: 15;
  min-width: 44px;
  max-width: 260px;
  transition: all 0.3s ease;
  max-height: calc(100vh - 200px);
  overflow-y: auto;
}
.location-viewer-panel.open { padding: 14px; }

.toggle {
  position: absolute;
  top: 4px; right: 4px;
  width: 32px; height: 32px;
  border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  font-size: 16px; padding: 0;
  background: var(--bg-panel);
}

.nav-content { margin-top: 20px; }

h4 { font-size: 13px; color: var(--text-dim); margin-bottom: 8px; text-transform: uppercase; letter-spacing: 1px; }

.nav-section { margin-bottom: 10px; }
.nav-label { font-size: 10px; color: var(--text-dim); display: block; margin-bottom: 4px; }

.nav-btn {
  display: block; width: 100%; text-align: left;
  font-size: 13px; padding: 6px 10px; margin-bottom: 3px;
  background: rgba(255,255,255,0.06); border-radius: 6px;
  cursor: pointer; transition: background 0.15s;
  border: none; color: var(--text);
}
.nav-btn:hover { background: rgba(255,255,255,0.12); }
.link-btn { border-left: 2px solid var(--accent-dim); }

.occupant-row {
  display: flex; align-items: center; gap: 6px;
  padding: 3px 8px; font-size: 12px;
}
.occupant-type {
  font-size: 9px; font-weight: 600; padding: 1px 5px; border-radius: 3px;
}
.occ-character { background: var(--accent-dim); color: var(--accent); }
.occ-gmc { background: rgba(232,136,48,0.2); color: var(--warn); }
.occupant-name { color: var(--text-dim); }

.loading, .error, .empty { font-size: 12px; color: var(--text-dim); padding: 8px 0; }
.error { color: var(--danger); }
</style>
