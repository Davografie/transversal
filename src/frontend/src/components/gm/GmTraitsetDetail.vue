<template>
  <div>
    <div class="ps-form">
      <label>Name</label>
      <input v-model="form.name" />
      <label>Universes</label>
      <ChipInput v-model="form.universes" :options="universeOptions" placeholder="Add universe…" />
      <label>Entity Types</label>
      <ChipInput v-model="form.entityTypes" :options="entityTypeOptions" placeholder="Add type…" />
      <label>Limit</label>
      <input v-model.number="form.limit" type="number" min="1" />
      <label>Polarity</label>
      <select v-model="form.polarity">
        <option value="">Inherit (positive)</option>
        <option value="POSITIVE">Positive</option>
        <option value="NEGATIVE">Negative</option>
      </select>
      <label class="checkbox-label"><input type="checkbox" v-model="form.allowDuplicates" /> Allow duplicate trait instances</label>
    </div>

    <h4 class="ps-section-title">Traits</h4>
    <div class="trait-head-actions">
      <button class="ps-add-btn" @click="onNewTrait">+ New Trait</button>
      <button class="ps-add-btn" @click="openBatchEdit">Batch Edit</button>
    </div>
    <GmList
      :items="traits"
      item-key="id"
      :selected-ids="selectedId ? [selectedId] : []"
      empty-text="No traits in this set"
      :row-class="(t) => (t._flash ? 'patch-flash' : '')"
      @click="onTraitClick"
    >
      <template #item="{ item: t }">
        <span class="entity-name">{{ t.name }}</span>
        <span :class="'die-' + (t.defaultDieType||'d6').toLowerCase()" style="font-weight:700;font-size:11px">{{ t.defaultDieType||'d6' }}</span>
      </template>
    </GmList>

    <div class="danger-zone">
      <DangerButton
        label="Delete Traitset"
        loading-label="Deleting…"
        :disabled="saving"
        @confirm="onDeleteTraitset"
      />
    </div>
  </div>
</template>

<script setup>
import { reactive, ref, watch, computed, onMounted } from 'vue'
import { ENTITY_TYPES } from '@/constants/entityTypes.js'
import { useApi } from '@/composables/useApi.js'
import { useTraitsConfig } from '@/composables/useTraitsConfig.js'
import { usePanel } from '@/composables/usePanel.js'
import ChipInput from './ChipInput.vue'
import GmTraitEditPanel from '@/components/gm/GmTraitEditPanel.vue'
import GmTraitBatchEditPanel from '@/components/gm/GmTraitBatchEditPanel.vue'
import GmList from './GmList.vue'
import DangerButton from '@/components/gm/DangerButton.vue'

const { graphql } = useApi()
const panel = usePanel()
const { traitsets, allSfxs, fetchTraitsConfig, patchData } = useTraitsConfig()

const universeOptions = ref([])

async function loadUniverseOptions() {
  try {
    const res = await graphql(`query($type: EntityType){ entities(type: $type){ id name currentUniverse } }`, { type: 'UNIVERSE' })
    universeOptions.value = (res?.entities || []).map(u => ({ value: u.currentUniverse, label: u.name }))
  } catch { /* leave empty */ }
}
const ENTITY_TYPE_LABELS = {
  CHARACTER: 'Character',
  GMC: 'GMC',
  ASSET: 'Asset',
  FACTION: 'Faction',
  LOCATION: 'Location',
}
// Universes don't carry traitsets, so they're excluded from the selector.
const entityTypeOptions = ENTITY_TYPES
  .filter(t => t !== 'UNIVERSE')
  .map(t => ({ label: ENTITY_TYPE_LABELS[t], value: t }))

const props = defineProps({
  traitsetId: { type: String, default: '' },
  selectedId: { type: String, default: '' },
})

// Derive traitset/traits reactively from the composable ref — stays current after refresh
const traitset = computed(() => {
  return traitsets.value.find(ts => ts.id === props.traitsetId) || null
})
const traits = computed(() => traitset.value?.traits || [])

// Close self if traitset was deleted
watch(traitset, (ts) => {
  if (!ts) panel.close()
})

const saving = ref(false)
const form = reactive({ name: '', universes: [], entityTypes: [], limit: 1, polarity: '', allowDuplicates: false })

watch(traitset, (ts) => {
  if (ts) {
    form.name = ts.name || ''
    form.universes = [...(ts.universes || [])]
    form.entityTypes = [...(ts.entityTypes || [])]
    form.limit = ts.limit || 1
    form.polarity = ts.polarity || ''
    form.allowDuplicates = !!ts.allowDuplicates
  }
}, { immediate: true })

let saveTimer = null
watch([() => form.name, () => [...form.universes], () => [...form.entityTypes], () => form.limit, () => form.polarity, () => form.allowDuplicates], () => {
  clearTimeout(saveTimer)
  saveTimer = setTimeout(() => saveTraitset(), 600)
})

async function saveTraitset() {
  if (!traitset.value?.id) return
  await graphql(
    `mutation($id: ID!, $name: String, $universes: [String!], $entityTypes: [EntityType!], $limit: Int, $polarity: Polarity, $clearPolarity: Boolean, $allowDuplicates: Boolean) { updateTraitset(id: $id, name: $name, universes: $universes, entityTypes: $entityTypes, limit: $limit, polarity: $polarity, clearPolarity: $clearPolarity, allowDuplicates: $allowDuplicates) { id } }`,
    { id: traitset.value.id, name: form.name, universes: form.universes, entityTypes: form.entityTypes, limit: form.limit, polarity: form.polarity || null, clearPolarity: !form.polarity, allowDuplicates: form.allowDuplicates }
  )
  patchData('traitsets', traitset.value.id, {
    name: form.name, universes: [...form.universes], entityTypes: [...form.entityTypes], limit: form.limit, polarity: form.polarity || null, allowDuplicates: form.allowDuplicates,
  })
}

function onTraitClick(t) {
  panel.open({
    component: GmTraitEditPanel,
    title: t.name,
    id: t.id,
    props: { traitId: t.id, traitsetId: props.traitsetId },
  })
}

function onNewTrait() {
  panel.open({
    component: GmTraitEditPanel,
    title: 'New Trait',
    props: { traitId: null, traitsetId: traitset.value?.id },
  })
}

function openBatchEdit() {
  panel.open({
    component: GmTraitBatchEditPanel,
    title: 'Batch Edit Traits',
    props: { initialTraitsetId: props.traitsetId },
  })
}

async function onDeleteTraitset() {
  if (!traitset.value?.id) return
  saving.value = true
  try {
    await graphql(`mutation($id: ID!) { deleteTraitset(id: $id) }`, { id: traitset.value.id })
    await fetchTraitsConfig()
    panel.close()
  } finally { saving.value = false }
}

onMounted(loadUniverseOptions)
</script>

<style scoped>
.ps-form input { font-size: 12px; padding: 6px 8px; }
.checkbox-label { display: flex; align-items: center; gap: 6px; font-size: 11px; text-transform: none; cursor: pointer; margin-top: 8px; }
.checkbox-label input { width: auto; }

.trait-head-actions { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; margin-top: 8px; }
.trait-head-actions .ps-add-btn { margin-top: 0; width: auto; }
</style>
