<template>
  <div class="rtp-root">
    <p class="rtp-hint">Roll tables grouped by scope. Click a group to see its tables.</p>

    <button class="rtp-group" @click="openFundamental">
      <span class="entity-name">Fundamental</span>
      <span class="entity-universe">{{ fundamentalCount }} tables · all universes</span>
    </button>

    <button class="rtp-group" @click="openShared">
      <span class="entity-name">Shared</span>
      <span class="entity-universe">{{ sharedCount }} tables · this universe</span>
    </button>

    <div class="rtp-section">
      <span class="rtp-subtitle">Life paths</span>
      <GmList
        :items="paths"
        item-key="id"
        empty-text="No life paths seeded."
        @click="openDetail"
      >
        <template #item="{ item: lp }">
          <span class="entity-name">{{ lp.name }}</span>
          <span class="entity-universe">{{ pathTableCount(lp.id) }} tables</span>
        </template>
      </GmList>
      <button class="rtp-add-btn" @click="addNew">＋ Add life path</button>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted } from 'vue'
import { useLifePaths } from '@/composables/useLifePaths.js'
import { useRollTables } from '@/composables/useRollTables.js'
import { usePanel } from '@/composables/usePanel.js'
import { usePanelBus } from '@/composables/usePanelBus.js'
import GmList from './GmList.vue'
import GmLifePathDetailPanel from './GmLifePathDetailPanel.vue'
import GmLifePathEditPanel from './GmLifePathEditPanel.vue'
import GmRollTableGroupPanel from './GmRollTableGroupPanel.vue'

const panel = usePanel()
const bus = usePanelBus()
const { paths, fetchLifePaths } = useLifePaths()
const { allTables, fetchAllTables } = useRollTables()

const props = defineProps({
  universe: { type: String, default: '' },
})

const fundamentalCount = computed(() =>
  allTables.value.filter(t => !t.universe && !t.lifePath).length,
)

const sharedCount = computed(() =>
  allTables.value.filter(t => t.universe === props.universe && !t.lifePath).length,
)

function pathTableCount(pathId) {
  return allTables.value.filter(t => t.lifePath === pathId).length
}

let offLifepathSaved = null
onMounted(() => {
  fetchLifePaths(props.universe)
  fetchAllTables()
  offLifepathSaved = bus.on('lifepath-saved', () => {
    fetchLifePaths(props.universe)
    fetchAllTables()
  })
})
onUnmounted(() => { if (offLifepathSaved) offLifepathSaved() })

function openFundamental() {
  panel.open({
    component: GmRollTableGroupPanel,
    title: 'Fundamental Tables',
    props: { kind: 'fundamental', universe: '' },
  })
}

function openShared() {
  panel.open({
    component: GmRollTableGroupPanel,
    title: 'Shared Tables',
    props: { kind: 'shared', universe: props.universe },
  })
}

function openDetail(lp) {
  panel.open({ component: GmLifePathDetailPanel, title: lp.name, props: { lp } })
}

function addNew() {
  const blank = { id: '', name: '', description: '', universe: props.universe, entryTableId: '' }
  panel.open({ component: GmLifePathEditPanel, title: 'New Life Path', props: { lp: blank } })
}
</script>

<style scoped>
.rtp-root { padding: 0; }
.rtp-hint { font-size: 10px; color: var(--text-dim); margin: 0 0 8px 0; }
.rtp-group {
  width: 100%; display: flex; align-items: center; gap: 8px;
  padding: 8px 10px; margin-bottom: 4px; border-radius: 6px; cursor: pointer;
  font-size: 13px; text-align: left; color: var(--text);
  background: var(--overlay-4); border: 1px solid transparent;
}
.rtp-group:hover { background: var(--overlay-8); }
.rtp-section { margin-top: 12px; }
.rtp-subtitle { display: block; font-size: 9px; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 4px; }
.rtp-add-btn {
  width: 100%; margin-top: 8px; font-size: 11px; padding: 6px 0;
  background: var(--resonance-8); border: 1px dashed var(--resonance-25);
  border-radius: 4px; color: var(--accent); cursor: pointer;
}
.rtp-add-btn:hover { background: var(--resonance-12); }
</style>
