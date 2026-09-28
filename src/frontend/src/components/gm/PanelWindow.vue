<template>
  <Panel
    :anchor="anchorRect"
    :direction="win.direction || 'left'"
    :min-visible-depth="0"
    :body-scroll="win.spec?.bodyScroll !== false"
    :title="win.spec?.title"
    :id="win.spec?.id"
    :spec="win.spec"
    :window-id="win.id"
    :can-dock="dockable"
    :collapsed="!!win.collapsed"
    :on-size="(w, h) => { panelSize.w = w; panelSize.h = h }"
    closable
    @close="$emit('close')"
    @dock="$emit('dock')"
    @toggle-collapse="toggleCollapsed"
  >
    <template v-if="win.spec" #default>
      <PanelScope :context="win.spec.context">
        <component :is="win.spec.component" v-bind="win.spec.props || {}" v-on="win.spec.listeners || {}" />
      </PanelScope>
    </template>
  </Panel>
</template>

<script setup>
// One floating window: a detached panel that carries its own anchor.
//
// The window is free-standing — it never snaps to a viewport edge the way the
// main stack's anchor does — but its anchor is clamped so the rail stays
// reachable, and everything inside the window (the panel, its chain, the rails)
// follows the same layout rules via Panel.vue: the window's root panel is
// simply the chain root whose anchor happens to be here.
//
// Its chain direction is its **own**, derived from where the window sits (same
// edge bands + keep-last rule as the main stack) rather than inherited: drag a
// window to the left edge and its chain opens rightwards, to the top and it
// opens downwards — with no effect on the root stack.
//
// It shadows the stack's panel registry with no-ops so a window's chain never
// participates in the main stack's depth-hiding fit loop, and provides its own
// drag/pulse so the rail's ⠿ handle moves *this* window.
import { computed, ref, provide, watch, onMounted, onUnmounted } from 'vue'
import Panel from './Panel.vue'
import PanelScope from './PanelScope.vue'
import { usePanelWindows } from '@/composables/usePanelWindows.js'
import { clampAnchor, deriveDirection, VIEWPORT_MARGIN } from '@/composables/usePanelAnchor.js'
import { dumpPanelLayoutSoon } from '@/composables/usePanelDiagnostics.js'

const props = defineProps({
  win: { type: Object, required: true },
  dockable: { type: Boolean, default: false },
})

defineEmits(['close', 'dock'])

const { move: moveWindow, setDirection: setWindowDirection, toggleCollapse } = usePanelWindows()

// The window's collapsed state lives in the registry, not in the Panel, so it is
// stored with the window and survives a reload. (It is `win.collapsed` that
// `panelWindowPersistence` writes; a Panel left uncontrolled would keep the state
// to itself and lose it.)
function toggleCollapsed() {
  toggleCollapse(props.win.id)
}

const viewportWidth = ref(window.innerWidth)
const viewportHeight = ref(window.innerHeight)

const anchorCenter = computed(() => {
  const w = props.win
  const x = w.x == null ? viewportWidth.value / 2 : w.x
  const y = w.y == null ? viewportHeight.value / 2 : w.y
  return clampAnchor(x, y, viewportWidth.value, viewportHeight.value)
})

// Which way this window's chain opens. Inside an edge band the window takes that
// edge's direction; away from every edge it keeps the one it has — *unless* the
// chain's panel can no longer fit on that side while the other side fits, in
// which case it switches, so a window dragged across the screen opens into the
// room it has instead of being shoved off its own anchor by the viewport clamp.
// (Measured by Panel.vue and reported through onSize.)
const panelSize = ref({ w: 0, h: 0 })

function fitsOnSide(dir, p) {
  const w = panelSize.value.w
  const h = panelSize.value.h
  if (!w || !h) return true // not measured yet: don't second-guess
  if (dir === 'left') return p.x - 1 - w >= VIEWPORT_MARGIN
  if (dir === 'right') return p.x + 1 + w <= viewportWidth.value - VIEWPORT_MARGIN
  if (dir === 'down') return p.y + 1 + h <= viewportHeight.value - VIEWPORT_MARGIN
  if (dir === 'up') return p.y - 1 - h >= VIEWPORT_MARGIN
  return true
}

const OPPOSITE = { left: 'right', right: 'left', up: 'down', down: 'up' }

function syncDirection() {
  const p = anchorCenter.value
  const band = deriveDirection(p.x, p.y, viewportWidth.value, viewportHeight.value)
  if (band) {
    if (band !== props.win.direction) setWindowDirection(props.win.id, band)
    return
  }
  const cur = props.win.direction
  if (cur && !fitsOnSide(cur, p) && fitsOnSide(OPPOSITE[cur], p)) {
    setWindowDirection(props.win.id, OPPOSITE[cur])
  }
}

onMounted(syncDirection)
watch(anchorCenter, syncDirection)
watch(panelSize, syncDirection, { deep: true })

function onViewportResize() {
  viewportWidth.value = window.innerWidth
  viewportHeight.value = window.innerHeight
  syncDirection()
}
onMounted(() => window.addEventListener('resize', onViewportResize))
onUnmounted(() => window.removeEventListener('resize', onViewportResize))

const anchorRect = computed(() => {
  const { x, y } = anchorCenter.value
  return { left: x - 21, right: x + 21, top: y - 21, bottom: y + 21, centerX: x, centerY: y }
})

// Bumped on every window move so the window's panels re-measure (their rails are
// viewport-pinned when they are the shallowest visible one).
const anchorVersion = ref(0)
provide('anchorVersion', anchorVersion)

// The ⠿ handle on the window's root rail drags the window. No snapping here:
// a floating window stays where it is put; only the clamp keeps its rail on screen.
function startDrag(e) {
  if (typeof e.button === 'number' && e.button !== 0) return
  e.preventDefault()
  const startX = e.clientX
  const startY = e.clientY
  const start = { ...anchorCenter.value }
  function onMove(ev) {
    const next = clampAnchor(
      start.x + (ev.clientX - startX),
      start.y + (ev.clientY - startY),
      viewportWidth.value,
      viewportHeight.value,
    )
    moveWindow(props.win.id, next.x, next.y)
    anchorVersion.value++
  }
  function finish() {
    window.removeEventListener('pointermove', onMove)
    window.removeEventListener('pointerup', finish)
    window.removeEventListener('pointercancel', finish)
    dumpPanelLayoutSoon('window-drag-release', {
      windowId: props.win.id,
      anchor: { ...anchorCenter.value },
      direction: props.win.direction,
    })
  }
  window.addEventListener('pointermove', onMove)
  window.addEventListener('pointerup', finish)
  window.addEventListener('pointercancel', finish)
  dumpPanelLayoutSoon('window-drag-start', { windowId: props.win.id, anchor: { ...anchorCenter.value } })
  onViewportResize()
}

provide('panelAnchorDrag', { begin: startDrag })

// A window's chain is its own world: no depth budget, no width bookkeeping.
provide('registerPanel', () => null)
provide('setPanelSize', () => {})
provide('unregisterPanel', () => {})
</script>
