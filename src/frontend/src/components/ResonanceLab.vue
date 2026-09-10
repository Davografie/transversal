<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useClipboard } from '@vueuse/core'
import { RESONANCE, signatureOf } from '@/composables/resonance.js'
import { drawResonanceFrame } from '@/composables/renderResonance.js'
import WaveformDivider from '@/components/WaveformDivider.vue'

const props = defineProps({
  embedded: { type: Boolean, default: false },
})
const emit = defineEmits(['close'])

function onBackdropClick() {
  if (!props.embedded) emit('close')
}

const mode = ref(RESONANCE.mode)
const layout = ref(RESONANCE.layout)
const renderDivisor = ref(RESONANCE.renderDivisor)
const drift = ref(RESONANCE.drift)
const height = ref(RESONANCE.height)
const durationMs = ref(RESONANCE.durationMs)
const collapseFraction = ref(RESONANCE.collapseFraction)
const transformFraction = ref(RESONANCE.transformFraction)
const expandFraction = ref(RESONANCE.expandFraction)
const egoBoost = ref(RESONANCE.egoBoost)
const radialPetals = ref(RESONANCE.radialPetals)
const breathDepth = ref(RESONANCE.breathDepth)
const breathRate = ref(RESONANCE.breathRate)

const progress = ref(0)
const playing = ref(false)
const fromRaw = ref({ traitSettings: [], razmerit: 0 })
const toRaw = ref({ traitSettings: [], razmerit: 0 })
const from = computed(() => signatureOf(fromRaw.value.traitSettings, fromRaw.value.razmerit, egoBoost.value))
const to = computed(() => signatureOf(toRaw.value.traitSettings, toRaw.value.razmerit, egoBoost.value))
const fromName = ref('kael-1')
const toName = ref('character-phaos-a2c7db71')
const fromLabel = ref('Kael Drift')
const toLabel = ref('Phaos Tyish')
const loading = ref(true)
const { copy: copyToClipboard, copied } = useClipboard({ copiedDuring: 1500 })

const canvasEl = ref(null)
let rafId = null
let lastNow = 0
let playElapsed = 0
const perfMs = ref(0)
const perfFps = ref(0)
let lastPerf = 0

const output = computed(() => JSON.stringify({
  mode: mode.value,
  layout: layout.value,
  renderDivisor: renderDivisor.value,
  drift: drift.value,
  height: height.value,
  egoBoost: egoBoost.value,
  radialPetals: radialPetals.value,
  breathDepth: breathDepth.value,
  breathRate: breathRate.value,
  durationMs: durationMs.value,
  collapseFraction: collapseFraction.value,
  transformFraction: transformFraction.value,
  expandFraction: expandFraction.value,
  progress: Number(progress.value.toFixed(3)),
}, null, 2))

async function fetchSignature(id) {
  const q = `query($id: ID!) { character(id: $id) { entity { id razmerit effectiveTraitSettings { id traitId traitsetId dice polarity fromType projectionId } } } }`
  const r = await fetch('/api/v1/graphql', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query: q, variables: { id } }),
  })
  const j = await r.json()
  const c = j.data?.character
  if (!c) return { traitSettings: [], razmerit: 0 }
  return { traitSettings: c.entity?.effectiveTraitSettings || [], razmerit: c.entity?.razmerit || 0 }
}

async function load() {
  loading.value = true
  const [a, b] = await Promise.all([fetchSignature(fromName.value), fetchSignature(toName.value)])
  fromRaw.value = a
  toRaw.value = b
  loading.value = false
  render()
}

function render(now = performance.now()) {
  if (layout.value === 'divider') return
  const canvas = canvasEl.value
  if (!canvas) return
  const dpr = Math.min(window.devicePixelRatio || 1, 1.5)
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
    layout: layout.value,
    renderDivisor: renderDivisor.value,
    drift: drift.value,
    colors: RESONANCE.colors,
    collapseFraction: collapseFraction.value,
    transformFraction: transformFraction.value,
    expandFraction: expandFraction.value,
    radialPetals: radialPetals.value,
    breathDepth: breathDepth.value,
    breathRate: breathRate.value,
    timeMs: now,
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
  }
}

function onScrub() {
  playing.value = false
}

