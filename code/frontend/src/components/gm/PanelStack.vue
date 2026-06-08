<template>
  <div class="panel-stack">
    <Panel
      v-for="(panel, i) in panels"
      :key="panel.id"
      :class="{ 'stack-active': i === panels.length - 1 }"
      @close="$emit('close', i)"
    >
      <component :is="panel.component" v-bind="panel.props || {}" />
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
  position: fixed; top: 50%; right: 370px; transform: translateY(-50%); z-index: 25;
  display: flex; flex-direction: row-reverse; align-items: center; gap: 24px;
}

@media (max-width: 720px) {
  .panel-stack {
    right: 8px; flex-direction: column; gap: 0;
  }
  .stack-active { display: block; }
}
</style>
