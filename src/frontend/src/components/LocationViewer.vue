<template>
  <div ref="viewerEl" class="location-viewer" :class="{ 'portal-active': travelAnim.active }" :style="{ '--controlled-scale': CONTROLLED_SCALE }" @click="onBgClick">
    <!-- Scene layer: background + world dots, all panned by ONE transform.
         Dots sit at image-space coordinates inside the layer, so panning
         never moves them individually (compositor-only, no per-dot paint). -->
    <div class="scene-layer" :style="sceneLayerStyle">
      <video v-if="currentImage && isVideoBg" ref="videoBgEl" :src="currentImage" class="scene-media" autoplay loop muted playsinline />
      <img v-else-if="currentImage" :src="currentImage" class="scene-media" alt="" />

      <!-- Zone dots -->
      <template v-for="(z, i) in zones" :key="'z-' + zoneId(z, i)">
      <MapDot
        v-if="showElements"
        type="zone"
        :x="z.x" :y="z.y"
        :image="childImage(z)"
        :label="z.name"
        :expanded="editZones || (activeElement?.type === 'zone' && activeElement?.id === zoneId(z, i)) || (expandLevels['zone-' + zoneId(z, i)] || 0) > 0"
        :draggable="editZones"
        :title="z.name"
        :hole-style="zoneHoleStyle(z)"
        :expand-level="expandLevels['zone-' + zoneId(z, i)] || 0"
        :class="{ armed: armedDot === 'zone-' + zoneId(z, i) }"
        @click="onDotClick('zone', z)"
        @overlay-click="onExpandedClick('zone', z)"
        @drag-start="(e) => onZoneDragStart(e, z, i)"
      />
      </template>

      <!-- Occupant dots (non-self only, always expanded) -->
      <template v-for="(o, i) in occupantDots" :key="'o-' + o.id">
      <MapDot
        v-if="!travelAnim.active && showElements"
        type="occupant"
        :variant="o.type"
        :class="{ 'dot-draft': o.unpublished, viewed: o.id === viewingEntityId, controlled: isControlled(o.id), settling: settlingIds.includes(o.id) }"
        :x="o.map_x ?? occupantX(i, o)" :y="o.map_y ?? occupantY(i, o)"
        :image="o.image"
        :image-transparent="!!o.image_transparent"
        :initials="occupantInitials(o.name)"
        :expanded="true"
        :draggable="canDragOccupant(o)"
        :lerping="lerpActive"
        :title="canDragOccupant(o) ? 'Drag to reposition' : (o.unpublished ? o.name + ' (draft)' : o.name)"
        @click="onDotClick('occupant', o)"
        @overlay-click="onExpandedClick('occupant', o)"
        @drag-start="(e) => onOccupantDragStart(e, o, i)"
      />
      <!-- Pool dice ring around occupant dot -->
      <PoolDiceRing
        v-if="!travelAnim.active && showElements && (poolDiceFor(o.id).length > 0 || remoteResults[o.id])"
        :dice="poolDiceFor(o.id)"
        :phase="poolPhaseFor(o.id)"
        :cx="o.map_x ?? occupantX(i, o)"
        :cy="o.map_y ?? occupantY(i, o)"
        :resolved="remoteResults[o.id] || null"
        :scale="isControlled(o.id) ? CONTROLLED_SCALE : 1"
        :transparent="!!o.image_transparent"
      />
      </template>

      <!-- Navigation dots -->
      <template v-for="nd in navDots" :key="'nav-' + nd.key">
      <MapDot
        v-if="showElements"
        type="nav"
        :variant="nd.type"
        :x="nd.x" :y="nd.y"
        :image="nd.image"
        :label="nd.name"
        :expanded="editZones || (activeElement?.type === 'nav' && activeElement?.key === nd.key) || (expandLevels['nav-' + nd.key] || 0) > 0"
        :draggable="editZones"
        :title="nd.name"
        :hole-style="navHoleStyle(nd)"
        :expand-level="expandLevels['nav-' + nd.key] || 0"
        :class="{ armed: armedDot === 'nav-' + nd.key }"
        @click="onDotClick('nav', nd)"
        @overlay-click="onExpandedClick('nav', nd)"
        @drag-start="(e) => onNavDragStart(e, nd)"
      />
      </template>
    </div>

    <!-- Visual overlay layer + canvas particles -->
    <SceneEffectsLayer :overlay="optimisticOverlay" :enabled="effectsEnabled" />

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

    <!-- Arrival animation rings -->
    <ArrivalRings
      v-if="!travelAnim.active && showElements && showSelf"
      :x="selfX"
      :y="selfY"
    />

    <!-- Self character dot (no parallax — 1:1 with touch). Keyed by the
         perspective entity so a take remounts it: the dot grows in rather than
         being patched in place (an unkeyed element never replays arrivePop). -->
    <MapDot
      v-if="!travelAnim.active && showElements && showSelf"
      :key="'self-' + (entityId || 'roam')"
      type="self"
      variant="character"
      class="fade-in"
      :class="{ controlled: !!entityId }"
      :x="selfX" :y="selfY"
      :image="selfImage"
      :image-transparent="!!selfOccupant.image_transparent"
      :initials="selfInitials"
      :expanded="true"
      :draggable="true"
      title="Drag to explore"
      @click="onSelfClick()"
      @overlay-click="onSelfClick()"
      @drag-start="(e) => onSelfDragStart(e)"
    />
    <PoolDiceRing
      v-if="!travelAnim.active && showElements && (poolDiceFor(entityId).length > 0 || remoteResults[entityId])"
      :dice="poolDiceFor(entityId)"
      :phase="poolPhaseFor(entityId)"
      :cx="selfX"
      :cy="selfY"
      :resolved="remoteResults[entityId] || null"
      :scale="isControlled(entityId) ? CONTROLLED_SCALE : 1"
      :transparent="!!selfOccupant.image_transparent"
    />

    <!-- Travel expansion animation -->
    <TravelOverlay
      v-if="travelAnim.active"
      :x="travelAnim.x"
      :y="travelAnim.y"
      :image="travelAnim.image"
      :bg-x="travelAnim.bgX"
      :bg-y="travelAnim.bgY"
    />

  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import SceneEffectsLayer from './location/SceneEffectsLayer.vue'
