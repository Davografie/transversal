<template>
  <div ref="wrapperEl" class="panel-node" :class="{ nested }" :style="nodeStyle">
    <div ref="actionsEl" class="panel-actions" :class="{ 'is-flipped': direction === 'right', 'is-row': isVertical, 'is-down': direction === 'down', 'is-up': direction === 'up', 'is-anchored': isShallowestVisible }" :style="actionsStyle" v-show="!isDepthHidden && !isCollapsed">
      <!-- Drag handle (drag-only): on the anchor rail it moves the whole stack
           (the anchor); on any other rail it slides this panel along its
           parent's edge (button-drift's manual override). -->
      <Button class="panel-action-btn panel-drag-handle" variant="ghost" size="icon" :title="isShallowestVisible ? 'Move the panel anchor' : 'Slide along the parent'" @pointerdown="onHandleDown">⠿</Button>
      <!-- Detach: leave the chain and float as its own window (the window parks
           exactly where the panel is, so nothing jumps). -->
      <Button v-if="!isRoot && onDetach" class="panel-action-btn" variant="neutral" size="icon" title="Detach into a floating window" @click="onDetach(detachAnchor())">⤢</Button>
      <!-- Dock: only while a live panel matching the window's remembered parent
           identity is open (a re-opened parent counts). -->
      <Button v-if="canDock" class="panel-action-btn" variant="neutral" size="icon" title="Dock back into its parent" @click="$emit('dock')">⤓</Button>
      <Button v-if="closable" class="panel-action-btn" title="Close" variant="neutral" size="icon" @click="$emit('close')">×</Button>
      <Button type="button" class="panel-action-btn" variant="neutral" size="icon" :title="isCollapsed ? 'Expand' : 'Collapse'" @click="toggleCollapse()">{{ isCollapsed ? '▸' : '▾' }}</Button>
    </div>
    <!-- ⚠ Depth hiding uses visibility/display via :style (see panelVisibilityStyle).
         A depth-hidden panel is removed from layout so the chain re-anchors. -->
    <div ref="panelEl" class="panel" :class="{ 'is-collapsed': isCollapsed, 'has-title': !!title }" :style="panelVisibilityStyle">
      <header v-if="title" class="panel-header" :class="{ 'is-collapsed': isCollapsed }">
        <slot name="header">
          <span class="panel-title">{{ title }}</span>
          <Button v-if="id && !isCollapsed" type="button" class="panel-id-btn" variant="neutral" size="sm" :title="copied ? 'Copied!' : 'Copy ID'" @click="copyId">{{ copied ? '✓' : '#' }}</Button>
        </slot>
      </header>
      <div class="panel-body" :class="{ 'is-flush': !bodyScroll }" v-show="!isCollapsed">
        <slot />
      </div>
    </div>
    <!-- Children = a tab group: collapsed siblings render as chips in a wrapping
         strip; the single active child renders as a panel below it. All child
         Panels stay mounted (v-show) so their drafts survive collapse; the strip
         shows lightweight tab buttons that reference them. -->
    <div class="panel-children" v-show="!isCollapsed">
      <div ref="tabsEl" class="panel-tabs" :class="{ 'is-flipped': direction === 'right', 'is-column': isVertical }" :style="tabsStyle" v-show="collapsedChildren.length && !isDepthHidden">
        <div v-for="c in collapsedChildren" :key="c.key" class="panel-chip" @click="toggleChildCollapse(c.key)">
          <span class="chip-expand">▸</span>
          <span class="chip-title">{{ c.spec.title }}</span>
          <Button type="button" class="chip-btn" variant="ghost" title="Close" @click.stop="closeChild(c.key)">×</Button>
        </div>
      </div>
      <Panel
        v-for="c in children"
        :key="c.key"
        v-show="c.key === activeKey"
        nested
        :depth="depth + 1"
        :min-visible-depth="minVisibleDepth"
        :title="c.spec.title"
        :id="c.spec.id"
        :collapsed="false"
        :active="c.key === activeKey"
        :direction="direction"
        :gap="gap"
        :top="activePosition.top"
        :left="activePosition.left"
        :max-height="activeMaxHeight"
        :max-width="activeMaxWidth"
        :bridge-top="childBridgeTop"
        :bridge-bottom="childBridgeBottom"
        :bridge-left="childBridgeLeft"
        :bridge-right="childBridgeRight"
        :origin-top="wrapperTopPx"
        :origin-left="wrapperLeftPx"
        :on-size="(w, h) => recordChildSize(c.key, w, h)"
        :on-detach="(point) => detachChild(c.key, point)"
        closable
        :on-close="() => closeChild(c.key)"
        :on-replace="(spec) => replaceChild(c.key, spec)"
        @close="closeChild(c.key)"
        @toggle-collapse="toggleChildCollapse(c.key)"
      >
        <template #default>
          <component :is="c.spec.component" v-bind="c.spec.props || {}" v-on="c.spec.listeners || {}" @close="closeChild(c.key)" />
        </template>
      </Panel>
    </div>
  </div>
</template>

<script setup>
import { shallowRef, ref, reactive, computed, markRaw, inject, provide, onMounted, onUnmounted, nextTick, watch } from 'vue'
import { useClipboard } from '@vueuse/core'
import { panelKey, panelIdentityKey, registerPanelIdentity, unregisterPanelIdentity } from '@/composables/usePanel.js'
import { usePanelWindows } from '@/composables/usePanelWindows.js'
import Button from '@/components/ui/Button.vue'

