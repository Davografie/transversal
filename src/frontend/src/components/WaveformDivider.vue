<script setup>
import { ref, watch, onMounted, onBeforeUnmount } from 'vue'
import { RESONANCE, radialHarmonics, sampleAt, totalAmplitude } from '@/composables/resonance.js'
import { getDieColor } from '@/composables/renderResonance.js'

/**
 * WaveformDivider — a section break whose boundary is the entity's linear
 * resonance "tangle". The composite line clips the edge; the component dice
 * are drawn on top as colored sine strokes. Both are pre-rendered once (on
 * mount, resize, or character change), then the whole band drifts via a pure
 * CSS translateX marquee, so the per-frame cost is compositor-only.
 */
const props = defineProps({
  osc: { type: Array, default: () => [] },
  height: { type: Number, default: 120 },
  colorTop: { type: String, default: '#1b1b28' },
  colorBottom: { type: String, default: '#2ac6a0' },
  points: { type: Number, default: 160 },
  renderDivisor: { type: Number, default: RESONANCE.renderDivisor },
  petals: { type: Number, default: 24 },
  driftSeconds: { type: Number, default: 14 },
  animate: { type: Boolean, default: true },
})

const root = ref(null)
const maskUrl = ref('')
const tangleUrl = ref('')
let ro = null

function makeCanvas(w, h, dpr) {
  const canvas = document.createElement('canvas')
  canvas.width = Math.round(w * dpr)
  canvas.height = Math.round(h * dpr)
  const ctx = canvas.getContext('2d')
  ctx.scale(dpr, dpr)
  ctx.clearRect(0, 0, w, h)
  return [canvas, ctx]
}

function buildTiles() {
  const node = root.value
  if (!node) return
  const w = node.clientWidth || 320
  const h = props.height
  if (w <= 0 || h <= 0) return

  const dpr = Math.min(window.devicePixelRatio || 1, 2)
  const periodic = radialHarmonics(props.osc, props.petals, props.renderDivisor)
  const total = totalAmplitude(periodic, [])
  const ampScale = h / 2 - 2
  const maxAmp = periodic.reduce((m, o) => Math.max(m, o.amp), 0) || 1
  const N = props.points

  // 1) Mask: the region above the composite curve (positive = up).
  const [maskCanvas, mctx] = makeCanvas(w, h, dpr)
  mctx.beginPath()
  mctx.moveTo(0, 0)
  for (let i = 0; i <= N; i++) {
    const t = i / N
    const v = total > 0 ? sampleAt(periodic, t / props.renderDivisor) / total : 0
    mctx.lineTo(t * w, h / 2 - v * ampScale)
  }
  mctx.lineTo(w, 0)
  mctx.closePath()
  mctx.fillStyle = '#fff'
  mctx.fill()
  maskUrl.value = maskCanvas.toDataURL()

  // 2) Tangle: the component dice as additive colored strokes.
  const [tangleCanvas, tctx] = makeCanvas(w, h, dpr)
  tctx.lineJoin = 'round'
  tctx.lineCap = 'round'
  tctx.globalCompositeOperation = 'lighter'
  for (const o of periodic) {
    const strength = o.amp / maxAmp
    const color = getDieColor(o.die, o.negative)
    const trace = (lineWidth, alpha) => {
      tctx.beginPath()
      tctx.strokeStyle = color
      tctx.globalAlpha = alpha
      tctx.lineWidth = lineWidth
      for (let i = 0; i <= N; i++) {
        const t = i / N
        const y = h / 2 - Math.sin(2 * Math.PI * o.freq * (t / props.renderDivisor) + o.phase) * ampScale * (0.35 + 0.65 * strength)
        i === 0 ? tctx.moveTo(t * w, y) : tctx.lineTo(t * w, y)
      }
      tctx.stroke()
    }
    trace(3.2, 0.12 * strength)
    trace(1.05, 0.85)
  }
  tangleUrl.value = tangleCanvas.toDataURL()
}

onMounted(() => {
  buildTiles()
  if (typeof ResizeObserver !== 'undefined') {
    ro = new ResizeObserver(() => buildTiles())
    ro.observe(root.value)
  }
})

onBeforeUnmount(() => {
  if (ro) ro.disconnect()
})

watch(() => props.osc, () => buildTiles())
watch(() => [props.height, props.points, props.renderDivisor, props.petals], () => buildTiles())
</script>

<template>
  <div ref="root" class="wd" :style="{ height: height + 'px' }">
    <div class="wd-bottom" :style="{ background: colorBottom }"></div>

    <div
      class="wd-scroll"
      :class="{ 'wd-scroll--animate': animate }"
      :style="{ animationDuration: driftSeconds + 's' }"
    >
      <div v-for="i in 2" :key="i" class="wd-tile">
        <div
          class="wd-top"
          :style="{
            background: colorTop,
            WebkitMaskImage: maskUrl ? `url(${maskUrl})` : 'none',
            maskImage: maskUrl ? `url(${maskUrl})` : 'none',
            WebkitMaskSize: '100% 100%',
            maskSize: '100% 100%',
            WebkitMaskRepeat: 'no-repeat',
            maskRepeat: 'no-repeat',
          }"
        ></div>
        <div
          class="wd-tangle"
          :style="{
            backgroundImage: tangleUrl ? `url(${tangleUrl})` : 'none',
            backgroundSize: '100% 100%',
            backgroundRepeat: 'no-repeat',
          }"
        ></div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.wd {
  position: relative;
  overflow: hidden;
  width: 100%;
}
.wd-bottom {
  position: absolute;
  top: 0;
  right: 0;
  bottom: 0;
  left: 0;
}
.wd-scroll {
  position: absolute;
  top: 0;
  bottom: 0;
  left: 0;
  width: 200%;
  display: flex;
}
.wd-tile {
  position: relative;
  flex: 1 1 50%;
  min-width: 50%;
}
.wd-top,
.wd-tangle {
  position: absolute;
  top: 0;
  right: 0;
  bottom: 0;
  left: 0;
}
.wd-tangle {
  pointer-events: none;
}
.wd-scroll--animate {
  animation: wd-drift 14s linear infinite;
}
@keyframes wd-drift {
  from {
    transform: translateX(0);
  }
  to {
    transform: translateX(-50%);
  }
}
</style>
