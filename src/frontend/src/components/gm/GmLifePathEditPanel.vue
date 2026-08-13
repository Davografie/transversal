<template>
  <div class="lpe-root">
    <div class="lpe-field">
      <label>Name</label>
      <input v-model="form.name" placeholder="Life path name…" />
    </div>
    <div class="lpe-field">
      <label>Universe</label>
      <input v-model="form.universe" placeholder="e.g. three_realms" />
    </div>
    <div class="lpe-field">
      <label>Description</label>
      <textarea v-model="form.description" rows="2" placeholder="What it is…"></textarea>
    </div>
    <div class="lpe-field">
      <label>Entry table id</label>
      <input v-model="form.entryTableId" placeholder="rt-…" />
      <span class="lpe-hint">The first roll table of this path.</span>
    </div>

    <button class="lpe-save" :disabled="saving" @click="save">{{ saving ? 'Saving…' : 'Save life path' }}</button>
    <div v-if="error" class="lpe-error">{{ error }}</div>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { useLifePaths } from '@/composables/useLifePaths.js'
import { usePanel } from '@/composables/usePanel.js'
import { usePanelBus } from '@/composables/usePanelBus.js'

const panel = usePanel()
const bus = usePanelBus()
const { saveLifePath } = useLifePaths()

const props = defineProps({
  lp: { type: Object, required: true },
})

const form = reactive({
  name: props.lp.name || '',
  universe: props.lp.universe || '',
  description: props.lp.description || '',
  entryTableId: props.lp.entryTableId || '',
})

const saving = ref(false)
const error = ref('')

async function save() {
  saving.value = true
  error.value = ''
  try {
    const result = await saveLifePath({
      id: props.lp.id || '',
      name: form.name,
      universe: form.universe,
      description: form.description,
      entryTableId: form.entryTableId,
      discovery: props.lp.discovery || null,
    })
    if (result?.ok) {
      bus.emit('lifepath-saved', { id: result.id, universe: form.universe, isNew: result.isNew })
      panel.close()
    }
  } catch (e) {
    error.value = e?.message || 'Save failed'
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.lpe-root { padding: 0; display: flex; flex-direction: column; gap: 8px; }
.lpe-field { display: flex; flex-direction: column; gap: 3px; }
.lpe-field label { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.5px; }
.lpe-field input, .lpe-field textarea {
  font-size: 12px; padding: 6px 8px;
  background: rgba(255,255,255,0.06); color: var(--text);
  border: 1px solid rgba(255,255,255,0.1); border-radius: 6px;
  font-family: inherit; width: 100%; box-sizing: border-box;
}
.lpe-field textarea { resize: vertical; min-height: 48px; }
.lpe-hint { font-size: 9px; color: var(--text-dim); }
.lpe-save { background: var(--success); color: #0a0a0f; font-weight: 600; padding: 7px 12px; border-radius: 6px; border: none; cursor: pointer; font-size: 12px; }
.lpe-save:disabled { opacity: 0.5; cursor: default; }
.lpe-error { font-size: 11px; color: var(--danger); background: rgba(212,64,64,0.08); padding: 6px 10px; border-radius: 4px; }
</style>
