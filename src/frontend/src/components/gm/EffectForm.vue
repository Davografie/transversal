<template>
  <div class="ee-form">
    <div class="ee-form-title">
      <span>{{ editing ? 'Edit effect' : 'Add effect' }}</span>
      <!-- No Add/Update button any more: the fields write through and the owner's
           auto-save is the commit point. The *inline* use of this form — a roll
           table's binding effects — has no panel chrome to close it, so only that
           one is given a dismiss control. -->
      <button v-if="closable" type="button" class="ee-form-close" title="Done" @click="emit('cancel')">✕</button>
    </div>
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
        <ConditionEditor v-model="newEffect.conditions" :source-element="sourceElement" :available-keys="availableKeys" :variables="scopedVariables" />
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
      <div v-if="chipVariables.length" class="ee-vars">
        <span class="ee-vars-label">Variables:</span>
        <button v-for="v in chipVariables" :key="v.name" type="button" class="ee-var" :class="{ copied: copiedVar === v.name }" @click="copyVariable(v.name)">
          {{ '{' + v.name + '}' }}<em class="ee-var-type">{{ v.type }}</em>
        </button>
      </div>
      <!-- The action's refs and fields, rendered from ONE ordered list: a declared
           `fieldOrder` may interleave them (a dice limit's pool reads before the
           limit it moves), and an undeclared one keeps the default — refs, then
           fields. Context fields are in the same list, so they can be positioned
           too. -->
      <template v-for="item in orderedInputs" :key="item.kind + (item.f.name || '')">
      <EffectRefField
        v-if="item.kind === 'ref'"
        :ref-def="item.f"
        :model-value="newEffect.refs[item.f.name]?.spec || { steps: [] }"
        :source-element="sourceElement"
        :variables="scopedVariables"
        @update:model-value="newEffect.refs[item.f.name].spec = $event"
      />
      <!-- Where this effect anchors what it makes, when the action says that is
           not the subject entity: a relationship edge, or another trait instance.
           Its destination comes from the action (`ownerElements`), so the builder
           offers exactly what that verb can anchor to and nothing else. -->
      <div v-else-if="item.kind === 'owner'" class="ee-field">
        <label>{{ item.f.label }}</label>
        <p class="ee-field-help">{{ ownerHelp }}</p>
        <PathField
          v-model="newEffect.ownerSpec"
          :destination="ownerPathDestination"
          :source-element="sourceElement"
          :variables="scopedVariables"
          title="Anchored to"
        />
      </div>
      <!-- The in-line trait editor describes the trait this effect *creates* —
           its rating type, its **rating**, its polarity, statement and notes — so
           for a gain verb it renders directly under the trait picker.
           `orderedInputs` places it there; it used to render after every field,
           which is what separated the two halves the author reads as one control.
           The rating goes **inside** the box (`after-dice`, between the rating
           type and the statement) rather than in its own field: the rating type
           and the dice are one answer, and the field is hidden on a gain verb so
           there is only ever one control ([[B307]]). -->
      <TraitInstanceEditor
        v-else-if="item.kind === 'gainEditor'"
        mode="single"
        variant="box"
        :show-capacity="false"
        :show-dice="false"
        :polarity="newEffect.negative ? 'NEGATIVE' : 'POSITIVE'"
        :rating-type="(newEffect.context.rating_type || 'STATIC').toUpperCase()"
        :statement="newEffect.context.statement"
        :notes="newEffect.context.notes"
        @update:polarity="newEffect.negative = $event === 'NEGATIVE'"
        @update:rating-type="newEffect.context.rating_type = $event.toLowerCase()"
        @update:statement="newEffect.context.statement = $event"
        @update:notes="newEffect.context.notes = $event"
      >
        <template #after-dice>
          <EffectRatingControl v-bind="ratingControl" />
        </template>
      </TraitInstanceEditor>
      <template v-else>
      <div class="ee-field">
        <label>{{ item.f.label }}</label>
        <p v-if="item.f.description" class="ee-field-help">{{ item.f.description }}</p>

        <div v-if="isScopedTargetField(item.f)" class="ee-target-group">
          <!-- An action whose target must be a path declares destinations but no
               picker kind, and has no keyword left to type — so the mode row
               would be a select with one option. It is not rendered at all; the
               path builder below is the only input. -->
          <div v-if="!pathOnlyTarget" class="ee-mode-row">
            <select v-model="newEffect.targetMode">
              <option value="literal">{{ selectedAction.targetKind ? 'Pick specific' : 'Strategy keyword' }}</option>
              <option v-if="selectedAction.supportsReturnExit" value="return">Named exit</option>
              <option value="spec">Targeting path</option>
            </select>
          </div>
          <input
            v-if="newEffect.targetMode === 'literal' && !selectedAction.targetKind && !pathOnlyTarget"
            v-model="newEffect.fields[item.f.name]"
            type="text"
            :placeholder="item.f.default || 'strategy…'"
          />
          <TargetPicker
            v-else-if="newEffect.targetMode === 'literal'"
            :model-value="newEffect.fields[item.f.name] || ''"
            :kind="selectedAction.targetKind"
            :scope="literalTargetScope"
            :allow-filters="false"
            :action="selectedAction.effectAction"
            :placeholder="`Pick ${selectedAction.targetKind}…`"
            @update:model-value="onTargetPicked(f, $event)"
          />
          <div v-else-if="newEffect.targetMode === 'return'" class="ee-field">
            <label>Exit name</label>
            <input v-model="newEffect.returnExit" type="text" placeholder="e.g. survived" />
          </div>
          <PathField
            v-else-if="newEffect.targetMode === 'spec'"
            v-model="newEffect.targetSpec"
            :destination="specDestination"
            :source-element="sourceElement"
            :variables="outputVariables"
            title="Targeting path"
            @resolve="targetLocus = $event"
          />
        </div>

        <template v-else-if="isEntityField(item.f)">
          <div class="ee-mode-row">
            <select v-model="newEffect.entityMode">
              <option value="literal">Pick specific</option>
              <option value="spec">Targeting path</option>
            </select>
          </div>
          <input v-if="newEffect.entityMode === 'literal'" v-model="newEffect.fields[item.f.name]" type="text" placeholder="self" />
          <PathField
            v-else
            v-model="newEffect.entitySpec"
            :destination="{ elements: ['entity'] }"
            :source-element="sourceElement"
            :variables="scopedVariables"
            title="Who it applies to"
          />
        </template>

        <template v-else>
          <template v-if="isResultDieField(item.f)">
            <EffectRatingControl v-bind="ratingControl" />
          </template>
          <!-- A context field with its own editor: the dice array, the effect-die
               die/`{variable}` toggle, and the shared-table return map. -->
          <DiePicker
            v-else-if="item.f.fieldType === 'dice_array'"
            multiple
            :model-value="newEffect.context[item.f.name] || []"
            @update:model-value="newEffect.context[item.f.name] = $event"
          />
          <template v-else-if="item.f.fieldType === 'die_select'">
            <div class="ee-result-mode">
              <button type="button" :class="{ active: effectDieMode === 'die' }" @click="effectDieMode = 'die'">Die</button>
              <button type="button" :class="{ active: effectDieMode === 'variable' }" @click="effectDieMode = 'variable'">Variable</button>
            </div>
            <select v-if="effectDieMode === 'die'" v-model="newEffect.context[item.f.name]">
              <option v-for="(o, i) in (item.f.options || [])" :key="o" :value="o">{{ (item.f.optionLabels || [])[i] || o }}</option>
            </select>
            <input v-else v-model="newEffect.context[item.f.name]" type="text" :placeholder="item.f.default || ''" />
          </template>
          <ReturnMapEditor
            v-else-if="item.f.fieldType === 'return_map'"
            :model-value="newEffect.context[item.f.name] || {}"
            @update:model-value="newEffect.context[item.f.name] = $event"
            :target="newEffect.fields.target"
            :universe="universe"
          />
          <select v-else-if="item.f.fieldType === 'die_select' || item.f.fieldType === 'select'" v-model="valueStore(item.f)[item.f.name]">
            <option v-for="(o, i) in (item.f.options || [])" :key="o" :value="o">{{ (item.f.optionLabels || [])[i] || o }}</option>
          </select>
          <!-- An amount can be a *value the rule named* rather than a literal —
               "increase the limit by the tier of this rating". A `type="number"`
               input cannot hold `{name}` at all, so a variable is its own mode.
               Only names bound to a number are offered: a die binding
               substitutes as "d8", which the handler cannot parse and would fall
               back to 1 for — a wrong amount that looks like a right one. -->
          <template v-else-if="item.f.fieldType === 'number'">
            <div v-if="numberVariables.length" class="ee-result-mode">
              <button type="button" :class="{ active: numberMode(item.f) === 'number' }" @click="setNumberMode(item.f, 'number')">Number</button>
              <button type="button" :class="{ active: numberMode(item.f) === 'variable' }" @click="setNumberMode(item.f, 'variable')">Variable</button>
            </div>
            <select
              v-if="numberMode(item.f) === 'variable'"
              :value="valueStore(item.f)[item.f.name] || ''"
              @change="valueStore(item.f)[item.f.name] = $event.target.value"
            >
              <option value="">— variable —</option>
              <option v-for="o in numberChoices(item.f)" :key="o.value" :value="o.value">{{ o.label }}</option>
            </select>
            <input v-else v-model.number="valueStore(item.f)[item.f.name]" type="number" />
          </template>
          <input v-else v-model="valueStore(item.f)[item.f.name]" type="text" :placeholder="item.f.default || ''" />
        </template>
      </div>
      </template>
      </template>
      <div v-if="hasExtraContext" class="ee-field">
        <label>Other context</label>
        <div v-for="(value, key) in newEffect.extraContext" :key="key" class="ee-extra-row">
          <span class="ee-extra-key">{{ key }}</span>
          <input v-model="newEffect.extraContext[key]" type="text" :placeholder="key" />
        </div>
      </div>
      <div v-if="durationShown" class="ee-field">
        <label>Duration (undo timer)</label>
        <DurationBuilder v-model="newEffect.duration" allow-rolls />
        <p v-if="durationOffered" class="ee-help">How long before this change reverts. This is the effect's own timer — separate from the SFX-level listening window (how long the SFX stays armed).</p>
        <!-- A duration that is *set* is always shown, even where this action has no
             use for one: a timer you cannot see is a timer you cannot clear, and
             saving drops it silently (see the payload builder). -->
        <p v-else class="ee-help">This action doesn't use a duration — the timer above is left over, and saving this effect drops it. Clear it here if you want to see that happen.</p>
      </div>
      <div v-if="selectedAction.supportsPolarity && !isGainAction" class="ee-field ee-polarity">
        <label class="ee-check">
          <input type="checkbox" v-model="newEffect.negative" />
          Negative (complication)
        </label>
      </div>
      <!-- The output name is what a *later* step reads, so it sits after the step
           it names rather than at the top of the form. -->
      <div v-if="outputElement" class="ee-field">
        <label>Output name</label>
        <input
          :value="newEffect.output || ''"
          placeholder="e.g. beast"
          @input="newEffect.output = $event.target.value"
        />
        <p class="ee-field-help">
          Names this step's result — a later step can target it with <b>select variable</b>.
        </p>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, reactive, watch, onMounted } from 'vue'