const props = defineProps({
  title: { type: String, default: '' },
  id: { type: String, default: '' },
  // This panel's own spec — `{ component, title, id, props, listeners }`.
  // Needed to register its identity (dock targets are found by component + id)
  // and to spawn the same panel as a floating window when it detaches.
  spec: { type: Object, default: null },
  // The stack's root window id ('root') or the floating window this panel
  // belongs to (used only for logging/diagnostics so far).
  windowId: { type: String, default: 'root' },
  // A floating window whose parent identity currently resolves to a live panel
  // gets a dock button.
  canDock: { type: Boolean, default: false },
  closable: { type: Boolean, default: false },
  nested: { type: Boolean, default: false },
  // Whether the panel body scrolls as one block (default) or the slot content
  // manages its own scrolling (e.g. a pinned filter bar above a scrolling
  // list). `false` makes the body a non-scrolling flex column.
  bodyScroll: { type: Boolean, default: true },
  depth: { type: Number, default: 0 },
  minVisibleDepth: { type: Number, default: 0 },
  // Controlled collapse. null = uncontrolled (panel owns its own local state,
  // e.g. the root). Any boolean = controlled by the parent.
  collapsed: { type: Boolean, default: null },
  // Whether this panel is the active child (signalled to slot content so
  // singleton-composable panels can reload their data on tab switch).
  active: { type: Boolean, default: true },
  // Parent panel's viewport bounds. When set, this panel's action rail prefers
  // its own vertical center but is clamped within these bounds (button-drift).
  bridgeTop: { type: Number, default: null },
  bridgeBottom: { type: Number, default: null },
  // ── Positioning (anchor + out-of-flow model) ──────────
  // Open direction: 'left' (right-to-left), 'right' (left-to-right), 'down'
  // (top-edge anchor) and 'up' (bottom-edge anchor).
  direction: { type: String, default: 'left' },
  gap: { type: Number, default: 8 },
  // Assigned offset (children only): absolute top/left within the parent's
  // node. Root panels compute their own position from `anchor`.
  top: { type: Number, default: null },
  left: { type: Number, default: null },
  // Cap this panel's height (active child under a chip strip).
  maxHeight: { type: Number, default: null },
  // Cap this panel's width (vertical chains: the row must fit the viewport).
  maxWidth: { type: Number, default: null },
  // Toggle anchor rect (root only): { left, right, top, bottom, centerX, centerY }.
  anchor: { type: Object, default: null },
  // Parent panel's viewport bounds along the perpendicular axis. When set, this
  // panel's action rail prefers its own center but is clamped within them
  // (button-drift: vertical span for lateral chains, horizontal for up/down).
  bridgeLeft: { type: Number, default: null },
  bridgeRight: { type: Number, default: null },
  // The parent's *node* origin in viewport coordinates. Offsets (top/left) are
  // relative to it, so this is how a child resolves its own viewport position
  // without measuring itself (which would feed its own clamp back into the
  // measurement).
  originTop: { type: Number, default: null },
  originLeft: { type: Number, default: null },
  // Report this panel's measured size up to the parent (children only).
  onSize: { type: Function, default: null },
  // Callbacks supplied by the parent Panel so this Panel can close/replace
  // itself in the parent's children list.
  onClose: { type: Function, default: null },
  onReplace: { type: Function, default: null },
  // Called with `{ x, y, direction }` when this panel detaches: the parent
  // spawns the floating window and drops the child.
  onDetach: { type: Function, default: null },
})

const emit = defineEmits(['close', 'toggle-collapse', 'dock'])

// Detaching spawns a floating window from the panel-window registry (a module
// singleton — any panel can spawn one, not just PanelStack).
const { spawn: spawnWindow } = usePanelWindows()

// Copy-ID helper — the header shows a # button that copies the panel id.
// legacy:true enables the execCommand fallback so copying works on plain-HTTP
// (non-secure-context) hosts, not just localhost/HTTPS.
const { copy, copied } = useClipboard({ copiedDuring: 1200, legacy: true })
async function copyId() {
  if (!props.id) return
  await copy(props.id)
}

// ⚠ shallowRef — must NOT be ref() because Vue deeply unwraps nested refs inside
// reactive objects. If a child spec contains computed refs (e.g. filteredTraitsets),
// ref() would unwrap them to plain values, breaking reactivity for sub-panels.
const children = shallowRef([])
let childSeq = 0

// Collapse/expand. Controlled by the parent when `collapsed` is passed;
// otherwise this panel owns a local toggle (root case).
const localCollapsed = ref(false)
const isCollapsed = computed(() => props.collapsed ?? localCollapsed.value)
function toggleCollapse() {
  if (props.collapsed !== null) emit('toggle-collapse')
  else localCollapsed.value = !localCollapsed.value
  panelLog('toggle-self')
}

// The single expanded (active) child. All other children are collapsed chips.
const activeKey = ref(null)

function toggleChildCollapse(key) {
  const next = activeKey.value === key ? null : key
  activeKey.value = next
  panelLog('toggle-child', { key, action: next === key ? 'expand' : 'collapse' })
}

// ── Measurement + positioning ─────────────────────────
const panelEl = ref(null)
const actionsEl = ref(null)
const wrapperEl = ref(null)
const tabsEl = ref(null)

const isRoot = computed(() => !props.nested)

