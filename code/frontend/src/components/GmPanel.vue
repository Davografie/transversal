<template>
  <div v-if="open" class="gm-backdrop" @click="open = false" @touchstart="open = false" />
  <div class="gm-panel panel" :class="{ open }">
    <button class="toggle" @click="open = !open">
      {{ open ? '×' : '🛠' }}
    </button>

    <div v-if="open" class="gm-content">
      <div v-if="loading" class="loading">Loading…</div>
      <div v-else-if="error" class="error">{{ error }}</div>

      <template v-else>
        <!-- Shortcut bar — always visible -->
        <div class="gm-shortcuts">
          <button class="shortcut-btn beat-btn" @click="nextBeat" title="Empty all dice pools">◆ Next Beat</button>
          <button class="shortcut-btn scene-btn" @click="endScene" title="Show scene summary">◈ End Scene</button>
          <button v-if="!sessionActive" class="shortcut-btn session-btn" @click="startSession" title="Start a new session">▶ Start Session</button>
          <button v-else class="shortcut-btn session-btn active" @click="endSession" title="End session, trigger queued effects">■ End Session</button>
        </div>

        <!-- Arrange Map toggle -->
        <button
          class="edit-zones-toggle"
          :class="{ active: editZones }"
          @click="$emit('update:editZones', !editZones)"
        >{{ editZones ? 'Done' : 'Arrange Map' }}</button>

        <!-- Navigation links -->
        <button v-if="view !== 'entities'" class="nav-link" @click="view = 'entities'">Manage Entities</button>
        <button v-if="view !== 'scene-summary'" class="nav-link" @click="showSceneSummary">Scene Summary</button>
        <button v-if="view !== 'shortcuts'" class="nav-link" @click="view = 'shortcuts'">← Shortcuts</button>

        <hr class="gm-divider" />

        <!-- ===== SHORTCUTS VIEW (default) ===== -->
        <div v-if="view === 'shortcuts'" class="shortcuts-view">
          <div class="shortcut-card">
            <h4>◆ Next Beat</h4>
            <p>Empty all dice pools and advance the narrative clock.</p>
          </div>
          <div class="shortcut-card">
            <h4>◈ End Scene</h4>
            <p>Review the current scene — see where everyone is and what's at stake.</p>
          </div>
          <div class="shortcut-card">
            <h4>{{ sessionActive ? '■ End Session' : '▶ Start Session' }}</h4>
            <p>{{ sessionActive ? 'Close the session and resolve any queued end-of-session effects.' : 'Begin a new play session.' }}</p>
          </div>
        </div>

        <!-- ===== SCENE SUMMARY VIEW ===== -->
        <div v-if="view === 'scene-summary'" class="scene-summary">
          <h3>Scene Summary</h3>
          <div v-if="sceneEntities.length === 0" class="empty">No characters or GMCs in this session</div>
          <div v-for="e in sceneEntities" :key="e.id" class="scene-row">
            <span class="entity-type-badge" :class="'type-' + e.type">{{ e.type === 'GMC' ? 'GMC' : 'PC' }}</span>
            <span class="entity-name">{{ e.name }}</span>
            <span class="scene-loc">{{ e.currentLocation || '—' }}</span>
            <span class="scene-universe">{{ e.currentUniverse }}</span>
            <span class="scene-raz">⚡{{ e.razmerit }}</span>
          </div>
        </div>

        <!-- ===== ENTITY LIST VIEW ===== -->
        <div v-if="view === 'entities'" class="entities-layout" :class="{ 'has-editor': editing || creating }">
          <!-- Edit panel (left of the list) -->
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

            <!-- Trait management -->
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

          <!-- Create panel (left of the list) -->
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

          <!-- Entity list column (always visible, right side) -->
          <div class="entity-list-col">
            <div class="type-filters">
              <button
                v-for="t in typeFilters"
                :key="t.value"
                :class="{ active: typeFilter === t.value }"
                @click="typeFilter = t.value"
              >{{ t.label }}</button>
            </div>

            <button class="create-btn" @click="startCreate">+ New Entity</button>

            <!-- Location tree view -->
            <template v-if="typeFilter === 'LOCATION'">
              <div v-if="flatTree.length === 0" class="empty">No locations found</div>
              <div
                v-for="node in flatTree"
                :key="node.id"
                class="entity-row tree-row"
                :class="{ selected: selectedId === node.id }"
                :style="{ paddingLeft: (12 + node.depth * 20) + 'px' }"
                @click="selectEntity({ id: node.id, type: 'LOCATION' })"
              >
                <span v-if="node.hasChildren" class="tree-toggle" @click.stop="toggleTreeNode(node.id)">
                  {{ expandedNodes[node.id] ? '▾' : '▸' }}
                </span>
                <span v-else class="tree-toggle leaf"></span>
                <span class="entity-type-badge type-LOCATION">LOC</span>
                <span class="entity-name">{{ node.name }}</span>
                <span class="entity-universe">{{ node.universe }}</span>
              </div>
            </template>
            <!-- Flat list for non-location types -->
            <template v-else>
              <div
                v-for="e in filteredEntities"
                :key="e.id"
                class="entity-row"
                :class="{ selected: selectedId === e.id }"
                @click="selectEntity(e)"
              >
                <span class="entity-type-badge" :class="'type-' + e.type">{{ e.type }}</span>
                <span class="entity-name">{{ e.name }}</span>
                <span class="entity-universe">{{ e.currentUniverse }}</span>
              </div>
              <div v-if="filteredEntities.length === 0" class="empty">No entities found</div>
            </template>
          </div>
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
  editZones: { type: Boolean, default: false },
})

