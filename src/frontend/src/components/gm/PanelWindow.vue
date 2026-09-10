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
    closable
    @close="$emit('close')"
    @dock="$emit('dock')"
  >
    <template v-if="win.spec" #default>
      <component :is="win.spec.component" v-bind="win.spec.props || {}" v-on="win.spec.listeners || {}" />
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
// It shadows the stack's panel registry with no-ops so a window's chain never
// participates in the main stack's depth-hiding fit loop, and provides its own
// drag/pulse so the rail's ⠿ handle moves *this* window.
import { computed, ref, provide } from 'vue'
import Panel from './Panel.vue'
import { usePanelWindows } from '@/composables/usePanelWindows.js'
import { clampAnchor } from '@/composables/usePanelAnchor.js'

const props = defineProps({
  win: { type: Object, required: true },
  dockable: { type: Boolean, default: false },
})

defineEmits(['close', 'dock'])

const { move: moveWindow } = usePanelWindows()

const viewportWidth = ref(window.innerWidth)
const viewportHeight = ref(window.innerHeight)

const anchorCenter = computed(() => {
  const w = props.win
  const x = w.x == null ? viewportWidth.value / 2 : w.x
  const y = w.y == null ? viewportHeight.value / 2 : w.y
  return clampAnchor(x, y, viewportWidth.value, viewportHeight.value)
})

const anchorRect = computed(() => {
  const { x, y } = anchorCenter.value
  return { left: x - 21, right: x + 21, top: y - 21, bottom: y + 21, centerX: x, centerY: y }
})

// The window's rail sits at its anchor.
provide('panelAnchorPoint', anchorCenter)

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
    window.removeEventListener('resize', onResize)
  }
  function onResize() {
    viewportWidth.value = window.innerWidth
    viewportHeight.value = window.innerHeight
  }
  window.addEventListener('pointermove', onMove)
  window.addEventListener('pointerup', finish)
  window.addEventListener('pointercancel', finish)
  window.addEventListener('resize', onResize)
  onResize()
}

provide('panelAnchorDrag', { begin: startDrag })

// A window's chain is its own world: no depth budget, no width bookkeeping.
provide('registerPanel', () => null)
provide('setPanelSize', () => {})
provide('unregisterPanel', () => {})
</script>
