<script setup>
import { ref, watch, onMounted, onBeforeUnmount } from 'vue'
import { RESONANCE, sampleAt, totalAmplitude } from '@/composables/resonance.js'

/**
 * WaveformDivider — a section break whose boundary is the entity's composite
 * resonance line. The curve is pre-rendered once to a canvas mask (only on
 * mount, resize, or character change); the animation is pure CSS transform,
 * so the per-frame cost is compositor-only rather than signal math.
 */
const props = defineProps({
  osc: { type: Array, default: () => [] },
  height: { type: Number, default: 96 },
  colorTop: { type: String, default: '#1b1b28' },
  colorBottom: { type: String, default: '#2ac6a0' },
  points: { type: Number, default: 140 },
  renderDivisor: { type: Number, default: RESONANCE.renderDivisor },
  animate: { type: Boolean, default: true },
})

const root = ref(null)
const maskUrl = ref('')
let ro = null

function buildMask() {
  const node = root.value
  if (!node) return
  const w = node.clientWidth || 320
  const h = props.height
  if (w <= 0 || h <= 0) return

  const dpr = Math.min(window.devicePixelRatio || 1, 2)
  const canvas = document.createElement('canvas')
  canvas.width = Math.round(w * dpr)
  canvas.height = Math.round(h * dpr)
  const ctx = canvas.getContext('2d')
  ctx.scale(dpr, dpr)
  ctx.clearRect(0, 0, w, h)

  // Top region above the composite curve. Positive signal = up, matching the
  // canvas renderer's ownOff sign convention.
  const total = totalAmplitude(props.osc, [])
  const ampScale = h / 2 - 2
  const N = props.points
  ctx.beginPath()
  ctx.moveTo(0, 0)
  for (let i = 0; i <= N; i++) {
    const t = i / N
    const v = total > 0 ? sampleAt(props.osc, t / props.renderDivisor) / total : 0
    const y = h / 2 - v * ampScale
    ctx.lineTo(t * w, y)
  }
  ctx.lineTo(w, 0)
  ctx.closePath()
  ctx.fillStyle = '#fff'
  ctx.fill()

  maskUrl.value = canvas.toDataURL()
}

onMounted(() => {
  buildMask()
  if (typeof ResizeObserver !== 'undefined') {
    ro = new ResizeObserver(() => buildMask())
    ro.observe(root.value)
  }
})

onBeforeUnmount(() => {
  if (ro) ro.disconnect()
})

watch(() => props.osc, () => buildMask())
watch(() => [props.height, props.points, props.renderDivisor], () => buildMask())
</script>

<template>
  <div ref="root" class="wd" :style="{ height: height + 'px' }">
    <div class="wd-bottom" :style="{ background: colorBottom }"></div>
    <div
      class="wd-top"
      :class="{ 'wd-top--animate': animate }"
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
  </div>
</template>

<style scoped>
.wd {
  position: relative;
  overflow: hidden;
  width: 100%;
}
.wd-bottom,
.wd-top {
  position: absolute;
  top: 0;
  right: 0;
  bottom: 0;
  left: 0;
}
.wd-top {
  transform-origin: top center;
}
.wd-top--animate {
  animation: wd-breathe 6s ease-in-out infinite;
}
@keyframes wd-breathe {
  0%,
  100% {
    transform: scaleY(1);
  }
  50% {
    transform: scaleY(1.08);
  }
}
</style>
