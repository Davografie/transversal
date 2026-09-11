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
        <label>Tags</label>
        <TagInput
          v-model="form.tags"
          :suggestions="tagSuggestions"
          placeholder="Add tag…"
          aria-label="Trait tags"
        />
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
          <Button class="row-del-btn" @click.stop="deleteDisplayName(dn._originalIndex)" title="Delete" variant="danger-ghost" size="sm">✕</Button>
        </template>
      </GmList>
      <Button class="ps-add-btn" @click="openDisplayNameEditor(null)" variant="secondary" block>+ Add Display Name</Button>

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
          <button
            type="button"
            class="vx-toggle"
            :class="{ 'is-on': form.defaultSfxIds.includes(s.id) }"
            :title="form.defaultSfxIds.includes(s.id) ? 'Default SFX — click to unset' : 'Not default — click to make default'"
            @click.stop="toggleDefaultSfx(s.id)"
          >{{ form.defaultSfxIds.includes(s.id) ? '✓' : '✗' }}</button>
          <span class="sfx-name">{{ s.name }}</span>
          <span class="sfx-trigger">{{ s.trigger || '' }}</span>
          <Button class="row-del-btn" @click.stop="removePossibleSfx(s.id)" title="Remove from trait" variant="danger-ghost" size="sm">✕</Button>
        </template>
      </GmList>
      <Button class="ps-add-btn" @click="openSfxPicker" variant="secondary" block>+ Add SFX</Button>

      <!-- Sub-trait assignment -->
      <h4 class="ps-section-title">Possible Sub-traits</h4>
      <p class="section-hint">Add a whole sub-trait set (e.g. "elements") to make every trait in it nestable, or add individual traits.</p>
      <GmList
        :items="possibleSubtargetItems"
        item-key="key"
        empty-text="No sub-traits assigned"
      >
        <template #item="{ item: st }">
          <span class="subtarget-kind" :class="st.kind">{{ st.kind === 'set' ? 'set' : 'trait' }}</span>
          <span class="sfx-name">{{ st.name }}</span>
          <span class="sfx-trigger">{{ st.traitsetName || '' }}</span>
          <Button class="row-del-btn" @click.stop="removePossibleSubtarget(st.key)" title="Remove" variant="danger-ghost" size="sm">✕</Button>
        </template>
      </GmList>
      <div class="subtrait-add">
        <select v-model="newSubtarget">
          <option value="" disabled>Add sub-trait…</option>
          <optgroup label="Trait sets">
            <option v-for="ts in unassignedSubtraitsets()" :key="'set-' + ts.id" :value="'set:' + ts.id">{{ ts.name }} (all traits)</option>
          </optgroup>
          <optgroup v-for="ts in subtraitTraitsets" :key="ts.id" :label="ts.name">
            <option v-for="st in unassignedSubtraitOptions(ts)" :key="st.id" :value="'trait:' + st.id">{{ st.name }}</option>
          </optgroup>
        </select>
        <Button class="save-btn" @click="addSubtarget" :disabled="!newSubtarget" variant="success" solid>Add</Button>
      </div>

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
        <label>Name</label>
        <input v-model="createForm.name" placeholder="Trait name…" />
        <label>Universes</label>
        <div class="universe-chips">
          <button
            v-for="u in createAllowedUniverses"
            :key="u.value"
            type="button"
            class="universe-chip"
            :class="{ enabled: createForm.universes.includes(u.value) }"
            :title="createForm.universes.includes(u.value) ? 'Enabled — click to disable' : 'Disabled — click to enable'"
            @click="createToggleUniverse(u.value)"
          >{{ u.label }}</button>
        </div>
        <label>Default Die Type</label>
        <select v-model="createForm.defaultDieType">
          <option value="D4">d4</option><option value="D6">d6</option><option value="D8">d8</option><option value="D10">d10</option><option value="D12">d12</option>
        </select>
        <label>Default Rating Type</label>
        <select v-model="createForm.defaultRatingType">
          <option value="STATIC">Static</option><option value="RESOURCE">Resource</option><option value="CHALLENGE">Challenge</option><option value="EMPTY">Empty</option>
        </select>
        <div class="default-ego-row">
          <span class="field-label">Default</span>
          <button type="button" class="ego-toggle" :class="{ 'is-ego': createForm.defaultEgo }" @click="createForm.defaultEgo = !createForm.defaultEgo">{{ createForm.defaultEgo ? 'ego' : 'morph' }}</button>
        </div>
        <label>Polarity</label>
        <select v-model="createForm.polarity">
          <option value="">Inherit traitset</option>
          <option value="POSITIVE">Positive</option>
          <option value="NEGATIVE">Negative</option>
        </select>
        <label>Tags</label>
        <TagInput
          v-model="createForm.tags"
          :suggestions="tagSuggestions"
          placeholder="Add tag…"
          aria-label="Trait tags"
        />
      </div>

      <h4 class="ps-section-title">Possible SFXs</h4>
      <GmList
        :items="createPossibleSfxs"
        item-key="id"
        empty-text="No SFXs assigned — add one below"
        @click="onSfxClick"
      >
        <template #item="{ item: s }">
          <button
            type="button"
            class="vx-toggle"
            :class="{ 'is-on': createForm.defaultSfxIds.includes(s.id) }"
            :title="createForm.defaultSfxIds.includes(s.id) ? 'Default SFX — click to unset' : 'Not default — click to make default'"
            @click.stop="createToggleDefaultSfx(s.id)"
          >{{ createForm.defaultSfxIds.includes(s.id) ? '✓' : '✗' }}</button>
          <span class="sfx-name">{{ s.name }}</span>
          <span class="sfx-trigger">{{ s.trigger || '' }}</span>
          <Button class="row-del-btn" @click.stop="createRemovePossibleSfx(s.id)" title="Remove from trait" variant="danger-ghost" size="sm">✕</Button>
        </template>
      </GmList>
      <Button class="ps-add-btn" @click="createOpenSfxPicker" variant="secondary" block>+ Add SFX</Button>

      <h4 class="ps-section-title">Possible Sub-traits</h4>
      <p class="section-hint">Add a whole sub-trait set (e.g. "elements") to make every trait in it nestable, or add individual traits.</p>
      <GmList
        :items="createPossibleSubtargetItems"
        item-key="key"
        empty-text="No sub-traits assigned"
      >
        <template #item="{ item: st }">
          <span class="subtarget-kind" :class="st.kind">{{ st.kind === 'set' ? 'set' : 'trait' }}</span>
          <span class="sfx-name">{{ st.name }}</span>
          <span class="sfx-trigger">{{ st.traitsetName || '' }}</span>
          <Button class="row-del-btn" @click.stop="createRemovePossibleSubtarget(st.key)" title="Remove" variant="danger-ghost" size="sm">✕</Button>
        </template>
      </GmList>
      <div class="subtrait-add">
        <select v-model="newSubtargetCreate">
          <option value="" disabled>Add sub-trait…</option>
          <optgroup label="Trait sets">
            <option v-for="ts in createUnassignedSubtraitsets()" :key="'set-' + ts.id" :value="'set:' + ts.id">{{ ts.name }} (all traits)</option>
          </optgroup>
          <optgroup v-for="ts in subtraitTraitsets" :key="ts.id" :label="ts.name">
            <option v-for="st in createUnassignedSubtraitOptions(ts)" :key="st.id" :value="'trait:' + st.id">{{ st.name }}</option>
          </optgroup>
        </select>
        <Button class="save-btn" @click="createAddSubtarget" :disabled="!newSubtargetCreate" variant="success" solid>Add</Button>
      </div>

      <div class="create-actions">
        <Button class="save-btn" @click="onCreate" :loading="saving" :disabled="saving || !createForm.name.trim()" variant="success" solid>{{ saving ? 'Creating…' : 'Create Trait' }}</Button>
      </div>
      <p v-if="createError" class="switch-error">{{ createError }}</p>
    </template>
  </div>
