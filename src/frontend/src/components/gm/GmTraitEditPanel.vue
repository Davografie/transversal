<template>
  <div>
    <!-- Trait details form (auto-save in edit mode) -->
    <template v-if="trait">
      <div class="ps-form">
        <label>Name</label>
        <input v-model="form.name" />
        <label>Universes</label>
        <ChipInput v-model="form.universes" :options="universeOptions" placeholder="Add universe…" />
        <label>Default Die Type</label>
        <select v-model="form.defaultDieType">
          <option value="D4">d4</option><option value="D6">d6</option><option value="D8">d8</option><option value="D10">d10</option><option value="D12">d12</option>
        </select>
        <label>Default Rating Type</label>
        <select v-model="form.defaultRatingType">
          <option value="STATIC">Static</option><option value="RESOURCE">Resource</option><option value="CHALLENGE">Challenge</option><option value="EMPTY">Empty</option>
        </select>
        <label class="checkbox-label"><input type="checkbox" v-model="form.locationRestricted" /> Location Restricted</label>
      </div>

      <!-- Display Names (read-only list → opens editor panel) -->
      <h4 class="ps-section-title">Display Names</h4>
      <div v-if="sortedDisplayNames.length === 0" class="empty">No display names — trait uses base name</div>
      <div v-else class="dn-list">
        <div
          v-for="(dn, dni) in sortedDisplayNames"
          :key="dni"
          class="dn-row"
          @click="openDisplayNameEditor(dn._originalIndex)"
        >
          <span class="dn-name">{{ dn.name }}</span>
          <span class="dn-universe">{{ universeLabel(dn.universe) }}</span>
          <span class="dn-ratings">
            <span v-for="(r, ri) in dn.ratings" :key="ri" class="dn-rating">
              <span v-for="(d, di) in r" :key="di" class="die-chip">{{ d }}</span>
              <span v-if="ri < dn.ratings.length - 1" class="dn-sep">|</span>
            </span>
          </span>
          <button class="row-del-btn" @click.stop="deleteDisplayName(dn._originalIndex)" title="Delete">✕</button>
        </div>
      </div>
      <button class="ps-add-btn" @click="openDisplayNameEditor(null)">+ Add Display Name</button>

      <!-- SFX assignment -->
      <h4 class="ps-section-title">Possible SFXs</h4>
      <div v-if="possibleSfxs.length === 0" class="empty">No SFXs assigned — add one below</div>
      <div v-else class="sfx-list">
        <div v-for="s in possibleSfxs" :key="s.id" class="sfx-row" @click="onSfxClick(s)">
          <label class="checkbox-inner" @click.stop>
            <input type="checkbox" :checked="form.defaultSfxIds.includes(s.id)"
              @change="toggleDefaultSfx(s.id)" title="Default SFX for this trait" />
          </label>
          <span class="sfx-name">{{ s.name }}</span>
          <span class="sfx-trigger">{{ s.trigger || '' }}</span>
          <button class="row-del-btn" @click.stop="removePossibleSfx(s.id)" title="Remove from trait">✕</button>
        </div>
      </div>
      <button class="ps-add-btn" @click="openSfxPicker">+ Add SFX</button>

      <div class="danger-zone">
        <button class="danger-btn" @click="onDelete" :disabled="saving">{{ saving ? 'Deleting…' : 'Delete Trait' }}</button>
      </div>
    </template>

    <!-- Create mode: new trait form -->
    <template v-else>
      <div class="ps-form">
        <label>ID</label>
        <input v-model="createForm.id" placeholder="trait-3r-my-trait" />
        <label>Name</label>
        <input v-model="createForm.name" placeholder="Trait name…" />
        <label>Universes</label>
        <ChipInput v-model="createForm.universes" :options="universeOptions" placeholder="Add universe…" />
        <label>Default Die Type</label>
        <select v-model="createForm.defaultDieType">
          <option value="D4">d4</option><option value="D6">d6</option><option value="D8">d8</option><option value="D10">d10</option><option value="D12">d12</option>
        </select>
        <label>Default Rating Type</label>
        <select v-model="createForm.defaultRatingType">
          <option value="STATIC">Static</option><option value="RESOURCE">Resource</option><option value="CHALLENGE">Challenge</option><option value="EMPTY">Empty</option>
        </select>
        <div class="create-actions">
          <button class="save-btn" @click="onCreate" :disabled="saving || !createForm.id.trim() || !createForm.name.trim()">{{ saving ? 'Creating…' : 'Create Trait' }}</button>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { reactive, ref, watch, onMounted, computed } from 'vue'
