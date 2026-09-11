<template>
  <div class="lpd-root">
    <div class="lpd-header">
      <span class="lpd-name">{{ lp.name }}</span>
      <span class="lpd-type">{{ lp.universe }}</span>
      <Button class="lpd-canvas" variant="neutral" title="Open in canvas" @click="openFullCanvas">🗺</Button>
      <Button class="lpd-edit" variant="neutral" @click="editPath">✎ Edit</Button>
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
      <Button class="lpd-add-btn" variant="secondary" block @click="addTable">＋ Add roll table</Button>
    </div>

    <Button class="lpd-delete" variant="danger-ghost" size="sm" block @click="onDeleteConfirmed">Delete life path</Button>
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
import GmList from '@/components/ui/GmList.vue'
import Button from '@/components/ui/Button.vue'

const panel = usePanel()
const bus = usePanelBus()
const { deleteLifePath } = useLifePaths()
const { tablesFor, fetchTables } = useRollTables()

const props = defineProps({
  lp: { type: Object, required: true },
})

// This path's tables, from the per-path store (a sibling panel on another path
// cannot clobber them).
const tables = tablesFor(props.lp?.id)

async function refreshTables() {
  try { await fetchTables(props.lp.id) } catch {}
}

// Re-fetch this path's tables when it becomes the active tab again — a sibling
// panel or a sub-panel may have changed them.
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
.lpd-type { font-size: 9px; color: var(--text-dim); text-transform: uppercase; background: var(--overlay-6); padding: 1px 5px; border-radius: 3px; }
.lpd-desc { font-size: 11px; color: var(--text-dim); margin: 0 0 8px 0; }
.lpd-subsection { margin-top: 8px; }
.lpd-subtitle { display: block; font-size: 9px; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 2px; }
.lpd-detail { display: block; font-size: 10px; color: var(--text-dim); line-height: 1.5; }
.lpd-table { width: 100%; border-collapse: collapse; margin: 4px 0 6px; font-size: 10px; }
.lpd-table td { padding: 2px 6px; border-bottom: 1px solid var(--overlay-2); color: var(--text); }
.lpd-key { color: var(--text-dim); width: 130px; }
/* Layout hooks only — fill/border/typography/state come from Button. */
.lpd-add-btn { margin-top: 4px; }
.lpd-edit { margin-left: auto; }
.lpd-delete { margin-top: 12px; }
</style>
