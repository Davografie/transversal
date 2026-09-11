<template>
  <div class="pool-tabs">
    <template v-for="g in groups" :key="g.key">
      <div v-if="g.label && groups.length > 1" class="pool-tab-group-label">{{ g.label }}</div>
      <button
        v-for="e in g.members"
        :key="e.id"
        class="pool-tab"
        :class="{
          active: activeId === e.id,
          self: e.id === selfTabId,
          blink: (e.id === selfTabId && youTabBlink) || (e.id === difficultyTab && difficultyTabBlink),
        }"
        @click="$emit('select', e.id)"
      >
        {{ e.name }}
      </button>
    </template>
  </div>
</template>

<script setup>
// The pool switcher: one tab per entity sharing this location's pool, grouped
// with optional labels. `self` marks your own tab; `blink` is the parent's
// attention nudge (your tab when someone challenges you, the difficulty tab
// when the GM's target changes).
defineProps({
  groups: { type: Array, default: () => [] },   // [{ key, label, members: [{ id, name }] }]
  activeId: { type: String, default: null },
  selfTabId: { type: String, default: null },
  difficultyTab: { type: String, default: null },
  youTabBlink: { type: Boolean, default: false },
  difficultyTabBlink: { type: Boolean, default: false },
})

defineEmits(['select'])
</script>

<style scoped>
.pool-tabs { display: flex; gap: 6px; flex-wrap: wrap; justify-content: center; }
.pool-tab-group-label {
  flex-basis: 100%; text-align: center; font-size: 11px; font-weight: 700;
  color: var(--text-dim); letter-spacing: 0.05em; text-transform: uppercase;
  margin: 2px 0 -2px;
}
.pool-tab {
  padding: 6px 10px; font-size: 12px; font-weight: 600; border-radius: 8px;
  cursor: pointer; border: 1px solid transparent; background: var(--overlay-6);
  color: var(--text-dim);
}
.pool-tab.active { background: var(--accent, #7aa2f7); color: var(--text-invert); }
.pool-tab.self { border-color: var(--accent, #7aa2f7); }
.pool-tab.self:not(.active) { color: var(--text); background: var(--accent-12); }
.pool-tab.blink { animation: tab-blink 0.9s ease-in-out infinite; }
@keyframes tab-blink { 0%, 100% { box-shadow: 0 0 0 rgba(64,136,212,0); } 50% { box-shadow: 0 0 10px 2px var(--accent-85); } }
</style>
