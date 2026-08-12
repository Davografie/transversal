<template>
  <div>
    <input v-model="search" class="filter-input" placeholder="Filter SFXs…" />

    <div v-if="filtered.length === 0" class="empty">No SFXs match</div>
    <div v-else class="sfx-list">
      <div
        v-for="s in filtered"
        :key="s.id"
        class="sfx-row"
        :class="{ selected: selectedIds.includes(s.id) }"
        @click="toggleSfx(s.id)"
      >
        <span class="pick-icon">{{ selectedIds.includes(s.id) ? '✓' : '+' }}</span>
        <span class="sfx-name">{{ s.name }}</span>
        <span class="sfx-trigger">{{ s.trigger || '' }}</span>
      </div>
    </div>

    <button class="ps-add-btn" @click="onNewSfx">+ New SFX</button>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useTraitsConfig } from '@/composables/useTraitsConfig.js'
import { usePanel } from '@/composables/usePanel.js'
import GmSfxEditPanel from '@/components/gm/GmSfxEditPanel.vue'

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
  background: rgba(255,255,255,0.06); color: var(--text); border: 1px solid rgba(255,255,255,0.1); border-radius: 6px; }

.sfx-list { display: flex; flex-direction: column; gap: 2px; }
.sfx-row { display: flex; align-items: center; gap: 6px; padding: 6px 8px; border-radius: 4px; cursor: pointer; font-size: 12px; transition: background 0.1s; background: rgba(255,255,255,0.04); }
.sfx-row:hover { background: rgba(255,255,255,0.08); }
.sfx-row.selected { background: rgba(64,136,212,0.12); }

.pick-icon { font-weight: 700; font-size: 12px; width: 16px; text-align: center; flex-shrink: 0; }
.sfx-row.selected .pick-icon { color: var(--success); }

.sfx-name { flex: 1; font-weight: 500; }
.sfx-trigger { font-size: 10px; color: var(--text-dim); }

.empty { font-size: 12px; color: var(--text-dim); padding: 12px 0; text-align: center; }

.ps-add-btn { font-size: 12px; padding: 6px; margin-top: 8px; background: var(--accent-dim); color: var(--text); border-radius: 6px; border: none; cursor: pointer; width: 100%; }
.ps-add-btn:hover { background: var(--accent); }
</style>
