<template>
  <div>
    <div v-if="sfx" class="sfx-id">ID: {{ sfx.id }}</div>
    <!-- Shared form -->
    <div class="ps-form">
      <label>Name</label>
      <input v-model="form.name" placeholder="SFX name…" />
      <label>Description</label>
      <textarea v-model="form.description" rows="2" placeholder="What it does…"></textarea>
      <label>Trigger</label>
      <select v-model="form.trigger">
        <option value="manual">Manual (player activates)</option>
        <option value="on_roll">On Roll</option>
        <option value="on_result">On Result</option>
        <option value="on_complication">On Complication (hitch)</option>
        <option value="on_botch">On Botch</option>
        <option value="on_success">On Success</option>
        <option value="on_failure">On Failure</option>
        <option value="on_contest_win">On Contest Win</option>
        <option value="on_contest_loss">On Contest Loss</option>
        <option value="on_give_in">On Give In</option>
        <option value="on_push">On Push</option>
        <option value="on_taken_out">On Taken Out</option>
        <option value="on_prevent_taken_out">On Prevent Taken Out</option>
        <option value="on_location_change">On Location Change</option>
        <option value="on_trait_change">On Trait Change</option>
        <option value="on_trait_learn">On Trait Learned</option>
        <option value="on_relationship_create">On Relationship Create</option>
      </select>
      <label>Consequence menu</label>
      <select v-model="form.menuContext">
        <option value="">(none — trigger only)</option>
        <option value="test_success">Test success</option>
        <option value="simplified_roll">Simplified roll</option>
        <option value="contest_win">Contest win</option>
        <option value="contest_give_in">Contest give in</option>
        <option value="hitch">Hitch</option>
      </select>
      <div v-if="scopeVariables.length" class="sfx-vars">
        <span class="sfx-vars-label">Available variables:</span>
        <span v-for="v in scopeVariables" :key="v.name" class="sfx-var">{{ '{' + v.name + '}' }}<em class="sfx-var-type">{{ v.type }}</em></span>
      </div>
      <label>Conditions</label>
      <ConditionEditor v-model="form.conditions" />
    </div>

    <!-- Effects (shared editor) -->
    <h4 class="ps-section-title">Effects</h4>
    <EffectEditor v-model="form.effects" :variables="scopeVariables" />

    <!-- Status messages -->
    <div v-if="errorMsg" class="error-msg">{{ errorMsg }}</div>
    <div v-if="successMsg" class="success-msg">{{ successMsg }}</div>

    <!-- Action buttons: differ by mode -->
    <button v-if="sfx" class="save-btn save-main" @click="onSave" :disabled="saving">
      {{ saving ? 'Saving…' : 'Save SFX' }}
    </button>
    <button v-else class="save-btn save-main" @click="onCreate" :disabled="saving || !form.name.trim()">
      {{ saving ? 'Creating…' : 'Create SFX' }}
    </button>

    <div v-if="sfx" class="danger-zone">
      <DangerButton
        label="Delete SFX"
        loading-label="Deleting…"
        :disabled="saving"
        @confirm="onDelete"
      />
    </div>
  </div>
</template>

<script setup>
import { reactive, ref, watch } from 'vue'
import { useApi } from '@/composables/useApi.js'
import { useTraitsConfig } from '@/composables/useTraitsConfig.js'
import { usePanel } from '@/composables/usePanel.js'
import { useScopeVariables } from '@/composables/useScopeVariables.js'
import DangerButton from '@/components/gm/DangerButton.vue'
import EffectEditor from './EffectEditor.vue'
import ConditionEditor from './ConditionEditor.vue'

const { graphql, error: apiError } = useApi()
const panel = usePanel()
const { patchData, fetchTraitsConfig } = useTraitsConfig()

const props = defineProps({
  sfx: { type: Object, default: null },
})

const emit = defineEmits(['sfx-created', 'sfx-updated', 'sfx-deleted'])

const saving = ref(false)
const errorMsg = ref('')
const successMsg = ref('')

function initialConditions(sfx) {
  if (sfx?.conditions?.length) {
    return sfx.conditions.map(c => ({
      type: c.type || 'ALWAYS',
      target: c.target || '',
      value: c.value || '',
      narrative: c.narrative || '',
    }))
  }
  if (sfx?.limit) {
    return [{ type: 'NARRATIVE', target: '', value: '', narrative: sfx.limit }]
  }
  return []
}

const form = reactive({
  name: props.sfx?.name || '',
  description: props.sfx?.description || '',
  trigger: props.sfx?.trigger || 'manual',
  menuContext: props.sfx?.menuContext || '',
  conditions: initialConditions(props.sfx),
  effects: (props.sfx?.effects || []).map(e => ({ ...e })),
})

const { variables: scopeVariables, fetchVariables } = useScopeVariables()
watch(() => [form.trigger, form.menuContext], ([t, m]) => { fetchVariables(t || '', m || '') }, { immediate: true })

function generateSfxId(name) {
  return 'sfx-' + name.trim().toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')
}