import { useClipboard } from '@vueuse/core'
import { useEffectActions } from '@/composables/useEffectActions.js'
import { useSfxMeta } from '@/composables/useSfxMeta.js'
import { useTraitsConfig } from '@/composables/useTraitsConfig.js'
import TargetPicker from '@/components/ui/TargetPicker.vue'
import PathField from './PathField.vue'
import EffectRefField from './EffectRefField.vue'
import { useTargetCatalog } from '@/composables/useTargetCatalog.js'
import {
  chipVariablesFor,
  ratingNamesFor,
  scopeEntries,
} from '@/composables/effectScopeVariables.js'
import { ratingFieldsFor, ratingRowFor } from '@/composables/effectRatingRow.js'
import ConditionEditor from './ConditionEditor.vue'
import DurationBuilder from './DurationBuilder.vue'
import TraitInstanceEditor from '@/components/ui/TraitInstanceEditor.vue'
import EffectRatingControl from './EffectRatingControl.vue'
import ReturnMapEditor from './ReturnMapEditor.vue'
import DiePicker from '@/components/DiePicker.vue'

const props = defineProps({
  value: { type: Object, default: null },
  universe: { type: String, default: '' },
  lifePath: { type: String, default: '' },
  variables: { type: Array, default: () => [] },
  // Names in scope that no earlier effect produced — a roll table's bound
  // variables ([[B281]]). `{name: {element, cardinality}}`.
  scopeVariables: { type: Object, default: () => ({}) },
  trigger: { type: String, default: '' },     // the SFX's trigger: an immediate effect reads its context
  placement: { type: String, default: '' },   // "menu" gates on the menu's outcome keys instead
  outputVariables: { type: Object, default: null }, // { name: {element, cardinality} } for `select variable`
  sourceElement: { type: String, default: '' },  // catalog element of the SFX's source_kind
  portalDestination: { type: String, default: '' },
  portalTargetType: { type: String, default: '' },
  portalUniverse: { type: String, default: '' },
  portalRootId: { type: String, default: '' },
  // True when this form is rendered *inline* — no panel around it — and so needs
  // its own way out. A form inside GmDraftEffectPanel/GmEffectEditPanel is closed
  // by the panel's rail instead, which is why this defaults off.
  closable: { type: Boolean, default: false },
})
const emit = defineEmits(['save', 'cancel'])


