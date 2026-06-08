<template>
  <button class="gm-toggle" :class="{ 'has-editor': editing || creating || inspectedEntity }" @click="open = !open">
    {{ open ? '×' : '🛠' }}
  </button>


  <div class="gm-panel panel" :class="{ open, 'has-editor': editing || creating || inspectedEntity }">
    <div v-if="open" class="gm-content">
      <div v-if="loading" class="loading">Loading…</div>
      <div v-else-if="error" class="error">{{ error }}</div>

      <template v-else>
        <div class="mode-tabs">
          <button :class="{ active: mode === 'play' }" @click="mode = 'play'">Play</button>
          <button :class="{ active: mode === 'prep' }" @click="mode = 'prep'">Prep</button>
        </div>

        <!-- ===== PLAY MODE ===== -->
        <template v-if="mode === 'play'">
          <div class="gm-shortcuts">
            <button class="shortcut-btn beat-btn" @click="nextBeat">◆ Next Beat</button>
            <button class="shortcut-btn scene-btn" @click="viewSceneSummary = !viewSceneSummary">◈ Scene</button>
            <button v-if="!sessionActive" class="shortcut-btn session-btn" @click="startSession">▶ Start</button>
            <button v-else class="shortcut-btn session-btn active" @click="endSession">■ End</button>
          </div>

          <GmSceneSummary v-if="viewSceneSummary" :entities="sceneEntities" @inspect="inspectEntity" />
        </template>

        <!-- ===== PREP MODE ===== -->
        <template v-if="mode === 'prep'">
          <div class="entities-layout">
            <div class="entity-list-col">
              <div class="filter-bar">
                <div class="filter-input-wrap">
                  <input v-model="filterQuery" class="filter-input" placeholder="Filter…"
                    @focus="showSuggestions = true" @blur="hideSuggestions"
                    @keyup.escape="filterQuery = ''; filterLocationId = ''" />
                  <button v-if="filterQuery" class="filter-clear-inline" @click="filterQuery = ''; filterLocationId = ''">✕</button>
                  <div v-if="showSuggestions && suggestions.length" class="filter-suggestions">
                    <div v-for="s in suggestions" :key="s.id" class="suggestion-row" @mousedown.prevent="selectSuggestion(s)">
                      <span class="entity-type-badge" :class="'type-' + s.type">{{ s.type }}</span>
                      <span>{{ s.name }}</span>
                    </div>
                  </div>
                </div>
              </div>

              <button class="create-btn" @click="startCreate">+ New Entity</button>

              <GmLocationTree
                :flat-tree="flatTree"
                :expanded-ids="expandedNodes"
                :selected-id="selectedId"
                :universe="universe"
                @select-location="onSelectLocation"
                @select-occupant="onSelectOccupant"
                @toggle-expand="toggleTreeNode"
                @move-entity="onMoveEntity"
              />

              <h4 v-if="filteredFactions.length" class="factions-heading">Factions</h4>
              <div v-for="e in filteredFactions" :key="e.id" class="entity-row" :class="{ selected: selectedId === e.id }" @click="toggleEntity(e)">
                <span class="entity-type-badge type-FACTION">FAC</span>
                <span class="entity-name">{{ e.name }}</span>
                <span class="entity-universe" v-if="e.currentUniverse !== universe">{{ e.currentUniverse }}</span>
              </div>

              <button class="create-btn" style="margin-top:8px" @click="configTraits = true">Manage Traits</button>

              <div v-if="flatTree.length === 0 && filteredFactions.length === 0" class="empty">No entities found</div>
            </div>
          </div>
        </template>
      </template>
    </div>
  </div>

  <!-- Unified secondary panels — PanelStack handles all -->
  <PanelStack :panels="secondaryPanels" @close="onSecondaryClose" @select="onTraitConfigSelect" @save="onTraitConfigSave">
    <template #entity v-if="editing || creating || inspectedEntity">
      <template v-if="inspectedEntity && !editing">
        <div class="form-actions top-actions">
          <button class="sheet-edit-btn" @click="switchToEdit">Edit</button>
        </div>
        <CharacterSheet :entity-id="inspectedEntity.id" :universe="universe" embedded :gm-mode="true" @add-to-pool="(d) => emit('add-to-pool', d)" />
      </template>
      <template v-if="editing && selected">
        <div class="form-actions top-actions">
          <button class="sheet-edit-btn" @click="switchToSheet">Sheet</button>
          <button class="danger-btn" @click="deleteSelected">Delete</button>
        </div>
        <GmEntityForm v-model="form" :universes="universes" :location-entities="locationEntities" :allow-type-change="false" @upload-bg="uploadBgImage" />
        <button class="save-btn" @click="saveEntity" :disabled="saving">{{ saving ? 'Saving…' : 'Save' }}</button>
        <TraitEditor :traits="selected.traitSettings" :available-traits="availableTraits" :adding="addingTrait" @add-trait="onAddTrait" @remove-trait="removeTrait" />
      </template>
      <template v-if="creating">
        <label>Name</label><input v-model="createForm.name" autofocus />
        <label>Type</label><select v-model="createForm.type"><option v-for="t in entityTypes" :key="t" :value="t">{{ t }}</option></select>
        <label>Universe</label><select v-model="createForm.universe"><option v-for="u in universes" :key="u.key" :value="u.key">{{ u.name }}</option></select>
        <label>Location</label><select v-model="createForm.location"><option value="">-- None --</option><option v-for="l in filteredLocations" :key="l.id" :value="l.id">{{ l.name }}</option></select>
        <label>Razmerit</label><input v-model.number="createForm.razmerit" type="number" />
        <button class="save-btn" @click="createEntity" :disabled="saving">{{ saving ? 'Creating…' : 'Create' }}</button>
      </template>
    </template>
  </PanelStack>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useApi } from '@/composables/useApi.js'
