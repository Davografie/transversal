<template>
  <g class="life-path-edge">
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
        class="vue-flow__arrowhead"
        viewBox="-10 -10 20 20"
        refX="0"
        refY="0"
        markerWidth="12.5"
        markerHeight="12.5"
        markerUnits="strokeWidth"
        orient="auto"
      >
        <polyline
          points="-5,-4 0,0 -5,4 -5,-4"
          stroke="#4088d4"
          fill="#4088d4"
          stroke-width="1"
          stroke-linecap="round"
          stroke-linejoin="round"
        />
      </marker>
    </defs>
    <path
      :d="path"
      fill="none"
      :stroke="`url(#${gradientId})`"
      stroke-width="2"
      :stroke-dasharray="isBack ? '6 5' : undefined"
      :marker-end="`url(#${arrowId})`"
    />
    <EdgeLabelRenderer>
      <div
        v-if="label"
        class="life-path-edge-label"
        :class="{ back: isBack }"
        :style="{ transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)` }"
      >{{ label }}</div>
    </EdgeLabelRenderer>
  </g>
</template>

<script setup>
import { computed } from 'vue'
import { EdgeLabelRenderer } from '@vue-flow/core'
import { asymmetricBezierPath } from '@/composables/useEdgeStyle.js'

const props = defineProps({
  id: { type: String, required: true },
  sourceX: { type: Number, required: true },
  sourceY: { type: Number, required: true },
  targetX: { type: Number, required: true },
  targetY: { type: Number, required: true },
  sourcePosition: { type: String, required: true },
  targetPosition: { type: String, required: true },
  label: { type: String, default: '' },
  data: { type: Object, default: () => ({}) },
})

const isBack = computed(() => props.data?.kind === 'back')
const gradientId = computed(() => `lpe-grad-${props.id.replace(/[^a-zA-Z0-9-]/g, '-')}`)
const arrowId = computed(() => `lpe-arrow-${props.id.replace(/[^a-zA-Z0-9-]/g, '-')}`)

const pathData = computed(() =>
  asymmetricBezierPath({
    sourceX: props.sourceX,
    sourceY: props.sourceY,
    sourcePosition: props.sourcePosition,
    targetX: props.targetX,
    targetY: props.targetY,
    targetPosition: props.targetPosition,
  }),
)

const path = computed(() => pathData.value[0])
const labelX = computed(() => pathData.value[1])
const labelY = computed(() => pathData.value[2])
</script>

<style scoped>
.life-path-edge-label {
  position: absolute;
  pointer-events: none;
  font-size: 10px;
  color: var(--text);
  background: rgba(10, 10, 15, 0.85);
  padding: 1px 5px;
  border-radius: 3px;
  white-space: nowrap;
}
.life-path-edge-label.back {
  color: #e88830;
  border: 1px solid rgba(232, 136, 48, 0.4);
}
</style>