// Depth-based hiding (viewport-aware panel limit). A shallow panel that's hidden
// is fully removed from layout (display:none) so it takes no horizontal space and
// the chain re-anchors rightward toward the toggle. Its children still render and
// inherit the anchor via the pass-through bridge below.
const isDepthHidden = computed(() => !!(props.minVisibleDepth && props.depth < props.minVisibleDepth))
// The shallowest VISIBLE panel — its action rail replaces the 🛠 toggle, so
// it is pinned to the toggle's viewport position (right: 12px).
const isShallowestVisible = computed(() =>
  !isDepthHidden.value && props.depth === (props.minVisibleDepth || 0)
)
const panelVisibilityStyle = computed(() => {
  const s = {}
  if (isDepthHidden.value) s.display = 'none'
  if (props.maxHeight != null) s.maxHeight = props.maxHeight + 'px'
  if (props.maxWidth != null) s.maxWidth = props.maxWidth + 'px'
  return s
})

// Measured size of THIS panel's `.panel` box (content-driven width, capped).
const nodeSize = reactive({ w: 0, h: 0 })

// Root panels compute their own viewport position; children use props.top/left.
const selfTop = ref(null)
const selfLeft = ref(null)

// Viewport geometry of THIS panel (for the rail clamp + child bridge bounds).
const panelTopPx = ref(null)
const panelBottomPx = ref(null)
const panelLeftPx = ref(null)
const panelRightPx = ref(null)
const wrapperTopPx = ref(null)
const wrapperLeftPx = ref(null)
const ownCenter = ref(null)
const ownCenterX = ref(null)

const viewWidth = ref(window.innerWidth)
const viewHeight = ref(window.innerHeight)

let lastReportedWidth = 0
let lastReportedHeight = 0

function measureSelf() {
  const p = panelEl.value?.getBoundingClientRect()
  const w = wrapperEl.value?.getBoundingClientRect()
  if (!p) return
  const pw = Math.round(p.width)
  const ph = Math.round(p.height)
  const sizeChanged = nodeSize.w !== pw || nodeSize.h !== ph
  if (nodeSize.w !== pw) nodeSize.w = pw
  if (nodeSize.h !== ph) nodeSize.h = ph
  ownCenter.value = p.top + p.height / 2
  ownCenterX.value = p.left + p.width / 2
  panelTopPx.value = p.top
  panelBottomPx.value = p.bottom
  panelLeftPx.value = p.left
  panelRightPx.value = p.right
  if (w) {
    wrapperTopPx.value = w.top
    wrapperLeftPx.value = w.left
  }
  if (props.onSize) props.onSize(pw, ph)
  // Report the *intrinsic* size for the fit calc. A depth-hidden panel measures
  // 0 (display:none) but must keep reporting its true size — otherwise the fit
  // loop sees "no size", un-hides it, and oscillates.
  if (pw > 0) lastReportedWidth = pw
  if (ph > 0) lastReportedHeight = ph
  const reportW = pw > 0 ? pw : lastReportedWidth
  const reportH = ph > 0 ? ph : lastReportedHeight
  if (sizeChanged && reportW > 0 && setPanelSize && panelUid != null) {
    setPanelSize(props.depth, panelUid, reportW, reportH)
  }
  if (isRoot.value) computeRootPosition()
}

// Root placement: anchor the panel to the toggle, centered on it as much as
// possible, but always clamped inside the viewport. Frozen afterwards — children
// are out of flow, so they never move the parent.
//
// The action rail replaces the 🛠 toggle, and the panel's inner (anchor-facing)
// edge tucks under it by RAIL_OVERHANG: the button is a 42px box, the rail a
// 36px run of buttons, so the inner edge lands 1px past the anchor center —
// anchor ± 1, whichever side the chain grows to.
const RAIL_OVERHANG = 20

function computeRootPosition() {
  const a = props.anchor
  // A depth-hidden root measures 0×0 but must still resolve a position so its
  // children (the now-shallowest panels) anchor near the toggle, not (0,0).
  if (!a) return
  const vw = window.innerWidth
  const vh = window.innerHeight
  const MARGIN = VIEWPORT_MARGIN
  let top, left
  if (props.direction === 'down') {
    // Vertical chains grow away from the anchor's edge: the panel's inner edge
    // (top for down, bottom for up) tucks under the rail, and the panel is
    // centered on the anchor along the other axis.
    top = a.bottom - RAIL_OVERHANG
    left = a.centerX - nodeSize.w / 2
  } else if (props.direction === 'up') {
    top = a.top + RAIL_OVERHANG - nodeSize.h
    left = a.centerX - nodeSize.w / 2
  } else if (props.direction === 'right') {
    left = a.right - RAIL_OVERHANG
    top = a.centerY - nodeSize.h / 2
  } else {
    // 'left' (default, right-to-left).
    left = a.left + RAIL_OVERHANG - nodeSize.w
    top = a.centerY - nodeSize.h / 2
  }
  left = Math.min(Math.max(left, MARGIN), Math.max(MARGIN, vw - nodeSize.w - MARGIN))
  top = Math.min(Math.max(top, MARGIN), Math.max(MARGIN, vh - nodeSize.h - MARGIN))
  selfTop.value = top
  selfLeft.value = left
}

// ── Child sizes + tab-group layout ─────────────────────
const childSizes = reactive({})

function recordChildSize(key, w, h) {
  const cur = childSizes[key]
  if (cur && cur.w === w && cur.h === h) return
  childSizes[key] = { w, h }
}

const activeChild = computed(() => children.value.find((c) => c.key === activeKey.value) || null)
const collapsedChildren = computed(() => children.value.filter((c) => c.key !== activeKey.value))

// ── Child layout: one model, two axes ────────────────
// A chain grows along its axis (X for left/right, Y for up/down). Along the
// axis each level is offset from its parent by the chain sign; perpendicular to
// it, the child row (chip strip + active panel) is centered on the parent's own
// center. `crossStart` is where that row begins, `chainOffset` where the row
// sits relative to the parent.
const isVertical = computed(() => props.direction === 'up' || props.direction === 'down')

