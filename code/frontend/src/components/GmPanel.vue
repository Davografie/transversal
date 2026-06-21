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
      <GmLocationTree :flat-tree="flatTree" :expanded-ids="expandedNodes" :selected-id="selectedId" :universe="universe" @select-location="onSelectLocation" @select-occupant="onSelectOccupant" @toggle-expand="toggleTreeNode" @move-entity="onMoveEntity" />
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
import { ref, computed, onMounted, watch, nextTick } from 'vue'
import { useApi } from '@/composables/useApi.js'
import CharacterSheet from '@/components/CharacterSheet.vue'
import GmSceneSummary from '@/components/gm/GmSceneSummary.vue'
import GmLocationTree from '@/components/gm/GmLocationTree.vue'
import GmTraitsetsPanel from '@/components/gm/GmTraitsetsPanel.vue'
import GmEntityEditPanel from '@/components/gm/GmEntityEditPanel.vue'
import GmEntityCreatePanel from '@/components/gm/GmEntityCreatePanel.vue'

const { error, graphql } = useApi()
const loading = ref(false)

const props = defineProps({
  universe: { type: String, default: 'earth' },
  currentLocationId: { type: String, default: '' },
  open: { type: Function, default: null },
})

const emit = defineEmits(['next-beat', 'start-session', 'end-session', 'add-to-pool'])

const mode = ref('play')
const viewSceneSummary = ref(true)
const sessionActive = ref(false)

const filterLocationId = ref('')
const activeFilters = ref([])
const filterInput = ref('')
const showSuggestions = ref(false)
const locationTree = ref([])
const expandedNodes = ref({})

const entities = ref([])
const selected = ref(null)
const selectedId = ref(null)
const editing = ref(false)
const creating = ref(false)
const saving = ref(false)
const addingTrait = ref(false)
const inspectedEntity = ref(null)

const traitsets = ref([])
const allSfxsData = ref([])
const traitsLoading = ref(false)

// Reactive computed — passed as ref through props so sub-panels see updates
const filteredTraitsets = computed(() => traitsets.value.filter(ts => traitsetMatchesFilters(ts)))

function nextBeat() { emit('next-beat') }
function startSession() { sessionActive.value = true; emit('start-session') }
function endSession() { sessionActive.value = false; emit('end-session') }

// ── Filter helpers ──────────────────────────────────
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

// ── Autocomplete ────────────────────────────────────
const suggestions = computed(() => {
  const q = filterInput.value.trim().toLowerCase()
  if (!q) return []
  const results = []
  const seen = new Set()
  // Universe suggestions
  for (const u of universes.value) {
    if ((u.key && fuzzyMatch(u.key, q)) || (u.name && fuzzyMatch(u.name, q))) {
      if (!seen.has('uni:' + u.key)) {
        seen.add('uni:' + u.key)
        results.push({ id: 'uni:' + u.key, name: u.name || u.key, entityType: 'UNIVERSE', hint: 'universe', filterType: 'universe', filterValue: u.key, filterLabel: u.name || u.key })
      }
    }
  }
  // Entity type suggestions
  const types = ['CHARACTER', 'LOCATION', 'GMC', 'FACTION', 'ASSET']
  for (const t of types) {
    if (fuzzyMatch(t, q)) {
      results.push({ id: 'type:' + t, name: t.charAt(0) + t.slice(1).toLowerCase(), entityType: t, hint: 'type', filterType: 'entityType', filterValue: t, filterLabel: t.charAt(0) + t.slice(1).toLowerCase() })
    }
  }
  // Entity name suggestions (filtered by active filters)
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
    // Don't add duplicate filters
    const exists = activeFilters.value.find(f => f.type === s.filterType && f.value === s.filterValue)
    if (!exists) {
      activeFilters.value.push({ type: s.filterType, value: s.filterValue, label: s.filterLabel || s.filterValue })
    }
  }
  filterInput.value = ''
}
function hideSuggestions() { setTimeout(() => { showSuggestions.value = false }, 150) }

