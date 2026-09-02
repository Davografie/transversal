<template>
  <div ref="wrapperEl" class="panel-node" :class="{ nested }" :style="nodeStyle">
    <div ref="actionsEl" class="panel-actions" :style="actionsStyle" v-show="!isDepthHidden">
      <button v-if="closable" class="panel-action-btn" title="Close" @click="$emit('close')">×</button>
      <button type="button" class="panel-action-btn" :title="isCollapsed ? 'Expand' : 'Collapse'" @click="toggleCollapse()">{{ isCollapsed ? '▸' : '▾' }}</button>
    </div>
    <!-- ⚠ Depth hiding uses visibility:hidden (NOT v-show/display:none) so the
         panel keeps its measured size/position. With display:none the rect
         collapses to zero and the whole geometry chain (child stacking + the
         button-drift bridge) zeroes out, which sends deeper panels' buttons
         flying off the top of the viewport. -->
    <div ref="panelEl" class="panel" :style="panelVisibilityStyle">
      <header v-if="title" class="panel-header">
        <slot name="header">
          <span class="panel-title">{{ title }}</span>
          <button v-if="id" type="button" class="panel-id-btn" :title="copied ? 'Copied!' : 'Copy ID'" @click="copyId">{{ copied ? '✓' : '#' }}</button>
        </slot>
      </header>
      <div class="panel-body" v-show="!isCollapsed">
        <slot />
      </div>
    </div>
    <!-- Self-reference: each child is a sibling Panel owned by THIS panel's
         children list. Children are positioned absolutely (out of flow) so the
         parent's own position is never influenced by them; only the children's
         offsets and their action-rail positions depend on the parent.
         :on-close / :on-replace let the child remove/replace itself in this
         list; @close handles the child's own × button. -->
    <div class="panel-children" v-show="!isCollapsed">
      <Panel
        v-for="c in children"
        :key="c.key"
        nested
        :depth="depth + 1"
        :min-visible-depth="minVisibleDepth"
        :title="c.spec.title"
        :id="c.spec.id"
        :collapsed="collapsedKeys.includes(c.key)"
        :direction="direction"
        :gap="gap"
        :top="childPositions[c.key]?.top ?? null"
        :left="childPositions[c.key]?.left ?? null"
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
// Same rule applies to the children list.
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

// Keys of THIS panel's children that are collapsed. Owned here so the parent
// can auto-collapse the oldest siblings when the vertical stack overflows.
const collapsedKeys = ref([])
// The child that should stay expanded: the last one opened or manually expanded.
const activeKey = ref(null)

function toggleChildCollapse(key) {
  const wasCollapsed = collapsedKeys.value.includes(key)
  if (wasCollapsed) {
    collapsedKeys.value = collapsedKeys.value.filter((k) => k !== key)
    activeKey.value = key // user expanded it → it becomes the active (protected) one
  } else {
    collapsedKeys.value = [...collapsedKeys.value, key]
  }
  panelLog('toggle-child', { key, action: wasCollapsed ? 'expand' : 'collapse' })
}

// ── Measurement + positioning ─────────────────────────
const panelEl = ref(null)
const actionsEl = ref(null)
const wrapperEl = ref(null)

const isRoot = computed(() => !props.nested)

// Depth-based hiding (viewport-aware panel limit). A shallow panel that's hidden
// is fully removed from layout (display:none) so it takes no horizontal space and
// the chain re-anchors rightward toward the toggle. Its children still render and
// inherit the anchor via the pass-through bridge below.
const isDepthHidden = computed(() => !!(props.minVisibleDepth && props.depth < props.minVisibleDepth))
const panelVisibilityStyle = computed(() => (isDepthHidden.value ? { display: 'none' } : {}))

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

// ── Child sizes + layout ──────────────────────────────
const childSizes = reactive({})

function recordChildSize(key, w, h) {
  const cur = childSizes[key]
  if (cur && cur.w === w && cur.h === h) return
  childSizes[key] = { w, h }
}

