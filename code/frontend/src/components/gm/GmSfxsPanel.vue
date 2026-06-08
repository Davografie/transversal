<template>
  <div>
    <div class="ps-list">
      <div v-for="s in sfxs" :key="s.id" class="entity-row"
        :class="{ selected: selectedId === s.id }"
        @click="$emit('select', s)">
        <span class="entity-name">{{ s.name }}</span>
        <span style="font-size:10px;color:var(--text-dim)">{{ s.trigger||'—' }}</span>
      </div>
      <div v-if="sfxs.length === 0" class="empty">No SFXs</div>
    </div>
  </div>
</template>

<script setup>
defineProps({
  sfxs: { type: Array, default: () => [] },
  selectedId: { type: String, default: '' },
})
defineEmits(['select', 'close'])
</script>

<style scoped>
.ps-list { display: flex; flex-direction: column; gap: 3px; }
.entity-row { display: flex; align-items: center; gap: 6px; padding: 8px 10px; border-radius: 6px; cursor: pointer; background: rgba(255,255,255,0.03); transition: background 0.15s; font-size: 13px; }
.entity-row:hover { background: rgba(255,255,255,0.06); }
.entity-row.selected { background: rgba(64,136,212,0.15); border: 1px solid var(--accent-dim); }
.entity-name { flex: 1; font-weight: 500; }
.empty { font-size: 12px; color: var(--text-dim); padding: 12px 0; text-align: center; }
</style>
