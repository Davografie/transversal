<template>
  <div>
    <div class="ps-form">
      <label>Name</label>
      <input v-model="form.name" />
      <label>Trigger</label>
      <select v-model="form.trigger">
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
      <textarea v-model="form.description" rows="3"></textarea>
      <button class="save-btn" @click="onSave" :disabled="saving">{{ saving ? 'Saving…' : 'Save' }}</button>
    </div>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { useApi } from '@/composables/useApi.js'

const { graphql } = useApi()

const props = defineProps({
  sfx: { type: Object, default: null },
  onRefresh: { type: Function, default: null },
  onPatch: { type: Function, default: null },
})

const saving = ref(false)

const form = reactive({
  name: props.sfx?.name || '',
  trigger: props.sfx?.trigger || '',
  description: props.sfx?.description || '',
})

async function onSave() {
  if (!props.sfx?.id) return
  saving.value = true
  try {
    await graphql(
      `mutation($input: SfxUpdateInput!) { updateSfx(input: $input) { id } }`,
      { input: { id: props.sfx.id, name: form.name, trigger: form.trigger || null, description: form.description || null } }
    )
    if (props.onPatch) props.onPatch('sfxs', props.sfx.id, {
      name: form.name,
      trigger: form.trigger || null,
      description: form.description || null,
    })
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.ps-form { display: flex; flex-direction: column; gap: 6px; }
.ps-form label { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.5px; }
.ps-form input, .ps-form select, .ps-form textarea { font-size: 12px; padding: 6px 8px; }
.save-btn { background: var(--success) !important; color: #0a0a0f !important; font-weight: 600; margin-top: 4px; padding: 8px; border-radius: 6px; border: none; cursor: pointer; }
</style>
