<template>
  <div class="scene-summary">
    <h3>Scene</h3>
    <div v-if="entities.length === 0" class="empty">No characters or GMCs here</div>
    <div v-for="e in entities" :key="e.id" class="scene-row" @click="$emit('inspect', e.id)">
      <span class="entity-type-badge" :class="'type-' + e.type">{{ e.type === 'GMC' ? 'GMC' : 'PC' }}</span>
      <span class="entity-name">{{ e.name }}</span>
      <span class="scene-raz">⚡{{ e.razmerit }}</span>
    </div>

    <!-- Parents and zones live under drawers: the roster above is here only. -->
    <template v-for="d in drawers" :key="d.key">
      <button class="scene-drawer" @click="toggle(d.key)">
        <span class="scene-caret">{{ open[d.key] ? '▾' : '▸' }}</span>
        {{ d.label }} ({{ d.groups.length }})
      </button>
      <div v-if="open[d.key]" class="scene-drawer-body">
        <div v-for="g in d.groups" :key="g.id" class="scene-group">
          <div class="scene-group-label">{{ g.name }}</div>
          <div v-if="!g.entities.length" class="empty scene-group-empty">no one</div>
          <div v-for="e in g.entities" :key="e.id" class="scene-row" @click="$emit('inspect', e.id)">
            <span class="entity-type-badge" :class="'type-' + e.type">{{ e.type === 'GMC' ? 'GMC' : 'PC' }}</span>
            <span class="entity-name">{{ e.name }}</span>
            <span class="scene-raz">⚡{{ e.razmerit }}</span>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed, reactive } from 'vue'

const props = defineProps({
  entities: { type: Array, default: () => [] },
  // [{ id, name, entities: [{ id, name, type, razmerit }] }]
  parents: { type: Array, default: () => [] },
  zones: { type: Array, default: () => [] },
})
defineEmits(['inspect'])

const drawers = computed(() => [
  { key: 'parents', label: 'Parents', groups: props.parents },
  { key: 'zones', label: 'Zones', groups: props.zones },
].filter((d) => d.groups.length))

// Collapsed by default — the point is a quiet roster with the wider picture a
// click away.
const open = reactive({ parents: false, zones: false })
function toggle(key) { open[key] = !open[key] }
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

.scene-drawer {
  display: flex; align-items: center; gap: 4px;
  width: 100%; margin-top: 6px; padding: 4px 2px;
  background: none; border: none; cursor: pointer;
  font-size: 11px; color: var(--text-dim);
  text-transform: uppercase; letter-spacing: 1px;
}
.scene-drawer:hover { color: var(--text); }
.scene-caret { font-size: 9px; }
.scene-drawer-body { padding-left: 4px; }
.scene-group { margin-bottom: 6px; }
.scene-group-label {
  font-size: 10px; color: var(--text-dim);
  padding: 2px 4px; margin-bottom: 2px;
}
.scene-group-empty { padding: 2px 10px; font-size: 11px; }
</style>
