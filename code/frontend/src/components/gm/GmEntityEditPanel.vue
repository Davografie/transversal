<template>
  <div>
    <div class="form-actions top-actions">
      <button class="sheet-edit-btn" @click="$emit('switch-to-sheet')">Sheet</button>
      <button class="danger-btn" @click="$emit('delete')">Delete</button>
    </div>
    <GmEntityForm
      :model-value="form"
      @update:model-value="onFormUpdate"
      :universes="universes"
      :location-entities="locationEntities"
      :parent-id="parentId"
      :entity-id="entityId"
      @update:parent-id="onParentUpdate"
      @upload-bg="(e) => $emit('upload-bg', e)"
    />
    <TraitEditor
      :traits="traitSettings"
      :available-traits="availableTraits"
      :adding="addingTrait"
      @add-trait="(i) => $emit('add-trait', i)"
      @remove-trait="(id) => $emit('remove-trait', id)"
    />
  </div>
</template>

<script setup>
import GmEntityForm from '@/components/gm/GmEntityForm.vue'
import TraitEditor from '@/components/gm/TraitEditor.vue'

defineProps({
  form: { type: Object, default: () => ({}) },
  universes: { type: Array, default: () => [] },
  locationEntities: { type: Array, default: () => [] },
  parentId: { type: String, default: null },
  entityId: { type: String, default: null },
  traitSettings: { type: Array, default: () => [] },
  availableTraits: { type: Array, default: () => [] },
  addingTrait: { type: Boolean, default: false },
})

const emit = defineEmits(['update:form', 'update:parent-id', 'upload-bg', 'add-trait', 'remove-trait', 'switch-to-sheet', 'delete'])

function onFormUpdate(v) { emit('update:form', v) }
function onParentUpdate(v) { emit('update:parent-id', v) }
</script>

<style scoped>
.form-actions { display: flex; gap: 6px; }
.top-actions { justify-content: space-between; margin-bottom: 4px; }
.sheet-edit-btn { background: var(--accent); color: #fff; font-size: 11px; padding: 4px 10px; border-radius: 4px; border: none; cursor: pointer; }
.danger-btn { background: var(--danger); color: #fff; font-size: 11px; padding: 4px 10px; border-radius: 4px; border: none; cursor: pointer; }
</style>
