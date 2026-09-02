<script setup>
import { ref, watch, onMounted, onBeforeUnmount } from 'vue'
import { RESONANCE, groupByTraitsetDie, sampleAt, totalAmplitude } from '@/composables/resonance.js'
import { drawResonanceFrame } from '@/composables/renderResonance.js'

/**
 * WaveformDivider — a section break whose edge is the entity's linear
 * resonance "tangle" at a given collapse progress. It reuses the same renderer
 * as the Resonance Lab (non-periodic frequencies), fills the top/bottom colors
 * around the composite curve, and drifts continuously via the renderer's own
 * time-based drift. This is per-frame (like the Lab), not a pre-rendered mask,
 * so it matches the exact non-periodic look.
 */
const props = defineProps({
  osc: { type: Array, default: () => [] },
  height: { type: Number, default: 120 },
  colorTop: { type: String, default: '#1b1b28' },
  colorBottom: { type: String, default: '#2ac6a0' },
  progress: { type: Number, default: 0.715 },
  mode: { type: String, default: RESONANCE.mode },
  renderDivisor: { type: Number, default: RESONANCE.renderDivisor },
  drift: { type: Number, default: RESONANCE.drift },
  collapseFraction: { type: Number, default: RESONANCE.collapseFraction },
  transformFraction: { type: Number, default: RESONANCE.transformFraction },
  expandFraction: { type: Number, default: RESONANCE.expandFraction },
  animate: { type: Boolean, default: true },
})

const canvasEl = ref(null)
let rafId = null
const isMobile = typeof window !== 'undefined' && (window.matchMedia?.('(pointer: coarse)').matches || window.innerWidth < 640)

function draw(now) {
  const canvas = canvasEl.value
  if (!canvas) return
  const dpr = isMobile ? 1 : Math.min(window.devicePixelRatio || 1, 1.5)
  const w = canvas.clientWidth || 320
  const h = canvas.clientHeight || props.height
  if (w <= 0 || h <= 0) return
  if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(h * dpr)) {
    canvas.width = Math.round(w * dpr)
    canvas.height = Math.round(h * dpr)
  }
  const ctx = canvas.getContext('2d')
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
  ctx.clearRect(0, 0, w, h)

  // Bottom region (below the composite edge).
  ctx.fillStyle = props.colorBottom
  ctx.fillRect(0, 0, w, h)

  // Top region (above the composite curve) — the clip edge.
  const groups = groupByTraitsetDie(props.osc)
  const total = totalAmplitude(groups, [])
  const baseDrift = props.drift * (now / 1000)
  const ampScale = h / 2 - 2
  const N = isMobile ? 96 : 160
  ctx.beginPath()
  ctx.moveTo(0, 0)
  for (let i = 0; i <= N; i++) {
    const t = i / N
    const v = total > 0 ? sampleAt(groups, t / props.renderDivisor + baseDrift) / total : 0
    ctx.lineTo(t * w, h / 2 - v * ampScale)
  }
  ctx.lineTo(w, 0)
  ctx.closePath()
  ctx.fillStyle = props.colorTop
  ctx.fill()

  // Tangle lines (component dice/groups converging at `progress`).
  drawResonanceFrame(ctx, w, h, props.osc, props.osc, props.progress, {
    mode: props.mode,
    layout: 'linear',
    renderDivisor: props.renderDivisor,
    drift: props.drift,
    collapseFraction: props.collapseFraction,
    transformFraction: props.transformFraction,
    expandFraction: props.expandFraction,
    lowQuality: isMobile,
    timeMs: now,
  })
}

function loop(now) {
  draw(now)
  rafId = requestAnimationFrame(loop)
}

onMounted(() => {
  if (props.animate) {
    rafId = requestAnimationFrame(loop)
  } else {
    draw(performance.now())
  }
})

onBeforeUnmount(() => {
  if (rafId) cancelAnimationFrame(rafId)
})

watch(
  () => [props.osc, props.progress, props.height, props.renderDivisor, props.drift, props.collapseFraction, props.transformFraction, props.expandFraction],
  () => { if (!props.animate) draw(performance.now()) },
)
</script>

<template>
  <div class="wd" :style="{ height: height + 'px' }">
    <canvas ref="canvasEl" class="wd-canvas"></canvas>
  </div>
</template>

<style scoped>
.wd {
  position: relative;
  width: 100%;
  overflow: hidden;
}
.wd-canvas {
  display: block;
  width: 100%;
  height: 100%;
}
</style>