import { useApi } from '@/composables/useApi.js'
import ChipInput from './ChipInput.vue'
import GmSfxEditPanel from '@/components/gm/GmSfxEditPanel.vue'
import GmSfxPickerPanel from '@/components/gm/GmSfxPickerPanel.vue'
import GmDisplayNameEditPanel from '@/components/gm/GmDisplayNameEditPanel.vue'

const { graphql } = useApi()

const props = defineProps({
  trait: { type: Object, default: null },
  allSfxs: { type: Array, default: () => [] },
  selectedId: { type: String, default: '' },
  traitsetId: { type: String, default: '' },
  onRefresh: { type: Function, default: null },
  onPatch: { type: Function, default: null },
  open: { type: Function, default: null },
  close: { type: Function, default: null },
})

const saving = ref(false)

// Self-fetch SFXs if the prop chain didn't deliver them
const localSfxs = ref([])
onMounted(async () => {
  if (!props.allSfxs || props.allSfxs.length === 0) {
    const data = await graphql(`{ sfxs { id name description trigger limit effects { polarity timing type action target result } } }`)
    if (data?.sfxs) localSfxs.value = data.sfxs
  }
})
const allSfxsEffective = computed(() =>
  (props.allSfxs && props.allSfxs.length > 0) ? props.allSfxs : localSfxs.value
)

const universeOptions = [
  { label: 'Earth', value: 'earth' },
  { label: 'Three Realms', value: 'three_realms' },
]

// ── Edit mode form ──
const form = reactive({
  name: '',
  universes: [],
  defaultDieType: 'D6',
  defaultRatingType: 'STATIC',
  locationRestricted: false,
  possibleSfxIds: [],
  defaultSfxIds: [],
})

// Display names — derived from props.trait, kept as local array for display/auto-save
const displayNames = ref([])

// Sorted by minimum die rating ascending
const DIE_ORDER = { D4: 0, D6: 1, D8: 2, D10: 3, D12: 4 }
function minRatingDie(ratings) {
  let min = 99
  for (const r of (ratings || [])) {
    for (const d of r) {
      if (DIE_ORDER[d] !== undefined && DIE_ORDER[d] < min) min = DIE_ORDER[d]
    }
  }
  return min === 99 ? 99 : min
}

const sortedDisplayNames = computed(() => {
  return displayNames.value
    .map((dn, i) => ({ ...dn, _originalIndex: i }))
    .sort((a, b) => minRatingDie(a.ratings) - minRatingDie(b.ratings))
})

function universeLabel(u) {
  if (u === 'earth') return 'Earth'
  if (u === 'three_realms') return 'Three Realms'
  if (u === '*') return '*'
  return u || ''
}

function syncDisplayNamesFromTrait(t) {
  if (t && t.displayNames) {
    displayNames.value = t.displayNames.map(dn => ({
      name: dn.name || '',
      universe: dn.universe || '',
      ratings: (dn.ratings || []).map(r => [...r]),
    }))
  } else {
    displayNames.value = []
  }
}

watch(() => props.trait, (t) => {
  if (t) {
    form.name = t.name || ''
    form.universes = [...(t.universes || [])]
    form.defaultDieType = t.defaultDieType || 'D6'
    form.defaultRatingType = t.defaultRatingType || 'STATIC'
    form.locationRestricted = t.locationRestricted || false
    form.possibleSfxIds = [...(t.possibleSfxIds || [])]
    form.defaultSfxIds = [...(t.defaultSfxIds || [])]
    syncDisplayNamesFromTrait(t)
  }
}, { immediate: true })

let saveTimer = null
watch([
  () => form.name, () => [...form.universes], () => form.defaultDieType,
  () => form.defaultRatingType, () => form.locationRestricted,
  () => [...form.possibleSfxIds], () => [...form.defaultSfxIds],
], () => {
  if (!props.trait) return
  clearTimeout(saveTimer)
  saveTimer = setTimeout(() => save(), 600)
}, { deep: true })

function serializeDisplayNames() {
  return displayNames.value
    .filter(dn => dn.name.trim())
    .map(dn => ({
      name: dn.name.trim(),
      universe: dn.universe || '',
      ratings: dn.ratings.filter(r => r.length > 0),
    }))
}

