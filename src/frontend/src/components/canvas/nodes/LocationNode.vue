<template>
  <div
    class="canvas-location-node"
    :class="{ focus: data.isFocus, scaffolding: data.isScaffolding }"
    @click.stop="data.onFocus?.(data.entityId)"
  >
    <div class="loc-header">
      <span class="loc-badge">LOC</span>
      <span class="loc-name">{{ data.name }}</span>
    </div>

    <div class="loc-actions" @click.stop>
      <button
        v-if="!data.isLeaf"
        class="loc-btn"
        :title="data.expanded ? 'Collapse' : 'Expand'"
        @click.stop="data.expanded ? data.onCollapse?.(data.entityId) : data.onExpand?.(data.entityId)"
      >{{ data.expanded ? '⊖' : '⊕' }}</button>
      <button
        class="loc-btn"
        :class="{ active: data.isFocus }"
        title="Focus here"
        @click.stop="data.onFocus?.(data.entityId)"
      >⊙</button>
      <button
        class="loc-btn"
        title="Open full viewport"
        @click.stop="data.onOpenFull?.(data.entityId)"
      >⛶</button>
    </div>

    <div v-if="data.occupants?.length" class="loc-occupants" @click.stop>
      <div
        v-for="occ in data.occupants"
        :key="occ.id"
        class="occ-tile"
        @mouseenter="data.onOccupantHover?.(occ.id)"
        @mouseleave="data.onOccupantLeave?.()"
        @click.stop="data.onInspect?.(occ.id)"
      >
        <span class="occ-name" :title="occ.name">{{ occ.name }}</span>
        <div class="occ-navdot">
          <img v-if="occ.image" :src="occ.image" :alt="occ.name" />
          <span v-else class="occ-initials">{{ initials(occ.name) }}</span>
        </div>
        <Handle
          :id="`occ-${occ.id}-source`"
          type="source"
          :position="Position.Right"
          class="occ-handle"
          :style="{ top: '50%', left: '50%', right: 'auto', bottom: 'auto', transform: 'translate(-50%, -50%)', width: '0', height: '0' }"
        />
        <Handle
          :id="`occ-${occ.id}-target`"
          type="target"
          :position="Position.Left"
          class="occ-handle"
          :style="{ top: '50%', left: '50%', right: 'auto', bottom: 'auto', transform: 'translate(-50%, -50%)', width: '0', height: '0' }"
        />
      </div>
    </div>

    <Handle v-if="!data.horizontal" id="top" type="source" :position="Position.Top" />
    <Handle v-if="!data.horizontal" id="bottom" type="target" :position="Position.Bottom" />
    <Handle v-if="!data.horizontal" id="bottom-source" type="source" :position="Position.Bottom" :style="{ left: '72%' }" />
    <Handle id="right" type="source" :position="Position.Right" />
    <Handle id="left" type="target" :position="Position.Left" />
    <Handle id="left-source" type="source" :position="Position.Left" />
    <Handle id="right-target" type="target" :position="Position.Right" />
  </div>
</template>

<script setup>
import { Handle, Position } from '@vue-flow/core'

defineProps({
  id: { type: String, required: true },
  data: { type: Object, required: true },
  selected: { type: Boolean, default: false },
})

function initials(name) {
  return (name || '?').split(/\s+/).map((w) => w[0]).join('').slice(0, 2).toUpperCase()
}
</script>

<style scoped>
.canvas-location-node {
  min-width: 150px;
  max-width: 240px;
  padding: 8px 10px;
  border-radius: 12px;
  background: radial-gradient(circle at 50% 30%, rgba(64, 136, 212, 0.35), rgba(20, 20, 35, 0.95));
  border: 1px solid var(--accent-dim);
  box-shadow: inset 0 0 12px rgba(64, 136, 212, 0.25);
  color: var(--text);
  cursor: pointer;
  transition: border-color 0.15s, box-shadow 0.15s;
}
.canvas-location-node.focus {
  border-color: var(--accent);
  box-shadow: 0 0 16px rgba(64, 136, 212, 0.6), inset 0 0 12px rgba(64, 136, 212, 0.3);
}
.canvas-location-node.scaffolding {
  opacity: 0.55;
  background: rgba(20, 20, 30, 0.8);
}
.loc-header { display: flex; align-items: center; gap: 6px; }
.loc-badge {
  font-size: 8px; text-transform: uppercase; padding: 1px 5px; border-radius: 3px;
  background: #40b860; color: #0a0a0f; font-weight: 700;
}
.loc-name { font-size: 13px; font-weight: 600; line-height: 1.2; }
.loc-actions { display: flex; gap: 4px; margin-top: 6px; }
.loc-btn {
  flex: 1; padding: 3px 0; font-size: 12px; border-radius: 5px;
  background: rgba(255, 255, 255, 0.06); color: var(--text-dim); border: none; cursor: pointer;
}
.loc-btn:hover { background: var(--accent); color: #fff; }
.loc-btn.active { background: var(--accent); color: #fff; }
.loc-occupants {
  display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px;
}
.occ-tile {
  position: relative; width: 32px; height: 32px;
}
.occ-name {
  position: absolute; bottom: 100%; left: 50%; transform: translateX(-50%);
  margin-bottom: 2px;
  font-size: 8px; max-width: 80px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  color: var(--text-dim); opacity: 0; transition: opacity 0.12s; pointer-events: none;
}
.occ-tile:hover .occ-name, .occ-tile:focus-within .occ-name { opacity: 1; }
.occ-navdot {
  position: absolute; inset: 0; width: 100%; height: 100%; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  background: var(--accent-dim); overflow: hidden;
}
.occ-navdot img { width: 100%; height: 100%; object-fit: cover; display: block; }
.occ-initials { font-size: 10px; font-weight: 700; color: #fff; }
.occ-handle { width: 0; height: 0; min-width: 0; min-height: 0; background: transparent; border: none; }
</style>
