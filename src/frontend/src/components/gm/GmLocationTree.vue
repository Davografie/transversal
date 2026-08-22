<template>
  <TransitionGroup name="tree">
    <div
      v-for="node in flatTree"
      :key="node.kind + '-' + node.id"
      class="entity-row tree-row"
      :class="{ selected: node.id === selectedId, occupant: node.kind === 'occupant', location: node.kind === 'location', 'drag-over': dragOverId === node.id, 'pulse-reject': node.id === rejectedId }"
      :style="{ paddingLeft: (12 + node.depth * 20) + 'px' }"
      :data-node-id="node.id"
      :data-node-kind="node.kind"
      :data-node-universe="node.universe || ''"
      @dragover.prevent="onDragOver($event, node)"
      @dragleave="onDragLeave(node)"
      @drop.prevent="onDrop($event, node)"
      @click="onClick(node)"
    >
      <span v-if="node.hasChildren" class="tree-toggle" @click.stop="$emit('toggle-expand', node.id)">
        {{ node.expanded ? '▾' : '▸' }}
      </span>
      <span v-else class="tree-toggle" :class="{ leaf: node.kind === 'location', occupant: node.kind === 'occupant', universe: node.kind === 'universe' }"></span>
      <span
        class="tree-drag-handle"
        :class="{ inactive: !isDraggable(node) }"
        :draggable="isDraggable(node)"
        title="Drag to move"
        @click.stop
        @dragstart="onDragStart($event, node)"
        @touchstart="onTouchStart($event, node)"
        @touchmove="onTouchMove"
        @touchend="onTouchEnd"
      >⠿</span>
      <span v-if="node.kind === 'universe'" class="entity-type-badge type-UNIVERSE">UNI</span>
      <span v-else-if="node.kind === 'location'" class="entity-type-badge type-LOCATION">LOC</span>
      <span v-else class="entity-type-badge" :class="'type-' + node.entityType">{{ shortType(node.entityType) }}</span>
      <span class="entity-name">{{ node.name }}</span>
    </div>
  </TransitionGroup>
</template>

<script setup>
import { ref } from 'vue'

const props = defineProps({
  flatTree: { type: Array, default: () => [] },
  expandedIds: { type: Object, default: () => ({}) },
  selectedId: { type: String, default: '' },
  rejectedId: { type: String, default: '' },
})

const emit = defineEmits(['select-universe', 'select-location', 'select-occupant', 'toggle-expand', 'move-entity'])

const dragOverId = ref(null)
const touchDrag = ref(null)
const preventNextClick = ref(false)

// Only occupants and locations can be moved (onto locations/universes).
function isDraggable(node) {
  return node.kind === 'occupant' || node.kind === 'location'
}

function shortType(t) { return t === 'CHARACTER' ? 'PC' : t === 'GMC' ? 'GMC' : t }

function onClick(node) {
  if (preventNextClick.value) { preventNextClick.value = false; return }
  if (node.kind === 'universe') emit('select-universe', node.id)
  else if (node.kind === 'location') emit('select-location', node.id)
  else emit('select-occupant', node.entity || { id: node.id })
}

// ── HTML5 Drag (mouse) — drag starts from the 6-dots handle ──
function onDragStart(e, node) {
  if (!isDraggable(node)) return
  e.dataTransfer.effectAllowed = 'move'
  e.dataTransfer.setData('text/plain', JSON.stringify({ id: node.id, kind: node.kind }))
}
function onDragOver(e, node) {
  if (node.kind === 'location' || node.kind === 'universe') dragOverId.value = node.id
}
function onDragLeave(node) { if (dragOverId.value === node.id) dragOverId.value = null }
function onDrop(e, node) {
  dragOverId.value = null
  if (node.kind !== 'location' && node.kind !== 'universe') return
  const raw = e.dataTransfer.getData('text/plain')
  if (!raw) return
  let payload
  try { payload = JSON.parse(raw) } catch { payload = { id: raw, kind: 'occupant' } }
  emit('move-entity', { entityId: payload.id, entityKind: payload.kind, targetId: node.id, targetKind: node.kind, targetUniverse: node.universe || '' })
}