const editing = computed(() => !!props.value)

const { load, actions: effectActions } = useEffectActions()
const newEffect = reactive({ actionId: '', timing: 'IMMEDIATE', fields: {}, context: {}, extraContext: {}, duration: { timers: [], combine: 'FIRST_TO_FIRE' }, targetMode: 'literal', targetSpec: { steps: [] }, resultSpec: { steps: [] }, ownerSpec: { steps: [] }, dieFilter: {}, returnExit: '', entityMode: 'literal', entitySpec: { steps: [] }, negative: false, refs: {}, output: '', conditions: [] })

// Variables the effect's *own* earlier paths expose. The engine walks an
// effect's paths in order — target, then its references — so a name that path 1
// outputs (its terminal step's `output`) is in scope for `select variable` in
// path 2. Traced from the in-progress effect, which also makes it work in the
// Add flow where the parent has no draft effect yet.
const { collectVariables } = useTargetCatalog()
const innerVariables = ref({})
let _innerTimer = null
watch(
  () => [newEffect.targetSpec, newEffect.entitySpec, newEffect.refs,
         newEffect.targetMode, newEffect.entityMode],
  () => {
    clearTimeout(_innerTimer)
    _innerTimer = setTimeout(async () => {
      const meta = selectedAction.value
      if (!meta) return
      try {
        innerVariables.value = await collectVariables(
          [buildEffect(meta)], props.sourceElement || null, null,
        )
      } catch {
        innerVariables.value = {}
      }
    }, 250)
  },
  { deep: true, immediate: true },
)

// Prior effects' outputs (from the panel) plus this effect's own — what the
// later builders inside this effect may start from. `scopeVariables` are names
// that are already in scope without any effect producing them (a roll table's
// bound variables, [[B281]]), so they sit under the outputs.
const scopedVariables = computed(() => ({
  ...(props.scopeVariables || {}),
  ...(props.outputVariables || {}),
  ...innerVariables.value,
}))
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

// Where this effect will be evaluated decides what a condition on it can read.
// The answer comes from the backend capability map (one implementation, shared
// with `validate_sfx`) rather than a list kept in step by hand; `null` means the
// site isn't modelled, so nothing is forbidden.
const { contextKeysFor } = useSfxMeta()
const availableKeys = ref(null)
watch(
  () => [props.trigger, props.placement, newEffect.timing],
  async () => {
    availableKeys.value = await contextKeysFor(
      props.trigger, props.placement, (newEffect.timing || '').toLowerCase(),
    )
  },
  { immediate: true },
)

// The names in scope for this effect — the activation's own, the declared bound
// variables, an earlier effect's outputs, this effect's own earlier paths — and
// the two lists built from them. The rule lives in `effectScopeVariables.js` so it
// can be executed by a check; both readers used to read `props.variables` alone,
// which is only the *activation's* names ([[B306]]).
const inScope = computed(() => scopeEntries(props.variables, scopedVariables.value))
const ratingNames = computed(() => ratingNamesFor(inScope.value, isRollTiming.value))

// ── A numeric field may read a *named* value ──────────────────
// The value carries its own mode (a bare `{name}` is a variable, digits are a
// number), so nothing about it depends on UI state surviving a save — the same
// reading the die field's `result`/`{variable}` split uses.
const NUMBER_ELEMENTS = ['int', 'number']

