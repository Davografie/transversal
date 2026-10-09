<template>
  <div class="rtg-root">
    <GmList
      :items="groupTables"
      item-key="id"
      empty-text="No roll tables in this group."
      @click="openTable"
    >
      <template #item="{ item: t }">
        <span class="entity-name">{{ t.name }}</span>
        <span class="entity-universe">{{ t.scheme }}</span>
        <span class="entity-id">{{ t.id }}</span>
      </template>
    </GmList>
    <Button class="rtg-add-btn" variant="secondary" block @click="addTable">＋ Add roll table</Button>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted } from 'vue'
import { useRollTables } from '@/composables/useRollTables.js'
import { usePanel } from '@/composables/usePanel.js'
import { usePanelBus } from '@/composables/usePanelBus.js'
import GmList from '@/components/ui/GmList.vue'
import Button from '@/components/ui/Button.vue'
import GmRollTableEditPanel from './GmRollTableEditPanel.vue'

const panel = usePanel()
const bus = usePanelBus()
const { allTables, fetchAllTables } = useRollTables()

const props = defineProps({
  kind: { type: String, required: true },   // 'fundamental' | 'shared'
  universe: { type: String, default: '' },
})

const groupTables = computed(() => {
  if (props.kind === 'fundamental') {
    return allTables.value.filter(t => !t.universe && !t.lifePath)
  }
  return allTables.value.filter(t => t.universe === props.universe && !t.lifePath)
})

let offLifepathSaved = null
onMounted(() => {
  fetchAllTables()
  offLifepathSaved = bus.on('lifepath-saved', fetchAllTables)
})
onUnmounted(() => { if (offLifepathSaved) offLifepathSaved() })

function openTable(t) {
  panel.open({ component: GmRollTableEditPanel, title: t.name, id: t.id, badge: 'ROLL-TABLE', props: { tableId: t.id } })
}

function addTable() {
  const universe = props.kind === 'fundamental' ? '' : props.universe
  panel.open({
    component: GmRollTableEditPanel,
    title: props.kind === 'fundamental' ? 'New Fundamental Table' : 'New Roll Table',
    badge: 'ROLL-TABLE',
    props: { tableId: '', universe, lifePathId: '' },
  })
}
</script>

<style scoped>
.rtg-root { padding: 0; }
.rtg-add-btn { margin-top: 8px; }
</style>
