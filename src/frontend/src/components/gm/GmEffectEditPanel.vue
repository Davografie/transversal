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
      @cancel="close"
    />
  </div>
</template>

<script setup>
import { computed, inject, ref, watch } from 'vue'
import EffectForm from './EffectForm.vue'
import { createSfxEdit } from '@/composables/useSfxEdit.js'
import { useSfxMeta } from '@/composables/useSfxMeta.js'
import { useTargetCatalog } from '@/composables/useTargetCatalog.js'
import { usePanel } from '@/composables/usePanel.js'

const props = defineProps({
  // Identity only (Rule 6): which effect to edit, or null to add. The effect
  // data itself lives in the shared useSfxEdit draft.
  index: { type: Number, default: null },
})

const panel = usePanel()
// The SFX editor provides its instance, so this child edits the same draft as
// its parent panel. A standalone open (none today) falls back to a private
// instance rather than a shared global.
const { draft, scopeVariables, save } = inject('sfxEdit', null) || createSfxEdit()
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
// activation's own (the trigger's declared variables and the source token),
// the SFX's conditions, and the effects *before* the one being edited.
const outputVariables = ref({})

function priorEffects() {
  const limit = props.index === null ? draft.effects.length : props.index
  return draft.effects.slice(0, limit)
}

watch(
  () => [draft.effects, draft.conditions, draft.trigger, draft.source_kind, props.index, sourceElement.value],
  async () => {
    outputVariables.value = await collectVariables(
      priorEffects(), sourceElement.value || null, draft.conditions || null,
      draft.trigger || null, draft.source_kind || null,
    )
  },
  { immediate: true, deep: true },
)

async function onSave(eff) {
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
  //
  // Awaited, and the panel only closes on success: closing before the write
  // settles lets the parent re-read the SFX list while it is still the previous
  // version, and the reload then discards the effect that was just added.
  const ok = await save()
  if (!ok) return
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
