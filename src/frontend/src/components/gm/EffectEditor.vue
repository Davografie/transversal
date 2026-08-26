<template>
  <div class="ee-root">
    <GmList
      :items="effects"
      reorderable
      empty-text="No effects defined"
      :row-class="rowClassFn"
      @click="onClickEffect"
      @reorder="onReorder"
    >
      <template #item="{ item: eff, index: i }">
        <span class="ee-cat" :class="'cat-' + effectCategory(eff)">{{ categorySign(effectCategory(eff)) }}</span>
        <span class="ee-summary">{{ effectSummary(eff) }}</span>
        <span class="ee-timing">{{ eff.timing }}</span>
        <span class="ee-handle">⠿</span>
        <button class="ee-del" @click.stop="removeEffect(i)" title="Remove">✕</button>
      </template>
    </GmList>

    <button class="ee-add" @click="showEditor ? closeEditor() : (showEditor = true)">
      {{ showEditor ? '− Cancel' : '+ Add effect' }}
    </button>

    <div v-if="showEditor" class="ee-form">
      <div class="ee-form-title">{{ editingIndex !== null ? 'Edit effect' : 'Add effect' }}</div>
      <select v-model="newEffect.actionId" @change="onActionChange">
        <option value="">-- pick an action --</option>
        <optgroup v-for="g in actionGroups" :key="g.name" :label="g.name">
          <option v-for="a in g.actions" :key="a.actionId" :value="a.actionId">{{ a.label }}</option>
        </optgroup>
      </select>
      <template v-if="selectedAction">
        <div class="ee-help">{{ selectedAction.description }}</div>
        <div v-if="isPortalLocation" class="ee-fixed-dest">Scope <b>{location:transversal_target}</b> → {{ portalDestination }} (+ zones)</div>
        <div v-else-if="isPortalUniverse" class="ee-fixed-dest">Scope <b>{universe:transversal_target}</b> → any location in {{ portalUniverse }}</div>
        <div v-if="variables.length" class="ee-vars">
          <span class="ee-vars-label">Variables:</span>
          <button v-for="v in variables" :key="v.name" type="button" class="ee-var" :class="{ copied: copiedVar === v.name }" @click="copyVariable(v.name)">
            {{ '{' + v.name + '}' }}<em class="ee-var-type">{{ v.type }}</em>
          </button>
        </div>
        <div v-for="f in visibleFields" :key="f.name" class="ee-field">
          <label>{{ f.label }}</label>

          <template v-if="isScopedTargetField(f)">
            <div class="ee-mode-row">
              <select v-model="newEffect.targetMode">
                <option value="literal">Pick specific</option>
                <option v-if="selectedAction.supportsReturnExit" value="return">Named exit</option>
                <option value="choose">Choose at runtime</option>
                <option value="random">Random</option>
              </select>
            </div>
            <div v-if="newEffect.targetMode !== 'return' && !isPortalTravel" class="ee-field">
              <label>Scope</label>
              <ScopeBuilder v-model="newEffect.scope" :universe="universe" />
              <template v-if="relevantFilterFields.length">
                <label>Only</label>
                <template v-for="ff in relevantFilterFields" :key="ff.field">
                  <label v-if="ff.valueType === 'boolean'" class="ee-check">
                    <input type="checkbox" :checked="!!newEffect.targetFilter[ff.field]" @change="toggleFilter(ff.field, $event)" />
                    {{ ff.label }}
                  </label>
                  <label v-else class="ee-check">
                    {{ ff.label }}
                    <select :value="newEffect.targetFilter[ff.field] || ''" @change="setFilterValue(ff.field, $event.target.value)">
                      <option value="">—</option>
                      <option v-for="o in (ff.options || [])" :key="o" :value="o">{{ o }}</option>
                    </select>
                  </label>
                </template>
              </template>
            </div>
            <TargetPicker
              v-if="newEffect.targetMode === 'literal'"
              :model-value="newEffect.fields[f.name] || ''"
              :kind="selectedAction.targetKind"
              :scope="literalTargetScope"
              :filter="newEffect.targetFilter"
              :action="selectedAction.effectAction"
              :placeholder="`Pick ${selectedAction.targetKind}…`"
              @update:model-value="onTargetPicked(f, $event)"
            />
            <div v-else-if="newEffect.targetMode === 'return'" class="ee-field">
              <label>Exit name</label>
              <input v-model="newEffect.returnExit" type="text" placeholder="e.g. survived" />
            </div>
            <div v-else-if="previewText" class="ee-preview">{{ previewText }}</div>
          </template>

          <template v-else-if="isEntityField(f)">
            <div class="ee-mode-row">
              <select v-model="newEffect.entityMode">
                <option value="literal">Pick specific</option>
                <option value="choose">Choose at runtime</option>
                <option value="random">Random</option>
              </select>
            </div>
            <input v-if="newEffect.entityMode === 'literal'" v-model="newEffect.fields[f.name]" type="text" placeholder="self" />
            <div v-else class="ee-field">
              <label>Entity scope</label>
              <ScopeBuilder v-model="newEffect.entityScope" :universe="universe" />
            </div>
          </template>

          <template v-else>
            <template v-if="isResultDieField(f)">
              <div class="ee-result-mode">
                <button type="button" :class="{ active: resultMode === 'die' }" @click="resultMode = 'die'">Die</button>
                <button type="button" :class="{ active: resultMode === 'variable' }" @click="resultMode = 'variable'">Variable</button>
              </div>
              <select v-if="resultMode === 'die'" v-model="newEffect.fields[f.name]">
                <option v-for="o in (f.options || [])" :key="o" :value="o">{{ o }}</option>
              </select>
              <input v-else v-model="newEffect.fields[f.name]" type="text" placeholder="{effect_die}" />
            </template>
            <select v-else-if="f.fieldType === 'die_select' || f.fieldType === 'select'" v-model="newEffect.fields[f.name]">
              <option v-for="o in (f.options || [])" :key="o" :value="o">{{ o }}</option>
            </select>
            <input v-else-if="f.fieldType === 'number'" v-model.number="newEffect.fields[f.name]" type="number" />
            <input v-else v-model="newEffect.fields[f.name]" type="text" :placeholder="f.default || ''" />
          </template>
        </div>
        <label class="ee-timing-label">Timing</label>
        <select v-model="newEffect.timing">
          <option v-for="t in (selectedAction.validTimings || ['IMMEDIATE'])" :key="t" :value="t">{{ t }}</option>
        </select>
        <div v-for="f in visibleContextFields" :key="f.name" class="ee-field">
          <label>{{ f.label }}</label>
          <select v-if="f.fieldType === 'select'" v-model="newEffect.context[f.name]">
            <option v-for="o in (f.options || [])" :key="o" :value="o">{{ o }}</option>
          </select>
          <ReturnMapEditor
            v-else-if="f.fieldType === 'return_map'"
            :model-value="newEffect.context[f.name] || {}"
            @update:model-value="newEffect.context[f.name] = $event"
            :target="newEffect.fields.target"
            :universe="universe"
          />
          <input v-else-if="f.fieldType === 'number'" v-model.number="newEffect.context[f.name]" type="number" :placeholder="f.default || ''" />
          <input v-else v-model="newEffect.context[f.name]" type="text" :placeholder="f.default || ''" />
        </div>
        <div v-if="hasExtraContext" class="ee-field">
          <label>Other context</label>
          <div v-for="(value, key) in newEffect.extraContext" :key="key" class="ee-extra-row">
            <span class="ee-extra-key">{{ key }}</span>
            <input v-model="newEffect.extraContext[key]" type="text" :placeholder="key" />
          </div>
        </div>
        <div v-if="selectedAction.supportsDuration" class="ee-field">
          <label>Duration</label>
          <DurationBuilder v-model="newEffect.duration" />
        </div>
        <div v-if="selectedAction.supportsPolarity" class="ee-field ee-polarity">
          <label class="ee-check">
            <input type="checkbox" v-model="newEffect.negative" />
            Negative (complication)
          </label>
        </div>
        <button class="ee-save" @click="commitEffect">{{ editingIndex !== null ? 'Update' : 'Add' }}</button>
      </template>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, reactive, watch, onMounted } from 'vue'
