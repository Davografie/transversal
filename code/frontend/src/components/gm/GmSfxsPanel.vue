<template>
  <div>
    <div class="ps-list">
      <div v-for="s in sfxs" :key="s.id" class="entity-row"
        :class="{ selected: selectedId === s.id }"
        @click="$emit('select', s)">
        <span class="entity-name">{{ s.name }}</span>
        <span style="font-size:10px;color:var(--text-dim)">{{ s.trigger||'—' }}</span>
        <button class="delete-btn" @click.stop="onDelete(s.id)" title="Delete SFX">×</button>
      </div>
      <div v-if="sfxs.length === 0 && !showCreate" class="empty">No SFXs</div>
    </div>

    <!-- Inline create form -->
    <div v-if="showCreate" class="create-form">
      <label>ID</label>
      <input v-model="createForm.id" placeholder="sfx-my-sfx" />
      <label>Name</label>
      <input v-model="createForm.name" placeholder="SFX name…" />
      <label>Trigger</label>
      <select v-model="createForm.trigger">
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
      <input v-model="createForm.description" placeholder="What it does…" />
      <div class="create-actions">
        <button class="save-btn" @click="onCreate" :disabled="saving || !createForm.id.trim() || !createForm.name.trim()">{{ saving ? 'Creating…' : 'Create' }}</button>
        <button class="cancel-btn" @click="showCreate = false">Cancel</button>
      </div>
    </div>

    <button v-if="!showCreate" class="ps-add-btn" @click="startCreate">+ New SFX</button>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { useApi } from '@/composables/useApi.js'

const { graphql } = useApi()

const props = defineProps({
  sfxs: { type: Array, default: () => [] },
  selectedId: { type: String, default: '' },
  onRefresh: { type: Function, default: null },
})

defineEmits(['select', 'close'])

const showCreate = ref(false)
const saving = ref(false)

const createForm = reactive({
  id: '',
  name: '',
  trigger: '',
  description: '',
})

function startCreate() {
  createForm.id = ''
  createForm.name = ''
  createForm.trigger = ''
  createForm.description = ''
  showCreate.value = true
}

async function onCreate() {
  saving.value = true
  try {
    await graphql(
      `mutation($input: SfxInput!) { createSfx(input: $input) { id } }`,
      { input: { id: createForm.id.trim(), name: createForm.name.trim(), trigger: createForm.trigger || '', description: createForm.description || '' } }
    )
    showCreate.value = false
    if (props.onRefresh) await props.onRefresh()
  } finally {
    saving.value = false
  }
}

async function onDelete(sfxId) {
  if (!confirm(`Delete SFX "${sfxId}"? This cannot be undone.`)) return
  saving.value = true
  try {
    await graphql(`mutation($id: ID!) { deleteSfx(id: $id) }`, { id: sfxId })
    if (props.onRefresh) await props.onRefresh()
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.ps-list { display: flex; flex-direction: column; gap: 3px; }
.entity-row { display: flex; align-items: center; gap: 6px; padding: 8px 10px; border-radius: 6px; cursor: pointer; background: rgba(255,255,255,0.03); transition: background 0.15s; font-size: 13px; }
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

.ps-add-btn { font-size: 12px; padding: 6px; margin-top: 8px; background: var(--accent-dim); color: var(--text); border-radius: 6px; border: none; cursor: pointer; width: 100%; }
.ps-add-btn:hover { background: var(--accent); }
</style>