async function save() {
  if (!props.trait?.id) return
  await graphql(
    `mutation($id: ID!, $input: TraitUpdateInput!) { updateTrait(id: $id, input: $input) { id } }`,
    { id: props.trait.id, input: { name: form.name, universes: form.universes, defaultDieType: form.defaultDieType, defaultRatingType: form.defaultRatingType, locationRestricted: form.locationRestricted, possibleSfxIds: form.possibleSfxIds, defaultSfxIds: form.defaultSfxIds } }
  )
  if (props.onPatch) props.onPatch('traits', props.trait.id, {
    name: form.name, universes: [...form.universes], defaultDieType: form.defaultDieType,
    defaultRatingType: form.defaultRatingType, locationRestricted: form.locationRestricted,
    possibleSfxIds: [...form.possibleSfxIds],
    defaultSfxIds: [...form.defaultSfxIds],
  })
}

// ── Display Name delete ──
async function deleteDisplayName(index) {
  if (!props.trait?.id) return
  const updated = displayNames.value
    .filter((_, i) => i !== index)
    .map(dn => ({
      name: dn.name || '',
      universe: dn.universe || '',
      ratings: (dn.ratings || []).filter(r => r.length > 0),
    }))
    .filter(dn => dn.name)
  displayNames.value = updated
  if (props.trait) props.trait.displayNames = updated
  await graphql(
    `mutation($id: ID!, $input: TraitUpdateInput!) { updateTrait(id: $id, input: $input) { id } }`,
    { id: props.trait.id, input: { displayNames: updated } }
  )
}

// ── Display Name editor ──
function openDisplayNameEditor(index) {
  if (!props.open || !props.trait?.id) return
  props.open({
    component: GmDisplayNameEditPanel,
    title: index === null ? 'Add Display Name' : 'Edit Display Name',
    props: {
      allDisplayNames: displayNames.value,
      editIndex: index,
      traitId: props.trait.id,
      onPatch: props.onPatch,
    },
    listeners: {
      'saved': (updatedList) => {
        displayNames.value = updatedList
        if (props.trait) props.trait.displayNames = updatedList
      },
    },
  })
}

// ── Create mode ──
const createForm = reactive({ id: '', name: '', universes: [], defaultDieType: 'D6', defaultRatingType: 'STATIC' })

async function onCreate() {
  saving.value = true
  try {
    const tsId = props.traitsetId || props.trait?.traitsetId || ''
    const universes = createForm.universes.length > 0 ? [...createForm.universes] : []
    await graphql(
      `mutation($input: TraitInput!) { createTrait(input: $input) { id } }`,
      { input: { id: createForm.id.trim(), name: createForm.name.trim(), universes, traitsetId: tsId, defaultDieType: createForm.defaultDieType, defaultRatingType: createForm.defaultRatingType, displayNames: [] } }
    )
    if (props.onRefresh) await props.onRefresh()
  } finally { saving.value = false }
}

// ── Possible SFXs (filtered from all) ──
const possibleSfxs = computed(() =>
  allSfxsEffective.value.filter(s => form.possibleSfxIds.includes(s.id))
)

function removePossibleSfx(id) {
  form.possibleSfxIds = form.possibleSfxIds.filter(sid => sid !== id)
  form.defaultSfxIds = form.defaultSfxIds.filter(sid => sid !== id)
}

function toggleDefaultSfx(id) {
  if (form.defaultSfxIds.includes(id)) {
    form.defaultSfxIds = form.defaultSfxIds.filter(sid => sid !== id)
  } else {
    form.defaultSfxIds.push(id)
  }
}

function openSfxPicker() {
  if (props.open) {
    props.open({
      component: GmSfxPickerPanel,
      title: 'Add SFX to Trait',
      props: {
        allSfxs: allSfxsEffective.value,
        selectedIds: [...form.possibleSfxIds],
        onRefresh: props.onRefresh,
        onPatch: props.onPatch,
      },
      listeners: {
        'add-sfx': (id) => {
          if (!form.possibleSfxIds.includes(id)) {
            form.possibleSfxIds.push(id)
          }
        },
        'remove-sfx': (id) => {
          form.possibleSfxIds = form.possibleSfxIds.filter(sid => sid !== id)
        },
      },
    })
  }
}

// ── SFX navigation ──
function onSfxClick(sfx) {
  if (props.open) {
    props.open({
      component: GmSfxEditPanel,
      title: sfx.name || 'Edit SFX',
      props: { sfx: sfx, onRefresh: props.onRefresh, onPatch: props.onPatch },
      listeners: {
        'sfx-updated': (updated) => {
          const idx = localSfxs.value.findIndex(s => s.id === updated.id)
          if (idx >= 0) Object.assign(localSfxs.value[idx], updated)
        },
        'sfx-deleted': (id) => {
          localSfxs.value = localSfxs.value.filter(s => s.id !== id)
        },
      },
    })
  }
}

