<template>
  <div
    class="entity-row gml-item"
    :class="[stateClass, { selected, dragging, 'drag-over': dragOver }]"
    :draggable="draggable && !dragHandle"
    @click="$emit('click', $event)"
    @dragstart="$emit('dragstart', $event)"
    @dragover.prevent="$emit('dragover', $event)"
    @dragleave="$emit('dragleave', $event)"
    @drop.prevent="$emit('drop', $event)"
    @dragend="$emit('dragend', $event)"
    @touchstart="onTouchStart"
  >
    <slot />
    <span
      v-if="draggable && dragHandle"
      class="gml-drag-handle"
      draggable="true"
      title="Drag to reorder"
      @touchstart.stop="onHandleTouchStart"
    >⠿</span>
  </div>
</template>

<script setup>
import { computed } from 'vue'

// Shared list-row primitive. Renders the global `.entity-row` shell plus the
// selection/drag/state modifiers that every GM list row needs. Content is
// slotted; selection, drag, and reorder are owned by GmList (or a custom
// parent) via the forwarded events — including `touchstart`, so a row (or, in
// `dragHandle` mode, only the ⠿ handle) can long-press-and-drag on touch.
const props = defineProps({
  selected: { type: Boolean, default: false },
  draggable: { type: Boolean, default: false },
  dragHandle: { type: Boolean, default: false },
  dragging: { type: Boolean, default: false },
  dragOver: { type: Boolean, default: false },
  // Semantic row state for styling: '', 'active', 'disabled', 'warning',
  // 'danger', 'success', 'muted'. Maps to `.gml-item.is-<state>`.
  state: { type: String, default: '' },
})

const emit = defineEmits(['click', 'dragstart', 'dragover', 'dragleave', 'drop', 'dragend', 'touchstart', 'handle-touchstart'])

const stateClass = computed(() => props.state ? `is-${props.state}` : '')

// Whole-row touch drag only when the row itself is the drag source
// (i.e. not in `dragHandle` mode, where the handle owns the gesture).
function onTouchStart(e) {
  if (props.draggable && !props.dragHandle) emit('touchstart', e)
}

function onHandleTouchStart(e) {
  // The ⠿ handle is a dedicated drag affordance: instant drag, no long-press.
  if (props.draggable) emit('handle-touchstart', e)
}
</script>

<style scoped>
.gml-item { user-select: none; }
.gml-item.dragging { opacity: 0.4; }
.gml-item.drag-over {
  background: rgba(64, 136, 212, 0.12);
  box-shadow: 0 0 0 1px var(--accent-dim) inset;
  transform: scale(1.02);
}
.gml-item.editing { background: rgba(64, 136, 212, 0.12); border: 1px solid var(--accent-dim); }

/* Semantic row states */
.gml-item.is-active {
  background: rgba(64, 136, 212, 0.12);
  box-shadow: 0 0 0 1px var(--accent) inset;
}
.gml-item.is-disabled {
  opacity: 0.45;
  pointer-events: none;
}
.gml-item.is-warning {
  background: rgba(232, 136, 48, 0.12);
  box-shadow: 0 0 0 1px var(--warn) inset;
}
.gml-item.is-danger {
  background: rgba(212, 64, 64, 0.12);
  box-shadow: 0 0 0 1px var(--danger) inset;
}
.gml-item.is-success {
  background: rgba(64, 184, 96, 0.12);
  box-shadow: 0 0 0 1px var(--success) inset;
}
.gml-item.is-muted {
  opacity: 0.6;
}

.gml-drag-handle { cursor: grab; color: var(--text-dim); font-size: 13px; flex-shrink: 0; user-select: none; margin-left: auto; }
</style>