</template>

<script setup>
import { reactive, ref, watch, onMounted, computed } from 'vue'
import { useApi } from '@/composables/useApi.js'
import { useTraitsConfig } from '@/composables/useTraitsConfig.js'
import { usePanel } from '@/composables/usePanel.js'
import GmSfxEditPanel from '@/components/gm/GmSfxEditPanel.vue'
import GmSfxPickerPanel from '@/components/gm/GmSfxPickerPanel.vue'
import GmDisplayNameEditPanel from '@/components/gm/GmDisplayNameEditPanel.vue'
import GmList from '@/components/ui/GmList.vue'
import DangerButton from '@/components/ui/DangerButton.vue'
import Button from '@/components/ui/Button.vue'
import TagInput from '@/components/ui/TagInput.vue'

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

// Existing tags across every trait — the free-form tag field's autocomplete.
// Case-insensitively deduped (first spelling wins) and sorted, so the dropdown
// stays stable. TagInput hides the ones already on the trait.
const tagSuggestions = computed(() => {
  const seen = new Map()
  for (const ts of (traitsets.value || [])) {
    for (const t of (ts.traits || [])) {
      for (const tag of (t.tags || [])) {
        const key = String(tag).toLowerCase()
        if (key && !seen.has(key)) seen.set(key, String(tag))
      }
    }
  }
  return [...seen.values()].sort((a, b) => a.localeCompare(b))
})

