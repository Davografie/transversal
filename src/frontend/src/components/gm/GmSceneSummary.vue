<template>
  <div class="scene-summary">
    <h3>Scene</h3>
    <div v-if="entities.length === 0" class="empty">No characters or GMCs here</div>
    <div v-for="e in entities" :key="e.id" class="scene-row" @click="$emit('inspect', e.id)">
      <span class="entity-type-badge" :class="'type-' + e.type">{{ e.type === 'GMC' ? 'GMC' : 'PC' }}</span>
      <span class="entity-name">{{ e.name }}</span>
      <span class="scene-raz">⚡{{ e.razmerit }}</span>
    </div>
  </div>
</template>

<script setup>
defineProps({ entities: { type: Array, default: () => [] } })
defineEmits(['inspect'])
</script>

<style scoped>
.scene-summary h3 {
  font-size: 12px; color: var(--text-dim); margin-bottom: 6px;
  text-transform: uppercase; letter-spacing: 1px;
}
.scene-row {
  display: flex; align-items: center; gap: 6px;
  padding: 6px 10px; margin-bottom: 3px;
  background: var(--overlay-4); border-radius: 6px;
  font-size: 13px; cursor: pointer; transition: background 0.15s;
}
.scene-row:hover { background: var(--overlay-8); }
.scene-raz { font-size: 11px; color: var(--accent); font-weight: 600; margin-left: auto; }
</style>
