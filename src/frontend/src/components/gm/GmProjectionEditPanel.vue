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
        <span v-if="saving" class="save-status">Saving…</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, watch, inject } from 'vue'
import { useEntityCrud } from '@/composables/useEntityCrud.js'
import { useUniverseNames } from '@/composables/useUniverseNames.js'
import TargetPicker from '@/components/ui/TargetPicker.vue'

const props = defineProps({
  projection: { type: Object, required: true },
})

// The entity panel that opened this one provides its own editor instance, so
// the updated projection lands in the list that panel actually renders (the
// shared instance's list is not on screen anywhere). Fall back to the shared
// instance if opened outside that tree.
const { updateProjection } = inject('entityEditor', null) || useEntityCrud()

const name = ref(props.projection.name || '')
const currentLocation = ref(props.projection.currentLocation || '')
const transversalType = ref(props.projection.transversalType || 'NATIVE')
const saving = ref(false)

const { name: universeName, load: loadUniverseNames } = useUniverseNames()

onMounted(loadUniverseNames)

// Auto-save, like the trait and trait-set editors: no Save button, no Cancel
// (a Cancel that does not revert would be a lie). The panel is closed from its
// own chrome.
let saveTimer = null
watch([name, currentLocation, transversalType], () => {
  clearTimeout(saveTimer)
  saveTimer = setTimeout(save, 600)
})

async function save() {
  saveTimer = null
  saving.value = true
  try {
    await updateProjection(props.projection.id, {
      name: name.value,
      // '' asks the service to clear (it reads null as "leave unchanged"), but
      // the GraphQL resolver folds '' back to None, so clearing still no-ops —
      // verified live and flagged to backend-platform. Sent as '' so the panel
      // is already correct once that is fixed.
      currentLocation: currentLocation.value || '',
      transversalType: transversalType.value,
    })
  } finally {
    saving.value = false
  }
}

// Closing the panel before the debounce fires must not lose the edit.
onUnmounted(() => { if (saveTimer) { clearTimeout(saveTimer); save() } })
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
.save-status { color: var(--accent); }
</style>
