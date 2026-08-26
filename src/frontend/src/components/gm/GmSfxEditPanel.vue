<template>
  <div>
    <div class="sfx-summary">{{ sfxSummary }}</div>
    <!-- Shared form -->
    <div class="ps-form">
      <label>Name</label>
      <input v-model="form.name" placeholder="SFX name…" />
      <label>Description</label>
      <textarea v-model="form.description" rows="2" placeholder="What it does…"></textarea>
      <label>Trigger</label>
      <select v-model="form.trigger">
        <optgroup v-for="g in triggerGroups" :key="g.label" :label="g.label">
          <option v-for="t in g.options" :key="t.value" :value="t.value">{{ t.label }}</option>
        </optgroup>
        <option v-if="!knownTrigger" :value="form.trigger">{{ form.trigger }}</option>
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

    <!-- Validation warnings (live) -->
    <div v-if="validationWarnings.length" class="sfx-warnings">
      <div v-for="w in validationWarnings" :key="w" class="sfx-warning">⚠ {{ w }}</div>
    </div>

    <!-- Action buttons: differ by mode -->
    <button v-if="sfx" class="save-btn save-main" @click="onSave" :disabled="saving">
      {{ saving ? 'Saving…' : (savedAt ? 'Saved ✓' : 'Save now') }}
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
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useApi } from '@/composables/useApi.js'
import { useTraitsConfig } from '@/composables/useTraitsConfig.js'
import { usePanel } from '@/composables/usePanel.js'
import { useScopeVariables } from '@/composables/useScopeVariables.js'
import { useSfxMeta } from '@/composables/useSfxMeta.js'
import DangerButton from '@/components/gm/DangerButton.vue'
import EffectEditor from './EffectEditor.vue'
import ConditionEditor from './ConditionEditor.vue'
import { useEffectActions } from '@/composables/useEffectActions.js'

const { graphql, error: apiError } = useApi()
const panel = usePanel()
const { patchData, fetchTraitsConfig, traitNameMap, traitsets } = useTraitsConfig()

const props = defineProps({
  sfx: { type: Object, default: null },
})

const emit = defineEmits(['sfx-created', 'sfx-updated', 'sfx-deleted'])

const saving = ref(false)
const errorMsg = ref('')
const successMsg = ref('')
const savedAt = ref(null)

function initialConditions(sfx) {
  if (sfx?.conditions?.length) {
    return sfx.conditions.map(c => ({
      type: c.type || 'ALWAYS',
      subject: c.subject || '',
      target: c.target || '',
      value: c.value || '',
      narrative: c.narrative || '',
    }))
  }
  if (sfx?.limit) {
    return [{ type: 'NARRATIVE', subject: '', target: '', value: '', narrative: sfx.limit }]
  }
  return []
}

const form = reactive({
  name: props.sfx?.name || '',
  description: props.sfx?.description || '',
  trigger: props.sfx?.trigger || 'manual',
  conditions: initialConditions(props.sfx),
  effects: (props.sfx?.effects || []).map(e => ({ ...e })),
})

const { variables: scopeVariables, fetchVariables } = useScopeVariables()
watch(() => form.trigger, (t) => { fetchVariables(t || '') }, { immediate: true })

const { load: loadSfxMeta, triggers } = useSfxMeta()
loadSfxMeta()

const { load: loadActions, summarize: summarizeEffect } = useEffectActions()

onMounted(() => {
  if (!traitsets.value.length) fetchTraitsConfig()
  loadEntityNames()
})
loadActions()

// Backend trigger vocabulary grouped into Manual / Auto-fire / Menus. A legacy
// value not in the vocabulary is still offered so saving never drops it.
const triggerGroups = computed(() => {
  const byGroup = { dicepool: [], manual: [], auto: [], menu: [] }
  for (const t of triggers.value) {
    ;(byGroup[t.group] || (byGroup[t.group] = [])).push(t)
  }
  return [
    { label: 'Dice Pool', options: byGroup.dicepool },
    { label: 'Manual', options: byGroup.manual },
    { label: 'Auto-fire', options: byGroup.auto },
    { label: 'Menus', options: byGroup.menu },
  ]
})
const knownTrigger = computed(() => !form.trigger || triggers.value.some(t => t.value === form.trigger))

// ── Plain-English summary ────────────────────────────

function triggerPhrase(trigger) {
  const t = triggers.value.find(t => t.value === trigger)
  return t?.label || trigger || 'Manual'
}

