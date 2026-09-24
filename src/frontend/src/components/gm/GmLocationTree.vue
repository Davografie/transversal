<template>
  <TransitionGroup name="tree">
    <div
      v-for="node in flatTree"
      :key="node.kind + '-' + node.id"
      class="entity-row tree-row"
      :class="{ selected: node.id === selectedId, occupant: node.kind === 'occupant', location: node.kind === 'location', more: node.kind === 'more', add: node.kind === 'add', 'drag-over': over && over.id === node.id, 'pulse-reject': node.id === rejectedId }"
      :style="{ paddingLeft: (12 + node.depth * 20) + 'px' }"
      :data-node-id="node.id"
      :data-node-kind="node.kind"
      :data-node-universe="node.universe || ''"
      @dragover.prevent="dragOver"
      @dragleave="dragLeave"
      @drop.prevent="drop"
      @click="onClick(node)"
      @touchstart="onRowTouchStart($event, node)"
    >
      <template v-if="node.kind === 'add'">
        <span class="tree-toggle add"></span>
        <span class="entity-name add-name">＋ {{ node.name }}</span>
      </template>
      <template v-else-if="node.kind === 'more'">
        <span class="tree-toggle more"></span>
        <span class="entity-name more-name" :title="`Show the other ${node.count} children of this level`">⋯ {{ node.name }}</span>
      </template>
      <template v-else>
      <!-- Three states. `partial` is the reveal a filter or the focus chain puts
           on screen by itself — some of the level's content, not all of it and not
           none — drawn as an *outline* of the same triangle: same shape (the
           children are below), different weight. The row names the state to move
           to, because a level can be open by default while `expandedNodes[id]` is
           still undefined, so one press has to collapse it. -->
      <span
        v-if="node.hasChildren"
        class="tree-toggle"
        :class="'reveal-' + node.reveal"
        :title="TOGGLE_TITLE[node.reveal]"
        @click.stop="$emit('toggle-expand', node.id, node.reveal !== 'expanded')"
      >{{ REVEAL_GLYPH[node.reveal] }}</span>
      <span v-else class="tree-toggle" :class="{ leaf: node.kind === 'location', occupant: node.kind === 'occupant', universe: node.kind === 'universe' }"></span>
      <span v-if="node.kind === 'universe'" class="entity-type-badge type-UNIVERSE">UNI</span>
      <span v-else-if="node.kind === 'location'" class="entity-type-badge type-LOCATION">LOC</span>
      <span v-else class="entity-type-badge" :class="'type-' + node.entityType">{{ shortType(node.entityType) }}</span>
      <span class="entity-name">{{ node.name }}</span>
      <!-- Drafts are not occupant-only: 30 locations, 6 factions and a universe
           are unpublished too, and that flag is what the filter narrows on. -->
      <span v-if="node.unpublished" class="draft-badge" title="Unpublished — GM-only">draft</span>
      <span
        class="tree-drag-handle"
        :class="{ inactive: !isDraggable(node) }"
        :draggable="isDraggable(node)"
        title="Drag to move"
        @click.stop
        @touchstart.stop="onHandleTouchStart($event, node)"
        @dragstart="onHandleDragStart($event, node)"
        @dragend="dragEnd"
      >⠿</span>
      </template>
    </div>
  </TransitionGroup>
</template>

<script setup>
import { useDragDrop } from '@/composables/useDragDrop.js'

const props = defineProps({
  flatTree: { type: Array, default: () => [] },
  expandedIds: { type: Object, default: () => ({}) },
  selectedId: { type: String, default: '' },
  rejectedId: { type: String, default: '' },
})

const emit = defineEmits(['select-universe', 'select-location', 'select-occupant', 'toggle-expand', 'move-entity', 'select-more', 'add-entity'])

// What the chevron shows for each of the three reveal states, and what pressing
// it will do. `partial` is the one worth a tooltip: it is not a state the GM set,
// it is what the filter or the focus chain left on screen.
const REVEAL_GLYPH = { collapsed: '▸', partial: '▿', expanded: '▾' }
const TOGGLE_TITLE = {
  collapsed: 'Collapsed — click to show everything inside',
  partial: 'Showing matches — click to show everything inside',
  expanded: 'Expanded — click to collapse',
}

let preventNextClick = false

// Only occupants and locations can be moved (onto locations/universes).
function isDraggable(node) {
  return node.kind === 'occupant' || node.kind === 'location'
}

function shortType(t) { return t === 'CHARACTER' ? 'PC' : t === 'GMC' ? 'GMC' : t }

function srcPayload(node) {
  return { entityId: node.id, entityKind: node.kind }
}

function onClick(node) {
  if (preventNextClick) { preventNextClick = false; return }
  if (node.kind === 'add') emit('add-entity', node)
  else if (node.kind === 'more') emit('select-more', node.parentId)
  else if (node.kind === 'universe') emit('select-universe', node.id)
  else if (node.kind === 'location') emit('select-location', node.id)
  else emit('select-occupant', node.entity || { id: node.id })
}