import { useClipboard } from '@vueuse/core'
import { useEffectActions } from '@/composables/useEffectActions.js'
import { useEffectTargets } from '@/composables/useEffectTargets.js'
import { useSfxMeta } from '@/composables/useSfxMeta.js'
import { useTraitsConfig } from '@/composables/useTraitsConfig.js'
import TargetPicker from './TargetPicker.vue'
import DurationBuilder from './DurationBuilder.vue'
import ScopeBuilder from './ScopeBuilder.vue'
import GmList from './GmList.vue'
import ReturnMapEditor from './ReturnMapEditor.vue'

const props = defineProps({
  modelValue: { type: Array, default: () => [] },
  universe: { type: String, default: '' },
  lifePath: { type: String, default: '' },
  variables: { type: Array, default: () => [] },
  portalDestination: { type: String, default: '' },
  portalTargetType: { type: String, default: '' },
  portalUniverse: { type: String, default: '' },
  portalRootId: { type: String, default: '' },
})
const emit = defineEmits(['update:modelValue'])

const effects = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const { load, actions: effectActions, summarize: effectSummary } = useEffectActions()
const showEditor = ref(false)
const editingIndex = ref(null)
const newEffect = reactive({ actionId: '', timing: 'IMMEDIATE', fields: {}, context: {}, extraContext: {}, duration: { timers: [], combine: 'FIRST_TO_FIRE' }, targetMode: 'literal', scope: '', targetFilter: {}, returnExit: '', entityMode: 'literal', entityScope: '', negative: false })
const resultMode = ref('die')
const copiedVar = ref('')
const { copy } = useClipboard()

