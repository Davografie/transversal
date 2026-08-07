<template>
  <div class="entity-form">
    <label>Name</label>
    <input v-model="local.name" @input="emitUpdate" />

    <label>Type</label>
    <select v-model="local.type" :disabled="!allowTypeChange" @change="emitUpdate">
      <option v-for="t in entityTypes" :key="t" :value="t">{{ t }}</option>
    </select>

    <!-- Universe, Location, and Parent Location are managed by drag-and-drop in the tree view. -->

    <!-- Razmerit: only CHARACTER, GMC, FACTION -->
    <template v-if="showRazmerit">
      <label>Razmerit</label>
      <input v-model.number="local.razmerit" type="number" @input="emitUpdate" />
    </template>

    <label>
      <input v-model="local.hidden" type="checkbox" @change="emitUpdate" />
      Hidden
    </label>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'

const props = defineProps({
  modelValue: { type: Object, default: () => ({}) },
  entityId: { type: String, default: null },
  allowTypeChange: { type: Boolean, default: false },
  entityTypes: { type: Array, default: () => ['CHARACTER', 'LOCATION', 'GMC', 'FACTION', 'ASSET'] },
})

const emit = defineEmits(['update:modelValue'])

const local = ref({ ...props.modelValue })

watch(() => props.modelValue, (v) => { local.value = { ...v } }, { deep: true })

function emitUpdate() {
  emit('update:modelValue', { ...local.value })
}

// ── Field visibility by entity type ──────────────────
const RAZMERIT_TYPES = new Set(['CHARACTER', 'GMC', 'FACTION'])
const showRazmerit = computed(() => RAZMERIT_TYPES.has(local.value.type))
</script>

<style scoped>
.entity-form { display: flex; flex-direction: column; gap: 8px; }
.entity-form label {
  font-size: 11px; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.5px;
}
.entity-form input, .entity-form select { font-size: 13px; padding: 6px 10px; }

</style>
