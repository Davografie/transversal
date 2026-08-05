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

    <!-- Background image + overlay: only LOCATION -->
    <template v-if="isLocation">
      <label>Background Image</label>
      <div class="bg-image-row">
        <input v-model="local.background_image" placeholder="/media/…" class="bg-url" @input="emitUpdate" />
        <input type="file" accept="image/*" @change="$emit('upload-bg', $event)" class="bg-upload" />
      </div>
      <img v-if="local.background_image" :src="local.background_image" class="bg-preview" />

      <label>Overlay Effect</label>
      <select v-model="local.overlay" @change="emitUpdate">
        <option :value="null">None</option>
        <option value="mist">Mist</option>
        <option value="fire">Fire</option>
        <option value="rain">Rain</option>
        <option value="snow">Snow</option>
        <option value="fog">Fog</option>
      </select>
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

const emit = defineEmits(['update:modelValue', 'upload-bg'])

const local = ref({ ...props.modelValue })

watch(() => props.modelValue, (v) => { local.value = { ...v } }, { deep: true })

function emitUpdate() {
  emit('update:modelValue', { ...local.value })
}

// ── Field visibility by entity type ──────────────────
const RAZMERIT_TYPES = new Set(['CHARACTER', 'GMC', 'FACTION'])
const isLocation = computed(() => local.value.type === 'LOCATION')
const showRazmerit = computed(() => RAZMERIT_TYPES.has(local.value.type))
</script>

<style scoped>
.entity-form { display: flex; flex-direction: column; gap: 8px; }
.entity-form label {
  font-size: 11px; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.5px;
}
.entity-form input, .entity-form select { font-size: 13px; padding: 6px 10px; }

.bg-image-row { display: flex; gap: 6px; }
.bg-url { flex: 1; font-size: 12px !important; }
.bg-upload {
  font-size: 11px; padding: 4px 8px; cursor: pointer;
  background: var(--accent-dim); color: var(--text); border-radius: 6px; border: none;
  white-space: nowrap; max-width: 120px; overflow: hidden;
}
.bg-upload::file-selector-button { display: none; }
.bg-preview { width: 100%; max-height: 120px; object-fit: cover; border-radius: 6px; margin-top: 4px; }
</style>
