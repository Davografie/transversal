<template>
  <div class="geep-root">
    <EffectEditor v-model="draft.effects" :variables="scopeVariables" />
  </div>
</template>

<script setup>
import EffectEditor from './EffectEditor.vue'
import { useSfxEdit } from '@/composables/useSfxEdit.js'

// Child panel for the SFX editor: edits the shared draft.effects state owned by
// useSfxEdit (no prop-drilling — the singleton carries identity + data).
const { draft, scopeVariables } = useSfxEdit()
</script>

<style scoped>
.geep-root {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
</style>
