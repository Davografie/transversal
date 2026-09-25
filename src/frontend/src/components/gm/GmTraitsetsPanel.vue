<template>
  <div>
    <Button class="ps-add-btn batch-btn" @click="openBatchEdit" variant="secondary" block>Batch Edit Traits</Button>
    <input v-model="search" class="filter-input" placeholder="Search…" style="margin-bottom:8px" />
    <!-- Reordering is only offered unfiltered: the mutation writes `order = i + 1`
         for the ids it is given, so dragging a filtered subset would renumber
         those few on top of the unfiltered list's orders and collide with them.
         A filtered subset has no position in the global order to write. -->
    <GmList
      :items="filtered"
      item-key="id"
      :selected-ids="selectedId ? [selectedId] : []"
      :reorderable="!search"
      :loading="loading"
      empty-text="No traitsets found"
      :row-class="(ts) => (ts._flash ? 'patch-flash' : '')"
      @click="onClick"
      @reorder="onReorder"
    >
      <template #item="{ item: ts }">
        <span class="entity-name">{{ ts.name }}</span>
        <span style="font-size:10px;color:var(--text-dim)">{{ (ts.traits?.length) || 0 }}</span>
        <span v-if="!search" class="drag-handle">⠿</span>
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
import Button from '@/components/ui/Button.vue'

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
    badge: 'TRAITSET',
    props: { traitsetId: ts.id },
    // The search box scopes both lists — the sets that match, and the traits
    // inside the set you open. Hand the live *ref* across in the spec's context:
    // a child panel cannot inject this panel's provide (see PanelScope), and a
    // copied value would go stale the moment the query is edited while the
    // detail is open, which it is, since the two panels sit side by side.
    context: { traitsetFilter: search },
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