onMounted(() => { load() })

const { load: loadSfxMeta, targetFilterFields } = useSfxMeta()
const { fetchTargets: fetchPreviewTargets } = useEffectTargets()
const previewText = ref('')
onMounted(() => { loadSfxMeta() })

const { traitsets, fetchTraitsConfig } = useTraitsConfig()
onMounted(() => { if (!traitsets.value.length) fetchTraitsConfig() })

const traitMeta = computed(() => {
  const m = {}
  for (const ts of traitsets.value) {
    for (const t of (ts.traits || [])) m[t.id] = t
  }
  return m
})

const GAIN_ACTIONS = new Set(['gain', 'gain_or_step_up', 'cortex_gain'])

function onTargetPicked(f, id) {
  newEffect.fields[f.name] = id
  if (f.name !== 'target' || selectedAction.value?.targetKind !== 'trait' || !GAIN_ACTIONS.has(selectedAction.value?.effectAction)) return
  const t = traitMeta.value[id]
  if (!t) return
  if (t.defaultDieType) newEffect.fields.result = String(t.defaultDieType).toLowerCase()
  let pol = t.polarity
  if (!pol && t.traitsetId) pol = traitsets.value.find(s => s.id === t.traitsetId)?.polarity
  newEffect.negative = String(pol || '').toLowerCase() === 'negative'
}

const selectedAction = computed(() => {
  if (!newEffect.actionId) return null
  return effectActions.value.find(a => a.actionId === newEffect.actionId) || null
})

const actionGroups = computed(() => {
  const groups = {}
  for (const a of effectActions.value) {
    const g = a.group || 'Other'
    if (!groups[g]) groups[g] = []
    groups[g].push(a)
  }
  return Object.entries(groups).map(([name, actions]) => ({ name, actions }))
})

const hasExtraContext = computed(() => Object.keys(newEffect.extraContext).length > 0)

function toggleFilter(field, e) {
  const next = { ...newEffect.targetFilter }
  if (e.target.checked) next[field] = true
  else delete next[field]
  newEffect.targetFilter = next
}

function setFilterValue(field, value) {
  const next = { ...newEffect.targetFilter }
  if (value) next[field] = value
  else delete next[field]
  newEffect.targetFilter = next
}

