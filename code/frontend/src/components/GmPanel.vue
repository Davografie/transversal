<template>
  <div class="gm-panel panel" :class="{ open, 'has-editor': editing || creating || inspectedEntity }">
    <button class="toggle" @click="open = !open">
      {{ open ? '×' : '🛠' }}
    </button>

    <div v-if="open" class="gm-content">
      <div v-if="loading" class="loading">Loading…</div>
      <div v-else-if="error" class="error">{{ error }}</div>

      <template v-else>
        <!-- Mode tabs: Play / Prep -->
        <div class="mode-tabs">
          <button :class="{ active: mode === 'play' }" @click="mode = 'play'">Play</button>
          <button :class="{ active: mode === 'prep' }" @click="mode = 'prep'">Prep</button>
        </div>

        <!-- ===== PLAY MODE ===== -->
        <template v-if="mode === 'play'">
          <!-- Shortcut bar -->
          <div class="gm-shortcuts">
            <button class="shortcut-btn beat-btn" @click="nextBeat">◆ Next Beat</button>
            <button class="shortcut-btn scene-btn" @click="viewSceneSummary = !viewSceneSummary">◈ Scene</button>
            <button v-if="!sessionActive" class="shortcut-btn session-btn" @click="startSession">▶ Start</button>
            <button v-else class="shortcut-btn session-btn active" @click="endSession">■ End</button>
          </div>

          <!-- Scene summary -->
          <div v-if="viewSceneSummary" class="scene-summary">
            <h3>Scene</h3>
            <div v-if="sceneEntities.length === 0" class="empty">No characters or GMCs here</div>
            <div v-for="e in sceneEntities" :key="e.id" class="scene-row" @click="inspectEntity(e.id)">
              <span class="entity-type-badge" :class="'type-' + e.type">{{ e.type === 'GMC' ? 'GMC' : 'PC' }}</span>
              <span class="entity-name">{{ e.name }}</span>
              <span class="scene-raz">⚡{{ e.razmerit }}</span>
            </div>
          </div>
        </template>

        <!-- ===== PREP MODE ===== -->
        <template v-if="mode === 'prep'">
          <div class="entities-layout">
            <!-- Entity list column (right side) -->
            <div class="entity-list-col">
              <!-- Filter -->
              <div class="filter-bar">
                <div class="filter-input-wrap">
                  <input
                    v-model="filterQuery"
                    class="filter-input"
                    placeholder="Filter…"
                    @focus="showSuggestions = true"
                    @blur="hideSuggestions"
                    @keyup.escape="filterQuery = ''; filterLocationId = ''"
                  />
                  <button v-if="filterQuery" class="filter-clear-inline" @click="filterQuery = ''; filterLocationId = ''">✕</button>
                  <div v-if="showSuggestions && suggestions.length" class="filter-suggestions">
                    <div
                      v-for="s in suggestions"
                      :key="s.id"
                      class="suggestion-row"
                      @mousedown.prevent="selectSuggestion(s)"
                    >
                      <span class="entity-type-badge" :class="'type-' + s.type">{{ s.type }}</span>
                      <span>{{ s.name }}</span>
                    </div>
                  </div>
                </div>
              </div>

              <button class="create-btn" @click="startCreate">+ New Entity</button>

              <!-- Location tree -->
              <div
                v-for="node in flatTree"
                :key="node.kind + '-' + node.id"
                class="entity-row tree-row"
                :class="{ selected: selectedId === node.id, occupant: node.kind === 'occupant' }"
                :style="{ paddingLeft: (12 + node.depth * 20) + 'px' }"
                @click="node.kind === 'location' ? toggleEntity({ id: node.id, type: 'LOCATION' }, true) : toggleEntity(node.entity)"
              >
                <span v-if="node.hasChildren" class="tree-toggle" @click.stop="toggleTreeNode(node.id)">
                  {{ (expandedNodes[node.id] || node.depth === 0 || !!filterQuery) ? '▾' : '▸' }}
                </span>
                <span v-else class="tree-toggle" :class="{ leaf: node.kind === 'location', occupant: node.kind === 'occupant' }"></span>
                <span v-if="node.kind === 'location'" class="entity-type-badge type-LOCATION">LOC</span>
                <span v-else class="entity-type-badge" :class="'type-' + node.entityType">{{ node.entityType === 'CHARACTER' ? 'PC' : node.entityType === 'GMC' ? 'GMC' : node.entityType }}</span>
                <span class="entity-name">{{ node.name }}</span>
                <span class="entity-universe" v-if="node.kind === 'location' && node.universe !== universe">{{ node.universe }}</span>
              </div>

              <!-- Factions -->
              <h4 v-if="filteredFactions.length" class="factions-heading">Factions</h4>
              <div
                v-for="e in filteredFactions"
                :key="e.id"
                class="entity-row"
                :class="{ selected: selectedId === e.id }"
                @click="toggleEntity(e)"
              >
                <span class="entity-type-badge type-FACTION">FAC</span>
                <span class="entity-name">{{ e.name }}</span>
                <span class="entity-universe" v-if="e.currentUniverse !== universe">{{ e.currentUniverse }}</span>
              </div>

              <div v-if="flatTree.length === 0 && filteredFactions.length === 0" class="empty">No entities found</div>
            </div>
          </div>
        </template>

        <!-- Inspected entity panel (Play mode) -->
        <div v-if="inspectedEntity && !editing" class="edit-panel inspect-panel">
          <button @click="inspectedEntity = null">← Back</button>
          <h3>{{ inspectedEntity.name }}</h3>
          <div class="inspect-meta">
            <span class="entity-type-badge" :class="'type-' + inspectedEntity.type">{{ inspectedEntity.type === 'GMC' ? 'GMC' : 'PC' }}</span>
            <span v-if="inspectedEntity.currentUniverse !== universe" class="entity-universe">{{ inspectedEntity.currentUniverse }}</span>
          </div>
          <div class="inspect-raz">⚡ {{ inspectedEntity.razmerit }} razmerit</div>

          <div v-if="inspectedEntity.traitSettings?.length" class="trait-list">
            <div v-for="ts in inspectedEntity.traitSettings" :key="ts.id" class="trait-row">
              <span class="trait-name">{{ ts.name }}</span>
              <span class="trait-die" :class="'die-' + ts.dieType.toLowerCase()">{{ ts.dieType }}</span>
              <span v-if="ts.ego" class="trait-ego">ego</span>
            </div>
          </div>
          <div v-else class="empty">No traits</div>
        </div>

        <!-- Edit panel (shared across modes) -->
        <div v-if="editing && selected" class="edit-panel">
          <div class="form-actions top-actions">
            <button @click="editing = false; selected = null">← Back</button>
            <button class="danger-btn" @click="deleteSelected">Delete</button>
          </div>

          <label>Name</label>
          <input v-model="form.name" />

          <label>Type</label>
          <select v-model="form.type" disabled>
            <option v-for="t in entityTypes" :key="t" :value="t">{{ t }}</option>
          </select>

          <label>Universe</label>
          <select v-model="form.current_universe">
            <option v-for="u in universes" :key="u.key" :value="u.key">{{ u.name }}</option>
          </select>

          <label>Location</label>
          <select v-model="form.current_location">
            <option value="">-- None --</option>
            <option v-for="l in locationEntities" :key="l.id" :value="l.id">{{ l.name }}</option>
          </select>

          <label>Razmerit</label>
          <input v-model.number="form.razmerit" type="number" />

          <label>Background Image</label>
          <div class="bg-image-row">
            <input v-model="form.background_image" placeholder="/media/…" class="bg-url" />
            <input type="file" accept="image/*" @change="uploadBgImage" class="bg-upload" />
          </div>
          <img v-if="form.background_image" :src="form.background_image" class="bg-preview" />

          <label>Overlay Effect</label>
          <select v-model="form.overlay">
            <option :value="null">None</option>
            <option value="mist">Mist</option>
            <option value="fire">Fire</option>
            <option value="rain">Rain</option>
            <option value="snow">Snow</option>
            <option value="fog">Fog</option>
          </select>

          <label>
            <input v-model="form.hidden" type="checkbox" />
            Hidden
          </label>

          <button class="save-btn" @click="saveEntity" :disabled="saving">{{ saving ? 'Saving…' : 'Save' }}</button>

          <h4 class="traits-heading">Traits</h4>
          <div v-if="selected.traitSettings?.length" class="trait-list">
            <div v-for="ts in selected.traitSettings" :key="ts.id" class="trait-row">
              <span class="trait-name">{{ ts.name }}</span>
              <span class="trait-die" :class="'die-' + ts.dieType.toLowerCase()">{{ ts.dieType }}</span>
              <span v-if="ts.ego" class="trait-ego">ego</span>
              <button class="trait-remove" @click="removeTrait(ts.id)">×</button>
            </div>
          </div>
          <div v-else class="empty">No traits assigned</div>

          <div class="add-trait">
            <select v-model="newTrait.traitId" @change="onTraitSelected">
              <option value="">-- Add trait --</option>
              <option v-for="t in availableTraits" :key="t.id" :value="t.id">
                {{ t.name }} ({{ t.defaultDieType }})
              </option>
            </select>
            <div v-if="newTrait.traitId" class="add-trait-detail">
              <label>Die</label>
              <select v-model="newTrait.dieType">
                <option v-for="d in dieTypes" :key="d" :value="d">{{ d }}</option>
              </select>
              <label>Rating</label>
              <input v-model="newTrait.rating" placeholder="d8" />
              <label>Statement</label>
              <input v-model="newTrait.statement" placeholder="Distinction statement…" />
              <button @click="addTrait" :disabled="addingTrait">Add</button>
            </div>
          </div>
        </div>

        <!-- Create panel (shared across modes) -->
        <div v-if="creating" class="edit-panel">
          <button @click="creating = false">← Back</button>
          <label>Name</label>
          <input v-model="createForm.name" autofocus />
          <label>Type</label>
          <select v-model="createForm.type">
            <option v-for="t in entityTypes" :key="t" :value="t">{{ t }}</option>
          </select>
          <label>Universe</label>
          <select v-model="createForm.universe">
            <option v-for="u in universes" :key="u.key" :value="u.key">{{ u.name }}</option>
          </select>
          <label>Location (optional)</label>
          <select v-model="createForm.location">
            <option value="">-- None --</option>
            <option v-for="l in filteredLocations" :key="l.id" :value="l.id">{{ l.name }}</option>
          </select>
          <label>Razmerit</label>
          <input v-model.number="createForm.razmerit" type="number" />
          <button class="save-btn" @click="createEntity" :disabled="saving">{{ saving ? 'Creating…' : 'Create' }}</button>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useApi } from '../composables/useApi.js'

