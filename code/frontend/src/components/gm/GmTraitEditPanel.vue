<template>
  <div>
    <!-- Trait details form (auto-save) -->
    <div class="ps-form">
      <label>Name</label>
      <input v-model="form.name" />
      <label>Default Die Type</label>
      <select v-model="form.defaultDieType">
        <option value="D4">d4</option>
        <option value="D6">d6</option>
        <option value="D8">d8</option>
        <option value="D10">d10</option>
        <option value="D12">d12</option>
      </select>
      <label>Default Rating Type</label>
      <select v-model="form.defaultRatingType">
        <option value="STATIC">Static</option>
        <option value="RESOURCE">Resource</option>
        <option value="CHALLENGE">Challenge</option>
        <option value="EMPTY">Empty</option>
      </select>
      <label class="checkbox-label">
        <input type="checkbox" v-model="form.locationRestricted" />
        Location Restricted
      </label>
    </div>

    <!-- SFX list -->
    <h4 class="ps-section-title">SFXs</h4>
    <div class="ps-list">
      <div v-for="s in sfxs" :key="s.id" class="entity-row"
        :class="{ selected: selectedId === s.id, 'patch-flash': s._flash }"
        @click="$emit('select', s)">
        <span class="entity-name">{{ s.name }}</span>
        <span style="font-size:10px;color:var(--text-dim)">{{ s.trigger||'—' }}</span>
        <button class="delete-btn" @click.stop="onDeleteSfx(s.id)" title="Delete SFX">×</button>
      </div>
      <div v-if="sfxs.length === 0 && !showSfxCreate" class="empty">No SFXs</div>
    </div>

    <!-- Inline SFX create form -->
    <div v-if="showSfxCreate" class="create-form">
      <label>ID</label>
      <input v-model="sfxCreate.id" placeholder="sfx-my-sfx" />
      <label>Name</label>
      <input v-model="sfxCreate.name" placeholder="SFX name…" />
      <label>Trigger</label>
      <select v-model="sfxCreate.trigger">
        <option value="">--</option>
        <option value="on_activate">On Activate</option>
        <option value="on_roll">On Roll</option>
        <option value="on_complication">On Complication</option>
        <option value="on_botch">On Botch</option>
        <option value="on_success">On Success</option>
        <option value="on_failure">On Failure</option>
        <option value="on_location_change">On Location Change</option>
        <option value="on_trait_change">On Trait Change</option>
      </select>
      <label>Description</label>
      <input v-model="sfxCreate.description" placeholder="What it does…" />
      <div class="create-actions">
        <button class="save-btn" @click="onCreateSfx" :disabled="sfxSaving || !sfxCreate.id.trim() || !sfxCreate.name.trim()">{{ sfxSaving ? 'Creating…' : 'Create' }}</button>
        <button class="cancel-btn" @click="showSfxCreate = false">Cancel</button>
      </div>
    </div>

    <button v-if="!showSfxCreate" class="ps-add-btn" @click="startSfxCreate">+ New SFX</button>

    <!-- Danger zone -->
    <div class="danger-zone">
      <button class="danger-btn" @click="onDelete" :disabled="saving">
        {{ saving ? 'Deleting…' : 'Delete Trait' }}
      </button>
    </div>
  </div>
</template>

<script setup>
import { reactive, ref, watch } from 'vue'
import { useApi } from '@/composables/useApi.js'

const { graphql } = useApi()

const props = defineProps({
  trait: { type: Object, default: null },
  sfxs: { type: Array, default: () => [] },
  selectedId: { type: String, default: '' },
  onRefresh: { type: Function, default: null },
  onPatch: { type: Function, default: null },
})

defineEmits(['select'])

const saving = ref(false)
const sfxSaving = ref(false)

// ── SFX create ──

const showSfxCreate = ref(false)
const sfxCreate = reactive({
  id: '',
  name: '',
  trigger: '',
  description: '',
})

function startSfxCreate() {
  sfxCreate.id = ''
  sfxCreate.name = ''
  sfxCreate.trigger = ''
  sfxCreate.description = ''
  showSfxCreate.value = true
}

async function onCreateSfx() {
  sfxSaving.value = true
  try {
    await graphql(
      `mutation($input: SfxInput!) { createSfx(input: $input) { id } }`,
      { input: { id: sfxCreate.id.trim(), name: sfxCreate.name.trim(), trigger: sfxCreate.trigger || '', description: sfxCreate.description || '' } }
    )
    showSfxCreate.value = false
    if (props.onRefresh) await props.onRefresh()
  } finally {
    sfxSaving.value = false
  }
}

async function onDeleteSfx(sfxId) {
  if (!confirm(`Delete SFX "${sfxId}"? This cannot be undone.`)) return
  sfxSaving.value = true
  try {
    await graphql(`mutation($id: ID!) { deleteSfx(id: $id) }`, { id: sfxId })
    if (props.onRefresh) await props.onRefresh()
  } finally {
    sfxSaving.value = false
  }
}

