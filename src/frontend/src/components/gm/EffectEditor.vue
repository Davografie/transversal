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
        :variables="variables"
        :output-variables="outputVariables"
        :portal-destination="portalDestination"
        :portal-target-type="portalTargetType"
        :portal-universe="portalUniverse"
        :portal-root-id="portalRootId"
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

const { collectVariables } = useTargetCatalog()

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

function openAdd() {
  editingIndex.value = null
  formKey.value++
  showEditor.value = true
}

function openEdit(i) {
  editingIndex.value = i
  formKey.value++
  showEditor.value = true
}

function onSave(eff) {
  if (editingIndex.value !== null) {
    const next = [...props.modelValue]
    next[editingIndex.value] = eff
    emit('update:modelValue', next)
  } else {
    emit('update:modelValue', [...props.modelValue, eff])
  }
  closeEditor()
}

function closeEditor() {
  showEditor.value = false
  editingIndex.value = null
}
</script>

<style scoped>
.ee-root { display: flex; flex-direction: column; gap: 4px; }
.ee-inline-form { margin-top: 6px; padding: 8px; background: var(--overlay-4); border: 1px solid var(--overlay-8); border-radius: 6px; }
</style>
