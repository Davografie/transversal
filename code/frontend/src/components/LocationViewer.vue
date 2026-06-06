<template>
  <div ref="viewerEl" class="location-viewer" :class="{ 'portal-active': travelAnim.active }" :style="bgStyle" @click="onBgClick">
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
    <button
      v-if="showElements"
      class="map-dot zone-dot fade-in"
      :class="{ expanded: (activeElement?.type === 'zone' && activeElement?.name === z.name) || hoveredDot === 'zone-' + z.name, draggable: editZones }"
      :style="parallaxedStyle(z.x, z.y)"
      @mousedown="(e) => onZoneDragStart(e, z, i)"
      @touchstart="(e) => onZoneDragStart(e, z, i)"
      @click.stop="onDotClick('zone', z)"
    >
      <div class="dot-overlay" v-if="childImage(z.name)" :style="{ backgroundImage: 'url(' + childImage(z.name) + ')' }" @click.stop="onExpandedClick('zone', z)" />
      <span v-else class="dot-label" @click.stop="onExpandedClick('zone', z)">{{ z.name }}</span>
    </button>
    </template>

    <!-- Occupant dots (non-self only) -->
    <template v-for="(o, i) in occupants.filter(x => x.id !== entityId)" :key="'o-' + o.id">
    <button
      v-if="!travelAnim.active && showElements"
      class="map-dot occ-dot fade-in"
      :class="['occ-' + o.type, { expanded: (activeElement?.type === 'occupant' && activeElement?.id === o.id) || hoveredDot === 'occupant-' + o.id, draggable: canDragOccupant(o) }]"
      :style="parallaxedStyle(o.map_x ?? occupantX(index, o), o.map_y ?? occupantY(index, o))"
      :title="canDragOccupant(o) ? 'Drag to reposition' : o.name"
      @mousedown="(e) => onOccupantDragStart(e, o, i)"
      @touchstart="(e) => onOccupantDragStart(e, o, i)"
      @click.stop="onDotClick('occupant', o)"
    >
      <div v-if="o.image" class="dot-overlay occ-img-overlay" :style="{ backgroundImage: 'url(' + o.image + ')' }" @click.stop="onExpandedClick('occupant', o)" />
      <span v-else class="dot-initials" @click.stop="onExpandedClick('occupant', o)">{{ occupantInitials(o.name) }}</span>
    </button>
    </template>

    <!-- Navigation dots -->
    <template v-for="nd in navDots" :key="'nav-' + nd.key">
    <button
      v-if="showElements"
      class="map-dot nav-dot fade-in"
      :class="'nav-' + nd.type + ((activeElement?.type === 'nav' && activeElement?.key === nd.key) || hoveredDot === 'nav-' + nd.key ? ' expanded' : '') + (editZones ? ' draggable' : '')"
      :style="parallaxedStyle(nd.x, nd.y)"
      @mousedown="(e) => onNavDragStart(e, nd)"
      @touchstart="(e) => onNavDragStart(e, nd)"
      @click.stop="onDotClick('nav', nd)"
    >
      <div v-if="nd.image" class="dot-overlay" :style="{ backgroundImage: 'url(' + nd.image + ')' }" @click.stop="onExpandedClick('nav', nd)" />
      <span v-else class="dot-label" @click.stop="onExpandedClick('nav', nd)">{{ nd.name }}</span>
    </button>
    </template>

    <!-- Self character dot (no parallax — 1:1 with touch) -->
    <button
      v-if="!travelAnim.active && showElements && showSelf"
      class="map-dot occ-dot fade-in self"
      :class="['occ-character', { expanded: true }]"
      :style="selfStyle"
      title="Drag to explore"
      @mousedown="(e) => onSelfDragStart(e)"
      @touchstart="(e) => onSelfDragStart(e)"
    >
      <div v-if="selfImage" class="dot-overlay occ-img-overlay" :style="{ backgroundImage: 'url(' + selfImage + ')' }" />
      <span v-else class="dot-initials">{{ selfInitials }}</span>
    </button>

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