const { loading, error, graphql } = useApi()

const props = defineProps({
  universe: { type: String, default: 'earth' },
  currentLocationId: { type: String, default: '' },
})

const emit = defineEmits(['next-beat', 'start-session', 'end-session'])

const open = ref(false)
const mode = ref('play')
const viewSceneSummary = ref(true)
const inspectedEntity = ref(null)

function inspectEntity(id) {
  if (inspectedEntity.value?.id === id) {
    inspectedEntity.value = null
  } else {
    const e = entities.value.find(en => en.id === id)
    if (e) {
      inspectedEntity.value = { ...e }
      if (e.type === 'CHARACTER' || e.type === 'GMC') loadTraitsForEntity(e)
    }
  }
}

async function loadTraitsForEntity(e) {
  const data = await graphql(`query($id: ID!) { entity(id: $id) { traitSettings { id name dieType rating ratingType statement ego sfxIds traitsetName universe } } }`, { id: e.id })
  if (data?.entity?.traitSettings) {
    inspectedEntity.value = { ...inspectedEntity.value, traitSettings: data.entity.traitSettings }
  }
}
const sessionActive = ref(false)

const filterLocationId = ref('')
const filterQuery = ref('')
const showSuggestions = ref(false)

const locationTree = ref([])
const expandedNodes = ref({})

