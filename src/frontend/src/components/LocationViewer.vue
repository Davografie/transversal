<template>
  <div ref="viewerEl" class="location-viewer" :class="{ 'portal-active': travelAnim.active }" :style="bgStyle" @click="onBgClick">
    <!-- Video background for animated/webm formats -->
    <video v-if="isVideoBg" ref="videoBgEl" :src="currentImage" class="video-bg" :style="videoStyle" autoplay loop muted playsinline />
    <!-- Visual overlay layer (CSS effects) -->
    <div v-if="effectsEnabled && optimisticOverlay" class="overlay-layer" :class="optimisticOverlay" />

    <!-- Canvas particle layer -->
    <canvas v-if="effectsEnabled" ref="particleCanvas" class="particle-canvas" />

    <!-- Location label (architect only) -->
    <div class="loc-label fade-in" v-if="showElements && gmMode">{{ displayName }}</div>
    <div class="uni-label fade-in" v-if="showElements && gmMode">{{ displayUniverse }}</div>

    <!-- Overlay preset switcher (architect only) -->
    <div class="overlay-switcher fade-in" v-if="showElements && gmMode">
      <button
        v-for="o in overlayPresets"
        :key="o.value"
        class="overlay-btn"
        :class="{ active: optimisticOverlay === o.value || (!optimisticOverlay && o.value === null) }"
        :title="o.label"
        @click="setOverlay(o.value)"
      >{{ o.icon }}</button>
      <span class="overlay-sep"></span>
      <button
        class="overlay-btn arrange-btn"
        :class="{ active: editZones }"
        title="Arrange map elements"
        @click="$emit('update:editZones', !editZones)"
      >🖉</button>
    </div>

    <!-- Effects toggle (players only, only when location has an effect) -->
    <div class="overlay-switcher fade-in" v-if="showElements && !gmMode && optimisticOverlay">
      <button
        class="overlay-btn"
        :class="{ active: effectsEnabled }"
        :title="effectsEnabled ? 'Disable effects' : 'Enable effects'"
        @click="effectsEnabled = !effectsEnabled"
      >{{ effectsEnabled ? '✨' : '🌑' }}</button>
    </div>

    <!-- Zone dots -->
    <template v-for="(z, i) in zones" :key="'z-' + z.name">
    <MapDot
      v-if="showElements"
      type="zone"
      :x="parallaxX(z.x)" :y="parallaxY(z.y)"
      :image="childImage(z)"
      :label="z.name"
      :expanded="editZones || (activeElement?.type === 'zone' && activeElement?.name === z.name) || hoveredDot === 'zone-' + z.name"
      :draggable="editZones"
      :title="z.name"
      :arrival-x="zoneCache(z)?.arriveX"
      :arrival-y="zoneCache(z)?.arriveY"
      :dest-aspect="zoneCache(z)?.destAspect"
      @click="onDotClick('zone', z)"
      @overlay-click="onExpandedClick('zone', z)"
      @drag-start="(e) => onZoneDragStart(e, z, i)"
    />
    </template>

    <!-- Occupant dots (non-self only, always expanded) -->
    <template v-for="(o, i) in occupants.filter(x => x.id !== entityId)" :key="'o-' + o.id">
    <MapDot
      v-if="!travelAnim.active && showElements"
      type="occupant"
      :variant="o.type"
      :x="parallaxX(o.map_x ?? occupantX(i, o))" :y="parallaxY(o.map_y ?? occupantY(i, o))"
      :image="o.image"
      :initials="occupantInitials(o.name)"
      :expanded="true"
      :draggable="canDragOccupant(o)"
      :lerping="lerpActive"
      :title="canDragOccupant(o) ? 'Drag to reposition' : o.name"
      @click="onDotClick('occupant', o)"
      @overlay-click="onExpandedClick('occupant', o)"
      @drag-start="(e) => onOccupantDragStart(e, o, i)"
    />
    <!-- Pool dice ring around occupant dot -->
    <PoolDiceRing
      v-if="!travelAnim.active && showElements && (poolDiceFor(o.id).length > 0 || (poolPhaseFor(o.id) === 'resolved' && remoteResults[o.id]))"
      :dice="poolDiceFor(o.id)"
      :phase="poolPhaseFor(o.id)"
      :cx="parallaxX(o.map_x ?? occupantX(i, o))"
      :cy="parallaxY(o.map_y ?? occupantY(i, o))"
      :resolved="remoteResults[o.id] || null"
    />
    </template>

    <!-- Navigation dots -->
    <template v-for="nd in navDots" :key="'nav-' + nd.key">
    <MapDot
      v-if="showElements"
      type="nav"
      :variant="nd.type"
      :x="parallaxX(nd.x)" :y="parallaxY(nd.y)"
      :image="nd.image"
      :label="nd.name"
      :expanded="editZones || (activeElement?.type === 'nav' && activeElement?.key === nd.key) || hoveredDot === 'nav-' + nd.key"
      :draggable="editZones"
      :title="nd.name"
      :arrival-x="destNavCache[nd.target.id]?.arriveX"
      :arrival-y="destNavCache[nd.target.id]?.arriveY"
      :dest-aspect="destNavCache[nd.target.id]?.destAspect"
      @click="onDotClick('nav', nd)"
      @overlay-click="onExpandedClick('nav', nd)"
      @drag-start="(e) => onNavDragStart(e, nd)"
    />
    </template>

    <!-- Arrival animation rings -->
    <div
      v-for="r in arrivalRings"
      :key="r.key"
      v-if="!travelAnim.active && showElements && showSelf"
      class="arrival-ring"
      :class="r.class"
      :style="{ left: selfX + '%', top: selfY + '%' }"
    />

    <!-- Self character dot (no parallax — 1:1 with touch) -->
    <MapDot
      v-if="!travelAnim.active && showElements && showSelf"
      type="self"
      variant="character"
      class="fade-in"
      :x="selfX" :y="selfY"
      :image="selfImage"
      :initials="selfInitials"
      :expanded="true"
      :draggable="true"
      title="Drag to explore"
      @click="onSelfClick()"
      @overlay-click="onSelfClick()"
      @drag-start="(e) => onSelfDragStart(e)"
    />
    <PoolDiceRing
      v-if="!travelAnim.active && showElements && (poolDiceFor(entityId).length > 0 || (poolPhaseFor(entityId) === 'resolved' && remoteResults[entityId]))"
      :dice="poolDiceFor(entityId)"
      :phase="poolPhaseFor(entityId)"
      :cx="selfX"
      :cy="selfY"
      :resolved="remoteResults[entityId] || null"
    />

    <!-- Travel expansion animation -->
    <div
      v-if="travelAnim.active"
      class="travel-overlay"
      :style="{
        '--travel-x': travelAnim.x + '%',
        '--travel-y': travelAnim.y + '%',
        backgroundImage: 'url(' + travelAnim.image + ')',
        backgroundPosition: (travelAnim.bgX || 50) + '% ' + (travelAnim.bgY || 50) + '%',
      }"
    />


  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import MapDot from './MapDot.vue'
import PoolDiceRing from './PoolDiceRing.vue'
import { useTransversalLinks } from '@/composables/useTransversalLinks.js'
import { isVideoUrl, panAxis } from '@/composables/media.js'

