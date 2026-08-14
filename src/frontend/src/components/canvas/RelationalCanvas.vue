<template>
  <div class="relational-canvas" :class="{ fullscreen }">
    <div class="canvas-toolbar">
      <div class="canvas-title">{{ title || 'Relational Canvas' }}</div>
      <div class="canvas-controls">
        <select
          v-model="selectedFaction"
          class="faction-select"
          @change="onFactionChange"
        >
          <option value="">— Filter by faction —</option>
          <option v-for="f in factions" :key="f.id" :value="f.id">{{ f.name }}</option>
        </select>
        <button v-if="mode !== 'location'" class="tool-btn" @click="backToLocation">← Location</button>
        <button class="tool-btn" @click="fitView">Fit</button>
        <button v-if="fullscreen" class="tool-btn close" @click="emit('close-full')">✕</button>
      </div>
    </div>
    <div class="canvas-hint">Drag from a location's right handle (→) to another location's left handle (←) to create a transversal link · click ⊕ to expand</div>

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
      @node-drag-stop="onNodeDragStop"
    >
      <Background :gap="24" />
      <Controls />
      <MiniMap />
    </VueFlow>
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
import LocationNode from '@/components/canvas/nodes/LocationNode.vue'
import OccupantNode from '@/components/canvas/nodes/OccupantNode.vue'
import GradientEdge from '@/components/canvas/edges/GradientEdge.vue'

const props = defineProps({
  locationId: { type: String, default: '' },
  initialFactionId: { type: String, default: '' },
  fullscreen: { type: Boolean, default: false },
})

const emit = defineEmits(['close-full'])

const bus = usePanelBus()

const canvas = useCanvas()
const { mode, title, loading, error, factions } = canvas
const nodes = canvas.nodes
const edges = canvas.edges

const selectedFaction = ref('')
const flowRef = ref(null)

function fitView() {
  flowRef.value?.fitView?.()
}

const nodeTypes = { location: LocationNode, occupant: OccupantNode }
const edgeTypes = { gradient: GradientEdge }

const displayNodes = computed(() =>
  nodes.value.map((n) => ({
    ...n,
    data: {
      ...n.data,
      onExpand: (id) => canvas.expandLocation(id),
      onCollapse: (id) => canvas.collapseLocation(id),
      onFocus: (id) => canvas.setFocus(id),
      onToggleRelations: (id) => canvas.toggleRelations(id),
      onShowFaction: (id) => canvas.showFaction(id),
      onInspect: (id) => bus.emit('canvas:inspect', id),
      onOpenFull: (id) => bus.emit('canvas:open-full', { mode: 'location', entityId: id }),
    },
  })),
)

function onFactionChange() {
  if (selectedFaction.value) {
    canvas.loadFaction(selectedFaction.value)
  }
}

async function onConnect(connection) {
  // Only the lateral handles (right → left) create transversal links.
  if (connection.sourceHandle !== 'right' || connection.targetHandle !== 'left') return
  const fromId = connection.source?.replace('loc:', '')
  const toId = connection.target?.replace('loc:', '')
  if (!fromId || !toId || fromId === toId) return
  const fromNode = nodes.value.find((n) => n.id === connection.source)
  const toNode = nodes.value.find((n) => n.id === connection.target)
  // Only allow location → location transversal links.
  if (fromNode?.type !== 'location' || toNode?.type !== 'location') return
  await canvas.createTransversal(fromId, toId)
}

function onNodeDragStop({ node }) {
  if (node) canvas.updateNodePosition(node.id, node.position)
}

function backToLocation() {
  if (props.locationId) canvas.loadLocation(props.locationId)
}

onMounted(async () => {
  canvas.loadFactions()
  if (props.initialFactionId) {
    await canvas.loadFaction(props.initialFactionId)
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
</style>

<style>
/* Vue Flow needs its nodes to render with explicit dimensions. */
.canvas-flow .vue-flow__node { font-size: 13px; }
</style>