function normalizeVar(entry) {
  if (!entry) return { element: '', cardinality: 'one' }
  if (typeof entry === 'string') return { element: entry, cardinality: 'one' }
  return { element: entry.element || '', cardinality: entry.cardinality || 'one' }
}

// Only the names bound to a number. A die would substitute as "d8" and reach the
// handler unparseable, where it falls back to 1. The type is not shown because
// there is only one kind here — a list of names is the whole answer.
const numberVariables = computed(() =>
  Object.entries(scopedVariables.value || {})
    .map(([name, entry]) => ({ name, ...normalizeVar(entry) }))
    .filter(v => NUMBER_ELEMENTS.includes(v.element))
    .map(v => v.name)
)

/** What a given field's variable picker offers, plus its own stored value when
 *  that names something no longer bound — an editor never rewrites a value it
 *  cannot represent (the rule the placement and arming-scope selects follow). */
function numberChoices(f) {
  const out = numberVariables.value.map(name => ({ value: `{${name}}`, label: name }))
  const current = String(valueStore(f)[f.name] || '')
  if (current && !out.some(o => o.value === current)) {
    out.push({ value: current, label: `${current} (not a bound number)` })
  }
  return out
}

function numberMode(f) {
  return /^\{[^{}]+\}$/.test(String(valueStore(f)[f.name] ?? '')) ? 'variable' : 'number'
}

function setNumberMode(f, mode) {
  const store = valueStore(f)
  if (mode === 'variable') {
    const first = numberVariables.value[0]
    store[f.name] = first ? `{${first}}` : ''
  } else {
    store[f.name] = ''
  }
}

// The chips the author reads — every name in scope, with a `many` one marked
// ([[B306]]; see `effectScopeVariables.js`).
const chipVariables = computed(() => chipVariablesFor(inScope.value, isRollTiming.value))

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

const { load: loadSfxMeta } = useSfxMeta()
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

// Actions that *produce* something worth naming (a gain makes a trait instance,
// a disguise makes a projection) declare the element here; only they show the
// output-name field, and only their names join the variable picker.
const outputElement = computed(() => selectedAction.value?.outputElement || '')

// The spec element types an effect's `target` may resolve to. Preferred: the
// action's declared `pathElements`, because the picker kind and the path's
// destination are different questions — there is no "die" picker, but a path to
// a die is perfectly writable, and one action can accept a die in a pool *or* a
// die of a trait's rating. Falls back to the legacy target_kind table.
// Cardinality is left loose — the wizard highlights on element match and shows
// the actual cardinality.
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
  const meta = selectedAction.value
  const declared = meta?.pathElements || []
  const fallback = meta?.targetKind ? [TARGET_KIND_ELEMENT[meta.targetKind]] : []
  const elements = (declared.length ? declared : fallback).filter(Boolean)
  return elements.length ? { elements } : null
})

// The owner path exists only when the action declares it, and it may land only on
// what the action declares — so the builder can never offer an anchor the verb
// cannot use.
const OWNER_ELEMENT_LABEL = {
  relationship: 'the relationship edge this trait hangs on',
  traitsetting: 'the trait instance this one nests under',
}
const ownerPathDestination = computed(() => {
  const elements = selectedAction.value?.ownerElements || []
  return elements.length ? { elements } : null
})
// The owner is a declared **anchor** reference now ([[B261]]): it renders as a ref
// row like every other input, so this block is its *fallback* — shown only while
// no ref is authored, the same shape `hiddenWhenRef` gives a superseded field.
// Content authored before the reference keeps its path editable here.
const ownerFallbackShown = computed(() =>
  !!ownerPathDestination.value
  && !(newEffect.refs?.owner?.spec?.steps || []).length)
const ownerHelp = computed(() => {
  const element = (selectedAction.value?.ownerElements || [])[0]
  return `Anchored to ${OWNER_ELEMENT_LABEL[element] || element}.`
})

// Only an action that **declares** the row creates a whole rating from it — the
// trait-gain family. `Add Die`, `Set Die`, `Play as Rating` and `Set Trait` take
// one die, so offering them a row would collect dice their handler drops.
const ratingIsRow = computed(() =>
  !!(selectedAction.value?.contextFields || []).some((f) => f.name === 'dice'))

// ── The die rating: a row of dice, one named die, or a path ──────
// The row is the authoring truth for "Dice" mode (`context.dice`), and `result`
// carries its first die so every single-die reader — this form's own Variable
// mode, the handlers, validation — keeps working unchanged. A `{variable}` in
// `result` means the whole rating is that one named die (five live rules take
// `{effect_die}`), so the row is left empty in that mode ([[B307]]).
const resultDice = computed(() => ratingRowFor(newEffect.context?.dice, newEffect.fields.result))

function setResultDice(row) {
  newEffect.context.dice = [...(row || [])]
  newEffect.fields.result = (row || [])[0] || ''
}

// Switching mode must not leave the other mode's value behind, or the effect
// would carry both and the row would win silently at fire time.
function setResultMode(mode) {
  resultMode.value = mode
  if (!ratingIsRow.value) return
  if (mode === 'die') {
    if (!(newEffect.context.dice || []).length) setResultDice(resultDice.value)
  } else {
    newEffect.context.dice = []
  }
}

// The action's own `result` field — its `options` are the literal dice the plain
// dropdown offers.
const resultFieldDef = computed(() =>
  (selectedAction.value?.fields || []).find((f) => f.name === 'result') || null)