// Assign each child an absolute offset (relative to THIS node) so siblings
// stack along the perpendicular axis, centered on the parent's own center.
// Only the parent's center/height and the children's measured sizes feed this —
// never the other way around, which is what keeps the parent position frozen.
const childPositions = computed(() => {
  const positions = {}
  const list = children.value
  const n = list.length
  const sizes = list.map((c) => childSizes[c.key] || { w: 0, h: 0 })
  let totalH = 0
  for (const s of sizes) totalH += s.h
  totalH += props.gap * Math.max(0, n - 1)
  const stackTopLocal = nodeSize.h / 2 - totalH / 2
  let acc = 0
  list.forEach((c, i) => {
    const s = sizes[i]
    if (props.direction === 'left') {
      positions[c.key] = { top: stackTopLocal + acc, left: -(s.w + props.gap) }
    } else {
      // TODO(Phase 2): other directions.
      positions[c.key] = { top: stackTopLocal + acc, left: nodeSize.w + props.gap }
    }
    acc += s.h + props.gap
  })
  return positions
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
// Direct getBoundingClientRect reads (not useElementBounding) so values stay
// fresh when the whole stack re-centers via transform — which ResizeObserver
// alone misses. Refreshed by a ResizeObserver + the layout watchers below.
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
// Enable in the browser console with `window.__PANEL_DEBUG__ = true`, then
// interact. Each panel logs its own viewport rects so layout issues can be
// deduced from the numbers instead of described.
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
    pos: { top: effectiveTop.value, left: effectiveLeft.value },
    size: { w: nodeSize.w, h: nodeSize.h },
    panel: rectOf(panelEl.value),
    actions: rectOf(actionsEl.value),
    buttons: buttonsOf(actionsEl.value),
    collapsedKeys: [...collapsedKeys.value],
    children: children.value.map((c) => ({ key: c.key, title: c.spec.title, id: c.spec.id, pos: childPositions.value[c.key] })),
    ...detail,
  }))
}

// ── Auto-collapse on vertical overflow ──────────────
// Collapses the oldest expanded child that is NOT the active one, until the
// sibling stack fits within the viewport height. This gives round-robin
// behavior: expanding an older panel makes it active and collapses the then-
// oldest expanded sibling instead.
const AUTO_COLLAPSE_MARGIN = 40

function stackHeight() {
  const list = children.value
  let h = 0
  for (const c of list) h += childSizes[c.key]?.h ?? 0
  return h + props.gap * Math.max(0, list.length - 1)
}

function autoCollapse() {
  if (stackHeight() <= viewHeight.value - AUTO_COLLAPSE_MARGIN) return
  const list = children.value
  for (let i = 0; i < list.length; i++) {
    const key = list[i].key
    if (key === activeKey.value) continue
    if (!collapsedKeys.value.includes(key)) {
      collapsedKeys.value = [...collapsedKeys.value, key]
      panelLog('auto-collapse', { collapsedKey: key })
      return // one at a time; the reactive height change re-triggers the watcher
    }
  }
}

let driftObserver = null
function setupObserver() {
  if (typeof ResizeObserver === 'undefined' || !panelEl.value) return
  driftObserver = new ResizeObserver(() => measureSelf())
  driftObserver.observe(panelEl.value)
  measureSelf()
}

function onResize() {
  viewHeight.value = window.innerHeight
  measureSelf()
}

onMounted(() => {
  if (registerPanel) panelUid = registerPanel(props.depth)
  setupObserver()
  window.addEventListener('resize', onResize)
})
onUnmounted(() => {
  if (driftObserver) driftObserver.disconnect()
  window.removeEventListener('resize', onResize)
  if (unregisterPanel && panelUid != null) unregisterPanel(props.depth, panelUid)
})

watch([children, collapsedKeys, viewHeight], () => nextTick(() => {
  autoCollapse()
  measureSelf()
}))
// The sibling stack re-centers (or this panel is re-anchored) without a size
// change, which ResizeObserver alone misses — re-measure on position change so
// the action rail follows the panel instead of stranding at the pre-move spot.
watch([effectiveTop, effectiveLeft], () => nextTick(measureSelf))
watch(childSizes, () => nextTick(autoCollapse), { deep: true })
watch(() => props.anchor, () => { if (isRoot.value) computeRootPosition() })

// ── Width reporting for horizontal fit (viewport-aware panel limit) ──
// PanelStack tracks per-depth widths to decide how many shallow levels to hide.
const registerPanel = inject('registerPanel', null)
const setPanelWidth = inject('setPanelWidth', null)
const unregisterPanel = inject('unregisterPanel', null)
let panelUid = null

function normalizeSpec(spec) {
  return { ...spec, component: markRaw(spec.component) }
}

// Opens a child panel. Default is parallel: append as a sibling. If a child
// with the same component + id is already open, replace (refresh) it instead,
// keeping its key/position so its local state survives.
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
   shrink-to-fits around that box; `.panel-actions` and child `.panel-node`s are
   absolutely positioned (out of flow) and therefore never affect the parent. */
.panel-node {
  position: absolute;
  pointer-events: auto;
}

/* Static wrapper whose children are absolutely positioned relative to
   .panel-node (the nearest positioned ancestor). v-show hides the whole
   child stack when this panel is collapsed, without affecting the parent. */
.panel-children {
  /* static; children are out of flow */
}

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
