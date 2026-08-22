<template>
  <div class="glp-root">
    <div class="glp-wrap">
      <div class="glp-filters">
        <select v-if="universeOptions.length > 1" v-model="filterUniverse" class="glp-filter">
          <option value="">All universes</option>
          <option v-for="u in universeOptions" :key="u" :value="u">{{ u }}</option>
        </select>
      </div>
      <div class="glp-input-wrap">
        <input
          v-model="search"
          :placeholder="selectedLabel || placeholder"
          @focus="open = true"
          @blur="close"
          @input="open = true"
          class="glp-input"
        />
        <button v-if="selectedLabel" class="glp-clear" title="Clear" @mousedown.prevent="clear">×</button>
        <div v-if="open" class="glp-drop">
          <div v-if="!filtered.length" class="glp-empty">No locations</div>
          <div v-for="loc in filtered" :key="loc.id" class="glp-item" @mousedown.prevent="pick(loc)">
            <span class="glp-loc-name">{{ loc.name }}</span>
            <span class="glp-loc-universe">{{ loc.universe }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useLocationTree } from '@/composables/useLocationTree.js'

const props = defineProps({
  modelValue: { type: String, default: '' },
  placeholder: { type: String, default: 'Search location…' },
  universe: { type: String, default: '' },
  rootId: { type: String, default: '' },
})

const emit = defineEmits(['update:modelValue', 'select'])
const { locationTree, fetchLocationTree } = useLocationTree({})

const filterUniverse = ref(props.universe || '')
const search = ref('')
const open = ref(false)

onMounted(async () => {
  if (!locationTree.value.length) await fetchLocationTree()
})

function flattenLocations(nodes, universe, out) {
  for (const n of (nodes || [])) {
    const u = n.universe || universe || ''
    if (n.node_type === 'location' || n.kind === 'location') {
      out.push({ id: n.id, name: n.name, universe: u })
    }
    if (n.children) flattenLocations(n.children, u, out)
  }
}

const allLocations = computed(() => {
  const out = []
  flattenLocations(locationTree.value, '', out)
  return out
})

function collectSubtree(node, out) {
  out.push(node.id)
  if (node.children) for (const c of node.children) collectSubtree(c, out)
}

// When rootId is set, restrict to that location plus its sub-locations (zones).
const subtreeIds = computed(() => {
  if (!props.rootId) return null
  let found = null
  const find = (nodes) => {
    for (const n of (nodes || [])) {
      if (n.id === props.rootId) { found = n; return }
      if (n.children) find(n.children)
    }
  }
  find(locationTree.value)
  if (!found) return new Set()
  const ids = []
  collectSubtree(found, ids)
  return new Set(ids)
})

const universeOptions = computed(() => {
  const s = new Set()
  for (const l of allLocations.value) if (l.universe) s.add(l.universe)
  return [...s].sort()
})

const selectedLocation = computed(() =>
  allLocations.value.find((l) => l.id === props.modelValue) || null
)
const selectedLabel = computed(() => selectedLocation.value?.name || '')

const filtered = computed(() => {
  const s = search.value.toLowerCase()
  const uFilter = filterUniverse.value
  const sub = subtreeIds.value
  return allLocations.value
    .filter((l) => {
      if (l.id === props.modelValue) return false
      if (sub && !sub.has(l.id)) return false
      if (uFilter && l.universe !== uFilter) return false
      if (s && !l.name.toLowerCase().includes(s)) return false
      return true
    })
})

function pick(loc) {
  emit('update:modelValue', loc.id)
  emit('select', loc)
  search.value = ''
  open.value = false
}

function clear() {
  emit('update:modelValue', '')
  search.value = ''
  open.value = false
}

function close() {
  setTimeout(() => { open.value = false }, 150)
}
</script>

<style scoped>
.glp-root { display: inline-block; width: 100%; }
.glp-wrap { display: flex; flex-direction: column; width: 100%; }
.glp-filters { display: flex; flex-direction: column; gap: 2px; margin-bottom: 2px; }
.glp-input-wrap { position: relative; }
.glp-filter {
  width: 100%; font-size: 9px; padding: 2px 4px; border-radius: 3px;
  border: 1px solid rgba(255,255,255,0.08); background: rgba(255,255,255,0.04); color: var(--text-dim);
  box-sizing: border-box;
}
.glp-input {
  width: 100%; font-size: 11px; padding: 4px 20px 4px 6px; border-radius: 3px;
  border: 1px solid rgba(255,255,255,0.1); background: rgba(255,255,255,0.04); color: var(--text);
  box-sizing: border-box;
}
.glp-input::placeholder { color: var(--text-dim); }
.glp-clear {
  position: absolute; right: 4px; top: 4px; font-size: 12px; line-height: 1;
  padding: 0 2px; cursor: pointer; background: none; border: none; color: var(--text-dim);
}
.glp-clear:hover { color: #e06060; }
.glp-drop {
  position: absolute; top: 100%; left: 0; right: 0; z-index: 10;
  max-height: 160px; overflow-y: auto;
  background: #1a1a2e; border: 1px solid rgba(255,255,255,0.1); border-radius: 3px;
}
.glp-item {
  display: flex; justify-content: space-between; align-items: center;
  font-size: 10px; padding: 4px 8px; cursor: pointer; color: var(--text);
}
.glp-item:hover { background: rgba(0,200,150,0.1); color: var(--accent); }
.glp-loc-name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.glp-loc-universe { font-size: 8px; color: var(--text-dim); margin-left: 8px; white-space: nowrap; }
.glp-empty { font-size: 10px; padding: 6px 8px; color: var(--text-dim); }
</style>
