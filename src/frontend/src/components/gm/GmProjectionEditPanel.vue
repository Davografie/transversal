<template>
  <div>
    <div class="ps-form">
      <label>Name</label>
      <input v-model="name" placeholder="Projection name (falls back to entity)" />

      <label>Universe</label>
      <!-- A filter over the location picker, not stored state of its own: it
           decides which universe's locations are offered. Picking a location
           there is what sends the body — its universe follows the location. -->
      <select v-model="universeFilter">
        <option v-for="u in universeChoices" :key="u.value" :value="u.value">{{ u.label }}</option>
      </select>

      <label>Current Location</label>
      <TargetPicker v-model="currentLocation" kind="location" :scope="universeFilter ? `universe:${universeFilter}` : ''" placeholder="Search location…" />

      <label>Type</label>
      <select v-model="transversalType">
        <option value="NATIVE">native</option>
        <option value="CONSCIOUSNESS">consciousness</option>
        <option value="INAPPOSITE">inapposite</option>
      </select>

      <div class="readonly-row">
        <span>Origin: {{ universeName(projection.originUniverse) }}</span>
        <span v-if="universe !== projection.originUniverse">Current universe: {{ universeName(universe) }}</span>
        <span v-if="saving" class="save-status">Saving…</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch, inject } from 'vue'
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
const { updateProjection, activateProjection } = inject('entityEditor', null) || useEntityCrud()

const name = ref(props.projection.name || '')
const currentLocation = ref(props.projection.currentLocation || '')
const transversalType = ref(props.projection.transversalType || 'NATIVE')
// The spec's `projection` is the object captured when the panel opened, so the
// panel keeps its own copy of the one field a send changes.
const universe = ref(props.projection.universe || '')
// Narrows the location picker to one universe. Starts on the body's own
// universe, so the field behaves as it always did until widened.
const universeFilter = ref(props.projection.universe || '')
const saving = ref(false)

// What this panel has already written. Panel.vue v-binds the spec's props, so
// `projection` is the object captured at open time and never follows a later
// patch — diffs must run against the panel's own last-known state, or every
// further edit would re-send the travel (and log a duplicate transversal).
const sent = {
  name: props.projection.name || '',
  transversalType: props.projection.transversalType || 'NATIVE',
  location: props.projection.currentLocation || '',
}

const { name: universeName, options: universeOptions, load: loadUniverseNames } = useUniverseNames()

// A body whose universe is missing from the list still needs a selected option.
const universeChoices = computed(() => {
  const list = universeOptions.value || []
  if (universeFilter.value && !list.some((o) => o.value === universeFilter.value)) {
    return [{ value: universeFilter.value, label: universeName(universeFilter.value) }, ...list]
  }
  return list
})

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
    const p = props.projection
    const next = currentLocation.value || ''
    const moved = !!next && next !== sent.location

    if (moved) {
      // A new location is travel, not a field edit: the body moves, its universe
      // follows the destination location, and the entity follows the body —
      // activateProjection does all three (a bare updateProjection location
      // would leave the body's universe pointing at the old one).
      const body = await activateProjection(p.id, next, p.entityId || null)
      sent.location = next
      if (body?.universe) {
        universe.value = body.universe
        universeFilter.value = body.universe
      }
    }

    const fields = {}
    if (name.value !== sent.name) fields.name = name.value
    if (transversalType.value !== sent.transversalType) fields.transversalType = transversalType.value
    // The location rides along unless the travel above just wrote it. Clearing
    // still no-ops server-side — '' asks the service to clear (it reads null as
    // "leave unchanged") but the GraphQL resolver folds '' back to None, verified
    // live and flagged to backend-platform — and is sent anyway so the panel is
    // already correct once that is fixed.
    if (!moved) fields.currentLocation = next

    if (Object.keys(fields).length) {
      await updateProjection(p.id, fields)
      Object.assign(sent, fields)
    }
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
