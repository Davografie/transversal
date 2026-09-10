<template>
  <div class="geep-root">
    <EffectForm
      :value="editingEffect"
      :variables="scopeVariables"
      :source-element="sourceElement"
      :output-variables="outputVariables"
      @save="onSave"
      @cancel="close"
    />
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import EffectForm from './EffectForm.vue'
import { useSfxEdit } from '@/composables/useSfxEdit.js'
import { useTargetCatalog } from '@/composables/useTargetCatalog.js'
import { usePanel } from '@/composables/usePanel.js'

const props = defineProps({
  // Identity only (Rule 6): which effect to edit, or null to add. The effect
  // data itself lives in the shared useSfxEdit draft.
  index: { type: Number, default: null },
})

const panel = usePanel()
const { draft, scopeVariables, save } = useSfxEdit()
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

// Typed output variables emitted by the SFX's conditions and by effects
// *before* the one being edited, available to `select variable` (cross-effect),
// traced with the SFX source.
const outputVariables = ref({})

function priorEffects() {
  const limit = props.index === null ? draft.effects.length : props.index
  return draft.effects.slice(0, limit)
}

watch(
  () => [draft.effects, draft.conditions, props.index, sourceElement.value],
  async () => {
    outputVariables.value = await collectVariables(
      priorEffects(), sourceElement.value || null, draft.conditions || null,
    )
  },
  { immediate: true, deep: true },
)

function onSave(eff) {
  const adding = props.index === null
  if (adding) {
    draft.effects = [...draft.effects, eff]
  } else {
    const next = [...draft.effects]
    next[props.index] = eff
    draft.effects = next
  }
  // Persist immediately: the effect form's Update/Add is the user's commit
  // point for this effect, so saving here removes the separate SFX-panel
  // "Save now" step (and any reliance on the debounced auto-save). A no-op for
  // a brand-new SFX (no id yet) — the create flow saves the whole draft.
  save()
  // Update leaves the panel open so an effect can be iterated on in place (the
  // form reloads from the draft, and this panel is pinned to one effect index).
  // Adding still closes — the next effect is a different form instance.
  if (adding) panel.close()
}

function close() {
  panel.close()
}
</script>

<style scoped>
.geep-root {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
</style>