const props = defineProps({
  locationId: { type: String, required: true },
  locationName: { type: String, default: '' },
  universe: { type: String, default: 'earth' },
  backgroundImage: { type: String, default: '' },
  rawBackgroundImage: { type: String, default: '' },  // pre-quality URL, used as load-error fallback
  entityId: { type: String, required: true },
  editZones: { type: Boolean, default: false },
  overlay: { type: String, default: null },
  gmMode: { type: Boolean, default: false },
  remotePools: { type: Object, default: () => ({}) },  // entity_id → { dice: [...], player_id, phase }
  remoteResults: { type: Object, default: () => ({}) },  // entity_id → { total, effect_die, rolls, ... }
})

const emit = defineEmits(['moved', 'update:editZones', 'inspectEntity'])
const { toggleTransversalType } = useTransversalLinks()

const currentImage = ref('')
const videoBgEl = ref(null)
const isVideoBg = computed(() => isVideoUrl(currentImage.value))
const nav = ref({})
const zones = ref([])
const occupants = ref([])
const viewerEl = ref(null)
const activeElement = ref(null)  // { type: 'zone'|'occupant', name?, id? } — which dot is popped out
const travelAnim = ref({ active: false, x: 50, y: 50, image: '' })
const showElements = ref(true)  // toggled off during portal for fade-in remount
const showSelf = ref(true)     // delayed after travel for dramatic arrival

const effectsEnabled = ref(localStorage.getItem('effectsEnabled') !== 'false')
watch(effectsEnabled, (v) => { localStorage.setItem('effectsEnabled', v ? 'true' : 'false') })

const overlayPresets = [
  { value: null, icon: '◌', label: 'None' },
  { value: 'mist', icon: '🌫', label: 'Mist' },
  { value: 'fire', icon: '🔥', label: 'Fire' },
  { value: 'rain', icon: '🌧', label: 'Rain' },
  { value: 'snow', icon: '❄', label: 'Snow' },
  { value: 'fog', icon: '🌁', label: 'Fog' },
]

const optimisticOverlay = ref(props.overlay)  // immediate UI feedback
watch(() => props.overlay, (val) => { optimisticOverlay.value = val })  // sync from SSE

// ── Canvas particle system ──────────────────────────

const particleCanvas = ref(null)
let particleRaf = null
let particles = []

const PARTICLE_CONFIGS = {
  fire: { type: 'ember', spawnRate: 0.4, maxCount: 60, colors: ['#ff6020', '#ffa030', '#ff4010', '#ff8020'], speed: [0.3, 1.2], size: [2, 5], lifetime: [60, 120], rise: true },
  snow: { type: 'flake', spawnRate: 0.25, maxCount: 40, colors: ['rgba(255,255,255,0.8)', 'rgba(220,230,255,0.6)'], speed: [0.1, 0.4], size: [2, 4], lifetime: [200, 400], rise: false },
  rain: { type: 'streak', spawnRate: 0.6, maxCount: 80, colors: ['rgba(100,140,200,0.5)', 'rgba(120,160,220,0.4)'], speed: [2, 5], size: [1, 1.5], lifetime: [40, 80], rise: false },
  mist: null,
  fog: null,
}

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
  const canvas = particleCanvas.value
  if (!canvas) { particleRaf = requestAnimationFrame(particleLoop); return }
  const cfg = PARTICLE_CONFIGS[optimisticOverlay.value] || null
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
  const canvas = particleCanvas.value
  if (canvas) { const ctx = canvas.getContext('2d'); ctx?.clearRect(0, 0, canvas.width, canvas.height) }
}

watch(optimisticOverlay, (val) => {
  if (PARTICLE_CONFIGS[val]) startParticles()
  else stopParticles()
})

onMounted(() => {
  console.log('[diag] LocationViewer mounted', { locationId: props.locationId, locationName: props.locationName, universe: props.universe, gmMode: props.gmMode })
  // Always start loop; it self-manages based on current overlay
  startParticles()
  window.addEventListener('resize', resizeCanvas)
})
onUnmounted(() => {
  stopParticles()
  window.removeEventListener('resize', resizeCanvas)
})

function resizeCanvas() {
  const canvas = particleCanvas.value
  if (!canvas) return
  canvas.width = canvas.offsetWidth
  canvas.height = canvas.offsetHeight
}

async function setOverlay(value) {
  optimisticOverlay.value = value  // instant visual update
  try {
    await fetch('/api/v1/graphql', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        query: `mutation($input: UpdateEntityInput!) { updateEntity(input: $input) { id } }`,
        variables: { input: { id: props.locationId, overlay: value || '' } },
      }),
    })
  } catch { optimisticOverlay.value = props.overlay }  // rollback on error
}

const selfOccupant = computed(() => occupants.value.find(o => o.id === props.entityId) || { map_x: 50, map_y: 50, name: '', image: null })
const selfX = computed(() => selfOccupant.value.map_x ?? 50)
const selfY = computed(() => selfOccupant.value.map_y ?? 50)
const selfImage = computed(() => selfOccupant.value.image || null)
const selfInitials = computed(() => occupantInitials(selfOccupant.value.name || 'You'))

const arrivalRings = [
  // Phase 1 — Reverse ripple (energy coalescing inward)
  { key: 'implode-1', class: 'ring-implode ring-implode-1' },
  { key: 'implode-2', class: 'ring-implode ring-implode-2' },
  // Phase 2 — Portal flash
  { key: 'flash', class: 'ring-flash' },
  // Phase 3 — Triple burst outward
  { key: 'burst-1', class: 'ring-burst ring-burst-1' },
  { key: 'burst-2', class: 'ring-burst ring-burst-2' },
  { key: 'burst-3', class: 'ring-burst ring-burst-3' },
]

function onSelfDragStart(e) {
  const idx = occupants.value.findIndex(o => o.id === props.entityId)
  if (idx === -1) return
  onOccupantDragStart(e, occupants.value[idx], idx)
}

function onSelfClick() {
  if (occSuppressClick) { occSuppressClick = false; return }
  emit('inspectEntity', props.entityId)
}

function parallaxOffset() {
  const self = occupants.value.find(o => o.id === props.entityId)
  const mx = self?.map_x ?? 50
  const my = self?.map_y ?? 50
  return { x: mx, y: my }
}

// Convert image-relative position to viewport position based on pan offset
function toViewportPos(imgX, imgY) {
  const self = occupants.value.find(o => o.id === props.entityId)
  const charX = self?.map_x ?? 50
  const charY = self?.map_y ?? 50
  const vw = window.innerWidth, vh = window.innerHeight
  const viewAspect = vw / vh
  const imgAspect = imageAspect.value

  if (imgAspect && imgAspect > viewAspect) {
    // Landscape: image fills height, overflows horizontally
    const imgW = vh * imgAspect
    const overflow = imgW - vw
    const panPx = ((charX / 100) * overflow)
    const dotPx = (imgX / 100) * imgW
    const viewX = ((dotPx - panPx) / vw) * 100
    return { left: viewX.toFixed(1) + '%', top: imgY.toFixed(1) + '%' }
  }
  if (imgAspect && imgAspect < viewAspect) {
    // Portrait: image fills width, overflows vertically
    const imgH = vw / imgAspect
    const overflow = imgH - vh
    const panPx = ((charY / 100) * overflow)
    const dotPy = (imgY / 100) * imgH
    const viewY = ((dotPy - panPx) / vh) * 100
    return { left: imgX.toFixed(1) + '%', top: viewY.toFixed(1) + '%' }
  }
  // Unknown aspect: fallback — dots locked to image via pan
  return { left: imgX.toFixed(1) + '%', top: imgY.toFixed(1) + '%' }
}