import CharacterSheet from '@/components/CharacterSheet.vue'
import GmSceneSummary from '@/components/gm/GmSceneSummary.vue'
import GmLocationTree from '@/components/gm/GmLocationTree.vue'
import GmEntityForm from '@/components/gm/GmEntityForm.vue'
import TraitEditor from '@/components/gm/TraitEditor.vue'
import PanelStack from '@/components/gm/PanelStack.vue'
import GmTraitsetsPanel from '@/components/gm/GmTraitsetsPanel.vue'
import GmTraitsPanel from '@/components/gm/GmTraitsPanel.vue'
import GmSfxsPanel from '@/components/gm/GmSfxsPanel.vue'
import GmSfxEditPanel from '@/components/gm/GmSfxEditPanel.vue'

const { error, graphql } = useApi()
const loading = ref(false)

const props = defineProps({
  universe: { type: String, default: 'earth' },
  currentLocationId: { type: String, default: '' },
})

const emit = defineEmits(['next-beat', 'start-session', 'end-session', 'add-to-pool'])

const open = ref(false)
const mode = ref('play')
const viewSceneSummary = ref(true)
const sessionActive = ref(false)
const inspectedEntity = ref(null)

const filterLocationId = ref('')
const filterQuery = ref('')
const showSuggestions = ref(false)

const locationTree = ref([])
const expandedNodes = ref({})

const entityTypes = ['CHARACTER', 'LOCATION', 'GMC', 'FACTION', 'ASSET']

const entities = ref([])
const selected = ref(null)
const selectedId = ref(null)
const editing = ref(false)
const creating = ref(false)
const saving = ref(false)
const addingTrait = ref(false)
const sfxSaving = ref(false)

// ── Traits config state ──
const configTraits = ref(false)
const traitSearch = ref('')
const traitsLoading = ref(false)
const activeTraitset = ref(null)
const activeTraitsetId = ref(null)
const activeTrait = ref(null)
const activeTraitId = ref(null)
const activeSfx = ref(null)
const activeSfxId = ref(null)
const sfxForm = ref({ name: '', trigger: '', description: '' })
const traitsets = ref([])
const allTraitsData = ref([])
const allSfxsData = ref([])

