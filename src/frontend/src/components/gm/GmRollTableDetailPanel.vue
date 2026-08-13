<template>
  <div class="rtd-root">
    <div class="rtd-header">
      <span class="rtd-name">{{ table?.name || name }}</span>
      <span class="rtd-type">{{ table?.universe }}</span>
    </div>

    <div class="rtd-meta">
      <span class="rtd-chip">scheme: {{ table?.scheme }}</span>
      <span class="rtd-chip">die: {{ table?.die }}</span>
      <span v-if="table?.lifePath" class="rtd-chip">path: {{ table.lifePath }}</span>
    </div>

    <div v-if="table?.check" class="rtd-subsection">
      <span class="rtd-subtitle">Check</span>
      <span class="rtd-detail">
        roll {{ table.check.traitIds.join(', ') || '(untrained)' }} vs {{ table.check.difficulty }}
        <template v-if="table.check.freeChoice"> · free choice</template>
      </span>
    </div>

    <div class="rtd-subsection">
      <span class="rtd-subtitle">Entries</span>
      <div v-if="!table?.entries?.length" class="rtd-detail">No entries</div>
      <table v-else class="rtd-table">
        <thead>
          <tr><th>#</th><th>Key</th><th>Label</th><th>Effects</th></tr>
        </thead>
        <tbody>
          <tr v-for="(e, i) in table.entries" :key="i">
            <td class="rtd-num">{{ i + 1 }}</td>
            <td class="rtd-key">{{ entryKey(e) }}</td>
            <td>
              <div class="rtd-label">{{ e.label }}</div>
              <div v-if="e.description" class="rtd-desc">{{ e.description }}</div>
              <div v-if="e.conditions?.length" class="rtd-conditions">
                <span v-for="(c, ci) in e.conditions" :key="ci" class="rtd-cond">if {{ conditionSummary(c) }}</span>
              </div>
            </td>
            <td>
              <div v-for="(eff, ei) in e.effects" :key="ei" class="rtd-effect">
                {{ effectSummary(eff) }}
              </div>
              <div v-if="!e.effects?.length" class="rtd-detail">—</div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useApi } from '@/composables/useApi.js'

const props = defineProps({
  tableId: { type: String, required: true },
  name: { type: String, default: '' },
})

const { graphql } = useApi()
const table = ref(null)

onMounted(async () => {
  try {
    const data = await graphql(`query($id:ID!){rollTable(id:$id){id name universe lifePath scheme die check{traitIds difficulty freeChoice} entries{label description minValue maxValue weight tier conditions{type target value narrative} effects{timing type action target result targetScope context}}}}`, { id: props.tableId })
    table.value = data?.rollTable || null
  } catch {}
})

function entryKey(e) {
  if (e.minValue != null || e.maxValue != null) return `${e.minValue ?? ''}–${e.maxValue ?? ''}`
  if (e.weight != null) return `w${e.weight}`
  if (e.tier) return e.tier
  return ''
}

function effectSummary(e) {
  const parts = [`${e.type}/${e.action}`]
  if (e.target) parts.push(e.target)
  if (e.result) parts.push(e.result)
  return parts.join(' ')
}

function conditionSummary(c) {
  const parts = [c.type]
  if (c.target) parts.push(c.target)
  if (c.value) parts.push(c.value)
  if (c.narrative) parts.push(`"${c.narrative}"`)
  return parts.join(' ')
}
</script>

<style scoped>
.rtd-root { padding: 0; }
.rtd-header { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
.rtd-name { font-weight: 600; font-size: 14px; }
.rtd-type { font-size: 9px; color: var(--text-dim); text-transform: uppercase; background: rgba(255,255,255,0.06); padding: 1px 5px; border-radius: 3px; }
.rtd-meta { display: flex; gap: 6px; margin-bottom: 8px; }
.rtd-chip { font-size: 9px; color: var(--text-dim); background: rgba(255,255,255,0.04); padding: 2px 6px; border-radius: 3px; text-transform: uppercase; }
.rtd-subsection { margin-top: 10px; }
.rtd-subtitle { display: block; font-size: 9px; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 4px; }
.rtd-detail { display: block; font-size: 10px; color: var(--text-dim); line-height: 1.5; }
.rtd-table { width: 100%; border-collapse: collapse; margin-top: 4px; font-size: 10px; }
.rtd-table th { text-align: left; padding: 2px 6px; border-bottom: 1px solid rgba(255,255,255,0.06); color: var(--text-dim); font-size: 8px; text-transform: uppercase; }
.rtd-table td { padding: 4px 6px; border-bottom: 1px solid rgba(255,255,255,0.03); vertical-align: top; color: var(--text); }
.rtd-num { width: 20px; color: var(--text-dim); }
.rtd-key { width: 60px; color: var(--text-dim); font-family: monospace; }
.rtd-label { font-weight: 500; }
.rtd-desc { font-size: 9px; color: var(--text-dim); }
.rtd-conditions { margin-top: 2px; display: flex; flex-direction: column; gap: 1px; }
.rtd-cond { font-size: 9px; color: var(--accent); }
.rtd-effect { font-family: monospace; font-size: 10px; color: var(--text); }
</style>
