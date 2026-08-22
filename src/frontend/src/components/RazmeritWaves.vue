<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { RESONANCE } from '@/composables/resonance.js'
import { drawResonanceFrame } from '@/composables/renderResonance.js'

/**
 * Live character-switch renderer. Thin wrapper around `drawResonanceFrame`
 * that advances progress over the load window.
 */
const props = defineProps({
  from: { type: Array, default: () => [] },
  to: { type: Array, default: () => [] },
  done: { type: Boolean, default: false },
  duration: { type: Number, default: RESONANCE.durationMs },
  fanDuration: { type: Number, default: RESONANCE.fanMs },
})

const canvasEl = ref(null)
let rafId = null
let lastNow = 0
let elapsed = 0

const H = RESONANCE.height

function clamp01(v) {
  return Math.max(0, Math.min(1, v))
}

function draw(now) {
  const canvas = canvasEl.value
  if (!canvas) return
  if (!lastNow) lastNow = now
  elapsed += now - lastNow
  lastNow = now

  const progress = clamp01(elapsed / props.duration)

  const dpr = window.devicePixelRatio || 1
  const w = canvas.clientWidth || 260
  if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(H * dpr)) {
    canvas.width = Math.round(w * dpr)
    canvas.height = Math.round(H * dpr)
  }

  const ctx = canvas.getContext('2d')
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
  ctx.clearRect(0, 0, w, H)

  drawResonanceFrame(ctx, w, H, props.from, props.to, progress, {
    mode: RESONANCE.mode,
    renderDivisor: RESONANCE.renderDivisor,
    drift: RESONANCE.drift,
    colors: RESONANCE.colors,
    collapseFraction: RESONANCE.collapseFraction,
    transformFraction: RESONANCE.transformFraction,
    expandFraction: RESONANCE.expandFraction,
  })

  rafId = requestAnimationFrame(draw)
}

onMounted(() => {
  rafId = requestAnimationFrame(draw)
})

onUnmounted(() => {
  if (rafId) cancelAnimationFrame(rafId)
})
</script>

<template>
  <canvas ref="canvasEl" class="razmerit-waves" aria-hidden="true"></canvas>
</template>

<style scoped>
.razmerit-waves {
  display: block;
  width: 100%;
  height: 200px;
}
</style>
