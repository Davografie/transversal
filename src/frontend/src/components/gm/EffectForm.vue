<template>
  <div class="ee-form">
    <div class="ee-form-title">{{ editing ? 'Edit effect' : 'Add effect' }}</div>
    <select v-model="newEffect.actionId" @change="onActionChange">
      <option value="">-- pick an action --</option>
      <optgroup v-for="g in actionGroups" :key="g.name" :label="g.name">
        <option v-for="a in g.actions" :key="a.actionId" :value="a.actionId">{{ a.label }}</option>
      </optgroup>
    </select>
    <template v-if="selectedAction">
      <div class="ee-help">{{ selectedAction.description }}</div>
      <div class="ee-timing-top">
        <label class="ee-timing-label">Timing</label>
        <select v-model="newEffect.timing">
          <option v-for="t in (selectedAction.validTimings || ['IMMEDIATE'])" :key="t" :value="t">{{ timingLabel(t) }}</option>
        </select>
      </div>
      <div class="ee-field ee-conditions">
        <label>Condition</label>
        <ConditionEditor v-model="newEffect.conditions" />
      </div>
      <div v-if="isRollTiming" class="ee-field">
        <label>Roll dice</label>
        <select :value="dieRole()" @change="setDieRole($event.target.value)">
          <option value="">any</option>
          <option value="null">unchosen</option>
          <option value="total">result</option>
          <option value="effect">effect</option>
        </select>
      </div>
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
              <option value="spec">Targeting path</option>
            </select>
          </div>
          <div v-if="newEffect.targetMode !== 'return' && newEffect.targetMode !== 'spec' && !isPortalTravel" class="ee-field">
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
          <TargetSpecBuilder
            v-else-if="newEffect.targetMode === 'spec'"
            v-model="newEffect.targetSpec"
            :destination="specDestination"
            :source-element="sourceElement"
            :variables="outputVariables"
          />
          <div v-else-if="previewText" class="ee-preview">{{ previewText }}</div>
        </template>

        <template v-else-if="isEntityField(f)">
          <div class="ee-mode-row">
            <select v-model="newEffect.entityMode">
              <option value="literal">Pick specific</option>
              <option value="choose">Choose at runtime</option>
              <option value="random">Random</option>
              <option value="spec">Targeting path</option>
            </select>
          </div>
          <input v-if="newEffect.entityMode === 'literal'" v-model="newEffect.fields[f.name]" type="text" placeholder="self" />
          <TargetSpecBuilder
            v-else-if="newEffect.entityMode === 'spec'"
            v-model="newEffect.entitySpec"
            :destination="{ element: 'entity' }"
            :source-element="sourceElement"
            :variables="outputVariables"
          />
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
      <div v-for="r in selectedAction.refs" :key="r.name" class="ee-field ee-ref">
        <label>{{ r.label }} <em class="ee-ref-element">{{ r.element }}</em></label>
        <TargetSpecBuilder
          v-model="newEffect.refs[r.name].spec"
          :destination="{ element: r.element }"
          :source-element="sourceElement"
          :variables="outputVariables"
        />
      </div>
      <div class="ee-field ee-outputs">
        <label>Outputs <em class="ee-ref-element">expose as {name} for later effects</em></label>
        <div v-for="(o, i) in newEffect.outputs" :key="i" class="ee-output-row">
          <input v-model="o.name" type="text" placeholder="name (e.g. complication)" />
          <select v-model="o.field" @change="onOutputFieldChange(o)">
            <option value="target">target</option>
            <option value="entity">entity</option>
            <option v-for="r in selectedAction.refs" :key="'refs.' + r.name" :value="'refs.' + r.name">refs.{{ r.name }}</option>
          </select>
          <input v-model="o.element" type="text" placeholder="element (e.g. traitsetting)" />
          <button type="button" class="ee-output-remove" @click="removeOutput(i)">✕</button>
        </div>
        <button type="button" class="ee-output-add" @click="addOutput">+ Add output</button>
      </div>
      <TraitInstanceEditor
        v-if="isGainAction"
        v-model:die="newEffect.fields.result"
        v-model:negative="newEffect.negative"
        v-model:rating-type="newEffect.context.rating_type"
        v-model:statement="newEffect.context.statement"
        v-model:notes="newEffect.context.notes"
        :variables="dieVariables"
        allow-variable
      />
      <div v-for="f in visibleContextFields" :key="f.name" class="ee-field">
        <label>{{ f.label }}</label>
        <DiePicker
          v-if="f.fieldType === 'dice_array'"
          multiple
          :model-value="newEffect.context[f.name] || []"
          @update:model-value="newEffect.context[f.name] = $event"
        />
        <template v-else-if="f.fieldType === 'die_select'">
          <div class="ee-result-mode">
            <button type="button" :class="{ active: effectDieMode === 'die' }" @click="effectDieMode = 'die'">Die</button>
            <button type="button" :class="{ active: effectDieMode === 'variable' }" @click="effectDieMode = 'variable'">Variable</button>
          </div>
          <select v-if="effectDieMode === 'die'" v-model="newEffect.context[f.name]">
            <option v-for="o in (f.options || [])" :key="o" :value="o">{{ o }}</option>
          </select>
          <input v-else v-model="newEffect.context[f.name]" type="text" :placeholder="f.default || ''" />
        </template>
        <select v-else-if="f.fieldType === 'select'" v-model="newEffect.context[f.name]">
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
      <div v-if="selectedAction.supportsPolarity && !isGainAction" class="ee-field ee-polarity">
        <label class="ee-check">
          <input type="checkbox" v-model="newEffect.negative" />
          Negative (complication)
        </label>
      </div>
      <div class="ee-form-actions">
        <button class="ee-cancel" type="button" @click="emit('cancel')">Cancel</button>
        <button class="ee-save" type="button" @click="commit">{{ editing ? 'Update' : 'Add' }}</button>
      </div>
    </template>
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
import TargetSpecBuilder from './TargetSpecBuilder.vue'
import ConditionEditor from './ConditionEditor.vue'
import DurationBuilder from './DurationBuilder.vue'
import TraitInstanceEditor from './TraitInstanceEditor.vue'
import ScopeBuilder from './ScopeBuilder.vue'
import ReturnMapEditor from './ReturnMapEditor.vue'
import DiePicker from '@/components/DiePicker.vue'