const entityTypes = ['CHARACTER', 'LOCATION', 'GMC', 'FACTION', 'ASSET']
const dieTypes = ['d4', 'd6', 'd8', 'd10', 'd12']

const entities = ref([])
const selected = ref(null)
const selectedId = ref(null)
const editing = ref(false)
const creating = ref(false)
const saving = ref(false)
const addingTrait = ref(false)

// ── Shortcut actions ───────────────────────────────

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
function hideSuggestions() {
  setTimeout(() => { showSuggestions.value = false }, 150)
}

// ── Filter resolution ──────────────────────────────

const allTreeNodesFlat = computed(() => {
  const result = []
  function walk(nodes) { for (const n of nodes) { result.push(n); if (n.children) walk(n.children) } }
  walk(locationTree.value)
  return result
})

const filterLocationIds = computed(() => {
  const ids = new Set()
  const lid = filterLocationId.value
  if (!lid) return ids
  function find(nodes) {
    for (const n of nodes) {
      if (n.id === lid) { collectDescendants(n, ids); return true }
      if (n.children && find(n.children)) return true
    }
    return false
  }
  find(locationTree.value)
  return ids
})

function collectDescendants(node, ids) {
  ids.add(node.id)
  if (node.children) for (const c of node.children) collectDescendants(c, ids)
}

