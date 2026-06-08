<template>
  <div>
    <div class="ps-list">
      <div v-for="t in traits" :key="t.id" class="entity-row"
        :class="{ selected: selectedId === t.id }"
        @click="$emit('select', t)">
        <span class="entity-name">{{ t.name }}</span>
        <span :class="'die-' + (t.defaultDieType||'d6').toLowerCase()" style="font-weight:700;font-size:11px">{{ t.defaultDieType||'d6' }}</span>
      </div>
      <div v-if="traits.length === 0" class="empty">No traits in this set</div>
    </div>
    <button class="ps-add-btn" @click="$emit('add-trait')">+ New Trait</button>
  </div>
</template>

<script setup>
defineProps({
  traits: { type: Array, default: () => [] },
  selectedId: { type: String, default: '' },
})
defineEmits(['select', 'close', 'add-trait'])
</script>

<style scoped>
.ps-list { display: flex; flex-direction: column; gap: 3px; }
.entity-row { display: flex; align-items: center; gap: 6px; padding: 8px 10px; border-radius: 6px; cursor: pointer; background: rgba(255,255,255,0.03); transition: background 0.15s; font-size: 13px; }
.entity-row:hover { background: rgba(255,255,255,0.06); }
.entity-row.selected { background: rgba(64,136,212,0.15); border: 1px solid var(--accent-dim); }
.entity-name { flex: 1; font-weight: 500; }
.empty { font-size: 12px; color: var(--text-dim); padding: 12px 0; text-align: center; }
.ps-add-btn { font-size: 12px; padding: 6px; margin-top: 8px; background: var(--accent-dim); color: var(--text); border-radius: 6px; border: none; cursor: pointer; width: 100%; }
.ps-add-btn:hover { background: var(--accent); }
</style>
