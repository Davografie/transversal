<template>
  <div class="peers-bar">
    <button
      v-for="p in peers"
      :key="p.id"
      class="peer-chip"
      :class="{ assumed: p.id === assumedId, viewing: p.id === viewedId }"
      :title="p.name"
      @click.stop="$emit('select', p.id)"
    >
      <MediaImage v-if="p.sheetImage" :src="p.sheetImage" class="peer-img" alt="" />
      <span v-else class="peer-avatar">{{ p.name.charAt(0) }}</span>
      <span class="peer-label">{{ p.name }}</span>
    </button>
  </div>
</template>

<script setup>
import MediaImage from '@/components/MediaImage.vue'

// The horizontal peer strip above the sheet/roller bands. `assumed` marks the
// entity you act as, `viewing` the one you are only peeking at — the parent
// decides both and handles the click.
defineProps({
  peers: { type: Array, default: () => [] },
  assumedId: { type: String, default: null },
  viewedId: { type: String, default: null },
})

defineEmits(['select'])
</script>

<style scoped>
.peers-bar {
  display: flex;
  gap: 6px;
  overflow-x: auto;
  padding: 4px 8px;
  scrollbar-width: none;
}
.peers-bar::-webkit-scrollbar { display: none; }
.peer-chip {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
  padding: 3px 10px 3px 4px;
  border-radius: 16px;
  background: var(--bg-panel);
  border: 1px solid var(--overlay-8);
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s;
}
.peer-chip:hover { border-color: var(--overlay-20); }
/* You ARE this entity — solid fill. */
.peer-chip.assumed {
  border-color: var(--accent);
  background: var(--accent-dim);
}
/* You are peeking at this entity (inspect) — highlight border only, no fill. */
.peer-chip.viewing {
  border-color: var(--accent);
}
.peer-img, .peer-avatar {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  object-fit: cover;
  flex-shrink: 0;
}
.peer-avatar {
  background: var(--accent-dim);
  color: var(--accent);
  font-size: 10px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
}
.peer-label {
  font-size: 12px;
  white-space: nowrap;
  color: var(--text-dim);
}
.peer-chip.assumed .peer-label { color: var(--text); }
.peer-chip.viewing .peer-label { color: var(--text-dim); }
</style>
