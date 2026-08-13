<template>
  <div>
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
        <option value="on_complication">On Complication</option>
        <option value="on_botch">On Botch</option>
        <option value="on_success">On Success</option>
        <option value="on_failure">On Failure</option>
        <option value="on_location_change">On Location Change</option>
        <option value="on_trait_change">On Trait Change</option>
        <option value="on_contest_win">On Contest Win</option>
        <option value="on_contest_loss">On Contest Loss</option>
      </select>
      <label>Limit <span class="hint">(markdown — narrative condition)</span></label>
      <textarea v-model="form.limit" rows="3" placeholder="When it works or when it doesn't…"></textarea>
    </div>

    <!-- Effects list (shared) -->
    <h4 class="ps-section-title">Effects</h4>
    <div v-if="form.effects.length === 0" class="empty">No effects defined — add one below</div>
    <div v-else class="effects-list">
      <div
        v-for="(eff, i) in form.effects"
        :key="i"
        class="effect-row"
        :class="{
          'drag-over': dragOverIndex === i,
          dragging: dragIndex === i,
          editing: editingEffectIndex === i,
        }"
        draggable="true"
        @dragstart="onDragStart(i, $event)"
        @dragover.prevent="onDragOver(i)"
        @dragleave="onDragLeave"
        @drop="onDrop(i)"
        @dragend="onDragEnd"
        @click="editEffect(i)"
      >
        <span class="drag-handle">⠿</span>
          <span class="cat-badge" :class="'cat-' + effectCategory(eff)">
          {{ categorySign(effectCategory(eff)) }}
        </span>
        <span class="effect-summary">{{ effectSummary(eff) }}</span>
        <span class="effect-timing">{{ eff.timing || 'immediate' }}</span>
        <button class="row-del-btn" @click.stop="removeEffect(i)" title="Remove effect">✕</button>
      </div>
    </div>
    <button class="ps-add-btn" @click="showAddEffect ? closeEffectEditor() : (showAddEffect = true)">
      {{ showAddEffect ? '− Cancel' : '+ Add Effect' }}
    </button>

    <!-- Add / Edit effect sub-form -->
    <div v-if="showAddEffect" class="add-effect-form">
      <div class="form-title">{{ editingEffectIndex !== null ? 'Edit Effect' : 'Add Effect' }}</div>
      <label>Action</label>
      <select v-model="newEffect.actionId" @change="onActionChange">
        <option value="">-- pick an action --</option>
        <option v-for="a in effectActions" :key="a.actionId" :value="a.actionId">
          {{ a.label }}
        </option>
      </select>
      <template v-if="selectedAction">
        <div class="action-help">{{ selectedAction.description }}</div>
        <div v-for="f in visibleFields" :key="f.name" class="field-row">
          <label>{{ f.label }}</label>
          <select v-if="f.fieldType === 'die_select' || f.fieldType === 'select'" v-model="newEffect.fields[f.name]">
            <option v-for="o in (f.options || [])" :key="o" :value="o">{{ o }}</option>
          </select>
          <input v-else-if="f.fieldType === 'number'" v-model.number="newEffect.fields[f.name]" type="number" :min="0" />
          <input v-else v-model="newEffect.fields[f.name]" type="text" :placeholder="f.default || ''" />
        </div>
        <label>Timing
          <span v-if="selectedAction.validTimings.length === 1" class="hint">(auto: {{ selectedAction.validTimings[0] }})</span>
        </label>
        <select v-if="selectedAction.validTimings.length > 1" v-model="newEffect.timing">
          <option v-for="t in selectedAction.validTimings" :key="t" :value="t">{{ t }}</option>
        </select>
        <button class="save-btn" @click="editingEffectIndex !== null ? updateEffect() : addEffect()">
          {{ editingEffectIndex !== null ? 'Update Effect' : 'Add Effect' }}
        </button>
      </template>
    </div>

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
import { reactive, ref, computed, onMounted } from 'vue'
import { useApi } from '@/composables/useApi.js'
import { useTraitsConfig } from '@/composables/useTraitsConfig.js'
import { usePanel } from '@/composables/usePanel.js'
import DangerButton from '@/components/gm/DangerButton.vue'

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

// ── Effects registry ──
const effectActions = ref([])
onMounted(async () => {
  const data = await graphql(`{ effectActions { actionId label description category effectType effectAction validTimings fields { name label fieldType required default options } implicitTarget implicitResult implicitTiming } }`)
  if (data?.effectActions) effectActions.value = data.effectActions
  else errorMsg.value = 'Failed to load effect actions — check API connection'
})

const selectedAction = computed(() => {
  if (!newEffect.actionId) return null
  return effectActions.value.find(a => a.actionId === newEffect.actionId) || null
})

const visibleFields = computed(() => {
  if (!selectedAction.value) return []
  return (selectedAction.value.fields || []).filter(f => {
    if (f.name === 'target' && selectedAction.value.implicitTarget) return false
    if (f.name === 'result' && selectedAction.value.implicitResult) return false
    return true
  })
})

