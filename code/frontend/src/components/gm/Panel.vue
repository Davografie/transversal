<template>
  <div class="panel-wrapper" :class="{ nested }">
    <button v-if="closable" class="panel-close" @click="$emit('close')">×</button>
    <div class="panel" v-show="!minVisibleDepth || depth >= minVisibleDepth">
      <header v-if="title" class="panel-header">
        <slot name="header">
          <span class="panel-title">{{ title }}</span>
        </slot>
      </header>
      <div class="panel-body">
        <slot :open="openChild" :close="closeChild" />
      </div>
    </div>
    <!-- Self-reference: nested child panel -->
    <Panel
      v-if="child"
      nested
      :depth="depth + 1"
      :min-visible-depth="minVisibleDepth"
      :title="child.title"
      closable
      @close="child = null"
    >
      <template #default="{ open: childOpen }">
        <component :is="child.component" v-bind="child.props || {}" :open="childOpen" :close="() => { child = null }" v-on="child.listeners || {}" @close="child = null" />
      </template>
    </Panel>
  </div>
</template>

<script setup>
import { shallowRef, nextTick, markRaw, inject, onMounted, onUnmounted } from 'vue'

const props = defineProps({
  title: { type: String, default: '' },
  closable: { type: Boolean, default: false },
  nested: { type: Boolean, default: false },
  depth: { type: Number, default: 0 },
  minVisibleDepth: { type: Number, default: 0 },
})

defineEmits(['close'])

const child = shallowRef(null)

// ── Depth tracking for viewport-aware visibility ──
const registerDepth = inject('registerDepth', null)
const unregisterDepth = inject('unregisterDepth', null)

onMounted(() => { if (registerDepth) registerDepth(props.depth) })
onUnmounted(() => { if (unregisterDepth) unregisterDepth(props.depth) })

function openChild(spec) {
  child.value = null
  nextTick(() => { child.value = { ...spec, component: markRaw(spec.component) } })
}

function closeChild() {
  child.value = null
}
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

/* Close button: outside the panel, between this and the previous panel */
.panel-close {
  position: absolute; top: 50%; right: -22px; transform: translateY(-50%); z-index: 2;
  width: 36px; height: 36px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  font-size: 14px; padding: 0;
  background: var(--bg-panel); backdrop-filter: blur(12px);
  border: 1px solid rgba(255,255,255,0.15);
  cursor: pointer;
}
.panel-close:hover { background: rgba(255,255,255,0.1); }

/* Nested panel covers parent on mobile */
.nested {
  position: absolute; inset: 0; z-index: 2;
}
.nested .panel {
  border-radius: 0; border: none; max-width: none;
}

.panel-header {
  display: flex;
  align-items: center;
  padding: 8px 12px;
  border-bottom: 1px solid rgba(255,255,255,0.06);
  flex-shrink: 0;
}
.panel-title {
  font-size: 12px; font-weight: 600; color: var(--text-dim);
  text-transform: uppercase; letter-spacing: 0.5px;
}

.panel-body {
  flex: 1; overflow-y: auto; padding: 10px;
}

/* Desktop: nested panels slide in beside parent */
@media (min-width: 721px) {
  .nested {
    position: relative;
    margin-left: 8px;
  }
  .nested .panel {
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 8px;
    max-width: 380px;
  }
}
</style>

