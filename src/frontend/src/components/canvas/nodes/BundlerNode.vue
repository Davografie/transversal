<template>
  <div class="bundler-node" :title="title">
    <span class="bd-count">{{ data.count }}</span>
    <Handle id="in" type="target" :position="Position.Left" />
    <Handle id="out" type="source" :position="Position.Right" />
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { Handle, Position } from '@vue-flow/core'

const props = defineProps({
  id: { type: String, required: true },
  data: { type: Object, required: true },
  selected: { type: Boolean, default: false },
})

const title = computed(() =>
  (props.data.labels || []).length ? props.data.labels.join(' · ') : `${props.data.count} entries`,
)
</script>

<style scoped>
.bundler-node {
  position: relative;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: #2dd4a8;
  border: 2px solid #0a0a0f;
  box-shadow: 0 0 6px rgba(45, 212, 168, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
}
.bd-count {
  font-size: 9px;
  font-weight: 700;
  color: #0a0a0f;
  line-height: 1;
}
</style>