// Keep filter in sync with current scene location
watch([() => props.currentLocationId, allTreeNodesFlat], ([newId, nodes]) => {
  if (newId && !filterQuery.value && nodes.length) {
    const loc = nodes.find(n => n.id === newId)
    if (loc) { filterQuery.value = loc.name; filterLocationId.value = newId }
  }
}, { immediate: true })

watch(filterQuery, (q) => {
  const t = q.trim()
  if (!t) { filterLocationId.value = ''; return }
  const m = allTreeNodesFlat.value.find(n => n.name.toLowerCase() === t.toLowerCase())
  filterLocationId.value = m ? m.id : ''
})

// ── Filtered data ──────────────────────────────────

const filteredFactions = computed(() => {
  let list = entities.value.filter(e => e.type === 'FACTION')
  const lid = filterLocationId.value
  if (lid && filterLocationIds.value.size > 0) {
    list = list.filter(e => e.currentLocation && filterLocationIds.value.has(e.currentLocation))
  } else if (filterQuery.value.trim()) {
    const q = filterQuery.value.trim().toLowerCase()
    list = list.filter(e => e.name.toLowerCase().includes(q))
  }
  return list
})

// ── Scene / location data ──────────────────────────

const sceneEntities = computed(() =>
  entities.value.filter(e => e.type === 'CHARACTER' || e.type === 'GMC')
)

const universes = computed(() => {
  return entities.value.filter(e => e.type === 'UNIVERSE').map(u => ({ key: u.currentUniverse, name: u.name }))
})

const locationEntities = computed(() => entities.value.filter(e => e.type === 'LOCATION'))

const filteredLocations = computed(() => {
  if (!creating.value) return locationEntities.value
  return locationEntities.value.filter(l => l.currentUniverse === createForm.value.universe)
})

// ── Forms ──────────────────────────────────────────

const form = ref({})
const createForm = ref({ name: '', type: 'CHARACTER', universe: 'earth', location: '', razmerit: 0 })
const newTrait = ref({ traitId: '', dieType: 'd6', rating: '', statement: '' })
const availableTraits = ref([])

// ── API ────────────────────────────────────────────

const ALL_ENTITIES = `
  query($type: EntityType) {
    entities(type: $type) {
      id type name razmerit currentUniverse currentLocation hidden
      backgroundImage traitSettings { id name dieType rating ratingType statement ego sfxIds traitsetName universe }
    }
  }
`
const ENTITY_QUERY = `
  query($id: ID!) {
    entity(id: $id) {
      id type name razmerit currentUniverse currentLocation hidden
      backgroundImage traitSettings { id name dieType rating ratingType statement ego sfxIds traitsetName universe }
    }
  }
`

async function fetchEntities() {
  const data = await graphql(ALL_ENTITIES, { type: null })
  if (data?.entities) entities.value = data.entities
}

function toggleEntity(e, expandIfLocation = false) {
  if (editing.value && selectedId.value === e.id) {
    editing.value = false; selected.value = null; selectedId.value = null
  } else {
    if (expandIfLocation) expandedNodes.value = { ...expandedNodes.value, [e.id]: true }
    selectEntity(e)
  }
}

async function selectEntity(e) {
  const data = await graphql(ENTITY_QUERY, { id: e.id })
  if (data?.entity) {
    selected.value = data.entity; selectedId.value = e.id; editing.value = true
    form.value = {
      name: data.entity.name, type: data.entity.type,
      current_universe: data.entity.currentUniverse,
      current_location: data.entity.currentLocation || '',
      razmerit: data.entity.razmerit,
      background_image: data.entity.backgroundImage || '',
      overlay: data.entity.overlay || null,
      hidden: data.entity.hidden,
    }
  }
}

