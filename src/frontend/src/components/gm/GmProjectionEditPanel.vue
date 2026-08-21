<template>
  <div>
    <div class="proj-id">ID: {{ projection.id }}</div>
    <div class="ps-form">
      <label>Name</label>
      <input v-model="name" placeholder="Projection name (falls back to entity)" />

      <label>Background Image</label>
      <div class="image-row">
        <MediaImage v-if="backgroundImage" :src="backgroundImage" class="proj-preview" />
        <span v-else class="proj-preview proj-preview-empty">🖼</span>
        <input v-model="backgroundImage" placeholder="/media/… or URL" class="image-input" />
        <button v-if="backgroundImage" type="button" class="clear-btn" title="Clear image" @click="backgroundImage = ''">✕</button>
      </div>

      <label>Current Location</label>
      <GmLocationPicker v-model="currentLocation" placeholder="Search location…" :universe="projection.universe" @select="onLocationSelect" />

      <div class="readonly-row">
        <span>Origin: {{ universeName(projection.originUniverse) }}</span>
        <span>Type: {{ (projection.transversalType || 'native').toLowerCase() }}</span>
        <span v-if="projection.universe !== projection.originUniverse">Current universe: {{ universeName(projection.universe) }}</span>
      </div>
    </div>

    <div class="actions">
      <button class="save-btn" :disabled="saving" @click="save">{{ saving ? 'Saving…' : 'Save' }}</button>
      <button class="cancel-btn" @click="panel.close()">Cancel</button>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useEntityCrud } from '@/composables/useEntityCrud.js'
import { useUniverseNames } from '@/composables/useUniverseNames.js'
import { usePanel } from '@/composables/usePanel.js'
import GmLocationPicker from '@/components/gm/GmLocationPicker.vue'
import MediaImage from '@/components/MediaImage.vue'

const props = defineProps({
  projection: { type: Object, required: true },
})

const panel = usePanel()
const { updateProjection } = useEntityCrud()

const name = ref(props.projection.name || '')
const backgroundImage = ref(props.projection.backgroundImage || '')
const currentLocation = ref(props.projection.currentLocation || '')
const saving = ref(false)

const { name: universeName, load: loadUniverseNames } = useUniverseNames()

onMounted(loadUniverseNames)

function onLocationSelect(loc) {
  currentLocation.value = loc.id
}

async function save() {
  saving.value = true
  try {
    await updateProjection(props.projection.id, {
      name: name.value,
      backgroundImage: backgroundImage.value || null,
      currentLocation: currentLocation.value || null,
    })
    panel.close()
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.proj-id {
  font-family: monospace;
  font-size: 11px;
  color: var(--text-dim);
  margin-bottom: 8px;
}
.ps-form {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.ps-form label {
  font-size: 10px;
  color: var(--text-dim);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-top: 6px;
}
.ps-form input {
  font-size: 12px;
  padding: 6px 8px;
}
.image-row {
  display: flex;
  align-items: center;
  gap: 6px;
}
.proj-preview {
  width: 40px;
  height: 40px;
  object-fit: cover;
  border-radius: 4px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  flex: 0 0 auto;
}
.proj-preview-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
  color: var(--text-dim);
  background: rgba(255, 255, 255, 0.04);
}
.image-input {
  flex: 1;
  min-width: 0;
}
.clear-btn {
  background: transparent;
  border: none;
  color: var(--text-dim);
  cursor: pointer;
  font-size: 13px;
  padding: 0 4px;
}
.clear-btn:hover {
  color: #e06060;
}
.readonly-row {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  font-size: 10px;
  color: var(--text-dim);
  margin-top: 8px;
}
.actions {
  display: flex;
  gap: 6px;
  margin-top: 14px;
}
.save-btn {
  background: var(--success);
  color: #0a0a0f;
  font-weight: 600;
  padding: 6px 14px;
  border-radius: 6px;
  border: none;
  cursor: pointer;
  font-size: 12px;
}
.save-btn:disabled {
  opacity: 0.5;
  cursor: default;
}
.cancel-btn {
  padding: 6px 14px;
  border-radius: 6px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  background: rgba(255, 255, 255, 0.03);
  color: var(--text);
  cursor: pointer;
  font-size: 12px;
}
.cancel-btn:hover {
  background: rgba(255, 255, 255, 0.06);
}
</style>