// Everything `EffectRatingControl` needs, bound once and used by **both** hosts:
// an action's own `result` field, and the rating slot inside a gain verb's trait
// instance editor. `v-bind` keeps the two from drifting.
const ratingControl = computed(() => ({
  field: resultFieldDef.value,
  mode: resultMode.value,
  'onUpdate:mode': setResultMode,
  row: resultDice.value,
  'onUpdate:row': setResultDice,
  result: strVal(newEffect.fields.result),
  'onUpdate:result': (v) => { newEffect.fields.result = v },
  spec: newEffect.resultSpec,
  'onUpdate:spec': (v) => { newEffect.resultSpec = v },
  canRow: ratingIsRow.value,
  variables: ratingNames.value,
  // `props.` is not decoration: inside `<script setup>` a prop is **not** a bare
  // binding. Reading `sourceElement` here threw a ReferenceError the moment the
  // slot rendered — the screen went blank and only the console said why.
  sourceElement: props.sourceElement || '',
  outputVariables: props.outputVariables || null,
}))

// The element the target path currently resolves to, reported by the builder.
// A change to a *rating* die is a fact about the character, so it can carry a
// duration; a change to a die in the pool is gone at the next roll, so offering a
// timer there would be a field that lies. Literal/choose/random modes name no
// path, so there is no locus to reason about and no duration either.
const targetLocus = ref('')

const durationOffered = computed(() => {
  const meta = selectedAction.value
  if (!meta?.supportsDuration) return false
  const only = meta.durationElements || []
  if (!only.length) return true
  return newEffect.targetMode === 'spec' && only.includes(targetLocus.value)
})

// A duration that exists is shown whether or not this action offers one: hiding a
// set value makes it impossible to clear, and this is exactly how a fabricated
// "1 roll" survived on rules nobody had authored one for.
const durationShown = computed(() =>
  durationOffered.value || (newEffect.duration?.timers || []).length > 0)

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

const isPortalTravel = computed(() => !!props.portalDestination && selectedAction.value?.effectType === 'travel')
const isPortalLocation = computed(() => isPortalTravel.value && props.portalTargetType === 'location')
const isPortalUniverse = computed(() => isPortalTravel.value && props.portalTargetType === 'universe')

const isGainAction = computed(() => ['gain', 'gain_or_step_up', 'cortex_gain'].includes(selectedAction.value?.effectAction))

const literalTargetScope = computed(() => {
  // A portal's fixed destination: the picker offers that place (and its zones),
  // or a location in that universe.
  if (isPortalTravel.value && props.portalRootId) return `subtree:${props.portalRootId}`
  if (isPortalTravel.value && props.portalUniverse) return `universe:${props.portalUniverse}`
  return ''
})

const visibleFields = computed(() => {
  if (!selectedAction.value) return []
  return (selectedAction.value.fields || []).filter(f => {
    if (f.name === 'target' && selectedAction.value.implicitTarget) return false
    if (f.name === 'result' && selectedAction.value.implicitResult) return false
    // On a gain verb the in-line trait editor renders the rating, inside its own
    // box and beside the rating type it belongs with — so the field steps aside,
    // exactly as it did before the rating gained its third mode ([[B307]]).
    if (f.name === 'result' && isGainAction.value) return false
    // A field a reference supersedes is the fallback form: once the reference is
    // authored the field steps aside (its stored value is still kept). A ref may
    // be authored as a path *or* as a picker value, so both count ([[B261]]).
    //
    // …and it steps aside **immediately** when the reference reads exactly like the
    // field. Two controls with one label asking one question is not a fallback, it
    // is a duplicate: `travel` showed two "Entity" inputs (the `entity` field and
    // the `recipient` ref) and two "Destination Location" ones. A fallback with its
    // own words — attune's "Target Universe" beside the "Attunes To (projection)"
    // ref — is a genuine simpler form and still shows until the ref is authored.
    if (f.hiddenWhenRef) {
      const ref = newEffect.refs?.[f.hiddenWhenRef]
      if (ref?.spec?.steps?.length || ref?.value) return false
      const declared = (selectedAction.value?.refs || [])
        .find((r) => r.name === f.hiddenWhenRef)
      if (declared && declared.label === f.label) return false
    }
    return true
  })
})

const visibleContextFields = computed(() => {
  return (selectedAction.value?.contextFields || []).filter(f => {
    if (f.name === 'projection' && (newEffect.context.transversal_type || 'inapposite') !== 'consciousness') return false
    if (isGainAction.value && (f.name === 'statement' || f.name === 'notes')) return false
    // The rating row is answered by `EffectRatingControl`, which renders every
    // mode in one control — on the trait-creating actions that declare it. Any
    // other action's `dice` field (Add Dice's own "Dice") renders normally.
    if (f.name === 'dice' && ratingIsRow.value) return false
    return true
  })
})

