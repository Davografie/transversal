<template>
  <div class="gm-content">
    <div class="mode-tabs">
      <button :class="{ active: mode === 'play' }" @click="mode = 'play'">Play</button>
      <button :class="{ active: mode === 'prep' }" @click="mode = 'prep'">Prep</button>
    </div>

    <template v-if="mode === 'play'">
      <div class="gm-shortcuts">
        <button class="shortcut-btn beat-btn" @click="nextBeat">◆ Next Beat</button>
        <button class="shortcut-btn scene-btn" @click="advanceScene">◈ Scene</button>
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
      <div class="canvas-btn-row">
        <button class="create-btn canvas-btn" @click="openLocationTreeCanvas">🗺 Canvas</button>
      </div>
      <button class="create-btn" @click="openTraitsConfig">Manage Traits</button>
      <button class="create-btn" @click="openSfxOwners">Manage SFX Owners</button>
      <GmLocationTree :flat-tree="flatTree" :expanded-ids="expandedNodes" :selected-id="selectedId" :rejected-id="rejectedUniverseId" @select-universe="onSelectUniverse" @select-location="onSelectLocation" @select-occupant="onSelectOccupant" @toggle-expand="toggleTreeNode" @move-entity="onMoveEntity" />
      <h4 v-if="filteredFactions.length" class="factions-heading">Factions</h4>
      <div v-for="e in filteredFactions" :key="e.id" class="entity-row" :class="{ selected: selectedId === e.id }" @click="toggleEntity(e)">
        <span class="entity-type-badge type-FACTION">FAC</span><span class="entity-name">{{ e.name }}</span>
        <span class="entity-universe" v-if="e.currentUniverse !== universe">{{ e.currentUniverse }}</span>
        <button class="faction-canvas-btn" title="Show in canvas" @click.stop="openFullFactionCanvas(e.id)">🗺</button>
      </div>
      <button class="fab-create" @click="startCreate" title="New Entity" aria-label="New Entity">＋</button>
      <div v-if="flatTree.length === 0 && filteredFactions.length === 0" class="empty">No entities found</div>
    </template>
  </div>
</template>

<script setup>
import { ref, toRef, onMounted, onUnmounted, watch } from 'vue'
import { useApi } from '@/composables/useApi.js'
import { useEntityCrud } from '@/composables/useEntityCrud.js'
import { useTraitsConfig } from '@/composables/useTraitsConfig.js'
import { useLocationTree } from '@/composables/useLocationTree.js'
import { useEntityFilter } from '@/composables/useEntityFilter.js'
import { usePanel } from '@/composables/usePanel.js'
import { usePanelBus } from '@/composables/usePanelBus.js'
import CharacterSheet from '@/components/CharacterSheet.vue'
import GmSceneSummary from '@/components/gm/GmSceneSummary.vue'
import GmLocationTree from '@/components/gm/GmLocationTree.vue'
import GmTraitsetsPanel from '@/components/gm/GmTraitsetsPanel.vue'
import GmSfxOwnersPanel from '@/components/gm/GmSfxOwnersPanel.vue'
import GmEntityEditPanel from '@/components/gm/GmEntityEditPanel.vue'
import GmEntityCreatePanel from '@/components/gm/GmEntityCreatePanel.vue'
import ImageViewer from '@/components/gm/ImageViewer.vue'

const { graphql } = useApi()
const panel = usePanel()
const bus = usePanelBus()
let offCanvasInspect = null
let offLocationsChanged = null

const props = defineProps({
  universe: { type: String, default: 'earth' },
  currentLocationId: { type: String, default: '' },
  currentEntityId: { type: String, default: '' },
})

const emit = defineEmits(['next-beat', 'advance-scene', 'start-session', 'end-session', 'add-to-pool'])

// ── Composables ─────────────────────────────────────
const {
  entities, selected, selectedId, editing, creating, saving,
  fetchEntities, selectEntity, createEntity,
  startJobPolling, stopJobPolling,
} = useEntityCrud()

const {
  traitsets, allSfxs,
  fetchTraitsConfig,
} = useTraitsConfig()

// ── Session UI ──────────────────────────────────────
const mode = ref('play')
const viewSceneSummary = ref(true)
const sessionActive = ref(false)

function nextBeat() { emit('next-beat') }
function advanceScene() { viewSceneSummary.value = true; emit('advance-scene') }
function startSession() { sessionActive.value = true; emit('start-session') }
function endSession() { sessionActive.value = false; emit('end-session') }

// ── Filtering (entities) ────────────────────────────
const {
  activeFilters, filterInput, showSuggestions,
  filteredEntities, filteredFactions, sceneEntities,
  suggestions, selectSuggestion, hideSuggestions,
} = useEntityFilter(entities)

// Default the entity filter to the acted character so the tree focuses on
// that character's location path instead of the whole hierarchy.
watch(() => props.currentEntityId, (id) => {
  if (!id) { activeFilters.value = []; return }
  const ent = entities.value.find((e) => e.id === id)
  activeFilters.value = [{ type: 'name', value: id, label: ent?.name || id }]
}, { immediate: true })

// ── Location tree ───────────────────────────────────
const {
  locationTree, expandedNodes,
  fetchLocationTree, toggleTreeNode, flatTree, findAncestorIds,
} = useLocationTree({ filteredEntities, activeFilters, currentUniverse: toRef(props, 'universe') })

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
      'go-to-location': () => bus.emit('switch-view-location', selectedId.value),
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
  // Scene overview click → assume this character (perspective switch), not a sheet peek.
  bus.emit('switch-perspective', id)
}

