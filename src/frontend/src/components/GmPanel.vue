<template>
  <div class="gm-content">
    <div class="mode-tabs">
      <button :class="{ active: mode === 'play' }" @click="mode = 'play'">Play</button>
      <button :class="{ active: mode === 'prep' }" @click="mode = 'prep'">Prep</button>
    </div>

    <template v-if="mode === 'play'">
      <div class="gm-shortcuts">
        <button class="shortcut-btn beat-btn" @click="nextBeat">◆ Next Beat</button>
        <button class="shortcut-btn scene-btn" @click="viewSceneSummary = !viewSceneSummary">◈ Scene</button>
        <button v-if="!sessionActive" class="shortcut-btn session-btn" @click="startSession">▶ Start</button>
        <button v-else class="shortcut-btn session-btn active" @click="endSession">■ End</button>
      </div>
      <GmSceneSummary v-if="viewSceneSummary" :entities="sceneEntities" @inspect="inspectEntity" />
    </template>

    <template v-if="mode === 'prep'">
      <div class="filter-bar">
        <div class="chip-bar">
          <span v-for="(f, i) in activeFilters" :key="i" class="filter-chip">
            <span class="chip-label">{{ f.label }}</span>
            <button class="chip-remove" @click="activeFilters.splice(i, 1)">×</button>
          </span>
        </div>
        <div class="filter-input-wrap">
          <input v-model="filterInput" class="filter-input" placeholder="Filter…" @focus="showSuggestions = true" @blur="hideSuggestions" @keyup.escape="filterInput = ''" />
          <button v-if="filterInput" class="filter-clear-inline" @click="filterInput = ''">✕</button>
          <div v-if="showSuggestions && suggestions.length" class="filter-suggestions">
            <div v-for="s in suggestions" :key="s.id" class="suggestion-row" @mousedown.prevent="selectSuggestion(s)">
              <span class="entity-type-badge" :class="'type-' + (s.entityType || s.type || '')">{{ s.entityType || s.type || '' }}</span><span>{{ s.name }}</span>
              <span class="suggestion-hint">{{ s.hint }}</span>
            </div>
          </div>
        </div>
      </div>
      <button class="create-btn" @click="startCreate">+ New Entity</button>
      <GmLocationTree :flat-tree="flatTree" :expanded-ids="expandedNodes" :selected-id="selectedId" @select-universe="onSelectUniverse" @select-location="onSelectLocation" @select-occupant="onSelectOccupant" @toggle-expand="toggleTreeNode" @move-entity="onMoveEntity" />
      <h4 v-if="filteredFactions.length" class="factions-heading">Factions</h4>
      <div v-for="e in filteredFactions" :key="e.id" class="entity-row" :class="{ selected: selectedId === e.id }" @click="toggleEntity(e)">
        <span class="entity-type-badge type-FACTION">FAC</span><span class="entity-name">{{ e.name }}</span>
        <span class="entity-universe" v-if="e.currentUniverse !== universe">{{ e.currentUniverse }}</span>
      </div>
      <button class="create-btn" style="margin-top:8px" @click="openTraitsConfig">Manage Traits</button>
      <div v-if="flatTree.length === 0 && filteredFactions.length === 0" class="empty">No entities found</div>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useApi } from '@/composables/useApi.js'
import { useEntityCrud } from '@/composables/useEntityCrud.js'
import { useTraitsConfig } from '@/composables/useTraitsConfig.js'
import { useLocationTree } from '@/composables/useLocationTree.js'
import { usePanel } from '@/composables/usePanel.js'
import CharacterSheet from '@/components/CharacterSheet.vue'
import GmSceneSummary from '@/components/gm/GmSceneSummary.vue'
import GmLocationTree from '@/components/gm/GmLocationTree.vue'
import GmTraitsetsPanel from '@/components/gm/GmTraitsetsPanel.vue'
import GmEntityEditPanel from '@/components/gm/GmEntityEditPanel.vue'
import GmEntityCreatePanel from '@/components/gm/GmEntityCreatePanel.vue'
import ImageViewer from '@/components/gm/ImageViewer.vue'

