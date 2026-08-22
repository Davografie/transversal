<template>
  <div class="lpl-root">
    <p class="lpl-hint">Life paths available in this universe. Click one for full details.</p>
    <GmList
      :items="paths"
      item-key="id"
      empty-text="No life paths seeded."
      @click="openDetail"
    >
      <template #item="{ item: lp }">
        <span class="entity-name">{{ lp.name }}</span>
      </template>
    </GmList>
    <button class="lpl-add-btn" @click="addNew">＋ Add life path</button>
  </div>
</template>

<script setup>
import { onMounted, onUnmounted } from 'vue'
import { useLifePaths } from '@/composables/useLifePaths.js'
import { usePanel } from '@/composables/usePanel.js'
import { usePanelBus } from '@/composables/usePanelBus.js'
import GmList from './GmList.vue'
import GmLifePathDetailPanel from './GmLifePathDetailPanel.vue'
import GmLifePathEditPanel from './GmLifePathEditPanel.vue'

const panel = usePanel()
const bus = usePanelBus()

const props = defineProps({
  universe: { type: String, default: '' },
})

const { paths, fetchLifePaths } = useLifePaths()

let offLifepathSaved = null
onMounted(() => {
  fetchLifePaths(props.universe)
  offLifepathSaved = bus.on('lifepath-saved', (payload) => {
    // Newly created paths are already in the shared list — just auto-open.
    if (payload?.isNew) {
      const lp = paths.value.find(p => p.id === payload.id)
      if (lp) openDetail(lp)
    }
  })
})
onUnmounted(() => { if (offLifepathSaved) offLifepathSaved() })

function openDetail(lp) {
  panel.open({
    component: GmLifePathDetailPanel,
    title: lp.name,
    props: { lp },
  })
}

function addNew() {
  const blank = { id: '', name: '', description: '', universe: props.universe, entryTableId: '' }
  panel.open({
    component: GmLifePathEditPanel,
    title: 'New Life Path',
    props: { lp: blank },
  })
}
</script>

<style scoped>
.lpl-root { padding: 0; }
.lpl-hint { font-size: 10px; color: var(--text-dim); margin: 0 0 8px 0; }
.lpl-add-btn {
  width: 100%; margin-top: 8px; font-size: 11px; padding: 6px 0;
  background: rgba(0,200,150,0.08); border: 1px dashed rgba(0,200,150,0.25);
  border-radius: 4px; color: var(--accent); cursor: pointer;
}
.lpl-add-btn:hover { background: rgba(0,200,150,0.14); }
</style>
