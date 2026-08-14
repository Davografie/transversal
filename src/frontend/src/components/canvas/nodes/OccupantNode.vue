<template>
  <div
    class="canvas-occupant-node"
    :class="{ 'is-gmc': data.entityType === 'gmc', 'is-pc': data.entityType === 'character' }"
    @click.stop="data.onInspect?.(data.entityId)"
  >
    <div class="occ-portrait" :style="portraitStyle">
      <span v-if="!data.image">{{ initials }}</span>
    </div>
    <div class="occ-body">
      <div class="occ-name">{{ data.name }}</div>
      <div v-if="data.role" class="occ-role">{{ data.role }}</div>
      <div v-if="data.rank" class="occ-rank">{{ data.rank }}</div>
      <div v-if="data.factions?.length" class="occ-factions">
        <span v-for="f in data.factions" :key="f.id" class="faction-chip">{{ f.name }}</span>
      </div>
    </div>
    <div class="occ-actions" @click.stop>
      <button class="occ-btn" title="Toggle relations" @click.stop="data.onToggleRelations?.(data.entityId)">🔗</button>
      <button class="occ-btn" title="Show faction" @click.stop="data.onShowFaction?.(data.entityId)">🏴</button>
      <button class="occ-btn" title="Inspect" @click.stop="data.onInspect?.(data.entityId)">🔍</button>
    </div>
    <Handle id="target-top" type="target" :position="Position.Top" />
    <Handle id="target-right" type="target" :position="Position.Right" />
    <Handle id="target-bottom" type="target" :position="Position.Bottom" />
    <Handle id="target-left" type="target" :position="Position.Left" />
    <Handle id="source-top" type="source" :position="Position.Top" />
    <Handle id="source-right" type="source" :position="Position.Right" />
    <Handle id="source-bottom" type="source" :position="Position.Bottom" />
    <Handle id="source-left" type="source" :position="Position.Left" />
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { Handle, Position } from '@vue-flow/core'

const props = defineProps({
  id: { type: String, required: true },
  data: { type: Object, required: true },
  selected: { type: Boolean, default: false },
})

const initials = computed(() => {
  return (props.data.name || '?').split(/\s+/).map((w) => w[0]).join('').slice(0, 2).toUpperCase()
})

const portraitStyle = computed(() => {
  if (props.data.image) return { backgroundImage: `url(${props.data.image})`, backgroundSize: 'cover', backgroundPosition: 'center' }
  return {}
})
</script>

<style scoped>
.canvas-occupant-node {
  display: flex; align-items: center; gap: 8px;
  min-width: 170px; max-width: 260px;
  padding: 6px 8px; border-radius: 20px;
  background: rgba(15, 15, 25, 0.92);
  border: 1px solid rgba(255, 255, 255, 0.12);
  color: var(--text); cursor: pointer;
}
.canvas-occupant-node.is-gmc { border-color: rgba(232, 136, 48, 0.5); }
.canvas-occupant-node.is-pc { border-color: var(--accent); }
.occ-portrait {
  width: 34px; height: 34px; border-radius: 50%; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center;
  background: var(--accent-dim); font-weight: 700; font-size: 12px; color: #fff;
}
.occ-body { flex: 1; min-width: 0; }
.occ-name { font-size: 13px; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.occ-role { font-size: 10px; color: var(--text-dim); font-style: italic; }
.occ-rank { font-size: 10px; color: var(--accent); font-weight: 700; }
.occ-factions { display: flex; flex-wrap: wrap; gap: 3px; margin-top: 2px; }
.faction-chip {
  font-size: 8px; padding: 1px 5px; border-radius: 3px;
  background: rgba(232, 136, 48, 0.25); color: #e88830;
}
.occ-actions { display: flex; flex-direction: column; gap: 2px; }
.occ-btn { padding: 2px 4px; font-size: 11px; border-radius: 4px; background: rgba(255,255,255,0.06); border: none; cursor: pointer; }
.occ-btn:hover { background: var(--accent); }
</style>
