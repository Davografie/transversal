<template>
  <div class="grtp-root">
    <div class="grtp-wrap">
      <div class="grtp-filters">
        <select v-if="universeOptions.length > 1" v-model="filterUniverse" class="grtp-filter">
          <option value="">All universes</option>
          <option v-for="u in universeOptions" :key="u" :value="u">{{ u }}</option>
        </select>
        <select v-if="factionOptions.length > 1" v-model="filterFaction" class="grtp-filter">
          <option value="">All factions</option>
          <option v-for="f in factionOptions" :key="f.id" :value="f.id">{{ f.name }}</option>
        </select>
        <select v-if="lifePathOptions.length > 1" v-model="filterLifePath" class="grtp-filter">
          <option value="">All life paths</option>
          <option v-for="lp in lifePathOptions" :key="lp.id" :value="lp.id">{{ lp.name }}</option>
        </select>
      </div>
      <div class="grtp-input-wrap">
        <input
          v-model="search"
          :placeholder="selectedLabel || placeholder"
          @focus="open = true"
          @blur="close"
          @input="open = true"
          class="grtp-input"
        />
        <button v-if="selectedLabel" class="grtp-clear" title="Clear selection" @mousedown.prevent="clear">×</button>
        <div v-if="open" class="grtp-drop">
          <div v-if="!filtered.length" class="grtp-empty">No matches</div>
          <div
            v-for="opt in filtered"
            :key="opt.id"
            class="grtp-item"
            @mousedown.prevent="pick(opt)"
          >
            <span class="grtp-name">{{ opt.name }}</span>
            <span class="grtp-sub">{{ subLabel(opt) }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { useApi } from '@/composables/useApi.js'

const props = defineProps({
  modelValue: { type: String, default: '' },
  universe: { type: String, default: '' },
  faction: { type: String, default: '' },
  lifePath: { type: String, default: '' },
  placeholder: { type: String, default: 'Search roll table…' },
  excludeIds: { type: Array, default: () => [] },
})

const emit = defineEmits(['update:modelValue'])
const { graphql } = useApi()

const tables = ref([])      // { id, name, universe, lifePath }
const lifePaths = ref([])   // { id, name, universe, factionIds }
const factions = ref([])    // { id, name }

const filterUniverse = ref(props.universe)
const filterFaction = ref(props.faction)
const filterLifePath = ref(props.lifePath)
const search = ref('')
const open = ref(false)

onMounted(async () => {
  try {
    const [t, lp, fac] = await Promise.all([
      graphql(`{ rollTables { id name universe lifePath } }`),
      graphql(`{ lifePaths { id name universe factionIds } }`),
      graphql(`query($type: EntityType){ entities(type: $type){ id name } }`, { type: 'FACTION' }),
    ])
    tables.value = t?.rollTables || []
    lifePaths.value = lp?.lifePaths || []
    factions.value = fac?.entities || []
    // Auto-preselect faction when the life path maps to exactly one faction.
    if (!filterFaction.value && filterLifePath.value) {
      const lp = lifePaths.value.find(x => x.id === filterLifePath.value)
      if (lp && (lp.factionIds || []).length === 1) filterFaction.value = lp.factionIds[0]
    }
  } catch { /* leave empty */ }
})

// Life paths that actually own at least one roll table.
const pathIdsWithTables = computed(() => new Set(tables.value.map(t => t.lifePath).filter(Boolean)))

const universeOptions = computed(() => {
  const s = new Set()
  for (const t of tables.value) if (t.universe) s.add(t.universe)
  return [...s].sort()
})

const lifePathOptions = computed(() =>
  lifePaths.value
    .filter(lp => pathIdsWithTables.value.has(lp.id))
    .filter(lp => !filterUniverse.value || lp.universe === filterUniverse.value)
    .slice()
    .sort((a, b) => a.name.localeCompare(b.name))
)

const factionOptions = computed(() => {
  const relevant = new Set()
  for (const lp of lifePathOptions.value) {
    for (const fid of (lp.factionIds || [])) relevant.add(fid)
  }
  return factions.value
    .filter(f => relevant.has(f.id))
    .slice()
    .sort((a, b) => a.name.localeCompare(b.name))
})

function lifePathName(id) {
  if (!id) return ''
  return lifePaths.value.find(lp => lp.id === id)?.name || ''
}

const selectedTable = computed(() => {
  if (!props.modelValue) return null
  return tables.value.find(t => t.id === props.modelValue) || null
})

const selectedLabel = computed(() => {
  const t = selectedTable.value
  if (!t) return ''
  const sub = lifePathName(t.lifePath) || t.universe
  return sub ? `${t.name} (${sub})` : t.name
})

function subLabel(t) {
  return lifePathName(t.lifePath) || t.universe || ''
}

const filtered = computed(() => {
  const s = search.value.toLowerCase()
  const uFilter = filterUniverse.value
  const lpFilter = filterLifePath.value
  const facFilter = filterFaction.value

  // faction → set of life path ids it offers
  const facPathIds = new Set()
  if (facFilter) {
    for (const lp of lifePaths.value) {
      if ((lp.factionIds || []).includes(facFilter)) facPathIds.add(lp.id)
    }
  }

  return tables.value
    .filter(t => {
      if (t.id === props.modelValue) return false
      if (props.excludeIds.includes(t.id)) return false
      if (uFilter && t.universe !== uFilter) return false
      if (lpFilter && t.lifePath !== lpFilter) return false
      if (facFilter && !facPathIds.has(t.lifePath)) return false
      if (s && !(t.name || '').toLowerCase().includes(s)) return false
      return true
    })
})

function pick(opt) {
  emit('update:modelValue', opt.id)
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

watch(() => props.modelValue, () => { search.value = '' })
watch(() => props.universe, (u) => { filterUniverse.value = u })
watch(() => props.faction, (f) => { filterFaction.value = f })
watch(() => props.lifePath, (lp) => { filterLifePath.value = lp })
watch(filterUniverse, () => {
  // Drop dependent filters when their option is no longer offered.
  if (filterLifePath.value && !lifePathOptions.value.some(lp => lp.id === filterLifePath.value)) filterLifePath.value = ''
  if (filterFaction.value && !factionOptions.value.some(f => f.id === filterFaction.value)) filterFaction.value = ''
})
</script>

<style scoped>
.grtp-root { display: inline-block; width: 100%; }
.grtp-wrap { display: flex; flex-direction: column; width: 100%; }
.grtp-filters { display: flex; flex-direction: column; gap: 2px; margin-bottom: 2px; }
.grtp-input-wrap { position: relative; }
.grtp-filter {
  width: 100%; font-size: 9px; padding: 2px 4px; border-radius: 3px;
  border: 1px solid rgba(255,255,255,0.08); background: rgba(255,255,255,0.04); color: var(--text-dim);
  box-sizing: border-box;
}
.grtp-input {
  width: 100%; font-size: 11px; padding: 4px 20px 4px 6px; border-radius: 3px;
  border: 1px solid rgba(255,255,255,0.1); background: rgba(255,255,255,0.04); color: var(--text);
  box-sizing: border-box;
}
.grtp-input::placeholder { color: var(--text-dim); }
.grtp-clear {
  position: absolute; right: 4px; top: 4px; font-size: 12px; line-height: 1;
  padding: 0 2px; cursor: pointer; background: none; border: none; color: var(--text-dim);
}
.grtp-clear:hover { color: #e06060; }
.grtp-drop {
  position: absolute; top: 100%; left: 0; right: 0; z-index: 10;
  max-height: 180px; overflow-y: auto;
  background: #1a1a2e; border: 1px solid rgba(255,255,255,0.1); border-radius: 3px;
}
.grtp-item {
  display: flex; justify-content: space-between; align-items: center;
  font-size: 10px; padding: 4px 8px; cursor: pointer; color: var(--text);
}
.grtp-item:hover { background: rgba(0,200,150,0.1); color: var(--accent); }
.grtp-name { flex: 1; }
.grtp-sub { font-size: 8px; color: var(--text-dim); margin-left: 8px; white-space: nowrap; }
.grtp-empty { font-size: 10px; padding: 6px 8px; color: var(--text-dim); }
</style>