const props = defineProps({
  value: { type: Object, default: null },
  universe: { type: String, default: '' },
  lifePath: { type: String, default: '' },
  variables: { type: Array, default: () => [] },
  outputVariables: { type: Object, default: null }, // { name: element } for `select variable`
  sourceElement: { type: String, default: '' },  // catalog element of the SFX's source_kind
  portalDestination: { type: String, default: '' },
  portalTargetType: { type: String, default: '' },
  portalUniverse: { type: String, default: '' },
  portalRootId: { type: String, default: '' },
})
const emit = defineEmits(['save', 'cancel'])

const editing = computed(() => !!props.value)

const { load, actions: effectActions } = useEffectActions()
const newEffect = reactive({ actionId: '', timing: 'IMMEDIATE', fields: {}, context: {}, extraContext: {}, duration: { timers: [], combine: 'FIRST_TO_FIRE' }, targetMode: 'literal', targetSpec: { steps: [] }, scope: '', targetFilter: {}, dieFilter: {}, returnExit: '', entityMode: 'literal', entitySpec: { steps: [] }, entityScope: '', negative: false, refs: {}, outputs: [], conditions: [] })
const resultMode = ref('die')
const effectDieMode = ref('variable')  // effect_die context field: Die dropdown vs {variable}
const copiedVar = ref('')
const { copy } = useClipboard()

const TIMING_LABELS = {
  'IMMEDIATE': 'Immediate',
  'ON_ROLL': 'On roll',
  'ON_SET': 'On set',
  'ON_RESULT': 'On result',
  'ON_CONTEST_WIN': 'On contest win',
  'ON_CONTEST_LOSS': 'On contest loss',
  'ON_SUCCESS': 'On success',
  'ON_FAILURE': 'On failure',
  'END_OF_BEAT': 'End of beat',
  'END_OF_SCENE': 'End of scene',
  'END_OF_SESSION': 'End of session',
  'AFTER_BEATS': 'After beats',
  'ON_CONDITION': 'On condition',
}
function timingLabel(t) { return TIMING_LABELS[t] || t }

const ROLL_TIMINGS = ['ON_RESULT', 'ON_SET', 'ON_ROLL']
const isRollTiming = computed(() => ROLL_TIMINGS.includes(newEffect.timing))