// ── Filtered data ──────────────────────────────────
const filteredEntities = computed(() => entities.value.filter(entityMatchesFilters))
const filteredFactions = computed(() => filteredEntities.value.filter(e => e.type === 'FACTION'))
const sceneEntities = computed(() => filteredEntities.value.filter(e => e.type === 'CHARACTER' || e.type === 'GMC'))
const locationEntities = computed(() => filteredEntities.value.filter(e => e.type === 'LOCATION'))
const universes = computed(() => entities.value.filter(e => e.type === 'UNIVERSE').map(u => ({ key: u.currentUniverse, name: u.name })))

// ── Forms ──────────────────────────────────────────
const form = ref({})
const parentId = ref(null)
const createForm = ref({ name: '', type: 'CHARACTER', universe: props.universe, location: '', razmerit: 0 })
const availableTraits = ref([])

// ── API ────────────────────────────────────────────
const ALL_ENTITIES = `query($type: EntityType) { entities(type: $type) { id type name razmerit currentUniverse currentLocation hidden backgroundImage traitSettings { id name dieType rating ratingType statement ego sfxIds traitsetName universe } } }`
const ENTITY_QUERY = `query($id: ID!) { entity(id: $id) { id type name razmerit currentUniverse currentLocation hidden backgroundImage traitSettings { id name dieType rating ratingType statement ego sfxIds traitsetName universe } } }`

async function fetchEntities() { loading.value = true; const data = await graphql(ALL_ENTITIES, { type: null }); if (data?.entities) entities.value = data.entities; loading.value = false }

async function fetchTraitsConfig() {
  traitsLoading.value = true
  const [ts, sf] = await Promise.all([
    graphql(`query { traitsets { id name universes entityTypes order limit traits { id name defaultDieType traitsetId universes possibleSfxIds } } }`),
    graphql(`query { sfxs { id name description trigger limit effects { polarity timing type action target result } } }`),
  ])
  if (ts?.traitsets) traitsets.value = ts.traitsets
  if (sf?.sfxs) allSfxsData.value = sf.sfxs
  traitsLoading.value = false
}

// ── Entity management ──────────────────────────────
function toggleEntity(e) {
  if (editing.value && selectedId.value === e.id) { editing.value = false; selected.value = null; selectedId.value = null }
  else { selectEntity(e) }
}
function onSelectLocation(id) { toggleEntity({ id }) }
function onSelectOccupant(e) { toggleEntity(e) }

async function selectEntity(e) {
  const alreadyEditing = editing.value && selectedId.value === e.id
  const data = await graphql(ENTITY_QUERY, { id: e.id })
  if (data?.entity) {
    selected.value = data.entity; selectedId.value = e.id; editing.value = true
    form.value = { name: data.entity.name, type: data.entity.type, current_universe: data.entity.currentUniverse, current_location: data.entity.currentLocation || '', razmerit: data.entity.razmerit, background_image: data.entity.backgroundImage || '', overlay: data.entity.overlay || null, hidden: data.entity.hidden }
    parentId.value = null; form.value._originalParentId = null
    if (data.entity.type === 'LOCATION') {
      try {
        const r = await fetch(`/api/v1/locations/${e.id}/navigate`)
        const nav = await r.json()
        parentId.value = nav.parent?._key || null
        form.value._originalParentId = parentId.value
      } catch { parentId.value = null; form.value._originalParentId = null }
    }
    await loadAvailableTraits()
    if (!alreadyEditing) openEntityEdit()
  }
}