async function onSave() {
  if (!props.sfx?.id) return
  saving.value = true
  errorMsg.value = ''
  try {
    const result = await graphql(
      `mutation($input: SfxUpdateInput!) { updateSfx(input: $input) { id name description trigger menuContext limit conditions { type target value narrative } effects { timing type action target entity result targetScope entityScope negative context duration { timers { event remaining } combine } } } }`,
      { input: { id: props.sfx.id, name: form.name, trigger: form.trigger, menuContext: form.menuContext, description: form.description, conditions: form.conditions, effects: form.effects } }
    )
    if (!result) { errorMsg.value = apiError.value || 'Save failed'; return }
    patchData('sfxs', props.sfx.id, {
      name: form.name, trigger: form.trigger, menuContext: form.menuContext, description: form.description, conditions: [...form.conditions], effects: [...form.effects],
    })
    emit('sfx-updated', {
      id: props.sfx.id, name: form.name, trigger: form.trigger, menuContext: form.menuContext,
      description: form.description, conditions: [...form.conditions], effects: [...form.effects],
    })
  } finally { saving.value = false }
}

async function onCreate() {
  saving.value = true
  errorMsg.value = ''
  const sfxId = generateSfxId(form.name)
  try {
    const result = await graphql(
      `mutation($input: SfxInput!) { createSfx(input: $input) { id name description trigger menuContext limit conditions { type target value narrative } effects { timing type action target entity result targetScope entityScope negative context duration { timers { event remaining } combine } } } }`,
      { input: { id: sfxId, name: form.name.trim(), trigger: form.trigger, menuContext: form.menuContext, description: form.description, conditions: form.conditions, effects: form.effects } }
    )
    if (!result) {
      const msg = apiError.value || ''
      if (msg.includes('unique constraint') || msg.includes('already exists') || msg.includes('conflicting key')) {
        errorMsg.value = `"${form.name}" already exists — close and re-open the trait to see it`
      } else {
        errorMsg.value = msg || 'Create failed'
      }
      return
    }
    errorMsg.value = ''
    await fetchTraitsConfig()
    patchData('sfxs', sfxId, {
      id: sfxId, name: form.name.trim(), trigger: form.trigger, menuContext: form.menuContext, description: form.description, conditions: [...form.conditions], effects: [...form.effects],
    })
    successMsg.value = `Created "${form.name}"`
    emit('sfx-created', {
      id: sfxId, name: form.name.trim(), trigger: form.trigger, menuContext: form.menuContext,
      description: form.description, conditions: [...form.conditions], effects: [...form.effects],
    })
    setTimeout(() => { panel.close() }, 600)
    form.name = ''
    form.description = ''
    form.conditions = []
    form.effects = []
    setTimeout(() => { successMsg.value = '' }, 8000)
  } finally { saving.value = false }
}

async function onDelete() {
  if (!props.sfx?.id) return
  saving.value = true
  try {
    await graphql(`mutation($id: ID!) { deleteSfx(id: $id) }`, { id: props.sfx.id })
    emit('sfx-deleted', props.sfx.id)
    await fetchTraitsConfig()
    panel.close()
  } finally { saving.value = false }
}
</script>

<style scoped>
.ps-form input, .ps-form select, .ps-form textarea {
  font-size: 12px; padding: 6px 8px;
  background: rgba(255,255,255,0.06); color: var(--text);
  border: 1px solid rgba(255,255,255,0.1); border-radius: 6px;
  font-family: inherit; width: 100%; box-sizing: border-box;
}
.ps-form textarea { resize: vertical; min-height: 48px; }
.sfx-id { font-size: 10px; color: var(--text-dim); font-family: monospace; margin-bottom: 6px; }
.sfx-vars { display: flex; flex-wrap: wrap; align-items: center; gap: 4px; margin-top: 2px; }
.sfx-vars-label { font-size: 9px; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.5px; }
.sfx-var { font-size: 10px; font-family: monospace; padding: 2px 6px; background: rgba(64,136,212,0.12); border: 1px solid var(--accent-dim); border-radius: 4px; color: var(--accent); }
.sfx-var-type { font-style: normal; font-family: inherit; font-size: 8px; color: var(--text-dim); margin-left: 3px; }
.hint { text-transform: none; letter-spacing: 0; color: var(--text-dim); font-size: 9px; }
.save-btn { background: var(--success); color: #0a0a0f; font-weight: 600; padding: 6px 12px; border-radius: 6px; border: none; cursor: pointer; font-size: 12px; }
.save-btn:disabled { opacity: 0.5; cursor: default; }
.save-main { margin-top: 10px; width: 100%; }
.error-msg { font-size: 11px; color: var(--danger); background: rgba(212,64,64,0.08); padding: 6px 10px; border-radius: 4px; margin-top: 8px; }
.success-msg { font-size: 11px; color: #40b860; background: rgba(64,184,96,0.08); padding: 6px 10px; border-radius: 4px; margin-top: 8px; }
</style>
