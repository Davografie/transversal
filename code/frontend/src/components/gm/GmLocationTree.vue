<template>
  <TransitionGroup name="tree">
    <div
      v-for="node in flatTree"
      :key="node.kind + '-' + node.id"
      class="entity-row tree-row"
      :class="{ selected: node.id === selectedId, occupant: node.kind === 'occupant', 'drag-over': dragOverId === node.id }"
      :style="{ paddingLeft: (12 + node.depth * 20) + 'px' }"
      :data-node-id="node.id"
      :data-node-kind="node.kind"
      :draggable="node.kind === 'occupant'"
      @dragstart="onDragStart($event, node)"
      @dragover.prevent="onDragOver($event, node)"
      @dragleave="onDragLeave(node)"
      @drop.prevent="onDrop($event, node)"
      @touchstart="onTouchStart($event, node)"
      @touchmove="onTouchMove"
      @touchend="onTouchEnd"
      @click="onClick(node)"
    >
      <span v-if="node.hasChildren" class="tree-toggle" @click.stop="$emit('toggle-expand', node.id)">
        {{ expandedIds[node.id] ?? (node.depth === 0) ? '▾' : '▸' }}
      </span>
      <span v-else class="tree-toggle" :class="{ leaf: node.kind === 'location', occupant: node.kind === 'occupant' }"></span>
      <span v-if="node.kind === 'location'" class="entity-type-badge type-LOCATION">LOC</span>
      <span v-else class="entity-type-badge" :class="'type-' + node.entityType">{{ shortType(node.entityType) }}</span>
      <span class="entity-name">{{ node.name }}</span>
      <span class="entity-universe" v-if="node.kind === 'location' && node.universe !== universe">{{ node.universe }}</span>
    </div>
  </TransitionGroup>
</template>

<script setup>
import { ref } from 'vue'

const props = defineProps({
  flatTree: { type: Array, default: () => [] },
  expandedIds: { type: Object, default: () => ({}) },
  selectedId: { type: String, default: '' },
  universe: { type: String, default: 'earth' },
})

const emit = defineEmits(['select-location', 'select-occupant', 'toggle-expand', 'move-entity'])

const dragOverId = ref(null)
const touchDrag = ref(null)
const preventNextClick = ref(false)

function shortType(t) { return t === 'CHARACTER' ? 'PC' : t === 'GMC' ? 'GMC' : t }

function onClick(node) {
  if (preventNextClick.value) { preventNextClick.value = false; return }
  if (node.kind === 'location') emit('select-location', node.id)
  else emit('select-occupant', node.entity || { id: node.id })
}

// ── HTML5 Drag ──
function onDragStart(e, node) {
  if (node.kind !== 'occupant') return
  e.dataTransfer.effectAllowed = 'move'
  e.dataTransfer.setData('text/plain', node.id)
}
function onDragOver(e, node) { if (node.kind === 'location') dragOverId.value = node.id }
function onDragLeave(node) { if (dragOverId.value === node.id) dragOverId.value = null }
function onDrop(e, node) {
  dragOverId.value = null
  if (node.kind !== 'location') return
  const entityId = e.dataTransfer.getData('text/plain')
  if (entityId) emit('move-entity', { entityId, targetLocationId: node.id })
}

// ── Touch Drag ──
function onTouchStart(e, node) {
  if (node.kind !== 'occupant') return
  const touch = e.touches[0]; const el = e.currentTarget
  touchDrag.value = { entityId: node.id, el, sx: touch.clientX, sy: touch.clientY, engaged: false, ghost: null }
  touchDrag.value._timer = setTimeout(() => engageTouchDrag(touch), 400)
}
function engageTouchDrag(touch) {
  if (!touchDrag.value) return
  touchDrag.value.engaged = true
  const el = touchDrag.value.el; const ghost = el.cloneNode(true)
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
  dragOverId.value = row && row.dataset.nodeKind === 'location' ? row.dataset.nodeId : null
}
function onTouchEnd(e) {
  if (!touchDrag.value) return
  clearTimeout(touchDrag.value._timer)
  if (touchDrag.value.engaged) {
    preventNextClick.value = true; setTimeout(() => { preventNextClick.value = false }, 100)
    const t = e.changedTouches[0]; const target = document.elementFromPoint(t.clientX, t.clientY)
    const row = target?.closest('.tree-row')
    const nodeId = row && row.dataset.nodeKind === 'location' ? row.dataset.nodeId : null
    if (nodeId) emit('move-entity', { entityId: touchDrag.value.entityId, targetLocationId: nodeId })
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
.tree-row.occupant { font-size: 12px; background: rgba(255,255,255,0.02); cursor: grab; touch-action: none; }
.tree-row.occupant:hover { background: rgba(255,255,255,0.05); }
.tree-row.occupant:active { cursor: grabbing; }
.tree-row.drag-over { background: rgba(64,136,212,0.15); border: 1px dashed var(--accent); }

.tree-toggle {
  font-size: 14px; width: 24px; min-height: 24px; line-height: 24px;
  color: var(--text-dim); cursor: pointer; flex-shrink: 0; text-align: center; user-select: none;
}
.tree-toggle:hover { color: var(--text); }
.tree-toggle.leaf { visibility: hidden; }
.tree-toggle.occupant { font-size: 8px; color: var(--text-dim); }

.entity-row {
  display: flex; align-items: center; gap: 6px;
  padding: 8px 10px; margin-bottom: 4px;
  background: rgba(255,255,255,0.04); border-radius: 6px;
  font-size: 13px;
}
.entity-type-badge {
  font-size: 9px; text-transform: uppercase; padding: 1px 6px; border-radius: 3px; font-weight: 600;
}
.type-CHARACTER, .type-PC { background: #4088d4; color: #fff; }
.type-LOCATION { background: #40b860; color: #0a0a0f; }
.type-GMC { background: #e88830; color: #0a0a0f; }
.type-ASSET { background: #888; color: #fff; }
.entity-name { flex: 1; font-weight: 500; }
.entity-universe { font-size: 10px; color: var(--text-dim); }

.tree-enter-active, .tree-leave-active { transition: all 0.2s ease; }
.tree-enter-from, .tree-leave-to { opacity: 0; transform: translateY(-8px); }
.tree-move { transition: transform 0.2s ease; }
</style>
