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
    </div>

    <h4 class="ps-section-title">Traits</h4>
    <div class="ps-list">
      <div v-for="t in traits" :key="t.id" class="entity-row"
        :class="{ selected: selectedId === t.id, 'patch-flash': t._flash }"
        @click="onTraitClick(t)">
        <span class="entity-name">{{ t.name }}</span>
        <span :class="'die-' + (t.defaultDieType||'d6').toLowerCase()" style="font-weight:700;font-size:11px">{{ t.defaultDieType||'d6' }}</span>
      </div>
      <div v-if="traits.length === 0" class="empty">No traits in this set</div>
    </div>
    <button class="ps-add-btn" @click="onNewTrait">+ New Trait</button>

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
import { reactive, ref, watch, computed } from 'vue'
import { useApi } from '@/composables/useApi.js'
import { useTraitsConfig } from '@/composables/useTraitsConfig.js'
import { usePanel } from '@/composables/usePanel.js'
import ChipInput from './ChipInput.vue'
import GmTraitEditPanel from '@/components/gm/GmTraitEditPanel.vue'
import DangerButton from '@/components/gm/DangerButton.vue'

const { graphql } = useApi()
const panel = usePanel()
const { traitsets, allSfxs, fetchTraitsConfig, patchData } = useTraitsConfig()

const universeOptions = [
  { label: 'Earth', value: 'earth' },
  { label: 'Three Realms', value: 'three_realms' },
]
const entityTypeOptions = [
  { label: 'Character', value: 'CHARACTER' },
  { label: 'Location', value: 'LOCATION' },
  { label: 'GMC', value: 'GMC' },
  { label: 'Faction', value: 'FACTION' },
  { label: 'Asset', value: 'ASSET' },
]

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
const form = reactive({ name: '', universes: [], entityTypes: [], limit: 1 })

watch(traitset, (ts) => {
  if (ts) {
    form.name = ts.name || ''
    form.universes = [...(ts.universes || [])]
    form.entityTypes = [...(ts.entityTypes || [])]
    form.limit = ts.limit || 1
  }
}, { immediate: true })

let saveTimer = null
watch([() => form.name, () => [...form.universes], () => [...form.entityTypes], () => form.limit], () => {
  clearTimeout(saveTimer)
  saveTimer = setTimeout(() => saveTraitset(), 600)
})

async function saveTraitset() {
  if (!traitset.value?.id) return
  await graphql(
    `mutation($id: ID!, $name: String, $universes: [String!], $entityTypes: [EntityType!], $limit: Int) { updateTraitset(id: $id, name: $name, universes: $universes, entityTypes: $entityTypes, limit: $limit) { id } }`,
    { id: traitset.value.id, name: form.name, universes: form.universes, entityTypes: form.entityTypes, limit: form.limit }
  )
  patchData('traitsets', traitset.value.id, {
    name: form.name, universes: [...form.universes], entityTypes: [...form.entityTypes], limit: form.limit,
  })
}

function onTraitClick(t) {
  panel.open({
    component: GmTraitEditPanel,
    title: t.name,
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

async function onDeleteTraitset() {
  if (!traitset.value?.id) return
  saving.value = true
  try {
    await graphql(`mutation($id: ID!) { deleteTraitset(id: $id) }`, { id: traitset.value.id })
    await fetchTraitsConfig()
    panel.close()
  } finally { saving.value = false }
}
</script>

<style scoped>
.ps-form { display: flex; flex-direction: column; gap: 6px; }
.ps-form label { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.5px; }
.ps-form input { font-size: 12px; padding: 6px 8px; }
.ps-section-title { font-size: 11px; color: var(--text-dim); text-transform: uppercase; letter-spacing: 1px; margin-top: 12px; padding-top: 8px; border-top: 1px solid rgba(255,255,255,0.08); }
.ps-list { display: flex; flex-direction: column; gap: 3px; }
.entity-row { display: flex; align-items: center; gap: 6px; padding: 8px 10px; border-radius: 6px; cursor: pointer; background: rgba(255,255,255,0.03); transition: background 0.15s; font-size: 13px; }
.entity-row:hover { background: rgba(255,255,255,0.06); }
.entity-row.selected { background: rgba(64,136,212,0.15); border: 1px solid var(--accent-dim); }
.entity-name { flex: 1; font-weight: 500; }
.empty { font-size: 12px; color: var(--text-dim); padding: 12px 0; text-align: center; }
.ps-add-btn { font-size: 12px; padding: 6px; margin-top: 8px; background: var(--accent-dim); color: var(--text); border-radius: 6px; border: none; cursor: pointer; width: 100%; }
.ps-add-btn:hover { background: var(--accent); }
.danger-zone { margin-top: 10px; padding-top: 8px; border-top: 1px solid rgba(212,64,64,0.2); }
</style>
