<template>
  <div
    class="entity-row gml-item"
    :class="{ selected, dragging, 'drag-over': dragOver }"
    :draggable="draggable && !dragHandle"
    @click="$emit('click', $event)"
    @dragstart="$emit('dragstart', $event)"
    @dragover.prevent="$emit('dragover', $event)"
    @dragleave="$emit('dragleave', $event)"
    @drop.prevent="$emit('drop', $event)"
    @dragend="$emit('dragend', $event)"
  >
    <span v-if="draggable && dragHandle" class="gml-drag-handle" draggable="true" title="Drag to reorder">⠿</span>
    <slot />
  </div>
</template>

<script setup>
// Shared list-row primitive. Renders the global `.entity-row` shell plus the
// selection/drag modifiers that every GM list row needs. Content is slotted;
// selection, drag, and reorder are owned by GmList (or a custom parent).
defineProps({
  selected: { type: Boolean, default: false },
  draggable: { type: Boolean, default: false },
  dragHandle: { type: Boolean, default: false },
  dragging: { type: Boolean, default: false },
  dragOver: { type: Boolean, default: false },
})

defineEmits(['click', 'dragstart', 'dragover', 'dragleave', 'drop', 'dragend'])
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
.gml-drag-handle { cursor: grab; color: var(--text-dim); font-size: 13px; flex-shrink: 0; user-select: none; }
</style>
