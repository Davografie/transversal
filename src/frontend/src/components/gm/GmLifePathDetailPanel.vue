<template>
  <div class="lpd-root">
    <div class="lpd-header">
      <span class="lpd-name">{{ lp.name }}</span>
      <span class="lpd-type">{{ lp.universe }}</span>
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
      <div v-if="!tables.length" class="lpd-detail">No tables linked</div>
      <button v-for="t in tables" :key="t.id" class="lpd-table-btn" @click="openTable(t)">
        <span class="lpd-table-name">{{ t.name }}</span>
        <span class="lpd-table-scheme">{{ t.scheme }}</span>
      </button>
    </div>

    <button class="lpd-delete" @click="onDeleteConfirmed">Delete life path</button>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useApi } from '@/composables/useApi.js'
import { usePanel } from '@/composables/usePanel.js'
import { usePanelBus } from '@/composables/usePanelBus.js'
import GmRollTableDetailPanel from './GmRollTableDetailPanel.vue'

const panel = usePanel()
const bus = usePanelBus()
const { graphql } = useApi()

const props = defineProps({
  lp: { type: Object, required: true },
})

const tables = ref([])

async function fetchTables() {
  try {
    const data = await graphql(`query($lp:String){rollTables(lifePathId:$lp){id name scheme die}}`, { lp: props.lp.id })
    tables.value = data?.rollTables || []
  } catch {}
}

let offLifepathSaved = null
onMounted(() => {
  fetchTables()
  offLifepathSaved = bus.on('lifepath-saved', fetchTables)
})
onUnmounted(() => { if (offLifepathSaved) offLifepathSaved() })

function openTable(t) {
  panel.open({ component: GmRollTableDetailPanel, title: t.name, props: { tableId: t.id, name: t.name } })
}

function onDeleteConfirmed() {
  graphql(`mutation($id:ID!){deleteLifePath(id:$id)}`, { id: props.lp.id })
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
.lpd-table-btn {
  display: flex; align-items: center; gap: 8px; width: 100%;
  background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.06);
  border-radius: 4px; padding: 6px 10px; margin-bottom: 4px;
  cursor: pointer; text-align: left; color: var(--text);
}
.lpd-table-btn:hover { border-color: rgba(0,200,150,0.3); background: rgba(0,200,150,0.05); }
.lpd-table-name { font-weight: 500; font-size: 11px; }
.lpd-table-scheme { font-size: 9px; color: var(--text-dim); text-transform: uppercase; margin-left: auto; }
.lpd-delete {
  width: 100%; margin-top: 12px; font-size: 11px; padding: 6px 0;
  background: rgba(212,64,64,0.08); border: 1px solid rgba(212,64,64,0.25);
  border-radius: 4px; color: var(--danger); cursor: pointer;
}
.lpd-delete:hover { background: rgba(212,64,64,0.16); }
</style>