import ArrivalRings from './location/ArrivalRings.vue'
import TravelOverlay from './location/TravelOverlay.vue'
import MapDot from './MapDot.vue'
import PoolDiceRing from './PoolDiceRing.vue'
import { useTransversalLinks } from '@/composables/useTransversalLinks.js'
import { isVideoUrl, coverOverscan, probeAspect } from '@/composables/media.js'
import { perfMark } from '@/composables/perfLog.js'
import { startFrameProfile, stopFrameProfile, notePointerEvent, noteFrameWork } from '@/composables/frameProfile.js'

// ── Tunable constants ──────────────────────────────────────────────────────
// Edit these to tune the navigation feel. PAN_OVERSCAN (background overscan,
// default 1.1) lives in composables/media.js next to coverOverscan.
const INVERSE_PAN_STRENGTH = 2   // hole "see-through" parallax strength (>1 = stronger)
const TEASER_ZOOM = 2            // mobile teaser-camera zoom factor
const CAMERA_START = 0.6         // window-height fraction where the zoom-in begins
const CAMERA_FULL = 0.2          // window-height fraction where the zoom is full
const EXPAND_PROXIMITY = 24      // image-% — distance at which bubbles pop out
const TRAVEL_PROXIMITY_FACTOR = 0.5  // <1 = narrower drop-to-travel zone
const CONTROLLED_SCALE = 1.4     // actively-controlled dots render this much bigger
                                 // (also drives the pool dice ring radius, so the
                                 // ring stays outside the rim at every size)

const props = defineProps({
  locationId: { type: String, required: true },
  locationName: { type: String, default: '' },
  universe: { type: String, default: 'earth' },
  backgroundImage: { type: String, default: '' },
  rawBackgroundImage: { type: String, default: '' },  // pre-quality URL, used as load-error fallback
  entityId: { type: String, default: null },  // null = GM free-roam (B95)
  viewingEntityId: { type: String, default: null },  // read-only peek target (see PeersBar "viewing")
  controlledEntityIds: { type: Array, default: () => [] },  // entities a client is driving (sized up)
  editZones: { type: Boolean, default: false },
  overlay: { type: String, default: null },
  gmMode: { type: Boolean, default: false },
  remotePools: { type: Object, default: () => ({}) },  // entity_id → { dice: [...], player_id, phase }
  remoteResults: { type: Object, default: () => ({}) },  // entity_id → { total, effect_die, rolls, ... }
})

const emit = defineEmits(['moved', 'update:editZones', 'inspectEntity', 'dragging'])
const { toggleTransversalType } = useTransversalLinks()

const currentImage = ref('')
const videoBgEl = ref(null)
const isVideoBg = computed(() => isVideoUrl(currentImage.value))
const nav = ref({})
const zones = ref([])
const occupants = ref([])
// Occupants shown as navdots: players never see unpublished (GM-only draft)
// entities; the architect sees them (marked as drafts).
const occupantDots = computed(() =>
  occupants.value.filter(o => o.id !== props.entityId && (props.gmMode || !o.unpublished))
)

// A take/release swaps elements — the local entity is excluded from
// `occupantDots` and renders as the keyed self dot — so the dot that *loses* the
// perspective mounts fresh and would appear at full size. Mark it for one
// animation cycle so it shrinks out instead. Skipped when the entity is still
// driven by a client: then its size does not change at all.
const settlingIds = ref([])
let lastPerspectiveId = null
watch(() => props.entityId, (id) => {
  const prev = lastPerspectiveId
  lastPerspectiveId = id
  if (!prev || prev === id || props.controlledEntityIds.includes(prev)) return
  settlingIds.value = [...settlingIds.value, prev]
  setTimeout(() => {
    settlingIds.value = settlingIds.value.filter(x => x !== prev)
  }, 300)
}, { immediate: true })
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