// ── Touch Drag — long-press the handle, then drag to a drop target ──
function onTouchStart(e, node) {
  if (!isDraggable(node)) return
  const touch = e.touches[0]
  // The handle is the touch target; drag the whole row as the ghost.
  const rowEl = e.currentTarget.closest('.tree-row')
  touchDrag.value = { entityId: node.id, entityKind: node.kind, el: rowEl, sx: touch.clientX, sy: touch.clientY, engaged: false, ghost: null }
  touchDrag.value._timer = setTimeout(() => engageTouchDrag(touch), 400)
}
function engageTouchDrag(touch) {
  if (!touchDrag.value) return
  touchDrag.value.engaged = true
  const el = touchDrag.value.el
  const ghost = el.cloneNode(true)
  ghost.style.cssText = `position:fixed;left:${touch.clientX - 20}px;top:${touch.clientY - 14}px;z-index:100;pointer-events:none;opacity:0.8;width:${el.offsetWidth}px`
  document.body.appendChild(ghost)
  touchDrag.value.ghost = ghost
}
function onTouchMove(e) {
  if (!touchDrag.value || !touchDrag.value.engaged) {
    if (touchDrag.value && !touchDrag.value.engaged) {
      const t = e.touches[0]
      if (Math.abs(t.clientX - touchDrag.value.sx) > 5 || Math.abs(t.clientY - touchDrag.value.sy) > 5) cancelTouchDrag()
    }
    return
  }
  const t = e.touches[0]; const ghost = touchDrag.value.ghost
  if (ghost) { ghost.style.left = (t.clientX - 20) + 'px'; ghost.style.top = (t.clientY - 14) + 'px' }
  const target = document.elementFromPoint(t.clientX, t.clientY)
  const row = target?.closest('.tree-row')
  const kind = row?.dataset.nodeKind
  dragOverId.value = (kind === 'location' || kind === 'universe') ? row.dataset.nodeId : null
}
function onTouchEnd(e) {
  if (!touchDrag.value) return
  clearTimeout(touchDrag.value._timer)
  if (touchDrag.value.engaged) {
    preventNextClick.value = true; setTimeout(() => { preventNextClick.value = false }, 100)
    const t = e.changedTouches[0]; const target = document.elementFromPoint(t.clientX, t.clientY)
    const row = target?.closest('.tree-row')
    const kind = row?.dataset.nodeKind
    const nodeId = (kind === 'location' || kind === 'universe') ? row.dataset.nodeId : null
    if (nodeId) emit('move-entity', { entityId: touchDrag.value.entityId, entityKind: touchDrag.value.entityKind, targetId: nodeId, targetKind: kind, targetUniverse: row?.dataset.nodeUniverse || '' })
    if (touchDrag.value.ghost) touchDrag.value.ghost.remove()
  }
  dragOverId.value = null; touchDrag.value = null
}
function cancelTouchDrag() {
  if (!touchDrag.value) return
  clearTimeout(touchDrag.value._timer)
  if (touchDrag.value.ghost) touchDrag.value.ghost.remove()
  dragOverId.value = null; touchDrag.value = null
}
</script>

<style scoped>
.tree-row { cursor: pointer; transition: background 0.15s; }
.tree-row:hover { background: rgba(255,255,255,0.06); }
.tree-row.selected { background: rgba(64,136,212,0.15); border: 1px solid var(--accent-dim); }
.tree-row.occupant { font-size: 12px; background: rgba(255,255,255,0.02); }
.tree-row.occupant:hover { background: rgba(255,255,255,0.05); }
.tree-row.location { }
.tree-row.drag-over { background: rgba(64,136,212,0.15); border: 1px dashed var(--accent); }
.tree-row.pulse-reject { animation: pulse-reject 0.7s ease; }
@keyframes pulse-reject {
  0%, 100% { box-shadow: none; }
  50% { box-shadow: inset 0 0 0 2px #e06060; }
}

.tree-toggle {
  font-size: 16px; width: 32px; min-height: 32px; line-height: 32px;
  color: var(--text-dim); cursor: pointer; flex-shrink: 0; text-align: center; user-select: none;
  border-radius: 6px; transition: background 0.12s, color 0.12s;
}
.tree-toggle:hover { color: var(--text); background: rgba(255,255,255,0.08); }
.tree-toggle:active { background: rgba(255,255,255,0.12); }
.tree-toggle.leaf { visibility: hidden; }
.tree-toggle.occupant { font-size: 8px; width: 32px; min-height: 32px; line-height: 32px; color: var(--text-dim); }

.tree-drag-handle {
  width: 28px; min-height: 32px; line-height: 32px;
  text-align: center; flex-shrink: 0; user-select: none;
  color: var(--text-dim); cursor: grab; font-size: 15px;
  touch-action: none; /* the handle is for dragging, not scrolling */
  border-radius: 6px;
}
.tree-drag-handle:hover { color: var(--text); background: rgba(255,255,255,0.08); }
.tree-drag-handle:active { cursor: grabbing; }
.tree-drag-handle.inactive { opacity: 0.15; cursor: default; }
.tree-drag-handle.inactive:hover { color: var(--text-dim); background: transparent; }

.entity-row { margin-bottom: 4px; }

.tree-enter-active, .tree-leave-active { transition: all 0.2s ease; }
.tree-enter-from, .tree-leave-to { opacity: 0; transform: translateY(-8px); }
.tree-move { transition: transform 0.2s ease; }
</style>