// Live preview: resolve the current scope/filter against the backend and show
// how many candidates match (authoring has no concrete entity, so entityId is
// null and the backend resolves with a synthetic universe context).
watch(
  () => [newEffect.targetMode, newEffect.scope, newEffect.targetFilter, selectedAction.value?.targetKind, selectedAction.value?.effectAction],
  async () => {
    previewText.value = ''
    const meta = selectedAction.value
    if (!meta?.targetKind) return
    const mode = newEffect.targetMode
    if (mode === 'literal' || mode === 'return') return
    const cands = await fetchPreviewTargets(
      meta.targetKind,
      newEffect.scope || null,
      null,
      meta.effectAction || null,
      Object.keys(newEffect.targetFilter).length ? newEffect.targetFilter : null,
    )
    previewText.value = cands.length
      ? `${cands.length} match — ${cands.slice(0, 3).map(c => c.name).join(', ')}${cands.length > 3 ? ' …' : ''}`
      : 'no candidates match'
  },
  { immediate: true, deep: true }
)

const isPortalTravel = computed(() => !!props.portalDestination && selectedAction.value?.effectType === 'travel')
const isPortalLocation = computed(() => isPortalTravel.value && props.portalTargetType === 'location')
const isPortalUniverse = computed(() => isPortalTravel.value && props.portalTargetType === 'universe')

// The literal picker resolves over the same scope/filter as choose/random.
// Portal travel is the one exception: its destination scope is fixed by the
// portal config, so derive it from the portal props rather than the free scope.
const literalTargetScope = computed(() => {
  if (isPortalTravel.value && props.portalRootId) return `subtree:${props.portalRootId}`
  if (isPortalTravel.value && props.portalUniverse) return `universe:${props.portalUniverse}`
  return newEffect.scope || ''
})

// Owner-context default: when an effect is authored inside a universe or life
// path, pre-scope its target so the picker starts in the right place.
function defaultScopeFor(kind) {
  if (kind === 'roll_table' && props.lifePath) return `life_path:${props.lifePath}`
  if (props.universe) return `universe:${props.universe}`
  return ''
}

const visibleFields = computed(() => {
  if (!selectedAction.value) return []
  return (selectedAction.value.fields || []).filter(f => {
    if (f.name === 'target' && selectedAction.value.implicitTarget) return false
    if (f.name === 'result' && selectedAction.value.implicitResult) return false
    return true
  })
})

const visibleContextFields = computed(() => {
  return (selectedAction.value?.contextFields || []).filter(f => {
    if (f.name === 'projection' && (newEffect.context.transversal_type || 'inapposite') !== 'consciousness') return false
    return true
  })
})

function isResultDieField(f) {
  return f.name === 'result' && f.fieldType === 'die_select'
}

function isScopedTargetField(f) {
  return f.name === 'target' && !!selectedAction.value?.targetKind
}

const relevantFilterFields = computed(() => {
  const kind = selectedAction.value?.targetKind
  if (!kind) return []
  return targetFilterFields.value.filter(ff => !ff.kinds?.length || ff.kinds.includes(kind))
})

function isEntityField(f) {
  return f.name === 'entity'
}

function detectTargetMode(eff, meta) {
  const kind = meta?.targetKind
  if (eff?.target?.startsWith('{return:')) return 'return'
  if (kind && eff?.target === `{choose_${kind}}`) return 'choose'
  if (kind && eff?.target === `{random:${kind}}`) return 'random'
  return 'literal'
}

function detectEntityMode(eff) {
  if (eff?.entity === '{choose_entity}') return 'choose'
  if (eff?.entity === '{random:entity}') return 'random'
  return 'literal'
}