// ── Delete ──
async function onDelete() {
  if (!props.trait?.id) return
  saving.value = true
  try { await graphql(`mutation($id: ID!) { deleteTrait(id: $id) }`, { id: props.trait.id }); if (props.onRefresh) await props.onRefresh(); if (props.close) props.close() }
  finally { saving.value = false }
}
</script>

<style scoped>
.ps-form { display: flex; flex-direction: column; gap: 6px; }
.ps-form label { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.5px; }
.ps-form input, .ps-form select { font-size: 12px; padding: 6px 8px; }
.checkbox-label { display: flex; align-items: center; gap: 6px; font-size: 11px; text-transform: none; cursor: pointer; }
.checkbox-label input { width: auto; }
.ps-section-title { font-size: 11px; color: var(--text-dim); text-transform: uppercase; letter-spacing: 1px; margin-top: 12px; padding-top: 8px; border-top: 1px solid rgba(255,255,255,0.08); }

.sfx-list { display: flex; flex-direction: column; gap: 2px; margin-top: 4px; }
.sfx-row { display: flex; align-items: center; gap: 6px; padding: 6px 8px; border-radius: 4px; cursor: pointer; font-size: 12px; transition: background 0.1s; background: rgba(255,255,255,0.04); }
.sfx-row:hover { background: rgba(255,255,255,0.08); }
.sfx-name { flex: 1; font-weight: 500; }
.checkbox-inner { display: inline-flex; align-items: center; cursor: pointer; flex-shrink: 0; }
.checkbox-inner input { width: auto; margin: 0; cursor: pointer; }
.sfx-trigger { font-size: 10px; color: var(--text-dim); }
.row-del-btn { font-size: 12px; padding: 2px 6px; background: none; color: var(--text-dim); border: none; cursor: pointer; border-radius: 3px; }
.row-del-btn:hover { color: var(--danger); background: rgba(212,64,64,0.12); }

.empty { font-size: 12px; color: var(--text-dim); padding: 12px 0; text-align: center; }
.ps-add-btn { font-size: 12px; padding: 6px; margin-top: 8px; background: var(--accent-dim); color: var(--text); border-radius: 6px; border: none; cursor: pointer; width: 100%; }
.ps-add-btn:hover { background: var(--accent); }
.ps-add-btn:disabled { opacity: 0.4; cursor: default; }
.create-actions { display: flex; gap: 6px; margin-top: 4px; }
.save-btn { background: var(--success); color: #0a0a0f; font-weight: 600; padding: 6px 12px; border-radius: 6px; border: none; cursor: pointer; font-size: 12px; }
.save-btn:disabled { opacity: 0.5; cursor: default; }
.danger-zone { margin-top: 10px; padding-top: 8px; border-top: 1px solid rgba(212,64,64,0.2); }
.danger-btn { width: 100%; font-size: 12px; padding: 6px; background: rgba(212,64,64,0.12); color: var(--danger); border: 1px solid rgba(212,64,64,0.25); border-radius: 6px; cursor: pointer; transition: background 0.15s; }
.danger-btn:hover { background: rgba(212,64,64,0.25); }
.danger-btn:disabled { opacity: 0.4; cursor: default; }

/* Display Names (read-only list) */
.dn-list { display: flex; flex-direction: column; gap: 2px; margin-top: 4px; }
.dn-row { display: flex; align-items: center; gap: 8px; padding: 6px 8px; border-radius: 4px; cursor: pointer; font-size: 12px; background: rgba(255,255,255,0.04); transition: background 0.1s; }
.dn-row:hover { background: rgba(255,255,255,0.08); }
.dn-name { font-weight: 500; min-width: 120px; }
.dn-universe { font-size: 10px; color: var(--text-dim); min-width: 80px; }
.dn-ratings { display: flex; align-items: center; gap: 2px; flex: 1; }
.dn-rating { display: inline-flex; align-items: center; gap: 2px; }
.die-chip { display: inline-block; padding: 1px 5px; background: rgba(255,255,255,0.1); border-radius: 3px; font-size: 10px; font-weight: 600; }
.dn-sep { color: var(--text-dim); margin: 0 2px; font-size: 10px; }
</style>
