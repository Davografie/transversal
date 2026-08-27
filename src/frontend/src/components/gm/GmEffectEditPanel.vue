<template>
  <div class="geep-root">
    <EffectForm
      :value="editingEffect"
      :variables="scopeVariables"
      @save="onSave"
      @cancel="close"
    />
  </div>
</template>

<script setup>
import { computed } from 'vue'
import EffectForm from './EffectForm.vue'
import { useSfxEdit } from '@/composables/useSfxEdit.js'
import { usePanel } from '@/composables/usePanel.js'

const props = defineProps({
  // Identity only (Rule 6): which effect to edit, or null to add. The effect
  // data itself lives in the shared useSfxEdit draft.
  index: { type: Number, default: null },
})

const panel = usePanel()
const { draft, scopeVariables } = useSfxEdit()

const editingEffect = computed(() => (props.index === null ? null : (draft.effects[props.index] || null)))

function onSave(eff) {
  if (props.index === null) {
    draft.effects = [...draft.effects, eff]
  } else {
    const next = [...draft.effects]
    next[props.index] = eff
    draft.effects = next
  }
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