// Measured size of the chip strip (0 when there are no collapsed siblings).
const tabsHeight = ref(0)
const tabsWidth = ref(0)
function measureTabs() {
  const el = tabsEl.value
  const w = el ? Math.round(el.getBoundingClientRect().width) : 0
  const h = el ? Math.round(el.getBoundingClientRect().height) : 0
  if (tabsWidth.value !== w) tabsWidth.value = w
  if (tabsHeight.value !== h) tabsHeight.value = h
}

const activeSize = computed(() => {
  const c = activeChild.value
  return c ? (childSizes[c.key] || { w: 0, h: 0 }) : { w: 0, h: 0 }
})

// The strip's extent and the active panel's extent along the perpendicular axis
// (the axis the strip and the panel stack along): heights for lateral chains,
// widths for vertical ones.
const tabExtent = computed(() => (isVertical.value ? tabsWidth.value : tabsHeight.value))
const activeExtent = computed(() => (isVertical.value ? activeSize.value.w : activeSize.value.h))
const stripGap = computed(() => (tabExtent.value > 0 ? props.gap : 0))
const crossTotal = computed(() => tabExtent.value + stripGap.value + activeExtent.value)
const crossStart = computed(() => {
  const parentExtent = isVertical.value ? nodeSize.w : nodeSize.h
  return parentExtent / 2 - crossTotal.value / 2
})

// Offset along the chain axis. Depth-hiding: a hidden panel contributes neither
// its extent nor a gap to the chain, so the shallowest visible panel takes the
// anchor's place. A negative-growth chain (left/up) collapses a hidden level
// onto this node's origin (its own extent measures 0); a positive-growth chain
// (right/down) anchors on this node's far edge instead.
const chainOffset = computed(() => {
  const hidden = isDepthHidden.value
  if (props.direction === 'down') {
    return hidden ? nodeSize.h : nodeSize.h + props.gap
  }
  if (props.direction === 'up') {
    return hidden ? -(activeSize.value.h) : -(activeSize.value.h + props.gap)
  }
  if (props.direction === 'right') {
    return hidden ? nodeSize.w : nodeSize.w + props.gap
  }
  return hidden ? -(activeSize.value.w) : -(activeSize.value.w + props.gap)
})

const tabsStyle = computed(() => {
  if (isVertical.value) {
    // A column on the parent side of the row, wrapping within the active
    // panel's height (a definite height is essential — an auto-sized column
    // shrink-to-fits to min-content and stacks every chip on its own row).
    const h = activeSize.value.h || nodeSize.h || 200
    return {
      left: crossStart.value + 'px',
      top: (props.direction === 'down' ? nodeSize.h + props.gap : -(h + props.gap)) + 'px',
      height: h + 'px',
    }
  }
  // Width the chip strip wraps within: the focus panel's width (so chips stay
  // no wider than the active panel), falling back to this panel's own width.
  const w = activeSize.value.w || nodeSize.w || 200
  return {
    top: crossStart.value + 'px',
    left: (props.direction === 'right' ? nodeSize.w + props.gap : -(w + props.gap)) + 'px',
    width: w + 'px',
  }
})

const activePosition = computed(() => {
  const c = activeChild.value
  if (!c) return { top: null, left: null }
  const crossOffset = crossStart.value + tabExtent.value + stripGap.value
  if (isVertical.value) {
    return { top: chainOffset.value, left: crossOffset }
  }
  return { top: crossOffset, left: chainOffset.value }
})

// Cap the active panel so the strip + panel fit the viewport along the free
// axis: a lateral chain caps the child's height (the strip stacks above it), a
// vertical chain caps its width (the strip sits beside it) and lets the chain
// axis use whatever room is left beyond the parent.
//
// ⚠ A vertical chain's cap must NOT depend on a depth-hidden parent's rect:
// a hidden panel measures 0, so the cap would jump wide, the child would grow,
// the fit loop would un-hide the parent — an endless flip. Hidden parents fall
// back to the flat chain budget (the same one the fit loop uses).
const activeMaxHeight = computed(() => {
  if (props.direction === 'down') {
    const bottom = isDepthHidden.value ? null : panelBottomPx.value
    const room = bottom == null ? viewHeight.value - 71 : viewHeight.value - 12 - bottom - props.gap
    return Math.max(120, room)
  }
  if (props.direction === 'up') {
    const top = isDepthHidden.value ? null : panelTopPx.value
    const room = top == null ? viewHeight.value - 71 : top - 12 - props.gap
    return Math.max(120, room)
  }
  return Math.max(120, viewHeight.value - 40 - tabExtent.value - stripGap.value)
})

// Vertical chains: the row (chip strip + panel) must fit the viewport width;
// this is the panel's share of it.
const activeMaxWidth = computed(() => {
  if (!isVertical.value) return null
  return Math.max(160, viewWidth.value - 40 - tabExtent.value - stripGap.value)
})

// The node is hidden until it has a measured size and a resolved position, so
// panels don't flash at their pre-layout spot for a frame.
const effectiveTop = computed(() => (isRoot.value ? selfTop.value : props.top))
const effectiveLeft = computed(() => (isRoot.value ? selfLeft.value : props.left))
const placed = computed(() =>
  effectiveTop.value != null && effectiveLeft.value != null &&
  nodeSize.w > 0 && nodeSize.h > 0
)
// ── Viewport clamp ────────────────────────────────────
// No panel may sit outside the viewport: children are placed by their parent's
// offsets, and a large panel centred on a small parent (or a long chain) can
// otherwise poke past an edge and become unreachable. Roots clamp themselves in
// computeRootPosition; a child resolves its intended viewport position from its
// parent's node origin + its own offsets and nudges back inside by the smallest
// shift. Deliberately *not* derived from this panel's own measured rect — that
// rect already contains the correction, so reading it back would flip-flop.
const VIEWPORT_MARGIN = 12

