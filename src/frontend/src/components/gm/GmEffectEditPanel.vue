<template>
  <div class="geep-root">
    <EffectForm
      :value="editingEffect"
      :variables="scopeVariables"
      :source-element="sourceElement"
      :trigger="draft.trigger"
      :placement="draft.placement"
      :output-variables="outputVariables"
      @save="onSave"
    />
  </div>
</template>

<script setup>
import { computed, inject, ref, watch } from 'vue'
import EffectForm from './EffectForm.vue'
import { createSfxEdit } from '@/composables/useSfxEdit.js'
import { useSfxMeta } from '@/composables/useSfxMeta.js'
import { useTargetCatalog } from '@/composables/useTargetCatalog.js'

const props = defineProps({
  // Identity only (Rule 6): which effect to edit, or null to add. The effect
  // data itself lives in the shared useSfxEdit draft.
  index: { type: Number, default: null },
})

// The SFX editor provides its instance, so this child edits the same draft as
// its parent panel. A standalone open (none today) falls back to a private
// instance rather than a shared global.
const { draft, scopeVariables } = inject('sfxEdit', null) || createSfxEdit()
const { load: loadCatalog, sourceKinds, collectVariables } = useTargetCatalog()
loadCatalog()

const editingEffect = computed(() => (props.index === null ? null : (draft.effects[props.index] || null)))

// The SFX's declared source_kind → its catalog element, so the targeting
// wizard can offer `select source` typed against it.
const sourceElement = computed(() => {
  const sk = draft.source_kind
  if (!sk) return ''
  const found = sourceKinds().find(s => s.value === sk)
  return found ? found.element : ''
})

// Typed names available to `select variable` in this effect's paths: the
// activation's own (the trigger's declared variables and the source token), the
// rule's **declared** bound variables (bound before the conditions, so before
// every effect), the SFX's conditions, and the effects *before* the one being
// edited.
const outputVariables = ref({})

function priorEffects() {
  const limit = props.index === null ? draft.effects.length : props.index
  return draft.effects.slice(0, limit)
}

watch(
  () => [draft.effects, draft.conditions, draft.trigger, draft.source_kind, draft.bound_variables, props.index, sourceElement.value],
  async () => {
    outputVariables.value = await collectVariables(
      priorEffects(), sourceElement.value || null, draft.conditions || null,
      draft.trigger || null, draft.source_kind || null,
      draft.bound_variables || null,
    )
  },
  { immediate: true, deep: true },
)

// Write-through: the form emits on every change, so the *first* emit of an add
// appends the effect and every later one replaces it. Nothing is saved from here
// and nothing closes: the SFX composer's own auto-save follows its **whole draft**
// (useSfxEdit), which is the commit point now that the form has no button. That
// also removes the old failure mode where closing before the write settled let the
// parent re-read the list and discard the effect just added.
let workingIndex = props.index

function onSave(eff) {
  if (workingIndex === null) {
    draft.effects = [...draft.effects, eff]
    workingIndex = draft.effects.length - 1
  } else {
    const next = [...draft.effects]
    next[workingIndex] = eff
    draft.effects = next
  }
}
</script>

<style scoped>
.geep-root {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
</style>
