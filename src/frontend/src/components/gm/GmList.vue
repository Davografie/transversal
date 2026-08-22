<template>
  <div class="gml-root">
    <div v-if="loading" class="loading">Loading…</div>
    <div v-else-if="items.length === 0" class="empty">{{ emptyText }}</div>
    <div v-else class="gml-list" :style="maxHeight ? { maxHeight, overflowY: 'auto' } : null">
      <GmListItem
        v-for="(item, i) in items"
        :key="itemKey ? item[itemKey] : i"
        :class="rowClass(item)"
        :selected="isSelected(item)"
        :draggable="reorderable"
        :dragging="dragIndex === i"
        :drag-over="dragOverIndex === i"
        @click="onRowClick(item, i)"
        @dragstart="onDragStart(i, $event)"
        @dragover="onDragOver(i)"
        @dragleave="onDragLeave"
        @drop="onDrop(i)"
        @dragend="onDragEnd"
      >
        <input
          v-if="selectable && selectStyle === 'checkbox'"
          type="checkbox"
          class="gml-check"
          :checked="isSelected(item)"
          @click.stop
          @change="emitToggle(item, i)"
        />
        <span v-else-if="selectable" class="gml-pick" :class="{ selected: isSelected(item) }">
          {{ isSelected(item) ? '✓' : '+' }}
        </span>
        <slot name="item" :item="item" :index="i" :selected="isSelected(item)" />
      </GmListItem>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import GmListItem from './GmListItem.vue'

// Generic controlled list for the GM panels. Owns the row loop, selection
// highlight, optional drag-reorder, and the empty/loading states. The parent
// supplies already-filtered `items` and renders row content via the #item slot;
// it reacts to `click` (open/toggle) and `reorder` (apply + persist the new
// order). Search/filtering stays in the parent for now.
const props = defineProps({
  items: { type: Array, default: () => [] },
  itemKey: { type: String, default: 'id' },
  selectedIds: { type: Array, default: () => [] },
  reorderable: { type: Boolean, default: false },
  loading: { type: Boolean, default: false },
  emptyText: { type: String, default: 'Nothing here' },
  // When selectable, row clicks toggle selection (emitting `toggle`) instead
  // of `click`; the row renders a checkbox or a ✓/+ pick affordance.
  selectable: { type: Boolean, default: false },
  selectStyle: { type: String, default: 'checkbox' }, // 'checkbox' | 'pick'
  // Optional max-height for a scrollable list (e.g. '240px').
  maxHeight: { type: String, default: '' },
  // Optional per-row class function, e.g. to flash a row after an update.
  rowClass: { type: Function, default: () => '' },
})

const emit = defineEmits(['click', 'reorder', 'toggle'])

const dragIndex = ref(-1)
const dragOverIndex = ref(-1)
let suppressNextClick = false

function isSelected(item) {
  const id = props.itemKey ? item[props.itemKey] : item
  return props.selectedIds.includes(id)
}

function onRowClick(item, i) {
  if (suppressNextClick) { suppressNextClick = false; return }
  if (props.selectable) emitToggle(item, i)
  else emit('click', item, i)
}

function emitToggle(item, i) {
  emit('toggle', item, i)
}

function onDragStart(i, e) {
  if (!props.reorderable) return
  dragIndex.value = i
  e.dataTransfer.effectAllowed = 'move'
  e.dataTransfer.setData('text/plain', '')
}

function onDragOver(i) {
  if (props.reorderable) dragOverIndex.value = i
}

function onDragLeave() {
  dragOverIndex.value = -1
}

function onDrop(i) {
  const from = dragIndex.value
  dragIndex.value = -1
  dragOverIndex.value = -1
  if (!props.reorderable || from < 0) return
  // A drop is a drag gesture, not a click — swallow the click that follows.
  suppressNextClick = true
  if (from !== i) emit('reorder', from, i)
}

function onDragEnd() {
  dragIndex.value = -1
  dragOverIndex.value = -1
  // Safety: clear the suppression if the browser never fires the follow-up click.
  setTimeout(() => { suppressNextClick = false }, 120)
}
</script>

<style scoped>
.gml-root { display: flex; flex-direction: column; gap: 3px; }
.gml-list { display: flex; flex-direction: column; gap: 3px; }
.gml-check { width: auto; margin: 0; flex-shrink: 0; cursor: pointer; }
.gml-pick { font-weight: 700; font-size: 12px; width: 16px; text-align: center; flex-shrink: 0; color: var(--text-dim); }
.gml-pick.selected { color: var(--success); }
</style>
