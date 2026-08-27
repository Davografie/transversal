<template>
  <div class="panel-wrapper" :class="{ nested }">
    <div ref="actionsEl" class="panel-actions">
      <button v-if="closable" class="panel-action-btn" title="Close" @click="$emit('close')">×</button>
      <button type="button" class="panel-action-btn" :title="isCollapsed ? 'Expand' : 'Collapse'" @click="toggleCollapse()">{{ isCollapsed ? '▸' : '▾' }}</button>
    </div>
    <!-- ⚠ v-show is on .panel (this panel's content) NOT on .panel-wrapper.
         If it were on the wrapper, nested child Panels would also be hidden.
         We want shallow panels to hide their content while their deeper
         children remain visible beside them. -->
    <div ref="panelEl" class="panel" v-show="!minVisibleDepth || depth >= minVisibleDepth">
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
         children list. :on-close / :on-replace let the child remove/replace
         itself in this list; @close handles the child's own × button. -->
    <div ref="siblingsEl" class="panel-siblings" v-show="!isCollapsed">
      <Panel
        v-for="c in children"
        :key="c.key"
        nested
        :depth="depth + 1"
        :min-visible-depth="minVisibleDepth"
        :title="c.spec.title"
        :id="c.spec.id"
        :collapsed="collapsedKeys.includes(c.key)"
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
import { shallowRef, ref, computed, markRaw, inject, provide, onMounted, onUnmounted, nextTick, watch } from 'vue'
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

// ── Diagnostic logging (opt-in) ─────────────────────
// Enable in the browser console with `window.__PANEL_DEBUG__ = true`, then
// interact. Each panel logs its own viewport rects so layout issues can be
// deduced from the numbers instead of described.
const panelEl = ref(null)
const actionsEl = ref(null)
const siblingsEl = ref(null)

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
    panel: rectOf(panelEl.value),
    siblings: rectOf(siblingsEl.value),
    actions: rectOf(actionsEl.value),
    buttons: buttonsOf(actionsEl.value),
    collapsedKeys: [...collapsedKeys.value],
    children: children.value.map((c) => ({ key: c.key, title: c.spec.title, id: c.spec.id })),
    ...detail,
  }))
}

// ── Auto-collapse on vertical overflow ──────────────
// Collapses the oldest expanded child that is NOT the active one, until the
// sibling column fits within the viewport height. This gives round-robin
// behavior: expanding an older panel makes it active and collapses the then-
// oldest expanded sibling instead.
const viewHeight = ref(window.innerHeight)
const AUTO_COLLAPSE_MARGIN = 40

function onResize() { viewHeight.value = window.innerHeight }
onMounted(() => { window.addEventListener('resize', onResize) })
onUnmounted(() => { window.removeEventListener('resize', onResize) })

function autoCollapse() {
  const el = siblingsEl.value
  if (!el) return
  if (el.offsetHeight <= viewHeight.value - AUTO_COLLAPSE_MARGIN) return
  const list = children.value
  for (let i = 0; i < list.length; i++) {
    const key = list[i].key
    if (key === activeKey.value) continue
    if (!collapsedKeys.value.includes(key)) {
      collapsedKeys.value = [...collapsedKeys.value, key]
      panelLog('auto-collapse', { collapsedKey: key })
      return // one at a time; the reactive height change re-triggers this watcher
    }
  }
}

watch([children, collapsedKeys, viewHeight], () => nextTick(autoCollapse))

// ── Depth tracking for viewport-aware visibility ──
const registerDepth = inject('registerDepth', null)
const unregisterDepth = inject('unregisterDepth', null)

onMounted(() => { if (registerDepth) registerDepth(props.depth) })
onUnmounted(() => { if (unregisterDepth) unregisterDepth(props.depth) })

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
.panel-wrapper {
  position: relative;
  flex-shrink: 0;
  display: flex;
  flex-direction: row-reverse;
  align-items: flex-start;
  gap: 8px;
}

/* Siblings (children of the same panel) stack vertically at their depth,
   to the left of the parent in the row-reverse layout. */
.panel-siblings {
  display: flex;
  flex-direction: column;
  gap: 8px;
  flex-shrink: 0;
}

.panel {
  display: flex;
  flex-direction: column;
  background: var(--bg-panel, rgba(10,10,20,0.92));
  backdrop-filter: blur(12px);
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: 8px;
  min-width: 260px;
  max-width: 380px;
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

/* Nested panel sits beside parent in the flex row */
.nested {
  position: relative;
}

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
