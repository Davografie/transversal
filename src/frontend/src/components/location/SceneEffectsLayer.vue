<template>
  <div v-if="enabled && overlay" class="overlay-layer" :class="overlay" />
  <canvas v-if="enabled" ref="canvasEl" class="particle-canvas" />
</template>

<script setup>
import { onMounted, onUnmounted, ref, watch } from 'vue'

// The location's weather/atmosphere: a CSS overlay layer plus the canvas
// particle engine behind it (embers, snow, rain). Only `fire`, `snow` and
// `rain` have particles — `mist` and `fog` are pure CSS, so the loop simply
// idles for them.
const props = defineProps({
  /** Overlay preset: 'mist' | 'fire' | 'rain' | 'snow' | 'fog' | null */
  overlay: { type: String, default: null },
  /** Player-facing effects toggle; false removes the layer entirely. */
  enabled: { type: Boolean, default: true },
})

const PARTICLE_CONFIGS = {
  fire: { type: 'ember', spawnRate: 0.4, maxCount: 60, colors: ['#ff6020', '#ffa030', '#ff4010', '#ff8020'], speed: [0.3, 1.2], size: [2, 5], lifetime: [60, 120], rise: true },
  snow: { type: 'flake', spawnRate: 0.25, maxCount: 40, colors: ['rgba(255,255,255,0.8)', 'rgba(220,230,255,0.6)'], speed: [0.1, 0.4], size: [2, 4], lifetime: [200, 400], rise: false },
  rain: { type: 'streak', spawnRate: 0.6, maxCount: 80, colors: ['rgba(100,140,200,0.5)', 'rgba(120,160,220,0.4)'], speed: [2, 5], size: [1, 1.5], lifetime: [40, 80], rise: false },
  mist: null,
  fog: null,
}

const canvasEl = ref(null)
let particleRaf = null
let particles = []

function initParticle(cfg) {
  const edge = Math.random() * 100
  const fromBottom = cfg.rise
  const life = cfg.lifetime[0] + Math.random() * (cfg.lifetime[1] - cfg.lifetime[0])
  return {
    x: edge,
    y: fromBottom ? 100 + Math.random() * 10 : -10 - Math.random() * 10,
    vx: cfg.speed[0] ? (cfg.speed[0] + Math.random() * (cfg.speed[1] - cfg.speed[0])) * (Math.random() > 0.5 ? 1 : -1) : 0,
    vy: cfg.speed ? (cfg.speed[0] + Math.random() * (cfg.speed[1] - cfg.speed[0])) * (fromBottom ? -1 : 1) : 0,
    size: cfg.size[0] + Math.random() * (cfg.size[1] - cfg.size[0]),
    color: cfg.colors[Math.floor(Math.random() * cfg.colors.length)],
    life,
    maxLife: life,
  }
}

function spawnParticles(cfg) {
  if (!cfg) return
  if (Math.random() < cfg.spawnRate && particles.length < cfg.maxCount) {
    particles.push(initParticle(cfg))
  }
}

function updateParticles(cfg) {
  for (let i = particles.length - 1; i >= 0; i--) {
    const p = particles[i]
    p.x += p.vx * 0.1
    p.y += p.vy
    p.life--
    if (p.life <= 0) particles.splice(i, 1)
  }
}

function drawParticles(ctx, w, h, cfg) {
  ctx.clearRect(0, 0, w, h)
  for (const p of particles) {
    const alpha = Math.min(1, p.life / p.maxLife * 2)
    if (cfg.type === 'streak') {
      // Rain: thin falling lines
      ctx.globalAlpha = alpha
      ctx.strokeStyle = p.color
      ctx.lineWidth = p.size
      ctx.beginPath()
      ctx.moveTo(p.x * w / 100, p.y * h / 100)
      ctx.lineTo(p.x * w / 100, (p.y - 3) * h / 100)
      ctx.stroke()
    } else {
      // Embers & flakes: circles
      ctx.globalAlpha = alpha
      ctx.fillStyle = p.color
      ctx.beginPath()
      ctx.arc(p.x * w / 100, p.y * h / 100, p.size, 0, Math.PI * 2)
      ctx.fill()
    }
  }
  ctx.globalAlpha = 1
}

function particleLoop() {
  const canvas = canvasEl.value
  if (!canvas) { particleRaf = requestAnimationFrame(particleLoop); return }
  const cfg = PARTICLE_CONFIGS[props.overlay] || null
  if (!cfg) { particles = []; particleRaf = requestAnimationFrame(particleLoop); return }
  const w = canvas.offsetWidth || window.innerWidth
  const h = canvas.offsetHeight || window.innerHeight
  if (canvas.width !== w) canvas.width = w
  if (canvas.height !== h) canvas.height = h
  const ctx = canvas.getContext('2d')
  spawnParticles(cfg)
  updateParticles(cfg)
  drawParticles(ctx, canvas.width, canvas.height, cfg)
  particleRaf = requestAnimationFrame(particleLoop)
}