async function saveEntity() {
  saving.value = true
  const MUTATION = `mutation($input: UpdateEntityInput!) { updateEntity(input: $input) { id name razmerit currentUniverse currentLocation hidden backgroundImage } }`
  await graphql(MUTATION, { input: { id: selected.value.id, name: form.value.name, razmerit: form.value.razmerit, currentUniverse: form.value.current_universe, currentLocation: form.value.current_location || null, hidden: form.value.hidden, backgroundImage: form.value.background_image || null, overlay: form.value.overlay } })
  saving.value = false
  await selectEntity(selected.value)
  await fetchEntities()
}

async function deleteSelected() {
  if (!confirm(`Delete ${selected.value.name}?`)) return
  await graphql(`mutation($id: ID!) { deleteEntity(id: $id) }`, { id: selected.value.id })
  selected.value = null; selectedId.value = null; editing.value = false
  await fetchEntities()
}

async function startCreate() {
  creating.value = true; editing.value = false; selected.value = null
  createForm.value = { name: '', type: 'CHARACTER', universe: props.universe, location: '', razmerit: 0 }
}

async function createEntity() {
  saving.value = true
  const MUTATION = `mutation($input: CreateEntityInput!) { createEntity(input: $input) { id name type razmerit currentUniverse currentLocation } }`
  await graphql(MUTATION, { input: { name: createForm.value.name, type: createForm.value.type, universe: createForm.value.universe, location: createForm.value.location || null, razmerit: createForm.value.razmerit } })
  saving.value = false; creating.value = false
  await fetchEntities()
}

// ── Trait management ───────────────────────────────

async function loadAvailableTraits() {
  if (!selected.value) return
  const data = await graphql(`query($u: String!) { traitsByUniverse(universe: $u) { id name defaultDieType traitsetId defaultRatingType } }`, { u: selected.value.currentUniverse })
  if (data?.traitsByUniverse) availableTraits.value = data.traitsByUniverse
}
watch(() => selected.value?.currentUniverse, () => { if (selected.value) loadAvailableTraits() })

function onTraitSelected() {
  const t = availableTraits.value.find(t => t.id === newTrait.value.traitId)
  if (t) { newTrait.value.dieType = t.defaultDieType.toLowerCase(); newTrait.value.rating = t.defaultDieType.toLowerCase() }
}

async function addTrait() {
  addingTrait.value = true
  const t = availableTraits.value.find(t => t.id === newTrait.value.traitId)
  await graphql(`mutation($eid: ID!, $input: TraitSettingInput!) { addTraitSetting(entityId: $eid, input: $input) { id } }`, { eid: selected.value.id, input: { traitId: newTrait.value.traitId, traitsetId: t?.traitsetId || '', dieType: newTrait.value.dieType.toUpperCase(), rating: newTrait.value.rating || newTrait.value.dieType, statement: newTrait.value.statement } })
  newTrait.value = { traitId: '', dieType: 'd6', rating: '', statement: '' }
  addingTrait.value = false
  await selectEntity(selected.value)
}

async function removeTrait(tsId) {
  await graphql(`mutation($id: ID!) { removeTraitSetting(id: $id) }`, { id: tsId })
  await selectEntity(selected.value)
}

async function uploadBgImage(e) {
  const file = e.target.files?.[0]
  if (!file) return
  const fd = new FormData(); fd.append('file', file)
  try {
    const r = await fetch(`/api/v1/media/upload?entity_id=${encodeURIComponent(selected.value?.id || '')}`, { method: 'POST', body: fd })
    const data = await r.json()
    if (data.path) {
      form.value.background_image = data.path
      await graphql(`mutation($input: UpdateEntityInput!) { updateEntity(input: $input) { id backgroundImage } }`, { input: { id: selected.value.id, backgroundImage: data.path } })
    }
  } catch (err) { error.value = err.message }
}

// ── Location tree ──────────────────────────────────

const TYPE_PRIORITY = { CHARACTER: 0, GMC: 1, ASSET: 2 }

