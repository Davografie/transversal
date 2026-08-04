<template>
  <TransitionGroup name="toast" tag="div" class="toast-bar">
    <div
      v-for="t in toasts"
      :key="t.id"
      class="toast-item"
      :class="'toast-' + t.type"
      @click="dismissToast(t.id)"
    >
      <span class="toast-icon">{{ typeIcon(t.type) }}</span>
      <span class="toast-msg">{{ t.message }}</span>
    </div>
  </TransitionGroup>
</template>

<script setup>
const props = defineProps({
  toasts: { type: Array, required: true },
})

const emit = defineEmits(['dismiss'])

function dismissToast(id) {
  emit('dismiss', id)
}

function typeIcon(type) {
  switch (type) {
    case 'dice': return '🎲'
    case 'roll': return '⚡'
    case 'move': return '📍'
    case 'trait': return '📋'
    case 'scene': return '◈'
    default:    return '·'
  }
}
</script>

<style scoped>
.toast-bar {
  position: fixed;
  z-index: 1000;
  bottom: 80px;
  right: 12px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  max-width: 260px;
  pointer-events: none;
}

.toast-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  border-radius: 6px;
  background: var(--bg-panel);
  border: 1px solid rgba(255,255,255,0.06);
  font-size: 12px;
  line-height: 1.3;
  color: var(--text-dim);
  cursor: pointer;
  pointer-events: auto;
  transition: background 0.15s;
  box-shadow: 0 2px 8px rgba(0,0,0,0.4);
}

.toast-item:hover {
  background: rgba(30, 30, 45, 0.95);
  color: var(--text);
}

.toast-icon {
  flex-shrink: 0;
  font-size: 13px;
  opacity: 0.6;
}

.toast-msg {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* type accents — subtle left-border via padding trick */
.toast-dice  { border-left: 2px solid var(--accent); }
.toast-roll  { border-left: 2px solid #e8a840; }
.toast-move  { border-left: 2px solid var(--success); }
.toast-trait { border-left: 2px solid #a860c8; }
.toast-scene { border-left: 2px solid #40c8c8; }
.toast-info  { border-left: 2px solid rgba(255,255,255,0.15); }

/* TransitionGroup animations */
.toast-enter-active {
  transition: all 0.3s ease-out;
}
.toast-leave-active {
  transition: all 0.4s ease-in;
}
.toast-enter-from {
  opacity: 0;
  transform: translateX(40px);
}
.toast-leave-to {
  opacity: 0;
  transform: translateY(-8px);
}
</style>