// Self position in image space. With a perspective entity it's that occupant's
// map position; without one (GM free-roam, entityId == null) it's the GM dot's
// position for THIS location, else centre. The GM dot is device-local and
// persisted per location, so a refresh — or a return — restores it.
const GM_DOT_KEY = 'gmDotPositions'
function loadGmDots() {
  try { return JSON.parse(localStorage.getItem(GM_DOT_KEY) || '{}') || {} } catch { return {} }
}
const gmDotPositions = ref(loadGmDots())  // { [locationId]: { x, y } }
const gmSelfPos = computed(() => gmDotPositions.value[props.locationId] || null)
function setGmDotPos(x, y) {
  gmDotPositions.value = { ...gmDotPositions.value, [props.locationId]: { x, y } }
}
function persistGmDots() {
  try { localStorage.setItem(GM_DOT_KEY, JSON.stringify(gmDotPositions.value)) } catch { /* storage unavailable */ }
}
const selfPos = computed(() => {
  const o = occupants.value.find(o => o.id === props.entityId)
  const g = gmSelfPos.value
  return { x: o?.map_x ?? g?.x ?? 50, y: o?.map_y ?? g?.y ?? 50 }
})

const selfOccupant = computed(() => occupants.value.find(o => o.id === props.entityId) || { name: '', image: null })
const selfX = computed(() => selfPos.value.x)
const selfY = computed(() => selfPos.value.y)
const selfImage = computed(() => selfOccupant.value.image || null)
// No portrait and no character name → show the role glyph used by the player
// settings overlay (🏛 Architect / 🎭 Player) instead of a bare "Y" (B34).
const selfInitials = computed(() => {
  const o = occupants.value.find(o => o.id === props.entityId)
  if (o?.name) return occupantInitials(o.name)
  return props.gmMode ? '🏛' : '🎭'
})

function onSelfDragStart(e) {
  const idx = occupants.value.findIndex(o => o.id === props.entityId)
  if (idx !== -1) { onOccupantDragStart(e, occupants.value[idx], idx); return }
  onGmDotDragStart(e)  // GM free-roam: local, non-persisted dot
}

function onSelfClick() {
  if (occSuppressClick) { occSuppressClick = false; return }
  if (!props.entityId) return  // GM free-roam dot — nothing to inspect
  emit('inspectEntity', props.entityId)
}

// ── Scene canvas tracking ────────────────────────────────────────────
// The whole scene renders relative to the viewer's CONTAINER (the location
// band on mobile, the window on desktop) so dots and background share one
// coherent coordinate space when the band shrinks — no squeezing, no drift.
// The camera is SIZE-DRIVEN, a pure function of the band height: full map
// down to CAMERA_START, then a continuous zoom toward the self character
// (centered at CAMERA_FULL). The band's own focus animation drives the zoom
// — no recalculation jump, no discrete camera flag.
const sceneW = ref(typeof window !== 'undefined' ? window.innerWidth : 1000)
const sceneH = ref(typeof window !== 'undefined' ? window.innerHeight : 800)
let sceneRO = null
onMounted(() => {
  sceneRO = new ResizeObserver((entries) => {
    const r = entries[0]?.contentRect
    if (r && r.width > 0) { sceneW.value = r.width; sceneH.value = r.height }
  })
  if (viewerEl.value) sceneRO.observe(viewerEl.value)
})
onUnmounted(() => sceneRO?.disconnect())

// ── Single camera source ──────────────────────────────────────────────────
// One object derives everything: container dims, scene size (cover + overscan,
// TEASER_ZOOM in teaser-camera mode), and the pan that anchors the self
// character (center-anchored in teaser mode). All pan/size derivations and the
// image↔viewport conversions read from this — nothing recomputes independently,
// so the math can't drift.
const sceneCamera = computed(() => {
  const cw = sceneW.value
  const ch = sceneH.value
  // Size-driven camera: 0 at CAMERA_START (full map) → 1 at CAMERA_FULL.
  const refH = typeof window !== 'undefined' ? window.innerHeight : 800
  const h0 = refH * CAMERA_START
  const h1 = refH * CAMERA_FULL
  const p = ch >= h0 ? 0 : ch <= h1 ? 1 : (h0 - ch) / (h0 - h1)
  const zoom = 1 + (TEASER_ZOOM - 1) * p
  const { x: mx, y: my } = selfPos.value
  // The character glides from its natural map position to the center.
  const anchor = { x: mx + (50 - mx) * p, y: my + (50 - my) * p }
  const { w, h } = imageAspect.value
    ? coverOverscan(cw * zoom, ch * zoom, imageAspect.value)
    : { w: cw * zoom * 1.8, h: ch * zoom * 1.8 }  // unknown aspect: 180% fallback
  // Pan shift in px (positive = scene shifted left/up) so the self character
  // sits at the anchor point.
  return {
    cw, ch, zoom, w, h,
    panX: (mx / 100) * w - (anchor.x / 100) * cw,
    panY: (my / 100) * h - (anchor.y / 100) * ch,
  }
})

