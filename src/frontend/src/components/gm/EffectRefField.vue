<template>
  <div class="ee-field ee-ref">
    <label>{{ refDef.label }} <em class="ee-ref-element">{{ elementNames }}</em></label>
    <PathField
      :model-value="modelValue"
      :destination="{ elements: refDef.elements || [] }"
      :source-element="sourceElement"
      :variables="variables"
      :title="refDef.label"
      @update:model-value="emit('update:modelValue', $event)"
    />
  </div>
</template>

<script setup>
// One named reference of an effect action, as its own component so the effect form
// can place it anywhere in the field order (`EffectActionMeta.field_order`) rather
// than only before or after the field block. The path itself is edited in a child
// panel (`PathField`), so a reference contributes one line to the form.
import { computed } from 'vue'
import PathField from './PathField.vue'
import { useTargetCatalog } from '@/composables/useTargetCatalog.js'

const props = defineProps({
  refDef: { type: Object, required: true },
  modelValue: { type: Object, default: () => ({ steps: [] }) },
  sourceElement: { type: String, default: '' },
  variables: { type: Object, default: null },   // { name: {element, cardinality} }
})
const emit = defineEmits(['update:modelValue'])

// The elements a reference accepts, in the author's words. Raw catalog names read
// as jargon once a reference accepts more than one — "traitsetsetting" is not a
// thing anyone says — and this line is the only place the form says what the
// reference will take ([[B326]]).
//
// **It does not load the catalog.** Every host of `EffectForm` already does
// (`GmSfxEditPanel`, `GmEffectEditPanel`, `EffectEditor`, `GmDraftEffectPanel`), and
// a field that fetches on mount fetches once per field per mount — which is the
// wrong thing to add to a form that can appear many times in one panel, and it
// made every remount of the GM panel issue its own catalog read. Until the shared
// catalog arrives the names are raw, which is what they were before this line.
const { elementLabel } = useTargetCatalog()

const elementNames = computed(() =>
  (props.refDef.elements || []).map(elementLabel).join(' / '))
</script>

<style scoped>
.ee-ref-element { font-style: normal; opacity: 0.6; }
</style>