function onRowTouchStart(e, node) {
  if (isDraggable(node)) touchStart(e, srcPayload(node))
}

function onHandleTouchStart(e, node) {
  // The ⠿ handle is a dedicated drag affordance: instant drag, no long-press.
  if (isDraggable(node)) touchStart(e, srcPayload(node), { instant: true })
}

function onHandleDragStart(e, node) {
  if (isDraggable(node)) dragStart(e, srcPayload(node))
}

const { over, touchStart, dragStart, dragOver, dragLeave, drop, dragEnd } = useDragDrop({
  resolveTarget: (el) => {
    const row = el && el.closest ? el.closest('.tree-row') : null
    if (!row) return null
    const kind = row.dataset.nodeKind
    if (kind !== 'location' && kind !== 'universe') return null
    return { id: row.dataset.nodeId, kind, universe: row.dataset.nodeUniverse || '' }
  },
  onCommit: ({ from, to }) => {
    preventNextClick = true
    setTimeout(() => { preventNextClick = false }, 100)
    emit('move-entity', {
      entityId: from.entityId,
      entityKind: from.entityKind,
      targetId: to.id,
      targetKind: to.kind,
      targetUniverse: to.universe,
    })
  },
  ghostSource: (el) => (el && el.closest ? el.closest('.tree-row') : el),
})
</script>

<style scoped>
.tree-row { cursor: pointer; transition: background 0.15s; touch-action: pan-y; }
.tree-row:hover { background: var(--overlay-6); }
.tree-row.selected { background: var(--accent-16); border: 1px solid var(--accent-dim); }
.tree-row.occupant { font-size: 12px; background: var(--overlay-2); }
.tree-row.occupant:hover { background: var(--overlay-4); }
.tree-row.location { }
.tree-row.drag-over { background: var(--accent-16); border: 1px dashed var(--accent); }
.tree-row.pulse-reject { animation: pulse-reject 0.7s ease; }
@keyframes pulse-reject {
  0%, 100% { box-shadow: none; }
  50% { box-shadow: inset 0 0 0 2px var(--danger-soft); }
}

.tree-toggle {
  font-size: 16px; width: 32px; min-height: 32px; line-height: 32px;
  color: var(--text-dim); cursor: pointer; flex-shrink: 0; text-align: center; user-select: none;
  border-radius: 6px; transition: background 0.12s, color 0.12s;
}
/* The partial reveal gets the accent tone. NOT `--accent-dim`: that one is a
   *background* tint (`background:`/`border:` everywhere it is used) and light
   theme flips it to a pale `#b9d3ec`, which as text on the light panel was
   invisible. `--accent` is the accent *foreground* (see `.ee-var`) and reads in
   both themes. Declared before `:hover` so the hover colour still wins — they
   have equal specificity, so source order decides. */
.tree-toggle.reveal-partial { color: var(--accent); }
.tree-toggle:hover { color: var(--text); background: var(--overlay-8); }
.tree-toggle:active { background: var(--overlay-12); }
.tree-toggle.leaf { visibility: hidden; }
.tree-toggle.occupant { font-size: 8px; width: 32px; min-height: 32px; line-height: 32px; color: var(--text-dim); }

.tree-drag-handle {
  width: 28px; min-height: 32px; line-height: 32px; margin-left: auto;
  text-align: center; flex-shrink: 0; user-select: none;
  color: var(--text-dim); cursor: grab; font-size: 15px;
  border-radius: 6px;
}
.tree-drag-handle:hover { color: var(--text); background: var(--overlay-8); }
.tree-drag-handle:active { cursor: grabbing; }
.tree-drag-handle.inactive { opacity: 0.15; cursor: default; }
.tree-drag-handle.inactive:hover { color: var(--text-dim); background: transparent; }

.entity-row { margin-bottom: 4px; }

/* "… N more" stub — collapsed siblings of a focused level. */
/* "… N more" stub — a first-class affordance (you click it to look for
   something else), not a footnote: full-contrast text, hover goes accent. */
.tree-toggle.more { cursor: default; }
.entity-name.more-name {
  font-style: normal; color: var(--text); font-size: 12px;
  cursor: pointer; border-bottom: 1px dashed var(--overlay-25);
}
.entity-row.more:hover .more-name { color: var(--accent); border-bottom-color: var(--accent); }

/* Inline "add" rows: trail their collection, quieter than real entities. */
.entity-name.add-name {
  font-style: normal; color: var(--text-dim); font-size: 11px;
  cursor: pointer; border-bottom: 1px dashed var(--overlay-18);
}
.entity-row.add:hover .add-name { color: var(--accent); border-bottom-color: var(--accent); }

.tree-enter-active, .tree-leave-active { transition: all 0.2s ease; }
.tree-enter-from, .tree-leave-to { opacity: 0; transform: translateY(-8px); }
.tree-move { transition: transform 0.2s ease; }
</style>
