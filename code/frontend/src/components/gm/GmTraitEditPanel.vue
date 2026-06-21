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

      <!-- SFX assignment -->
      <h4 class="ps-section-title">Available SFXs</h4>
      <div v-if="allSfxsEffective.length === 0" class="empty">No SFXs defined</div>
      <div v-else class="checkbox-list">
        <div v-for="s in allSfxsEffective" :key="s.id" class="checkbox-row" :class="{ checked: form.possibleSfxIds.includes(s.id) }" @click="onSfxClick(s)">
          <label class="checkbox-inner" @click.stop>
            <input type="checkbox" :value="s.id" v-model="form.possibleSfxIds" />
          </label>
          <span class="sfx-name">{{ s.name }}</span>
          <span class="sfx-trigger">{{ s.trigger || '' }}</span>
        </div>
      </div>
      <button class="ps-add-btn" @click="onNewSfx">+ New SFX</button>

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
})

watch(() => props.trait, (t) => {
  if (t) {
    form.name = t.name || ''
    form.universes = [...(t.universes || [])]
    form.defaultDieType = t.defaultDieType || 'D6'
    form.defaultRatingType = t.defaultRatingType || 'STATIC'
    form.locationRestricted = t.locationRestricted || false
    form.possibleSfxIds = [...(t.possibleSfxIds || [])]
  }
}, { immediate: true })

let saveTimer = null
watch([() => form.name, () => [...form.universes], () => form.defaultDieType, () => form.defaultRatingType, () => form.locationRestricted, () => [...form.possibleSfxIds]], () => {
  if (!props.trait) return
  clearTimeout(saveTimer)
  saveTimer = setTimeout(() => save(), 600)
})

async function save() {
  if (!props.trait?.id) return
  await graphql(
    `mutation($id: ID!, $input: TraitUpdateInput!) { updateTrait(id: $id, input: $input) { id } }`,
    { id: props.trait.id, input: { name: form.name, universes: form.universes, defaultDieType: form.defaultDieType, defaultRatingType: form.defaultRatingType, locationRestricted: form.locationRestricted, possibleSfxIds: form.possibleSfxIds } }
  )
  if (props.onPatch) props.onPatch('traits', props.trait.id, {
    name: form.name, universes: [...form.universes], defaultDieType: form.defaultDieType,
    defaultRatingType: form.defaultRatingType, locationRestricted: form.locationRestricted,
    possibleSfxIds: [...form.possibleSfxIds],
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
      { input: { id: createForm.id.trim(), name: createForm.name.trim(), universes, traitsetId: tsId, defaultDieType: createForm.defaultDieType, defaultRatingType: createForm.defaultRatingType } }
    )
    if (props.onRefresh) await props.onRefresh()
  } finally { saving.value = false }
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

function onNewSfx() {
  if (props.open) {
    props.open({
      component: GmSfxEditPanel,
      title: 'New SFX',
      props: { sfx: null, onRefresh: props.onRefresh, onPatch: props.onPatch },
      listeners: {
        'sfx-created': (created) => {
          localSfxs.value.push(created)
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

.checkbox-list { display: flex; flex-direction: column; gap: 2px; margin-top: 4px; }
.checkbox-row { display: flex; align-items: center; gap: 6px; padding: 4px 8px; border-radius: 4px; cursor: pointer; font-size: 12px; transition: background 0.1s; }
.checkbox-row:hover { background: rgba(255,255,255,0.04); }
.checkbox-row.checked { background: rgba(64,136,212,0.08); }
.checkbox-inner { display: inline-flex; align-items: center; cursor: pointer; }
.checkbox-row input { width: auto; margin: 0; }
.sfx-name { flex: 1; }
.sfx-trigger { font-size: 10px; color: var(--text-dim); }

.empty { font-size: 12px; color: var(--text-dim); padding: 12px 0; text-align: center; }
.ps-add-btn { font-size: 12px; padding: 6px; margin-top: 8px; background: var(--accent-dim); color: var(--text); border-radius: 6px; border: none; cursor: pointer; width: 100%; }
.ps-add-btn:hover { background: var(--accent); }
.create-actions { display: flex; gap: 6px; margin-top: 4px; }
.save-btn { background: var(--success); color: #0a0a0f; font-weight: 600; padding: 6px 12px; border-radius: 6px; border: none; cursor: pointer; font-size: 12px; }
.save-btn:disabled { opacity: 0.5; cursor: default; }
.danger-zone { margin-top: 10px; padding-top: 8px; border-top: 1px solid rgba(212,64,64,0.2); }
.danger-btn { width: 100%; font-size: 12px; padding: 6px; background: rgba(212,64,64,0.12); color: var(--danger); border: 1px solid rgba(212,64,64,0.25); border-radius: 6px; cursor: pointer; transition: background 0.15s; }
.danger-btn:hover { background: rgba(212,64,64,0.25); }
.danger-btn:disabled { opacity: 0.4; cursor: default; }
</style>
