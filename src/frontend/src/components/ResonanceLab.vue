<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { RESONANCE, signatureOf } from '@/composables/resonance.js'
import { drawResonanceFrame } from '@/composables/renderResonance.js'

const emit = defineEmits(['close'])

const mode = ref(RESONANCE.mode)
const renderDivisor = ref(RESONANCE.renderDivisor)
const drift = ref(RESONANCE.drift)
const height = ref(RESONANCE.height)
const durationMs = ref(RESONANCE.durationMs)
const collapseFraction = ref(RESONANCE.collapseFraction)
const transformFraction = ref(RESONANCE.transformFraction)
const expandFraction = ref(RESONANCE.expandFraction)

const progress = ref(0)
const playing = ref(false)
const from = ref([])
const to = ref([])
const fromName = ref('kael-1')
const toName = ref('character-phaos-a2c7db71')
const fromLabel = ref('Kael Drift')
const toLabel = ref('Phaos Tyish')
const loading = ref(true)
const copied = ref(false)

const canvasEl = ref(null)
let rafId = null
let lastNow = 0
let playElapsed = 0

const output = computed(() => JSON.stringify({
  mode: mode.value,
  renderDivisor: renderDivisor.value,
  drift: drift.value,
  height: height.value,
  durationMs: durationMs.value,
  collapseFraction: collapseFraction.value,
  transformFraction: transformFraction.value,
  expandFraction: expandFraction.value,
  progress: Number(progress.value.toFixed(3)),
}, null, 2))

async function fetchSignature(id) {
  const q = `query($id: ID!) { character(id: $id) { entity { id razmerit } traitSettings { id traitId traitsetId dice polarity fromType projectionId ego } } }`
  const r = await fetch('/api/v1/graphql', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query: q, variables: { id } }),
  })
  const j = await r.json()
  const c = j.data?.character
  return c ? signatureOf(c.traitSettings || [], c.entity?.razmerit || 0) : []
}

async function load() {
  loading.value = true
  const [a, b] = await Promise.all([fetchSignature(fromName.value), fetchSignature(toName.value)])
  from.value = a
  to.value = b
  loading.value = false
  render()
}

function render() {
  const canvas = canvasEl.value
  if (!canvas) return
  const dpr = window.devicePixelRatio || 1
  const w = canvas.clientWidth || 600
  if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(height.value * dpr)) {
    canvas.width = Math.round(w * dpr)
    canvas.height = Math.round(height.value * dpr)
  }
  const ctx = canvas.getContext('2d')
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
  ctx.clearRect(0, 0, w, height.value)

  drawResonanceFrame(ctx, w, height.value, from.value, to.value, progress.value, {
    mode: mode.value,
    renderDivisor: renderDivisor.value,
    drift: drift.value,
    colors: RESONANCE.colors,
    collapseFraction: collapseFraction.value,
    transformFraction: transformFraction.value,
    expandFraction: expandFraction.value,
  })
}

function togglePlay() {
  playing.value = !playing.value
  if (playing.value) {
    if (progress.value >= 1) {
      progress.value = 0
      playElapsed = 0
    }
    lastNow = 0
    rafId = requestAnimationFrame(tick)
  } else {
    if (rafId) cancelAnimationFrame(rafId)
  }
}

function tick(now) {
  if (!lastNow) lastNow = now
  playElapsed += now - lastNow
  lastNow = now
  progress.value = Math.min(1, playElapsed / durationMs.value)
  render()
  if (progress.value >= 1) {
    playing.value = false
    return
  }
  rafId = requestAnimationFrame(tick)
}

function onScrub() {
  playing.value = false
  if (rafId) cancelAnimationFrame(rafId)
  render()
}

async function copyOutput() {
  try {
    await navigator.clipboard.writeText(output.value)
    copied.value = true
    setTimeout(() => { copied.value = false }, 1500)
  } catch {
    // clipboard may be unavailable; the <pre> is still selectable
  }
}

watch([progress, mode, renderDivisor, drift, height, collapseFraction, transformFraction, expandFraction], () => {
  if (!playing.value) render()
})

onMounted(() => {
  load()
})

onUnmounted(() => {
  if (rafId) cancelAnimationFrame(rafId)
})
</script>