function loop(now) {
  if (lastPerf) {
    const dt = now - lastPerf
    perfMs.value = perfMs.value * 0.9 + dt * 0.1
    perfFps.value = perfMs.value > 0 ? 1000 / perfMs.value : 0
  }
  lastPerf = now

  if (playing.value) {
    if (!lastNow) lastNow = now
    playElapsed += now - lastNow
    lastNow = now
    progress.value = Math.min(1, playElapsed / durationMs.value)
    if (progress.value >= 1) playing.value = false
  } else {
    lastNow = 0
  }
  render(now)
  rafId = requestAnimationFrame(loop)
}

async function copyOutput() {
  await copyToClipboard(output.value)
}

onMounted(() => {
  load()
  rafId = requestAnimationFrame(loop)
})

onUnmounted(() => {
  if (rafId) cancelAnimationFrame(rafId)
})
</script>

<template>
  <div :class="embedded ? 'reslab-embed' : 'reslab-backdrop'" @click.self="onBackdropClick">
    <div class="reslab panel" :class="{ 'reslab--embedded': embedded }">
      <div class="reslab-head">
        <h3>Resonance Lab</h3>
        <span class="reslab-pair">{{ fromLabel }} → {{ toLabel }}</span>
        <button v-if="!embedded" class="reslab-close" @click="emit('close')">✕</button>
      </div>

      <div v-if="loading" class="reslab-loading">Loading signatures…</div>

      <template v-else>
        <canvas v-if="layout !== 'divider'" ref="canvasEl" class="reslab-canvas" :style="{ height: height + 'px' }" />

        <div v-if="layout === 'divider'" class="reslab-divider">
          <div class="reslab-divider-label">Waveform divider preview (drifting tangle @ 0.715)</div>
          <WaveformDivider
            :osc="to"
            :height="Math.max(120, height)"
            :progress="0.715"
            :render-divisor="renderDivisor"
            :drift="drift"
            :collapse-fraction="collapseFraction"
            :transform-fraction="transformFraction"
            :expand-fraction="expandFraction"
          />
        </div>

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
          <span class="reslab-perf">{{ perfFps.toFixed(0) }} fps · {{ perfMs.toFixed(1) }} ms</span>
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
            <span>Layout</span>
            <select v-model="layout">
              <option value="linear">linear</option>
              <option value="radial">radial</option>
              <option value="divider">divider</option>
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
            <span>egoBoost {{ egoBoost.toFixed(2) }}</span>
            <input v-model.number="egoBoost" type="range" min="1" max="4" step="0.1" />
          </label>

          <label class="reslab-knob">
            <span>radialPetals {{ radialPetals }}</span>
            <input v-model.number="radialPetals" type="range" min="8" max="64" step="1" />
          </label>

          <label class="reslab-knob">
            <span>breathDepth {{ breathDepth.toFixed(2) }}</span>
            <input v-model.number="breathDepth" type="range" min="0" max="0.9" step="0.05" />
          </label>

          <label class="reslab-knob">
            <span>breathRate {{ breathRate.toFixed(2) }}</span>
            <input v-model.number="breathRate" type="range" min="0.1" max="3" step="0.1" />
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
.reslab-embed {
  width: 100%;
}
.reslab--embedded {
  width: 100%;
  max-height: min(60vh, 520px);
  overflow-y: auto;
}
/* The settings overlay styles inputs/buttons broadly; restore the Lab's own
   control sizing when it is embedded inside that overlay. */
.reslab--embedded .reslab-play {
  padding: 0;
}
.reslab--embedded .reslab-knob input[type='range'] {
  padding: 0;
  font-size: inherit;
  text-align: left;
}
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
  background: var(--bg-panel-solid);
  border: 1px solid var(--overlay-10);
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
  border: 1px solid var(--overlay-10);
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
  flex-shrink: 0;
  background: var(--overlay-2);
  border-radius: 8px;
}
.reslab-divider {
  border-radius: 8px;
  overflow: hidden;
  flex-shrink: 0;
}
.reslab-divider-label {
  font-size: 11px;
  color: var(--text-dim);
  margin-bottom: 6px;
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
  border: 1px solid var(--overlay-15);
  background: var(--overlay-6);
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
.reslab-perf {
  min-width: 96px;
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
  border: 1px solid var(--overlay-12);
  background: var(--overlay-4);
  color: var(--text);
}
.reslab-output {
  border-top: 1px solid var(--overlay-8);
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
  border: 1px solid var(--overlay-12);
  background: var(--overlay-4);
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
