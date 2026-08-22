<template>
  <div>
    <button class="ps-add-btn batch-btn" @click="openBatchEdit">Batch Edit Traits</button>
    <input v-model="search" class="filter-input" placeholder="Search…" style="margin-bottom:8px" />
    <div v-if="loading.value" class="loading">Loading…</div>
    <div v-else class="ps-list">
      <div
        v-for="(ts, i) in filtered"
        :key="ts.id"
        class="entity-row"
        :class="{
          selected: selectedId === ts.id,
          'drag-over': dragOverIndex === i,
          dragging: dragIndex === i,
          'patch-flash': ts._flash,
        }"
        draggable="true"
        @click="onClick(ts)"
        @dragstart="onDragStart(i, $event)"
        @dragover.prevent="onDragOver(i)"
        @dragleave="onDragLeave"
        @drop="onDrop(i)"
        @dragend="onDragEnd"
      >
        <span class="drag-handle">⠿</span>
        <span class="entity-name">{{ ts.name }}</span>
        <span style="font-size:10px;color:var(--text-dim)">{{ (ts.traits?.length) || 0 }}</span>
      </div>
      <div v-if="filtered.length === 0" class="empty">No traitsets found</div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useApi } from '@/composables/useApi.js'
import { useTraitsConfig } from '@/composables/useTraitsConfig.js'
import { usePanel } from '@/composables/usePanel.js'
import GmTraitsetDetail from '@/components/gm/GmTraitsetDetail.vue'
import GmTraitBatchEditPanel from '@/components/gm/GmTraitBatchEditPanel.vue'

const { graphql } = useApi()
const panel = usePanel()
const { traitsets, allSfxs, loading, fetchTraitsConfig } = useTraitsConfig()

const props = defineProps({
  selectedId: { type: String, default: '' },
})

const search = ref('')

// ── Drag-and-drop reorder ────────────────────────────
const dragIndex = ref(-1)
const dragOverIndex = ref(-1)
let localOrder = null

const filtered = computed(() => {
  const q = search.value.toLowerCase()
  const list = localOrder || traitsets.value
  if (!q) return list
  return list.filter(ts =>
    ts.name.toLowerCase().includes(q) ||
    (ts.traits || []).some(t => t.name.toLowerCase().includes(q))
  )
})

function onClick(ts) {
  if (dragIndex.value >= 0) return
  panel.open({
    component: GmTraitsetDetail,
    title: ts.name,
    props: { traitsetId: ts.id },
  })
}

function openBatchEdit() {
  panel.open({
    component: GmTraitBatchEditPanel,
    title: 'Batch Edit Traits',
    props: {},
  })
}

function onDragStart(i, e) {
  dragIndex.value = i
  e.dataTransfer.effectAllowed = 'move'
  e.dataTransfer.setData('text/plain', '')
}
function onDragOver(i) { dragOverIndex.value = i }
function onDragLeave() { dragOverIndex.value = -1 }
function onDrop(i) {
  if (dragIndex.value < 0 || dragIndex.value === i) return
  const list = [...filtered.value]
  const [moved] = list.splice(dragIndex.value, 1)
  list.splice(i, 0, moved)
  localOrder = list
  const ids = list.map(ts => ts.id)
  graphql(`mutation($ids: [ID!]!) { reorderTraitsets(ids: $ids) }`, { ids }).then(() => {
    fetchTraitsConfig()
    localOrder = null
  })
  dragOverIndex.value = -1; dragIndex.value = -1
}
function onDragEnd() { dragIndex.value = -1; dragOverIndex.value = -1 }
</script>

<style scoped>
.ps-list { display: flex; flex-direction: column; gap: 3px; }
.batch-btn { margin-top: 0; margin-bottom: 8px; }
.entity-row { user-select: none; transition: background 0.15s, transform 0.15s, box-shadow 0.15s; }
.entity-row.dragging { opacity: 0.4; }
.entity-row.drag-over { background: rgba(64,136,212,0.12); box-shadow: 0 0 0 1px var(--accent-dim) inset; transform: scale(1.02); }
.drag-handle { font-size: 12px; color: var(--text-dim); cursor: grab; opacity: 0.4; transition: opacity 0.15s; padding: 0 2px; }
.entity-row:hover .drag-handle { opacity: 0.7; }
</style>
