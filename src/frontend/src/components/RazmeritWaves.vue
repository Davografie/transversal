<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { RESONANCE, morphWaves } from '@/composables/resonance.js'

/**
 * Razmerit resonance — transversal gradient.
 *
 * No hard left/right split: every wave spans the whole X-axis. In crossfade
 * mode the source waves carry a left→right decreasing amplitude envelope and
 * the target waves the mirror image, so the two universes overlap as a
 * gradient. In morph mode each source wave glides its frequency/amplitude into
 * its nearest target wave. Additive blending makes overlapping waves sum into
 * a single bright signal.
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
const RENDER_DIVISOR = RESONANCE.renderDivisor
const DRIFT = RESONANCE.drift

function clamp01(v) {
  return Math.max(0, Math.min(1, v))
}

function colorOf(kind) {
  return RESONANCE.colors[kind] || '#8fd3ff'
}

function maxAmp(arr) {
  let m = 0
  for (const o of arr) if (o.amp > m) m = o.amp
  return m
}

function draw(now) {
  const canvas = canvasEl.value
  if (!canvas) return
  if (!lastNow) lastNow = now
  elapsed += now - lastNow
  lastNow = now

  const progress = clamp01(elapsed / props.duration)
  const driftOffset = progress * DRIFT

  const dpr = window.devicePixelRatio || 1
  const w = canvas.clientWidth || 260
  if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(H * dpr)) {
    canvas.width = Math.round(w * dpr)
    canvas.height = Math.round(H * dpr)
  }

  const ctx = canvas.getContext('2d')
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
  ctx.clearRect(0, 0, w, H)

  const midY = H / 2
  const ampScale = H / 2 - 14

  ctx.save()
  ctx.lineJoin = 'round'
  ctx.lineCap = 'round'
  ctx.globalCompositeOperation = 'lighter'

  const drawSet = (osc, gain, envelope) => {
    if (!osc.length || gain <= 0) return
    const max = maxAmp(osc) || 1

    for (const o of osc) {
      const strength = o.amp / max
      const color = colorOf(o.kind)

      // Halo pass.
      ctx.beginPath()
      ctx.strokeStyle = color
      ctx.globalAlpha = 0.12 * strength * gain
      ctx.lineWidth = 3.2
      for (let x = 0; x <= w; x += 2) {
        const nx = x / w
        const tt = nx / RENDER_DIVISOR + driftOffset
        const y = midY - Math.sin(2 * Math.PI * o.freq * tt + o.phase) * ampScale * (0.35 + 0.65 * strength) * envelope(nx)
        x === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y)
      }
      ctx.stroke()

      // Core pass.
      ctx.beginPath()
      ctx.strokeStyle = color
      ctx.globalAlpha = 0.85 * gain
      ctx.lineWidth = 1.05
      for (let x = 0; x <= w; x += 2) {
        const nx = x / w
        const tt = nx / RENDER_DIVISOR + driftOffset
        const y = midY - Math.sin(2 * Math.PI * o.freq * tt + o.phase) * ampScale * (0.35 + 0.65 * strength) * envelope(nx)
        x === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y)
      }
      ctx.stroke()
    }
  }

  if (RESONANCE.mode === 'morph') {
    // Uniform envelope: the whole signal morphs from source to target.
    const waves = morphWaves(props.from, props.to, progress)
    drawSet(waves, 1, () => 1)
  } else {
    // Gradient overlap: source fades left→right, target fades right→left.
    drawSet(props.from, 1 - progress, (x) => 1 - x)
    drawSet(props.to, progress, (x) => x)
  }

  ctx.restore()

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
