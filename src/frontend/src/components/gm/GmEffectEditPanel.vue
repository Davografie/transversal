<template>
  <div class="geep-root">
    <EffectForm
      :value="editingEffect"
      :variables="scopeVariables"
      :source-element="sourceElement"
      @save="onSave"
      @cancel="close"
    />
  </div>
</template>

<script setup>
import { computed } from 'vue'
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
const { load: loadCatalog, sourceKinds } = useTargetCatalog()
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

function onSave(eff) {
  if (props.index === null) {
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
  panel.close()
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
