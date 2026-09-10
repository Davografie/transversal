<template>
  <div>
    <div class="ps-form">
      <label>Name</label>
      <input v-model="name" placeholder="Projection name (falls back to entity)" />

      <label>Current Location</label>
      <TargetPicker v-model="currentLocation" kind="location" :scope="projection.universe ? `universe:${projection.universe}` : ''" placeholder="Search location…" />

      <label>Type</label>
      <select v-model="transversalType">
        <option value="NATIVE">native</option>
        <option value="CONSCIOUSNESS">consciousness</option>
        <option value="INAPPOSITE">inapposite</option>
      </select>

      <div class="readonly-row">
        <span>Origin: {{ universeName(projection.originUniverse) }}</span>
        <span v-if="projection.universe !== projection.originUniverse">Current universe: {{ universeName(projection.universe) }}</span>
      </div>
    </div>

    <div class="actions">
      <Button class="save-btn" :loading="saving" :disabled="saving" @click="save" variant="success" solid>{{ saving ? 'Saving…' : 'Save' }}</Button>
      <Button class="cancel-btn" variant="neutral" @click="panel.close()">Cancel</Button>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useEntityCrud } from '@/composables/useEntityCrud.js'
import { useUniverseNames } from '@/composables/useUniverseNames.js'
import { usePanel } from '@/composables/usePanel.js'
import TargetPicker from '@/components/ui/TargetPicker.vue'
import Button from '@/components/ui/Button.vue'

const props = defineProps({
  projection: { type: Object, required: true },
})

const panel = usePanel()
const { updateProjection } = useEntityCrud()

const name = ref(props.projection.name || '')
const currentLocation = ref(props.projection.currentLocation || '')
const transversalType = ref(props.projection.transversalType || 'NATIVE')
const saving = ref(false)

const { name: universeName, load: loadUniverseNames } = useUniverseNames()

onMounted(loadUniverseNames)

async function save() {
  saving.value = true
  try {
    await updateProjection(props.projection.id, {
      name: name.value,
      currentLocation: currentLocation.value || null,
      transversalType: transversalType.value,
    })
    panel.close()
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
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
  border: 1px solid var(--overlay-12);
  flex: 0 0 auto;
}
.proj-preview-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
  color: var(--text-dim);
  background: var(--overlay-4);
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
  color: var(--danger-soft);
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
.actions .cancel-btn {
  padding: 6px 14px;
}
</style>