const viewportFix = computed(() => {
  if (isRoot.value) return { x: 0, y: 0 }
  const oy = props.originTop
  const ox = props.originLeft
  if (oy == null || ox == null || !nodeSize.w || !nodeSize.h) return { x: 0, y: 0 }
  const vw = viewWidth.value
  const vh = viewHeight.value
  const intendedTop = oy + (effectiveTop.value ?? 0) + (isVertical.value ? 0 : slideOffset.value)
  const intendedLeft = ox + (effectiveLeft.value ?? 0) + (isVertical.value ? slideOffset.value : 0)
  const top = Math.min(Math.max(intendedTop, VIEWPORT_MARGIN), Math.max(VIEWPORT_MARGIN, vh - nodeSize.h - VIEWPORT_MARGIN))
  const left = Math.min(Math.max(intendedLeft, VIEWPORT_MARGIN), Math.max(VIEWPORT_MARGIN, vw - nodeSize.w - VIEWPORT_MARGIN))
  return { x: left - intendedLeft, y: top - intendedTop }
})

const nodeStyle = computed(() => {
  const fix = viewportFix.value
  return {
    top: ((effectiveTop.value ?? 0) + (isVertical.value ? 0 : slideOffset.value) + fix.y) + 'px',
    left: ((effectiveLeft.value ?? 0) + (isVertical.value ? slideOffset.value : 0) + fix.x) + 'px',
    visibility: placed.value ? 'visible' : 'hidden',
  }
})

// The scope children clamp their rail to (the parent's panel box). When THIS
// panel is depth-hidden its own bounds are meaningless, so pass the inherited
// scope through unchanged — the shallowest visible descendant then falls back
// to its own center, which is the anchor it should inherit.
const childBridgeTop = computed(() => (isDepthHidden.value ? props.bridgeTop : panelTopPx.value))
const childBridgeBottom = computed(() => (isDepthHidden.value ? props.bridgeBottom : panelBottomPx.value))
const childBridgeLeft = computed(() => (isDepthHidden.value ? props.bridgeLeft : panelLeftPx.value))
const childBridgeRight = computed(() => (isDepthHidden.value ? props.bridgeRight : panelRightPx.value))

// ── Button-drift: prefer own center, clamp within the parent's bounds ──
// Lateral chains clamp the rail's vertical center to the parent's vertical
// span; vertical chains clamp its horizontal center to the parent's span.
const railCenterViewport = computed(() => {
  const c = ownCenter.value
  if (c == null) return null
  if (props.bridgeTop == null || props.bridgeBottom == null) return c
  return Math.min(Math.max(c, props.bridgeTop), props.bridgeBottom)
})

const railCenterViewportX = computed(() => {
  const c = ownCenterX.value
  if (c == null) return null
  if (props.bridgeLeft == null || props.bridgeRight == null) return c
  return Math.min(Math.max(c, props.bridgeLeft), props.bridgeRight)
})

// Wrapper-relative Y/X for the rail (null → fall back to the CSS default).
const railCenterLocal = computed(() => {
  const rcv = railCenterViewport.value
  const wt = wrapperTopPx.value
  if (rcv == null || wt == null) return null
  return rcv - wt
})

const railCenterLocalX = computed(() => {
  const rcx = railCenterViewportX.value
  const wl = wrapperLeftPx.value
  if (rcx == null || wl == null) return null
  return rcx - wl
})

// The rail's icon buttons are 36px circles, so the rail is one column wide.
const RAIL_W = 36

// The anchor rail (shallowest visible panel) — the 🛠 button's successor. It is
// pinned to the anchor point, exactly where the 🛠 sits when the stack is
// closed, so the closed button and the open rail occupy the same spot. Move the
// anchor (drag the handle / the 🛠) and the rail moves with it.
const anchorPoint = inject('panelAnchorPoint', null)
const anchorDrag = inject('panelAnchorDrag', null)
const anchorVersion = inject('anchorVersion', null)
// Coalesce to one measure per frame: the anchor moves on every pointermove, and
// re-measuring inside the ResizeObserver's own notification window is what
// provokes "ResizeObserver loop completed with undelivered notifications".
if (anchorVersion) watch(anchorVersion, () => queueMeasure())

function onAnchorDragStart(e) {
  if (anchorDrag) anchorDrag.begin(e)
}

// ── Sliding a panel along its parent's edge ───────────
// Dragging the ⠿ handle of a non-anchor panel moves that panel along the edge
// it shares with its parent — vertically on left/right chains, horizontally on
// up/down ones — clamped so the panel's rail centre stays within the parent's
// span (prefer-own-center becomes a manual override once dragged).
const slideOffset = ref(0)

function onHandleDown(e) {
  if (isShallowestVisible.value) {
    onAnchorDragStart(e)
    return
  }
  beginSlide(e)
}

