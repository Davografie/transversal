<template>
  <div class="lpd-root">
    <div class="lpd-header">
      <span class="lpd-name">{{ lp.name }}</span>
      <span class="lpd-type">{{ lp.universe }}</span>
      <button class="lpd-canvas" title="Open in canvas" @click="openFullCanvas">🗺</button>
      <button class="lpd-edit" @click="editPath">✎ Edit</button>
    </div>
    <p class="lpd-desc">{{ lp.description || 'No description' }}</p>

    <div class="lpd-subsection">
      <span class="lpd-subtitle">Entry table</span>
      <span class="lpd-detail">{{ lp.entryTableId || 'None' }}</span>
    </div>

    <div class="lpd-subsection">
      <span class="lpd-subtitle">Discovery</span>
      <span v-if="!discoveryRows.length" class="lpd-detail">None — visible to all</span>
      <table v-else class="lpd-table">
        <tbody>
          <tr v-for="(row, i) in discoveryRows" :key="i">
            <td class="lpd-key">{{ row.typeLabel }}</td>
            <td>{{ row.valueLabel }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="lpd-subsection">
      <span class="lpd-subtitle">Roll tables</span>
      <GmList
        :items="tables"
        item-key="id"
        empty-text="No tables linked"
        @click="openTable"
      >
        <template #item="{ item: t }">
          <span class="entity-name">{{ t.name }}</span>
          <span class="entity-universe">{{ t.scheme }}</span>
          <span class="entity-id">{{ t.id }}</span>
        </template>
      </GmList>
      <button class="lpd-add-btn" @click="addTable">＋ Add roll table</button>
    </div>

    <button class="lpd-delete" @click="onDeleteConfirmed">Delete life path</button>
  </div>
</template>

<script setup>
import { computed, inject, onMounted, onUnmounted, watch } from 'vue'
import { useLifePaths } from '@/composables/useLifePaths.js'
import { useRollTables } from '@/composables/useRollTables.js'
import { usePanel } from '@/composables/usePanel.js'
import { usePanelBus } from '@/composables/usePanelBus.js'
import GmRollTableDetailPanel from './GmRollTableDetailPanel.vue'
import GmRollTableEditPanel from './GmRollTableEditPanel.vue'
import GmLifePathEditPanel from './GmLifePathEditPanel.vue'
import GmList from './GmList.vue'

const panel = usePanel()
const bus = usePanelBus()
const { deleteLifePath } = useLifePaths()
const { tables, fetchTables } = useRollTables()

const props = defineProps({
  lp: { type: Object, required: true },
})

async function refreshTables() {
  try { await fetchTables(props.lp.id) } catch {}
}

// `tables` is a module-level singleton (useRollTables); re-fetch this path's
// tables when it becomes the active tab again so it doesn't show another path's.
const panelActive = inject('panelActive', computed(() => true))
watch(panelActive, (active) => { if (active) refreshTables() })

let offLifepathSaved = null
onMounted(() => {
  refreshTables()
  offLifepathSaved = bus.on('lifepath-saved', refreshTables)
})
onUnmounted(() => { if (offLifepathSaved) offLifepathSaved() })

function openTable(t) {
  panel.open({ component: GmRollTableDetailPanel, title: t.name, id: t.id, props: { tableId: t.id, name: t.name } })
}

function addTable() {
  panel.open({
    component: GmRollTableEditPanel,
    title: 'New Roll Table',
    props: { tableId: '', lifePathId: props.lp.id, universe: props.lp.universe },
  })
}

function editPath() {
  panel.open({ component: GmLifePathEditPanel, title: 'Edit ' + props.lp.name, props: { lp: props.lp } })
}

function openFullCanvas() {
  bus.emit('canvas:open-full', { mode: 'life-path', entityId: props.lp.id, lifePath: props.lp })
}

async function onDeleteConfirmed() {
  await deleteLifePath(props.lp.id)
  bus.emit('lifepath-saved', { id: props.lp.id, universe: props.lp.universe })
  panel.close()
}

const discoveryRows = computed(() => {
  const rows = []
  const d = props.lp.discovery
  if (!d) return rows
  for (const loc of (d.atLocation || [])) rows.push({ typeLabel: '📍 Location', valueLabel: loc })
  for (const ent of (d.knowsEntity || [])) rows.push({ typeLabel: '👤 Knows', valueLabel: ent })
  for (const trait of (d.possessesTrait || [])) rows.push({ typeLabel: '🎯 Has trait', valueLabel: trait })
  for (const [trait, die] of Object.entries(d.hasTraitRating || {})) rows.push({ typeLabel: `⭐ Rating ≥ ${die}`, valueLabel: trait })
  for (const rel of (d.hasRelationship || [])) rows.push({ typeLabel: '🔗 Relationship', valueLabel: rel })
  return rows
})
</script>

<style scoped>
.lpd-root { padding: 0; }
.lpd-header { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
.lpd-name { font-weight: 600; font-size: 14px; }
.lpd-type { font-size: 9px; color: var(--text-dim); text-transform: uppercase; background: rgba(255,255,255,0.06); padding: 1px 5px; border-radius: 3px; }
.lpd-desc { font-size: 11px; color: var(--text-dim); margin: 0 0 8px 0; }
.lpd-subsection { margin-top: 8px; }
.lpd-subtitle { display: block; font-size: 9px; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 2px; }
.lpd-detail { display: block; font-size: 10px; color: var(--text-dim); line-height: 1.5; }
.lpd-table { width: 100%; border-collapse: collapse; margin: 4px 0 6px; font-size: 10px; }
.lpd-table td { padding: 2px 6px; border-bottom: 1px solid rgba(255,255,255,0.03); color: var(--text); }
.lpd-key { color: var(--text-dim); width: 130px; }
.lpd-add-btn {
  width: 100%; margin-top: 4px; font-size: 11px; padding: 6px 0;
  background: rgba(0,200,150,0.08); border: 1px dashed rgba(0,200,150,0.25);
  border-radius: 4px; color: var(--accent); cursor: pointer;
}
.lpd-add-btn:hover { background: rgba(0,200,150,0.14); }
.lpd-edit { margin-left: auto; font-size: 10px; padding: 2px 8px; background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.1); color: var(--text); border-radius: 4px; cursor: pointer; }
.lpd-canvas { font-size: 12px; padding: 2px 6px; background: rgba(0,200,150,0.08); border: 1px solid rgba(0,200,150,0.25); color: var(--accent); border-radius: 4px; cursor: pointer; }
.lpd-canvas:hover { background: rgba(0,200,150,0.16); }
.lpd-delete {
  width: 100%; margin-top: 12px; font-size: 11px; padding: 6px 0;
  background: rgba(212,64,64,0.08); border: 1px solid rgba(212,64,64,0.25);
  border-radius: 4px; color: var(--danger); cursor: pointer;
}
.lpd-delete:hover { background: rgba(212,64,64,0.16); }
</style>