function startParticles() {
  if (particleRaf) cancelAnimationFrame(particleRaf)
  particles = []
  particleRaf = requestAnimationFrame(particleLoop)
}

function stopParticles() {
  if (particleRaf) { cancelAnimationFrame(particleRaf); particleRaf = null }
  particles = []
  const canvas = canvasEl.value
  if (canvas) { const ctx = canvas.getContext('2d'); ctx?.clearRect(0, 0, canvas.width, canvas.height) }
}

watch(() => props.overlay, (val) => {
  if (PARTICLE_CONFIGS[val]) startParticles()
  else stopParticles()
})

onMounted(() => {
  // Always start the loop; it self-manages based on the current overlay.
  startParticles()
  window.addEventListener('resize', resizeCanvas)
})
onUnmounted(() => {
  stopParticles()
  window.removeEventListener('resize', resizeCanvas)
})

function resizeCanvas() {
  const canvas = canvasEl.value
  if (!canvas) return
  canvas.width = canvas.offsetWidth
  canvas.height = canvas.offsetHeight
}
</script>

<style scoped>
/* ── Visual overlay layer ────────────────────────── */

.overlay-layer {
  position: absolute; inset: 0; z-index: 30;
  pointer-events: none;
  opacity: 0.6;
}

.particle-canvas {
  position: absolute; inset: 0; z-index: 31;
  pointer-events: none;
  width: 100%; height: 100%;
}

/* Mist: drifting horizontal fog + blur */
.overlay-layer.mist {
  background: linear-gradient(90deg, transparent 0%, rgba(180,190,200,0.15) 30%, rgba(200,210,220,0.25) 50%, rgba(180,190,200,0.15) 70%, transparent 100%);
  background-size: 200% 100%;
  animation: mistDrift 8s ease-in-out infinite;
  backdrop-filter: blur(3px) saturate(0.8);
}
@keyframes mistDrift {
  0%, 100% { background-position: 0% 50%; opacity: 0.5; }
  50% { background-position: 100% 50%; opacity: 0.7; }
}

/* Fire: rising flickering glow + warmth */
.overlay-layer.fire {
  background: radial-gradient(ellipse at 50% 100%, rgba(255,120,20,0.3) 0%, rgba(255,60,10,0.15) 30%, transparent 70%);
  animation: fireFlicker 3s ease-in-out infinite;
  backdrop-filter: brightness(1.1) saturate(1.4);
}
@keyframes fireFlicker {
  0%, 100% { opacity: 0.5; transform: scaleY(1); }
  25% { opacity: 0.7; transform: scaleY(1.05); }
  50% { opacity: 0.4; transform: scaleY(0.95); }
  75% { opacity: 0.65; transform: scaleY(1.02); }
}

/* Rain: falling streaks + darken */
.overlay-layer.rain {
  background:
    repeating-linear-gradient(0deg, transparent, transparent 3px, rgba(100,140,200,0.08) 3px, rgba(100,140,200,0.08) 4px),
    repeating-linear-gradient(90deg, transparent, transparent 20px, rgba(100,140,200,0.05) 20px, rgba(100,140,200,0.05) 22px);
  animation: rainFall 1.5s linear infinite;
  backdrop-filter: saturate(0.6) brightness(0.85);
}
@keyframes rainFall {
  0% { background-position: 0 0, 0 0; }
  100% { background-position: 0 15px, -3px 0; }
}

/* Snow: drifting flakes + brighten/wash */
.overlay-layer.snow {
  background:
    radial-gradient(circle at 20% 10%, rgba(255,255,255,0.12) 0%, transparent 2%),
    radial-gradient(circle at 60% 30%, rgba(255,255,255,0.1) 0%, transparent 2%),
    radial-gradient(circle at 40% 60%, rgba(255,255,255,0.08) 0%, transparent 3%),
    radial-gradient(circle at 80% 80%, rgba(255,255,255,0.1) 0%, transparent 2%),
    radial-gradient(circle at 10% 50%, rgba(255,255,255,0.09) 0%, transparent 2%);
  background-size: 100% 200%;
  animation: snowFall 10s linear infinite;
  backdrop-filter: brightness(1.15) saturate(0.5);
}
@keyframes snowFall {
  0% { background-position: 0 0, 0 0, 0 0, 0 0, 0 0; }
  100% { background-position: 15px 100px, -10px 80px, 5px 120px, -5px 60px, 10px 90px; }
}

/* Fog: thick bottom mist + heavy blur */
.overlay-layer.fog {
  background: linear-gradient(to top, rgba(180,190,200,0.3) 0%, rgba(160,170,185,0.15) 40%, transparent 80%);
  animation: fogRoll 12s ease-in-out infinite;
  backdrop-filter: blur(4px) saturate(0.6) brightness(0.95);
}
@keyframes fogRoll {
  0%, 100% { background-position: 0% 100%; opacity: 0.5; }
  50% { background-position: 10% 100%; opacity: 0.65; }
}

</style>