const occupantsByLocation = computed(() => {
  const map = {}
  for (const e of entities.value) {
    if ((e.type === 'CHARACTER' || e.type === 'GMC' || e.type === 'ASSET') && e.currentLocation) {
      if (!map[e.currentLocation]) map[e.currentLocation] = []
      map[e.currentLocation].push(e)
    }
  }
  for (const key of Object.keys(map)) {
    map[key].sort((a, b) => (TYPE_PRIORITY[a.type] ?? 9) - (TYPE_PRIORITY[b.type] ?? 9))
  }
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
    const expanded = depth === 0 || !!query || expandedNodes.value[node.id]
    if (expanded && occupants[node.id]) {
      for (const e of occupants[node.id]) {
        if (query && !e.name.toLowerCase().includes(query)) continue
        result.push({ id: e.id, name: e.name, universe: e.currentUniverse || '', depth: depth + 1, hasChildren: false, kind: 'occupant', entityType: e.type, entity: e })
      }
    }
    if (expanded && node.children && node.children.length) {
      result.push(...flattenTree(node.children, occupants, depth + 1, query))
    }
  }
  return result
}

const flatTree = computed(() => {
  let roots = locationTree.value
  const q = (!filterLocationId.value && filterQuery.value.trim()) ? filterQuery.value.trim().toLowerCase() : ''
  if (filterLocationId.value) {
    function findNode(nodes) {
      for (const n of nodes) {
        if (n.id === filterLocationId.value) return [n]
        if (n.children) { const f = findNode(n.children); if (f) return f }
      }
      return null
    }
    roots = findNode(locationTree.value) || []
  }
  return flattenTree(roots, occupantsByLocation.value, 0, q)
})

function toggleTreeNode(id) {
  expandedNodes.value = { ...expandedNodes.value, [id]: !expandedNodes.value[id] }
}

async function fetchLocationTree() {
  try {
    const r = await fetch('/api/v1/locations/tree')
    locationTree.value = await r.json()
  } catch { locationTree.value = [] }
}

// ── Lifecycle ──────────────────────────────────────

watch(open, (val) => {
  if (val) { mode.value = 'play'; fetchEntities(); fetchLocationTree() }
})

onMounted(() => { fetchEntities(); fetchLocationTree() })
</script>

<style scoped>
.gm-panel {
  position: fixed; top: 50%; right: 12px; transform: translateY(-50%); z-index: 20;
  width: 48px; max-width: 48px; height: 48px; padding: 8px;
  transition: width 0.3s ease, max-width 0.3s ease, height 0.3s ease, padding 0.3s ease;
  overflow: hidden;
}
.gm-panel.open {
  width: 320px; max-width: calc(100vw - 80px); height: auto; max-height: 90vh;
  overflow-y: auto; padding: 16px;
}
.gm-panel.open.has-editor { overflow: visible; }

.toggle {
  position: absolute; top: 6px; right: 6px; width: 36px; height: 36px;
  border-radius: 50%; display: flex; align-items: center; justify-content: center;
  font-size: 20px; padding: 0; z-index: 1; background: var(--bg-panel);
}
.gm-content { margin-top: 24px; }

/* ── Mode tabs ─────────────────────────────────── */

