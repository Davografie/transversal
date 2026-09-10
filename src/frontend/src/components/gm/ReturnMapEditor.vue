<template>
  <div class="rme-root">
    <div v-if="loadingExits" class="rme-hint">Loading exits…</div>
    <div v-else-if="!exits.length" class="rme-hint">No named exits in this table.</div>
    <div v-else class="rme-list">
      <div v-for="name in exits" :key="name" class="rme-row">
        <label class="rme-label">{{ name }}</label>
        <TargetPicker
          :model-value="map[name] || ''"
          @update:model-value="setExit(name, $event)"
          kind="roll_table"
          :scope="universe ? `universe:${universe}` : ''"
        />
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { useApi } from '@/composables/useApi.js'
import TargetPicker from '@/components/ui/TargetPicker.vue'

// Editor for a next_step "return map": a shared roll table declares named
// exits (entries whose next_step target is "{return:<name>}"), and the caller
// maps each exit to a per-path table id.
const props = defineProps({
  modelValue: { type: Object, default: () => ({}) },
  target: { type: String, default: '' },      // the shared table id
  universe: { type: String, default: '' },
})

const emit = defineEmits(['update:modelValue'])
const { graphql } = useApi()

const exits = ref([])
const loadingExits = ref(false)

const map = computed(() => props.modelValue || {})

async function loadExits() {
  exits.value = []
  if (!props.target || props.target.startsWith('{')) return
  loadingExits.value = true
  try {
    const data = await graphql(
      `query($id:ID!){ rollTable(id:$id){ entries{ effects{ action target } } } }`,
      { id: props.target },
    )
    const names = new Set()
    for (const e of data?.rollTable?.entries || []) {
      for (const eff of (e.effects || [])) {
        if (eff.action === 'next_step' && eff.target?.startsWith('{return:') && eff.target.endsWith('}')) {
          names.add(eff.target.slice('{return:'.length, -1))
        }
      }
    }
    exits.value = [...names]
  } finally {
    loadingExits.value = false
  }
}

function setExit(name, tableId) {
  const next = { ...map.value }
  if (tableId) next[name] = tableId
  else delete next[name]
  emit('update:modelValue', next)
}

onMounted(loadExits)
watch(() => props.target, loadExits)
</script>

<style scoped>
.rme-root { display: flex; flex-direction: column; gap: 4px; }
.rme-hint { font-size: 9px; color: var(--text-dim); font-style: italic; }
.rme-list { display: flex; flex-direction: column; gap: 4px; }
.rme-row { display: flex; flex-direction: column; gap: 2px; }
.rme-label { font-size: 9px; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.5px; }
</style>