function openEntityEdit() {
  if (!props.open || !selected.value) return
  creating.value = false
  props.open({
    component: GmEntityEditPanel,
    title: selected.value.name || 'Edit Entity',
    props: {
      form: form.value,
      universes: universes.value,
      locationEntities: locationEntities.value,
      parentId: parentId.value,
      entityId: selectedId.value,
      traitSettings: selected.value.traitSettings || [],
      availableTraits: availableTraits.value,
      addingTrait: addingTrait.value,
    },
    listeners: {
      'update:form': (v) => { form.value = v },
      'update:parent-id': (v) => { parentId.value = v },
      'upload-bg': uploadBgImage,
      'add-trait': onAddTrait,
      'remove-trait': removeTrait,
      'switch-to-sheet': switchToSheet,
      'delete': deleteSelected,
    },
  })
}
async function saveEntity() {
  saving.value = true
  const result = await graphql(`mutation($input: UpdateEntityInput!) { updateEntity(input: $input) { id name razmerit currentUniverse currentLocation hidden backgroundImage } }`, { input: { id: selected.value.id, name: form.value.name, razmerit: form.value.razmerit, currentUniverse: form.value.current_universe, currentLocation: form.value.current_location || null, hidden: form.value.hidden, backgroundImage: form.value.background_image || null, overlay: form.value.overlay } })
  // Update selected entity directly — don't call selectEntity() which would re-trigger the watcher loop
  if (result?.updateEntity) {
    const ue = result.updateEntity
    if (selected.value) {
      selected.value.name = ue.name
      selected.value.razmerit = ue.razmerit
      selected.value.currentUniverse = ue.currentUniverse
      selected.value.currentLocation = ue.currentLocation
      selected.value.hidden = ue.hidden
      selected.value.backgroundImage = ue.backgroundImage
    }
  }
  if (selected.value && selected.value.type === 'LOCATION') {
    const newParent = parentId.value || null
    const oldParent = form.value._originalParentId
    if (newParent !== oldParent) {
      if (oldParent) { try { await fetch(`/api/v1/locations/${selected.value.id}/edges/${oldParent}?type=super`, { method: 'DELETE' }) } catch {} }
      if (newParent) { try { await fetch(`/api/v1/locations/${selected.value.id}/edges/${newParent}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ type: 'super' }) }) } catch {} }
      form.value._originalParentId = newParent
    }
    await fetchLocationTree()
  }
  saving.value = false
  await fetchEntities()
}
let entitySaveTimer = null
watch([() => form.value, () => parentId.value], () => {
  if (!editing.value || !selected.value) return
  clearTimeout(entitySaveTimer)
  entitySaveTimer = setTimeout(() => saveEntity(), 600)
}, { deep: true })

async function deleteSelected() {
  if (!confirm(`Delete ${selected.value.name}?`)) return
  await graphql(`mutation($id: ID!) { deleteEntity(id: $id) }`, { id: selected.value.id })
  selected.value = null; selectedId.value = null; editing.value = false; await fetchEntities()
}
async function startCreate() {
  creating.value = true; editing.value = false; selected.value = null
  if (props.open) {
    props.open({
      component: GmEntityCreatePanel,
      title: 'New Entity',
      props: { universes: universes.value, locationEntities: locationEntities.value, saving: saving.value },
      listeners: { 'create': createEntity },
    })
  }
}
async function createEntity(formData) {
  const f = formData || createForm.value
  saving.value = true
  await graphql(`mutation($input: CreateEntityInput!) { createEntity(input: $input) { id name type razmerit currentUniverse currentLocation } }`, { input: { name: f.name, type: f.type, universe: f.universe, location: f.location || null, razmerit: f.razmerit || 0 } })
  saving.value = false; creating.value = false; await fetchEntities()
}

function switchToSheet() {
  if (!props.open || !selected.value) return
  editing.value = false
  props.open({
    component: CharacterSheet,
    title: selected.value.name || 'Character Sheet',
    props: { entityId: selected.value.id, universe: props.universe, embedded: true, gmMode: true },
  })
}

// ── Traits ─────────────────────────────────────────
async function loadAvailableTraits() {
  if (!selected.value) return
  const data = await graphql(`query($u: String!) { traitsByUniverse(universe: $u) { id name defaultDieType traitsetId defaultRatingType } }`, { u: selected.value.currentUniverse })
  if (data?.traitsByUniverse) availableTraits.value = data.traitsByUniverse
}
watch(() => selected.value?.currentUniverse, () => { if (selected.value) loadAvailableTraits() })
async function onAddTrait(input) {
  addingTrait.value = true
  await graphql(`mutation($eid: ID!, $input: TraitSettingInput!) { addTraitSetting(entityId: $eid, input: $input) { id } }`, { eid: selected.value.id, input })
  addingTrait.value = false; await selectEntity(selected.value)
}
async function removeTrait(tsId) { await graphql(`mutation($id: ID!) { removeTraitSetting(id: $id) }`, { id: tsId }); await selectEntity(selected.value) }

// ── Drag-drop move ─────────────────────────────────
async function onMoveEntity({ entityId, targetLocationId }) {
  await graphql(`mutation($input: UpdateEntityInput!) { updateEntity(input: $input) { id currentLocation } }`, { input: { id: entityId, currentLocation: targetLocationId } })
  fetchEntities()
}

// ── Image upload ───────────────────────────────────
async function uploadBgImage(e) {
  const file = e.target?.files?.[0]; if (!file) return
  const fd = new FormData(); fd.append('file', file)
  try {
    const r = await fetch(`/api/v1/media/upload?entity_id=${encodeURIComponent(selected.value?.id || '')}`, { method: 'POST', body: fd })
    const data = await r.json()
    if (data.path) { form.value.background_image = data.path; await graphql(`mutation($input: UpdateEntityInput!) { updateEntity(input: $input) { id backgroundImage } }`, { input: { id: selected.value.id, backgroundImage: data.path } }) }
  } catch (err) { error.value = err.message }
}

// ── Location tree ──────────────────────────────────
const TYPE_PRIORITY = { CHARACTER: 0, GMC: 1, ASSET: 2 }
const occupantsByLocation = computed(() => {
  const map = {}
  const src = filteredEntities.value
  for (const e of src) { if ((e.type === 'CHARACTER' || e.type === 'GMC' || e.type === 'ASSET') && e.currentLocation) { if (!map[e.currentLocation]) map[e.currentLocation] = []; map[e.currentLocation].push(e) } }
  for (const key of Object.keys(map)) map[key].sort((a, b) => (TYPE_PRIORITY[a.type] ?? 9) - (TYPE_PRIORITY[b.type] ?? 9))
  return map
})
const filtersActive = computed(() => activeFilters.value.length > 0)
// Prune locations only when an entity-type filter narrows which types to show.
// Universe filters already handled above; name filters should only filter occupants, not locations.
const hasTypeFilter = computed(() => activeFilters.value.some(f => f.type === 'entityType'))
// Auto-expand when any occupant-affecting filter (type or name) is active, so the
// user can see matching entities without manually expanding every node.
const hasOccupantFilter = computed(() => activeFilters.value.some(f => f.type === 'entityType' || f.type === 'name'))
// Set of location IDs that have at least one occupant (direct or descendant)
const populatedLocations = computed(() => {
  const occ = occupantsByLocation.value
  const set = new Set(Object.keys(occ))
  // Walk the location tree and mark ancestors of occupied locations
  function markAncestors(nodes, targetSet) {
    for (const n of nodes) {
      let hasOccupiedDescendant = false
      if (n.children) hasOccupiedDescendant = markAncestors(n.children, targetSet)
      if (targetSet.has(n.id) || hasOccupiedDescendant) {
        set.add(n.id)
        return true
      }
    }
    return false
  }
  markAncestors(locationTree.value, set)
  return set
})
function fuzzyMatch(value, q) {
  if (!value || !q) return false
  const raw = value.toLowerCase()
  const ql = q.toLowerCase()
  if (raw.includes(ql)) return true
  // Normalize underscores → spaces to match user-friendly input
  const normalized = raw.replace(/_/g, ' ')
  if (normalized.includes(ql)) return true
  // Also try the reverse: spaces → underscores in query
  const qNormalized = ql.replace(/ /g, '_')
  if (raw.includes(qNormalized)) return true
  return false
}
// Extract universe keys from active universe filters
const activeUniverseFilters = computed(() => {
  const keys = new Set()
  for (const f of activeFilters.value) {
    if (f.type === 'universe') keys.add(f.value)
  }
  return keys
})

function flattenTree(nodes, occupants, depth = 0) {
  const result = []
  for (const node of nodes) {
    // If universe filters are active, only show locations in those universes
    if (activeUniverseFilters.value.size > 0 && node.universe && !activeUniverseFilters.value.has(node.universe)) continue
    // When occupant-affecting filters are active, prune locations that have no matching occupants
    if (hasOccupantFilter.value && !populatedLocations.value.has(node.id)) continue
    const hasChildren = (node.children && node.children.length > 0) || (occupants[node.id] && occupants[node.id].length > 0)
    let expanded
    if (expandedNodes.value[node.id] !== undefined) {
      expanded = expandedNodes.value[node.id]  // user explicitly toggled
    } else if (hasOccupantFilter.value) {
      expanded = populatedLocations.value.has(node.id)  // auto-expand path to matching occupants
    } else {
      expanded = depth === 0  // default: expand only root level
    }
    result.push({ id: node.id, name: node.name, universe: node.universe, depth, hasChildren, kind: 'location', expanded })
    if (expanded && occupants[node.id]) { for (const e of occupants[node.id]) { result.push({ id: e.id, name: e.name, universe: e.currentUniverse || '', depth: depth + 1, hasChildren: false, kind: 'occupant', entityType: e.type, entity: e }) } }
    if (expanded && node.children && node.children.length) result.push(...flattenTree(node.children, occupants, depth + 1))
  }
  return result
}
const flatTree = computed(() => {
  let roots = locationTree.value
  if (filterLocationId.value) {
    function findNode(nodes) { for (const n of nodes) { if (n.id === filterLocationId.value) return [n]; if (n.children) { const f = findNode(n.children); if (f) return f } } return null }
    roots = findNode(locationTree.value) || []
  }
  return flattenTree(roots, occupantsByLocation.value, 0)
})
function toggleTreeNode(id) { expandedNodes.value = { ...expandedNodes.value, [id]: !expandedNodes.value[id] } }
async function fetchLocationTree() { try { const r = await fetch('/api/v1/locations/tree'); locationTree.value = await r.json() } catch { locationTree.value = [] } }

// ── Inspection ─────────────────────────────────────
function inspectEntity(id) {
  editing.value = false; creating.value = false; selected.value = null; selectedId.value = null
  if (props.open) {
    props.open({
      component: CharacterSheet,
      title: 'Character Sheet',
      props: { entityId: id, universe: props.universe, embedded: true, gmMode: true },
    })
  }
}

// ── Traits config (via open) ───────────────────────
async function openTraitsConfig() {
  editing.value = false; creating.value = false; selected.value = null; selectedId.value = null; inspectedEntity.value = null
  if (traitsets.value.length === 0 || allSfxsData.value.length === 0) await fetchTraitsConfig()
  // Pass raw refs as props so sub-panels see updates reactively
  if (props.open) {
    props.open({
      component: GmTraitsetsPanel,
      title: 'Traitsets',
      props: { traitsets: filteredTraitsets, allSfxs: allSfxsData, loading: traitsLoading, onRefresh: fetchTraitsConfig },
    })
  }
}

// ── Patch helper ──
function patchData(collection, id, changes) {
  let arr
  if (collection === 'traitsets') {
    arr = traitsets
  } else if (collection === 'traits') {
    for (const ts of traitsets.value) {
      const idx = (ts.traits || []).findIndex(t => t.id === id)
      if (idx >= 0) {
        Object.assign(ts.traits[idx], changes)
        ts.traits[idx]._flash = (ts.traits[idx]._flash || 0) + 1
        setTimeout(() => { if (ts.traits[idx]._flash) ts.traits[idx]._flash = 0 }, 600)
        break
      }
    }
    return
  } else if (collection === 'sfxs') {
    arr = allSfxsData
  }
  if (arr) {
    const idx = arr.value.findIndex(item => item.id === id)
    if (idx >= 0) {
      Object.assign(arr.value[idx], changes)
      arr.value[idx]._flash = (arr.value[idx]._flash || 0) + 1
      setTimeout(() => { if (arr.value[idx]._flash) arr.value[idx]._flash = 0 }, 600)
    } else if (changes.id) {
      // New item — push it
      arr.value.push({ ...changes, _flash: 1 })
      setTimeout(() => {
        const newIdx = arr.value.findIndex(item => item.id === id)
        if (newIdx >= 0 && arr.value[newIdx]._flash) arr.value[newIdx]._flash = 0
      }, 600)
    }
  }
}

// ── Lifecycle ──────────────────────────────────────
onMounted(() => { fetchEntities(); fetchLocationTree() })
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
