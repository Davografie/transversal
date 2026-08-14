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
        v-if="!data.expanded"
        class="loc-btn"
        title="Expand (load neighbors)"
        @click.stop="data.onExpand?.(data.entityId)"
      >⊕</button>
      <button
        v-else
        class="loc-btn"
        title="Collapse"
        @click.stop="data.onCollapse?.(data.entityId)"
      >⊖</button>
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
    <Handle type="target" :position="Position.Top" />
    <Handle type="source" :position="Position.Bottom" />
    <Handle type="source" :position="Position.Right" id="lateral" />
    <Handle type="target" :position="Position.Left" id="lateral-in" />
  </div>
</template>

<script setup>
import { Handle, Position } from '@vue-flow/core'

defineProps({
  id: { type: String, required: true },
  data: { type: Object, required: true },
  selected: { type: Boolean, default: false },
})
</script>

<style scoped>
.canvas-location-node {
  min-width: 150px;
  max-width: 220px;
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
</style>
