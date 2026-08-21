<template>
  <div class="panel-wrapper" :class="{ nested }">
    <!-- ⚠ v-show is on .panel (this panel's content) NOT on .panel-wrapper.
         If it were on the wrapper, nested child Panels would also be hidden.
         We want shallow panels to hide their content while their deeper
         children remain visible beside them. -->
    <div class="panel" v-show="!minVisibleDepth || depth >= minVisibleDepth">
      <header v-if="title || closable" class="panel-header">
        <slot name="header">
          <span v-if="title" class="panel-title">{{ title }}</span>
        </slot>
        <button v-if="closable" class="panel-close" @click="$emit('close')" title="Close" aria-label="Close">✕</button>
      </header>
      <div class="panel-body">
        <slot />
      </div>
    </div>
    <!-- Self-reference: nested child panel.
         :on-close / :on-replace let the nested Panel close/replace itself
         in THIS panel's stack. @close handles the nested Panel's own × button. -->
    <Panel
      v-if="child"
      nested
      :depth="depth + 1"
      :min-visible-depth="minVisibleDepth"
      :title="child.title"
      closable
      :on-close="() => { child = null }"
      :on-replace="(spec) => { child = normalizeSpec(spec) }"
      @close="child = null"
    >
      <template #default>
        <component :is="child.component" v-bind="child.props || {}" v-on="child.listeners || {}" @close="child = null" />
      </template>
    </Panel>
  </div>
</template>

<script setup>
import { shallowRef, nextTick, markRaw, inject, provide, onMounted, onUnmounted } from 'vue'
import { panelKey } from '@/composables/usePanel.js'

const props = defineProps({
  title: { type: String, default: '' },
  closable: { type: Boolean, default: false },
  nested: { type: Boolean, default: false },
  depth: { type: Number, default: 0 },
  minVisibleDepth: { type: Number, default: 0 },
  // Callbacks supplied by the parent Panel so this Panel can close/replace
  // itself in the parent's stack.
  onClose: { type: Function, default: null },
  onReplace: { type: Function, default: null },
})

defineEmits(['close'])

// ⚠ shallowRef — must NOT be ref() because Vue deeply unwraps nested refs inside
// reactive objects. If child.props contains computed refs (e.g. filteredTraitsets),
// ref() would unwrap them to plain values, breaking reactivity for sub-panels.
const child = shallowRef(null)

// ── Depth tracking for viewport-aware visibility ──
const registerDepth = inject('registerDepth', null)
const unregisterDepth = inject('unregisterDepth', null)

onMounted(() => { if (registerDepth) registerDepth(props.depth) })
onUnmounted(() => { if (unregisterDepth) unregisterDepth(props.depth) })

function normalizeSpec(spec) {
  return { ...spec, component: markRaw(spec.component) }
}

// Opens a child Panel. The spec.component is markRaw'd to prevent Vue from
// making the component definition reactive (triggers "Component made reactive" warning).
// Setting child=null then reassigning on nextTick ensures the leave transition
// (if any) plays before the new panel enters.
function openChild(spec) {
  child.value = null
  nextTick(() => { child.value = normalizeSpec(spec) })
}

// Closes the current child Panel (pops the stack).
function closeChild() {
  child.value = null
}

// Closes THIS panel (removes it from the parent's stack).
function closeSelf() {
  if (props.onClose) props.onClose()
}

// Replaces THIS panel with another spec in the parent's stack.
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
  align-items: center;
  gap: 8px;
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

/* Nested panel sits beside parent in the flex row */
.nested {
  position: relative;
  margin-left: 8px;
}

.panel-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px 6px 12px;
  border-bottom: 1px solid rgba(255,255,255,0.06);
  flex-shrink: 0;
}
.panel-title {
  flex: 1;
  font-size: 12px; font-weight: 600; color: var(--text-dim);
  text-transform: uppercase; letter-spacing: 0.5px;
}
.panel-close {
  flex: 0 0 auto;
  margin-left: auto;
  width: 44px; height: 44px;
  border-radius: 8px;
  display: flex; align-items: center; justify-content: center;
  font-size: 18px; padding: 0;
  background: transparent;
  border: 1px solid transparent;
  color: var(--text-dim);
  cursor: pointer;
}
.panel-close:hover { background: rgba(255,255,255,0.08); color: var(--text); }

.panel-body {
  flex: 1; overflow-y: auto; padding: 10px;
}
</style>