function beginSlide(e) {
  if (typeof e.button === 'number' && e.button !== 0) return
  e.preventDefault()
  const vertical = isVertical.value
  const startOffset = slideOffset.value
  const startX = e.clientX
  const startY = e.clientY
  const startCenter = vertical ? ownCenterX.value : ownCenter.value
  const lo = vertical ? props.bridgeLeft : props.bridgeTop
  const hi = vertical ? props.bridgeRight : props.bridgeBottom
  // The measured centre already includes the current offset — clamp in offset
  // space (bounded by the parent's span), not against the measured centre, or a
  // second drag would mix a stale centre with a fresh offset and overshoot.
  const baseCenter = startCenter == null ? null : startCenter - startOffset
  const minOffset = baseCenter == null || lo == null ? null : lo - baseCenter
  const maxOffset = baseCenter == null || hi == null ? null : hi - baseCenter

  function onMove(ev) {
    const delta = vertical ? ev.clientX - startX : ev.clientY - startY
    let next = startOffset + delta
    if (minOffset != null && next < minOffset) next = minOffset
    if (maxOffset != null && next > maxOffset) next = maxOffset
    slideOffset.value = next
    // A slide is a *position* change, which the ResizeObserver never reports —
    // keep the measured centre fresh, or the next drag clamps against a stale one.
    queueMeasure()
  }
  function finish() {
    window.removeEventListener('pointermove', onMove)
    window.removeEventListener('pointerup', finish)
    window.removeEventListener('pointercancel', finish)
  }
  window.addEventListener('pointermove', onMove)
  window.addEventListener('pointerup', finish)
  window.addEventListener('pointercancel', finish)
}

const actionsStyle = computed(() => {
  if (isShallowestVisible.value) {
    const p = anchorPoint ? anchorPoint.value : null
    if (p) {
      if (isVertical.value) {
        // Row rail at the anchor point (centred by CSS translate(-50%,-50%)).
        return {
          position: 'fixed', right: 'auto', bottom: 'auto',
          left: p.x + 'px',
          top: p.y + 'px',
        }
      }
      return {
        position: 'fixed', right: 'auto',
        left: (p.x - RAIL_W / 2) + 'px',
        top: p.y + 'px',
      }
    }
    // No anchor context (defensive): the historical fixed spot.
    const top = railCenterViewport.value
    return top == null
      ? { position: 'fixed', right: '12px' }
      : { position: 'fixed', right: '12px', top: top + 'px' }
  }
  if (isVertical.value) {
    // Row rail: CSS places it on the child's top/bottom edge (the one facing
    // the parent); only the slide along the parent's span is set here.
    const localX = railCenterLocalX.value
    return localX == null ? {} : { left: localX + 'px' }
  }
  const local = railCenterLocal.value
  return local == null ? {} : { top: local + 'px' }
})

// ── Diagnostic logging (opt-in) ─────────────────────
function isDebug() {
  return typeof window !== 'undefined' && !!window.__PANEL_DEBUG__
}
function rectOf(el) {
  if (!el) return null
  const r = el.getBoundingClientRect()
  return { top: Math.round(r.top), bottom: Math.round(r.bottom), left: Math.round(r.left), right: Math.round(r.right), w: Math.round(r.width), h: Math.round(r.height) }
}
function buttonsOf(el) {
  if (!el) return []
  return Array.from(el.querySelectorAll('button')).map((b) => {
    const r = b.getBoundingClientRect()
    return { label: (b.textContent || '').trim(), top: Math.round(r.top), bottom: Math.round(r.bottom), left: Math.round(r.left), right: Math.round(r.right) }
  })
}
function panelLog(reason, detail = {}) {
  if (!isDebug()) return
  console.log('[panel]', reason, JSON.stringify({
    title: props.title || '(root)',
    depth: props.depth,
    collapsed: isCollapsed.value,
    activeKey: activeKey.value,
    viewHeight: viewHeight.value,
    bridgeTop: props.bridgeTop,
    bridgeBottom: props.bridgeBottom,
    minVisibleDepth: props.minVisibleDepth,
    depthHidden: isDepthHidden.value,
    ownCenter: ownCenter.value,
    railCenterViewport: railCenterViewport.value,
    tabsHeight: tabsHeight.value,
    pos: { top: effectiveTop.value, left: effectiveLeft.value },
    size: { w: nodeSize.w, h: nodeSize.h },
    panel: rectOf(panelEl.value),
    actions: rectOf(actionsEl.value),
    buttons: buttonsOf(actionsEl.value),
    children: children.value.map((c) => ({ key: c.key, title: c.spec.title, id: c.spec.id, active: c.key === activeKey.value })),
    ...detail,
  }))
}

// ── Observers + watchers ──────────────────────────────
let driftObserver = null
let tabsObserver = null
// Coalesced re-measure: one pass per frame, never inside a ResizeObserver's own
// notification (mutating reactive state there re-triggers the observer in the
// same delivery and provokes "ResizeObserver loop completed with undelivered
// notifications").
let measureQueued = false
function queueMeasure() {
  if (measureQueued) return
  measureQueued = true
  requestAnimationFrame(() => {
    measureQueued = false
    measureSelf()
    measureTabs()
  })
}

function setupObserver() {
  if (typeof ResizeObserver === 'undefined') return
  if (panelEl.value) {
    driftObserver = new ResizeObserver(() => queueMeasure())
    driftObserver.observe(panelEl.value)
  }
  if (tabsEl.value) {
    tabsObserver = new ResizeObserver(() => queueMeasure())
    tabsObserver.observe(tabsEl.value)
  }
  measureSelf()
  measureTabs()
}

function onResize() {
  viewWidth.value = window.innerWidth
  viewHeight.value = window.innerHeight
  measureSelf()
  measureTabs()
}