const form = reactive({
  name: '',
  defaultDieType: 'D6',
  defaultRatingType: 'STATIC',
  locationRestricted: false,
})

watch(() => props.trait, (t) => {
  if (t) {
    form.name = t.name || ''
    form.defaultDieType = t.defaultDieType || 'D6'
    form.defaultRatingType = t.defaultRatingType || 'STATIC'
    form.locationRestricted = t.locationRestricted || false
  }
}, { immediate: true })

let saveTimer = null
watch([() => form.name, () => form.defaultDieType, () => form.defaultRatingType, () => form.locationRestricted], () => {
  if (saving.value) return
  clearTimeout(saveTimer)
  saveTimer = setTimeout(() => save(), 600)
})

async function save() {
  if (!props.trait?.id) return
  saving.value = true
  await graphql(
    `mutation($id: ID!, $input: TraitUpdateInput!) { updateTrait(id: $id, input: $input) { id } }`,
    {
      id: props.trait.id,
      input: {
        name: form.name,
        defaultDieType: form.defaultDieType,
        defaultRatingType: form.defaultRatingType,
        locationRestricted: form.locationRestricted,
      },
    }
  )
  if (props.onPatch) props.onPatch('traits', props.trait.id, {
    name: form.name,
    defaultDieType: form.defaultDieType,
    defaultRatingType: form.defaultRatingType,
    locationRestricted: form.locationRestricted,
  })
  setTimeout(() => { saving.value = false }, 200)
}

async function onDelete() {
  if (!props.trait?.id) return
  if (!confirm(`Delete trait "${props.trait.name}"? This will also remove all trait settings referencing it.`)) return
  saving.value = true
  try {
    await graphql(`mutation($id: ID!) { deleteTrait(id: $id) }`, { id: props.trait.id })
    if (props.onRefresh) await props.onRefresh()
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.ps-form { display: flex; flex-direction: column; gap: 6px; }
.ps-form label { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.5px; }
.ps-form input, .ps-form select { font-size: 12px; padding: 6px 8px; }
.checkbox-label { display: flex; align-items: center; gap: 6px; font-size: 11px; text-transform: none; cursor: pointer; }
.checkbox-label input { width: auto; }

.ps-section-title {
  font-size: 11px; color: var(--text-dim); text-transform: uppercase;
  letter-spacing: 1px; margin-top: 12px; padding-top: 8px;
  border-top: 1px solid rgba(255,255,255,0.08);
}
.ps-list { display: flex; flex-direction: column; gap: 3px; }
.entity-row {
  display: flex; align-items: center; gap: 6px; padding: 8px 10px;
  border-radius: 6px; cursor: pointer;
  background: rgba(255,255,255,0.03);
  transition: background 0.15s; font-size: 13px;
}
.entity-row:hover { background: rgba(255,255,255,0.06); }
.entity-row.selected { background: rgba(64,136,212,0.15); border: 1px solid var(--accent-dim); }
.entity-name { flex: 1; font-weight: 500; }
.empty { font-size: 12px; color: var(--text-dim); padding: 12px 0; text-align: center; }
.delete-btn { font-size: 14px; padding: 2px 6px; background: none; color: var(--danger); border-radius: 4px; cursor: pointer; }
.delete-btn:hover { background: rgba(212,64,64,0.15); }

.create-form { display: flex; flex-direction: column; gap: 6px; margin-top: 8px; padding: 8px; background: rgba(255,255,255,0.03); border-radius: 6px; }
.create-form label { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.5px; }
.create-form input, .create-form select { font-size: 12px; padding: 6px 8px; }
.create-actions { display: flex; gap: 6px; margin-top: 4px; }
.save-btn { background: var(--success); color: #0a0a0f; font-weight: 600; padding: 6px 12px; border-radius: 6px; border: none; cursor: pointer; font-size: 12px; }
.save-btn:disabled { opacity: 0.5; cursor: default; }
.cancel-btn { background: rgba(255,255,255,0.08); color: var(--text-dim); padding: 6px 12px; border-radius: 6px; border: none; cursor: pointer; font-size: 12px; }

.ps-add-btn {
  font-size: 12px; padding: 6px; margin-top: 8px;
  background: var(--accent-dim); color: var(--text);
  border-radius: 6px; border: none; cursor: pointer; width: 100%;
}
.ps-add-btn:hover { background: var(--accent); }

.danger-zone { margin-top: 10px; padding-top: 8px; border-top: 1px solid rgba(212,64,64,0.2); }
.danger-btn {
  width: 100%; font-size: 12px; padding: 6px;
  background: rgba(212,64,64,0.12); color: var(--danger);
  border: 1px solid rgba(212,64,64,0.25); border-radius: 6px;
  cursor: pointer; transition: background 0.15s;
}
.danger-btn:hover { background: rgba(212,64,64,0.25); }
.danger-btn:disabled { opacity: 0.4; cursor: default; }
</style>