const { graphql } = useApi()
const panel = usePanel()

const props = defineProps({
  universe: { type: String, default: 'earth' },
  currentLocationId: { type: String, default: '' },
})

const emit = defineEmits(['next-beat', 'start-session', 'end-session', 'add-to-pool'])

// ── Composables ─────────────────────────────────────
const {
  entities, selected, selectedId, editing, creating, saving, form,
  jobStatuses, imagenJob, animateJob,
  fetchEntities, selectEntity, saveEntity, deleteEntity, createEntity,
  uploadBgImage, pollJobs, onImagen, onCancel,
} = useEntityCrud()

const {
  traitsets, allSfxs, loading: traitsLoading,
  fetchTraitsConfig, patchData, traitNameMap,
} = useTraitsConfig()

// ── Session UI ──────────────────────────────────────
const mode = ref('play')
const viewSceneSummary = ref(true)
const sessionActive = ref(false)

function nextBeat() { emit('next-beat') }
function startSession() { sessionActive.value = true; emit('start-session') }
function endSession() { sessionActive.value = false; emit('end-session') }

// ── Job polling ─────────────────────────────────────
let _jobPollTimer = null
function startJobPolling() {
  pollJobs()
  _jobPollTimer = setInterval(pollJobs, 2000)
}
function stopJobPolling() { clearInterval(_jobPollTimer) }

// ── Filter state ────────────────────────────────────
const activeFilters = ref([])
const filterInput = ref('')
const showSuggestions = ref(false)

// ⚠ Both value AND q must be lowercased.
function fuzzyMatch(value, q) {
  if (!value || !q) return false
  const raw = value.toLowerCase()
  const ql = q.toLowerCase()
  if (raw.includes(ql)) return true
  const normalized = raw.replace(/_/g, ' ')
  if (normalized.includes(ql)) return true
  const qNormalized = ql.replace(/ /g, '_')
  if (raw.includes(qNormalized)) return true
  return false
}

function entityMatchesFilters(e) {
  for (const f of activeFilters.value) {
    if (f.type === 'universe' && e.currentUniverse !== f.value) return false
    if (f.type === 'entityType' && e.type !== f.value) return false
    if (f.type === 'name' && !fuzzyMatch(e.name, f.value)) return false
  }
  return true
}

function traitsetMatchesFilters(ts) {
  for (const f of activeFilters.value) {
    if (f.type === 'universe' && !(ts.universes || []).includes(f.value)) return false
    if (f.type === 'entityType' && (ts.entityTypes || []).length > 0 && !(ts.entityTypes || []).includes(f.value)) return false
    if (f.type === 'name' && !fuzzyMatch(ts.name, f.value)) return false
  }
  return true
}

// ── Filtered data ───────────────────────────────────
const filteredEntities = computed(() => entities.value.filter(entityMatchesFilters))
const filteredFactions = computed(() => filteredEntities.value.filter(e => e.type === 'FACTION'))
const sceneEntities = computed(() => filteredEntities.value.filter(e => e.type === 'CHARACTER' || e.type === 'GMC'))
const locationEntities = computed(() => filteredEntities.value.filter(e => e.type === 'LOCATION'))
const universes = computed(() => entities.value.filter(e => e.type === 'UNIVERSE').map(u => ({ key: u.currentUniverse, name: u.name })))

