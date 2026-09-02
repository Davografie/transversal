<template>
  <div ref="wrapperEl" class="panel-node" :class="{ nested }" :style="nodeStyle">
    <div ref="actionsEl" class="panel-actions" :style="actionsStyle" v-show="!isDepthHidden && !isCollapsed">
      <button v-if="closable" class="panel-action-btn" title="Close" @click="$emit('close')">×</button>
      <button type="button" class="panel-action-btn" :title="isCollapsed ? 'Expand' : 'Collapse'" @click="toggleCollapse()">{{ isCollapsed ? '▸' : '▾' }}</button>
    </div>
    <!-- ⚠ Depth hiding uses visibility/display via :style (see panelVisibilityStyle).
         A depth-hidden panel is removed from layout so the chain re-anchors. -->
    <div ref="panelEl" class="panel" :class="{ 'is-collapsed': isCollapsed, 'has-title': !!title }" :style="panelVisibilityStyle">
      <header v-if="title" class="panel-header" :class="{ 'is-collapsed': isCollapsed }">
        <slot name="header">
          <span class="panel-title">{{ title }}</span>
          <button v-if="id && !isCollapsed" type="button" class="panel-id-btn" :title="copied ? 'Copied!' : 'Copy ID'" @click="copyId">{{ copied ? '✓' : '#' }}</button>
        </slot>
      </header>
      <div class="panel-body" v-show="!isCollapsed">
        <slot />
      </div>
    </div>
    <!-- Children = a tab group: collapsed siblings render as chips in a wrapping
         strip; the single active child renders as a panel below it. All child
         Panels stay mounted (v-show) so their drafts survive collapse; the strip
         shows lightweight tab buttons that reference them. -->
    <div class="panel-children" v-show="!isCollapsed">
      <div ref="tabsEl" class="panel-tabs" :style="tabsStyle" v-show="collapsedChildren.length">
        <div v-for="c in collapsedChildren" :key="c.key" class="panel-chip" @click="toggleChildCollapse(c.key)">
          <span class="chip-expand">▸</span>
          <span class="chip-title">{{ c.spec.title }}</span>
          <button type="button" class="chip-btn" title="Close" @click.stop="closeChild(c.key)">×</button>
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
        :direction="direction"
        :gap="gap"
        :top="activePosition.top"
        :left="activePosition.left"
        :max-height="activeMaxHeight"
        :bridge-top="childBridgeTop"
        :bridge-bottom="childBridgeBottom"
        :on-size="(w, h) => recordChildSize(c.key, w, h)"
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
import { panelKey } from '@/composables/usePanel.js'

const props = defineProps({
  title: { type: String, default: '' },
  id: { type: String, default: '' },
  closable: { type: Boolean, default: false },
  nested: { type: Boolean, default: false },
  depth: { type: Number, default: 0 },
  minVisibleDepth: { type: Number, default: 0 },
  // Controlled collapse. null = uncontrolled (panel owns its own local state,
  // e.g. the root). Any boolean = controlled by the parent.
  collapsed: { type: Boolean, default: null },
  // Parent panel's viewport bounds. When set, this panel's action rail prefers
  // its own vertical center but is clamped within these bounds (button-drift).
  bridgeTop: { type: Number, default: null },
  bridgeBottom: { type: Number, default: null },
  // ── Positioning (anchor + out-of-flow model) ──────────
  // Open direction: 'left' (right-to-left) is implemented; right/up/down come
  // with the per-anchor direction work (Phase 2).
  direction: { type: String, default: 'left' },
  gap: { type: Number, default: 8 },
  // Assigned offset (children only): absolute top/left within the parent's
  // node. Root panels compute their own position from `anchor`.
  top: { type: Number, default: null },
  left: { type: Number, default: null },
  // Cap this panel's height (active child under a chip strip).
  maxHeight: { type: Number, default: null },
  // Toggle anchor rect (root only): { left, right, top, bottom, centerX, centerY }.
  anchor: { type: Object, default: null },
  // Report this panel's measured size up to the parent (children only).
  onSize: { type: Function, default: null },
  // Callbacks supplied by the parent Panel so this Panel can close/replace
  // itself in the parent's children list.
  onClose: { type: Function, default: null },
  onReplace: { type: Function, default: null },
})