// ── Edit mode form ──
const form = reactive({
  name: '',
  universes: [],
  defaultDieType: 'D6',
  defaultRatingType: 'STATIC',
  defaultEgo: false,
  polarity: '',
  tags: [],   // free-form labels a condition/target can match on (B116) — edited via TagInput
  possibleSfxIds: [],
  defaultSfxIds: [],
  possibleSubtraitIds: [],
  possibleSubtraitsetIds: [],
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
    form.defaultEgo = t.defaultEgo || false
    form.polarity = t.polarity || ''
    form.tags = [...(t.tags || [])]
    form.possibleSfxIds = [...(t.possibleSfxIds || [])]
    form.defaultSfxIds = [...(t.defaultSfxIds || [])]
    form.possibleSubtraitIds = [...(t.possibleSubtraitIds || [])]
    form.possibleSubtraitsetIds = [...(t.possibleSubtraitsetIds || [])]
    syncDisplayNamesFromTrait(t)
  }
}, { immediate: true })

let saveTimer = null
watch([
  () => form.name, () => [...form.universes], () => form.defaultDieType,
  () => form.defaultRatingType, () => form.defaultEgo,
  () => form.polarity, () => [...form.tags],
  () => [...form.possibleSfxIds], () => [...form.defaultSfxIds], () => [...form.possibleSubtraitIds], () => [...form.possibleSubtraitsetIds],
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
    { id: trait.value.id, input: { name: form.name, universes: form.universes, defaultDieType: form.defaultDieType, defaultRatingType: form.defaultRatingType, defaultEgo: form.defaultEgo, tags: form.tags, polarity: form.polarity || null, clearPolarity: !form.polarity, possibleSfxIds: form.possibleSfxIds, defaultSfxIds: form.defaultSfxIds, possibleSubtraitIds: form.possibleSubtraitIds, possibleSubtraitsetIds: form.possibleSubtraitsetIds } }
  )
  patchData('traits', trait.value.id, {
    name: form.name, universes: [...form.universes], defaultDieType: form.defaultDieType,
    defaultRatingType: form.defaultRatingType, defaultEgo: form.defaultEgo,
    tags: [...form.tags],
    polarity: form.polarity || null,
    possibleSfxIds: [...form.possibleSfxIds],
    defaultSfxIds: [...form.defaultSfxIds],
    possibleSubtraitIds: [...form.possibleSubtraitIds],
    possibleSubtraitsetIds: [...form.possibleSubtraitsetIds],
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
const createForm = reactive({
  name: '',
  universes: [],
  defaultDieType: 'D6',
  defaultRatingType: 'STATIC',
  defaultEgo: false,
  polarity: '',
  tags: [],
  possibleSfxIds: [],
  defaultSfxIds: [],
  possibleSubtraitIds: [],
  possibleSubtraitsetIds: [],
})
const createError = ref('')

function generateTraitId(name) {
  return 'trait-' + name.trim().toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')
}

// Create mode: universes restricted to the target traitset (same as edit mode).
const createAllowedUniverses = computed(() => {
  const ts = (traitsets.value || []).find((t) => t.id === props.traitsetId)
  if (!ts) return []
  return (ts.universes || []).map((u) => universeOptions.value.find((o) => o.value === u) || { label: u, value: u })
})

function createToggleUniverse(value) {
  const idx = createForm.universes.indexOf(value)
  if (idx === -1) createForm.universes.push(value)
  else createForm.universes.splice(idx, 1)
}

// Default a new trait to the traitset's universes (all enabled) — a trait with
// no universes would be usable nowhere.
watch(createAllowedUniverses, (allowed) => {
  if (allowed.length && createForm.universes.length === 0) {
    createForm.universes = allowed.map((u) => u.value)
  }
}, { immediate: true })

async function onCreate() {
  if (!createForm.name.trim()) return
  saving.value = true
  createError.value = ''
  try {
    const tsId = props.traitsetId || trait.value?.traitsetId || ''
    const input = {
      id: generateTraitId(createForm.name),
      name: createForm.name.trim(),
      universes: [...createForm.universes],
      traitsetId: tsId,
      defaultDieType: createForm.defaultDieType,
      defaultRatingType: createForm.defaultRatingType,
      defaultEgo: createForm.defaultEgo,
      tags: [...createForm.tags],
      polarity: createForm.polarity || null,
      possibleSfxIds: [...createForm.possibleSfxIds],
      defaultSfxIds: [...createForm.defaultSfxIds],
      possibleSubtraitIds: [...createForm.possibleSubtraitIds],
      possibleSubtraitsetIds: [...createForm.possibleSubtraitsetIds],
      displayNames: [],
    }
    await graphql(`mutation($input: TraitInput!) { createTrait(input: $input) { id } }`, { input })
    await fetchTraitsConfig()
    panel.close()
  } catch (e) {
    const msg = e?.message || 'Create failed'
    createError.value = /unique|already exists|conflicting key/i.test(msg)
      ? `"${createForm.name.trim()}" already exists`
      : msg
  } finally { saving.value = false }
}

// ── Create-mode SFX / sub-trait helpers (mirror edit mode against createForm) ──
const createPossibleSfxs = computed(() =>
  allSfxs.value.filter((s) => createForm.possibleSfxIds.includes(s.id))
)

function createRemovePossibleSfx(id) {
  createForm.possibleSfxIds = createForm.possibleSfxIds.filter((sid) => sid !== id)
  createForm.defaultSfxIds = createForm.defaultSfxIds.filter((sid) => sid !== id)
}

function createToggleDefaultSfx(id) {
  if (createForm.defaultSfxIds.includes(id)) {
    createForm.defaultSfxIds = createForm.defaultSfxIds.filter((sid) => sid !== id)
  } else {
    createForm.defaultSfxIds.push(id)
  }
}

function createOpenSfxPicker() {
  panel.open({
    component: GmSfxPickerPanel,
    title: 'Add SFX to Trait',
    props: {
      selectedIds: [...createForm.possibleSfxIds],
    },
    listeners: {
      'add-sfx': (id) => {
        if (!createForm.possibleSfxIds.includes(id)) createForm.possibleSfxIds.push(id)
      },
      'remove-sfx': (id) => {
        createForm.possibleSfxIds = createForm.possibleSfxIds.filter((sid) => sid !== id)
      },
    },
  })
}

const newSubtargetCreate = ref('')
const createPossibleSubtargetItems = computed(() => [
  ...(createForm.possibleSubtraitsetIds || []).map((id) => ({ key: 'set:' + id, kind: 'set', name: subtraitsetMap.value[id]?.name || id, traitsetName: '' })),
  ...(createForm.possibleSubtraitIds || []).map((id) => ({ key: 'trait:' + id, kind: 'trait', name: subtraitTraitMap.value[id]?.name || id, traitsetName: subtraitTraitMap.value[id]?.traitsetName || '' })),
])

function createUnassignedSubtraitsets() {
  return subtraitTraitsets.value.filter((ts) => !createForm.possibleSubtraitsetIds.includes(ts.id))
}

function createUnassignedSubtraitOptions(ts) {
  return (ts.traits || []).filter((t) => !createForm.possibleSubtraitIds.includes(t.id))
}

function createAddSubtarget() {
  if (!newSubtargetCreate.value) return
  if (newSubtargetCreate.value.startsWith('set:')) {
    const id = newSubtargetCreate.value.slice(4)
    if (!createForm.possibleSubtraitsetIds.includes(id)) createForm.possibleSubtraitsetIds.push(id)
  } else {
    const id = newSubtargetCreate.value.slice(6)
    if (!createForm.possibleSubtraitIds.includes(id)) createForm.possibleSubtraitIds.push(id)
  }
  newSubtargetCreate.value = ''
}

function createRemovePossibleSubtarget(key) {
  if (key.startsWith('set:')) {
    createForm.possibleSubtraitsetIds = createForm.possibleSubtraitsetIds.filter((id) => id !== key.slice(4))
  } else {
    createForm.possibleSubtraitIds = createForm.possibleSubtraitIds.filter((id) => id !== key.slice(6))
  }
}

// ── Possible SFXs (filtered from all) ──
const possibleSfxs = computed(() =>
  allSfxs.value.filter(s => form.possibleSfxIds.includes(s.id))
)

function removePossibleSfx(id) {
  form.possibleSfxIds = form.possibleSfxIds.filter(sid => sid !== id)
  form.defaultSfxIds = form.defaultSfxIds.filter(sid => sid !== id)
}

// ── Possible Sub-traits (set refs + individual traits) ──
const newSubtarget = ref('')

const subtraitTraitsets = computed(() =>
  (traitsets.value || []).filter(ts => (ts.entityTypes || []).includes('SUBTRAIT'))
)

const subtraitsetMap = computed(() => {
  const m = {}
  for (const ts of subtraitTraitsets.value) m[ts.id] = { id: ts.id, name: ts.name }
  return m
})

const subtraitTraitMap = computed(() => {
  const m = {}
  for (const ts of subtraitTraitsets.value) {
    for (const t of (ts.traits || [])) {
      m[t.id] = { id: t.id, name: t.name, traitsetName: ts.name }
    }
  }
  return m
})

// Assigned entries, unified for display (sets collapsed, traits individual).
const possibleSubtargetItems = computed(() => [
  ...(form.possibleSubtraitsetIds || []).map(id => ({ key: 'set:' + id, kind: 'set', name: subtraitsetMap.value[id]?.name || id, traitsetName: '' })),
  ...(form.possibleSubtraitIds || []).map(id => ({ key: 'trait:' + id, kind: 'trait', name: subtraitTraitMap.value[id]?.name || id, traitsetName: subtraitTraitMap.value[id]?.traitsetName || '' })),
])

function unassignedSubtraitsets() {
  return subtraitTraitsets.value.filter(ts => !form.possibleSubtraitsetIds.includes(ts.id))
}

function unassignedSubtraitOptions(ts) {
  return (ts.traits || []).filter(t => !form.possibleSubtraitIds.includes(t.id))
}

function addSubtarget() {
  if (!newSubtarget.value) return
  if (newSubtarget.value.startsWith('set:')) {
    const id = newSubtarget.value.slice(4)
    if (!form.possibleSubtraitsetIds.includes(id)) form.possibleSubtraitsetIds.push(id)
  } else {
    const id = newSubtarget.value.slice(6)
    if (!form.possibleSubtraitIds.includes(id)) form.possibleSubtraitIds.push(id)
  }
  newSubtarget.value = ''
}

function removePossibleSubtarget(key) {
  if (key.startsWith('set:')) {
    form.possibleSubtraitsetIds = form.possibleSubtraitsetIds.filter(id => id !== key.slice(4))
  } else {
    form.possibleSubtraitIds = form.possibleSubtraitIds.filter(id => id !== key.slice(6))
  }
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
  background: var(--overlay-6);
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
  background: var(--accent-12);
}
.universe-chip:not(.enabled) {
  border-color: var(--danger);
  color: var(--danger);
  background: var(--danger-12);
}
.sfx-name { flex: 1; font-weight: 500; }
.vx-toggle {
  flex-shrink: 0;
  width: 22px; height: 22px;
  display: inline-flex; align-items: center; justify-content: center;
  font-size: 12px; line-height: 1; font-weight: 700;
  border-radius: 4px;
  border: 1px solid var(--text-dim);
  background: transparent;
  color: var(--text-dim);
  cursor: pointer;
  padding: 0;
}
.vx-toggle.is-on {
  border-color: var(--success);
  color: var(--success);
  background: var(--success-12);
}
.sfx-trigger { font-size: 10px; color: var(--text-dim); }
.subtrait-add { display: flex; gap: 6px; margin-top: 4px; }
.subtrait-add select { flex: 1; font-size: 12px; padding: 6px 8px; }
.subtarget-kind {
  flex-shrink: 0;
  font-size: 9px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  padding: 1px 6px;
  border-radius: 999px;
  border: 1px solid var(--text-dim);
  color: var(--text-dim);
}
.subtarget-kind.set { border-color: var(--accent); color: var(--accent); }

.create-actions { display: flex; gap: 6px; margin-top: 4px; }

/* Display Names (read-only list) */
.dn-name { font-weight: 500; min-width: 120px; }
.dn-universe { font-size: 10px; color: var(--text-dim); min-width: 80px; }
.dn-ratings { display: flex; align-items: center; gap: 2px; flex: 1; }
.dn-rating { display: inline-flex; align-items: center; gap: 2px; }
.die-chip { display: inline-block; padding: 1px 5px; background: var(--overlay-10); border-radius: 3px; font-size: 10px; font-weight: 600; }
.dn-sep { color: var(--text-dim); margin: 0 2px; font-size: 10px; }
</style>