function nextBeat() { emit('next-beat') }
function startSession() { sessionActive.value = true; emit('start-session') }
function endSession() { sessionActive.value = false; emit('end-session') }

// ── Autocomplete ────────────────────────────────────
const suggestions = computed(() => {
  const q = filterQuery.value.trim().toLowerCase()
  if (!q) return []
  return entities.value.filter(e => e.name.toLowerCase().includes(q)).slice(0, 8)
})
function selectSuggestion(s) {
  filterQuery.value = s.name
  filterLocationId.value = s.type === 'LOCATION' ? s.id : ''
  showSuggestions.value = false
}
function hideSuggestions() { setTimeout(() => { showSuggestions.value = false }, 150) }

// ── Filter resolution ──────────────────────────────
const allTreeNodesFlat = computed(() => {
  const r = []
  function walk(n) { for (const x of n) { r.push(x); if (x.children) walk(x.children) } }
  walk(locationTree.value)
  return r
})
const filterLocationIds = computed(() => {
  const ids = new Set(); const lid = filterLocationId.value
  if (!lid) return ids
  function find(n) { for (const x of n) { if (x.id === lid) { collectDescendants(x, ids); return true } if (x.children && find(x.children)) return true } return false }
  find(locationTree.value); return ids
})
function collectDescendants(node, ids) { ids.add(node.id); if (node.children) for (const c of node.children) collectDescendants(c, ids) }

watch([() => props.currentLocationId, allTreeNodesFlat], ([newId, nodes]) => {
  if (newId && nodes.length) {
    const loc = nodes.find(n => n.id === newId)
    if (loc) { filterQuery.value = loc.name; filterLocationId.value = newId }
  }
}, { immediate: true })
watch(filterQuery, (q) => {
  const t = q.trim(); if (!t) { filterLocationId.value = ''; return }
  const m = allTreeNodesFlat.value.find(n => n.name.toLowerCase() === t.toLowerCase())
  filterLocationId.value = m ? m.id : ''
})

// ── Filtered data ──────────────────────────────────
const filteredFactions = computed(() => {
  let list = entities.value.filter(e => e.type === 'FACTION')
  const lid = filterLocationId.value
  if (lid && filterLocationIds.value.size > 0) list = list.filter(e => e.currentLocation && filterLocationIds.value.has(e.currentLocation))
  else if (filterQuery.value.trim()) list = list.filter(e => e.name.toLowerCase().includes(filterQuery.value.trim().toLowerCase()))
  return list
})
const sceneEntities = computed(() => entities.value.filter(e => e.type === 'CHARACTER' || e.type === 'GMC'))
const universes = computed(() => entities.value.filter(e => e.type === 'UNIVERSE').map(u => ({ key: u.currentUniverse, name: u.name })))
const locationEntities = computed(() => entities.value.filter(e => e.type === 'LOCATION'))
const filteredLocations = computed(() => creating.value ? locationEntities.value.filter(l => l.currentUniverse === createForm.value.universe) : locationEntities.value)

// ── Forms ──────────────────────────────────────────
const form = ref({})
const createForm = ref({ name: '', type: 'CHARACTER', universe: 'earth', location: '', razmerit: 0 })
const availableTraits = ref([])

// ── API ────────────────────────────────────────────
const ALL_ENTITIES = `query($type: EntityType) { entities(type: $type) { id type name razmerit currentUniverse currentLocation hidden backgroundImage traitSettings { id name dieType rating ratingType statement ego sfxIds traitsetName universe } } }`
const ENTITY_QUERY = `query($id: ID!) { entity(id: $id) { id type name razmerit currentUniverse currentLocation hidden backgroundImage traitSettings { id name dieType rating ratingType statement ego sfxIds traitsetName universe } } }`

async function fetchEntities() { loading.value = true; const data = await graphql(ALL_ENTITIES, { type: null }); if (data?.entities) entities.value = data.entities; loading.value = false }

