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
        <!-- Header -->
        <div class="gm-header">
          <h3>GM Tools</h3>
          <button
            class="edit-zones-toggle"
            :class="{ active: editZones }"
            @click="$emit('update:editZones', !editZones)"
          >{{ editZones ? 'Done Editing' : 'Edit Zones' }}</button>
          <div class="type-filters">
            <button
              v-for="t in typeFilters"
              :key="t.value"
              :class="{ active: typeFilter === t.value }"
              @click="typeFilter = t.value"
            >{{ t.label }}</button>
          </div>
        </div>

        <!-- Entity list -->
        <div v-if="!editing && !creating" class="entity-list">
          <button class="create-btn" @click="startCreate">+ New Entity</button>
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
        </div>

        <!-- Edit form -->
        <div v-if="editing && selected" class="edit-form">
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

        <!-- Create form -->
        <div v-if="creating" class="create-form">
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
  editZones: { type: Boolean, default: false },
})

const emit = defineEmits(['update:editZones'])

const open = ref(false)
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

const universes = computed(() => {
  // Derive from universe-type entities so we get human-readable names
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
      // Persist immediately to the database
      const MUTATION = `mutation($input: UpdateEntityInput!) { updateEntity(input: $input) { id backgroundImage } }`
      await graphql(MUTATION, { input: { id: selected.value.id, backgroundImage: data.path } })
    }
  } catch (err) {
    error.value = err.message
  }
}

onMounted(fetchEntities)
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

.gm-header h3 {
  font-size: 14px; color: var(--text-dim); margin-bottom: 8px;
  text-transform: uppercase; letter-spacing: 1px;
}

.edit-zones-toggle {
  width: 100%; font-size: 12px; padding: 6px; margin-bottom: 8px;
  background: rgba(255,255,255,0.06); color: var(--text-dim);
  border-radius: 6px; border: 1px solid rgba(255,255,255,0.1);
  cursor: pointer; transition: all 0.2s;
}
.edit-zones-toggle.active {
  background: var(--accent); color: #fff; border-color: var(--accent);
}

.type-filters {
  display: flex; gap: 4px; flex-wrap: wrap; margin-bottom: 10px;
}
.type-filters button {
  font-size: 10px; padding: 3px 8px; border-radius: 4px;
  background: rgba(255,255,255,0.06); color: var(--text-dim);
}
.type-filters button.active { background: var(--accent); color: #fff; }

.entity-list { margin-top: 8px; }
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
.type-CHARACTER { background: #4088d4; color: #fff; }
.type-LOCATION { background: #40b860; color: #0a0a0f; }
.type-GMC { background: #e88830; color: #0a0a0f; }
.type-FACTION { background: #d44040; color: #fff; }
.type-ASSET { background: #888; color: #fff; }

.entity-name { flex: 1; font-weight: 500; }
.entity-universe { font-size: 10px; color: var(--text-dim); }

.edit-form, .create-form {
  display: flex; flex-direction: column; gap: 8px;
}
.edit-form label, .create-form label {
  font-size: 11px; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.5px;
}
.edit-form input, .edit-form select,
.create-form input, .create-form select {
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
  white-space: nowrap;
}
.bg-upload::file-selector-button {
  display: none;
}
.bg-preview {
  width: 100%; max-height: 120px; object-fit: cover;
  border-radius: 6px; margin-top: 4px;
}

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