<template>
  <div class="reslab-backdrop" @click.self="emit('close')">
    <div class="reslab panel">
      <div class="reslab-head">
        <h3>Resonance Lab</h3>
        <span class="reslab-pair">{{ fromLabel }} → {{ toLabel }}</span>
        <button class="reslab-close" @click="emit('close')">✕</button>
      </div>

      <div v-if="loading" class="reslab-loading">Loading signatures…</div>

      <template v-else>
        <canvas ref="canvasEl" class="reslab-canvas" :style="{ height: height + 'px' }" />

        <div class="reslab-scrub-row">
          <button class="reslab-play" @click="togglePlay">{{ playing ? '❚❚' : '▶' }}</button>
          <input
            v-model.number="progress"
            type="range"
            min="0"
            max="1"
            step="0.001"
            class="reslab-scrub"
            @input="onScrub"
          />
          <span class="reslab-progress">{{ (progress * 100).toFixed(1) }}%</span>
        </div>

        <div class="reslab-knobs">
          <label class="reslab-knob">
            <span>Mode</span>
            <select v-model="mode">
              <option value="harmonic">harmonic</option>
              <option value="crossfade">crossfade</option>
              <option value="morph">morph</option>
            </select>
          </label>

          <label class="reslab-knob">
            <span>renderDivisor {{ renderDivisor }}</span>
            <input v-model.number="renderDivisor" type="range" min="80" max="400" step="5" />
          </label>

          <label class="reslab-knob">
            <span>drift {{ drift.toFixed(4) }}</span>
            <input v-model.number="drift" type="range" min="0" max="0.02" step="0.0005" />
          </label>

          <label class="reslab-knob">
            <span>height {{ height }}</span>
            <input v-model.number="height" type="range" min="120" max="360" step="10" />
          </label>

          <label class="reslab-knob">
            <span>durationMs {{ durationMs }}</span>
            <input v-model.number="durationMs" type="range" min="1000" max="60000" step="500" />
          </label>

          <label class="reslab-knob">
            <span>collapseFraction {{ collapseFraction.toFixed(2) }}</span>
            <input v-model.number="collapseFraction" type="range" min="0.1" max="0.7" step="0.05" />
          </label>

          <label class="reslab-knob">
            <span>transformFraction {{ transformFraction.toFixed(2) }}</span>
            <input v-model.number="transformFraction" type="range" min="0.05" max="0.5" step="0.05" />
          </label>

          <label class="reslab-knob">
            <span>expandFraction {{ expandFraction.toFixed(2) }}</span>
            <input v-model.number="expandFraction" type="range" min="0.1" max="0.5" step="0.05" />
          </label>
        </div>

        <div class="reslab-output">
          <div class="reslab-output-head">
            <span>Variables</span>
            <button class="reslab-copy" @click="copyOutput">{{ copied ? 'Copied ✓' : 'Copy' }}</button>
          </div>
          <pre class="reslab-pre">{{ output }}</pre>
        </div>
      </template>
    </div>
  </div>
</template>

<style scoped>
.reslab-backdrop {
  position: fixed;
  inset: 0;
  z-index: 110;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.7);
  backdrop-filter: blur(6px);
}
.reslab {
  width: min(720px, calc(100vw - 32px));
  max-height: calc(100vh - 32px);
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 16px;
  border-radius: 12px;
  background: #10101a;
  border: 1px solid rgba(255, 255, 255, 0.1);
  color: var(--text);
}
.reslab-head {
  display: flex;
  align-items: center;
  gap: 12px;
}
.reslab-head h3 {
  font-size: 18px;
  margin: 0;
  color: var(--text);
}
.reslab-pair {
  font-size: 12px;
  color: var(--text-dim);
}
.reslab-close {
  margin-left: auto;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  border: 1px solid rgba(255, 255, 255, 0.1);
  background: transparent;
  color: var(--text-dim);
  cursor: pointer;
}
.reslab-loading {
  padding: 40px 0;
  text-align: center;
  color: var(--text-dim);
}
.reslab-canvas {
  display: block;
  width: 100%;
  background: rgba(255, 255, 255, 0.02);
  border-radius: 8px;
}
.reslab-scrub-row {
  display: flex;
  align-items: center;
  gap: 10px;
}
.reslab-play {
  width: 40px;
  height: 32px;
  border-radius: 6px;
  border: 1px solid rgba(255, 255, 255, 0.15);
  background: rgba(255, 255, 255, 0.06);
  color: var(--text);
  cursor: pointer;
  font-size: 14px;
}
.reslab-scrub {
  flex: 1;
}
.reslab-progress {
  width: 52px;
  text-align: right;
  font-size: 12px;
  color: var(--text-dim);
  font-variant-numeric: tabular-nums;
}
.reslab-knobs {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px 20px;
}
.reslab-knob {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 12px;
  color: var(--text-dim);
}
.reslab-knob input[type='range'] {
  width: 100%;
}
.reslab-knob select {
  width: 100%;
  padding: 5px 6px;
  border-radius: 5px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  background: rgba(255, 255, 255, 0.05);
  color: var(--text);
}
.reslab-output {
  border-top: 1px solid rgba(255, 255, 255, 0.08);
  padding-top: 12px;
}
.reslab-output-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
  font-size: 12px;
  color: var(--text-dim);
}
.reslab-copy {
  padding: 4px 10px;
  border-radius: 5px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  background: rgba(255, 255, 255, 0.05);
  color: var(--text);
  cursor: pointer;
  font-size: 12px;
}
.reslab-pre {
  margin: 0;
  padding: 10px;
  border-radius: 6px;
  background: rgba(0, 0, 0, 0.4);
  color: var(--text-dim);
  font-size: 12px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  white-space: pre-wrap;
  max-height: 160px;
  overflow: auto;
  user-select: text;
}
</style>
