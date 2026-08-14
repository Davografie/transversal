<template>
  <g class="gradient-edge">
    <defs>
      <linearGradient
        :id="gradientId"
        :x1="sourceX"
        :y1="sourceY"
        :x2="targetX"
        :y2="targetY"
        gradientUnits="userSpaceOnUse"
      >
        <stop offset="0%" stop-color="#e88830" />
        <stop offset="100%" stop-color="#4088d4" />
      </linearGradient>
      <marker
        :id="arrowId"
        viewBox="0 0 12 12"
        refX="10"
        refY="6"
        markerWidth="12"
        markerHeight="12"
        orient="auto"
      >
        <path d="M0,0 L0,12 L12,6 z" fill="#4088d4" />
      </marker>
    </defs>
    <path
      :d="path"
      fill="none"
      :stroke="`url(#${gradientId})`"
      stroke-width="2"
      :marker-end="`url(#${arrowId})`"
    />
    <EdgeLabelRenderer>
      <div
        v-if="label"
        class="gradient-edge-label"
        :style="{ transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)` }"
      >{{ label }}</div>
    </EdgeLabelRenderer>
  </g>
</template>

<script setup>
import { computed } from 'vue'
import { getBezierPath, EdgeLabelRenderer } from '@vue-flow/core'

const props = defineProps({
  id: { type: String, required: true },
  sourceX: { type: Number, required: true },
  sourceY: { type: Number, required: true },
  targetX: { type: Number, required: true },
  targetY: { type: Number, required: true },
  sourcePosition: { type: String, required: true },
  targetPosition: { type: String, required: true },
  label: { type: String, default: '' },
})

const gradientId = computed(() => `gradient-${props.id.replace(/[^a-zA-Z0-9-]/g, '-')}`)
const arrowId = computed(() => `${gradientId.value}-arrow`)

const pathData = computed(() => getBezierPath({
  sourceX: props.sourceX,
  sourceY: props.sourceY,
  sourcePosition: props.sourcePosition,
  targetX: props.targetX,
  targetY: props.targetY,
  targetPosition: props.targetPosition,
}))

const path = computed(() => pathData.value[0])
const labelX = computed(() => pathData.value[1])
const labelY = computed(() => pathData.value[2])
</script>

<style scoped>
.gradient-edge-label {
  position: absolute;
  pointer-events: none;
  font-size: 10px;
  color: var(--text);
  background: rgba(10, 10, 15, 0.85);
  padding: 1px 5px;
  border-radius: 3px;
  white-space: nowrap;
}
</style>