// ── Declared input order ─────────────────────────────────────
//
// An action may name the order its inputs read in (`fieldOrder`), because the
// default is not always right: a dice limit's pool is the *subject* ("whose
// limit"), so it belongs before the limit chosen and the amount applied. A name
// may be a ref or a field (context fields included) — the editor only cares
// where each one goes.
//
// Unnamed items keep the default reading order: refs first when the action says
// one names its subject (`refsFirst`, "Trait to Move" before "Give To"), then
// the fields. One list, rendered once, so a field cannot be placed twice or
// dropped on the way.
const orderedInputs = computed(() => {
  const order = selectedAction.value?.fieldOrder || []
  const rank = {}
  order.forEach((name, i) => { rank[name] = i })
  const refs = selectedAction.value?.refs || []
  const fields = [...(visibleFields.value || []), ...(visibleContextFields.value || [])]
  const unranked = rank_by_declaration(refs, fields, refsFirst.value)
  const declared = order.map((name) => by_name(name, refs, fields)).filter(Boolean)
  const declaredNames = new Set(declared.map((x) => x.f.name))
  const tail = unranked.filter((x) => !declaredNames.has(x.f.name))
  const items = [...declared, ...tail]
  // An action that declares an owner path but does not rank it still shows it, at
  // the end — the anchor reads after the thing it anchors. Added only when nothing
  // else already answers "Anchored to": the ranked names are **empty** for an action
  // with no `fieldOrder`, so the declared owner reference rendered from the tail
  // *and* this block was appended as well — two "Anchored to" inputs for
  // `gain_or_step_up_trait`, `gain_trait`, `cortex_gain_trait` and
  // `set_trait_statement` ([[B272]]). The question is "is an owner input already
  // here", not "was it ranked".
  if (ownerFallbackShown.value && !items.some((x) => x.f.name === 'owner')) items.push(OWNER_INPUT)
  // A gain verb's in-line trait editor belongs with the trait it is about (see
  // the template). Placed *after* the trait field, wherever that field landed —
  // and appended when the action has no target field, which is exactly where it
  // rendered before for every gain verb.
  if (!isGainAction.value) return items
  const at = items.findIndex((x) => x.kind === 'field' && x.f.name === 'target')
  return at === -1
    ? [...items, GAIN_EDITOR_INPUT]
    : [...items.slice(0, at + 1), GAIN_EDITOR_INPUT, ...items.slice(at + 1)]
})

const OWNER_INPUT = { kind: 'owner', f: { name: 'owner', label: 'Anchored to' } }
const GAIN_EDITOR_INPUT = { kind: 'gainEditor', f: { name: 'gain_editor' } }

// A declared order ranks refs among the fields, so it decides their side itself;
// without one, the action's own `refsFirst` does.
const refsFirst = computed(() =>
  !!(selectedAction.value?.refsFirst || (selectedAction.value?.fieldOrder || []).length))

// The items the action did not place, in their own natural order.
function rank_by_declaration(refs, fields, refsFirst) {
  const refItems = refs.map((f) => ({ kind: 'ref', f }))
  const fieldItems = fields.map((f) => ({ kind: 'field', f }))
  return refsFirst ? [...refItems, ...fieldItems] : [...fieldItems, ...refItems]
}

function by_name(name, refs, fields) {
  if (name === 'owner' && ownerFallbackShown.value) return OWNER_INPUT
  const r = refs.find((x) => x.name === name)
  if (r) return { kind: 'ref', f: r }
  const f = fields.find((x) => x.name === name)
  return f ? { kind: 'field', f } : null
}

// A field's storage: action *inputs* live in `fields`, everything else the
// action reads (a limit, an effect die) lives in `context`.
function valueStore(f) {
  return (selectedAction.value?.fields || []).some((x) => x.name === f.name)
    ? newEffect.fields
    : newEffect.context
}

function isResultDieField(f) {
  return f.name === 'result' && f.fieldType === 'die_select'
}

function isScopedTargetField(f) {
  // A path is offered when the action says what a path resolves to — which an
  // action can declare without declaring a picker kind (Step Down Die's target
  // is a die; there is no die picker). One action may accept several kinds of
  // thing, so the declaration is a list.
  return f.name === 'target'
    && !!(selectedAction.value?.targetKind || selectedAction.value?.pathElements?.length)
}