function parallaxedStyle(imgX, imgY) {
  return toViewportPos(imgX, imgY)
}

function parallaxX(imgX) { return parseFloat(toViewportPos(imgX, 0).left) || imgX }
function parallaxY(imgY) { return parseFloat(toViewportPos(0, imgY).top) || imgY }

function occupantX(index, occupant) {
  if (zones.value.length > 0) {
    const zoneIdx = index % zones.value.length
    const z = zones.value[zoneIdx]
    const offset = 5 + (Math.floor(index / zones.value.length) * 5)
    return z.x + offset
  }
  return 20 + (index * 15) % 60
}

function occupantY(index, occupant) {
  if (zones.value.length > 0) {
    const zoneIdx = index % zones.value.length
    const z = zones.value[zoneIdx]
    const offset = 5 + (Math.floor(index / zones.value.length) * 5)
    return z.y + offset
  }
  return 75 + (index * 5) % 15
}

// ── Drag state ─────────────────────────────────────

const dragging = ref(null)  // { zoneIndex, startX, startY, origX, origY }

function toImagePos(viewX, viewY) {
  const self = occupants.value.find(o => o.id === props.entityId)
  const charX = self?.map_x ?? 50
  const charY = self?.map_y ?? 50
  const vw = window.innerWidth, vh = window.innerHeight
  const viewAspect = vw / vh
  const imgAspect = imageAspect.value

  if (imgAspect && imgAspect > viewAspect) {
    const imgW = vh * imgAspect
    const overflow = imgW - vw
    const panPx = (charX / 100) * overflow
    const dotPx = (viewX / 100) * vw + panPx
    return { x: (dotPx / imgW) * 100, y: viewY }
  }
  if (imgAspect && imgAspect < viewAspect) {
    const imgH = vw / imgAspect
    const overflow = imgH - vh
    const panPy = (charY / 100) * overflow
    const dotPy = (viewY / 100) * vh + panPy
    return { x: viewX, y: (dotPy / imgH) * 100 }
  }
  return { x: viewX, y: viewY }
}

function getPosFromEvent(e) {
  const el = viewerEl.value
  if (!el) return { x: 50, y: 50 }
  const rect = el.getBoundingClientRect()
  const clientX = e.touches ? e.touches[0].clientX : e.clientX
  const clientY = e.touches ? e.touches[0].clientY : e.clientY
  const vx = ((clientX - rect.left) / rect.width) * 100
  const vy = ((clientY - rect.top) / rect.height) * 100
  return toImagePos(vx, vy)
}

function onZoneDragStart(e, zone, index) {
  if (!props.editZones) return
  e.preventDefault()
  const pos = getPosFromEvent(e)
  dragging.value = { index, startX: pos.x, startY: pos.y, origX: zone.x, origY: zone.y }
  document.addEventListener('mousemove', onDragMove)
  document.addEventListener('mouseup', onDragEnd)
  document.addEventListener('touchmove', onDragMove, { passive: false })
  document.addEventListener('touchend', onDragEnd)
}

function onDragMove(e) {
  if (!dragging.value) return
  e.preventDefault()
  const pos = getPosFromEvent(e)
  const dz = zones.value[dragging.value.index]
  if (dz) {
    dz.x = Math.max(2, Math.min(98, Math.round(pos.x)))
    dz.y = Math.max(2, Math.min(98, Math.round(pos.y)))
  }
}

async function onDragEnd() {
  document.removeEventListener('mousemove', onDragMove)
  document.removeEventListener('mouseup', onDragEnd)
  document.removeEventListener('touchmove', onDragMove)
  document.removeEventListener('touchend', onDragEnd)
  if (!dragging.value) return
  dragging.value = null

  // Save to API
  try {
    await fetch(`/api/v1/locations/${props.locationId}/zones`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(zones.value.map(z => ({ name: z.name, x: z.x, y: z.y }))),
    })
  } catch { /* silent */ }
}

onUnmounted(() => {
  document.removeEventListener('mousemove', onDragMove)
  document.removeEventListener('mouseup', onDragEnd)
  document.removeEventListener('touchmove', onDragMove)
  document.removeEventListener('touchend', onDragEnd)
})

const UNIVERSE_NAMES = { earth: 'Earth', three_realms: 'Three Realms' }
const displayUniverse = computed(() => UNIVERSE_NAMES[props.universe] || props.universe)
const displayName = computed(() => nav.value.location?.name || props.locationName || props.locationId)

const navDotPositions = ref({ parent: { x: 90, y: 15 }, portal: { x: 90, y: 50 } })

function loadNavPositions() {
  const raw = nav.value.location?.nav_positions
  if (raw) {
    try {
      const parsed = typeof raw === 'string' ? JSON.parse(raw) : raw
      for (const [k, v] of Object.entries(parsed || {})) {
        if (v && typeof v.x === 'number' && typeof v.y === 'number') {
          navDotPositions.value[k] = v
        }
      }
    } catch {}
  }
}

const navDots = computed(() => {
  const dots = []
  if (nav.value.parent) {
    const pos = navDotPositions.value.parent
    dots.push({
      key: 'parent', type: 'parent', name: nav.value.parent.name,
      image: nav.value.parent.background_image || null,
      x: pos.x, y: pos.y,
      target: { id: nav.value.parent._key, universe: nav.value.parent.current_universe },
    })
  }
  for (const [i, t] of (nav.value.transversal || []).entries()) {
    const key = i === 0 ? 'portal' : `portal:${i}`
    const pos = navDotPositions.value[key] || { x: 90, y: 50 + i * 10 }
    dots.push({
      key, type: 'portal', name: `${t.name} · ${t.transversal_type || 'inapposite'}`,
      image: t.background_image || null,
      x: pos.x, y: pos.y,
      transversal_type: t.transversal_type || 'inapposite',
      target: { id: t._key, universe: t.current_universe },
    })
  }
  return dots
})

const imageAspect = ref(null)  // width/height ratio of current image, or null if unknown

const bgStyle = computed(() => {
  if (!currentImage.value) return ''
  if (isVideoBg.value) return ''  // video element handles the visual

  const self = occupants.value.find(o => o.id === props.entityId)
  const mx = self?.map_x ?? 50
  const my = self?.map_y ?? 50
  const viewAspect = window.innerWidth / window.innerHeight
  const axis = panAxis(imageAspect.value, viewAspect)

  if (axis === 'x') {
    // Image is wider: fit height, pan horizontally only
    return {
      backgroundImage: `url(${currentImage.value})`,
      backgroundSize: `auto 100%`,
      backgroundPosition: `${mx}% 50%`,
    }
  } else if (axis === 'y') {
    // Image is taller: fit width, pan vertically only
    return {
      backgroundImage: `url(${currentImage.value})`,
      backgroundSize: `100% auto`,
      backgroundPosition: `50% ${my}%`,
    }
  }
  // Unknown aspect: default 180% both axes
  return {
    backgroundImage: `url(${currentImage.value})`,
    backgroundSize: '180%',
    backgroundPosition: `${mx}% ${my}%`,
  }
})

