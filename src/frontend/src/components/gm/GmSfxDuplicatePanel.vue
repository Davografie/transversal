<template>
  <div>
    <p class="hint">
      Copying <strong>{{ sourceName }}</strong>. The copy is a <em>new</em> rule and
      is not attached to anything — put it where it belongs afterwards.
    </p>

    <label>Name for the copy</label>
    <input v-model="name" class="name-input" placeholder="SFX name…" @keyup.enter="submit" />

    <div v-if="error" class="error-msg">{{ error }}</div>

    <Button class="ps-add-btn" block variant="secondary" :loading="saving"
            :disabled="!name.trim()" @click="submit">Duplicate</Button>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useApi } from '@/composables/useApi.js'
import Button from '@/components/ui/Button.vue'

const props = defineProps({
  /** The rule being copied. The server reads the *stored* rule, so this is only
   *  needed for its id and the default name. */
  sfx: { type: Object, required: true },
})

const emit = defineEmits(['duplicated'])

const { graphql, error: apiError } = useApi()

const sourceName = props.sfx.name || props.sfx.id
const name = ref(`${sourceName} (copy)`)
const saving = ref(false)
const error = ref('')

// The selection mirrors the `sfxs` query in `useTraitsConfig`, so the object this
// panel hands back is the same shape the editor is opened with from the list.
const DUPLICATE_MUTATION = `mutation($id: ID!, $name: String) {
  duplicateSfx(id: $id, name: $name) {
    id name description trigger limit sourceKind ownerSurfaces
    placement armingScope
    duration { timers { event remaining } combine }
    listenerSpec reach
    boundVariables { name spec }
    conditions { type subject target targets value operator narrative spec }
    effects { timing type action target entity result dieFilter negative context duration { timers { event remaining } combine } targetSpec entitySpec resultSpec ownerSpec refs output conditions { type subject target targets value operator narrative spec } }
  }
}`

async function submit() {
  if (saving.value || !name.value.trim()) return
  saving.value = true
  error.value = ''
  try {
    const data = await graphql(DUPLICATE_MUTATION, { id: props.sfx.id, name: name.value.trim() })
    const created = data?.duplicateSfx
    if (!created) { error.value = apiError.value || 'Duplicate failed'; return }
    emit('duplicated', created)
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.hint { font-size: 11px; color: var(--text-dim); margin: 0 0 10px; line-height: 1.45; }
.name-input { width: 100%; font-size: 12px; padding: 6px 8px; margin-bottom: 10px; box-sizing: border-box;
  background: var(--overlay-6); color: var(--text); border: 1px solid var(--overlay-10); border-radius: 6px; }
.error-msg { font-size: 11px; color: var(--danger); background: var(--danger-8); padding: 6px 10px;
  border-radius: 4px; margin-bottom: 8px; }
</style>