function onActionChange() {
  newEffect.fields = {}
  newEffect.context = {}
  newEffect.extraContext = {}
  newEffect.duration = { timers: [], combine: 'FIRST_TO_FIRE' }
  newEffect.targetMode = 'literal'
  newEffect.scope = defaultScopeFor(selectedAction.value?.targetKind)
  newEffect.targetFilter = {}
  newEffect.returnExit = ''
  newEffect.entityMode = 'literal'
  newEffect.entityScope = ''
  newEffect.negative = false
  resultMode.value = 'die'
  const meta = selectedAction.value
  if (meta) {
    for (const f of (meta.fields || [])) {
      if (f.default) newEffect.fields[f.name] = f.default
    }
    for (const f of (meta.contextFields || [])) {
      if (f.default) newEffect.context[f.name] = f.default
    }
    if ((meta.validTimings || []).length === 1) newEffect.timing = meta.validTimings[0]
  }
}

function strVal(v) {
  return (v === null || v === undefined) ? null : String(v)
}

function cleanContext(obj) {
  const out = {}
  for (const [k, v] of Object.entries(obj || {})) {
    if (v !== '' && v !== null && v !== undefined) out[k] = v
  }
  return out
}

function buildEffect(meta) {
  const kind = meta.targetKind
  const mode = kind ? (newEffect.targetMode || 'literal') : 'literal'
  let target = meta.implicitTarget || newEffect.fields.target || ''
  if (kind && mode === 'choose') target = `{choose_${kind}}`
  if (kind && mode === 'random') target = `{random:${kind}}`
  if (mode === 'return') target = `{return:${newEffect.returnExit || ''}}`
  const entityMode = newEffect.entityMode || 'literal'
  let entity = newEffect.fields.entity || ''
  if (entityMode === 'choose') entity = '{choose_entity}'
  if (entityMode === 'random') entity = '{random:entity}'
  const context = { ...cleanContext(newEffect.context), ...newEffect.extraContext }
  if ((context.transversal_type || 'inapposite') !== 'consciousness') {
    context.projection = 'active'
  }
  let targetScope = kind ? (newEffect.scope || null) : null
  if (isPortalLocation.value) targetScope = '{location:transversal_target}'
  if (isPortalUniverse.value) targetScope = '{universe:transversal_target}'
  return {
    timing: newEffect.timing || 'IMMEDIATE',
    type: meta.effectType,
    action: meta.effectAction,
    target,
    entity,
    result: meta.implicitResult || strVal(newEffect.fields.result),
    targetScope,
    targetFilter: kind ? (newEffect.targetFilter || {}) : {},
    entityScope: (entityMode !== 'literal') ? (newEffect.entityScope || null) : null,
    negative: meta.supportsPolarity ? !!newEffect.negative : false,
    context,
    duration: (meta.supportsDuration && (newEffect.duration?.timers || []).length)
      ? {
          timers: newEffect.duration.timers.map(t => ({ event: t.event || 'scene', remaining: Number(t.remaining) || 0 })),
          combine: newEffect.duration.combine || 'FIRST_TO_FIRE',
        }
      : null,
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
  newEffect.targetMode = detectTargetMode(eff, meta)
  newEffect.scope = eff.targetScope || ''
  newEffect.targetFilter = eff.targetFilter || {}
  newEffect.entityMode = detectEntityMode(eff)
  newEffect.entityScope = eff.entityScope || ''
  newEffect.negative = !!eff.negative
  resultMode.value = (eff.result && eff.result.startsWith('{')) ? 'variable' : 'die'
  if (newEffect.targetMode === 'literal' && eff.target && eff.target !== (meta?.implicitTarget || '')) {
    newEffect.fields.target = eff.target
  }
  if (newEffect.targetMode === 'return' && eff.target) {
    newEffect.returnExit = eff.target.slice('{return:'.length, -1)
  }
  if (eff.result && eff.result !== (meta?.implicitResult || '')) newEffect.fields.result = eff.result
  if (newEffect.entityMode === 'literal' && eff.entity) newEffect.fields.entity = eff.entity
  const ctx = eff.context || {}
  const known = new Set((meta?.contextFields || []).map(f => f.name))
  const knownCtx = {}
  const extraCtx = {}
  for (const [k, v] of Object.entries(ctx)) {
    if (known.has(k)) knownCtx[k] = v
    else if (k === 'projection' && v === 'active') continue // implicit morph-by-default
    else extraCtx[k] = v
  }
  newEffect.context = knownCtx
  newEffect.extraContext = extraCtx
  newEffect.duration = eff.duration
    ? {
        timers: (eff.duration.timers || []).map(t => ({ event: t.event || 'scene', remaining: t.remaining ?? 0 })),
        combine: eff.duration.combine || 'FIRST_TO_FIRE',
      }
    : { timers: [], combine: 'FIRST_TO_FIRE' }
}

function closeEditor() {
  showEditor.value = false
  editingIndex.value = null
  newEffect.actionId = ''
  newEffect.fields = {}
  newEffect.timing = 'IMMEDIATE'
  newEffect.context = {}
  newEffect.extraContext = {}
  newEffect.duration = { timers: [], combine: 'FIRST_TO_FIRE' }
  newEffect.targetMode = 'literal'
  newEffect.scope = ''
  newEffect.targetFilter = {}
  newEffect.returnExit = ''
  newEffect.entityMode = 'literal'
  newEffect.entityScope = ''
  newEffect.negative = false
  resultMode.value = 'die'
}

async function copyVariable(v) {
  const token = `{${v}}`
  try {
    await copy(token)
  } catch { /* non-fatal: token stays visible for manual copy */ }
  copiedVar.value = v
  setTimeout(() => { if (copiedVar.value === v) copiedVar.value = '' }, 1200)
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
// Row interactions — the list/reorder rendering is owned by GmList.
function onClickEffect(eff, i) { editEffect(i) }
function onReorder(from, to) {
  const next = [...props.modelValue]
  const [moved] = next.splice(from, 1)
  next.splice(to, 0, moved)
  emit('update:modelValue', next)
}
function rowClassFn(eff) {
  return editingIndex.value !== null && effects.value[editingIndex.value] === eff ? 'editing' : ''
}
</script>

<style scoped>
.ee-root { display: flex; flex-direction: column; gap: 4px; }
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
.ee-extra-row { display: flex; align-items: center; gap: 6px; }
.ee-extra-key { font-size: 9px; color: var(--text-dim); font-family: monospace; flex: none; min-width: 90px; }
.ee-extra-row input { flex: 1; min-width: 0; }
.ee-mode-row { display: flex; margin-top: 2px; }
.ee-field label, .ee-timing-label { font-size: 9px; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.5px; }
.ee-help { font-size: 9px; color: var(--text-dim); font-style: italic; }
.ee-fixed-dest { font-size: 10px; color: var(--text-dim); }
.ee-fixed-dest b { color: var(--text); font-weight: 600; }
.ee-vars { display: flex; flex-wrap: wrap; align-items: center; gap: 4px; }
.ee-vars-label { font-size: 9px; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.5px; }
.ee-var { font-size: 10px; font-family: monospace; padding: 2px 6px; background: rgba(64,136,212,0.12); border: 1px solid var(--accent-dim); border-radius: 4px; color: var(--accent); cursor: pointer; }
.ee-var.copied { background: rgba(64,184,96,0.2); border-color: #40b860; color: #40b860; }
.ee-var-type { font-style: normal; font-family: inherit; font-size: 8px; color: var(--text-dim); margin-left: 3px; }
.ee-result-mode { display: flex; gap: 4px; }
.ee-result-mode button { font-size: 9px; padding: 2px 7px; border-radius: 4px; background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.1); color: var(--text-dim); cursor: pointer; }
.ee-result-mode button.active { background: rgba(64,136,212,0.2); border-color: var(--accent-dim); color: var(--accent); }
.ee-check { display: flex; align-items: center; gap: 5px; font-size: 11px; color: var(--text); text-transform: none; letter-spacing: 0; cursor: pointer; }
.ee-check input { width: auto; }
.ee-preview { font-size: 10px; color: var(--accent); font-style: italic; margin-top: 2px; }
.ee-save { background: var(--success); color: #0a0a0f; font-weight: 600; padding: 5px 10px; border-radius: 4px; border: none; cursor: pointer; font-size: 11px; }
</style>
