<template>
  <div>
    <input v-model="search" class="filter-input" placeholder="Filter SFXs…" />

    <GmList
      :items="filtered"
      item-key="id"
      selectable
      :selected-ids="selectedIds"
      empty-text="No SFXs match"
      @toggle="onToggle"
    >
      <template #item="{ item: s }">
        <span class="entity-name">{{ s.name }}</span>
        <span class="entity-universe">{{ s.trigger || '' }}</span>
      </template>
    </GmList>

    <Button class="ps-add-btn" @click="onNewSfx" variant="secondary" block>+ New SFX</Button>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useTraitsConfig } from '@/composables/useTraitsConfig.js'
import { usePanel } from '@/composables/usePanel.js'
import GmList from '@/components/ui/GmList.vue'
import GmSfxEditPanel from '@/components/gm/GmSfxEditPanel.vue'
import Button from '@/components/ui/Button.vue'

const panel = usePanel()
const { allSfxs, fetchTraitsConfig, patchData } = useTraitsConfig()

const props = defineProps({
  selectedIds: { type: Array, default: () => [] },
})

const emit = defineEmits(['add-sfx', 'remove-sfx'])

const search = ref('')

const filtered = computed(() => {
  const q = search.value.toLowerCase()
  if (!q) return allSfxs.value
  return allSfxs.value.filter(s =>
    s.name.toLowerCase().includes(q) ||
    (s.trigger || '').toLowerCase().includes(q) ||
    (s.description || '').toLowerCase().includes(q)
  )
})

function toggleSfx(id) {
  if (props.selectedIds.includes(id)) {
    emit('remove-sfx', id)
  } else {
    emit('add-sfx', id)
  }
}

function onToggle(s) { toggleSfx(s.id) }

function onNewSfx() {
  panel.open({
    component: GmSfxEditPanel,
    title: 'New SFX',
    props: { sfx: null },
    listeners: {
      'sfx-created': (created) => {
        emit('add-sfx', created.id)
        panel.close()
      },
    },
  })
}
</script>

<style scoped>
.filter-input { width: 100%; font-size: 12px; padding: 6px 8px; margin-bottom: 8px; box-sizing: border-box;
  background: var(--overlay-6); color: var(--text); border: 1px solid var(--overlay-10); border-radius: 6px; }


</style>
