<template>
  <div class="ee-root">
    <EffectList
      :model-value="effects"
      :editing-index="editingIndex"
      @update:model-value="effects = $event"
      @add="openAdd"
      @edit="openEdit"
    />

    <div v-if="showEditor" class="ee-inline-form">
      <EffectForm
        :key="formKey"
        :value="editingIndex !== null ? effects[editingIndex] : null"
        :universe="universe"
        :life-path="lifePath"
        :variables="chipVariables"
        :output-variables="outputVariables"
        :scope-variables="resolvedScope"
        :portal-destination="portalDestination"
        :portal-target-type="portalTargetType"
        :portal-universe="portalUniverse"
        :portal-root-id="portalRootId"
        :closable="true"
        @save="onSave"
        @cancel="closeEditor"
      />
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import EffectList from './EffectList.vue'
import EffectForm from './EffectForm.vue'
import { useTargetCatalog } from '@/composables/useTargetCatalog.js'
import { useBoundVariableScope } from '@/composables/useBoundVariableScope.js'

const props = defineProps({
  modelValue: { type: Array, default: () => [] },
  universe: { type: String, default: '' },
  lifePath: { type: String, default: '' },
  variables: { type: Array, default: () => [] },
  // Names already in scope when this effect runs that **no earlier effect
  // produced** — a roll table's bound variables, resolved before any row's effects
  // run ([[B281]]). `{name: {element, cardinality}}`, the same shape an output
  // variable has, so `select variable` offers them identically. Without this a
  // table's declared names would be authorable but unusable in the effects that
  // are supposed to consume them.
  scopeVariables: { type: Object, default: () => ({}) },
  // Declaration rows to resolve **on top of** `scopeVariables` before this effect
  // runs — the chosen row's own bound variables ([[B281]]). Resolved per editor
  // instance, which is what lets the connector column's effect builder see the
  // names *that row* exposes: the row's names resolve after the table's, exactly
  // as `table_bindings()` orders them.
  scopeDeclarations: { type: Array, default: () => [] },
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

const { collectVariables } = useTargetCatalog()

// The names this effect may start a targeting path from: the ones already in scope
// (`scopeVariables` — a table's ambient facts and its own declarations) plus this
// row's own declarations, traced against them ([[B281]]). The composable returns
// both merged, so this is the engine's own order.
const { scope: resolvedScope } = useBoundVariableScope(
  computed(() => props.scopeDeclarations || []),
  computed(() => props.scopeVariables || {}),
)

// The `{name}` chips, which are the same names by a different route — a flat field
// substitutes one, and both layers are substitutable.
const chipVariables = computed(() => {
  const declared = Object.entries(resolvedScope.value || {}).map(([name, t]) => ({
    name, type: (t && t.element) || '',
  }))
  const known = new Set((props.variables || []).map(v => v.name || v))
  return [...(props.variables || []), ...declared.filter(v => !known.has(v.name))]
})

const showEditor = ref(false)
const editingIndex = ref(null)
// Bumped on every open so the form remounts and re-populates from `value`
// (add ↔ edit, or switching the edited index while the form stays open).
const formKey = ref(0)

// Bound, typed output variables emitted by effects *before* the one being
// edited, available to `select variable` in the targeting wizard.
const outputVariables = ref({})

function priorEffects() {
  const limit = editingIndex.value !== null ? editingIndex.value : props.modelValue.length
  return props.modelValue.slice(0, limit)
}

watch(
  () => [props.modelValue, editingIndex.value],
  async () => {
    outputVariables.value = await collectVariables(priorEffects())
  },
  { immediate: true, deep: true },
)

// Write-through: the form emits on every change, so the *first* emit of an add
// appends the row and every later one replaces it. Local to the open, because
// `editingIndex` is reset when the form closes.
let writingIndex = null

function openAdd() {
  writingIndex = null
  editingIndex.value = null
  formKey.value++
  showEditor.value = true
}

function openEdit(i) {
  writingIndex = i
  editingIndex.value = i
  formKey.value++
  showEditor.value = true
}

function onSave(eff) {
  if (writingIndex === null) {
    const next = [...props.modelValue, eff]
    emit('update:modelValue', next)
    writingIndex = next.length - 1
  } else {
    const next = [...props.modelValue]
    next[writingIndex] = eff
    emit('update:modelValue', next)
  }
  // The form stays open: with no commit button it is dismissed by its own ✕ (this
  // is the only *inline* consumer of the form), not by finishing an edit.
}

function closeEditor() {
  showEditor.value = false
  editingIndex.value = null
  writingIndex = null
}
</script>

<style scoped>
.ee-root { display: flex; flex-direction: column; gap: 4px; }
.ee-inline-form { margin-top: 6px; padding: 8px; background: var(--overlay-4); border: 1px solid var(--overlay-8); border-radius: 6px; }
</style>