const ROLL_CONTEXT_VARIABLES = ['effect_die', 'total', 'triggered_die_tier', 'triggered_die_effect_die', 'triggered_die_result', 'triggered_die_die']
const dieVariables = computed(() => {
  const names = (props.variables || []).map(v => v.name || v)
  const out = [...names]
  if (isRollTiming.value) for (const v of ROLL_CONTEXT_VARIABLES) if (!out.includes(v)) out.push(v)
  return out
})

function dieRole() {
  if (!newEffect.dieFilter || !('role' in newEffect.dieFilter)) return ''
  const r = newEffect.dieFilter.role
  return r === null ? 'null' : r
}

function setDieRole(v) {
  if (v === '') {
    const { role, ...rest } = newEffect.dieFilter || {}
    newEffect.dieFilter = rest
  } else if (v === 'null') {
    newEffect.dieFilter = { ...newEffect.dieFilter, role: null }
  } else {
    newEffect.dieFilter = { ...newEffect.dieFilter, role: v }
  }
}

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

// The spec element type an effect's `target` should resolve to, derived from
// the legacy target_kind. Cardinality is left loose — the wizard highlights on
// element match and shows the actual cardinality.
const TARGET_KIND_ELEMENT = {
  trait: 'traitsetting',
  traitsetting: 'traitsetting',
  entity: 'entity',
  occupant: 'entity',
  location: 'location',
  traitset: 'traitset',
  universe: 'universe',
  projection: 'projection',
  rating_die: 'die',
  pool: 'pool',
}

const specDestination = computed(() => {
  const kind = selectedAction.value?.targetKind
  const element = kind ? TARGET_KIND_ELEMENT[kind] : null
  return element ? { element } : null
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

watch(
  () => [newEffect.targetMode, newEffect.scope, newEffect.targetFilter, selectedAction.value?.targetKind, selectedAction.value?.effectAction],
  async () => {
    previewText.value = ''
    const meta = selectedAction.value
    if (!meta?.targetKind) return
    const mode = newEffect.targetMode
    if (mode === 'literal' || mode === 'return' || mode === 'spec') return
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

const isGainAction = computed(() => ['gain', 'gain_or_step_up', 'cortex_gain'].includes(selectedAction.value?.effectAction))

const literalTargetScope = computed(() => {
  if (isPortalTravel.value && props.portalRootId) return `subtree:${props.portalRootId}`
  if (isPortalTravel.value && props.portalUniverse) return `universe:${props.portalUniverse}`
  return newEffect.scope || ''
})

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
    if (f.name === 'result' && isGainAction.value) return false
    return true
  })
})