const emit = defineEmits(['close', 'toggle-collapse'])

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
const panelVisibilityStyle = computed(() => {
  const s = {}
  if (isDepthHidden.value) s.display = 'none'
  if (props.maxHeight != null) s.maxHeight = props.maxHeight + 'px'
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
const wrapperTopPx = ref(null)
const ownCenter = ref(null)

const viewHeight = ref(window.innerHeight)

let lastReportedWidth = 0

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
  panelTopPx.value = p.top
  panelBottomPx.value = p.bottom
  if (w) wrapperTopPx.value = w.top
  if (props.onSize) props.onSize(pw, ph)
  // Report the *intrinsic* width for the horizontal-fit calc. A depth-hidden
  // panel measures 0 (display:none) but must keep reporting its true width —
  // otherwise the fit loop sees "no width", un-hides it, and oscillates.
  if (pw > 0) lastReportedWidth = pw
  const reportW = pw > 0 ? pw : lastReportedWidth
  if (sizeChanged && reportW > 0 && setPanelWidth && panelUid != null) {
    setPanelWidth(props.depth, panelUid, reportW)
  }
  if (isRoot.value) computeRootPosition()
}

// Root placement: anchor the panel to the toggle, centered on it as much as
// possible, but always clamped inside the viewport. Frozen afterwards — children
// are out of flow, so they never move the parent.
function computeRootPosition() {
  const a = props.anchor
  // A depth-hidden root measures 0×0 but must still resolve a position so its
  // children (the now-shallowest panels) anchor near the toggle, not (0,0).
  if (!a) return
  const vw = window.innerWidth
  const vh = window.innerHeight
  const MARGIN = 12
  let top, left
  if (props.direction === 'left') {
    left = a.left - props.gap - nodeSize.w
    top = a.centerY - nodeSize.h / 2
  } else {
    // TODO(Phase 2): other directions.
    left = a.right + props.gap
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

// Measured height of the chip strip (0 when there are no collapsed siblings).
const tabsHeight = ref(0)
function measureTabs() {
  const el = tabsEl.value
  const h = el ? Math.round(el.getBoundingClientRect().height) : 0
  if (tabsHeight.value !== h) tabsHeight.value = h
}

const activeSize = computed(() => {
  const c = activeChild.value
  return c ? (childSizes[c.key] || { w: 0, h: 0 }) : { w: 0, h: 0 }
})

// Strip + active panel are centered on the parent's own vertical center.
const stripGap = computed(() => (tabsHeight.value > 0 ? props.gap : 0))
const columnTotal = computed(() => tabsHeight.value + stripGap.value + activeSize.value.h)
const columnTop = computed(() => nodeSize.h / 2 - columnTotal.value / 2)

const tabsStyle = computed(() => {
  // Width the chip strip wraps within: the focus panel's width (so chips stay
  // no wider than the active panel), falling back to this panel's own width.
  // A definite width is essential — an auto width with a right-only offset
  // shrink-to-fits to min-content and stacks every chip on its own row.
  const w = activeSize.value.w || nodeSize.w || 200
  const style = {
    top: columnTop.value + 'px',
    width: w + 'px',
  }
  if (props.direction === 'left') style.left = -(w + props.gap) + 'px'
  else style.left = (nodeSize.w + props.gap) + 'px' // TODO(Phase 2)
  return style
})

const activePosition = computed(() => {
  const c = activeChild.value
  if (!c) return { top: null, left: null }
  const top = columnTop.value + tabsHeight.value + stripGap.value
  const left = props.direction === 'left'
    ? -(activeSize.value.w + props.gap)
    : nodeSize.w + props.gap // TODO(Phase 2)
  return { top, left }
})

// Cap the active panel so the strip + panel fit the viewport.
const activeMaxHeight = computed(() => {
  const h = viewHeight.value - 40 - tabsHeight.value - stripGap.value
  return Math.max(120, h)
})

// The node is hidden until it has a measured size and a resolved position, so
// panels don't flash at their pre-layout spot for a frame.
const effectiveTop = computed(() => (isRoot.value ? selfTop.value : props.top))
const effectiveLeft = computed(() => (isRoot.value ? selfLeft.value : props.left))
const placed = computed(() =>
  effectiveTop.value != null && effectiveLeft.value != null &&
  nodeSize.w > 0 && nodeSize.h > 0
)
const nodeStyle = computed(() => ({
  top: (effectiveTop.value ?? 0) + 'px',
  left: (effectiveLeft.value ?? 0) + 'px',
  visibility: placed.value ? 'visible' : 'hidden',
}))

// The vertical scope children clamp their rail to. When THIS panel is
// depth-hidden its own bounds are meaningless, so pass the inherited scope
// through unchanged — the shallowest visible descendant then falls back to its
// own center, which is the anchor it should inherit.
const childBridgeTop = computed(() => (isDepthHidden.value ? props.bridgeTop : panelTopPx.value))
const childBridgeBottom = computed(() => (isDepthHidden.value ? props.bridgeBottom : panelBottomPx.value))

// ── Button-drift: prefer own center, clamp within the parent's bounds ──
const railCenterViewport = computed(() => {
  const c = ownCenter.value
  if (c == null) return null
  if (props.bridgeTop == null || props.bridgeBottom == null) return c
  return Math.min(Math.max(c, props.bridgeTop), props.bridgeBottom)
})

// Wrapper-relative Y for the rail (null → fall back to CSS top:50%).
const railCenterLocal = computed(() => {
  const rcv = railCenterViewport.value
  const wt = wrapperTopPx.value
  if (rcv == null || wt == null) return null
  return rcv - wt
})

const actionsStyle = computed(() => {
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
function setupObserver() {
  if (typeof ResizeObserver === 'undefined') return
  if (panelEl.value) {
    driftObserver = new ResizeObserver(() => measureSelf())
    driftObserver.observe(panelEl.value)
  }
  if (tabsEl.value) {
    tabsObserver = new ResizeObserver(() => measureTabs())
    tabsObserver.observe(tabsEl.value)
  }
  measureSelf()
  measureTabs()
}

function onResize() {
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

// ── Width reporting for horizontal fit (viewport-aware panel limit) ──
const registerPanel = inject('registerPanel', null)
const setPanelWidth = inject('setPanelWidth', null)
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

// Closes THIS panel (removes it from the parent's children list).
function closeSelf() {
  if (props.onClose) props.onClose()
}

// Replaces THIS panel with another spec in the parent's children list.
function replaceSelf(spec) {
  if (props.onReplace) props.onReplace(spec)
}

// ── Panel navigation context for the component in this panel's slot ──
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

/* Chip strip: collapsed siblings as compact tabs, wrapping right-to-left. */
.panel-tabs {
  position: absolute;
  display: flex;
  flex-wrap: wrap-reverse;
  justify-content: flex-end;
  gap: 4px;
  pointer-events: auto;
}
.panel-chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 3px 8px;
  font-size: 11px;
  border-radius: 6px;
  background: var(--bg-panel, rgba(10,10,20,0.92));
  border: 1px solid rgba(255,255,255,0.12);
  cursor: pointer;
  white-space: nowrap;
}
.panel-chip:hover { background: rgba(255,255,255,0.08); }
.chip-expand { color: var(--text-dim); font-size: 11px; }
.chip-title {
  color: var(--text-dim);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  font-weight: 600;
  font-size: 11px;
}
.chip-btn {
  background: none; border: none; color: var(--text-dim);
  cursor: pointer; font-size: 12px; padding: 0 2px; line-height: 1;
}
.chip-btn:hover { color: var(--text); }

.panel {
  display: inline-flex;
  flex-direction: column;
  background: var(--bg-panel, rgba(10,10,20,0.92));
  backdrop-filter: blur(12px);
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: 8px;
  /* Variable width: content-driven, floored and capped. */
  min-width: 260px;
  max-width: var(--gm-panel-max-w, 440px);
  max-height: calc(100vh - 40px);
  overflow: auto;
}

/* Panel action rail: vertical column of icon buttons outside the panel's
   right edge (close, collapse/expand, and later detach/drag). */
.panel-actions {
  position: absolute; top: 50%; right: -22px; transform: translateY(-50%); z-index: 2;
  display: flex; flex-direction: column; gap: 4px;
}
.panel-action-btn {
  width: 36px; height: 36px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  font-size: 14px; padding: 0;
  background: var(--bg-panel); backdrop-filter: blur(12px);
  border: 1px solid rgba(255,255,255,0.15);
  cursor: pointer;
}
.panel-action-btn:hover { background: rgba(255,255,255,0.1); }

.panel-header {
  display: flex;
  align-items: center;
  padding: 8px 12px;
  border-bottom: 1px solid rgba(255,255,255,0.06);
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
.panel-id-btn {
  flex-shrink: 0;
  font-family: monospace;
  font-size: 11px;
  font-weight: 600;
  color: var(--text-dim);
  background: transparent;
  border: 1px solid rgba(255,255,255,0.12);
  border-radius: 4px;
  padding: 1px 7px;
  line-height: 1.4;
  cursor: pointer;
}
.panel-id-btn:hover { color: var(--text); border-color: rgba(255,255,255,0.25); background: rgba(255,255,255,0.05); }

.panel-body {
  flex: 1; overflow-y: auto; padding: 10px;
}
</style>