// The target may only be named by a path: destinations are declared, no picker
// kind is, and there is no keyword left to type. The mode row and the literal
// input are then not rendered, and the path is what the form offers.
const pathOnlyTarget = computed(() => {
  const meta = selectedAction.value
  return !!meta?.pathElements?.length && !meta.targetKind
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
  newEffect.targetMode = pathOnlyTarget.value ? 'spec' : 'literal'
  newEffect.targetSpec = { steps: [] }
  targetLocus.value = ''
  newEffect.dieFilter = {}
  newEffect.returnExit = ''
  newEffect.entityMode = 'literal'
  newEffect.entitySpec = { steps: [] }
  newEffect.resultSpec = { steps: [] }
  newEffect.ownerSpec = { steps: [] }
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
  // A path is offered wherever the action says what a path *resolves to* — which
  // an action can declare without a picker kind (`pathElements`: Step Down Die
  // targets a die). Gating the mode on `targetKind` alone meant the editor showed
  // the path but the save silently downgraded it to the keyword target: the
  // author's spec was dropped on every Update.
  const canPath = !!(meta.targetKind || meta.pathElements?.length)
  // A path-only target has no other mode to fall back to, so its mode is `spec`
  // whatever a stale draft says.
  const mode = pathOnlyTarget.value ? 'spec' : (canPath ? (newEffect.targetMode || 'literal') : 'literal')
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
  // The rating: a row of dice for "Dice" mode on an action that declares one, or
  // the single die/named die the author typed. `result` is the row's first die so
  // a single-die reader sees the same thing; an empty row is dropped rather than
  // written as `[]` ([[B307]]).
  const rating = ratingIsRow.value
    ? ratingFieldsFor(resultMode.value, resultDice.value, newEffect.fields.result)
    : null
  if (rating) {
    if (rating.dice) context.dice = rating.dice
    else delete context.dice
  }
  return {
    timing: newEffect.timing || 'IMMEDIATE',
    type: meta.effectType,
    action: meta.effectAction,
    target,
    entity,
    result: meta.implicitResult || (rating ? rating.result : strVal(newEffect.fields.result)),
    dieFilter: newEffect.dieFilter || {},
    negative: meta.supportsPolarity ? !!newEffect.negative : false,
    context,
    duration: (durationOffered.value && (newEffect.duration?.timers || []).length)
      ? {
          timers: newEffect.duration.timers.map(t => ({ event: t.event || 'scene', remaining: Number(t.remaining) || 0 })),
          combine: newEffect.duration.combine || 'FIRST_TO_FIRE',
        }
      : null,
    targetSpec: mode === 'spec' && (newEffect.targetSpec?.steps || []).length ? newEffect.targetSpec : null,
    // A die named by a path: sent only in that mode, so a literal/variable die is
    // never shadowed by a stale spec the author left behind.
    resultSpec: resultMode.value === 'spec' && (newEffect.resultSpec?.steps || []).length ? newEffect.resultSpec : null,
    // One home for the anchor where the action declares the reference: leaving the
    // positional spec behind would fold back in at runtime and resurrect an anchor
    // the author had just cleared ([[B272]]).
    ownerSpec: (!newEffect.refs.owner && (newEffect.ownerSpec?.steps || []).length)
      ? newEffect.ownerSpec : null,
    entitySpec: entityMode === 'spec' && (newEffect.entitySpec?.steps || []).length ? newEffect.entitySpec : null,
    refs: buildRefs(),
    output: (newEffect.output || '').trim() || null,
    conditions: (newEffect.conditions || []).map(c => ({ ...c })),
  }
}

// ── No commit button: the effect writes through as it is edited ─────────
// Every edit persists on its own (B211's convention), and an effect being composed
// is part of its owner's draft — so its fields *are* the draft's fields, and the
// owner's auto-save is the only commit point. Nothing is emitted until an action is
// chosen: an effect with no action is not an effect, which is the one validity rule
// the old Add/Update button enforced (its `commit()` returned early without a meta).
//
// `_lastEmitted` is the guard the other half needs. The owner puts what we send
// back into its list, that arrives as a new `props.value`, and the re-hydrate watch
// below would then rebuild the form from it — resetting the fields under the cursor
// on every keystroke. Skipping the value we just sent is what makes write-through
// safe.
let _lastEmitted = null

watch(
  newEffect,
  () => {
    const meta = selectedAction.value
    if (!meta) return
    const eff = buildEffect(meta)
    _lastEmitted = JSON.stringify(eff)
    emit('save', eff)
  },
  { deep: true, flush: 'sync' },
)

// Populate the editor from an existing effect (edit mode) or leave it blank
// (add mode). Called once on mount; the parent remounts this form per edit.
function populate(eff) {
  const meta = effectActions.value.find(a => a.effectType === eff.type && a.effectAction === eff.action)
  newEffect.actionId = meta?.actionId || ''
  initRefs(meta)
  newEffect.timing = eff.timing || 'IMMEDIATE'
  newEffect.output = eff.output || ''
  newEffect.fields = {}
  newEffect.targetMode = detectTargetMode(eff, meta)
  newEffect.targetSpec = eff.targetSpec || { steps: [] }
  if ((eff.targetSpec?.steps || []).length) newEffect.targetMode = 'spec'
  // A path-only action reads its stored spec, or starts a fresh one — either way
  // the path is the mode, since there is no other input to show.
  if (pathOnlyTarget.value) newEffect.targetMode = 'spec'
  newEffect.dieFilter = eff.dieFilter || {}
  newEffect.entityMode = detectEntityMode(eff)
  newEffect.entitySpec = eff.entitySpec || { steps: [] }
  if ((eff.entitySpec?.steps || []).length) newEffect.entityMode = 'spec'
  newEffect.negative = !!eff.negative
  newEffect.conditions = (eff.conditions || []).map(c => ({ ...c }))
  if (eff.refs) {
    for (const [name, ref] of Object.entries(eff.refs)) {
      if (!newEffect.refs[name]) newEffect.refs[name] = { value: '', spec: { steps: [] } }
      newEffect.refs[name].value = ref?.value || ''
      newEffect.refs[name].spec = ref?.spec || { steps: [] }
    }
  }
  newEffect.conditions = (eff.conditions || []).map(c => ({ ...c }))
  resultMode.value = (eff.resultSpec?.steps || []).length
    ? 'spec'
    : ((eff.result && eff.result.startsWith('{')) ? 'variable' : 'die')
  newEffect.resultSpec = eff.resultSpec || { steps: [] }
  newEffect.ownerSpec = eff.ownerSpec || { steps: [] }
  // The positional owner spec is the fallback the refs migration left behind. Fold
  // it into the declared reference on the way in — the same move `effective_refs`
  // makes at runtime — so a stored path is visible and editable in the **one** owner
  // input instead of sitting in a second one beside it ([[B272]]). Three retired
  // verbs declare `owner_elements` with no owner reference; for them the fallback is
  // still the only home, and nothing here touches it.
  if (newEffect.refs.owner && !(newEffect.refs.owner.spec?.steps || []).length
      && (newEffect.ownerSpec.steps || []).length) {
    newEffect.refs.owner.spec = newEffect.ownerSpec
  }
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
  // The rating row is the authoring truth and `result` its first die; content
  // authored before the row existed carries only `result`, so the row is seeded
  // from it — a value the form cannot see is a value it erases on the next save
  // ([[B307]]). Set *after* `context` so it survives the known/extra split, and
  // only on an action that actually creates a whole rating.
  if (ratingIsRow.value) knownCtx.dice = ratingRowFor(ctx.dice, eff.result)
  newEffect.duration = eff.duration
    ? {
        timers: (eff.duration.timers || []).map(t => ({ event: t.event || 'scene', remaining: t.remaining ?? 0 })),
        combine: eff.duration.combine || 'FIRST_TO_FIRE',
      }
    : { timers: [], combine: 'FIRST_TO_FIRE' }
}

// Reset the form to a blank (add-mode) state.
function resetBlank() {
  newEffect.actionId = ''
  newEffect.timing = 'IMMEDIATE'
  newEffect.fields = {}
  newEffect.context = {}
  newEffect.extraContext = {}
  newEffect.duration = { timers: [], combine: 'FIRST_TO_FIRE' }
  newEffect.targetMode = pathOnlyTarget.value ? 'spec' : 'literal'
  newEffect.targetSpec = { steps: [] }
  targetLocus.value = ''
  newEffect.dieFilter = {}
  newEffect.returnExit = ''
  newEffect.entityMode = 'literal'
  newEffect.entitySpec = { steps: [] }
  newEffect.resultSpec = { steps: [] }
  newEffect.ownerSpec = { steps: [] }
  newEffect.negative = false
  newEffect.refs = {}
  newEffect.conditions = []
  resultMode.value = 'die'
  effectDieMode.value = 'variable'
}

// Hydrate the form from an effect. ``effectActions`` must be loaded first so an
// existing effect's (type, action) resolves to an actionId.
async function hydrate(eff) {
  await load()
  if (eff) populate(eff)
  else resetBlank()
}

onMounted(() => { hydrate(props.value) })

// The parent reuses this form instance when the user switches which effect they
// are editing (the child panel is replaced in place, not remounted), so re-sync
// when the effect changes — otherwise the form keeps showing the previous one.
watch(() => props.value, (eff) => {
  // Skip the echo of what this form just emitted (see the write-through watcher):
  // re-hydrating our own write would reset the fields under the cursor.
  if (eff && _lastEmitted && JSON.stringify(eff) === _lastEmitted) return
  hydrate(eff)
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
.ee-form-title { display: flex; align-items: center; justify-content: space-between; font-size: 10px; font-weight: 600; color: var(--accent); text-transform: uppercase; }
.ee-form-close { border: none; background: none; padding: 0 2px; color: var(--text-dim); cursor: pointer; font-size: 11px; }
.ee-form-close:hover { color: var(--text); }
.ee-form select, .ee-form input, .ee-form textarea { font-size: 11px; padding: 4px 6px; background: var(--overlay-6); color: var(--text); border: 1px solid var(--overlay-10); border-radius: 4px; font-family: inherit; width: 100%; box-sizing: border-box; }
.ee-form textarea { resize: vertical; min-height: 34px; }
.ee-field { display: flex; flex-direction: column; gap: 2px; }
/* The target controls (mode + scope + filters + picker) are one idea: box them
   so they read as "this is the target", not as four loose inputs. */
.ee-target-group {
  display: flex; flex-direction: column; gap: 4px;
  border: 1px solid var(--overlay-12); border-left: 2px solid var(--overlay-30);
  border-radius: 5px; padding: 6px 8px; margin-top: 2px;
  background: var(--overlay-6);
}
.ee-timing-top { display: flex; flex-direction: column; gap: 2px; margin-bottom: 2px; }
.ee-extra-row { display: flex; align-items: center; gap: 6px; }
.ee-extra-key { font-size: 9px; color: var(--text-dim); font-family: monospace; flex: none; min-width: 90px; }
.ee-extra-row input { flex: 1; min-width: 0; }
.ee-mode-row { display: flex; margin-top: 2px; }
.ee-field label, .ee-timing-label { font-size: 9px; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.5px; }
.ee-help { font-size: 9px; color: var(--text-dim); font-style: italic; }
.ee-field-help { font-size: 10px; color: var(--text-dim); margin: 2px 0 0; }
.ee-ref-element { font-style: normal; font-family: monospace; font-size: 8px; color: var(--text-dim); margin-left: 4px; }
.ee-output-row { display: flex; align-items: center; gap: 6px; }
.ee-output-row input { flex: 1; min-width: 0; }
.ee-output-row select { flex: none; }
.ee-output-remove { background: var(--danger-12); border: 1px solid var(--danger-45); color: var(--danger-pale); border-radius: 4px; cursor: pointer; font-size: 10px; padding: 2px 6px; }
.ee-output-add { align-self: flex-start; font-size: 10px; padding: 3px 8px; border-radius: 4px; background: var(--overlay-6); border: 1px solid var(--overlay-12); color: var(--text); cursor: pointer; }
.ee-fixed-dest { font-size: 10px; color: var(--text-dim); }
.ee-fixed-dest b { color: var(--text); font-weight: 600; }
.ee-vars { display: flex; flex-wrap: wrap; align-items: center; gap: 4px; }
.ee-vars-label { font-size: 9px; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.5px; }
.ee-var { font-size: 10px; font-family: monospace; padding: 2px 6px; background: var(--accent-12); border: 1px solid var(--accent-dim); border-radius: 4px; color: var(--accent); cursor: pointer; }
.ee-var.copied { background: rgba(64,184,96,0.2); border-color: var(--success); color: var(--success); }
.ee-var-type { font-style: normal; font-family: inherit; font-size: 8px; color: var(--text-dim); margin-left: 3px; }
.ee-result-mode { display: flex; gap: 4px; }
.ee-result-mode button { font-size: 9px; padding: 2px 7px; border-radius: 4px; background: var(--overlay-6); border: 1px solid var(--overlay-10); color: var(--text-dim); cursor: pointer; }
.ee-result-mode button.active { background: var(--accent-20); border-color: var(--accent-dim); color: var(--accent); }
.ee-check { display: flex; align-items: center; gap: 5px; font-size: 11px; color: var(--text); text-transform: none; letter-spacing: 0; cursor: pointer; }
.ee-check input { width: auto; }
.ee-preview { font-size: 10px; color: var(--accent); font-style: italic; margin-top: 2px; }
</style>
