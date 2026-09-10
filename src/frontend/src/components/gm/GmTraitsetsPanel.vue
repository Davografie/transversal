<template>
  <div>
    <button class="ps-add-btn batch-btn" @click="openBatchEdit">Batch Edit Traits</button>
    <input v-model="search" class="filter-input" placeholder="Search…" style="margin-bottom:8px" />
    <GmList
      :items="filtered"
      item-key="id"
      :selected-ids="selectedId ? [selectedId] : []"
      reorderable
      :loading="loading"
      empty-text="No traitsets found"
      :row-class="(ts) => (ts._flash ? 'patch-flash' : '')"
      @click="onClick"
      @reorder="onReorder"
    >
      <template #item="{ item: ts }">
        <span class="entity-name">{{ ts.name }}</span>
        <span style="font-size:10px;color:var(--text-dim)">{{ (ts.traits?.length) || 0 }}</span>
        <span class="drag-handle">⠿</span>
      </template>
    </GmList>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useApi } from '@/composables/useApi.js'
import { useTraitsConfig } from '@/composables/useTraitsConfig.js'
import { usePanel } from '@/composables/usePanel.js'
import GmList from '@/components/ui/GmList.vue'
import GmTraitsetDetail from '@/components/gm/GmTraitsetDetail.vue'
import GmTraitBatchEditPanel from '@/components/gm/GmTraitBatchEditPanel.vue'

const { graphql } = useApi()
const panel = usePanel()
const { traitsets, allSfxs, loading, fetchTraitsConfig } = useTraitsConfig()

const props = defineProps({
  selectedId: { type: String, default: '' },
})

const search = ref('')

// Temporary local ordering applied during a drag-reorder, until the server
// confirms the new order and we re-fetch.
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
  panel.open({
    component: GmTraitsetDetail,
    title: ts.name,
    id: ts.id,
    props: { traitsetId: ts.id },
  })
}

function onReorder(from, to) {
  const list = [...filtered.value]
  const [moved] = list.splice(from, 1)
  list.splice(to, 0, moved)
  localOrder = list
  const ids = list.map(ts => ts.id)
  graphql(`mutation($ids: [ID!]!) { reorderTraitsets(ids: $ids) }`, { ids }).then(() => {
    fetchTraitsConfig()
    localOrder = null
  })
}

function openBatchEdit() {
  panel.open({
    component: GmTraitBatchEditPanel,
    title: 'Batch Edit Traits',
    props: {},
  })
}
</script>

<style scoped>
.batch-btn { margin-top: 0; margin-bottom: 8px; }
.drag-handle { font-size: 12px; color: var(--text-dim); cursor: grab; opacity: 0.4; transition: opacity 0.15s; padding: 0 2px; margin-left: auto; }
.entity-row:hover .drag-handle { opacity: 0.7; }
</style>