function conditionPhrase(c) {
  if (!c || !c.type) return ''
  switch (c.type) {
    case 'ALWAYS': return ''
    case 'NARRATIVE': return c.narrative || ''
    case 'UNPLACED': return 'unplaced'
    case 'AT_LOCATION': return `at ${c.target}`
    case 'HAS_TRAIT': return `has ${c.target}`
    case 'HAS_TRAIT_IN_TRAITSET': return `has a trait in ${c.target}`
    case 'HAS_RELATIONSHIP': return `related to ${c.target}`
    case 'TRAIT_RATING': return `${c.target} ≥ ${c.value}`
    case 'IN_UNIVERSE': return `in ${c.target}`
    default: return `${c.type}`
  }
}

const entityNames = ref({})

async function loadEntityNames() {
  try {
    const data = await graphql(`query { entities { id name } }`)
    const m = {}
    for (const e of (data?.entities || [])) m[e.id] = e.name
    entityNames.value = m
  } catch { /* summary stays id-based on failure */ }
}

function resolveName(id) {
  if (!id) return id
  if (traitNameMap.value[id]) return traitNameMap.value[id]
  if (entityNames.value[id]) return entityNames.value[id]
  return id
}

const sfxSummary = computed(() => {
  let out = triggerPhrase(form.trigger)
  const conds = (form.conditions || []).map(conditionPhrase).filter(Boolean)
  if (conds.length) out += ` · if ${conds.join(', ')}`
  const effs = (form.effects || []).map((e) => summarizeEffect(e, resolveName)).filter(Boolean)
  if (effs.length) out += ` → ${effs.join(' then ')}`
  return out
})

// ── Authoring validation (live, debounced) ─────────
const validationWarnings = ref([])
let validationTimer = null

async function runValidation() {
  try {
    const input = {
      id: props.sfx?.id || generateSfxId(form.name) || 'sfx-draft',
      name: form.name || 'Draft',
      trigger: form.trigger,
      conditions: form.conditions || [],
      effects: form.effects || [],
    }
    const data = await graphql(
      `query($input: SfxInput!) { validateSfx(input: $input) }`,
      { input }
    )
    validationWarnings.value = data?.validateSfx || []
  } catch {
    validationWarnings.value = []
  }
}

watch(() => [form.trigger, form.conditions, form.effects], () => {
  clearTimeout(validationTimer)
  validationTimer = setTimeout(runValidation, 400)
}, { deep: true })

// Auto-save (debounced) — edits persist without an explicit save click.
let saveTimer = null
watch(
  () => [form.name, form.description, form.trigger, form.conditions, form.effects],
  () => {
    if (!props.sfx?.id) return
    savedAt.value = null // dirty again
    clearTimeout(saveTimer)
    saveTimer = setTimeout(() => { onSave() }, 700)
  },
  { deep: true }
)

function generateSfxId(name) {
  return 'sfx-' + name.trim().toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')
}

async function onSave() {
  if (!props.sfx?.id) return
  saving.value = true
  errorMsg.value = ''
  try {
    const result = await graphql(
      `mutation($input: SfxUpdateInput!) { updateSfx(input: $input) { id name description trigger limit conditions { type target value narrative } effects { timing type action target entity result targetScope entityScope targetFilter negative context duration { timers { event remaining } combine } } } }`,
      { input: { id: props.sfx.id, name: form.name, trigger: form.trigger, description: form.description, conditions: form.conditions, effects: form.effects } }
    )
    if (!result) { errorMsg.value = apiError.value || 'Save failed'; return }
    patchData('sfxs', props.sfx.id, {
      name: form.name, trigger: form.trigger, description: form.description, conditions: [...form.conditions], effects: [...form.effects],
    })
    savedAt.value = Date.now()
    emit('sfx-updated', {
      id: props.sfx.id, name: form.name, trigger: form.trigger,
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
      `mutation($input: SfxInput!) { createSfx(input: $input) { id name description trigger limit conditions { type target value narrative } effects { timing type action target entity result targetScope entityScope targetFilter negative context duration { timers { event remaining } combine } } } }`,
      { input: { id: sfxId, name: form.name.trim(), trigger: form.trigger, description: form.description, conditions: form.conditions, effects: form.effects } }
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
      id: sfxId, name: form.name.trim(), trigger: form.trigger, description: form.description, conditions: [...form.conditions], effects: [...form.effects],
    })
    successMsg.value = `Created "${form.name}"`
    emit('sfx-created', {
      id: sfxId, name: form.name.trim(), trigger: form.trigger,
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

.sfx-summary { font-size: 11px; color: var(--accent); font-family: monospace; background: rgba(64,136,212,0.08); border: 1px solid var(--accent-dim); border-radius: 4px; padding: 6px 8px; margin-bottom: 8px; line-height: 1.4; }
.sfx-warnings { margin-top: 10px; display: flex; flex-direction: column; gap: 4px; }
.sfx-warning { font-size: 11px; color: #e8b54a; background: rgba(212,160,64,0.1); border: 1px solid rgba(212,160,64,0.3); border-radius: 4px; padding: 5px 8px; font-family: monospace; }
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