const videoStyle = computed(() => {
  if (!isVideoBg.value || !currentImage.value) return {}
  const self = occupants.value.find(o => o.id === props.entityId)
  const mx = self?.map_x ?? 50
  const my = self?.map_y ?? 50
  return { objectPosition: `${mx}% ${my}%` }
})

// Track image aspect ratio on load — uses video element for .webm/.mp4
watch(currentImage, (url) => {
  if (!url) { imageAspect.value = null; return }
  if (isVideoUrl(url)) {
    const vid = document.createElement('video')
    vid.preload = 'metadata'
    vid.onloadedmetadata = () => { imageAspect.value = vid.videoWidth / vid.videoHeight || null }
    vid.onerror = () => { imageAspect.value = null }
    vid.src = url
  } else {
    const img = new Image()
    img.onload = () => { imageAspect.value = img.width / img.height }
    img.onerror = () => {
      imageAspect.value = null
      // Quality fallback 404'd (e.g. no static sibling) — revert to original.
      if (props.rawBackgroundImage && props.rawBackgroundImage !== url) {
        currentImage.value = props.rawBackgroundImage
      }
    }
    img.src = url
  }
})

// ── Occupant positioning ────────────────────────────

function occupantStyle(index, occupant) {
  // Position only — dot styling is handled by CSS
  if (occupant.map_x != null && occupant.map_y != null) {
    return { left: occupant.map_x + '%', top: occupant.map_y + '%' }
  }
  if (zones.value.length > 0) {
    const zoneIdx = index % zones.value.length
    const z = zones.value[zoneIdx]
    const offset = 5 + (Math.floor(index / zones.value.length) * 5)
    return { left: (z.x + offset) + '%', top: (z.y + offset) + '%' }
  }
  const x = 20 + (index * 15) % 60
  const y = 75 + (index * 5) % 15
  return { left: x + '%', top: y + '%' }
}

function canDragOccupant(occupant) {
  if (props.editZones) return true                // GM can drag anyone
  if (occupant.id === props.entityId) return true  // player can drag self
  if (occupant.type === 'gmc' || occupant.type === 'asset') return true  // always draggable
  return false
}

function occupantInitials(name) {
  return name.split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase()
}

const poolDiceFor = (eid) => {
  const pool = props.remotePools[eid]
  if (!pool) return []
  // In adding phase, dice are strings or { die, label } objects
  if (pool.phase === 'adding') return (pool.dice || []).map(d => typeof d === 'string' ? d : d.die || d)
  // In picking/resolved, dice are result objects
  const results = props.remoteResults[eid]
  if (pool.phase === 'picking' && results?.rolls) return results.rolls
  return []
}
const poolPhaseFor = (eid) => props.remotePools[eid]?.phase || 'adding'

// ── Occupant drag ──────────────────────────────────

const occDragging = ref(null)  // { index }
let occDragMoved = false       // pointer moved past the tap threshold
let occSuppressClick = false   // suppress the synthesized click after a real drag
let dragTarget = null  // non-reactive: nearest target during self-drag
const hoveredDot = ref('')  // reactive: CSS class for proximity highlight (e.g. 'zone-Verdant Dominion')

function onOccupantDragStart(e, occupant, index) {
  if (!canDragOccupant(occupant)) return
  occDragMoved = false
  const el = viewerEl.value
  if (!el) return
  const rect = el.getBoundingClientRect()
  const clientX = e.touches ? e.touches[0].clientX : e.clientX
  const clientY = e.touches ? e.touches[0].clientY : e.clientY
  // Store initial position so we can compute delta
  occDragging.value = {
    index,
    startX: clientX,
    startY: clientY,
    origX: (occupant.map_x ?? parseFloat(occupantStyle(index, occupant).left)) || 50,
    origY: (occupant.map_y ?? parseFloat(occupantStyle(index, occupant).top)) || 50,
  }
  document.addEventListener('mousemove', onOccDragMove)
  document.addEventListener('mouseup', onOccDragEnd)
  document.addEventListener('touchmove', onOccDragMove, { passive: false })
  document.addEventListener('touchend', onOccDragEnd)
}

function onOccDragMove(e) {
  if (!occDragging.value) return
  const el = viewerEl.value
  if (!el) return
  const clientX = e.touches ? e.touches[0].clientX : e.clientX
  const clientY = e.touches ? e.touches[0].clientY : e.clientY
  const start = occDragging.value
  if (!occDragMoved) {
    if (Math.hypot(clientX - start.startX, clientY - start.startY) < 6) return
    occDragMoved = true
  }
  e.preventDefault()
  const rect = el.getBoundingClientRect()
  const dx = ((clientX - start.startX) / rect.width) * 100
  const dy = ((clientY - start.startY) / rect.height) * 100
  const occ = occupants.value[start.index]
  if (occ) {
    const viewX = occDragging.value.origX + dx
    const viewY = occDragging.value.origY + dy
    const img = toImagePos(viewX, viewY)
    occ.map_x = Math.max(2, Math.min(98, Math.round(img.x)))
    occ.map_y = Math.max(2, Math.min(98, Math.round(img.y)))
  }

  // Track nearest target — all positions now image-relative
  if (occ && occ.id === props.entityId) {
    const px = occ.map_x, py = occ.map_y
    let nearest = null, nearestDist = 12
    for (const z of zones.value) {
      const dist = Math.sqrt((z.x - px) ** 2 + (z.y - py) ** 2)
      if (dist < nearestDist) { nearest = { type: 'zone', name: z.name }; nearestDist = dist }
    }
    for (const o of occupants.value) {
      if (o.id === props.entityId) continue
      const ox = o.map_x ?? 50, oy = o.map_y ?? 50
      const dist = Math.sqrt((ox - px) ** 2 + (oy - py) ** 2)
      if (dist < nearestDist) { nearest = { type: 'occupant', id: o.id }; nearestDist = dist }
    }
    for (const nd of navDots.value) {
      const dist = Math.sqrt((nd.x - px) ** 2 + (nd.y - py) ** 2)
      if (dist < nearestDist) { nearest = { type: 'nav', key: nd.key }; nearestDist = dist }
    }
    dragTarget = nearest
    hoveredDot.value = nearest ? `${nearest.type}-${nearest.name || nearest.key || nearest.id}` : ''
  }
}