// Convert image-relative position to viewport position based on the camera
function toViewportPos(imgX, imgY) {
  const c = sceneCamera.value
  const viewX = (((imgX / 100) * c.w - c.panX) / c.cw) * 100
  const viewY = (((imgY / 100) * c.h - c.panY) / c.ch) * 100
  return { left: viewX.toFixed(1) + '%', top: viewY.toFixed(1) + '%' }
}


// Inverse parallax for navdot "hole" images: the destination scene pans
// opposite to the current scene's shift, like looking through a hole in the
// world at a distant scene. Returns the offset in destination-image % units.
const navDotPerspective = computed(() => {
  const c = sceneCamera.value
  const out = {}
  for (const nd of navDots.value) {
    const destAspect = destNavCache.value[nd.target.id]?.destAspect
    if (!destAspect) continue
    const dest = coverOverscan(c.cw, c.ch, destAspect)
    const overX = dest.w - c.cw
    const overY = dest.h - c.ch
    out[nd.key] = {
      panX: overX > 0 ? -(c.panX / overX) * 100 * INVERSE_PAN_STRENGTH : 0,
      panY: overY > 0 ? -(c.panY / overY) * 100 * INVERSE_PAN_STRENGTH : 0,
    }
  }
  return out
})

// "Hole" preview style for zone/nav dots: the destination image rendered as a
// screen-fixed window. The px transform (a) cancels the scene layer's pan so
// the content stays anchored to the viewport, (b) aligns the destination's
// arrival point, and (c) adds the inverse-parallax shift from navDotPerspective.
function holeStyleFor(imgX, imgY, arriveX, arriveY, destAspect, panX, panY) {
  if (arriveX == null || arriveY == null || !destAspect) return null
  const c = sceneCamera.value
  const { w, h } = coverOverscan(c.cw, c.ch, destAspect)
  const overX = w - c.cw
  const overY = h - c.ch
  // Clamp the alignment point to [0, 100]: beyond the image there is nothing
  // to show, so the parallax shift is limited by the remaining image space in
  // each direction (asymmetric when the arrival point sits near an edge).
  const alignX = Math.min(100, Math.max(0, arriveX + (panX || 0)))
  const alignY = Math.min(100, Math.max(0, arriveY + (panY || 0)))
  const x = (-(alignX / 100) * overX) + c.panX - ((imgX / 100) * c.w)
  const y = (-(alignY / 100) * overY) + c.panY - ((imgY / 100) * c.h)
  return {
    width: `${w}px`,
    height: `${h}px`,
    transform: `translate3d(${x}px, ${y}px, 0)`,
  }
}

function zoneHoleStyle(z) {
  const c = zoneCache(z)
  return c ? holeStyleFor(z.x, z.y, c.arriveX, c.arriveY, c.destAspect, 0, 0) : null
}

function navHoleStyle(nd) {
  const c = destNavCache.value[nd.target.id]
  const p = navDotPerspective.value[nd.key]
  if (!c) return null
  return holeStyleFor(nd.x, nd.y, c.arriveX, c.arriveY, c.destAspect, p?.panX || 0, p?.panY || 0)
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
  const c = sceneCamera.value
  return {
    x: (((viewX / 100) * c.cw + c.panX) / c.w) * 100,
    y: (((viewY / 100) * c.ch + c.panY) / c.h) * 100,
  }
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
      // PUT replaces the whole zone list: send every field back, or a drag
      // silently strips the zone→child link (`location_id`) and its image.
      body: JSON.stringify(zones.value.map(z => ({
        name: z.name, x: z.x, y: z.y,
        background_image: z.background_image ?? null,
        location_id: z.location_id ?? null,
      }))),
    })
  } catch { /* silent */ }
}

onUnmounted(() => {
  document.removeEventListener('mousemove', onDragMove)
  document.removeEventListener('mouseup', onDragEnd)
  document.removeEventListener('touchmove', onDragMove)
  document.removeEventListener('touchend', onDragEnd)
  document.removeEventListener('mousemove', onGmDotDragMove)
  document.removeEventListener('mouseup', onGmDotDragEnd)
  document.removeEventListener('touchmove', onGmDotDragMove)
  document.removeEventListener('touchend', onGmDotDragEnd)
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
      image: nav.value.parent.navdot_image || nav.value.parent.background_image || null,
      x: pos.x, y: pos.y,
      target: { id: nav.value.parent._key, universe: nav.value.parent.current_universe },
    })
  }
  for (const [i, t] of (nav.value.transversal || []).entries()) {
    const key = i === 0 ? 'portal' : `portal:${i}`
    const pos = navDotPositions.value[key] || { x: 90, y: 50 + i * 10 }
    dots.push({
      key, type: 'portal', name: `${t.name} · ${t.transversal_type || 'inapposite'}`,
      image: t.navdot_image || t.background_image || null,
      x: pos.x, y: pos.y,
      transversal_type: t.transversal_type || 'inapposite',
      target: { id: t._key, universe: t.current_universe },
    })
  }
  return dots
})

const imageAspect = ref(null)  // width/height ratio of current image, or null if unknown

