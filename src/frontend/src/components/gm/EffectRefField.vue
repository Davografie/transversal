<template>
  <div class="ee-field ee-ref">
    <label>{{ refDef.label }} <em class="ee-ref-element">{{ (refDef.elements || []).join(' / ') }}</em></label>
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
import PathField from './PathField.vue'

defineProps({
  refDef: { type: Object, required: true },
  modelValue: { type: Object, default: () => ({ steps: [] }) },
  sourceElement: { type: String, default: '' },
  variables: { type: Object, default: null },   // { name: {element, cardinality} }
})
const emit = defineEmits(['update:modelValue'])
</script>

<style scoped>
.ee-ref-element { font-style: normal; opacity: 0.6; }
</style>