// ── Category (sign) helpers ──
function effectCategory(eff) {
  const meta = effectActions.value.find(a => a.effectType === eff.type && a.effectAction === eff.action)
  return meta?.category || 'either'
}

function categorySign(cat) {
  if (cat === 'cost') return '−'
  if (cat === 'benefit') return '+'
  return '~'
}

function effectSummary(eff) {
  const parts = [eff.type, eff.action].filter(Boolean)
  let tail = ''
  if (eff.target && eff.target !== 'self' && eff.target !== '{source_trait}') tail += ` → ${eff.target}`
  if (eff.result) tail += ` (${eff.result})`
  return parts.join('/') + tail
}

// ── Shared form state ──
const form = reactive({
  name: props.sfx?.name || '',
  description: props.sfx?.description || '',
  trigger: props.sfx?.trigger || 'manual',
  limit: props.sfx?.limit || '',
  effects: (props.sfx?.effects || []).map(e => ({ ...e })),
})

function generateSfxId(name) {
  return 'sfx-' + name.trim().toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')
}

// ── Save (edit mode) ──
async function onSave() {
  if (!props.sfx?.id) return
  saving.value = true
  errorMsg.value = ''
  try {
    const result = await graphql(
      `mutation($input: SfxUpdateInput!) { updateSfx(input: $input) { id name description trigger limit effects { timing type action target result targetScope } } }`,
      { input: { id: props.sfx.id, name: form.name, trigger: form.trigger, description: form.description, limit: form.limit, effects: form.effects } }
    )
    if (!result) { errorMsg.value = apiError.value || 'Save failed'; return }
    patchData('sfxs', props.sfx.id, {
      name: form.name, trigger: form.trigger, description: form.description, limit: form.limit, effects: [...form.effects],
    })
    emit('sfx-updated', {
      id: props.sfx.id, name: form.name, trigger: form.trigger,
      description: form.description, limit: form.limit, effects: [...form.effects],
    })
  } finally { saving.value = false }
}

