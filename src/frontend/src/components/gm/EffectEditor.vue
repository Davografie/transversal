<template>
  <div class="ee-root">
    <div v-if="!effects.length" class="ee-empty">No effects defined</div>
    <div v-else class="ee-list">
      <div
        v-for="(eff, i) in effects"
        :key="i"
        class="ee-row"
        :class="{ editing: editingIndex === i, dragging: dragIndex === i, 'drag-over': dragOverIndex === i }"
        draggable="true"
        @dragstart="onDragStart(i, $event)"
        @dragover.prevent="onDragOver(i)"
        @dragleave="onDragLeave"
        @drop="onDrop(i)"
        @dragend="onDragEnd"
        @click="editEffect(i)"
      >
        <span class="ee-handle">⠿</span>
        <span class="ee-cat" :class="'cat-' + effectCategory(eff)">{{ categorySign(effectCategory(eff)) }}</span>
        <span class="ee-summary">{{ effectSummary(eff) }}</span>
        <span class="ee-timing">{{ eff.timing }}</span>
        <button class="ee-del" @click.stop="removeEffect(i)" title="Remove">✕</button>
      </div>
    </div>

    <button class="ee-add" @click="showEditor ? closeEditor() : (showEditor = true)">
      {{ showEditor ? '− Cancel' : '+ Add effect' }}
    </button>

    <div v-if="showEditor" class="ee-form">
      <div class="ee-form-title">{{ editingIndex !== null ? 'Edit effect' : 'Add effect' }}</div>
      <select v-model="newEffect.actionId" @change="onActionChange">
        <option value="">-- pick an action --</option>
        <option v-for="a in effectActions" :key="a.actionId" :value="a.actionId">{{ a.label }}</option>
      </select>
      <template v-if="selectedAction">
        <div class="ee-help">{{ selectedAction.description }}</div>
        <div v-for="f in visibleFields" :key="f.name" class="ee-field">
          <label>{{ f.label }}</label>
          <select v-if="f.fieldType === 'die_select' || f.fieldType === 'select'" v-model="newEffect.fields[f.name]">
            <option v-for="o in (f.options || [])" :key="o" :value="o">{{ o }}</option>
          </select>
          <input v-else-if="f.fieldType === 'number'" v-model.number="newEffect.fields[f.name]" type="number" />
          <input v-else v-model="newEffect.fields[f.name]" type="text" :placeholder="f.default || ''" />
        </div>
        <label class="ee-timing-label">Timing</label>
        <select v-model="newEffect.timing">
          <option v-for="t in (selectedAction.validTimings || ['IMMEDIATE'])" :key="t" :value="t">{{ t }}</option>
        </select>
        <div class="ee-field">
          <label>Context (JSON)</label>
          <textarea v-model="newEffect.context" rows="2" placeholder='{"relationship": "fac-…"}'></textarea>
        </div>
        <button class="ee-save" @click="commitEffect">{{ editingIndex !== null ? 'Update' : 'Add' }}</button>
      </template>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, reactive, onMounted } from 'vue'
import { useApi } from '@/composables/useApi.js'

const props = defineProps({
  modelValue: { type: Array, default: () => [] },
})
const emit = defineEmits(['update:modelValue'])

const { graphql } = useApi()

const effects = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const effectActions = ref([])
const showEditor = ref(false)
const editingIndex = ref(null)
const newEffect = reactive({ actionId: '', timing: 'IMMEDIATE', fields: {}, context: '' })