const emit = defineEmits(['update:editZones', 'next-beat', 'start-session', 'end-session'])

const open = ref(false)
const view = ref('shortcuts')
const sessionActive = ref(false)

const typeFilter = ref('')
const typeFilters = [
  { value: '', label: 'All' },
  { value: 'CHARACTER', label: 'Chars' },
  { value: 'LOCATION', label: 'Locs' },
  { value: 'GMC', label: 'GMCs' },
  { value: 'FACTION', label: 'Factions' },
  { value: 'ASSET', label: 'Assets' },
]
const entityTypes = ['CHARACTER', 'LOCATION', 'GMC', 'FACTION', 'ASSET']
const dieTypes = ['d4', 'd6', 'd8', 'd10', 'd12']

const entities = ref([])
const selected = ref(null)
const selectedId = ref(null)
const editing = ref(false)
const creating = ref(false)
const saving = ref(false)
const addingTrait = ref(false)

const filteredEntities = computed(() => {
  if (!typeFilter.value) return entities.value
  return entities.value.filter(e => e.type === typeFilter.value)
})

const sceneEntities = computed(() =>
  entities.value.filter(e => e.type === 'CHARACTER' || e.type === 'GMC')
)

const universes = computed(() => {
  const unis = entities.value.filter(e => e.type === 'UNIVERSE')
  return unis.map(u => ({ key: u.currentUniverse, name: u.name }))
})

const locationEntities = computed(() =>
  entities.value.filter(e => e.type === 'LOCATION')
)

const filteredLocations = computed(() => {
  const uni = creating.value ? createForm.value.universe : ''
  if (!uni) return locationEntities.value
  return locationEntities.value.filter(l => l.currentUniverse === uni)
})

// ── Shortcut actions ───────────────────────────────

function nextBeat() {
  emit('next-beat')
}

function endScene() {
  showSceneSummary()
}

function showSceneSummary() {
  view.value = 'scene-summary'
  fetchEntities()
}

function startSession() {
  sessionActive.value = true
  emit('start-session')
}

function endSession() {
  sessionActive.value = false
  emit('end-session')
}

// ── Forms ──────────────────────────────────────────

const form = ref({})
const createForm = ref({
  name: '',
  type: 'CHARACTER',
  universe: 'earth',
  location: '',
  razmerit: 0,
})

