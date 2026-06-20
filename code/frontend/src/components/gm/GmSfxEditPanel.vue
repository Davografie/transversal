<template>
  <div>
    <!-- Edit mode -->
    <template v-if="sfx">
      <div class="ps-form">
        <label>Name</label>
        <input v-model="form.name" />
        <label>Trigger</label>
        <select v-model="form.trigger">
          <option value="">--</option>
          <option value="on_activate">On Activate</option><option value="on_roll">On Roll</option>
          <option value="on_complication">On Complication</option><option value="on_botch">On Botch</option>
          <option value="on_success">On Success</option><option value="on_failure">On Failure</option>
          <option value="on_location_change">On Location Change</option><option value="on_trait_change">On Trait Change</option>
        </select>
        <label>Description</label>
        <textarea v-model="form.description" rows="3"></textarea>
        <button class="save-btn" @click="onSave" :disabled="saving">{{ saving ? 'Saving…' : 'Save' }}</button>
      </div>
      <div class="danger-zone">
        <button class="danger-btn" @click="onDelete" :disabled="saving">{{ saving ? 'Deleting…' : 'Delete SFX' }}</button>
      </div>
    </template>

    <!-- Create mode -->
    <template v-else>
      <div class="ps-form">
        <label>ID</label>
        <input v-model="createForm.id" placeholder="sfx-my-sfx" />
        <label>Name</label>
        <input v-model="createForm.name" placeholder="SFX name…" />
        <label>Trigger</label>
        <select v-model="createForm.trigger">
          <option value="">--</option>
          <option value="on_activate">On Activate</option><option value="on_roll">On Roll</option>
          <option value="on_complication">On Complication</option><option value="on_botch">On Botch</option>
          <option value="on_success">On Success</option><option value="on_failure">On Failure</option>
          <option value="on_location_change">On Location Change</option><option value="on_trait_change">On Trait Change</option>
        </select>
        <label>Description</label>
        <input v-model="createForm.description" placeholder="What it does…" />
        <div class="create-actions">
          <button class="save-btn" @click="onCreate" :disabled="saving || !createForm.id.trim() || !createForm.name.trim()">{{ saving ? 'Creating…' : 'Create SFX' }}</button>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { useApi } from '@/composables/useApi.js'

const { graphql } = useApi()

const props = defineProps({
  sfx: { type: Object, default: null },  // null = create mode
  onRefresh: { type: Function, default: null },
  onPatch: { type: Function, default: null },
})

const saving = ref(false)

// ── Edit mode ──
const form = reactive({ name: props.sfx?.name || '', trigger: props.sfx?.trigger || '', description: props.sfx?.description || '' })

async function onSave() {
  if (!props.sfx?.id) return
  saving.value = true
  try {
    await graphql(
      `mutation($input: SfxUpdateInput!) { updateSfx(input: $input) { id } }`,
      { input: { id: props.sfx.id, name: form.name, trigger: form.trigger || null, description: form.description || null } }
    )
    if (props.onPatch) props.onPatch('sfxs', props.sfx.id, { name: form.name, trigger: form.trigger || null, description: form.description || null })
  } finally { saving.value = false }
}

async function onDelete() {
  if (!props.sfx?.id) return
  if (!confirm(`Delete SFX "${props.sfx.name}"? This cannot be undone.`)) return
  saving.value = true
  try { await graphql(`mutation($id: ID!) { deleteSfx(id: $id) }`, { id: props.sfx.id }); if (props.onRefresh) await props.onRefresh() }
  finally { saving.value = false }
}

// ── Create mode ──
const createForm = reactive({ id: '', name: '', trigger: '', description: '' })

async function onCreate() {
  saving.value = true
  try {
    await graphql(
      `mutation($input: SfxInput!) { createSfx(input: $input) { id } }`,
      { input: { id: createForm.id.trim(), name: createForm.name.trim(), trigger: createForm.trigger || '', description: createForm.description || '' } }
    )
    if (props.onRefresh) await props.onRefresh()
  } finally { saving.value = false }
}
</script>

<style scoped>
.ps-form { display: flex; flex-direction: column; gap: 6px; }
.ps-form label { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.5px; }
.ps-form input, .ps-form select, .ps-form textarea { font-size: 12px; padding: 6px 8px; }
.save-btn { background: var(--success); color: #0a0a0f; font-weight: 600; padding: 6px 12px; border-radius: 6px; border: none; cursor: pointer; font-size: 12px; }
.save-btn:disabled { opacity: 0.5; cursor: default; }
.create-actions { display: flex; gap: 6px; margin-top: 4px; }
.danger-zone { margin-top: 10px; padding-top: 8px; border-top: 1px solid rgba(212,64,64,0.2); }
.danger-btn { width: 100%; font-size: 12px; padding: 6px; background: rgba(212,64,64,0.12); color: var(--danger); border: 1px solid rgba(212,64,64,0.25); border-radius: 6px; cursor: pointer; transition: background 0.15s; }
.danger-btn:hover { background: rgba(212,64,64,0.25); }
.danger-btn:disabled { opacity: 0.4; cursor: default; }
</style>