onMounted(() => {
  if (registerPanel) panelUid = registerPanel(props.depth)
  setupObserver()
  window.addEventListener('resize', onResize)
})
onUnmounted(() => {
  if (driftObserver) driftObserver.disconnect()
  if (tabsObserver) tabsObserver.disconnect()
  window.removeEventListener('resize', onResize)
  if (unregisterPanel && panelUid != null) unregisterPanel(props.depth, panelUid)
})

watch([children, activeKey, viewHeight], () => nextTick(() => {
  measureTabs()
  measureSelf()
}))
// The sibling stack re-centers (or this panel is re-anchored) without a size
// change, which ResizeObserver alone misses — re-measure on position change so
// the action rail follows the panel instead of stranding at the pre-move spot.
watch([effectiveTop, effectiveLeft], () => nextTick(measureSelf))
watch(childSizes, () => nextTick(() => {
  measureTabs()
  measureSelf()
}), { deep: true })
watch(() => props.anchor, () => { if (isRoot.value) computeRootPosition() })

// Diagnostic: log each panel's depth-hide/show transition with its resolved
// position so the visible chain can be read from the console
// (window.__PANEL_DEBUG__ = true).
watch(isDepthHidden, (hidden) => {
  nextTick(() => {
    panelLog(hidden ? 'depth-hide' : 'depth-show', {
      minVisibleDepth: props.minVisibleDepth,
      panel: rectOf(panelEl.value),
    })
  })
})

// ── Width reporting for horizontal fit (viewport-aware panel limit) ──
const registerPanel = inject('registerPanel', null)
const setPanelSize = inject('setPanelSize', null)
const unregisterPanel = inject('unregisterPanel', null)
let panelUid = null

function normalizeSpec(spec) {
  return { ...spec, component: markRaw(spec.component) }
}

// Opens a child panel. If a child with the same component + id is already open,
// replace (refresh) it in place; otherwise append it. Either way it becomes the
// single active child (all other siblings collapse into chips).
function openChild(spec) {
  const normalized = normalizeSpec(spec)
  const idx = children.value.findIndex((c) => {
    if (c.spec.component !== normalized.component) return false
    if (normalized.id) return c.spec.id === normalized.id
    return !c.spec.id
  })
  if (idx >= 0) {
    children.value = children.value.map((c, i) =>
      i === idx ? { ...c, spec: normalized } : c
    )
    activeKey.value = children.value[idx].key
  } else {
    const key = `c${++childSeq}`
    children.value = [...children.value, { key, spec: normalized }]
    activeKey.value = key
  }
  panelLog('open', { childId: normalized.id, activeKey: activeKey.value })
}

// Closes a specific child by key, or the last child when no key is given.
function closeChild(key) {
  const removing = key == null
    ? (children.value[children.value.length - 1]?.key ?? null)
    : key
  children.value = key == null
    ? children.value.slice(0, -1)
    : children.value.filter((c) => c.key !== key)
  if (activeKey.value === removing) {
    activeKey.value = children.value[children.value.length - 1]?.key ?? null
  }
  panelLog('close-child', { key: removing })
}

function replaceChild(key, spec) {
  children.value = children.value.map((c) =>
    c.key === key ? { ...c, spec: normalizeSpec(spec) } : c
  )
}

// Detach a child into its own floating window: the window is parked where the
// child already is (so nothing visibly moves), it remembers this panel's
// identity as its parent, and the child leaves the chain.
function detachChild(key, point) {
  const c = children.value.find((x) => x.key === key)
  if (!c) return
  spawnWindow({ ...c.spec }, {
    x: point.x,
    y: point.y,
    direction: point.direction,
    sourceParentKey: panelIdentityKey(props.spec?.component, props.spec?.id),
  })
  children.value = children.value.filter((x) => x.key !== key)
  if (activeKey.value === key) {
    activeKey.value = children.value[children.value.length - 1]?.key ?? null
  }
  panelLog('detach-child', { key, point })
}

// Closes THIS panel (removes it from the parent's children list).
function closeSelf() {
  if (props.onClose) props.onClose()
}

// Where the floating window's anchor goes so detaching doesn't move the panel:
// the anchor-facing edge it already has (the window's chain then opens the same
// way, from the same spot).
function detachAnchor() {
  const r = panelEl.value?.getBoundingClientRect()
  if (!r) return { x: null, y: null, direction: props.direction }
  const cx = r.left + r.width / 2
  const cy = r.top + r.height / 2
  if (props.direction === 'right') return { x: r.left - 1, y: cy, direction: props.direction }
  if (props.direction === 'down') return { x: cx, y: r.top - 1, direction: props.direction }
  if (props.direction === 'up') return { x: cx, y: r.bottom + 1, direction: props.direction }
  return { x: r.right + 1, y: cy, direction: props.direction }
}

// ── Identity registration (dock targets) ──────────────
// The panel registers itself under "component + spec id" so a floating window
// that used to live inside it can find it again after a close/re-open.
const selfKey = computed(() => panelIdentityKey(props.spec?.component, props.spec?.id))
let identityHandle = null

onMounted(() => {
  if (!selfKey.value) return
  identityHandle = { openChild, close: closeSelf }
  registerPanelIdentity(selfKey.value, identityHandle)
})
watch(selfKey, (key, prev) => {
  if (prev && identityHandle) unregisterPanelIdentity(prev, identityHandle)
  if (key && identityHandle) registerPanelIdentity(key, identityHandle)
})
onUnmounted(() => {
  if (selfKey.value && identityHandle) unregisterPanelIdentity(selfKey.value, identityHandle)
})