async function onOccDragEnd() {
  document.removeEventListener('mousemove', onOccDragMove)
  document.removeEventListener('mouseup', onOccDragEnd)
  document.removeEventListener('touchmove', onOccDragMove)
  document.removeEventListener('touchend', onOccDragEnd)
  hoveredDot.value = ''
  if (!occDragging.value) return
  const occ = occupants.value[occDragging.value.index]
  const wasMoved = occDragMoved
  occDragging.value = null
  occDragMoved = false
  if (!occ) return
  if (!wasMoved) return  // tap — the synthesized click handles inspect/pop

  occSuppressClick = true

  // If player dropped near a target, trigger interaction
  if (occ.id === props.entityId && dragTarget && !props.editZones) {
    const t = dragTarget
    dragTarget = null
    if (t.type === 'zone') {
      const zone = zones.value.find(z => z.name === t.name)
      if (zone) {
        const child = childForZone(zone)
        if (child) {
          travelWithAnimation(zone, child)
        } else {
          moveTo(zone.location_id || child?._key || '', '')
        }
        return
      }
    }
    if (t.type === 'nav') {
      const nd = navDots.value.find(d => d.key === t.key)
      if (nd) {
        activeElement.value = { type: 'nav', key: nd.key }
        const fakeZone = { x: nd.x, y: nd.y }
        const fakeChild = { _key: nd.target.id, current_universe: nd.target.universe, transversal_type: nd.type === 'portal' ? nd.transversal_type : null }
        travelWithAnimation(fakeZone, fakeChild, nd.image)
        return
      }
    }
  }
  dragTarget = null
  // Keep self popped
  activeElement.value = { type: 'occupant', id: props.entityId }

  try {
    await fetch(`/api/v1/entities/${occ.id}/map-position`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ map_x: occ.map_x, map_y: occ.map_y }),
    })
  } catch { /* silent */ }
}

// ── Fetch nav data ─────────────────────────────────

async function fetchNav() {
  try {
    const r = await fetch(`/api/v1/locations/${props.locationId}/navigate`)
    const data = await r.json()
    nav.value = data
    zones.value = data.location?.zones || []
    occupants.value = data.occupants || []
    loadNavPositions()

    // Lazy pre-fetch destination nav data in background (doesn't block render)
    preloadDestNavCache()

    // Auto-pop the player's own character
    const self = occupants.value.find(o => o.id === props.entityId)
    if (self) {
      activeElement.value = { type: 'occupant', id: self.id }
    }

    // Fetch pool dice at this location (background, don't block nav)
    fetchPools()
  } catch { /* silent */ }
}

async function fetchPools() {
  try {
    const r = await fetch(`/api/v1/locations/${props.locationId}/pools`)
    const data = await r.json()
    // Merge pool data into remotePools format
    const pools = data.pools || {}
    for (const [eid, pool] of Object.entries(pools)) {
      if (pool.dice && pool.dice.length) {
        props.remotePools[eid] = {
          dice: pool.dice.map(d => d.die),
          player_id: eid,
          phase: 'adding',
        }
      }
    }
  } catch { /* pools endpoint might not exist yet — silent */ }
}

// ── Navigation ─────────────────────────────────────

async function moveTo(locationId, universe) {
  try {
    const r = await fetch(`/api/v1/entities/${props.entityId}/move`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ location: locationId, universe })
    })
    const data = await r.json()
    emit('moved', data)
  } catch { /* silent */ }
}

async function relocate(locationId, universe, consciousness) {
  if (consciousness) {
    try {
      const r = await fetch(`/api/v1/entities/${props.entityId}/consciousness-travel`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ location: locationId })
      })
      const data = await r.json()
      emit('moved', data)
    } catch { /* silent */ }
    return
  }
  await moveTo(locationId, universe)
}

// ── Child location image lookup ────────────────────

function childForZone(zone) {
  // Match zone to child by location_id first, then by name
  const children = nav.value.children || []
  if (zone.location_id) {
    const byId = children.find(c => c._key === zone.location_id)
    if (byId) return byId
  }
  return children.find(c => c.name === zone.name) || null
}

function childImage(zone) {
  const child = childForZone(zone)
  return child?.navdot_image || child?.background_image || null
}

function childId(zone) {
  const child = childForZone(zone)
  return child?._key || null
}

function zoneCache(zone) {
  const cid = childId(zone)
  return cid ? destNavCache.value[cid] : null
}

// ── Nav dot drag ───────────────────────────────────

function onNavDragStart(e, nd) {
  if (!props.editZones) return
  e.preventDefault()
  const el = viewerEl.value
  if (!el) return
  const rect = el.getBoundingClientRect()
  const clientX = e.touches ? e.touches[0].clientX : e.clientX
  const clientY = e.touches ? e.touches[0].clientY : e.clientY
  const startX = clientX, startY = clientY
  const origX = nd.x, origY = nd.y

  function onMove(ev) {
    ev.preventDefault()
    const cx = ev.touches ? ev.touches[0].clientX : ev.clientX
    const cy = ev.touches ? ev.touches[0].clientY : ev.clientY
    const dx = ((cx - startX) / rect.width) * 100
    const dy = ((cy - startY) / rect.height) * 100
    navDotPositions.value[nd.key] = {
      x: Math.max(2, Math.min(98, Math.round(origX + dx))),
      y: Math.max(2, Math.min(98, Math.round(origY + dy))),
    }
  }

  async function onEnd() {
    document.removeEventListener('mousemove', onMove)
    document.removeEventListener('mouseup', onEnd)
    document.removeEventListener('touchmove', onMove)
    document.removeEventListener('touchend', onEnd)
    // Persist to database
    try {
      await fetch('/api/v1/graphql', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query: `mutation($input: UpdateEntityInput!) { updateEntity(input: $input) { id } }`,
          variables: {
            input: {
              id: nav.value.location?._key || props.locationId,
              navPositions: JSON.stringify(navDotPositions.value),
            }
          }
        }),
      })
    } catch {}
  }

  document.addEventListener('mousemove', onMove)
  document.addEventListener('mouseup', onEnd)
  document.addEventListener('touchmove', onMove, { passive: false })
  document.addEventListener('touchend', onEnd)
}

// ── Two-phase interaction ──────────────────────────

async function togglePortalType(nd) {
  const t = (nav.value.transversal || []).find(t => t._key === nd.target.id)
  if (!t) return
  const next = await toggleTransversalType(props.locationId, t._key, t.transversal_type)
  t.transversal_type = next
}

function onDotClick(type, item) {
  if (occSuppressClick) { occSuppressClick = false; return }
  if (props.editZones) {
    // In edit mode, clicking a portal navdot toggles its transversal type.
    if (type === 'nav' && item.type === 'portal') togglePortalType(item)
    return
  }
  // Never un-pop the player's own character
  if (type === 'occupant' && item.id === props.entityId) return
  // If already popped, dismiss; otherwise pop this one
  if (activeElement.value?.type === type) {
    const match = type === 'zone' ? activeElement.value.name === item.name
      : type === 'nav' ? activeElement.value.key === item.key
      : activeElement.value.id === item.id
    if (match) {
      activeElement.value = null
      return
    }
  }
  activeElement.value = type === 'zone' ? { type: 'zone', name: item.name }
    : type === 'nav' ? { type: 'nav', key: item.key }
    : { type: 'occupant', id: item.id }
  if (type === 'occupant') emit('inspectEntity', item.id)
}

