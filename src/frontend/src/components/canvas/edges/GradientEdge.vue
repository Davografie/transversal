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
        class="vue-flow__arrowhead"
        viewBox="-10 -10 20 20"
        refX="0"
        refY="0"
        markerWidth="12.5"
        markerHeight="12.5"
        markerUnits="strokeWidth"
        orient="auto-start-reverse"
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
import { EdgeLabelRenderer } from '@vue-flow/core'

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

const SOURCE_CURVATURE = 0.05 // shallow near the source
const TARGET_CURVATURE = 0.28 // steep near the target

const pathData = computed(() => {
  const { sourceX, sourceY, targetX, targetY } = props
  const dx = targetX - sourceX
  const dy = targetY - sourceY
  const len = Math.hypot(dx, dy) || 1

  // Consistent perpendicular (left of the source→target vector), so mutual
  // edges curve away from each other instead of overlapping.
  const ux = -dy / len
  const uy = dx / len

  const sourceOffset = SOURCE_CURVATURE * len
  const targetOffset = TARGET_CURVATURE * len

  const scx = sourceX + ux * sourceOffset
  const scy = sourceY + uy * sourceOffset
  // Opposite side of the target → S-shaped rather than C-shaped.
  const tcx = targetX - ux * targetOffset
  const tcy = targetY - uy * targetOffset

  const path = `M${sourceX},${sourceY} C${scx},${scy} ${tcx},${tcy} ${targetX},${targetY}`
  // Bezier midpoint (t = 0.5) for the label.
  const labelX = sourceX * 0.125 + scx * 0.375 + tcx * 0.375 + targetX * 0.125
  const labelY = sourceY * 0.125 + scy * 0.375 + tcy * 0.375 + targetY * 0.125
  return [path, labelX, labelY]
})

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