// ── Autocomplete ────────────────────────────────────
const suggestions = computed(() => {
  const q = filterInput.value.trim().toLowerCase()
  if (!q) return []
  const results = []
  const seen = new Set()
  for (const u of universes.value) {
    if ((u.key && fuzzyMatch(u.key, q)) || (u.name && fuzzyMatch(u.name, q))) {
      if (!seen.has('uni:' + u.key)) {
        seen.add('uni:' + u.key)
        results.push({ id: 'uni:' + u.key, name: u.name || u.key, entityType: 'UNIVERSE', hint: 'universe', filterType: 'universe', filterValue: u.key, filterLabel: u.name || u.key })
      }
    }
  }
  const types = ['CHARACTER', 'LOCATION', 'GMC', 'FACTION', 'ASSET']
  for (const t of types) {
    if (fuzzyMatch(t, q)) {
      results.push({ id: 'type:' + t, name: t.charAt(0) + t.slice(1).toLowerCase(), entityType: t, hint: 'type', filterType: 'entityType', filterValue: t, filterLabel: t.charAt(0) + t.slice(1).toLowerCase() })
    }
  }
  for (const e of entities.value.filter(entityMatchesFilters)) {
    if (fuzzyMatch(e.name, q) && !seen.has('ent:' + e.id)) {
      seen.add('ent:' + e.id)
      results.push({ id: 'ent:' + e.id, name: e.name, entityType: e.type, hint: 'name', filterType: 'name', filterValue: e.name, filterLabel: e.name })
    }
  }
  return results.slice(0, 10)
})

function selectSuggestion(s) {
  if (s.filterType && s.filterValue) {
    const exists = activeFilters.value.find(f => f.type === s.filterType && f.value === s.filterValue)
    if (!exists) {
      activeFilters.value.push({ type: s.filterType, value: s.filterValue, label: s.filterLabel || s.filterValue })
    }
  }
  filterInput.value = ''
}
function hideSuggestions() { setTimeout(() => { showSuggestions.value = false }, 150) }

// ── Location tree ───────────────────────────────────
const {
  locationTree, expandedNodes,
  fetchLocationTree, toggleTreeNode, flatTree, findAncestorIds,
} = useLocationTree({ filteredEntities, activeFilters })

// ── Entity selection ────────────────────────────────
function toggleEntity(e) {
  if (editing.value && selectedId.value === e.id) {
    editing.value = false; selected.value = null; selectedId.value = null
    panel.closeChild()
  } else {
    onSelectEntity(e)
  }
}
function onSelectUniverse(id) { toggleEntity({ id }) }
function onSelectLocation(id) { toggleEntity({ id }) }
function onSelectOccupant(e) { toggleEntity(e) }

async function onSelectEntity(e) {
  const alreadyEditing = await selectEntity(e)
  if (!alreadyEditing) openEntityEdit()
}

// ── Panel opening ───────────────────────────────────
function openEntityEdit() {
  if (!panel.open || !selected.value) return
  creating.value = false
  panel.open({
    component: GmEntityEditPanel,
    title: selected.value.name || 'Edit Entity',
    props: { entityId: selectedId.value },
    listeners: {
      'switch-to-sheet': switchToSheet,
      'image-open': onImageOpen,
    },
  })
}

function switchToSheet() {
  if (!panel.open || !selected.value) return
  editing.value = false
  panel.open({
    component: CharacterSheet,
    title: selected.value.name || 'Character Sheet',
    props: { entityId: selected.value.id, universe: props.universe, embedded: true, gmMode: true },
  })
}

function inspectEntity(id) {
  editing.value = false; creating.value = false; selected.value = null; selectedId.value = null
  panel.open({
    component: CharacterSheet,
    title: 'Character Sheet',
    props: { entityId: id, universe: props.universe, embedded: true, gmMode: true },
  })
}

function startCreate() {
  creating.value = true; editing.value = false; selected.value = null
  panel.open({
    component: GmEntityCreatePanel,
    title: 'New Entity',
    props: { defaultUniverse: props.universe, defaultLocationId: props.currentLocationId, locationTree: locationTree.value, saving: saving.value, entityTypes: ['CHARACTER', 'LOCATION', 'GMC', 'FACTION', 'ASSET'] },
    listeners: { 'create': createEntity },
  })
}

async function openTraitsConfig() {
  editing.value = false; creating.value = false; selected.value = null; selectedId.value = null
  if (traitsets.value.length === 0 || allSfxs.value.length === 0) await fetchTraitsConfig()
  panel.open({
    component: GmTraitsetsPanel,
    title: 'Traitsets',
    props: {},
  })
}