const newTrait = ref({
  traitId: '',
  dieType: 'd6',
  rating: '',
  statement: '',
})

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
  const data = await graphql(ALL_ENTITIES, { type: typeFilter.value || null })
  if (data?.entities) {
    entities.value = data.entities
  }
}

async function selectEntity(e) {
  const data = await graphql(ENTITY_QUERY, { id: e.id })
  if (data?.entity) {
    selected.value = data.entity
    selectedId.value = e.id
    editing.value = true
    form.value = {
      name: data.entity.name,
      type: data.entity.type,
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
  const MUTATION = `
    mutation($input: UpdateEntityInput!) {
      updateEntity(input: $input) { id name razmerit currentUniverse currentLocation hidden backgroundImage }
    }
  `
  await graphql(MUTATION, {
    input: {
      id: selected.value.id,
      name: form.value.name,
      razmerit: form.value.razmerit,
      currentUniverse: form.value.current_universe,
      currentLocation: form.value.current_location || null,
      hidden: form.value.hidden,
      backgroundImage: form.value.background_image || null,
      overlay: form.value.overlay,
    }
  })
  saving.value = false
  await selectEntity(selected.value)
  await fetchEntities()
}

async function deleteSelected() {
  if (!confirm(`Delete ${selected.value.name}?`)) return
  const MUTATION = `mutation($id: ID!) { deleteEntity(id: $id) }`
  await graphql(MUTATION, { id: selected.value.id })
  selected.value = null
  selectedId.value = null
  editing.value = false
  await fetchEntities()
}

async function startCreate() {
  creating.value = true
  editing.value = false
  selected.value = null
  createForm.value = {
    name: '',
    type: typeFilter.value || 'CHARACTER',
    universe: props.universe,
    location: '',
    razmerit: 0,
  }
}

async function createEntity() {
  saving.value = true
  const MUTATION = `
    mutation($input: CreateEntityInput!) {
      createEntity(input: $input) { id name type razmerit currentUniverse currentLocation }
    }
  `
  await graphql(MUTATION, {
    input: {
      name: createForm.value.name,
      type: createForm.value.type,
      universe: createForm.value.universe,
      location: createForm.value.location || null,
      razmerit: createForm.value.razmerit,
    }
  })
  saving.value = false
  creating.value = false
  await fetchEntities()
}

// ── Trait management ───────────────────────────────

async function loadAvailableTraits() {
  if (!selected.value) return
  const uni = selected.value.currentUniverse
  const QUERY = `query($u: String!) { traitsByUniverse(universe: $u) { id name defaultDieType traitsetId defaultRatingType } }`
  const data = await graphql(QUERY, { u: uni })
  if (data?.traitsByUniverse) {
    availableTraits.value = data.traitsByUniverse
  }
}

watch(() => selected.value?.currentUniverse, () => {
  if (selected.value) loadAvailableTraits()
})

function onTraitSelected() {
  const t = availableTraits.value.find(t => t.id === newTrait.value.traitId)
  if (t) {
    newTrait.value.dieType = t.defaultDieType.toLowerCase()
    newTrait.value.rating = t.defaultDieType.toLowerCase()
  }
}

async function addTrait() {
  addingTrait.value = true
  const MUTATION = `
    mutation($eid: ID!, $input: TraitSettingInput!) {
      addTraitSetting(entityId: $eid, input: $input) { id }
    }
  `
  const t = availableTraits.value.find(t => t.id === newTrait.value.traitId)
  await graphql(MUTATION, {
    eid: selected.value.id,
    input: {
      traitId: newTrait.value.traitId,
      traitsetId: t?.traitsetId || '',
      dieType: newTrait.value.dieType.toUpperCase(),
      rating: newTrait.value.rating || newTrait.value.dieType,
      statement: newTrait.value.statement,
    }
  })
  newTrait.value = { traitId: '', dieType: 'd6', rating: '', statement: '' }
  addingTrait.value = false
  await selectEntity(selected.value)
}

async function removeTrait(tsId) {
  const MUTATION = `mutation($id: ID!) { removeTraitSetting(id: $id) }`
  await graphql(MUTATION, { id: tsId })
  await selectEntity(selected.value)
}

async function uploadBgImage(e) {
  const file = e.target.files?.[0]
  if (!file) return
  const formData = new FormData()
  formData.append('file', file)
  try {
    const r = await fetch(`/api/v1/media/upload?entity_id=${encodeURIComponent(selected.value?.id || '')}`, {
      method: 'POST',
      body: formData,
    })
    const data = await r.json()
    if (data.path) {
      form.value.background_image = data.path
      const MUTATION = `mutation($input: UpdateEntityInput!) { updateEntity(input: $input) { id backgroundImage } }`
      await graphql(MUTATION, { input: { id: selected.value.id, backgroundImage: data.path } })
    }
  } catch (err) {
    error.value = err.message
  }
}

// ── Location tree ──────────────────────────────────

const locationTree = ref([])
const expandedNodes = ref({})

function flattenTree(nodes, depth = 0) {
  const result = []
  for (const node of nodes) {
    const hasChildren = node.children && node.children.length > 0
    result.push({
      id: node.id,
      name: node.name,
      universe: node.universe,
      depth,
      hasChildren,
    })
    if (hasChildren && expandedNodes.value[node.id]) {
      result.push(...flattenTree(node.children, depth + 1))
    }
  }
  return result
}

const flatTree = computed(() => flattenTree(locationTree.value))

async function fetchLocationTree() {
  try {
    const r = await fetch('/api/v1/locations/tree')
    locationTree.value = await r.json()
  } catch {
    locationTree.value = []
  }
}

function toggleTreeNode(id) {
  expandedNodes.value = { ...expandedNodes.value, [id]: !expandedNodes.value[id] }
}

// Reset view to shortcuts when panel closes/opens
watch(open, (val) => {
  if (val) {
    view.value = 'shortcuts'
    fetchEntities()
    fetchLocationTree()
  }
})

// Fetch tree when switching to LOCATION filter
watch(typeFilter, (val) => {
  if (val === 'LOCATION') fetchLocationTree()
})

onMounted(() => {
  fetchEntities()
  fetchLocationTree()
})
</script>

<style scoped>
.gm-backdrop {
  position: fixed; inset: 0; z-index: 19;
  background: transparent;
}

.gm-panel {
  position: fixed;
  top: 50%;
  right: 12px;
  transform: translateY(-50%);
  z-index: 20;
  width: 48px;
  max-width: 48px;
  height: 48px;
  padding: 8px;
  transition: width 0.3s ease, max-width 0.3s ease, height 0.3s ease, padding 0.3s ease;
  overflow: hidden;
}

.gm-panel.open {
  width: 320px;
  max-width: calc(100vw - 80px);
  height: auto;
  max-height: 90vh;
  overflow-y: auto;
  padding: 16px;
}

.gm-panel.open:has(.has-editor) {
  overflow: visible;
}

.toggle {
  position: absolute;
  top: 6px; right: 6px;
  width: 36px; height: 36px;
  border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  font-size: 20px; padding: 0;
  z-index: 1;
  background: var(--bg-panel);
}
.gm-content { margin-top: 24px; }

/* ── Shortcut bar ──────────────────────────────── */

.gm-shortcuts {
  display: flex; gap: 4px; flex-wrap: wrap; margin-bottom: 8px;
}

.shortcut-btn {
  flex: 1; min-width: 0; font-size: 11px; padding: 8px 6px;
  border-radius: 6px; border: 1px solid rgba(255,255,255,0.08);
  background: rgba(255,255,255,0.04); color: var(--text-dim);
  cursor: pointer; transition: all 0.2s;
  white-space: nowrap;
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

/* ── Arrange Map ────────────────────────────────── */

.edit-zones-toggle {
  width: 100%; font-size: 12px; padding: 6px; margin-bottom: 6px;
  background: rgba(255,255,255,0.06); color: var(--text-dim);
  border-radius: 6px; border: 1px solid rgba(255,255,255,0.1);
  cursor: pointer; transition: all 0.2s;
}
.edit-zones-toggle.active {
  background: var(--accent); color: #fff; border-color: var(--accent);
}

/* ── Nav links ──────────────────────────────────── */

.nav-link {
  display: inline-block; font-size: 11px; padding: 4px 10px; margin-right: 4px; margin-bottom: 4px;
  background: none; color: var(--accent-dim); border: 1px solid rgba(255,255,255,0.06);
  border-radius: 4px; cursor: pointer;
}
.nav-link:hover { color: var(--accent); border-color: var(--accent-dim); }

.gm-divider {
  border: none; border-top: 1px solid rgba(255,255,255,0.06); margin: 8px 0;
}

/* ── Shortcuts view ─────────────────────────────── */

.shortcuts-view {
  display: flex; flex-direction: column; gap: 8px;
}

.shortcut-card {
  padding: 12px; background: rgba(255,255,255,0.03);
  border-radius: 8px; border: 1px solid rgba(255,255,255,0.05);
}
.shortcut-card h4 {
  font-size: 13px; margin-bottom: 4px; color: var(--text);
}
.shortcut-card p {
  font-size: 11px; color: var(--text-dim); line-height: 1.4; margin: 0;
}

/* ── Scene summary ──────────────────────────────── */

.scene-summary h3 {
  font-size: 14px; color: var(--text-dim); margin-bottom: 8px;
  text-transform: uppercase; letter-spacing: 1px;
}

.scene-row {
  display: flex; align-items: center; gap: 6px;
  padding: 8px 10px; margin-bottom: 4px;
  background: rgba(255,255,255,0.04); border-radius: 6px;
  font-size: 13px;
}

.scene-loc { font-size: 11px; color: var(--text-dim); flex: 1; text-align: right; }
.scene-universe { font-size: 10px; color: var(--text-dim); }
.scene-raz { font-size: 11px; color: var(--accent); font-weight: 600; }

/* ── Type filters ────────────────────────────────── */

.type-filters {
  display: flex; gap: 4px; flex-wrap: wrap; margin-bottom: 10px;
}
.type-filters button {
  font-size: 10px; padding: 3px 8px; border-radius: 4px;
  background: rgba(255,255,255,0.06); color: var(--text-dim);
}
.type-filters button.active { background: var(--accent); color: #fff; }

/* ── Entity list ─────────────────────────────────── */

.create-btn {
  width: 100%; font-size: 12px; padding: 8px; margin-bottom: 8px;
  background: var(--accent-dim); color: var(--text);
}
.create-btn:hover { background: var(--accent); }

.entity-row {
  display: flex; align-items: center; gap: 6px;
  padding: 8px 10px; margin-bottom: 4px;
  background: rgba(255,255,255,0.04); border-radius: 6px;
  cursor: pointer; transition: background 0.15s;
  font-size: 13px;
}
.entity-row:hover { background: rgba(255,255,255,0.08); }
.entity-row.selected { background: rgba(64,136,212,0.15); border: 1px solid var(--accent-dim); }

.entity-type-badge {
  font-size: 9px; text-transform: uppercase;
  padding: 1px 6px; border-radius: 3px;
  font-weight: 600;
}
.type-CHARACTER, .type-PC { background: #4088d4; color: #fff; }
.type-LOCATION { background: #40b860; color: #0a0a0f; }
.type-GMC { background: #e88830; color: #0a0a0f; }
.type-FACTION { background: #d44040; color: #fff; }
.type-ASSET { background: #888; color: #fff; }

.entity-name { flex: 1; font-weight: 500; }
.entity-universe { font-size: 10px; color: var(--text-dim); }

/* ── Location tree ─────────────────────────────── */

.tree-row {
  cursor: pointer; transition: background 0.15s;
}
.tree-row:hover { background: rgba(255,255,255,0.06); }

.tree-toggle {
  font-size: 10px; width: 14px; color: var(--text-dim);
  cursor: pointer; flex-shrink: 0; text-align: center;
  user-select: none;
}
.tree-toggle:hover { color: var(--text); }
.tree-toggle.leaf { visibility: hidden; }

/* ── Entities layout ───────────────────────────── */

.entities-layout {
  position: relative;
}

.entity-list-col {
  /* Always full-width — never impacted by edit panel */
  overflow-y: auto; max-height: calc(90vh - 180px);
}

/* ── Edit / create panel (fixed, left of list) ── */

.edit-panel {
  position: fixed;
  top: 50%;
  transform: translateY(-50%);
  right: 352px;
  width: 360px;
  max-height: 90vh;
  overflow-y: auto;
  display: flex; flex-direction: column; gap: 8px;
  padding: 16px;
  background: var(--bg-panel);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border-radius: 8px;
  border: 1px solid rgba(255,255,255,0.06);
  animation: slideInLeft 0.2s ease;
}

@keyframes slideInLeft {
  from { opacity: 0; transform: translateY(-50%) translateX(12px); }
  to   { opacity: 1; transform: translateY(-50%) translateX(0); }
}

.edit-panel label {
  font-size: 11px; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.5px;
}
.edit-panel input, .edit-panel select {
  font-size: 13px; padding: 6px 10px;
}

.form-actions { display: flex; gap: 6px; }
.top-actions { justify-content: space-between; margin-bottom: 4px; }
.danger-btn { background: var(--danger) !important; color: #fff !important; }
.save-btn {
  background: var(--success) !important; color: #0a0a0f !important;
  font-weight: 600; margin-top: 4px;
}

.bg-image-row {
  display: flex; gap: 6px;
}
.bg-url { flex: 1; font-size: 12px !important; }
.bg-upload {
  font-size: 11px; padding: 4px 8px; cursor: pointer;
  background: var(--accent-dim); color: var(--text);
  border-radius: 6px; border: none;
  white-space: nowrap; max-width: 120px; overflow: hidden;
}
.bg-upload::file-selector-button {
  display: none;
}
.bg-preview {
  width: 100%; max-height: 120px; object-fit: cover;
  border-radius: 6px; margin-top: 4px;
}

/* ── Trait management ─────────────────────────────── */

.traits-heading {
  font-size: 12px; color: var(--text-dim); text-transform: uppercase;
  letter-spacing: 1px; margin-top: 12px; padding-top: 8px;
  border-top: 1px solid rgba(255,255,255,0.08);
}

.trait-list { display: flex; flex-direction: column; gap: 4px; }
.trait-row {
  display: flex; align-items: center; gap: 6px;
  padding: 4px 8px; background: rgba(255,255,255,0.04);
  border-radius: 4px; font-size: 12px;
}
.trait-name { flex: 1; font-weight: 500; }
.trait-die { font-weight: 700; font-size: 11px; }
.die-d4  { color: #e88830; }
.die-d6  { color: #e0e0e0; }
.die-d8  { color: #d44040; }
.die-d10 { color: #4088d4; }
.die-d12 { color: #40b860; }
.trait-ego {
  font-size: 9px; background: var(--accent-dim); color: var(--accent);
  padding: 1px 5px; border-radius: 3px; text-transform: uppercase;
}
.trait-remove {
  font-size: 14px; padding: 2px 6px; background: none; color: var(--danger);
  border-radius: 4px;
}
.trait-remove:hover { background: rgba(212,64,64,0.15); }

.add-trait { margin-top: 8px; }
.add-trait select { width: 100%; font-size: 12px; }
.add-trait-detail {
  display: flex; flex-direction: column; gap: 6px;
  margin-top: 8px; padding: 8px;
  background: rgba(255,255,255,0.03); border-radius: 6px;
}
.add-trait-detail label { font-size: 10px; }
.add-trait-detail input, .add-trait-detail select { font-size: 12px; }
.add-trait-detail button { font-size: 12px; padding: 6px; }

.loading, .error, .empty { font-size: 12px; color: var(--text-dim); padding: 12px 0; text-align: center; }
.error { color: var(--danger); }
</style>
