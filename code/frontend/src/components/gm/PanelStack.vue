<template>
  <div class="panel-stack">
    <Panel
      v-for="(panel, i) in panels"
      :key="panel.id"
      :class="{ 'stack-active': i === panels.length - 1 }"
      @close="$emit('close', i)"
    >
      <slot v-if="!panel.component && (panel.id === 'inspect' || panel.id === 'edit' || panel.id === 'create')" name="entity" />
      <slot v-else-if="!panel.component && panel.id === 'gm'" name="gm" />
      <component v-else :is="panel.component" v-bind="panel.props || {}" @select="$emit('select', $event)" @save="$emit('save', $event)" @add-trait="$emit('add-trait', $event)" />
    </Panel>
  </div>
</template>

<script setup>
import Panel from './Panel.vue'

defineProps({
  panels: { type: Array, default: () => [] },
})
defineEmits(['close'])
</script>

<style scoped>
.panel-stack {
  position: fixed; top: 50%; right: 36px; transform: translateY(-50%); z-index: 25;
  display: flex; flex-direction: row-reverse; align-items: center; gap: 8px;
  pointer-events: none;
}
.panel-stack > * {
  pointer-events: auto;
}

@media (max-width: 720px) {
  .panel-stack {
    right: 8px; flex-direction: column; gap: 0;
  }
  .stack-active { display: block; }
}
</style>