// Replaces THIS panel with another spec in the parent's children list.
function replaceSelf(spec) {
  if (props.onReplace) props.onReplace(spec)
}

// ── Panel navigation context for the component in this panel's slot ──
// Whether this panel is the active tab (consumed by slot content to reload
// singleton-composable data when the active sibling changes).
provide('panelActive', computed(() => props.active))
provide(panelKey, {
  open: openChild,
  closeChild,
  close: closeSelf,
  replace: replaceSelf,
})
</script>

<style scoped>
/* The node is the positioned box. Its only in-flow child is `.panel`, so it
   shrink-to-fits around that box; `.panel-actions`, `.panel-tabs` and child
   `.panel-node`s are absolutely positioned (out of flow) and therefore never
   affect the parent. */
.panel-node {
  position: absolute;
  pointer-events: auto;
}

/* Static wrapper whose children are absolutely positioned relative to
   .panel-node (the nearest positioned ancestor). v-show hides the whole
   child stack when this panel is collapsed. */
.panel-children {
  /* static; children are out of flow */
}

/* Chip strip: collapsed siblings as compact tabs — a row wrapping right-to-left
   (leftward chains) or left-to-right (rightward chains), and a wrapping column
   for up/down chains, where it stands beside the active panel. */
.panel-tabs {
  position: absolute;
  display: flex;
  flex-wrap: wrap-reverse;
  justify-content: flex-end;
  gap: 4px;
  pointer-events: auto;
}
.panel-tabs.is-flipped { justify-content: flex-start; }
.panel-tabs.is-column {
  flex-direction: column;
  justify-content: flex-start;
  align-items: flex-start;
}
.panel-chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 3px 8px;
  font-size: 11px;
  border-radius: 6px;
  background: var(--bg-panel, var(--bg-panel));
  border: 1px solid var(--overlay-12);
  cursor: pointer;
  white-space: nowrap;
}
.panel-chip:hover { background: var(--overlay-8); }
.chip-expand { color: var(--text-dim); font-size: 11px; }
.chip-title {
  color: var(--text-dim);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  font-weight: 600;
  font-size: 11px;
}
.panel-chip .chip-btn {
  padding: 0 2px; font-size: 12px; line-height: 1;
}

.panel {
  display: inline-flex;
  flex-direction: column;
  background: var(--bg-panel, var(--bg-panel));
  backdrop-filter: blur(12px);
  border: 1px solid var(--overlay-8);
  border-radius: 8px;
  /* Variable width: content-driven, floored and capped. The cap is also
     viewport-bound: the panel's right edge sits at vw-34 (under the action
     rail), leaving a 12px left margin, so width ≤ vw-46. */
  min-width: min(260px, calc(100vw - 46px));
  max-width: min(var(--gm-panel-max-w, 440px), calc(100vw - 46px));
  max-height: calc(100vh - 40px);
  overflow: auto;
}

/* Panel action rail: a column of icon buttons outside the panel's right edge
   (close, collapse/expand, and the anchor drag handle). For a rightward chain
   the rail faces the parent on the panel's left edge. */
.panel-actions {
  position: absolute; top: 50%; right: -22px; transform: translateY(-50%); z-index: 2;
  display: flex; flex-direction: column; gap: 4px;
}
.panel-actions.is-flipped { right: auto; left: -22px; }

/* Up/down chains: the rail is a row on the edge facing the parent — the panel's
   top edge when the chain grows down, its bottom edge when it grows up — and
   slides along that edge (left set inline). */
.panel-actions.is-row {
  flex-direction: row;
  right: auto; left: auto;
  transform: translateX(-50%);
}
.panel-actions.is-row.is-down { bottom: auto; top: -22px; }
.panel-actions.is-row.is-up { top: auto; bottom: -22px; }
/* The anchor rail sits *on* the anchor point, both axes centred. */
.panel-actions.is-row.is-anchored { transform: translate(-50%, -50%); }
.panel-actions .panel-action-btn {
  width: 36px; height: 36px; border-radius: 50%;
  backdrop-filter: blur(12px);
}

/* The anchor rail's ⠿ handle: drag-only, so it can grab the pointer without
   the click/drag threshold the 🛠 needs. Same glyph as GmListItem's handle. */
.panel-actions .panel-drag-handle {
  cursor: grab;
  touch-action: none;
  color: var(--text-dim);
  font-size: 13px;
}
.panel-actions .panel-drag-handle:active { cursor: grabbing; }

.panel-header {
  display: flex;
  align-items: center;
  padding: 8px 12px;
  border-bottom: 1px solid var(--overlay-6);
  flex-shrink: 0;
}
/* Collapsed panels shrink to just the title: no divider, no copy-ID button,
   no minimum width (unless there's no title to size against). */
.panel-header.is-collapsed {
  border-bottom: none;
}
.panel.is-collapsed.has-title {
  min-width: 0;
}
.panel-header.is-collapsed .panel-title {
  flex: none;
  white-space: nowrap;
}
.panel-title {
  flex: 1; min-width: 0;
  font-size: 12px; font-weight: 600; color: var(--text-dim);
  text-transform: uppercase; letter-spacing: 0.5px;
}
.panel-header .panel-id-btn {
  flex-shrink: 0;
  font-family: monospace;
  font-weight: 600;
}

.panel-body {
  flex: 1; overflow-y: auto; padding: 10px;
}

/* Content owns its scrolling: the body becomes a flex column that fills the
   panel, so inner zones (and only they) can set overflow-y: auto. */
.panel-body.is-flush {
  overflow: hidden;
  display: flex;
  flex-direction: column;
  min-height: 0;
}
</style>
