<template>
  <div>
    <!-- Trait details form (auto-save in edit mode) -->
    <template v-if="trait">
      <div class="ps-form">
        <label>Name</label>
        <input v-model="form.name" />
        <label>Universes</label>
        <div class="universe-chips">
          <button
            v-for="u in allowedUniverses"
            :key="u.value"
            type="button"
            class="universe-chip"
            :class="{ enabled: form.universes.includes(u.value) }"
            :title="form.universes.includes(u.value) ? 'Enabled — click to disable' : 'Disabled — click to enable'"
            @click="toggleUniverse(u.value)"
          >{{ u.label }}</button>
        </div>
        <label>Default Die Type</label>
        <select v-model="form.defaultDieType">
          <option value="D4">d4</option><option value="D6">d6</option><option value="D8">d8</option><option value="D10">d10</option><option value="D12">d12</option>
        </select>
        <label>Default Rating Type</label>
        <select v-model="form.defaultRatingType">
          <option value="STATIC">Static</option><option value="RESOURCE">Resource</option><option value="CHALLENGE">Challenge</option><option value="EMPTY">Empty</option>
        </select>
        <label class="checkbox-label"><input type="checkbox" v-model="form.locationRestricted" /> Location Restricted</label>
        <div class="default-ego-row">
          <span class="field-label">Default</span>
          <button type="button" class="ego-toggle" :class="{ 'is-ego': form.defaultEgo }" @click="form.defaultEgo = !form.defaultEgo">{{ form.defaultEgo ? 'ego' : 'morph' }}</button>
        </div>
        <label>Polarity</label>
        <select v-model="form.polarity">
          <option value="">Inherit traitset</option>
          <option value="POSITIVE">Positive</option>
          <option value="NEGATIVE">Negative</option>
        </select>
      </div>

      <!-- Display Names (read-only list → opens editor panel) -->
      <h4 class="ps-section-title">Display Names</h4>
      <GmList
        :items="sortedDisplayNames"
        item-key="_originalIndex"
        empty-text="No display names — trait uses base name"
        @click="onDisplayNameClick"
      >
        <template #item="{ item: dn }">
          <span class="dn-name">{{ dn.name }}</span>
          <span class="dn-universe">{{ universeLabel(dn.universe) }}</span>
          <span class="dn-ratings">
            <span v-for="(r, ri) in dn.ratings" :key="ri" class="dn-rating">
              <span v-for="(d, di) in r" :key="di" class="die-chip">{{ d }}</span>
              <span v-if="ri < dn.ratings.length - 1" class="dn-sep">|</span>
            </span>
          </span>
          <button class="row-del-btn" @click.stop="deleteDisplayName(dn._originalIndex)" title="Delete">✕</button>
        </template>
      </GmList>
      <button class="ps-add-btn" @click="openDisplayNameEditor(null)">+ Add Display Name</button>

      <!-- SFX assignment -->
      <h4 class="ps-section-title">Possible SFXs</h4>
      <p class="section-hint">Each row is an SFX this trait can grant. Check an SFX to make it a <strong>default</strong> — characters with this trait get it automatically. Remove one from the list with ✕.</p>
      <GmList
        :items="possibleSfxs"
        item-key="id"
        empty-text="No SFXs assigned — add one below"
        @click="onSfxClick"
      >
        <template #item="{ item: s }">
          <label class="checkbox-inner" @click.stop>
            <input type="checkbox" :checked="form.defaultSfxIds.includes(s.id)"
              @change="toggleDefaultSfx(s.id)" title="Default SFX for this trait" />
          </label>
          <span class="sfx-name">{{ s.name }}</span>
          <span class="sfx-trigger">{{ s.trigger || '' }}</span>
          <button class="row-del-btn" @click.stop="removePossibleSfx(s.id)" title="Remove from trait">✕</button>
        </template>
      </GmList>
      <button class="ps-add-btn" @click="openSfxPicker">+ Add SFX</button>

      <div class="danger-zone">
        <DangerButton
          label="Delete Trait"
          loading-label="Deleting…"
          :disabled="saving"
          @confirm="onDelete"
        />
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
import { useTraitsConfig } from '@/composables/useTraitsConfig.js'
import { usePanel } from '@/composables/usePanel.js'
import ChipInput from './ChipInput.vue'
import GmSfxEditPanel from '@/components/gm/GmSfxEditPanel.vue'
import GmSfxPickerPanel from '@/components/gm/GmSfxPickerPanel.vue'
import GmDisplayNameEditPanel from '@/components/gm/GmDisplayNameEditPanel.vue'
import GmList from './GmList.vue'
import DangerButton from '@/components/gm/DangerButton.vue'

const { graphql } = useApi()
const panel = usePanel()
const { traitsets, allSfxs, fetchTraitsConfig, patchData } = useTraitsConfig()

// Derive trait reactively from the composable — stays current after refresh
const trait = computed(() => {
  for (const ts of traitsets?.value ?? []) {
    const found = (ts.traits || []).find(t => t.id === props.traitId)
    if (found) return found
  }
  return null
})

