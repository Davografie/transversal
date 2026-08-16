<template>
  <div class="relational-canvas" :class="{ fullscreen }">
    <div class="canvas-toolbar">
      <div class="canvas-title">
        {{ title || 'Relational Canvas' }}
        <span v-if="lifePathFactions.length" class="canvas-faction-badges">
          <span v-for="f in lifePathFactions" :key="f" class="canvas-faction-badge">{{ f }}</span>
        </span>
      </div>
      <div class="canvas-controls">
        <select
          v-if="mode === 'location'"
          v-model="selectedFaction"
          class="faction-select"
          @change="onFactionChange"
        >
          <option value="">— Filter by faction —</option>
          <option v-for="f in factions" :key="f.id" :value="f.id">{{ f.name }}</option>
        </select>
        <button
          v-if="mode === 'location'"
          class="tool-btn"
          :title="layoutOrientation === 'horizontal' ? 'Switch to vertical layout' : 'Pivot to horizontal layout'"
          @click="toggleLayoutOrientation"
        >⇄</button>
        <button v-if="mode === 'faction' || mode === 'gmc-web'" class="tool-btn" @click="backToLocation">← Location</button>
        <button v-if="mode === 'life-path'" class="tool-btn" title="Reset layout" @click="resetLayout">↺</button>
        <button v-if="!fullscreen" class="tool-btn" title="Open fullscreen" @click="openFull">⛶</button>
        <button class="tool-btn" @click="fitView">Fit</button>
        <button v-if="fullscreen" class="tool-btn close" @click="emit('close-full')">✕</button>
      </div>
    </div>
    <div v-if="mode === 'life-path'" class="canvas-hint">Roll tables linked by next_step effects · dashed orange edges loop back · click ✎ to open a table</div>
    <div v-else class="canvas-hint">Drag → to ← to create a transversal link · click a transversal edge to toggle · ⊕/⊖ collapse subtree · hover an occupant to highlight relations</div>

    <div v-if="loading" class="canvas-status">Loading…</div>
    <div v-else-if="error" class="canvas-status error">{{ error }}</div>

    <VueFlow
      v-else
      ref="flowRef"
      :nodes="displayNodes"
      :edges="edges"
      :node-types="nodeTypes"
      :edge-types="edgeTypes"
      :min-zoom="0.15"
      :max-zoom="2.5"
      fit-view-on-init
      class="canvas-flow"
      @connect="onConnect"
      @connect-start="onConnectStart"
      @connect-end="onConnectEnd"
      @node-drag-stop="onNodeDragStop"
      @edge-click="onEdgeClick"
      @pane-click="clearSelection"
    >
      <Background :gap="24" />
      <Controls v-if="fullscreen" />
      <MiniMap
        v-if="fullscreen"
        :width="minimapSize.width"
        :height="minimapSize.height"
        :node-color="nodeColorFn"
        node-stroke-color="#0a0a0f"
        :node-stroke-width="1"
        mask-color="rgba(10, 10, 15, 0.10)"
        mask-stroke-color="#0a0a0f"
      />
    </VueFlow>

    <div v-if="linkMenu" class="link-menu" :style="{ left: linkMenu.x + 'px', top: linkMenu.y + 'px' }">
      <div class="link-menu-title">Link to roll table</div>
      <GmRollTablePicker
        model-value=""
        placeholder="Search roll table…"
        :exclude-ids="[linkMenu.sourceTableId]"
        @update:model-value="onLinkPicked"
      />
      <button class="link-menu-close" title="Cancel" @click="linkMenu = null">✕</button>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { VueFlow } from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'
import { MiniMap } from '@vue-flow/minimap'
import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'
import '@vue-flow/controls/dist/style.css'
import '@vue-flow/minimap/dist/style.css'

import { useCanvas } from '@/composables/useCanvas.js'
import { usePanelBus } from '@/composables/usePanelBus.js'
import { usePanel } from '@/composables/usePanel.js'
import LocationNode from '@/components/canvas/nodes/LocationNode.vue'
import OccupantNode from '@/components/canvas/nodes/OccupantNode.vue'
import RollTableNode from '@/components/canvas/nodes/RollTableNode.vue'
import BundlerNode from '@/components/canvas/nodes/BundlerNode.vue'
import UniverseNode from '@/components/canvas/nodes/UniverseNode.vue'
import GradientEdge from '@/components/canvas/edges/GradientEdge.vue'
import LifePathEdge from '@/components/canvas/edges/LifePathEdge.vue'
import GmRollTableDetailPanel from '@/components/gm/GmRollTableDetailPanel.vue'
import GmRollTablePicker from '@/components/gm/GmRollTablePicker.vue'

const props = defineProps({
  locationId: { type: String, default: '' },
  initialFactionId: { type: String, default: '' },
  initialGmcId: { type: String, default: '' },
  initialLifePath: { type: Object, default: null },
  initialUniverse: { type: String, default: '' },
  fullscreen: { type: Boolean, default: false },
})

