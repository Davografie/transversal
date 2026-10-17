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
import { computed, onMounted } from 'vue'
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
// reference will take ([[B326]]). The catalog is a shared singleton: `load` is
// idempotent and already been called wherever a path is edited.
const { load, elementLabel } = useTargetCatalog()
// Swallowed: this is a label. A catalog that cannot load leaves the names raw,
// which is what it showed before this existed — it must never become a render
// error on a form that has nothing to do with targeting.
onMounted(() => { load().catch(() => {}) })

const elementNames = computed(() =>
  (props.refDef.elements || []).map(elementLabel).join(' / '))
</script>

<style scoped>
.ee-ref-element { font-style: normal; opacity: 0.6; }
</style>
