<template>
  <div
    class="rolltable-node"
    :class="{ 'external-terminal': data.terminal, 'external-middle': data.external && !data.terminal }"
  >
    <div class="rt-header">
      <span class="rt-badge">TBL</span>
      <span class="rt-name">{{ data.name }}</span>
      <button class="rt-edit" title="Open table" @click.stop="data.onOpenTable?.(data.entityId)">✎</button>
    </div>
    <div class="rt-subtitle">
      <span v-if="data.lifePathName">{{ data.lifePathName }}</span>
      <span v-if="data.factionNames?.length" class="rt-sub-faction">{{ data.factionNames.join(' + ') }}</span>
    </div>
    <div class="rt-meta">
      <span class="rt-chip">{{ data.scheme }}</span>
      <span class="rt-chip">{{ data.die }}</span>
      <span v-if="data.rollSource === 'trait_dice'" class="rt-chip rt-chip-accent">trait dice</span>
    </div>
    <div
      v-for="row in data.rows"
      :key="row.index"
      class="rt-row"
      :class="{ 'has-next': row.nextTarget }"
      :title="rowTooltip(row)"
    >
      <span class="rt-num">{{ row.index + 1 }}</span>
      <span v-if="row.key" class="rt-key">{{ row.key }}</span>
      <span class="rt-label">{{ row.label || '—' }}</span>
      <span v-if="row.nextTarget" class="rt-next">→ {{ row.nextTarget.name }}</span>
    </div>

    <Handle id="target" type="target" :position="Position.Top" />
    <Handle
      v-for="row in data.rows.filter(r => r.nextTarget)"
      :key="'h' + row.index"
      :id="'row-' + row.index"
      type="source"
      :position="Position.Right"
      :style="{ top: rowCenter(row.index) + 'px' }"
    />
  </div>
</template>

<script setup>
import { onMounted } from 'vue'
import { Handle, Position } from '@vue-flow/core'
import { useEffectActions } from '@/composables/useEffectActions.js'
import { RT_HEADER_H, RT_SUBTITLE_H, RT_META_H, RT_ROW_H } from '@/composables/lifePathGraph.js'

const props = defineProps({
  id: { type: String, required: true },
  data: { type: Object, required: true },
  selected: { type: Boolean, default: false },
})

const { load: loadEffectActions, summarize } = useEffectActions()
onMounted(() => { loadEffectActions() })

// Absolute Y of a row's center within the node, matching the fixed CSS heights.
function rowCenter(index) {
  return RT_HEADER_H + RT_SUBTITLE_H + RT_META_H + index * RT_ROW_H + RT_ROW_H / 2
}

function resolve(target) {
  return props.data.tableNames?.[target] || target
}

function rowTooltip(row) {
  const parts = []
  if (row.label) parts.push(row.label)
  const effs = (row.effects || []).map((e) => summarize(e, resolve)).filter(Boolean)
  if (effs.length) parts.push(effs.join(' · '))
  const conds = (row.conditions || []).map((c) => c.narrative || c.type).filter(Boolean)
  if (conds.length) parts.push('if ' + conds.join(' · '))
  return parts.join('\n')
}
</script>

<style scoped>
.rolltable-node {
  position: relative;
  width: 250px;
  background: rgba(14, 16, 26, 0.96);
  border: 1px solid var(--accent-dim);
  border-radius: 8px;
  color: var(--text);
  overflow: visible;
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.35);
}
.rolltable-node.external-terminal { border-color: #e88830; }
.rolltable-node.external-middle { border-color: #40b860; }
.rt-header {
  height: 40px; box-sizing: border-box;
  display: flex; align-items: center; gap: 6px; padding: 0 8px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}
.rt-badge {
  font-size: 8px; text-transform: uppercase; padding: 1px 5px; border-radius: 3px;
  background: #40b860; color: #0a0a0f; font-weight: 700; flex-shrink: 0;
}
.rt-name { font-size: 13px; font-weight: 600; flex: 1; min-width: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.rt-edit { font-size: 12px; padding: 2px 6px; border-radius: 4px; background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.1); color: var(--text); cursor: pointer; flex-shrink: 0; }
.rt-edit:hover { background: var(--accent); color: #fff; }
.rt-subtitle {
  height: 16px; box-sizing: border-box;
  display: flex; align-items: center; gap: 6px; padding: 0 8px;
  font-size: 9px; color: var(--text-dim);
  border-bottom: 1px solid rgba(255, 255, 255, 0.04);
  white-space: nowrap; overflow: hidden;
}
.rt-sub-faction { color: #e88830; }
.rt-meta {
  height: 20px; box-sizing: border-box;
  display: flex; align-items: center; gap: 4px; padding: 0 8px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.04);
}
.rt-chip {
  font-size: 8px; color: var(--text-dim); background: rgba(255,255,255,0.05);
  padding: 1px 5px; border-radius: 3px; text-transform: uppercase;
}
.rt-chip-accent { color: var(--accent); }
.rt-row {
  height: 26px; box-sizing: border-box;
  display: flex; align-items: center; gap: 6px; padding: 0 8px;
  font-size: 10px; border-bottom: 1px solid rgba(255, 255, 255, 0.03);
  white-space: nowrap; overflow: hidden;
}
.rt-row:last-child { border-bottom: none; }
.rt-num { width: 14px; color: var(--text-dim); flex-shrink: 0; }
.rt-key { color: var(--text-dim); font-family: monospace; flex-shrink: 0; }
.rt-label { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; }
.rt-next {
  font-size: 8px; color: var(--accent); background: rgba(0, 200, 150, 0.12);
  padding: 1px 4px; border-radius: 3px; flex-shrink: 0; max-width: 90px;
  overflow: hidden; text-overflow: ellipsis;
}
</style>