const emit = defineEmits(['close-full'])

const bus = usePanelBus()
const panel = usePanel()

const canvas = useCanvas()
const { mode, title, loading, error, factions, layoutOrientation, toggleLayoutOrientation, setHighlightedOccupant, setFactionFilter, selectEntity, clearSelection } = canvas
const nodes = canvas.nodes
const edges = canvas.edges

function nodeColorFn(node) {
  switch (node.type) {
    case 'location': return '#4ea1ff'
    case 'universe': return '#a86bf0'
    case 'occupant': return '#e88830'
    case 'rolltable': return '#40b860'
    default: return '#c0c0d0'
  }
}

const minimapSize = computed(() => {
  const list = nodes.value || []
  if (!list.length) return { width: 180, height: 120 }
  let minX = Infinity
  let minY = Infinity
  let maxX = -Infinity
  let maxY = -Infinity
  for (const n of list) {
    const w = n.type === 'universe' ? 160 : n.type === 'location' ? 220 : 180
    const occ = n.data?.occupants?.length || 0
    const rows = Math.ceil(occ / 3)
    const h = 60 + (occ ? 8 + rows * 32 + (rows - 1) * 6 : 0)
    minX = Math.min(minX, n.position.x)
    minY = Math.min(minY, n.position.y)
    maxX = Math.max(maxX, n.position.x + w)
    maxY = Math.max(maxY, n.position.y + h)
  }
  const bw = Math.max(1, maxX - minX)
  const bh = Math.max(1, maxY - minY)
  const maxDim = 180
  const scale = Math.min(maxDim / bw, maxDim / bh)
  return { width: Math.max(60, Math.round(bw * scale)), height: Math.max(60, Math.round(bh * scale)) }
})

const selectedFaction = ref('')
const pendingLink = ref(null)
const linkMenu = ref(null)
const lifePathFactions = computed(() => {
  if (mode.value !== 'life-path') return []
  const ids = props.initialLifePath?.factionIds || []
  const byId = new Map(factions.value.map((f) => [f.id, f.name]))
  return ids.map((id) => byId.get(id) || id).filter(Boolean)
})
const flowRef = ref(null)

function fitView() {
  flowRef.value?.fitView?.()
}

const nodeTypes = { location: LocationNode, occupant: OccupantNode, rolltable: RollTableNode, bundler: BundlerNode, universe: UniverseNode }
const edgeTypes = { gradient: GradientEdge, lifepath: LifePathEdge }

const displayNodes = computed(() =>
  nodes.value.map((n) => ({
    ...n,
    data: {
      ...n.data,
      onExpand: (id) => canvas.expandLocation(id),
      onCollapse: (id) => canvas.collapseLocation(id),
      onSelect: (id, ev) => selectEntity('location', id, ev?.shiftKey),
      onSelectOccupant: (id, ev) => selectEntity('occupant', id, ev?.shiftKey),
      onInspectOccupant: (id) => bus.emit('canvas:inspect', id),
      onToggleExpand: (id) => canvas.toggleUniverseExpand(id),
      onOccupantHover: (id) => setHighlightedOccupant(id),
      onOccupantLeave: () => setHighlightedOccupant(null),
      onToggleRelations: (id) => canvas.toggleRelations(id),
      onShowFaction: (id) => canvas.showFaction(id),
      onInspect: (id) => bus.emit('canvas:inspect', id),
      onOpenFull: (id) => bus.emit('canvas:open-full', { mode: 'location', entityId: id, scope: 'focus' }),
      onOpenTable: (id) => openTable(id),
    },
  })),
)

function onFactionChange() {
  setFactionFilter(selectedFaction.value)
}

function openTable(tableId) {
  const node = nodes.value.find((n) => n.id === `rt:${tableId}`)
  const name = node?.data?.name || tableId
  panel.open({ component: GmRollTableDetailPanel, title: name, props: { tableId, name } })
}

function openFull() {
  const payload = { mode: mode.value, entityId: canvas.focusId.value }
  if (mode.value === 'location') payload.scope = 'focus'
  if (mode.value === 'life-path') payload.lifePath = props.initialLifePath
  bus.emit('canvas:open-full', payload)
  panel.close()
}

async function onConnect(connection) {
  pendingLink.value = null
  if (!connection.source || !connection.target || connection.source === connection.target) return
  const fromNode = nodes.value.find((n) => n.id === connection.source)
  const toNode = nodes.value.find((n) => n.id === connection.target)
  if (!fromNode || !toNode) return

  // Location → location transversal links (lateral handles only).
  if (fromNode.type === 'location' && toNode.type === 'location') {
    if (connection.sourceHandle !== 'right' || connection.targetHandle !== 'left') return
    await canvas.createTransversal(fromNode.data.entityId, toNode.data.entityId)
    return
  }

  // Occupant → occupant directed relationships.
  if (fromNode.type === 'occupant' && toNode.type === 'occupant') {
    if (!connection.sourceHandle?.startsWith('source-') || !connection.targetHandle?.startsWith('target-')) return
    await canvas.createRelation(fromNode.data.entityId, toNode.data.entityId)
  }
}