const props = defineProps({
  locationId: { type: String, required: true },
  locationName: { type: String, default: '' },
  universe: { type: String, default: 'earth' },
  backgroundImage: { type: String, default: '' },
  entityId: { type: String, required: true },
  editZones: { type: Boolean, default: false },
  overlay: { type: String, default: null },
  gmMode: { type: Boolean, default: false },
})

const emit = defineEmits(['moved', 'update:editZones'])

const currentImage = ref('')
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
  { value: null, icon: '🌫', label: 'None' },
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
const selfStyle = computed(() => {
  const s = selfOccupant.value
  return { left: (s.map_x ?? 50).toFixed(1) + '%', top: (s.map_y ?? 50).toFixed(1) + '%' }
})
const selfImage = computed(() => selfOccupant.value.image || null)
const selfInitials = computed(() => occupantInitials(selfOccupant.value.name || 'You'))

function onSelfDragStart(e) {
  const idx = occupants.value.findIndex(o => o.id === props.entityId)
  if (idx === -1) return
  onOccupantDragStart(e, occupants.value[idx], idx)
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
      if (parsed.parent) navDotPositions.value.parent = parsed.parent
      if (parsed.portal) navDotPositions.value.portal = parsed.portal
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
  if (nav.value.transversal?.length) {
    const t = nav.value.transversal[0]
    const pos = navDotPositions.value.portal
    dots.push({
      key: 'portal', type: 'portal', name: t.name,
      image: t.background_image || null,
      x: pos.x, y: pos.y,
      target: { id: t._key, universe: t.current_universe },
    })
  }
  return dots
})

const imageAspect = ref(null)  // width/height ratio of current image, or null if unknown

