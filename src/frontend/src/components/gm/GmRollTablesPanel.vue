<template>
  <div class="rtp-root">
    <p class="rtp-hint">Roll tables grouped by scope. Click a group to see its tables.</p>

    <Button class="rtp-group" variant="neutral" block @click="openFundamental">
      <span class="entity-name">Fundamental</span>
      <span class="entity-universe">{{ fundamentalCount }} tables · all universes</span>
    </Button>

    <Button class="rtp-group" variant="neutral" block @click="openShared">
      <span class="entity-name">Shared</span>
      <span class="entity-universe">{{ sharedCount }} tables · this universe</span>
    </Button>

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
      <Button class="rtp-add-btn" variant="secondary" block @click="addNew">＋ Add life path</Button>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted } from 'vue'
import { useLifePaths } from '@/composables/useLifePaths.js'
import { useRollTables } from '@/composables/useRollTables.js'
import { usePanel } from '@/composables/usePanel.js'
import { usePanelBus } from '@/composables/usePanelBus.js'
import GmList from '@/components/ui/GmList.vue'
import Button from '@/components/ui/Button.vue'
import GmLifePathDetailPanel from './GmLifePathDetailPanel.vue'
import GmRollTableGroupPanel from './GmRollTableGroupPanel.vue'

const panel = usePanel()
const bus = usePanelBus()
const { pathsFor, fetchLifePaths } = useLifePaths()
const { allTables, fetchAllTables } = useRollTables()

const props = defineProps({
  universe: { type: String, default: '' },
})

// This panel's universe, from the per-universe store.
const paths = pathsFor(props.universe)

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
  panel.open({ component: GmLifePathDetailPanel, title: lp.name, id: lp.id, badge: 'LIFE-PATH', props: { lp } })
}

function addNew() {
  // The detail panel *is* the editor now, so creating opens it with a blank
  // path: an empty id makes `saveLifePath` generate one.
  const blank = { id: '', name: '', description: '', universe: props.universe, entryTableId: '' }
  panel.open({ component: GmLifePathDetailPanel, title: 'New Life Path', badge: 'LIFE-PATH', props: { lp: blank } })
}
</script>

<style scoped>
.rtp-root { padding: 0; }
.rtp-hint { font-size: 10px; color: var(--text-dim); margin: 0 0 8px 0; }
/* Layout hooks only — the primitive supplies fill/border/typography. */
.rtp-group { margin-bottom: 4px; text-align: left; }
/* The row label is the primitive's own wrapper: make it span the button so
   `.entity-name`'s flex:1 still flushes the meta text to the right. */
.rtp-group :deep(.btn-label) {
  display: flex; align-items: center; gap: 8px; width: 100%;
}
.rtp-section { margin-top: 12px; }
.rtp-subtitle { display: block; font-size: 9px; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 4px; }
.rtp-add-btn { margin-top: 8px; }
</style>