function onEdgeClick({ edge }) {
  canvas.toggleTransversalEdge(edge)
}

function onConnectStart({ nodeId, handleId }) {
  if (handleId?.startsWith('row-')) {
    const sourceNode = nodes.value.find((n) => n.id === nodeId)
    pendingLink.value = {
      sourceTableId: sourceNode?.data?.entityId,
      rowIndex: parseInt(handleId.slice(4), 10),
    }
  } else {
    pendingLink.value = null
  }
}

function onConnectEnd(event) {
  const link = pendingLink.value
  pendingLink.value = null
  if (!link?.sourceTableId) return
  const touch = event?.changedTouches?.[0]
  linkMenu.value = {
    ...link,
    x: event?.clientX ?? touch?.clientX ?? 0,
    y: event?.clientY ?? touch?.clientY ?? 0,
  }
}

async function onLinkPicked(tableId) {
  if (!linkMenu.value || !tableId) return
  const { sourceTableId, rowIndex } = linkMenu.value
  linkMenu.value = null
  await canvas.linkRollTable(sourceTableId, rowIndex, tableId)
}

function onNodeDragStop({ node }) {
  if (node) canvas.updateNodePosition(node.id, node.position)
}

function backToLocation() {
  if (props.locationId) canvas.loadLocation(props.locationId)
}

async function resetLayout() {
  if (mode.value !== 'life-path' || !props.initialLifePath) return
  await canvas.clearLifePathPositions(props.initialLifePath.id)
  await canvas.loadLifePath(props.initialLifePath)
}

onMounted(async () => {
  canvas.loadFactions()
  if (props.initialFactionId) {
    await canvas.loadFaction(props.initialFactionId)
  } else if (props.initialGmcId) {
    await canvas.loadGmcWeb(props.initialGmcId)
  } else if (props.initialLifePath) {
    await canvas.loadLifePath(props.initialLifePath)
  } else if (props.initialUniverse) {
    await canvas.loadLocationTree(props.initialUniverse)
  } else if (props.locationId) {
    await canvas.loadLocation(props.locationId)
  }
})
</script>

<style scoped>
.relational-canvas {
  display: flex; flex-direction: column; height: 100%; min-height: 320px;
  background: #0a0a0f; color: var(--text);
}
.relational-canvas.fullscreen {
  position: fixed; inset: 0; z-index: 20; height: 100vh; min-height: 0;
}
.canvas-toolbar {
  display: flex; align-items: center; justify-content: space-between; gap: 8px;
  padding: 6px 8px; background: rgba(20, 20, 35, 0.9);
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
}
.canvas-title { font-size: 13px; font-weight: 700; }
.canvas-faction-badges { display: inline-flex; gap: 4px; margin-left: 6px; vertical-align: middle; }
.canvas-faction-badge {
  font-size: 9px; font-weight: 500; padding: 1px 6px; border-radius: 3px;
  background: rgba(232, 136, 48, 0.2); color: #e88830; white-space: nowrap;
}
.canvas-controls { display: flex; align-items: center; gap: 6px; }
.faction-select {
  background: var(--bg-panel); color: var(--text); border: 1px solid var(--accent-dim);
  border-radius: 5px; padding: 3px 6px; font-size: 11px;
}
.tool-btn {
  background: rgba(255, 255, 255, 0.06); color: var(--text); border: none;
  border-radius: 5px; padding: 3px 8px; font-size: 11px; cursor: pointer;
}
.tool-btn:hover { background: var(--accent); }
.tool-btn.close { background: rgba(232, 106, 106, 0.2); }
.tool-btn.close:hover { background: #c05050; }
.canvas-status { padding: 20px; text-align: center; color: var(--text-dim); }
.canvas-status.error { color: #e86a6a; }
.canvas-hint { padding: 4px 8px; font-size: 10px; color: var(--text-dim); background: rgba(20,20,35,0.9); border-bottom: 1px solid rgba(255,255,255,0.06); }
.canvas-flow { flex: 1; }
.link-menu {
  position: fixed; z-index: 30; width: 260px;
  background: #1a1a2e; border: 1px solid rgba(255,255,255,0.15); border-radius: 6px;
  padding: 8px; box-shadow: 0 4px 20px rgba(0,0,0,0.5);
}
.link-menu-title { font-size: 9px; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 4px; }
.link-menu-close {
  position: absolute; top: 4px; right: 4px; font-size: 12px; line-height: 1;
  padding: 2px 4px; background: none; border: none; color: var(--text-dim); cursor: pointer;
}
.link-menu-close:hover { color: #e06060; }
</style>

<style>
/* Vue Flow needs its nodes to render with explicit dimensions. */
.canvas-flow .vue-flow__node { font-size: 13px; }
</style>