// ── Create (new mode) ──
async function onCreate() {
  saving.value = true
  errorMsg.value = ''
  const sfxId = generateSfxId(form.name)
  try {
    const result = await graphql(
      `mutation($input: SfxInput!) { createSfx(input: $input) { id name description trigger limit effects { timing type action target result targetScope } } }`,
      { input: { id: sfxId, name: form.name.trim(), trigger: form.trigger, description: form.description, limit: form.limit, effects: form.effects } }
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
    // Refresh the SFX list so the new SFX appears on next panel open
    await fetchTraitsConfig()
    patchData('sfxs', sfxId, {
      id: sfxId, name: form.name.trim(), trigger: form.trigger, description: form.description, limit: form.limit, effects: [...form.effects],
    })
    // Show success and clear form for next SFX
    successMsg.value = `Created "${form.name}"`
    emit('sfx-created', {
      id: sfxId, name: form.name.trim(), trigger: form.trigger,
      description: form.description, limit: form.limit, effects: [...form.effects],
    })
    // Close the panel after a brief delay so the user sees the success message
    setTimeout(() => { panel.close() }, 600)
    form.name = ''
    form.description = ''
    form.limit = ''
    form.effects = []
    setTimeout(() => { successMsg.value = '' }, 8000)
  } finally { saving.value = false }
}

// ── Delete ──
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

// ── Effects CRUD ──
const showAddEffect = ref(false)
const editingEffectIndex = ref(null)  // null = adding new, number = editing existing
const newEffect = reactive({
  actionId: '',
  timing: 'IMMEDIATE',
  fields: {},
})

function onActionChange() {
  newEffect.fields = {}
  const meta = selectedAction.value
  if (meta) {
    for (const f of (meta.fields || [])) {
      if (f.default) newEffect.fields[f.name] = f.default
    }
    if ((meta.validTimings || []).length === 1) {
      newEffect.timing = meta.validTimings[0]
    }
  }
}

function strVal(v) {
  return (v === null || v === undefined) ? null : String(v)
}

function addEffect() {
  const meta = selectedAction.value
  if (!meta) return
  const eff = {
    timing: newEffect.timing || 'IMMEDIATE',
    type: meta.effectType,
    action: meta.effectAction,
    target: meta.implicitTarget || newEffect.fields.target || '',
    result: meta.implicitResult || strVal(newEffect.fields.result),
  }
  form.effects.push(eff)
  closeEffectEditor()
}

function removeEffect(i) {
  form.effects.splice(i, 1)
  if (editingEffectIndex.value === i) {
    closeEffectEditor()
  } else if (editingEffectIndex.value > i) {
    editingEffectIndex.value--
  }
}

function editEffect(i) {
  const eff = form.effects[i]
  editingEffectIndex.value = i
  showAddEffect.value = true
  // Find the matching action metadata
  const meta = effectActions.value.find(a => a.effectType === eff.type && a.effectAction === eff.action)
  newEffect.actionId = meta?.actionId || ''
  newEffect.timing = eff.timing || 'IMMEDIATE'
  newEffect.fields = {}
  if (eff.target && eff.target !== (meta?.implicitTarget || '')) newEffect.fields.target = eff.target
  if (eff.result && eff.result !== (meta?.implicitResult || '')) newEffect.fields.result = eff.result
}

function updateEffect() {
  const meta = selectedAction.value
  if (!meta || editingEffectIndex.value === null) return
  const i = editingEffectIndex.value
  form.effects[i] = {
    timing: newEffect.timing || 'IMMEDIATE',
    type: meta.effectType,
    action: meta.effectAction,
    target: meta.implicitTarget || newEffect.fields.target || '',
    result: meta.implicitResult || strVal(newEffect.fields.result),
  }
  closeEffectEditor()
}

function closeEffectEditor() {
  showAddEffect.value = false
  editingEffectIndex.value = null
  newEffect.actionId = ''
  newEffect.fields = {}
  newEffect.timing = 'IMMEDIATE'
}

// ── Drag-and-drop reorder ──
const dragIndex = ref(-1)
const dragOverIndex = ref(-1)
function onDragStart(i, e) {
  dragIndex.value = i
  e.dataTransfer.effectAllowed = 'move'
  e.dataTransfer.setData('text/plain', '')
}
function onDragOver(i) { dragOverIndex.value = i }
function onDragLeave() { dragOverIndex.value = -1 }
function onDrop(i) {
  if (dragIndex.value < 0 || dragIndex.value === i) return
  const list = [...form.effects]
  const [moved] = list.splice(dragIndex.value, 1)
  list.splice(i, 0, moved)
  form.effects = list
}
function onDragEnd() { dragIndex.value = -1; dragOverIndex.value = -1 }
</script>

<style scoped>
.ps-form input, .ps-form select, .ps-form textarea {
  font-size: 12px; padding: 6px 8px;
  background: rgba(255,255,255,0.06); color: var(--text);
  border: 1px solid rgba(255,255,255,0.1); border-radius: 6px;
  font-family: inherit; width: 100%; box-sizing: border-box;
}
.ps-form textarea { resize: vertical; min-height: 48px; }
.hint { text-transform: none; letter-spacing: 0; color: var(--text-dim); font-size: 9px; }


.effects-list { display: flex; flex-direction: column; gap: 2px; margin-top: 4px; }
.effect-row { display: flex; align-items: center; gap: 6px; padding: 6px 8px; border-radius: 4px; cursor: grab; font-size: 12px; background: rgba(255,255,255,0.04); transition: background 0.1s; }
.effect-row:hover { background: rgba(255,255,255,0.08); }
.effect-row.drag-over { background: rgba(64,136,212,0.12); border: 1px dashed var(--accent); }
.effect-row.dragging { opacity: 0.4; }
.effect-row.editing { background: rgba(64,136,212,0.12); border: 1px solid var(--accent-dim); }
.effect-row { cursor: pointer; }
.drag-handle { cursor: grab; color: var(--text-dim); font-size: 14px; user-select: none; }

.cat-badge { font-weight: 700; font-size: 11px; width: 20px; text-align: center; border-radius: 3px; flex-shrink: 0; }
.cat-cost { color: #d44040; background: rgba(212,64,64,0.12); }
.cat-benefit { color: #40b860; background: rgba(64,184,96,0.12); }
.cat-either { color: var(--text-dim); background: rgba(255,255,255,0.06); }

.effect-summary { flex: 1; font-family: monospace; font-size: 11px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.effect-timing { font-size: 10px; color: var(--text-dim); flex-shrink: 0; }


.add-effect-form { margin-top: 8px; padding: 8px; background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.08); border-radius: 6px; display: flex; flex-direction: column; gap: 6px; }
.form-title { font-size: 11px; font-weight: 600; color: var(--accent); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 2px; }
.add-effect-form label { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.5px; }
.add-effect-form select, .add-effect-form input {
  font-size: 12px; padding: 4px 6px;
  background: rgba(255,255,255,0.06); color: var(--text);
  border: 1px solid rgba(255,255,255,0.1); border-radius: 4px;
  font-family: inherit;
}
.action-help { font-size: 10px; color: var(--text-dim); font-style: italic; }

.save-btn { background: var(--success); color: #0a0a0f; font-weight: 600; padding: 6px 12px; border-radius: 6px; border: none; cursor: pointer; font-size: 12px; }
.save-btn:disabled { opacity: 0.5; cursor: default; }
.save-main { margin-top: 10px; width: 100%; }
.error-msg { font-size: 11px; color: var(--danger); background: rgba(212,64,64,0.08); padding: 6px 10px; border-radius: 4px; margin-top: 8px; }
.success-msg { font-size: 11px; color: #40b860; background: rgba(64,184,96,0.08); padding: 6px 10px; border-radius: 4px; margin-top: 8px; }
</style>
