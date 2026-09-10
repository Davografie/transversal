<template>
  <div>
    <label>Name</label>
    <input v-model="form.name" autofocus />

    <label>Type</label>
    <select v-model="form.type">
      <option v-for="t in ENTITY_TYPES" :key="t" :value="t">{{ t }}</option>
    </select>

    <label>Location</label>
    <select v-model="form.location" :disabled="form.type === 'UNIVERSE'">
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
    <div class="raz-dots" role="radiogroup" aria-label="Starting razmerit">
      <button
        v-for="n in 5"
        :key="n"
        type="button"
        class="raz-dot"
        :class="{ filled: form.razmerit >= n }"
        role="radio"
        :aria-checked="form.razmerit === n"
        :aria-label="`${n} razmerit`"
        @click="setRazmerit(n)"
      ></button>
    </div>

    <Button class="save-btn" block @click="onSubmit" :disabled="saving || !form.name.trim()" variant="success" solid>
      {{ saving ? 'Creating…' : 'Create' }}
    </Button>
  </div>
</template>

<script setup>
import { reactive, computed, watch } from 'vue'
import { ENTITY_TYPES } from '@/constants/entityTypes.js'
import Button from '@/components/ui/Button.vue'

const props = defineProps({
  defaultUniverse: { type: String, default: 'earth' },
  defaultLocationId: { type: String, default: '' },
  locationTree: { type: Array, default: () => [] },
  saving: { type: Boolean, default: false },
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

// Universe entities have no location; clear and disable the picker.
watch(() => form.type, (t) => {
  if (t === 'UNIVERSE') form.location = ''
})

function setRazmerit(n) {
  form.razmerit = form.razmerit === n ? 0 : n
}

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
select:disabled { opacity: 0.45; cursor: not-allowed; }
.raz-dots { display: flex; gap: 10px; margin-top: 6px; }
.raz-dot {
  width: 40px; height: 40px; border-radius: 50%;
  padding: 0; cursor: pointer;
  background: var(--overlay-6);
  border: 2px solid var(--overlay-25);
  transition: background 0.15s, border-color 0.15s, transform 0.1s;
}
.raz-dot.filled {
  background: var(--accent, var(--resonance));
  border-color: var(--accent, var(--resonance));
}
.raz-dot:active { transform: scale(0.92); }
optgroup { font-weight: 600; color: var(--text); }
.save-btn { margin-top: 8px; }
</style>
