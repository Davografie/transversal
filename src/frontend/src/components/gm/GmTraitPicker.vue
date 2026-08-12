<template>
  <div class="gtp-root">
    <div class="gtp-wrap">
      <select v-if="tsOptions.length > 1" v-model="filterTs" class="gtp-filter">
        <option value="">All trait sets</option>
        <option v-for="ts in tsOptions" :key="ts.id" :value="ts.id">{{ ts.name }}</option>
      </select>
      <div class="gtp-input-wrap">
        <input
          v-model="search"
          :placeholder="selectedLabel || placeholder"
          @focus="open = true"
          @blur="close"
          @input="open = true"
          class="gtp-input"
        />
        <button v-if="selectedLabel" class="gtp-clear" title="Clear selection" @mousedown.prevent="clear">×</button>
        <div v-if="open" class="gtp-drop">
        <div v-if="!filtered.length" class="gtp-empty">No matches</div>
        <div
          v-for="opt in filtered"
          :key="opt.id"
          class="gtp-item"
          @mousedown.prevent="pick(opt)"
        >
          <span class="gtp-trait-name">{{ opt.name }}</span>
          <span class="gtp-ts-name">{{ opt.tsName }}</span>
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
  placeholder: { type: String, default: 'Search trait…' },
})

const emit = defineEmits(['update:modelValue'])
const { graphql } = useApi()

const traits = ref([])            // { id, name, traitsetId }
const traitSetMap = ref({})       // id → name
const filterTs = ref('')
const search = ref('')
const open = ref(false)

onMounted(async () => {
  if (!props.universe) return
  try {
    const [tData, tsData] = await Promise.all([
      graphql(`query($u: String!) { traitsByUniverse(universe: $u) { id name traitsetId } }`, { u: props.universe }),
      graphql(`query($u: String!) { traitsetsByUniverse(universe: $u) { id name } }`, { u: props.universe }),
    ])
    if (tData?.traitsByUniverse) traits.value = tData.traitsByUniverse
    if (tsData?.traitsetsByUniverse) {
      tsData.traitsetsByUniverse.forEach(ts => { traitSetMap.value[ts.id] = ts.name })
    }
  } catch {}
})

const tsOptions = computed(() => {
  const seen = new Set()
  const opts = []
  for (const t of traits.value) {
    if (!t.traitsetId || seen.has(t.traitsetId)) continue
    seen.add(t.traitsetId)
    opts.push({ id: t.traitsetId, name: traitSetMap.value[t.traitsetId] || t.traitsetId })
  }
  opts.sort((a, b) => a.name.localeCompare(b.name))
  return opts
})

const selectedTrait = computed(() => {
  if (props.modelValue) return traits.value.find(t => t.id === props.modelValue)
  return null
})

const selectedLabel = computed(() => {
  const t = selectedTrait.value
  if (!t) return ''
  const tsName = traitSetMap.value[t.traitsetId]
  return tsName ? `${t.name} (${tsName})` : t.name
})

const filtered = computed(() => {
  const s = search.value.toLowerCase()
  const tsFilter = filterTs.value
  return traits.value
    .filter(t => {
      if (t.id === props.modelValue) return false
      if (tsFilter && t.traitsetId !== tsFilter) return false
      if (s && !t.name.toLowerCase().includes(s)) return false
      return true
    })
    .map(t => ({
      id: t.id,
      name: t.name,
      tsName: traitSetMap.value[t.traitsetId] || '',
    }))
    .slice(0, 20)
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
</script>

<style scoped>
.gtp-root { display: inline-block; width: 100%; }
.gtp-wrap { display: flex; flex-direction: column; width: 100%; }
.gtp-input-wrap { position: relative; }
.gtp-filter {
  width: 100%; font-size: 9px; padding: 2px 4px; margin-bottom: 2px; border-radius: 3px;
  border: 1px solid rgba(255,255,255,0.08); background: rgba(255,255,255,0.04); color: var(--text-dim);
  box-sizing: border-box;
}
.gtp-input {
  width: 100%; font-size: 11px; padding: 4px 20px 4px 6px; border-radius: 3px;
  border: 1px solid rgba(255,255,255,0.1); background: rgba(255,255,255,0.04); color: var(--text);
  box-sizing: border-box;
}
.gtp-input::placeholder { color: var(--text-dim); }
.gtp-clear {
  position: absolute; right: 4px; top: 4px; font-size: 12px; line-height: 1;
  padding: 0 2px; cursor: pointer; background: none; border: none; color: var(--text-dim);
}
.gtp-clear:hover { color: #e06060; }
.gtp-drop {
  position: absolute; top: 100%; left: 0; right: 0; z-index: 10;
  max-height: 140px; overflow-y: auto;
  background: #1a1a2e; border: 1px solid rgba(255,255,255,0.1); border-radius: 3px;
}
.gtp-item {
  display: flex; justify-content: space-between; align-items: center;
  font-size: 10px; padding: 4px 8px; cursor: pointer; color: var(--text);
}
.gtp-item:hover { background: rgba(0,200,150,0.1); color: var(--accent); }
.gtp-trait-name { flex: 1; }
.gtp-ts-name { font-size: 8px; color: var(--text-dim); margin-left: 8px; white-space: nowrap; }
.gtp-empty { font-size: 10px; padding: 6px 8px; color: var(--text-dim); }
</style>
