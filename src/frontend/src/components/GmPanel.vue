<template>
  <div class="gm-content">
    <div class="mode-tabs">
      <button :class="{ active: mode === 'play' }" @click="mode = 'play'">Play</button>
      <button :class="{ active: mode === 'prep' }" @click="mode = 'prep'">Prep</button>
    </div>

    <template v-if="mode === 'play'">
      <div class="gm-tab-body">
        <div class="gm-shortcuts">
          <Button class="shortcut-btn beat-btn" variant="neutral" @click="nextBeat">◆ Next Beat</Button>
          <Button class="shortcut-btn scene-btn" variant="neutral" @click="advanceScene">◈ Scene</Button>
          <Button v-if="!inSession" class="shortcut-btn session-btn" variant="neutral" title="Start the session" @click="startSession">▶ Start</Button>
          <Button v-else class="shortcut-btn session-btn" variant="danger" title="End the session" @click="endSession">■ End</Button>
        </div>
        <GmTroupeOverview :current-location-id="currentLocationId" :current-location-name="currentLocationName" @go-to-location="goToLocation" />
        <GmSceneSummary
          v-if="viewSceneSummary"
          :entities="sceneEntitiesHere"
          :parents="sceneParentGroups"
          :zones="sceneZoneGroups"
          @inspect="inspectEntity"
        />
      </div>
    </template>

    <template v-if="mode === 'prep'">
      <!-- Authoring tools first: they open their own child panels and are not
           touched by the focus filter below. -->
      <div class="gm-tools">
        <Button class="create-btn" variant="secondary" block @click="openTraitsConfig">Manage Traits</Button>
        <Button class="create-btn" variant="secondary" block @click="openSfxManager">Manage SFX</Button>
      </div>

      <!-- Focus: shapes what the Places tree and the Factions list show. -->
      <div class="focus-bar">
        <div class="chip-bar">
          <span v-for="(f, i) in activeFilters" :key="i" class="filter-chip">
            <span class="chip-label">{{ f.label }}</span>
            <Button class="chip-remove" variant="ghost" @click="activeFilters.splice(i, 1)">×</Button>
          </span>
        </div>
        <div class="filter-input-wrap">
          <input v-model="filterInput" class="filter-input" placeholder="Filter…" @focus="showSuggestions = true" @blur="hideSuggestions" @keyup.escape="filterInput = ''" />
          <Button v-if="filterInput" class="filter-clear-inline" variant="ghost" @click="filterInput = ''">✕</Button>
          <div v-if="showSuggestions && suggestions.length" class="filter-suggestions">
            <div v-for="s in suggestions" :key="s.id" class="suggestion-row" @mousedown.prevent="selectSuggestion(s)">
              <span class="entity-type-badge" :class="'type-' + (s.entityType || s.type || '')">{{ s.entityType || s.type || '' }}</span><span>{{ s.name }}</span>
              <span class="suggestion-hint">{{ s.hint }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Browse: Places | Factions (both read the focus filter). -->
      <div class="browse-tabs">
        <Button variant="neutral" :active="browseTab === 'tree'" @click="browseTab = 'tree'">Places</Button>
        <Button variant="neutral" :active="browseTab === 'factions'" @click="browseTab = 'factions'">
          Factions<span v-if="filteredFactions.length" class="tab-count">{{ filteredFactions.length }}</span>
        </Button>
      </div>

      <div class="browse-zone">
        <template v-if="browseTab === 'tree'">
          <!-- The breadcrumb bar that used to live here is gone (the human's
               call, B112); its two actions stay. -->
          <div class="tree-actions">
            <Button class="crumb-action" variant="ghost" size="icon" title="Collapse all levels" @click="collapseTree">⌃</Button>
            <Button class="crumb-action" variant="ghost" size="icon" title="Jump to the current location" @click="scrollToNode(props.currentLocationId)">⊙</Button>
          </div>
          <GmLocationTree :flat-tree="flatTree" :expanded-ids="expandedNodes" :selected-id="selectedId" :rejected-id="rejectedUniverseId" @select-universe="onSelectUniverse" @select-location="onSelectLocation" @select-occupant="onSelectOccupant" @toggle-expand="toggleTreeNode" @select-more="expandLevel" @move-entity="onMoveEntity" />
          <div v-if="flatTree.length === 0" class="empty">No entities found</div>
        </template>
        <template v-else>
          <GmList
            v-if="filteredFactions.length"
            :items="filteredFactions"
            item-key="id"
            :selected-ids="selectedId ? [selectedId] : []"
            @click="toggleEntity"
          >
            <template #item="{ item: e }">
              <span class="entity-type-badge type-FACTION">FAC</span><span class="entity-name">{{ e.name }}</span>
              <span class="entity-universe" v-if="e.currentUniverse !== universe">{{ e.currentUniverse }}</span>
              <Button class="faction-canvas-btn" variant="ghost" size="sm" title="Show in canvas" @click.stop="openFullFactionCanvas(e.id)">🗺</Button>
            </template>
          </GmList>
          <div v-else class="empty">No factions match the focus</div>
        </template>
      </div>

      <div class="gm-footer">
        <Button class="canvas-btn" variant="secondary" block @click="openLocationTreeCanvas">🗺 Canvas</Button>
      </div>

      <Button class="fab-create" variant="primary" size="icon" @click="startCreate" title="New Entity" aria-label="New Entity">＋</Button>
    </template>
  </div>
</template>

<script setup>
import { ref, toRef, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { useApi } from '@/composables/useApi.js'
import { useEntityCrud } from '@/composables/useEntityCrud.js'
import Button from '@/components/ui/Button.vue'
import { useTraitsConfig } from '@/composables/useTraitsConfig.js'
import { useLocationTree } from '@/composables/useLocationTree.js'
import { useEntityFilter } from '@/composables/useEntityFilter.js'
import { usePanel } from '@/composables/usePanel.js'
import { usePanelBus } from '@/composables/usePanelBus.js'
import CharacterSheet from '@/components/CharacterSheet.vue'
import GmSceneSummary from '@/components/gm/GmSceneSummary.vue'
import GmTroupeOverview from '@/components/gm/GmTroupeOverview.vue'
import GmLocationTree from '@/components/gm/GmLocationTree.vue'
import GmList from '@/components/ui/GmList.vue'
import GmTraitsetsPanel from '@/components/gm/GmTraitsetsPanel.vue'
import GmSfxManagementPanel from '@/components/gm/GmSfxManagementPanel.vue'
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
  currentLocationName: { type: String, default: '' },
  entityId: { type: String, default: '' },
  inSession: { type: Boolean, default: false },
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
// The session's in_session flag is owned by App.vue (session join + the
// session_started/session_ended SSE broadcasts) so this button reflects the
// real state — e.g. after a refresh or when another device toggles it.
const mode = ref('play')
const viewSceneSummary = ref(true)
// Prep's browsing surface: the Places tree or the Factions list (both read the
// focus filter above them).
const browseTab = ref('tree')

function nextBeat() { emit('next-beat') }
function advanceScene() { viewSceneSummary.value = true; emit('advance-scene') }
function startSession() { emit('start-session') }
function endSession() { emit('end-session') }

// ── Filtering (entities) ────────────────────────────
const {
  activeFilters, filterInput, showSuggestions,
  filteredEntities, filteredFactions,
  suggestions, selectSuggestion, hideSuggestions,
} = useEntityFilter(entities)

// Default the entity filter to the acted character so the tree focuses on
// that character's location path instead of the whole hierarchy.
watch(() => props.entityId, (id) => {
  if (!id) { activeFilters.value = []; return }
  const ent = entities.value.find((e) => e.id === id)
  activeFilters.value = [{ type: 'name', value: id, label: ent?.name || id }]
}, { immediate: true })

// ── Location tree ───────────────────────────────────
const {
  locationTree, expandedNodes,
  fetchLocationTree, toggleTreeNode, flatTree, findAncestorIds,
  focusPath, setFocus, collapseAll,
} = useLocationTree({ filteredEntities, activeFilters, currentUniverse: toRef(props, 'universe') })

// ── Free-roam drill-down ────────────────────────────
// With no acting entity there is no name filter focusing the tree, so expand
// the path from its universe root down to the GM's current location (and bring
// the row into view) whenever the location or the acting entity changes.
function expandPathTo(locationId) {
  if (!locationId || !locationTree.value.length) return false
  const path = []
  if (!findAncestorIds(locationTree.value, locationId, path)) return false
  const next = { ...expandedNodes.value }
  let changed = false
  for (const id of path) {
    if (!next[id]) { next[id] = true; changed = true }
  }
  if (changed) expandedNodes.value = next
  return true
}

function scrollLocationIntoView(locationId) {
  nextTick(() => {
    // 'center' keeps the ancestor chain visible above the location, instead of
    // parking the row flush against the panel's bottom edge ('nearest').
    document
      .querySelector(`.gm-content [data-node-id="${locationId}"]`)
      ?.scrollIntoView({ block: 'center', behavior: 'smooth' })
  })
}

// Reveal a focused level's hidden siblings (the "… N more" stub).
function expandLevel(parentId) {
  expandedNodes.value = { ...expandedNodes.value, [parentId]: true }
}

function collapseTree() {
  collapseAll()
}

// Locate: make sure the target is on screen (and its level open).
function scrollToNode(nodeId) {
  if (!nodeId) return
  const expanded = { ...expandedNodes.value }
  const path = []
  if (findAncestorIds(locationTree.value, nodeId, path)) {
    // Open the whole chain down to the target. Without this the jump was a
    // silent no-op in the plain view — only the current universe renders open
    // by default there, so the target row did not exist and the scroll found
    // nothing (the acting-entity case, once its filter chip is removed).
    path.filter((id) => id !== nodeId).forEach((id) => { expanded[id] = true })
    expandedNodes.value = expanded
  }
  scrollLocationIntoView(nodeId)
}

watch(
  [() => props.entityId, () => props.currentLocationId, locationTree],
  ([entityId, locationId]) => {
    // An acting entity means the tree is driven by the name-filter chip; no
    // focus chain. Free-roam: focus the GM's current location (the chain
    // expands by default in focus mode, so there is nothing to expand here).
    if (entityId || !locationId) { setFocus(''); return }
    setFocus(locationId)
    nextTick(() => {
      if (!focusPath.value.length) return  // location is not in the tree
      scrollLocationIntoView(locationId)
    })
  },
  { immediate: true },
)

// The panel opens on Play, where the tree isn't rendered — the drill above can
// run before its rows exist. Re-scroll when the GM switches to Prep.
watch(() => mode.value, (m) => {
  if (m !== 'prep' || props.entityId || !props.currentLocationId) return
  scrollLocationIntoView(props.currentLocationId)
})

// The scene's pool: every occupant type, assets included, and deliberately
// **unfiltered** — the focus chips belong to Prep. The Play screen shows the
// scene as it is; the GM's own acting-entity chip must not narrow it to them.
const SCENE_TYPE_PRIORITY = { CHARACTER: 0, GMC: 1, ASSET: 2 }
const sceneOccupants = computed(() =>
  entities.value.filter((e) => e.type in SCENE_TYPE_PRIORITY)
)

// Scene scope: the current location only — its parents and zones are drawers in
// the summary, not part of the roster (the human's call).
const sceneEntitiesHere = computed(() =>
  sceneOccupants.value.filter((e) => e.currentLocation === props.currentLocationId)
)

function _findTreeNode(nodes, id) {
  for (const n of nodes) {
    if (n.id === id) return n
    const hit = _findTreeNode(n.children || [], id)
    if (hit) return hit
  }
  return null
}

function _sceneEntitiesAt(locationId) {
  return sceneOccupants.value.filter((e) => e.currentLocation === locationId)
}

function _placeName(id) {
  return entities.value.find((e) => e.id === id)?.name || id
}

// Parents: the ancestor chain, nearest first (the universe is the last step).
const sceneParentGroups = computed(() => {
  const path = []
  if (!findAncestorIds(locationTree.value, props.currentLocationId, path)) return []
  return path
    .filter((id) => id !== props.currentLocationId)
    .reverse()
    .map((id) => ({ id, name: _placeName(id), entities: _sceneEntitiesAt(id) }))
})

// Zones: the current location's sub-locations, in tree order.
const sceneZoneGroups = computed(() => {
  const node = _findTreeNode(locationTree.value, props.currentLocationId)
  return (node?.children || []).map((c) => ({ id: c.id, name: c.name, entities: _sceneEntitiesAt(c.id) }))
})

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
    id: selectedId.value,
    badge: selected.value.type,
    props: { entityId: selectedId.value, currentEntityId: props.entityId, currentLocationId: props.currentLocationId },
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

function goToLocation(locId) {
  // Troupe row click → move the GM's view to that location without assuming
  // the character (perspective stays put).
  if (!locId) return
  bus.emit('switch-view-location', locId)
}

function startCreate() {
  creating.value = true; editing.value = false; selected.value = null
  panel.open({
    component: GmEntityCreatePanel,
    title: 'New Entity',
    props: { defaultUniverse: props.universe, defaultLocationId: props.currentLocationId, locationTree: locationTree.value },
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

async function openSfxManager() {
  editing.value = false; creating.value = false; selected.value = null; selectedId.value = null
  if (allSfxs.value.length === 0) await fetchTraitsConfig()
  panel.open({
    component: GmSfxManagementPanel,
    title: 'Manage SFX',
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
  // A location dropped on itself — or anywhere inside its own subtree — would
  // re-parent it to itself and detach the whole branch from the root (the
  // limbo Yinling Creek fell into). Flash the target instead of moving.
  if (entityKind === 'location' && targetKind === 'location') {
    const chain = []
    if (findAncestorIds(locationTree.value, targetId, chain) && chain.includes(entityId)) {
      rejectedUniverseId.value = targetId
      setTimeout(() => { if (rejectedUniverseId.value === targetId) rejectedUniverseId.value = null }, 700)
      return
    }
  }
  if (entityKind === 'occupant') {
    const data = await graphql(
      `query($id: ID!) { entity(id: $id) { currentProjection projections { id originUniverse universe currentLocation } } }`,
      { id: entityId }
    )
    const projections = data?.entity?.projections || []
    // Last used wins: the active projection is the most recently touched body,
    // so it beats an arbitrary first match (same rule as Import to Location).
    const inUniverse = projections.filter((p) => p.universe === targetUniverse || p.originUniverse === targetUniverse)
    const proj = inUniverse.find((p) => p.id === data?.entity?.currentProjection) || inUniverse[0] || null

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
    // The entity list carries currentLocation, and the scene roster reads it —
    // without this a placement left it stale until some unrelated refetch.
    await fetchEntities()
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


.gm-content {
  position: relative;
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
/* The Play tab scrolls as one block; Prep pins its chrome and scrolls only the
   browsing zone (see .browse-zone) so the focus bar stays visible. */
/* ── Panel zones ─────────────────────────────────
   Pinned chrome rows never shrink (they are the panel's controls); only the
   scrolling zones flex. Without this the Play|Prep row — the one item whose
   `overflow: hidden` lets it shrink past its content — absorbs any margin
   overflow and collapses to a sliver. */
.gm-content > .mode-tabs,
.gm-content > .gm-tools,
.gm-content > .focus-bar,
.gm-content > .browse-tabs,
.gm-content > .gm-footer { flex: 0 0 auto; }
.gm-tab-body { flex: 1 1 auto; min-height: 0; overflow-y: auto; }
.gm-tools { display: flex; gap: 6px; margin-bottom: 8px; }
.gm-tools .create-btn { flex: 1; margin-bottom: 0; }

.browse-tabs { display: flex; gap: 4px; margin-bottom: 6px; }
.tab-count {
  margin-left: 5px; font-size: 9px; padding: 0 5px; border-radius: 8px;
  background: var(--overlay-12); color: var(--text-dim);
}
.browse-zone { flex: 1 1 auto; min-height: 0; overflow-y: auto; }

/* Tree actions, right-aligned above the tree. The sticky breadcrumb bar that
   used to carry them (a way up after scrolling) is gone by the human's call —
   the jump-to-current-location button is what they kept. */
.tree-actions { display: flex; align-items: center; justify-content: flex-end; gap: 4px; padding: 0 0 4px; }

.gm-footer { padding-top: 8px; }
.gm-footer .canvas-btn { margin-bottom: 0; }

.mode-tabs { display: flex; gap: 0; margin-bottom: 10px; border-radius: 6px; overflow: hidden; border: 1px solid var(--overlay-8); }
.mode-tabs button { flex: 1; font-size: 12px; line-height: 1.4; padding: 7px 0; border: none; background: var(--overlay-4); color: var(--text-dim); cursor: pointer; transition: all 0.15s; }
.mode-tabs button.active { background: var(--accent); color: var(--text-on-accent); }
.mode-tabs button:hover:not(.active) { background: var(--overlay-8); }

.gm-shortcuts { display: flex; gap: 4px; flex-wrap: wrap; margin-bottom: 8px; }
.gm-shortcuts .shortcut-btn { flex: 1; padding: 8px 6px; font-size: 11px; white-space: nowrap; }
/* Per-action border hues (the primitive owns fill/hover/radius). */
.gm-shortcuts .beat-btn { border-color: var(--accent-32); }
.gm-shortcuts .beat-btn:hover { border-color: var(--accent); }
.gm-shortcuts .scene-btn { border-color: var(--success-32); }
.gm-shortcuts .scene-btn:hover { border-color: var(--success); }
.gm-shortcuts .session-btn { border-color: var(--warn-32); }
.gm-shortcuts .session-btn:hover { border-color: var(--warn); }

.focus-bar { margin-bottom: 8px; }.chip-bar { display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 4px; }
.filter-chip { display: flex; align-items: center; gap: 2px; font-size: 11px; padding: 3px 8px; background: var(--accent-16); border: 1px solid var(--accent-dim); border-radius: 10px; color: var(--text); }
.chip-label { max-width: 140px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.filter-chip .chip-remove { font-size: 14px; padding: 0 2px; line-height: 1; }
.suggestion-hint { font-size: 9px; color: var(--text-dim); text-transform: uppercase; margin-left: auto; }
.filter-input-wrap { position: relative; }
.filter-input { width: 100%; font-size: 12px; padding: 6px 28px 6px 8px; box-sizing: border-box; }
.filter-input-wrap .filter-clear-inline { position: absolute; right: 4px; top: 50%; transform: translateY(-50%); padding: 2px 6px; }
.filter-suggestions { position: absolute; top: 100%; left: 0; right: 0; z-index: 30; background: var(--bg-panel); backdrop-filter: blur(12px); border: 1px solid var(--overlay-10); border-radius: 0 0 6px 6px; max-height: 200px; overflow-y: auto; }
.suggestion-row { display: flex; align-items: center; gap: 6px; padding: 6px 10px; font-size: 12px; cursor: pointer; }
.suggestion-row:hover { background: var(--overlay-6); }

.gm-content .create-btn { padding: 8px; margin-bottom: 8px; }
.gm-content .canvas-btn { border: 1px dashed var(--accent-dim); }

.draft-badge {
  flex: 0 0 auto; font-size: 9px; text-transform: uppercase; letter-spacing: 0.5px;
  padding: 1px 5px; border-radius: 3px; color: var(--accent-pale);
  background: var(--accent-16); border: 1px solid var(--accent-45);
  margin-left: 6px;
}

.gm-content .fab-create {
  position: absolute; right: 12px; bottom: 62px; z-index: 20;
  width: 56px; height: 56px;
  border-radius: 50%;
  font-size: 26px; font-weight: 700; line-height: 1;
  box-shadow: 0 4px 12px rgba(0,0,0,0.4);
}

.entity-row { margin-bottom: 4px; }

.form-actions { display: flex; gap: 6px; }
.top-actions { justify-content: space-between; margin-bottom: 4px; }
.danger-btn { background: var(--danger) !important; color: var(--text-on-accent) !important; }
.sheet-edit-btn { background: var(--accent); color: var(--text-on-accent); }
.save-btn { background: var(--success) !important; color: var(--text-invert) !important; font-weight: 600; margin-top: 4px; }
.panel-body label { font-size: 11px; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.5px; display: block; margin-top: 8px; }
.panel-body input, .panel-body select { font-size: 13px; padding: 6px 10px; width: 100%; box-sizing: border-box; }


</style>
