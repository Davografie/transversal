<template>
  <div>
    <label>Name</label>
    <input v-model="form.name" autofocus />

    <label>Type</label>
    <select v-model="form.type">
      <option v-for="t in entityTypes" :key="t" :value="t">{{ t }}</option>
    </select>

    <label>Location</label>
    <select v-model="form.location">
      <option value="">-- None --</option>
      <optgroup v-for="uni in universeGroups" :key="uni.key" :label="uni.name">
        <option
          v-for="loc in uni.locations"
          :key="loc.id"
          :value="loc.id"
        >{{ ' '.repeat(loc.depth) + loc.name }}</option>
      </optgroup>
    </select>

    <label>Razmerit</label>
    <input v-model.number="form.razmerit" type="number" />

    <button class="save-btn" @click="onSubmit" :disabled="saving || !form.name.trim()">
      {{ saving ? 'Creating…' : 'Create' }}
    </button>
  </div>
</template>

<script setup>
import { reactive, computed } from 'vue'

const props = defineProps({
  defaultUniverse: { type: String, default: 'earth' },
  defaultLocationId: { type: String, default: '' },
  locationTree: { type: Array, default: () => [] },
  saving: { type: Boolean, default: false },
  entityTypes: { type: Array, default: () => ['CHARACTER', 'LOCATION', 'GMC', 'FACTION', 'ASSET'] },
})

const emit = defineEmits(['create'])

// Build a flat, depth-annotated list of locations per universe from the tree
const universeGroups = computed(() => {
  function walk(nodes, depth, out) {
    for (const n of nodes) {
      if (n.node_type === 'universe') {
        const group = { key: n.universe || n.id, name: n.name, locations: [] }
        walk(n.children || [], 0, group.locations)
        out.push(group)
      } else if (n.node_type === 'location' || n.kind === 'location') {
        out.push({ id: n.id, name: n.name, depth })
        walk(n.children || [], depth + 1, out)
      }
    }
  }
  const groups = []
  walk(props.locationTree, 0, groups)
  return groups
})

// Resolve universe from the chosen location (for non-location entity types)
function resolveUniverse(locationId) {
  for (const g of universeGroups.value) {
    for (const l of g.locations) {
      if (l.id === locationId) return g.key
    }
  }
  return props.defaultUniverse
}

const initForm = () => ({
  name: '',
  type: 'CHARACTER',
  location: props.defaultLocationId || '',
  razmerit: 0,
})
const form = reactive(initForm())

function onSubmit() {
  emit('create', {
    ...form,
    universe: resolveUniverse(form.location),
  })
  Object.assign(form, initForm())
}
</script>

<style scoped>
label { font-size: 11px; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.5px; display: block; margin-top: 8px; }
input, select { font-size: 13px; padding: 6px 10px; width: 100%; box-sizing: border-box; }
optgroup { font-weight: 600; color: var(--text); }
.save-btn { background: var(--success); color: #0a0a0f; font-weight: 600; margin-top: 8px; padding: 8px; border-radius: 6px; border: none; cursor: pointer; width: 100%; }
.save-btn:disabled { opacity: 0.5; cursor: default; }
</style>