async function travelWithAnimation(zone, child, imageUrl = null) {
  const img = imageUrl || childImage(zone)
  const sourceId = props.locationId  // remember where we came from
  if (!img) {
    relocate(child._key, child.current_universe, child.transversal_type === 'consciousness')
    return
  }

  // Keep dot expanded during animation
  activeElement.value = { type: 'zone', name: zone.name }

  // Preload destination image
  const preload = new Image()
  preload.src = img
  await new Promise((resolve) => {
    if (preload.complete) resolve()
    else { preload.onload = resolve; preload.onerror = resolve }
  })

  // Hide elements during portal
  showElements.value = false
  showSelf.value = false

  // Pre-fetch destination nav data to find the exact arrival position
  let arriveX = zone.x, arriveY = zone.y  // fallback: use source zone position
  try {
    const r = await fetch(`/api/v1/locations/${child._key}/navigate`)
    const destNav = await r.json()
    const destLoc = destNav.location
    // Find which dot on destination points back to source
    for (const z of (destLoc?.zones || [])) {
      const destChildren = destNav.children || []
      const c = destChildren.find(ch => ch.name === z.name)
      if (c && c._key === sourceId) { arriveX = z.x; arriveY = z.y; break }
    }
    if (arriveX === zone.x && arriveY === zone.y) {
      // Check parent dot
      const parent = destNav.parent
      if (parent && parent._key === sourceId) {
        const parentPos = (destLoc?.nav_positions?.parent) || { x: 90, y: 15 }
        arriveX = parentPos.x; arriveY = parentPos.y
      }
      // Check portal dot
      const trans = destNav.transversal || []
      if (trans.some(t => t._key === sourceId)) {
        const portalPos = (destLoc?.nav_positions?.portal) || { x: 90, y: 50 }
        arriveX = portalPos.x; arriveY = portalPos.y
      }
    }
  } catch { /* use fallback */ }

  // Compute portal origin using current character position
  const vp = toViewportPos(zone.x, zone.y)

  travelAnim.value = { active: true, x: parseFloat(vp.left), y: parseFloat(vp.top), image: img, bgX: arriveX, bgY: arriveY }

  // Now set the new aspect ratio so background switch uses correct sizing
  if (preload.naturalWidth && preload.naturalHeight) {
    imageAspect.value = preload.naturalWidth / preload.naturalHeight
  }

  relocate(child._key, child.current_universe, child.transversal_type === 'consciousness')

  setTimeout(async () => {
    await fetchNav()

    // Reset overlay to new location's value (may be null)
    optimisticOverlay.value = props.overlay

    // Lock position, switch background, and remove portal — all in one frame
    const so = occupants.value.find(o => o.id === props.entityId)
    if (so) { so.map_x = arriveX; so.map_y = arriveY }
    currentImage.value = img

    // Force-disable transitions on the viewer element to prevent any cross-frame animation
    if (viewerEl.value) {
      viewerEl.value.style.transition = 'none'
    }
    travelAnim.value.active = false
    // Sync background if it changed during travel (watch skips while travelAnim is active)
    if (props.backgroundImage && props.backgroundImage !== currentImage.value) {
      currentImage.value = props.backgroundImage
    }
    activeElement.value = null

    // Fade-in elements
    showElements.value = true

    // Re-enable transitions after paint
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        if (viewerEl.value) viewerEl.value.style.transition = ''
      })
    })
    showSelf.value = true
  }, 1300)
}

function placeCharacterAtSource(sourceId) {
  if (!sourceId) return
  const self = occupants.value.find(o => o.id === props.entityId)
  if (!self) return

  // Determine new position
  let nx = 50, ny = 50
  for (const z of zones.value) {
    const children = nav.value.children || []
    const child = children.find(c => c.name === z.name)
    if (child && child._key === sourceId) { nx = z.x; ny = z.y; break }
  }
  if (nx === 50 && ny === 50) {
    const nd = navDots.value.find(d => d.key === 'parent')
    if (nd && nav.value.parent?._key === sourceId) { nx = nd.x; ny = nd.y }
  }
  if (nx === 50 && ny === 50) {
    const pd = navDots.value.find(d => d.type === 'portal' && d.target?.id === sourceId)
    if (pd) { nx = pd.x; ny = pd.y }
  }

  // Set position (dot not mounted yet, just update data)
  self.map_x = nx; self.map_y = ny

  // Save position
  fetch(`/api/v1/entities/${props.entityId}/map-position`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ map_x: nx, map_y: ny }),
  }).catch(() => {})
}

function onExpandedClick(type, item) {
  if (occSuppressClick) { occSuppressClick = false; return }
  if (props.editZones) return
  if (type === 'zone') {
    const child = childForZone(item)
    if (child) {
      travelWithAnimation(item, child)
    }
  } else if (type === 'nav') {
    // Use travel animation for nav dots too
    activeElement.value = { type: 'nav', key: item.key }
    const fakeZone = { x: item.x, y: item.y }
    const fakeChild = { _key: item.target.id, current_universe: item.target.universe, transversal_type: item.type === 'portal' ? item.transversal_type : null }
    travelWithAnimation(fakeZone, fakeChild, item.image)
  } else if (type === 'occupant') {
    emit('inspectEntity', item.id)
  } else {
    activeElement.value = null
  }
}

// Dismiss pop-out when clicking background
function onBgClick(e) {
  if (e.target === viewerEl.value) {
    // Keep self popped
    const self = occupants.value.find(o => o.id === props.entityId)
    activeElement.value = self ? { type: 'occupant', id: self.id } : null
  }
}



// ── Reactivity ─────────────────────────────────────

watch(() => props.backgroundImage, (img) => {
  if (img === currentImage.value || travelAnim.value.active) return
  currentImage.value = img || ''
}, { immediate: true })

watch(() => props.locationId, () => {
  if (!travelAnim.value.active) fetchNav()
})

const lerpActive = ref(false)
const destNavCache = ref({})  // { [locationId]: { arriveX, arriveY, destAspect } } lazy-populated

// ── Lazy pre-fetch destination nav data for dot overlay positioning ──

async function preloadDestNavCache() {
  const currentId = props.locationId
  const destinations = []

  // Children
  for (const child of (nav.value.children || [])) {
    destinations.push({ id: child._key, name: child.name, kind: 'child' })
  }
  // Parent
  if (nav.value.parent) {
    destinations.push({ id: nav.value.parent._key, name: nav.value.parent.name, kind: 'parent' })
  }
  // Portal
  for (const t of (nav.value.transversal || [])) {
    destinations.push({ id: t._key, name: t.name, kind: 'portal' })
  }

  for (const dest of destinations) {
    if (destNavCache.value[dest.id]) continue  // already cached
    try {
      const r = await fetch(`/api/v1/locations/${dest.id}/navigate`)
      const data = await r.json()
      const loc = data.location
      let arriveX = null, arriveY = null

      if (dest.kind === 'child') {
        // Child's parent dot points back to us
        const parentPos = loc?.nav_positions?.parent
        if (parentPos) { arriveX = parentPos.x; arriveY = parentPos.y }
      } else if (dest.kind === 'parent') {
        // Parent: find which zone on parent points back to us (our name matches a zone name)
        for (const z of (loc?.zones || [])) {
          const destChildren = data.children || []
          if (destChildren.some(c => c.name === z.name && c._key === currentId)) {
            arriveX = z.x; arriveY = z.y; break
          }
        }
      } else if (dest.kind === 'portal') {
        // Portal: use the destination's matching portal dot position
        const idx = (data.transversal || []).findIndex(t => t._key === currentId)
        const posKey = idx > 0 ? `portal:${idx}` : 'portal'
        const portalPos = loc?.nav_positions?.[posKey] || loc?.nav_positions?.portal
        if (portalPos) { arriveX = portalPos.x; arriveY = portalPos.y }
      }

      // Fallback: use default positions
      if (arriveX == null) arriveX = dest.kind === 'parent' ? 90 : 50
      if (arriveY == null) arriveY = dest.kind === 'parent' ? 15 : 50

      // Get destination image aspect
      let destAspect = null
      const bgImg = loc?.background_image
      if (bgImg) {
        destAspect = await new Promise((resolve) => {
          const img = new Image()
          img.onload = () => resolve(img.width / img.height)
          img.onerror = () => resolve(null)
          img.src = bgImg
        })
      }

      destNavCache.value = { ...destNavCache.value, [dest.id]: { arriveX, arriveY, destAspect } }
    } catch { /* skip failed pre-fetches */ }
  }
}