function toggleEntity(e) {
  if (editing.value && selectedId.value === e.id) { editing.value = false; selected.value = null; selectedId.value = null }
  else { selectEntity(e) }
}
function onSelectLocation(id) { toggleEntity({ id }, true) }
function onSelectOccupant(e) { toggleEntity(e) }

async function selectEntity(e) {
  const data = await graphql(ENTITY_QUERY, { id: e.id })
  if (data?.entity) {
    selected.value = data.entity; selectedId.value = e.id; editing.value = true
    form.value = { name: data.entity.name, type: data.entity.type, current_universe: data.entity.currentUniverse, current_location: data.entity.currentLocation || '', razmerit: data.entity.razmerit, background_image: data.entity.backgroundImage || '', overlay: data.entity.overlay || null, hidden: data.entity.hidden }
  }
}
async function saveEntity() {
  saving.value = true
  await graphql(`mutation($input: UpdateEntityInput!) { updateEntity(input: $input) { id name razmerit currentUniverse currentLocation hidden backgroundImage } }`, { input: { id: selected.value.id, name: form.value.name, razmerit: form.value.razmerit, currentUniverse: form.value.current_universe, currentLocation: form.value.current_location || null, hidden: form.value.hidden, backgroundImage: form.value.background_image || null, overlay: form.value.overlay } })
  saving.value = false; await selectEntity(selected.value); await fetchEntities()
}
async function deleteSelected() {
  if (!confirm(`Delete ${selected.value.name}?`)) return
  await graphql(`mutation($id: ID!) { deleteEntity(id: $id) }`, { id: selected.value.id })
  selected.value = null; selectedId.value = null; editing.value = false; await fetchEntities()
}
async function startCreate() { creating.value = true; editing.value = false; selected.value = null; createForm.value = { name: '', type: 'CHARACTER', universe: props.universe, location: '', razmerit: 0 } }
async function createEntity() {
  saving.value = true
  await graphql(`mutation($input: CreateEntityInput!) { createEntity(input: $input) { id name type razmerit currentUniverse currentLocation } }`, { input: { name: createForm.value.name, type: createForm.value.type, universe: createForm.value.universe, location: createForm.value.location || null, razmerit: createForm.value.razmerit } })
  saving.value = false; creating.value = false; await fetchEntities()
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

// ── Navigation ─────────────────────────────────────
function closeSecondary() { if (configTraits.value) { closeTraitsConfig(); return; } editing.value = false; creating.value = false; selected.value = null; selectedId.value = null; inspectedEntity.value = null }
function switchToSheet() { if (!selected.value) return; inspectedEntity.value = { id: selected.value.id }; editing.value = false; selected.value = null; selectedId.value = null }
function switchToEdit() { if (!inspectedEntity.value) return; const id = inspectedEntity.value.id; inspectedEntity.value = null; selectEntity({ id }) }

// ── Location tree ──────────────────────────────────
const TYPE_PRIORITY = { CHARACTER: 0, GMC: 1, ASSET: 2 }
const occupantsByLocation = computed(() => {
  const map = {}
  for (const e of entities.value) { if ((e.type === 'CHARACTER' || e.type === 'GMC' || e.type === 'ASSET') && e.currentLocation) { if (!map[e.currentLocation]) map[e.currentLocation] = []; map[e.currentLocation].push(e) } }
  for (const key of Object.keys(map)) map[key].sort((a, b) => (TYPE_PRIORITY[a.type] ?? 9) - (TYPE_PRIORITY[b.type] ?? 9))
  return map
})
function nodeOrDescendantsMatch(node, occupants, q) {
  if (node.name.toLowerCase().includes(q)) return true
  if (occupants[node.id]) { for (const e of occupants[node.id]) { if (e.name.toLowerCase().includes(q)) return true } }
  if (node.children) { for (const c of node.children) { if (nodeOrDescendantsMatch(c, occupants, q)) return true } }
  return false
}
function flattenTree(nodes, occupants, depth = 0, query = '') {
  const result = []
  for (const node of nodes) {
    if (query && !nodeOrDescendantsMatch(node, occupants, query)) continue
    const hasChildren = (node.children && node.children.length > 0) || (occupants[node.id] && occupants[node.id].length > 0)
    result.push({ id: node.id, name: node.name, universe: node.universe, depth, hasChildren, kind: 'location' })
    const expanded = (expandedNodes.value[node.id] !== undefined ? expandedNodes.value[node.id] : depth === 0) || !!query
    if (expanded && occupants[node.id]) { for (const e of occupants[node.id]) { if (query && !e.name.toLowerCase().includes(query)) continue; result.push({ id: e.id, name: e.name, universe: e.currentUniverse || '', depth: depth + 1, hasChildren: false, kind: 'occupant', entityType: e.type, entity: e }) } }
    if (expanded && node.children && node.children.length) result.push(...flattenTree(node.children, occupants, depth + 1, query))
  }
  return result
}
const flatTree = computed(() => {
  let roots = locationTree.value
  const q = (!filterLocationId.value && filterQuery.value.trim()) ? filterQuery.value.trim().toLowerCase() : ''
  if (filterLocationId.value) {
    function findNode(nodes) { for (const n of nodes) { if (n.id === filterLocationId.value) return [n]; if (n.children) { const f = findNode(n.children); if (f) return f } } return null }
    roots = findNode(locationTree.value) || []
  }
  return flattenTree(roots, occupantsByLocation.value, 0, q)
})
function toggleTreeNode(id) { expandedNodes.value = { ...expandedNodes.value, [id]: !expandedNodes.value[id] } }
async function fetchLocationTree() { try { const r = await fetch('/api/v1/locations/tree'); locationTree.value = await r.json() } catch { locationTree.value = [] } }

// ── Inspection ─────────────────────────────────────
function inspectEntity(id) {
  if (inspectedEntity.value?.id === id) { inspectedEntity.value = null }
  else { editing.value = false; creating.value = false; selected.value = null; selectedId.value = null; inspectedEntity.value = { id } }
}

// ── Traits config ──────────────────────────────────

watch(configTraits, async (val) => {
  if (val && traitsets.value.length === 0) await fetchTraitsConfig()
})

async function fetchTraitsConfig() {
  traitsLoading.value = true
  const [ts, tr, sf] = await Promise.all([
    graphql(`query { traitsets { id name } }`),
    graphql(`query($u: String!) { traitsByUniverse(universe: $u) { id name defaultDieType traitsetId } }`, { u: props.universe }),
    graphql(`query { sfxs { id name description trigger } }`),
  ])
  if (ts?.traitsets) traitsets.value = ts.traitsets
  if (tr?.traitsByUniverse) allTraitsData.value = tr.traitsByUniverse
  if (sf?.sfxs) allSfxsData.value = sf.sfxs
  traitsLoading.value = false
}

// ── Unified secondary panels ────────────────────────

const secondaryPanels = computed(() => {
  const panels = []
  // Entity secondary panels (level 0) — content comes from #entity slot
  if (inspectedEntity.value && !editing.value) {
    panels.push({ id: 'inspect' })
  } else if (editing.value && selected.value) {
    panels.push({ id: 'edit' })
  } else if (creating.value) {
    panels.push({ id: 'create' })
  } else if (configTraits.value) {
    return traitConfigPanels.value
  }
  return panels
})

function onSecondaryClose(level) {
  if (configTraits.value) { closeTraitConfigLevel(level); return }
  closeSecondary()
}

// ── PanelStack for traits config ────────────────────

const traitConfigPanels = computed(() => {
  const panels = []
  // Level 0: traitsets list
  panels.push({
    id: 'traitsets',
    component: GmTraitsetsPanel,
    title: 'Traitsets',
    props: {
      traitsets: traitsets.value,
      allTraits: allTraitsData.value,
      allSfxs: allSfxsData.value,
      loading: traitsLoading.value,
      selectedId: activeTraitsetId.value,
    },
  })
  // Level 1: traits in selected traitset
  if (activeTraitset.value) {
    panels.push({
      id: 'traits',
      component: GmTraitsPanel,
      title: activeTraitset.value.name,
      props: {
        traits: allTraitsData.value.filter(t => t.traitsetId === activeTraitsetId.value),
        selectedId: activeTraitId.value,
      },
    })
  }
  // Level 2: SFXs
  if (activeTrait.value) {
    panels.push({
      id: 'sfxs',
      component: GmSfxsPanel,
      title: activeTrait.value.name,
      props: {
        sfxs: allSfxsData.value,
        selectedId: activeSfxId.value,
      },
    })
  }
  // Level 3: SFX editor
  if (activeSfx.value) {
    panels.push({
      id: 'sfx-edit',
      component: GmSfxEditPanel,
      title: activeSfx.value.name,
      hideBack: false,
      props: { sfx: activeSfx.value },
    })
  }
  return panels
})

function closeTraitConfigLevel(level) {
  // level is the index of the panel to close and all deeper
  if (level <= 0) { closeTraitsConfig(); return }
  if (level <= 1) { activeTraitset.value = null; activeTraitsetId.value = null; activeTrait.value = null; activeTraitId.value = null; activeSfx.value = null; activeSfxId.value = null; return }
  if (level <= 2) { activeTrait.value = null; activeTraitId.value = null; activeSfx.value = null; activeSfxId.value = null; return }
  activeSfx.value = null; activeSfxId.value = null
}

function closeTraitsConfig() {
  configTraits.value = false
  activeTraitset.value = null; activeTraitsetId.value = null
  activeTrait.value = null; activeTraitId.value = null
  activeSfx.value = null; activeSfxId.value = null
  traitSearch.value = ''
}

function onTraitConfigSelect(item) {
  // Figure out what type of item was selected by its fields
  if (item.traitsetId !== undefined) {
    // It's a trait
    activeTrait.value = item; activeTraitId.value = item.id
    activeSfx.value = null; activeSfxId.value = null
  } else if (item.trigger !== undefined || item.description !== undefined) {
    // It's an SFX
    activeSfx.value = item; activeSfxId.value = item.id
  } else {
    // It's a traitset
    activeTraitset.value = item; activeTraitsetId.value = item.id
    activeTrait.value = null; activeTraitId.value = null
    activeSfx.value = null; activeSfxId.value = null
  }
}

function onTraitConfigSave(form) {
  if (!activeSfx.value) return
  sfxSaving.value = true
  graphql(
    `mutation($input: SfxInput!) { updateSfx(input: $input) { id } }`,
    { input: { id: activeSfx.value.id, name: form.name, trigger: form.trigger || null, description: form.description || null } }
  ).finally(() => { sfxSaving.value = false; fetchTraitsConfig() })
}

// ── Lifecycle ──────────────────────────────────────
watch(open, (val) => { if (val) { mode.value = 'play'; fetchEntities(); fetchLocationTree() } })
onMounted(() => { fetchEntities(); fetchLocationTree() })
</script>

<style scoped>
.gm-toggle {
  position: fixed; top: 50%; right: 12px; transform: translateY(-50%); z-index: 21;
  width: 42px; height: 42px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  font-size: 20px; padding: 0;
  background: var(--bg-panel); backdrop-filter: blur(12px);
  border: 1px solid rgba(255,255,255,0.1);
}
.gm-panel {
  position: fixed; top: 50%; right: 38px; transform: translateY(-50%); z-index: 20;
  width: 0; max-width: 0; max-height: 0; padding: 0;
  border-radius: 12px;
  transition: width 0.3s ease, max-width 0.3s ease, max-height 0.3s ease, padding 0.3s ease;
  overflow: hidden;
}
.gm-panel.open {
  width: 320px; max-width: calc(100vw - 100px); max-height: 90vh; height: auto;
  overflow: visible; padding: 16px;
}
.gm-panel.open.has-editor { overflow: visible; }
.gm-content { overflow-y: auto; max-height: calc(90vh - 32px); }

/* ── Mode tabs ─────────────────────────────────── */
.mode-tabs { display: flex; gap: 0; margin-bottom: 10px; border-radius: 6px; overflow: hidden; border: 1px solid rgba(255,255,255,0.08); }
.mode-tabs button { flex: 1; font-size: 12px; padding: 6px 0; border: none; background: rgba(255,255,255,0.04); color: var(--text-dim); cursor: pointer; transition: all 0.15s; }
.mode-tabs button.active { background: var(--accent); color: #fff; }
.mode-tabs button:hover:not(.active) { background: rgba(255,255,255,0.08); }

/* ── Shortcuts ──────────────────────────────────── */
.gm-shortcuts { display: flex; gap: 4px; flex-wrap: wrap; margin-bottom: 8px; }
.shortcut-btn { flex: 1; min-width: 0; font-size: 11px; padding: 8px 6px; border-radius: 6px; border: 1px solid rgba(255,255,255,0.08); background: rgba(255,255,255,0.04); color: var(--text-dim); cursor: pointer; transition: all 0.2s; white-space: nowrap; }
.shortcut-btn:hover { background: rgba(255,255,255,0.08); color: var(--text); }
.beat-btn { border-color: rgba(64,136,212,0.3); } .beat-btn:hover { border-color: var(--accent); background: rgba(64,136,212,0.12); }
.scene-btn { border-color: rgba(64,184,96,0.3); } .scene-btn:hover { border-color: #40b860; background: rgba(64,184,96,0.12); }
.session-btn { border-color: rgba(232,136,48,0.3); } .session-btn:hover { border-color: #e88830; background: rgba(232,136,48,0.12); }
.session-btn.active { border-color: #d44040; color: #d44040; } .session-btn.active:hover { background: rgba(212,64,64,0.12); }

/* ── Entities layout ───────────────────────────── */
.entities-layout { position: relative; }
.entity-list-col { overflow-y: auto; max-height: calc(90vh - 180px); }

/* ── Filter ─────────────────────────────────────── */
.filter-bar { margin-bottom: 8px; }
.filter-input-wrap { position: relative; }
.filter-input { width: 100%; font-size: 12px; padding: 6px 28px 6px 8px; box-sizing: border-box; }
.filter-clear-inline { position: absolute; right: 4px; top: 50%; transform: translateY(-50%); font-size: 12px; padding: 2px 6px; background: none; color: var(--text-dim); border: none; cursor: pointer; }
.filter-clear-inline:hover { color: var(--text); }
.filter-suggestions { position: absolute; top: 100%; left: 0; right: 0; z-index: 30; background: var(--bg-panel); backdrop-filter: blur(12px); border: 1px solid rgba(255,255,255,0.1); border-radius: 0 0 6px 6px; max-height: 200px; overflow-y: auto; }
.suggestion-row { display: flex; align-items: center; gap: 6px; padding: 6px 10px; font-size: 12px; cursor: pointer; }
.suggestion-row:hover { background: rgba(255,255,255,0.06); }

/* ── Create button ──────────────────────────────── */
.create-btn { width: 100%; font-size: 12px; padding: 8px; margin-bottom: 8px; background: var(--accent-dim); color: var(--text); }
.create-btn:hover { background: var(--accent); }

/* ── Entity rows ────────────────────────────────── */
.entity-row { display: flex; align-items: center; gap: 6px; padding: 8px 10px; margin-bottom: 4px; background: rgba(255,255,255,0.04); border-radius: 6px; cursor: pointer; transition: background 0.15s; font-size: 13px; }
.entity-row:hover { background: rgba(255,255,255,0.08); }
.entity-row.selected { background: rgba(64,136,212,0.15); border: 1px solid var(--accent-dim); }
.entity-type-badge { font-size: 9px; text-transform: uppercase; padding: 1px 6px; border-radius: 3px; font-weight: 600; }
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

@media (max-width: 720px) {
  .gm-panel.has-editor, .gm-toggle.has-editor { display: none; }
}
</style>
