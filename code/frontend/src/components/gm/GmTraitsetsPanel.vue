<template>
  <div>
    <input v-model="search" class="filter-input" placeholder="Search…" style="margin-bottom:8px" />
    <div v-if="loading" class="loading">Loading…</div>
    <div v-else class="ps-list">
      <div v-for="ts in filtered" :key="ts.id" class="entity-row"
        :class="{ selected: selectedId === ts.id }"
        @click="$emit('select', ts)">
        <span class="entity-name">{{ ts.name }}</span>
        <span style="font-size:10px;color:var(--text-dim)">{{ traitCount(ts.id) }}</span>
      </div>
      <div v-if="filtered.length === 0" class="empty">No traitsets found</div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'

const props = defineProps({
  traitsets: { type: Array, default: () => [] },
  allTraits: { type: Array, default: () => [] },
  allSfxs: { type: Array, default: () => [] },
  selectedId: { type: String, default: '' },
  loading: { type: Boolean, default: false },
})

const emit = defineEmits(['select', 'close'])
const search = ref('')

const filtered = computed(() => {
  const q = search.value.toLowerCase()
  if (!q) return props.traitsets
  return props.traitsets.filter(ts =>
    ts.name.toLowerCase().includes(q) ||
    props.allTraits.some(t => t.traitsetId === ts.id && t.name.toLowerCase().includes(q)) ||
    props.allSfxs.some(s => s.name.toLowerCase().includes(q))
  )
})

function traitCount(tsId) {
  return props.allTraits.filter(t => t.traitsetId === tsId).length
}
</script>

<style scoped>
.ps-list { display: flex; flex-direction: column; gap: 3px; }
.entity-row { display: flex; align-items: center; gap: 6px; padding: 8px 10px; border-radius: 6px; cursor: pointer; background: rgba(255,255,255,0.03); transition: background 0.15s; font-size: 13px; }
.entity-row:hover { background: rgba(255,255,255,0.06); }
.entity-row.selected { background: rgba(64,136,212,0.15); border: 1px solid var(--accent-dim); }
.entity-name { flex: 1; font-weight: 500; }
.loading, .empty { font-size: 12px; color: var(--text-dim); padding: 12px 0; text-align: center; }
</style>
