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
      <label>Entry table</label>
      <GmScopePicker
        v-model="form.entryTableId"
        :options="entryTableOptions"
        empty-label="None"
        placeholder="Select entry table…"
      />
      <span class="lpe-hint">The first roll table of this path.</span>
    </div>

    <Button class="lpe-save" variant="success" solid :loading="saving" :disabled="saving" @click="save">{{ saving ? 'Saving…' : 'Save life path' }}</Button>
    <div v-if="error" class="lpe-error">{{ error }}</div>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { useApi } from '@/composables/useApi.js'
import { useLifePaths } from '@/composables/useLifePaths.js'
import { usePanel } from '@/composables/usePanel.js'
import { usePanelBus } from '@/composables/usePanelBus.js'
import Button from '@/components/ui/Button.vue'
import GmScopePicker from './GmScopePicker.vue'

const panel = usePanel()
const bus = usePanelBus()
const { graphql } = useApi()
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

const entryTableOptions = ref([])

// Table names repeat across life paths ("Learn", "Mishap", "Survival" ×2), so
// the owning path — or the shared/fundamental scope — disambiguates the label.
async function loadEntryTableOptions() {
  try {
    const [tables, lps] = await Promise.all([
      graphql(`{ rollTables { id name universe lifePath } }`),
      graphql(`{ lifePaths { id name } }`),
    ])
    const pathNames = Object.fromEntries((lps?.lifePaths || []).map(l => [l.id, l.name]))
    entryTableOptions.value = (tables?.rollTables || []).map(t => ({
      value: t.id,
      label: t.name + (t.lifePath
        ? ` · ${pathNames[t.lifePath] || t.lifePath}`
        : t.universe ? ' · shared' : ' · fundamental'),
    }))
  } catch { /* leave empty */ }
}

onMounted(loadEntryTableOptions)

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
  background: var(--overlay-6); color: var(--text);
  border: 1px solid var(--overlay-10); border-radius: 6px;
  font-family: inherit; width: 100%; box-sizing: border-box;
}
.lpe-field textarea { resize: vertical; min-height: 48px; }
.lpe-hint { font-size: 9px; color: var(--text-dim); }
.lpe-error { font-size: 11px; color: var(--danger); background: var(--danger-8); padding: 6px 10px; border-radius: 4px; }
</style>