.mode-tabs {
  display: flex; gap: 0; margin-bottom: 10px;
  border-radius: 6px; overflow: hidden;
  border: 1px solid rgba(255,255,255,0.08);
}
.mode-tabs button {
  flex: 1; font-size: 12px; padding: 6px 0; border: none;
  background: rgba(255,255,255,0.04); color: var(--text-dim);
  cursor: pointer; transition: all 0.15s;
}
.mode-tabs button.active { background: var(--accent); color: #fff; }
.mode-tabs button:hover:not(.active) { background: rgba(255,255,255,0.08); }

/* ── Shortcut bar ──────────────────────────────── */

.gm-shortcuts { display: flex; gap: 4px; flex-wrap: wrap; margin-bottom: 8px; }
.shortcut-btn {
  flex: 1; min-width: 0; font-size: 11px; padding: 8px 6px;
  border-radius: 6px; border: 1px solid rgba(255,255,255,0.08);
  background: rgba(255,255,255,0.04); color: var(--text-dim);
  cursor: pointer; transition: all 0.2s; white-space: nowrap;
}
.shortcut-btn:hover { background: rgba(255,255,255,0.08); color: var(--text); }
.beat-btn { border-color: rgba(64,136,212,0.3); }
.beat-btn:hover { border-color: var(--accent); background: rgba(64,136,212,0.12); }
.scene-btn { border-color: rgba(64,184,96,0.3); }
.scene-btn:hover { border-color: #40b860; background: rgba(64,184,96,0.12); }
.session-btn { border-color: rgba(232,136,48,0.3); }
.session-btn:hover { border-color: #e88830; background: rgba(232,136,48,0.12); }
.session-btn.active { border-color: #d44040; color: #d44040; }
.session-btn.active:hover { background: rgba(212,64,64,0.12); }

/* ── Scene summary ──────────────────────────────── */

.scene-summary h3 {
  font-size: 12px; color: var(--text-dim); margin-bottom: 6px;
  text-transform: uppercase; letter-spacing: 1px;
}
.scene-row {
  display: flex; align-items: center; gap: 6px;
  padding: 6px 10px; margin-bottom: 3px;
  background: rgba(255,255,255,0.04); border-radius: 6px;
  font-size: 13px; cursor: pointer; transition: background 0.15s;
}
.scene-row:hover { background: rgba(255,255,255,0.08); }
.scene-raz { font-size: 11px; color: var(--accent); font-weight: 600; margin-left: auto; }

/* ── Inspect panel ────────────────────────────── */

.inspect-panel h3 { font-size: 16px; margin: 0; }
.inspect-meta { display: flex; align-items: center; gap: 8px; }
.inspect-raz { font-size: 13px; color: var(--accent); }

/* ── Entities layout ───────────────────────────── */

.entities-layout { position: relative; }
.entity-list-col { overflow-y: auto; max-height: calc(90vh - 180px); }

/* ── Filter bar ────────────────────────────────── */

.filter-bar { margin-bottom: 8px; }
.filter-input-wrap { position: relative; }
.filter-input { width: 100%; font-size: 12px; padding: 6px 28px 6px 8px; box-sizing: border-box; }
.filter-clear-inline {
  position: absolute; right: 4px; top: 50%; transform: translateY(-50%);
  font-size: 12px; padding: 2px 6px; background: none; color: var(--text-dim); border: none; cursor: pointer;
}
.filter-clear-inline:hover { color: var(--text); }
.filter-suggestions {
  position: absolute; top: 100%; left: 0; right: 0; z-index: 30;
  background: var(--bg-panel); backdrop-filter: blur(12px);
  border: 1px solid rgba(255,255,255,0.1); border-radius: 0 0 6px 6px;
  max-height: 200px; overflow-y: auto;
}
.suggestion-row {
  display: flex; align-items: center; gap: 6px;
  padding: 6px 10px; font-size: 12px; cursor: pointer;
}
.suggestion-row:hover { background: rgba(255,255,255,0.06); }

/* ── Create button ─────────────────────────────── */

.create-btn {
  width: 100%; font-size: 12px; padding: 8px; margin-bottom: 8px;
  background: var(--accent-dim); color: var(--text);
}
.create-btn:hover { background: var(--accent); }

/* ── Entity rows ───────────────────────────────── */

.entity-row {
  display: flex; align-items: center; gap: 6px;
  padding: 8px 10px; margin-bottom: 4px;
  background: rgba(255,255,255,0.04); border-radius: 6px;
  cursor: pointer; transition: background 0.15s; font-size: 13px;
}
.entity-row:hover { background: rgba(255,255,255,0.08); }
.entity-row.selected { background: rgba(64,136,212,0.15); border: 1px solid var(--accent-dim); }

.entity-type-badge {
  font-size: 9px; text-transform: uppercase; padding: 1px 6px; border-radius: 3px; font-weight: 600;
}
.type-CHARACTER, .type-PC { background: #4088d4; color: #fff; }
.type-LOCATION { background: #40b860; color: #0a0a0f; }
.type-GMC { background: #e88830; color: #0a0a0f; }
.type-FACTION { background: #d44040; color: #fff; }
.type-ASSET { background: #888; color: #fff; }

.entity-name { flex: 1; font-weight: 500; }
.entity-universe { font-size: 10px; color: var(--text-dim); }

/* ── Location tree ─────────────────────────────── */

.tree-row { cursor: pointer; transition: background 0.15s; }
.tree-row:hover { background: rgba(255,255,255,0.06); }
.tree-toggle {
  font-size: 14px; width: 24px; min-height: 24px; line-height: 24px;
  color: var(--text-dim); cursor: pointer; flex-shrink: 0; text-align: center; user-select: none;
}
.tree-toggle:hover { color: var(--text); }
.tree-toggle.leaf { visibility: hidden; }
.tree-toggle.occupant { font-size: 8px; color: var(--text-dim); }
.tree-row.occupant { font-size: 12px; background: rgba(255,255,255,0.02); }
.tree-row.occupant:hover { background: rgba(255,255,255,0.05); }

/* ── Factions ──────────────────────────────────── */

.factions-heading {
  font-size: 11px; color: var(--text-dim); text-transform: uppercase;
  letter-spacing: 1px; margin-top: 12px; padding-top: 8px;
  border-top: 1px solid rgba(255,255,255,0.08);
}

/* ── Edit panel ────────────────────────────────── */

.edit-panel {
  position: fixed; top: 50%; transform: translateY(-50%); right: 352px;
  width: 360px; max-height: 90vh; overflow-y: auto;
  display: flex; flex-direction: column; gap: 8px; padding: 16px;
  background: var(--bg-panel); backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px);
  border-radius: 8px; border: 1px solid rgba(255,255,255,0.06);
  animation: slideInLeft 0.2s ease;
}
@keyframes slideInLeft {
  from { opacity: 0; transform: translateY(-50%) translateX(12px); }
  to   { opacity: 1; transform: translateY(-50%) translateX(0); }
}
.edit-panel label { font-size: 11px; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.5px; }
.edit-panel input, .edit-panel select { font-size: 13px; padding: 6px 10px; }

.form-actions { display: flex; gap: 6px; }
.top-actions { justify-content: space-between; margin-bottom: 4px; }
.danger-btn { background: var(--danger) !important; color: #fff !important; }
.save-btn { background: var(--success) !important; color: #0a0a0f !important; font-weight: 600; margin-top: 4px; }

.bg-image-row { display: flex; gap: 6px; }
.bg-url { flex: 1; font-size: 12px !important; }
.bg-upload {
  font-size: 11px; padding: 4px 8px; cursor: pointer;
  background: var(--accent-dim); color: var(--text); border-radius: 6px; border: none;
  white-space: nowrap; max-width: 120px; overflow: hidden;
}
.bg-upload::file-selector-button { display: none; }
.bg-preview { width: 100%; max-height: 120px; object-fit: cover; border-radius: 6px; margin-top: 4px; }

.traits-heading {
  font-size: 12px; color: var(--text-dim); text-transform: uppercase;
  letter-spacing: 1px; margin-top: 12px; padding-top: 8px;
  border-top: 1px solid rgba(255,255,255,0.08);
}
.trait-list { display: flex; flex-direction: column; gap: 4px; }
.trait-row {
  display: flex; align-items: center; gap: 6px;
  padding: 4px 8px; background: rgba(255,255,255,0.04); border-radius: 4px; font-size: 12px;
}
.trait-name { flex: 1; font-weight: 500; }
.trait-die { font-weight: 700; font-size: 11px; }
.die-d4  { color: #e88830; } .die-d6  { color: #e0e0e0; } .die-d8  { color: #d44040; }
.die-d10 { color: #4088d4; } .die-d12 { color: #40b860; }
.trait-ego { font-size: 9px; background: var(--accent-dim); color: var(--accent); padding: 1px 5px; border-radius: 3px; text-transform: uppercase; }
.trait-remove { font-size: 14px; padding: 2px 6px; background: none; color: var(--danger); border-radius: 4px; }
.trait-remove:hover { background: rgba(212,64,64,0.15); }

.add-trait { margin-top: 8px; }
.add-trait select { width: 100%; font-size: 12px; }
.add-trait-detail {
  display: flex; flex-direction: column; gap: 6px; margin-top: 8px; padding: 8px;
  background: rgba(255,255,255,0.03); border-radius: 6px;
}
.add-trait-detail label { font-size: 10px; }
.add-trait-detail input, .add-trait-detail select { font-size: 12px; }
.add-trait-detail button { font-size: 12px; padding: 6px; }

.loading, .error, .empty { font-size: 12px; color: var(--text-dim); padding: 12px 0; text-align: center; }
.error { color: var(--danger); }
</style>