onMounted(async () => {
  try {
    const data = await graphql(`{ effectActions { actionId label description category effectType effectAction validTimings fields { name label fieldType required default options } implicitTarget implicitResult implicitTiming targetKind requiresChoice } }`)
    if (data?.effectActions) effectActions.value = data.effectActions
  } catch {}
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

function onActionChange() {
  newEffect.fields = {}
  newEffect.context = ''
  const meta = selectedAction.value
  if (meta) {
    for (const f of (meta.fields || [])) {
      if (f.default) newEffect.fields[f.name] = f.default
    }
    if ((meta.validTimings || []).length === 1) newEffect.timing = meta.validTimings[0]
  }
}

function strVal(v) {
  return (v === null || v === undefined) ? null : String(v)
}

function parseContext(s) {
  if (!s) return {}
  try { return JSON.parse(s) } catch { return {} }
}

function buildEffect(meta) {
  return {
    timing: newEffect.timing || 'IMMEDIATE',
    type: meta.effectType,
    action: meta.effectAction,
    target: meta.implicitTarget || newEffect.fields.target || '',
    result: meta.implicitResult || strVal(newEffect.fields.result),
    targetScope: meta.requiresChoice ? (meta.targetKind || null) : null,
    context: parseContext(newEffect.context),
  }
}

function commitEffect() {
  const meta = selectedAction.value
  if (!meta) return
  const eff = buildEffect(meta)
  if (editingIndex.value !== null) {
    const next = [...props.modelValue]
    next[editingIndex.value] = eff
    emit('update:modelValue', next)
  } else {
    emit('update:modelValue', [...props.modelValue, eff])
  }
  closeEditor()
}

function removeEffect(i) {
  const next = [...props.modelValue]
  next.splice(i, 1)
  emit('update:modelValue', next)
  if (editingIndex.value === i) closeEditor()
}

function editEffect(i) {
  const eff = props.modelValue[i]
  editingIndex.value = i
  showEditor.value = true
  const meta = effectActions.value.find(a => a.effectType === eff.type && a.effectAction === eff.action)
  newEffect.actionId = meta?.actionId || ''
  newEffect.timing = eff.timing || 'IMMEDIATE'
  newEffect.fields = {}
  if (eff.target && eff.target !== (meta?.implicitTarget || '')) newEffect.fields.target = eff.target
  if (eff.result && eff.result !== (meta?.implicitResult || '')) newEffect.fields.result = eff.result
  newEffect.context = eff.context && Object.keys(eff.context).length ? JSON.stringify(eff.context) : ''
}

function closeEditor() {
  showEditor.value = false
  editingIndex.value = null
  newEffect.actionId = ''
  newEffect.fields = {}
  newEffect.timing = 'IMMEDIATE'
  newEffect.context = ''
}

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

// Drag reorder
const dragIndex = ref(-1)
const dragOverIndex = ref(-1)
function onDragStart(i, e) { dragIndex.value = i; e.dataTransfer.effectAllowed = 'move'; e.dataTransfer.setData('text/plain', '') }
function onDragOver(i) { dragOverIndex.value = i }
function onDragLeave() { dragOverIndex.value = -1 }
function onDrop(i) {
  if (dragIndex.value < 0 || dragIndex.value === i) return
  const next = [...props.modelValue]
  const [moved] = next.splice(dragIndex.value, 1)
  next.splice(i, 0, moved)
  emit('update:modelValue', next)
}
function onDragEnd() { dragIndex.value = -1; dragOverIndex.value = -1 }
</script>

<style scoped>
.ee-root { display: flex; flex-direction: column; gap: 4px; }
.ee-empty { font-size: 10px; color: var(--text-dim); }
.ee-list { display: flex; flex-direction: column; gap: 2px; }
.ee-row { display: flex; align-items: center; gap: 6px; padding: 5px 7px; border-radius: 4px; cursor: pointer; font-size: 11px; background: rgba(255,255,255,0.04); }
.ee-row:hover { background: rgba(255,255,255,0.08); }
.ee-row.editing { background: rgba(64,136,212,0.12); border: 1px solid var(--accent-dim); }
.ee-row.dragging { opacity: 0.4; }
.ee-row.drag-over { border: 1px dashed var(--accent); }
.ee-handle { cursor: grab; color: var(--text-dim); font-size: 13px; }
.ee-cat { font-weight: 700; font-size: 11px; width: 18px; text-align: center; }
.cat-cost { color: #d44040; }
.cat-benefit { color: #40b860; }
.cat-either { color: var(--text-dim); }
.ee-summary { flex: 1; font-family: monospace; font-size: 10px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ee-timing { font-size: 9px; color: var(--text-dim); }
.ee-del { background: none; border: none; color: var(--danger); cursor: pointer; font-size: 12px; }
.ee-add { font-size: 10px; padding: 3px 8px; background: rgba(255,255,255,0.04); border: 1px dashed rgba(255,255,255,0.15); border-radius: 4px; color: var(--text-dim); cursor: pointer; }
.ee-form { margin-top: 6px; padding: 8px; background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.08); border-radius: 6px; display: flex; flex-direction: column; gap: 6px; }
.ee-form-title { font-size: 10px; font-weight: 600; color: var(--accent); text-transform: uppercase; }
.ee-form select, .ee-form input, .ee-form textarea { font-size: 11px; padding: 4px 6px; background: rgba(255,255,255,0.06); color: var(--text); border: 1px solid rgba(255,255,255,0.1); border-radius: 4px; font-family: inherit; width: 100%; box-sizing: border-box; }
.ee-form textarea { resize: vertical; min-height: 34px; }
.ee-field { display: flex; flex-direction: column; gap: 2px; }
.ee-field label, .ee-timing-label { font-size: 9px; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.5px; }
.ee-help { font-size: 9px; color: var(--text-dim); font-style: italic; }
.ee-save { background: var(--success); color: #0a0a0f; font-weight: 600; padding: 5px 10px; border-radius: 4px; border: none; cursor: pointer; font-size: 11px; }
</style>