// Scene layer: background + world dots, sized to the overscanned scene and
// moved by a single translate3d. Panning is one compositor operation; the dots
// inside never move individually (no per-dot layout/paint during pan).
const sceneLayerStyle = computed(() => {
  const c = sceneCamera.value
  return {
    width: `${c.w}px`,
    height: `${c.h}px`,
    transform: `translate3d(${-c.panX}px, ${-c.panY}px, 0)`,
  }
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

function canDragOccupant(occupant) {
  if (props.editZones) return true                // GM can drag anyone
  if (occupant.id === props.entityId) return true  // player can drag self
  if (props.gmMode && (occupant.type === 'gmc' || occupant.type === 'asset')) return true  // GM moves world occupants directly
  return false
}

function occupantInitials(name) {
  return name.split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase()
}

const poolDiceFor = (eid) => {
  const pool = props.remotePools[eid]
  const results = props.remoteResults[eid]
  // Rolled results win whenever we have them — the ring shows the numbers that
  // landed, in every phase after the roll (not just while picking).
  if (results?.rolls?.length) return results.rolls
  if (!pool) return []
  // `adding` and `rolling` both carry the pool's dice; during a roll the ring
  // tumbles them (see PoolDiceRing).
  if (pool.phase === 'adding' || pool.phase === 'rolling') {
    return (pool.dice || []).map(d => (typeof d === 'string' ? d : d.die || d))
  }
  return []
}
const poolPhaseFor = (eid) => props.remotePools[eid]?.phase || 'adding'

// ── Occupant drag ──────────────────────────────────

const occDragging = ref(null)  // { index }
let occDragMoved = false       // pointer moved past the tap threshold
let draggingEmitted = false    // emitted 'dragging' so the HUD hides during a real drag
let occSuppressClick = false   // suppress the synthesized click after a real drag
// Arm that suppression for one click only. It disarms on the next pointerdown,
// so when the drag's synthesized click never fires (mouseup landed off the dot)
// the flag cannot linger and swallow a later, unrelated click.
function armClickSuppression() {
  occSuppressClick = true
  document.addEventListener(
    'pointerdown', () => { occSuppressClick = false },
    { capture: true, once: true },
  )
}
let dragTarget = null  // non-reactive: nearest travel target during self-drag
// Coalesce high-frequency pointermove into one update per animation frame: a
// high-polling mouse otherwise triggers a full re-render + layout on every
// event and starves requestAnimationFrame (measured ~6 fps during drags).
let occDragRafId = null
let occDragPending = null  // { clientX, clientY } — latest unapplied pointer position
const expandLevels = ref({})  // reactive: 'zone-<name>'/'nav-<key>' → 0..1 proximity level
const armedDot = ref('')   // reactive: travel is armed on this dot (drop → travel)

// Drop-to-travel radius in image-% units: the expanded bubble's on-screen
// radius plus the self dot's radius, converted through the current image scale.
// Travel only triggers when the character is dropped on the bubble.
function travelProximity() {
  const c = sceneCamera.value
  const bubbleW = Math.min(260, Math.max(120, c.cw * 0.14))
  const selfW = Math.min(88, Math.max(60, c.cw * 0.055))
  const radiusPx = bubbleW / 2 + selfW / 2
  const pxPerPct = c.w / 100  // image-% ↔ px on the X axis
  return (radiusPx / pxPerPct) * TRAVEL_PROXIMITY_FACTOR
}

function onOccupantDragStart(e, occupant, index) {
  if (!canDragOccupant(occupant)) return
  occDragMoved = false
  // The template loops over the filtered (non-self) occupants, so the loop
  // index does not match occupants.value — resolve the real index by id.
  const realIndex = occupants.value.findIndex(o => o.id === occupant.id)
  if (realIndex === -1) return
  const el = viewerEl.value
  if (!el) return
  const clientX = e.touches ? e.touches[0].clientX : e.clientX
  const clientY = e.touches ? e.touches[0].clientY : e.clientY

  // Drag origin must be the dot's rendered viewport position at grab time:
  // self renders 1:1 at its map %, other occupants render through the
  // parallax conversion — otherwise the dot jumps on the first move.
  const imgX = occupant.map_x ?? occupantX(index, occupant)
  const imgY = occupant.map_y ?? occupantY(index, occupant)
  let origX, origY
  if (occupant.id === props.entityId) {
    origX = imgX
    origY = imgY
  } else {
    const vp = toViewportPos(imgX, imgY)
    origX = parseFloat(vp.left)
    origY = parseFloat(vp.top)
    if (Number.isNaN(origX)) origX = 50
    if (Number.isNaN(origY)) origY = 50
  }

  // Store initial position so we can compute delta
  occDragging.value = {
    index: realIndex,
    startX: clientX,
    startY: clientY,
    origX,
    origY,
  }
  document.addEventListener('mousemove', onOccDragMove)
  document.addEventListener('mouseup', onOccDragEnd)
  document.addEventListener('touchmove', onOccDragMove, { passive: false })
  document.addEventListener('touchend', onOccDragEnd)
}

function onOccDragMove(e) {
  if (!occDragging.value) return
  const clientX = e.touches ? e.touches[0].clientX : e.clientX
  const clientY = e.touches ? e.touches[0].clientY : e.clientY
  const start = occDragging.value
  if (!occDragMoved) {
    if (Math.hypot(clientX - start.startX, clientY - start.startY) < 6) return
    occDragMoved = true
    const isSelf = occupants.value[start.index]?.id === props.entityId
    startFrameProfile(isSelf ? 'self' : 'occupant')
    if (!draggingEmitted) { draggingEmitted = true; emit('dragging', true) }
  }
  e.preventDefault()
  notePointerEvent()
  occDragPending = { clientX, clientY }
  if (occDragRafId == null) occDragRafId = requestAnimationFrame(applyOccDragFrame)
}

// Apply the latest buffered pointer position once per frame (not per event),
// so a high-polling mouse can't saturate the main thread with re-renders.
async function applyOccDragFrame() {
  occDragRafId = null
  if (!occDragging.value || !occDragPending) return
  const t0 = performance.now()
  const { clientX, clientY } = occDragPending
  occDragPending = null
  const start = occDragging.value
  const c = sceneCamera.value
  const dx = ((clientX - start.startX) / c.cw) * 100
  const dy = ((clientY - start.startY) / c.ch) * 100
  const occ = occupants.value[start.index]
  if (occ) {
    const viewX = occDragging.value.origX + dx
    const viewY = occDragging.value.origY + dy
    const img = toImagePos(viewX, viewY)
    occ.map_x = Math.max(2, Math.min(98, Math.round(img.x)))
    occ.map_y = Math.max(2, Math.min(98, Math.round(img.y)))
  }

  if (occ && occ.id === props.entityId) updateTravelTargets(occ.map_x, occ.map_y)

  await nextTick() // wait for Vue to flush the reactive re-render
  noteFrameWork(performance.now() - t0)
}

// Proximity feedback for a dot at (px, py) in image space: EXPAND_PROXIMITY opens
// every nearby bubble (size coupled to distance, quick near the dot);
// travelProximity() arms travel on the single nearest bubble.
function updateTravelTargets(px, py) {
  const travelDist = travelProximity()
  const levels = {}
  let travelNearest = null, travelNearestDist = travelDist
  const scan = (type, id, tx, ty) => {
    const dist = Math.sqrt((tx - px) ** 2 + (ty - py) ** 2)
    if (dist < travelNearestDist) { travelNearest = { type, id }; travelNearestDist = dist }
    if (dist < EXPAND_PROXIMITY) {
      const t = dist / EXPAND_PROXIMITY
      levels[`${type}-${id}`] = 1 - t * t  // quadratic: expands fast
    }
  }
  for (const z of zones.value) scan('zone', zoneId(z), z.x, z.y)
  for (const nd of navDots.value) scan('nav', nd.key, nd.x, nd.y)
  dragTarget = travelNearest
  expandLevels.value = levels
  armedDot.value = (!props.editZones && travelNearest) ? `${travelNearest.type}-${travelNearest.id}` : ''
}

// Drop-on-target travel, shared by the occupant self-drag and the GM dot drag.
function travelToTarget(t) {
  if (!t) return false
  if (t.type === 'zone') {
    const zone = zones.value.find(z => zoneId(z) === t.id)
    if (!zone) return false
    const child = childForZone(zone)
    if (child) {
      travelWithAnimation(zone, child)
    } else if (props.entityId && zone.location_id) {
      moveTo(zone.location_id, '')
    } else {
      // No link and nothing to fall back to (e.g. an unlinked zone): no-op
      // rather than a moveTo('') request.
      return false
    }
    return true
  }
  if (t.type === 'nav') {
    const nd = navDots.value.find(d => d.key === t.id)
    if (!nd) return false
    activeElement.value = { type: 'nav', key: nd.key }
    // Destination display name, for the view-only move's location label
    const destName = nd.type === 'parent'
      ? nav.value.parent?.name
      : (nav.value.transversal || []).find(x => x._key === nd.target.id)?.name
    const fakeZone = { x: nd.x, y: nd.y }
    const fakeChild = { _key: nd.target.id, name: destName, current_universe: nd.target.universe, transversal_type: nd.type === 'portal' ? nd.transversal_type : null }
    travelWithAnimation(fakeZone, fakeChild, nd.image)
    return true
  }
  return false
}

async function onOccDragEnd() {
  document.removeEventListener('mousemove', onOccDragMove)
  document.removeEventListener('mouseup', onOccDragEnd)
  document.removeEventListener('touchmove', onOccDragMove)
  document.removeEventListener('touchend', onOccDragEnd)
  expandLevels.value = {}
  armedDot.value = ''
  if (draggingEmitted) { draggingEmitted = false; emit('dragging', false) }
  if (!occDragging.value) return
  const occ = occupants.value[occDragging.value.index]
  const wasMoved = occDragMoved
  if (wasMoved) stopFrameProfile()
  if (occDragRafId != null) { cancelAnimationFrame(occDragRafId); occDragRafId = null }
  occDragPending = null
  occDragging.value = null
  occDragMoved = false
  if (!occ) return
  if (!wasMoved) return  // tap — the synthesized click handles inspect/pop

  armClickSuppression()

  // If the player dropped near a target, travel there
  if (occ.id === props.entityId && dragTarget && !props.editZones) {
    const t = dragTarget
    dragTarget = null
    if (travelToTarget(t)) return
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

// ── GM free-roam dot drag ──────────────────────────
// With no perspective entity (entityId == null) there is nothing to persist, so
// the GM dot moves locally and the camera pans with it. Coalesced to one update
// per frame, like the occupant drag.

let gmDrag = null          // { startX, startY, origX, origY } — client px + image %
let gmDragMoved = false
let gmDragRafId = null
let gmDragPending = null

function onGmDotDragStart(e) {
  if (!viewerEl.value) return
  const clientX = e.touches ? e.touches[0].clientX : e.clientX
  const clientY = e.touches ? e.touches[0].clientY : e.clientY
  const p = selfPos.value
  gmDrag = { startX: clientX, startY: clientY, origX: p.x, origY: p.y }
  gmDragMoved = false
  document.addEventListener('mousemove', onGmDotDragMove)
  document.addEventListener('mouseup', onGmDotDragEnd)
  document.addEventListener('touchmove', onGmDotDragMove, { passive: false })
  document.addEventListener('touchend', onGmDotDragEnd)
}

function onGmDotDragMove(e) {
  if (!gmDrag) return
  const clientX = e.touches ? e.touches[0].clientX : e.clientX
  const clientY = e.touches ? e.touches[0].clientY : e.clientY
  if (!gmDragMoved) {
    if (Math.hypot(clientX - gmDrag.startX, clientY - gmDrag.startY) < 6) return
    gmDragMoved = true
    if (!draggingEmitted) { draggingEmitted = true; emit('dragging', true) }
  }
  e.preventDefault()
  gmDragPending = { clientX, clientY }
  if (gmDragRafId == null) gmDragRafId = requestAnimationFrame(applyGmDotDragFrame)
}

function applyGmDotDragFrame() {
  gmDragRafId = null
  if (!gmDrag || !gmDragPending) return
  const { clientX, clientY } = gmDragPending
  gmDragPending = null
  const c = sceneCamera.value
  // The self dot is the camera anchor, so its image % and viewport % coincide —
  // add the pointer delta in viewport % and convert back to image space.
  const viewX = gmDrag.origX + ((clientX - gmDrag.startX) / c.cw) * 100
  const viewY = gmDrag.origY + ((clientY - gmDrag.startY) / c.ch) * 100
  const img = toImagePos(viewX, viewY)
  setGmDotPos(
    Math.max(2, Math.min(98, Math.round(img.x))),
    Math.max(2, Math.min(98, Math.round(img.y)))
  )
  updateTravelTargets(gmSelfPos.value.x, gmSelfPos.value.y)
}

function onGmDotDragEnd() {
  document.removeEventListener('mousemove', onGmDotDragMove)
  document.removeEventListener('mouseup', onGmDotDragEnd)
  document.removeEventListener('touchmove', onGmDotDragMove)
  document.removeEventListener('touchend', onGmDotDragEnd)
  if (gmDragRafId != null) { cancelAnimationFrame(gmDragRafId); gmDragRafId = null }
  gmDragPending = null
  const wasMoved = gmDragMoved
  gmDrag = null
  gmDragMoved = false
  expandLevels.value = {}
  armedDot.value = ''
  if (draggingEmitted) { draggingEmitted = false; emit('dragging', false) }
  const t = dragTarget
  dragTarget = null
  if (!wasMoved) return
  armClickSuppression()  // a drag must not fire the click handler
  persistGmDots()
  // Dropped on a location → travel the view there
  if (t && !props.editZones) travelToTarget(t)
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
    perfMark('location-nav-loaded', { locationId: props.locationId, occupants: occupants.value.length })

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

async function relocate(locationId, universe, consciousness, effects, name) {
  // GM free-roam (no perspective entity): there is nothing to move — travel
  // just switches the viewed location. Nothing is persisted.
  if (!props.entityId) {
    emit('moved', { location: name || locationId, location_id: locationId, universe })
    return
  }
  if (effects && effects.length) {
    try {
      const r = await fetch(`/api/v1/locations/${props.locationId}/portal/${locationId}/fire`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ entity_id: props.entityId })
      })
      const data = await r.json()
      emit('moved', data)
    } catch { /* silent */ }
    return
  }
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
  // Identity is the stored link, never the label: names are editable, and a
  // rename must not orphan or mis-route a zone. Zones get their `location_id`
  // when the `super` edge is created (repository `_ensure_child_zone`).
  if (!zone.location_id) return null
  return (nav.value.children || []).find(c => c._key === zone.location_id) || null
}

// Identity for a zone: the linked child's ID, else its position in the current
// list (stable per fetch). Used for dot keys and proximity state — a rename
// must not re-key, re-arm, or re-target anything.
function zoneId(z, i) {
  if (z.location_id) return z.location_id
  return `idx-${i === undefined ? zones.value.indexOf(z) : i}`
}

// Is a client actively driving this entity? (The `controlled` dot state, and the
// input to the pool dice ring radius.) Props are NOT auto-unwrapped in script
// scope — this must go through `props`.
function isControlled(id) {
  return !!id && props.controlledEntityIds.includes(id)
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
  // Occupants always inspect — no toggle. The sheet itself handles
  // open/switch/close, so a second click must reach it too.
  if (type === 'occupant') {
    if (item.id === props.entityId) return  // self is filtered out anyway
    emit('inspectEntity', item.id)
    return
  }
  // Zones / nav dots: pop or dismiss the expanded bubble.
  if (activeElement.value?.type === type) {
    const same = type === 'zone'
      ? activeElement.value.id === zoneId(item)
      : activeElement.value.key === item.key
    if (same) {
      activeElement.value = null
      return
    }
  }
  activeElement.value = type === 'zone' ? { type: 'zone', id: zoneId(item) }
    : { type: 'nav', key: item.key }
}

async function travelWithAnimation(zone, child, imageUrl = null) {
  const img = imageUrl || childImage(zone)
  const sourceId = props.locationId  // remember where we came from
  if (!img) {
    relocate(child._key, child.current_universe, child.transversal_type === 'consciousness', child.effects, child.name)
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
    // Find which dot on destination links back to source (by child ID)
    for (const z of (destLoc?.zones || [])) {
      if (z.location_id === sourceId) { arriveX = z.x; arriveY = z.y; break }
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

  relocate(child._key, child.current_universe, child.transversal_type === 'consciousness', child.effects, child.name)

  setTimeout(async () => {
    await fetchNav()

    // Reset overlay to new location's value (may be null)
    optimisticOverlay.value = props.overlay

    // Lock position, switch background, and remove portal — all in one frame
    const so = occupants.value.find(o => o.id === props.entityId)
    if (so) { so.map_x = arriveX; so.map_y = arriveY }
    else { setGmDotPos(arriveX, arriveY); persistGmDots() }  // free-roam dot lands here
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
    if (z.location_id === sourceId) { nx = z.x; ny = z.y; break }
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
        // Parent: find which zone on parent links back to us (by child ID)
        for (const z of (loc?.zones || [])) {
          if (z.location_id === currentId) { arriveX = z.x; arriveY = z.y; break }
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

      // Get destination image aspect. Videos must be probed through metadata:
      // an <img> cannot decode .webm, which silently left animated destinations
      // (e.g. Cloud-Soaked Bazaar) without a hole preview.
      const destAspect = await probeAspect(loc?.background_image)

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
  overflow: hidden;
  background-color: #0a0a0f;
  background-image: radial-gradient(ellipse at 40% 40%, #1a1a2e 0%, #0a0a0f 70%);
  z-index: 0;
}

/* Scene layer: the overscanned background + world dots, sized and panned by
   sceneLayerStyle (one transform). pointer-events: none so background clicks
   fall through to the viewer; the dots re-enable events with auto. */
.scene-layer {
  position: absolute;
  top: 0; left: 0;
  z-index: 0;
  pointer-events: none;
  will-change: transform;
}

.scene-media {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
  pointer-events: none;
}

.loc-label {
  position: absolute;
  top: env(safe-area-inset-top, 16px);
  left: 16px;
  font-size: 20px; font-weight: 600;
  color: var(--map-text);
  text-shadow: 0 2px 8px rgba(0,0,0,0.8);
  z-index: 2;
  pointer-events: none;
}

.uni-label {
  position: absolute;
  top: calc(env(safe-area-inset-top, 16px) + 24px);
  left: 16px;
  font-size: 12px; color: var(--map-text-dim);
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
  border-color: var(--map-accent);
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
  /* Centered via negative margins; dots live inside the transformed scene layer */
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
  font-size: 11px; font-weight: 600; color: var(--map-text);
  text-align: center; padding: 4px; line-height: 1.2;
}
.dot-initials {
  font-size: 18px; font-weight: 800; color: #fff;
}

/* Draggable state — show as expanded bubbles */
.map-dot.draggable {
  cursor: grab; border: 2px dashed var(--map-accent);
  animation: dot-pulse 2s ease-in-out infinite;
}
/* Zones full-size when editing */
.zone-dot.draggable {
  width: 240px !important; height: 240px !important;
  margin-left: -120px; margin-top: -120px;
  background: rgba(10,10,20,0.85);
  z-index: 10;
  overflow: hidden;
}
/* Nav dots full-size when editing */
.nav-dot.draggable {
  width: 240px !important; height: 240px !important;
  margin-left: -120px; margin-top: -120px;
  background: rgba(10,10,20,0.85);
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
  0%, 100% { border-color: var(--map-accent); }
  50% { border-color: rgba(64,136,212,0.3); }
}



/* ── Transitions ─────────────────────────────────── */

.fade-in {
  animation: fadeIn 0.4s ease both;
}
/* Self character pops in immediately on arrival */
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