function onImageOpen(img) {
  panel.open({
    component: ImageViewer,
    title: img.id,
    props: { src: img.path_animated || img.path_large, animatedSrc: img.path_animated, alt: img.image_type + ' — ' + img.width + '×' + img.height, entityId: selectedId.value, imageId: img.id, imageType: img.image_type, roles: img.roles || [], sizeBytes: img.size_bytes },
    listeners: {},
  })
}

// ── Drag-drop move ──────────────────────────────────
async function onMoveEntity({ entityId, entityKind, targetId, targetKind, targetUniverse }) {
  if (entityKind === 'occupant') {
    await graphql(`mutation($input: UpdateEntityInput!) { updateEntity(input: $input) { id currentLocation } }`, { input: { id: entityId, currentLocation: targetId } })
  } else if (entityKind === 'location') {
    if (targetUniverse) {
      try { await graphql(`mutation($input: UpdateEntityInput!) { updateEntity(input: $input) { id currentUniverse } }`, { input: { id: entityId, currentUniverse: targetUniverse } }) } catch {}
    }
    try {
      const r = await fetch(`/api/v1/locations/${entityId}/navigate`)
      const nav = await r.json()
      const oldParentId = nav.parent?._key || null
      if (targetKind === 'universe') {
        if (oldParentId) {
          await fetch(`/api/v1/locations/${entityId}/edges/${oldParentId}?type=super`, { method: 'DELETE' })
        }
      } else if (targetKind === 'location' && targetId !== oldParentId) {
        if (oldParentId) {
          await fetch(`/api/v1/locations/${entityId}/edges/${oldParentId}?type=super`, { method: 'DELETE' })
        }
        await fetch(`/api/v1/locations/${entityId}/edges/${targetId}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ type: 'super' }),
        })
      }
    } catch {}
    await fetchLocationTree()
  }
  fetchEntities()
}

// ── Auto-expand current location ────────────────────
watch([locationTree, () => props.currentLocationId], () => {
  const path = []
  if (props.currentLocationId && findAncestorIds(locationTree.value, props.currentLocationId, path)) {
    const next = { ...expandedNodes.value }
    for (const id of path) next[id] = true
    expandedNodes.value = next
  }
})

// ── Lifecycle ───────────────────────────────────────
onMounted(() => { fetchEntities(); fetchLocationTree(); startJobPolling() })
onUnmounted(() => { stopJobPolling() })
</script>

<style scoped>


.mode-tabs { display: flex; gap: 0; margin-bottom: 10px; border-radius: 6px; overflow: hidden; border: 1px solid rgba(255,255,255,0.08); }
.mode-tabs button { flex: 1; font-size: 12px; padding: 6px 0; border: none; background: rgba(255,255,255,0.04); color: var(--text-dim); cursor: pointer; transition: all 0.15s; }
.mode-tabs button.active { background: var(--accent); color: #fff; }
.mode-tabs button:hover:not(.active) { background: rgba(255,255,255,0.08); }

.gm-shortcuts { display: flex; gap: 4px; flex-wrap: wrap; margin-bottom: 8px; }
.shortcut-btn { flex: 1; font-size: 11px; padding: 8px 6px; border-radius: 6px; border: 1px solid rgba(255,255,255,0.08); background: rgba(255,255,255,0.04); color: var(--text-dim); cursor: pointer; transition: all 0.2s; white-space: nowrap; }
.shortcut-btn:hover { background: rgba(255,255,255,0.08); color: var(--text); }
.beat-btn { border-color: rgba(64,136,212,0.3); } .beat-btn:hover { border-color: var(--accent); background: rgba(64,136,212,0.12); }
.scene-btn { border-color: rgba(64,184,96,0.3); } .scene-btn:hover { border-color: #40b860; background: rgba(64,184,96,0.12); }
.session-btn { border-color: rgba(232,136,48,0.3); } .session-btn:hover { border-color: #e88830; background: rgba(232,136,48,0.12); }
.session-btn.active { border-color: #d44040; color: #d44040; } .session-btn.active:hover { background: rgba(212,64,64,0.12); }

.filter-bar { margin-bottom: 8px; }
.chip-bar { display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 4px; }
.filter-chip { display: flex; align-items: center; gap: 2px; font-size: 11px; padding: 3px 8px; background: rgba(64,136,212,0.15); border: 1px solid var(--accent-dim); border-radius: 10px; color: var(--text); }
.chip-label { max-width: 140px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.chip-remove { font-size: 14px; padding: 0 2px; background: none; border: none; color: var(--text-dim); cursor: pointer; line-height: 1; }
.chip-remove:hover { color: var(--danger); }
.suggestion-hint { font-size: 9px; color: var(--text-dim); text-transform: uppercase; margin-left: auto; }
.filter-input-wrap { position: relative; }
.filter-input { width: 100%; font-size: 12px; padding: 6px 28px 6px 8px; box-sizing: border-box; }
.filter-clear-inline { position: absolute; right: 4px; top: 50%; transform: translateY(-50%); font-size: 12px; padding: 2px 6px; background: none; color: var(--text-dim); border: none; cursor: pointer; }
.filter-clear-inline:hover { color: var(--text); }
.filter-suggestions { position: absolute; top: 100%; left: 0; right: 0; z-index: 30; background: var(--bg-panel); backdrop-filter: blur(12px); border: 1px solid rgba(255,255,255,0.1); border-radius: 0 0 6px 6px; max-height: 200px; overflow-y: auto; }
.suggestion-row { display: flex; align-items: center; gap: 6px; padding: 6px 10px; font-size: 12px; cursor: pointer; }
.suggestion-row:hover { background: rgba(255,255,255,0.06); }

.create-btn { width: 100%; font-size: 12px; padding: 8px; margin-bottom: 8px; background: var(--accent-dim); color: var(--text); }
.create-btn:hover { background: var(--accent); }

.entity-row { display: flex; align-items: center; gap: 6px; padding: 8px 10px; margin-bottom: 4px; background: rgba(255,255,255,0.04); border-radius: 6px; cursor: pointer; transition: background 0.15s; font-size: 13px; }
.entity-row:hover { background: rgba(255,255,255,0.08); }
.entity-row.selected { background: rgba(64,136,212,0.15); border: 1px solid var(--accent-dim); }
.entity-type-badge { font-size: 9px; text-transform: uppercase; padding: 1px 6px; border-radius: 3px; font-weight: 600; }
.type-character, .type-pc { background: #4088d4; color: #fff; }
.type-location { background: #40b860; color: #0a0a0f; }
.type-gmc { background: #e88830; color: #0a0a0f; }
.type-faction { background: #d44040; color: #fff; }
.type-asset { background: #888; color: #fff; }
.type-CHARACTER, .type-PC { background: #4088d4; color: #fff; }
.type-LOCATION { background: #40b860; color: #0a0a0f; }
.type-GMC { background: #e88830; color: #0a0a0f; }
.type-FACTION { background: #d44040; color: #fff; }
.type-ASSET { background: #888; color: #fff; }
.entity-name { flex: 1; font-weight: 500; }
.entity-universe { font-size: 10px; color: var(--text-dim); }
.factions-heading { font-size: 11px; color: var(--text-dim); text-transform: uppercase; letter-spacing: 1px; margin-top: 12px; padding-top: 8px; border-top: 1px solid rgba(255,255,255,0.08); }

.form-actions { display: flex; gap: 6px; }
.top-actions { justify-content: space-between; margin-bottom: 4px; }
.danger-btn { background: var(--danger) !important; color: #fff !important; }
.sheet-edit-btn { background: var(--accent); color: #fff; }
.save-btn { background: var(--success) !important; color: #0a0a0f !important; font-weight: 600; margin-top: 4px; }
.panel-body label { font-size: 11px; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.5px; display: block; margin-top: 8px; }
.panel-body input, .panel-body select { font-size: 13px; padding: 6px 10px; width: 100%; box-sizing: border-box; }

.loading, .error, .empty { font-size: 12px; color: var(--text-dim); padding: 12px 0; text-align: center; }
.error { color: var(--danger); }
</style>