const bgStyle = computed(() => {
  if (!currentImage.value) return ''

  const self = occupants.value.find(o => o.id === props.entityId)
  const mx = self?.map_x ?? 50
  const my = self?.map_y ?? 50
  const vw = window.innerWidth
  const vh = window.innerHeight
  const viewAspect = vw / vh
  const imgAspect = imageAspect.value

  if (imgAspect && imgAspect > viewAspect) {
    // Image is wider: fit height, pan horizontally only
    return {
      backgroundImage: `url(${currentImage.value})`,
      backgroundSize: `auto 100%`,
      backgroundPosition: `${mx}% 50%`,
    }
  } else if (imgAspect && imgAspect < viewAspect) {
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

// Track image aspect ratio on load
watch(currentImage, (url) => {
  if (!url) { imageAspect.value = null; return }
  const img = new Image()
  img.onload = () => { imageAspect.value = img.width / img.height }
  img.onerror = () => { imageAspect.value = null }
  img.src = url
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
  if (props.editZones) return true          // GM can drag anyone
  if (occupant.id === props.entityId) return true  // player can drag self
  return false
}

function occupantInitials(name) {
  return name.split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase()
}

// ── Occupant drag ──────────────────────────────────

const occDragging = ref(null)  // { index }
let dragTarget = null  // non-reactive: nearest target during self-drag
const hoveredDot = ref('')  // reactive: CSS class for proximity highlight (e.g. 'zone-Verdant Dominion')

function onOccupantDragStart(e, occupant, index) {
  if (!canDragOccupant(occupant)) return
  e.preventDefault()
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
  e.preventDefault()
  const el = viewerEl.value
  if (!el) return
  const rect = el.getBoundingClientRect()
  const clientX = e.touches ? e.touches[0].clientX : e.clientX
  const clientY = e.touches ? e.touches[0].clientY : e.clientY
  const dx = ((clientX - occDragging.value.startX) / rect.width) * 100
  const dy = ((clientY - occDragging.value.startY) / rect.height) * 100
  const occ = occupants.value[occDragging.value.index]
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
  occDragging.value = null
  if (!occ) return

  // If player dropped near a target, trigger interaction
  if (occ.id === props.entityId && dragTarget && !props.editZones) {
    const t = dragTarget
    dragTarget = null
    if (t.type === 'zone') {
      const children = nav.value.children || []
      const child = children.find(c => c.name === t.name)
      if (child) {
        const zone = zones.value.find(z => z.name === t.name)
        if (zone) {
          travelWithAnimation(zone, child)
        } else {
          moveTo(child._key, child.current_universe)
        }
        return
      }
    }
    if (t.type === 'nav') {
      const nd = navDots.value.find(d => d.key === t.key)
      if (nd) {
        activeElement.value = { type: 'nav', key: nd.key }
        const fakeZone = { x: nd.x, y: nd.y }
        const fakeChild = { _key: nd.target.id, current_universe: nd.target.universe }
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

    // Auto-pop the player's own character
    const self = occupants.value.find(o => o.id === props.entityId)
    if (self) {
      activeElement.value = { type: 'occupant', id: self.id }
    }
  } catch { /* silent */ }
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

// ── Child location image lookup ────────────────────

function childImage(zoneName) {
  const children = nav.value.children || []
  const child = children.find(c => c.name === zoneName)
  return child?.background_image || null
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

function onDotClick(type, item) {
  if (props.editZones) return
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
}

async function travelWithAnimation(zone, child, imageUrl = null) {
  const img = imageUrl || childImage(zone.name)
  const sourceId = props.locationId  // remember where we came from
  if (!img) {
    moveTo(child._key, child.current_universe)
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

  moveTo(child._key, child.current_universe)

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
    const pd = navDots.value.find(d => d.key === 'portal')
    if (pd && nav.value.transversal?.some(t => t._key === sourceId)) { nx = pd.x; ny = pd.y }
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
  if (props.editZones) return
  if (type === 'zone') {
    const children = nav.value.children || []
    const child = children.find(c => c.name === item.name)
    if (child) {
      travelWithAnimation(item, child)
    }
  } else if (type === 'nav') {
    // Use travel animation for nav dots too
    activeElement.value = { type: 'nav', key: item.key }
    const fakeZone = { x: item.x, y: item.y }
    const fakeChild = { _key: item.target.id, current_universe: item.target.universe }
    travelWithAnimation(fakeZone, fakeChild, item.image)
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

onMounted(fetchNav)
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
.occ-dot.self { z-index: 20 !important; }

/* Navigation dots */
.nav-dot {
  width: 16px; height: 16px;
}
.nav-dot.nav-parent { background: rgba(200,170,60,0.8); box-shadow: 0 0 6px rgba(200,170,60,0.4); }
.nav-dot.nav-portal { background: rgba(160,80,200,0.8); box-shadow: 0 0 6px rgba(160,80,200,0.4); }
.nav-dot.expanded {
  width: 240px !important; height: 240px !important;
  margin-left: -120px; margin-top: -120px;
  background: rgba(10,10,20,0.85);
  backdrop-filter: blur(8px);
  border: 2px solid rgba(255,255,255,0.2);
  z-index: 10;
  overflow: hidden;
}

/* Expanded state — smooth transition from dot to circle */
.map-dot.expanded {
  width: 240px !important; height: 240px !important;
  margin-left: -120px; margin-top: -120px;
  background: rgba(10,10,20,0.85);
  backdrop-filter: blur(8px);
  border: 2px solid rgba(255,255,255,0.2);
  box-shadow: 0 4px 20px rgba(0,0,0,0.5);
  z-index: 10;
  overflow: hidden;
}
.occ-dot.expanded {
  width: 96px !important; height: 96px !important;
  margin-left: -48px; margin-top: -48px;
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
}
.map-dot.expanded .dot-overlay { opacity: 1; }

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
  position: absolute; inset: 0; z-index: 1;
  pointer-events: none;
  opacity: 0.6;
}

.particle-canvas {
  position: absolute; inset: 0; z-index: 2;
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
  clip-path: circle(120px at var(--travel-x, 50%) var(--travel-y, 50%));
  animation: portal-expand 1.2s ease-out forwards;
  pointer-events: none;
  opacity: 1;
}

@keyframes portal-expand {
  0% {
    clip-path: circle(120px at var(--travel-x, 50%) var(--travel-y, 50%));
  }
  100% {
    clip-path: circle(150vmax at var(--travel-x, 50%) var(--travel-y, 50%));
  }
}

.fade-in {
  animation: fadeIn 0.4s ease both;
}
/* Self character gets a pop animation on arrival */
.self.fade-in {
  animation: arrivePop 0.5s cubic-bezier(0.34, 1.56, 0.64, 1) both;
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

@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}
</style>