const visibleContextFields = computed(() => {
  return (selectedAction.value?.contextFields || []).filter(f => {
    if (f.name === 'projection' && (newEffect.context.transversal_type || 'inapposite') !== 'consciousness') return false
    if (isGainAction.value && (f.name === 'statement' || f.name === 'notes')) return false
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
  newEffect.targetSpec = { steps: [] }
  newEffect.scope = defaultScopeFor(selectedAction.value?.targetKind)
  newEffect.targetFilter = {}
  newEffect.dieFilter = {}
  newEffect.returnExit = ''
  newEffect.entityMode = 'literal'
  newEffect.entitySpec = { steps: [] }
  newEffect.entityScope = ''
  newEffect.negative = false
  newEffect.conditions = []
  initRefs(selectedAction.value)
  resultMode.value = 'die'
  effectDieMode.value = 'variable'
  const meta = selectedAction.value
  if (meta) {
    for (const f of (meta.fields || [])) {
      if (f.default) newEffect.fields[f.name] = f.default
    }
    for (const f of (meta.contextFields || [])) {
      if (f.default) newEffect.context[f.name] = f.default
    }
    if ((meta.validTimings || []).length === 1) newEffect.timing = meta.validTimings[0]
    if (['gain', 'gain_or_step_up', 'cortex_gain'].includes(meta.effectAction)) {
      newEffect.context.rating_type = 'static'
    }
  }
}

function strVal(v) {
  return (v === null || v === undefined) ? null : String(v)
}

function initRefs(meta) {
  newEffect.refs = {}
  for (const r of (meta?.refs || [])) {
    newEffect.refs[r.name] = { value: '', spec: { steps: [] }, scope: '' }
  }
}

function cleanContext(obj) {
  const out = {}
  for (const [k, v] of Object.entries(obj || {})) {
    if (v !== '' && v !== null && v !== undefined) out[k] = v
  }
  return out
}

function buildRefs() {
  const out = {}
  for (const r of (selectedAction.value?.refs || [])) {
    const ref = newEffect.refs[r.name]
    if (!ref) continue
    out[r.name] = {
      value: ref.value || '',
      spec: (ref.spec?.steps || []).length ? ref.spec : null,
      scope: ref.scope || null,
    }
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
  if (mode === 'spec') target = ''
  const entityMode = newEffect.entityMode || 'literal'
  let entity = newEffect.fields.entity || ''
  if (entityMode === 'choose') entity = '{choose_entity}'
  if (entityMode === 'random') entity = '{random:entity}'
  if (entityMode === 'spec') entity = ''
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
    dieFilter: newEffect.dieFilter || {},
    entityScope: (entityMode !== 'literal') ? (newEffect.entityScope || null) : null,
    negative: meta.supportsPolarity ? !!newEffect.negative : false,
    context,
    duration: (meta.supportsDuration && (newEffect.duration?.timers || []).length)
      ? {
          timers: newEffect.duration.timers.map(t => ({ event: t.event || 'scene', remaining: Number(t.remaining) || 0 })),
          combine: newEffect.duration.combine || 'FIRST_TO_FIRE',
        }
      : null,
    targetSpec: mode === 'spec' && (newEffect.targetSpec?.steps || []).length ? newEffect.targetSpec : null,
    entitySpec: entityMode === 'spec' && (newEffect.entitySpec?.steps || []).length ? newEffect.entitySpec : null,
    refs: buildRefs(),
    outputs: (newEffect.outputs || []).filter(o => o && o.name).map(o => ({ name: o.name, field: o.field || 'target', element: o.element || '' })),
    conditions: (newEffect.conditions || []).map(c => ({ ...c })),
  }
}

function addOutput() {
  newEffect.outputs.push({ name: '', field: 'target', element: '' })
}
function removeOutput(i) {
  newEffect.outputs.splice(i, 1)
}
function outputElementFor(field) {
  if (field === 'entity') return 'entity'
  if (field && field.startsWith('refs.')) {
    const name = field.slice('refs.'.length)
    const ref = (selectedAction.value?.refs || []).find((r) => r.name === name)
    return ref?.element || ''
  }
  return ''
}
function onOutputFieldChange(o) {
  const el = outputElementFor(o.field)
  if (el) o.element = el
}

function commit() {
  const meta = selectedAction.value
  if (!meta) return
  emit('save', buildEffect(meta))
}

// Populate the editor from an existing effect (edit mode) or leave it blank
// (add mode). Called once on mount; the parent remounts this form per edit.
function populate(eff) {
  const meta = effectActions.value.find(a => a.effectType === eff.type && a.effectAction === eff.action)
  newEffect.actionId = meta?.actionId || ''
  initRefs(meta)
  newEffect.timing = eff.timing || 'IMMEDIATE'
  newEffect.fields = {}
  newEffect.targetMode = detectTargetMode(eff, meta)
  newEffect.targetSpec = eff.targetSpec || { steps: [] }
  if ((eff.targetSpec?.steps || []).length) newEffect.targetMode = 'spec'
  newEffect.scope = eff.targetScope || ''
  newEffect.targetFilter = eff.targetFilter || {}
  newEffect.dieFilter = eff.dieFilter || {}
  newEffect.entityMode = detectEntityMode(eff)
  newEffect.entitySpec = eff.entitySpec || { steps: [] }
  if ((eff.entitySpec?.steps || []).length) newEffect.entityMode = 'spec'
  newEffect.entityScope = eff.entityScope || ''
  newEffect.negative = !!eff.negative
  newEffect.conditions = (eff.conditions || []).map(c => ({ ...c }))
  if (eff.refs) {
    for (const [name, ref] of Object.entries(eff.refs)) {
      if (!newEffect.refs[name]) newEffect.refs[name] = { value: '', spec: { steps: [] }, scope: '' }
      newEffect.refs[name].value = ref?.value || ''
      newEffect.refs[name].spec = ref?.spec || { steps: [] }
      newEffect.refs[name].scope = ref?.scope || ''
    }
  }
  newEffect.outputs = (eff.outputs || []).map(o => ({ name: o?.name || '', field: o?.field || 'target', element: o?.element || '' }))
  resultMode.value = (eff.result && eff.result.startsWith('{')) ? 'variable' : 'die'
  effectDieMode.value = (eff.context?.effect_die && String(eff.context.effect_die).startsWith('{')) ? 'variable' : 'die'
  if (newEffect.targetMode === 'literal' && eff.target && eff.target !== (meta?.implicitTarget || '')) {
    newEffect.fields.target = eff.target
  }
  if (newEffect.targetMode === 'return' && eff.target) {
    newEffect.returnExit = eff.target.slice('{return:'.length, -1)
  }
  if (eff.result && eff.result !== (meta?.implicitResult || '')) newEffect.fields.result = eff.result
  if (newEffect.entityMode === 'literal' && eff.entity) newEffect.fields.entity = eff.entity
  const ctx = eff.context || {}
  const known = new Set([
    ...(meta?.contextFields || []).map(f => f.name),
    'rating_type',
  ])
  const knownCtx = {}
  const extraCtx = {}
  for (const [k, v] of Object.entries(ctx)) {
    if (known.has(k)) knownCtx[k] = v
    else if (k === 'projection' && v === 'active') continue
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

onMounted(async () => {
  // effectActions must be loaded before we can resolve an existing effect's
  // (type, action) → actionId for the editor.
  await load()
  if (props.value) populate(props.value)
})

async function copyVariable(v) {
  const token = `{${v}}`
  try {
    await copy(token)
  } catch { /* non-fatal */ }
  copiedVar.value = v
  setTimeout(() => { if (copiedVar.value === v) copiedVar.value = '' }, 1200)
}
</script>

<style scoped>
.ee-form { display: flex; flex-direction: column; gap: 6px; }
.ee-form-title { font-size: 10px; font-weight: 600; color: var(--accent); text-transform: uppercase; }
.ee-form select, .ee-form input, .ee-form textarea { font-size: 11px; padding: 4px 6px; background: rgba(255,255,255,0.06); color: var(--text); border: 1px solid rgba(255,255,255,0.1); border-radius: 4px; font-family: inherit; width: 100%; box-sizing: border-box; }
.ee-form textarea { resize: vertical; min-height: 34px; }
.ee-field { display: flex; flex-direction: column; gap: 2px; }
.ee-timing-top { display: flex; flex-direction: column; gap: 2px; margin-bottom: 2px; }
.ee-extra-row { display: flex; align-items: center; gap: 6px; }
.ee-extra-key { font-size: 9px; color: var(--text-dim); font-family: monospace; flex: none; min-width: 90px; }
.ee-extra-row input { flex: 1; min-width: 0; }
.ee-mode-row { display: flex; margin-top: 2px; }
.ee-field label, .ee-timing-label { font-size: 9px; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.5px; }
.ee-help { font-size: 9px; color: var(--text-dim); font-style: italic; }
.ee-ref-element { font-style: normal; font-family: monospace; font-size: 8px; color: var(--text-dim); margin-left: 4px; }
.ee-output-row { display: flex; align-items: center; gap: 6px; }
.ee-output-row input { flex: 1; min-width: 0; }
.ee-output-row select { flex: none; }
.ee-output-remove { background: rgba(200,60,60,0.15); border: 1px solid rgba(200,60,60,0.4); color: #e08a8a; border-radius: 4px; cursor: pointer; font-size: 10px; padding: 2px 6px; }
.ee-output-add { align-self: flex-start; font-size: 10px; padding: 3px 8px; border-radius: 4px; background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.12); color: var(--text); cursor: pointer; }
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
.ee-form-actions { display: flex; gap: 6px; margin-top: 4px; }
.ee-save { background: var(--success); color: #0a0a0f; font-weight: 600; padding: 5px 10px; border-radius: 4px; border: none; cursor: pointer; font-size: 11px; }
.ee-cancel { background: rgba(255,255,255,0.06); color: var(--text-dim); padding: 5px 10px; border-radius: 4px; border: 1px solid rgba(255,255,255,0.1); cursor: pointer; font-size: 11px; }
</style>