function startCreate() {
  creating.value = true; editing.value = false; selected.value = null
  panel.open({
    component: GmEntityCreatePanel,
    title: 'New Entity',
    props: { defaultUniverse: props.universe, defaultLocationId: props.currentLocationId, locationTree: locationTree.value, saving: saving.value },
    listeners: { 'create': createEntity },
  })
}

function openLocationTreeCanvas() {
  bus.emit('canvas:open-full', { mode: 'location', entityId: props.universe, scope: 'tree' })
}

function openFullFactionCanvas(factionId) {
  bus.emit('canvas:open-full', { mode: 'faction', entityId: factionId })
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

async function openSfxOwners() {
  editing.value = false; creating.value = false; selected.value = null; selectedId.value = null
  if (allSfxs.value.length === 0) await fetchTraitsConfig()
  panel.open({
    component: GmSfxOwnersPanel,
    title: 'SFX Owners',
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
const rejectedUniverseId = ref(null)

async function onMoveEntity({ entityId, entityKind, targetId, targetKind, targetUniverse }) {
  if (entityKind === 'occupant') {
    const data = await graphql(
      `query($id: ID!) { entity(id: $id) { projections { id originUniverse universe currentLocation } } }`,
      { id: entityId }
    )
    const projections = data?.entity?.projections || []
    const proj = projections.find((p) => p.universe === targetUniverse || p.originUniverse === targetUniverse)

    if (targetKind === 'universe') {
      if (proj) {
        await graphql(
          `mutation($entityId: ID!, $projectionId: ID!) { activateProjection(entityId: $entityId, projectionId: $projectionId) { id } }`,
          { entityId, projectionId: proj.id }
        )
        const next = { ...expandedNodes.value }
        next[targetId] = true
        if (proj.currentLocation) {
          const path = []
          if (findAncestorIds(locationTree.value, proj.currentLocation, path)) {
            for (const id of path) next[id] = true
          }
        }
        expandedNodes.value = next
      } else {
        rejectedUniverseId.value = targetId
        setTimeout(() => { if (rejectedUniverseId.value === targetId) rejectedUniverseId.value = null }, 700)
      }
    } else if (proj) {
      // Location drop with a projection in that universe: assume it and move it.
      await graphql(
        `mutation($entityId: ID!, $projectionId: ID!, $location: ID) { activateProjection(entityId: $entityId, projectionId: $projectionId, location: $location) { id } }`,
        { entityId, projectionId: proj.id, location: targetId }
      )
    } else {
      // No projection in that universe → inapposite: relocate the current projection.
      await graphql(
        `mutation($entityId: ID!, $location: ID!) { inappositeTravel(entityId: $entityId, location: $location) { id } }`,
        { entityId, location: targetId }
      )
    }
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

// ── Lifecycle ───────────────────────────────────────
onMounted(() => {
  fetchEntities(); fetchLocationTree(); startJobPolling()
  offCanvasInspect = bus.on('canvas:inspect', (id) => toggleEntity({ id }))
  offLocationsChanged = bus.on('locations-changed', () => { fetchLocationTree(); fetchEntities() })
})
onUnmounted(() => {
  stopJobPolling()
  if (offCanvasInspect) offCanvasInspect()
  if (offLocationsChanged) offLocationsChanged()
})
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
.canvas-btn { background: rgba(64, 136, 212, 0.3); border: 1px dashed var(--accent-dim); }
.canvas-btn:hover { background: var(--accent); border-color: var(--accent); }
.canvas-btn-row { display: flex; gap: 6px; }
.canvas-btn-row .create-btn { flex: 1; }
.faction-canvas-btn { background: rgba(255,255,255,0.06); border: none; border-radius: 4px; padding: 2px 5px; cursor: pointer; font-size: 12px; }
.faction-canvas-btn:hover { background: var(--accent); }

.fab-create {
  position: sticky; bottom: 16px; z-index: 20;
  display: flex; align-items: center; justify-content: center;
  width: 56px; height: 56px;
  margin-left: auto; margin-top: 12px;
  border-radius: 50%; border: none; cursor: pointer;
  background: var(--accent); color: #0a0a0f;
  font-size: 26px; font-weight: 700; line-height: 1;
  box-shadow: 0 4px 12px rgba(0,0,0,0.4);
}
.fab-create:hover { opacity: 0.9; }

.entity-row { margin-bottom: 4px; }
.factions-heading { font-size: 11px; color: var(--text-dim); text-transform: uppercase; letter-spacing: 1px; margin-top: 12px; padding-top: 8px; border-top: 1px solid rgba(255,255,255,0.08); }

.form-actions { display: flex; gap: 6px; }
.top-actions { justify-content: space-between; margin-bottom: 4px; }
.danger-btn { background: var(--danger) !important; color: #fff !important; }
.sheet-edit-btn { background: var(--accent); color: #fff; }
.save-btn { background: var(--success) !important; color: #0a0a0f !important; font-weight: 600; margin-top: 4px; }
.panel-body label { font-size: 11px; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.5px; display: block; margin-top: 8px; }
.panel-body input, .panel-body select { font-size: 13px; padding: 6px 10px; width: 100%; box-sizing: border-box; }


</style>