async function fetchNavWithLerp() {
  lerpActive.value = true
  await fetchNav()
  setTimeout(() => { lerpActive.value = false }, 1600)
}

defineExpose({ fetchNav, fetchNavWithLerp })

onMounted(() => {
  console.log('[diag] LocationViewer fetchNav mounted')
  fetchNav()
})
</script>

<style scoped>
.location-viewer {
  position: fixed;
  inset: 0;
  background-size: cover;
  background-position: center;
  background-repeat: no-repeat;
  background-color: #0a0a0f;
  background-image: radial-gradient(ellipse at 40% 40%, #1a1a2e 0%, #0a0a0f 70%);
  transition: background-image 0.8s ease, background-position 0.3s ease-out;
  z-index: 0;
}
/* No background fade during portal travel — portal handles the transition */
.location-viewer.portal-active {
  transition: none;
}

.video-bg {
  position: absolute; inset: 0;
  width: 100%; height: 100%;
  object-fit: cover;
  z-index: 0; pointer-events: none;
}

.loc-label {
  position: absolute;
  top: env(safe-area-inset-top, 16px);
  left: 16px;
  font-size: 20px; font-weight: 600;
  text-shadow: 0 2px 8px rgba(0,0,0,0.8);
  z-index: 2;
  pointer-events: none;
}

.uni-label {
  position: absolute;
  top: calc(env(safe-area-inset-top, 16px) + 24px);
  left: 16px;
  font-size: 12px; color: var(--text-dim);
  text-transform: uppercase; letter-spacing: 2px;
  z-index: 2;
  pointer-events: none;
}

/* ── Overlay switcher ────────────────────────────── */

.overlay-switcher {
  position: absolute;
  top: calc(env(safe-area-inset-top, 16px) + 44px);
  left: 12px;
  display: flex; gap: 2px;
  z-index: 6;
}
.overlay-btn {
  width: 28px; height: 28px;
  border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  font-size: 14px; padding: 0;
  background: rgba(10,10,20,0.5);
  backdrop-filter: blur(4px);
  border: 1px solid rgba(255,255,255,0.1);
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s;
  -webkit-tap-highlight-color: transparent;
}
.overlay-btn.active {
  background: rgba(64,136,212,0.3);
  border-color: var(--accent);
}
.overlay-btn:hover { background: rgba(255,255,255,0.1); }

.overlay-sep {
  width: 1px; height: 20px; align-self: center;
  background: rgba(255,255,255,0.12); margin: 0 4px;
}

.arrange-btn { font-size: 12px; }

/* ── Map dots ────────────────────────────────────── */

.map-dot {
  position: absolute;
  /* Centered via negative margins (not transform) to preserve background-attachment: fixed */
  margin-left: -8px; margin-top: -8px;
  border-radius: 50%;
  border: none;
  cursor: pointer;
  transition: width 0.25s ease, height 0.25s ease, margin 0.25s ease, background 0.25s ease, border 0.25s ease, box-shadow 0.25s ease;
  -webkit-tap-highlight-color: transparent;
  padding: 0;
  z-index: 3;
}

/* Zone dots: small colored circle */
.zone-dot {
  width: 16px; height: 16px;
  background: rgba(64,184,96,0.7);
  box-shadow: 0 0 6px rgba(64,184,96,0.4);
}

/* Occupant dots */
.occ-dot {
  width: 16px; height: 16px;
}
.occ-dot.occ-character { background: rgba(64,136,212,0.8); box-shadow: 0 0 6px rgba(64,136,212,0.4); }
.occ-dot.occ-gmc { background: rgba(232,136,48,0.8); box-shadow: 0 0 6px rgba(232,136,48,0.4); }

.pool-badge {
  position: absolute;
  z-index: 22;
  background: rgba(30,30,30,0.85);
  color: #fff;
  font-size: 0.65rem;
  font-weight: 700;
  min-width: 16px;
  height: 16px;
  line-height: 16px;
  text-align: center;
  border-radius: 8px;
  padding: 0 4px;
  box-shadow: 0 0 4px rgba(0,0,0,0.5);
  pointer-events: none;
  transition: opacity 0.3s ease;
}

.occ-dot.self {
  z-index: 20 !important;
  border: 2px solid rgba(255,255,255,0.5) !important;
  box-shadow: 0 0 16px rgba(100,180,255,0.7), 0 0 32px rgba(100,180,255,0.35), 0 0 64px rgba(100,180,255,0.18) !important;
  animation: selfPulse 2.5s ease-in-out infinite;
}

@keyframes selfPulse {
  0%, 100% { box-shadow: 0 0 16px rgba(100,180,255,0.7), 0 0 32px rgba(100,180,255,0.35), 0 0 64px rgba(100,180,255,0.18); }
  50% { box-shadow: 0 0 24px rgba(100,180,255,0.9), 0 0 48px rgba(100,180,255,0.5), 0 0 80px rgba(100,180,255,0.25); }
}

/* Non-self dots lerp only on SSE-triggered position updates */
.occ-dot:not(.self).lerping {
  transition: left 1.5s ease-out, top 1.5s ease-out, width 0.25s ease, height 0.25s ease, margin 0.25s ease, background 0.25s ease, border 0.25s ease, box-shadow 0.25s ease;
}

/* Navigation dots */
.nav-dot {
  width: 16px; height: 16px;
}
.nav-dot.nav-parent { background: rgba(200,170,60,0.8); box-shadow: 0 0 6px rgba(200,170,60,0.4); }
.nav-dot.nav-portal { background: rgba(160,80,200,0.8); box-shadow: 0 0 6px rgba(160,80,200,0.4); }
.nav-dot.expanded {
  width: clamp(120px, 14vw, 260px) !important; height: clamp(120px, 14vw, 260px) !important;
  margin-left: calc(clamp(120px, 14vw, 260px) / -2); margin-top: calc(clamp(120px, 14vw, 260px) / -2);
  background: rgba(10,10,20,0.85);
  backdrop-filter: blur(8px);
  border: none;
  box-shadow: inset 0 0 20px rgba(0,0,0,0.6), inset 0 0 4px rgba(255,255,255,0.1);
  z-index: 10;
  overflow: hidden;
}

/* Expanded state — smooth transition from dot to circle */
.map-dot.expanded {
  width: clamp(120px, 14vw, 260px) !important; height: clamp(120px, 14vw, 260px) !important;
  margin-left: calc(clamp(120px, 14vw, 260px) / -2); margin-top: calc(clamp(120px, 14vw, 260px) / -2);
  background: rgba(10,10,20,0.85);
  backdrop-filter: blur(8px);
  border: none;
  box-shadow: inset 0 0 20px rgba(0,0,0,0.6), inset 0 0 4px rgba(255,255,255,0.1);
  z-index: 10;
  overflow: hidden;
}
.occ-dot.expanded {
  width: clamp(60px, 5.5vw, 88px) !important; height: clamp(60px, 5.5vw, 88px) !important;
  margin-left: calc(clamp(60px, 5.5vw, 88px) / -2); margin-top: calc(clamp(60px, 5.5vw, 88px) / -2);
}

/* Inner overlay — fills the expanded dot, hidden when collapsed */
.dot-overlay {
  position: absolute; inset: 0;
  border-radius: 50%;
  background-size: cover;
  background-position: center;
  opacity: 0;
  transition: opacity 0.2s ease;
  cursor: pointer;
  pointer-events: none;
}
.map-dot.expanded .dot-overlay { opacity: 1; pointer-events: auto; }

.zone-dot .dot-overlay,
.nav-dot .dot-overlay {
  background-attachment: fixed;
}
.occ-img-overlay { border-radius: 50%; }

.dot-label, .dot-initials {
  position: absolute; inset: 0;
  display: flex; align-items: center; justify-content: center;
  opacity: 0; transition: opacity 0.2s ease;
  cursor: pointer;
}
.map-dot.expanded .dot-label,
.map-dot.expanded .dot-initials { opacity: 1; }

.dot-label {
  font-size: 11px; font-weight: 600; color: var(--text);
  text-align: center; padding: 4px; line-height: 1.2;
}
.dot-initials {
  font-size: 18px; font-weight: 800; color: #fff;
}

/* Draggable state — show as expanded bubbles */
.map-dot.draggable {
  cursor: grab; border: 2px dashed var(--accent);
  animation: dot-pulse 2s ease-in-out infinite;
}
/* Zones full-size when editing */
.zone-dot.draggable {
  width: 240px !important; height: 240px !important;
  margin-left: -120px; margin-top: -120px;
  background: rgba(10,10,20,0.85);
  backdrop-filter: blur(8px);
  z-index: 10;
  overflow: hidden;
}
/* Occupants full-size when editing (self stays same) */
.occ-dot.draggable:not(.self) {
  width: 96px !important; height: 96px !important;
  margin-left: -48px; margin-top: -48px;
  background: rgba(10,10,20,0.85);
  backdrop-filter: blur(8px);
  z-index: 10;
  overflow: hidden;
}
/* Nav dots full-size when editing */
.nav-dot.draggable {
  width: 240px !important; height: 240px !important;
  margin-left: -120px; margin-top: -120px;
  background: rgba(10,10,20,0.85);
  backdrop-filter: blur(8px);
  z-index: 10;
  overflow: hidden;
}
/* Show overlay in edit mode */
.map-dot.draggable .dot-overlay,
.map-dot.draggable .dot-label,
.map-dot.draggable .dot-initials {
  opacity: 1;
}
@keyframes dot-pulse {
  0%, 100% { border-color: var(--accent); }
  50% { border-color: rgba(64,136,212,0.3); }
}



/* ── Transitions ─────────────────────────────────── */

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

/* ── Travel expansion animation ──────────────────── */

.travel-overlay {
  position: fixed; inset: 0; z-index: 50;
  background-size: cover;
  background-position: center;
  clip-path: circle(clamp(40px, 5vw, 120px) at var(--travel-x, 50%) var(--travel-y, 50%));
  animation: portal-expand 1.2s ease-out forwards;
  pointer-events: none;
  opacity: 1;
}

@keyframes portal-expand {
  0% {
    clip-path: circle(clamp(40px, 5vw, 120px) at var(--travel-x, 50%) var(--travel-y, 50%));
  }
  100% {
    clip-path: circle(150vmax at var(--travel-x, 50%) var(--travel-y, 50%));
  }
}

.fade-in {
  animation: fadeIn 0.4s ease both;
}
/* Self character pops in after implosion completes */
.self.fade-in {
  animation: arrivePop 0.5s cubic-bezier(0.34, 1.56, 0.64, 1) both;
  animation-delay: 0.9s;
}

@keyframes arrivePop {
  0% {
    opacity: 0;
    transform: scale(0.3);
    filter: brightness(2);
  }
  60% {
    opacity: 1;
    transform: scale(1.1);
    filter: brightness(1.2);
  }
  100% {
    opacity: 1;
    transform: scale(1);
    filter: brightness(1);
  }
}

/* ── Arrival rings ────────────────────────────────── */

.arrival-ring {
  position: absolute;
  border-radius: 50%;
  pointer-events: none;
  z-index: 19;
}

/* Phase 1 — Reverse ripple (energy drawn inward) */
.ring-implode {
  border: 4px solid rgba(100,180,255,0.6);
  animation: implodeRing 0.9s cubic-bezier(0.4, 0, 1, 1) both;
  box-shadow: 0 0 20px white;
}
.ring-implode-1 { animation-delay: 0s; }
.ring-implode-2 { animation-delay: 0.15s; }

@keyframes implodeRing {
  0%   { width: 600px; height: 600px; margin-left: -300px; margin-top: -300px; opacity: 0.4; }
  70%  { opacity: 0.8; }
  100% { width: 8px; height: 8px; margin-left: -4px; margin-top: -4px; opacity: 1; }
}

/* Phase 2 — Portal flash */
.ring-flash {
  width: 40px; height: 40px;
  margin-left: -20px; margin-top: -20px;
  background: radial-gradient(circle, rgba(255,255,255,0.9) 0%, rgba(200,220,255,0.6) 30%, transparent 70%);
  animation: portalFlash 0.3s ease-out both;
  animation-delay: 0.85s;
}

@keyframes portalFlash {
  0%   { width: 8px; height: 8px; margin-left: -4px; margin-top: -4px; opacity: 0; }
  30%  { width: 60px; height: 60px; margin-left: -30px; margin-top: -30px; opacity: 1; }
  100% { width: 90px; height: 90px; margin-left: -45px; margin-top: -45px; opacity: 0; }
}

/* Phase 3 — Triple burst outward */
.ring-burst {
  border: 2px solid rgba(100,180,255,0.7);
  animation: burstRing 1s ease-out both;
}
.ring-burst-1 { animation-delay: 0.9s; }
.ring-burst-2 { animation-delay: 1.05s; }
.ring-burst-3 { animation-delay: 1.2s; }

@keyframes burstRing {
  0%   { width: 20px; height: 20px; margin-left: -10px; margin-top: -10px; opacity: 1; }
  100% { width: 240px; height: 240px; margin-left: -120px; margin-top: -120px; opacity: 0; }
}

@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}
</style>
