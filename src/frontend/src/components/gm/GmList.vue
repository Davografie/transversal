<template>
  <div class="gml-root">
    <div v-if="loading" class="loading">Loading…</div>
    <div v-else-if="items.length === 0" class="empty">{{ emptyText }}</div>
    <div v-else class="gml-list" :style="maxHeight ? { maxHeight, overflowY: 'auto' } : null">
      <GmListItem
        v-for="(item, i) in items"
        :key="itemKey && item[itemKey] != null ? item[itemKey] : i"
        :data-gml-idx="i"
        :class="rowClass(item)"
        :state="rowState(item)"
        :selected="isSelected(item)"
        :draggable="reorderable"
        :drag-handle="dragHandle"
        :dragging="source === i"
        :drag-over="over === i"
        @click="onRowClick(item, i)"
        @touchstart="touchStart($event, i)"
        @dragstart="dragStart($event, i)"
        @dragover="dragOver"
        @dragleave="dragLeave"
        @drop="drop"
        @dragend="dragEnd"
      >
        <span v-if="selectable" class="gml-pick" :class="{ selected: isSelected(item) }">
          {{ isSelected(item) ? '✓' : '+' }}
        </span>
        <slot name="item" :item="item" :index="i" :selected="isSelected(item)" />
      </GmListItem>
    </div>
  </div>
</template>

<script setup>
import GmListItem from './GmListItem.vue'
import { useDragDrop } from '@/composables/useDragDrop.js'

// Generic controlled list for the GM panels. Owns the row loop, selection
// highlight, optional drag-reorder (mouse + touch long-press, via useDragDrop),
// and the empty/loading states. The parent supplies already-filtered `items`
// and renders row content via the #item slot; it reacts to `click`
// (open/toggle) and `reorder` (apply + persist the new order). Search/filtering
// stays in the parent for now.
const props = defineProps({
  items: { type: Array, default: () => [] },
  itemKey: { type: String, default: 'id' },
  selectedIds: { type: Array, default: () => [] },
  reorderable: { type: Boolean, default: false },
  // When reorderable && dragHandle, only the ⠿ handle is draggable (for rows
  // that contain form inputs where whole-row drag would break text selection).
  dragHandle: { type: Boolean, default: false },
  loading: { type: Boolean, default: false },
  emptyText: { type: String, default: 'Nothing here' },
  // When selectable, row clicks toggle selection (emitting `toggle`) instead
  // of `click`; the row renders a ✓/+ pick affordance.
  selectable: { type: Boolean, default: false },
  // Optional max-height for a scrollable list (e.g. '240px').
  maxHeight: { type: String, default: '' },
  // Optional per-row class function, e.g. to flash a row after an update.
  rowClass: { type: Function, default: () => '' },
  // Optional per-row semantic state function, e.g. (item) => 'active'.
  // Values map to `.gml-item.is-<state>` (active/disabled/warning/danger/success/muted).
  rowState: { type: Function, default: () => '' },
})

const emit = defineEmits(['click', 'reorder', 'toggle'])

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

const { source, over, touchStart, dragStart, dragOver, dragLeave, drop, dragEnd } = useDragDrop({
  resolveTarget: (el) => {
    const row = el && el.closest ? el.closest('.gml-item') : null
    return row ? Number(row.dataset.gmlIdx) : null
  },
  onCommit: ({ from, to }) => {
    if (from === to) return
    // A drop is a drag gesture, not a click — swallow the click that follows.
    suppressNextClick = true
    setTimeout(() => { suppressNextClick = false }, 120)
    emit('reorder', from, to)
  },
  ghostSource: (el) => (el && el.closest ? el.closest('.gml-item') : el),
})
</script>

<style scoped>
.gml-root { display: flex; flex-direction: column; gap: 3px; }
.gml-list { display: flex; flex-direction: column; gap: 3px; }
.gml-pick { font-weight: 700; font-size: 12px; width: 16px; text-align: center; flex-shrink: 0; color: var(--text-dim); }
.gml-pick.selected { color: var(--success); }
</style>