const props = defineProps({
  traitId: { type: String, default: null },
  selectedId: { type: String, default: '' },
  traitsetId: { type: String, default: '' },
})

const saving = ref(false)

// allSfxs is now provided by useTraitsConfig() composable — no local fallback needed

const universeOptions = ref([])

async function loadUniverseOptions() {
  try {
    const res = await graphql(`query($type: EntityType){ entities(type: $type){ id name currentUniverse } }`, { type: 'UNIVERSE' })
    universeOptions.value = (res?.entities || []).map(u => ({ value: u.currentUniverse, label: u.name }))
  } catch { /* leave empty */ }
}
onMounted(loadUniverseOptions)

// Only universes the trait's own trait set is enabled in — traits can't widen scope.
const allowedUniverses = computed(() => {
  const ts = (traitsets.value || []).find(ts => ts.id === trait.value?.traitsetId)
  if (!ts) return []
  return (ts.universes || []).map(u => universeOptions.value.find(o => o.value === u) || { label: u, value: u })
})

// ── Edit mode form ──
const form = reactive({
  name: '',
  universes: [],
  defaultDieType: 'D6',
  defaultRatingType: 'STATIC',
  locationRestricted: false,
  defaultEgo: false,
  polarity: '',
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
  if (u === '*') return '*'
  const opt = universeOptions.value.find(o => o.value === u)
  return opt?.label || u || ''
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

function toggleUniverse(value) {
  const idx = form.universes.indexOf(value)
  if (idx === -1) form.universes.push(value)
  else form.universes.splice(idx, 1)
}

watch(trait, (t) => {
  if (t) {
    form.name = t.name || ''
    form.universes = (t.universes || []).filter(u => {
      const ts = (traitsets.value || []).find(ts => ts.id === t.traitsetId)
      return !ts || (ts.universes || []).includes(u)
    })
    form.defaultDieType = t.defaultDieType || 'D6'
    form.defaultRatingType = t.defaultRatingType || 'STATIC'
    form.locationRestricted = t.locationRestricted || false
    form.defaultEgo = t.defaultEgo || false
    form.polarity = t.polarity || ''
    form.possibleSfxIds = [...(t.possibleSfxIds || [])]
    form.defaultSfxIds = [...(t.defaultSfxIds || [])]
    syncDisplayNamesFromTrait(t)
  }
}, { immediate: true })

let saveTimer = null
watch([
  () => form.name, () => [...form.universes], () => form.defaultDieType,
  () => form.defaultRatingType, () => form.locationRestricted, () => form.defaultEgo,
  () => form.polarity,
  () => [...form.possibleSfxIds], () => [...form.defaultSfxIds],
], () => {
  if (!trait.value) return
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
  if (!trait.value?.id) return
  await graphql(
    `mutation($id: ID!, $input: TraitUpdateInput!) { updateTrait(id: $id, input: $input) { id } }`,
    { id: trait.value.id, input: { name: form.name, universes: form.universes, defaultDieType: form.defaultDieType, defaultRatingType: form.defaultRatingType, locationRestricted: form.locationRestricted, defaultEgo: form.defaultEgo, polarity: form.polarity || null, clearPolarity: !form.polarity, possibleSfxIds: form.possibleSfxIds, defaultSfxIds: form.defaultSfxIds } }
  )
  patchData('traits', trait.value.id, {
    name: form.name, universes: [...form.universes], defaultDieType: form.defaultDieType,
    defaultRatingType: form.defaultRatingType, locationRestricted: form.locationRestricted, defaultEgo: form.defaultEgo,
    polarity: form.polarity || null,
    possibleSfxIds: [...form.possibleSfxIds],
    defaultSfxIds: [...form.defaultSfxIds],
  })
}

// ── Display Name delete ──
async function deleteDisplayName(index) {
  if (!trait.value?.id) return
  const updated = displayNames.value
    .filter((_, i) => i !== index)
    .map(dn => ({
      name: dn.name || '',
      universe: dn.universe || '',
      ratings: (dn.ratings || []).filter(r => r.length > 0),
    }))
    .filter(dn => dn.name)
  displayNames.value = updated
  await graphql(
    `mutation($id: ID!, $input: TraitUpdateInput!) { updateTrait(id: $id, input: $input) { id } }`,
    { id: trait.value.id, input: { displayNames: updated } }
  )
}

// ── Display Name editor ──
function openDisplayNameEditor(index) {
  if (!panel.open || !trait.value?.id) return
  panel.open({
    component: GmDisplayNameEditPanel,
    title: index === null ? 'Add Display Name' : 'Edit Display Name',
    props: {
      allDisplayNames: displayNames.value,
      editIndex: index,
      traitId: trait.value.id,
    },
    listeners: {
      'saved': (updatedList) => {
        displayNames.value = updatedList
      },
    },
  })
}

// ── Create mode ──
const createForm = reactive({ id: '', name: '', universes: [], defaultDieType: 'D6', defaultRatingType: 'STATIC' })

async function onCreate() {
  saving.value = true
  try {
    const tsId = props.traitsetId || trait.value?.traitsetId || ''
    const universes = createForm.universes.length > 0 ? [...createForm.universes] : []
    await graphql(
      `mutation($input: TraitInput!) { createTrait(input: $input) { id } }`,
      { input: { id: createForm.id.trim(), name: createForm.name.trim(), universes, traitsetId: tsId, defaultDieType: createForm.defaultDieType, defaultRatingType: createForm.defaultRatingType, displayNames: [] } }
    )
    await fetchTraitsConfig()
  } finally { saving.value = false }
}

// ── Possible SFXs (filtered from all) ──
const possibleSfxs = computed(() =>
  allSfxs.value.filter(s => form.possibleSfxIds.includes(s.id))
)

function removePossibleSfx(id) {
  form.possibleSfxIds = form.possibleSfxIds.filter(sid => sid !== id)
  form.defaultSfxIds = form.defaultSfxIds.filter(sid => sid !== id)
}

function onDisplayNameClick(dn) { openDisplayNameEditor(dn._originalIndex) }

function toggleDefaultSfx(id) {
  if (form.defaultSfxIds.includes(id)) {
    form.defaultSfxIds = form.defaultSfxIds.filter(sid => sid !== id)
  } else {
    form.defaultSfxIds.push(id)
  }
}

function openSfxPicker() {
  panel.open({
    component: GmSfxPickerPanel,
    title: 'Add SFX to Trait',
    props: {
      selectedIds: [...form.possibleSfxIds],
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

// ── SFX navigation ──
function onSfxClick(sfx) {
  panel.open({
    component: GmSfxEditPanel,
    title: sfx.name || 'Edit SFX',
    id: sfx.id,
    props: { sfx: sfx },
    listeners: {},
  })
}

// ── Delete ──
async function onDelete() {
  if (!trait.value?.id) return
  saving.value = true
  try { await graphql(`mutation($id: ID!) { deleteTrait(id: $id) }`, { id: trait.value.id }); await fetchTraitsConfig(); panel.close() }
  finally { saving.value = false }
}
</script>

<style scoped>
.ps-form input, .ps-form select { font-size: 12px; padding: 6px 8px; }

.checkbox-label { display: flex; align-items: center; gap: 6px; font-size: 11px; text-transform: none; cursor: pointer; }
.checkbox-label input { width: auto; }
.default-ego-row { display: flex; align-items: center; gap: 8px; }
.field-label { font-size: 11px; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.5px; }
.section-hint { font-size: 11px; color: var(--text-dim); margin: 0 0 6px; line-height: 1.4; }
.section-hint strong { color: var(--text); }
.ego-toggle {
  padding: 3px 12px;
  border-radius: 999px;
  border: 1px solid var(--text-dim);
  background: transparent;
  color: var(--text-dim);
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  cursor: pointer;
}
.ego-toggle.is-ego {
  border-color: var(--accent);
  color: var(--accent);
  background: rgba(255, 255, 255, 0.06);
}
.universe-chips { display: flex; flex-wrap: wrap; gap: 6px; }
.universe-chip {
  padding: 4px 10px;
  border-radius: 999px;
  border: 1px solid;
  font-size: 11px;
  cursor: pointer;
  transition: background 0.15s, color 0.15s, border-color 0.15s;
}
.universe-chip.enabled {
  border-color: var(--accent);
  color: var(--accent);
  background: rgba(64, 136, 212, 0.12);
}
.universe-chip:not(.enabled) {
  border-color: var(--danger);
  color: var(--danger);
  background: rgba(212, 64, 64, 0.10);
}
.sfx-name { flex: 1; font-weight: 500; }
.checkbox-inner { display: inline-flex; align-items: center; cursor: pointer; flex-shrink: 0; }
.checkbox-inner input { width: auto; margin: 0; cursor: pointer; }
.sfx-trigger { font-size: 10px; color: var(--text-dim); }

.create-actions { display: flex; gap: 6px; margin-top: 4px; }
.save-btn { background: var(--success); color: #0a0a0f; font-weight: 600; padding: 6px 12px; border-radius: 6px; border: none; cursor: pointer; font-size: 12px; }
.save-btn:disabled { opacity: 0.5; cursor: default; }

/* Display Names (read-only list) */
.dn-name { font-weight: 500; min-width: 120px; }
.dn-universe { font-size: 10px; color: var(--text-dim); min-width: 80px; }
.dn-ratings { display: flex; align-items: center; gap: 2px; flex: 1; }
.dn-rating { display: inline-flex; align-items: center; gap: 2px; }
.die-chip { display: inline-block; padding: 1px 5px; background: rgba(255,255,255,0.1); border-radius: 3px; font-size: 10px; font-weight: 600; }
.dn-sep { color: var(--text-dim); margin: 0 2px; font-size: 10px; }
</style>
