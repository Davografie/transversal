<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import { RESONANCE, groupByTraitsetDie, sampleAt, totalAmplitude, easeInOutCubic, sinApprox } from '@/composables/resonance.js'
import { getDieColor, weightedColor, mixColor } from '@/composables/renderResonance.js'

/**
 * WaveformDivider — a small section break whose edge is the entity's linear
 * resonance "tangle" at a given collapse progress. This is a dedicated slim
 * renderer (not the full drawResonanceFrame path): it samples the composite
 * once per column, reuses those values for both the clip fill and the group
 * lines, and draws single strokes with normal compositing so it stays cheap on
 * phones.
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

const groups = computed(() => groupByTraitsetDie(props.osc))
const total = computed(() => totalAmplitude(groups.value, []))
const entityColor = computed(() => weightedColor(groups.value))
const maxAmp = computed(() => groups.value.reduce((m, o) => Math.max(m, o.amp), 0) || 1)

// Collapse convergence amount, mirroring the Lab's expand phase at `progress`.
const conv = computed(() => {
  const sum = props.collapseFraction + props.transformFraction + props.expandFraction || 1
  const expandStart = (props.collapseFraction + props.transformFraction) / sum
  const p = Math.max(0, Math.min(1, props.progress))
  const s = easeInOutCubic(Math.max(0, Math.min(1, (p - expandStart) / (1 - expandStart))))
  const c = 1 - s
  return easeInOutCubic(Math.max(0, Math.min(1, (c - 0.5) * 2)))
})

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

  const gs = groups.value
  const tot = total.value
  const ec = entityColor.value
  const mx = maxAmp.value
  const cv = conv.value
  const baseDrift = props.drift * (now / 1000)
  const ampScale = h / 2 - 2
  const N = isMobile ? 72 : 160

  // Composite offsets — sampled once, reused for fill and as the target line.
  const offs = new Float32Array(N + 1)
  for (let i = 0; i <= N; i++) {
    const t = i / N
    const v = tot > 0 ? sampleAt(gs, t / props.renderDivisor + baseDrift) / tot : 0
    offs[i] = v * ampScale
  }

  // Bottom region.
  ctx.fillStyle = props.colorBottom
  ctx.fillRect(0, 0, w, h)

  // Top region (clip edge).
  ctx.beginPath()
  ctx.moveTo(0, 0)
  for (let i = 0; i <= N; i++) ctx.lineTo((i / N) * w, h / 2 - offs[i])
  ctx.lineTo(w, 0)
  ctx.closePath()
  ctx.fillStyle = props.colorTop
  ctx.fill()

  // Tangle: one thin stroke per group, converging toward the composite.
  ctx.lineJoin = 'round'
  ctx.lineCap = 'round'
  for (const g of gs) {
    const strength = g.amp / mx
    const color = mixColor(getDieColor(g.die, g.negative), ec, cv)
    const dr = g.driftMul ?? 1
    ctx.beginPath()
    ctx.strokeStyle = color
    ctx.globalAlpha = 0.8
    ctx.lineWidth = 1.1
    for (let i = 0; i <= N; i++) {
      const t = i / N
      const own = sinApprox(2 * Math.PI * g.freq * (t / props.renderDivisor + baseDrift * dr) + g.phase) * ampScale * (0.35 + 0.65 * strength)
      const off = own + (offs[i] - own) * cv
      const y = h / 2 - off
      i === 0 ? ctx.moveTo(t * w, y) : ctx.lineTo(t * w, y)
    }
    ctx.stroke()
  }
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
