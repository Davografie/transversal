<template>
  <div class="lpd-root">
    <div class="lpd-header">
      <span class="lpd-name">{{ path.name }}</span>
      <span class="lpd-type">{{ path.universe }}</span>
      <Button class="lpd-canvas" variant="neutral" title="Open in canvas" @click="openFullCanvas">🗺</Button>
      <Button class="lpd-edit" variant="neutral" @click="editPath">✎ Edit</Button>
    </div>
    <p class="lpd-desc">{{ path.description || 'No description' }}</p>

    <div class="lpd-subsection">
      <span class="lpd-subtitle">Entry table</span>
      <span class="lpd-detail">{{ path.entryTableId || 'None' }}</span>
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
import GmRollTableEditPanel from './GmRollTableEditPanel.vue'
import GmLifePathEditPanel from './GmLifePathEditPanel.vue'
import GmList from '@/components/ui/GmList.vue'
import Button from '@/components/ui/Button.vue'

const panel = usePanel()
const bus = usePanelBus()
const { deleteLifePath, pathsByUniverse } = useLifePaths()
const { tablesFor, fetchTables } = useRollTables()

const props = defineProps({
  lp: { type: Object, required: true },
})

// The *stored* copy wins over the prop we were opened with. The panel is handed
// a plain object snapshot, and saving from the editor patches the store — so
// reading through the store is what makes an edited description (or conditions,
// or the entry table) show up here instead of going stale (B41). Falls back to
// the prop when the store has no bucket for this path, e.g. opened from the
// canvas, which never fetched a universe list.
const path = computed(() => {
  for (const list of Object.values(pathsByUniverse.value || {})) {
    const found = (list || []).find(p => p.id === props.lp.id)
    if (found) return found
  }
  return props.lp
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
  // The step wrapping this table, so the editor's connector column edits the
  // right one. A path may wrap the same table twice, and this list shows each
  // wrapped table once — the first step is the one this row means.
  const step = (path.value.steps || []).find(s => s.tableId === t.id) || null
  panel.open({
    component: GmRollTableEditPanel,
    title: t.name,
    id: t.id,
    badge: 'ROLL-TABLE',
    props: { tableId: t.id, lifePathId: path.value.id, stepId: step?.id || '' },
  })
}

function addTable() {
  panel.open({
    component: GmRollTableEditPanel,
    title: 'New Roll Table',
    badge: 'ROLL-TABLE',
    props: { tableId: '', lifePathId: path.value.id, universe: path.value.universe },
  })
}

function editPath() {
  panel.open({
    component: GmLifePathEditPanel,
    title: 'Edit ' + path.value.name,
    id: path.value.id,
    badge: 'LIFE-PATH',
    props: { lp: path.value },
  })
}

function openFullCanvas() {
  bus.emit('canvas:open-full', { mode: 'life-path', entityId: path.value.id, lifePath: path.value })
}

async function onDeleteConfirmed() {
  await deleteLifePath(props.lp.id)
  bus.emit('lifepath-saved', { id: props.lp.id, universe: props.lp.universe })
  panel.close()
}

const discoveryRows = computed(() => {
  const rows = []
  const d = path.value.discovery
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
