<template>
  <div class="canvas-universe-node" :class="{ current: data.isCurrent }">
    <div class="uni-header">
      <span class="uni-badge">UNI</span>
      <span class="uni-name">{{ data.name }}</span>
    </div>
    <div class="uni-actions" @click.stop>
      <button
        class="uni-btn"
        :title="data.expanded ? 'Collapse' : 'Expand'"
        @click.stop="data.onToggleExpand?.(data.entityId)"
      >{{ data.expanded ? '⊖' : '⊕' }}</button>
    </div>
    <Handle id="bottom" type="target" :position="Position.Bottom" />
    <Handle id="right" type="target" :position="Position.Right" />
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
.canvas-universe-node {
  min-width: 150px;
  padding: 8px 10px;
  border-radius: 10px;
  background: radial-gradient(circle at 50% 30%, rgba(150, 90, 220, 0.3), rgba(20, 20, 35, 0.95));
  border: 1px solid rgba(150, 90, 220, 0.5);
  color: var(--text);
}
.canvas-universe-node.current { border-color: #a86bf0; box-shadow: 0 0 12px rgba(150, 90, 220, 0.4); }
.uni-header { display: flex; align-items: center; gap: 6px; }
.uni-badge {
  font-size: 8px; text-transform: uppercase; padding: 1px 5px; border-radius: 3px;
  background: #a86bf0; color: #0a0a0f; font-weight: 700;
}
.uni-name { font-size: 13px; font-weight: 600; }
.uni-actions { display: flex; justify-content: flex-end; margin-top: 6px; }
.uni-btn {
  font-size: 13px; padding: 2px 8px; border-radius: 5px;
  background: rgba(255, 255, 255, 0.06); color: var(--text-dim); border: none; cursor: pointer;
}
.uni-btn:hover { background: #a86bf0; color: #fff; }
</style>
