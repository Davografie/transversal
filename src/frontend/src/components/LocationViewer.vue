<template>
  <div ref="viewerEl" class="location-viewer" :class="{ 'portal-active': travelAnim.active }" :style="{ '--controlled-scale': CONTROLLED_SCALE }" @click="onBgClick">
    <!-- Scene layer: background + world dots, all panned by ONE transform.
         Dots sit at image-space coordinates inside the layer, so panning
         never moves them individually (compositor-only, no per-dot paint). -->
    <div class="scene-layer" :style="sceneLayerStyle">
      <video v-if="currentImage && isVideoBg" ref="videoBgEl" :src="currentImage" class="scene-media" autoplay loop muted playsinline />
      <img v-else-if="currentImage" ref="bgImgEl" :src="currentImage" class="scene-media" alt="" />

      <!-- Placed trait chips (B92): scene elements at their stored image-space x/y,
           so they pan and zoom with the map exactly like the dots. Unplaced ones
           stay in the stack beside the labels. A placed chip rests as its marker and
           opens by proximity, pointer or tap — the stack below is always open. -->
      <TraitChip
        v-for="t in placedTraits"
        :key="'tc-' + t.id"
        v-show="showElements"
        :trait="t"
        :x="traitPositions[t.id].x"
        :y="traitPositions[t.id].y"
        :draggable="editZones"
        :expanded="traitChipExpanded(t)"
        @mouseenter="hoveredTraitId = t.id"
        @mouseleave="hoveredTraitId = ''"
        @mousedown="editZones && onTraitChipDragStart($event, t)"
        @touchstart="editZones && onTraitChipDragStart($event, t)"
        @click="!editZones && onTraitChipClick(t)"
      />

      <!-- Zone dots -->
      <template v-for="(z, i) in zones" :key="'z-' + zoneId(z, i)">
      <MapDot
        v-if="showElements"
        type="zone"
        :x="z.x" :y="z.y"
        :image="childImage(z)"
        :label="zoneLabel(z)"
        :show-label="editZones"
        :expanded="editZones || (activeElement?.type === 'zone' && activeElement?.id === zoneId(z, i)) || (expandLevels['zone-' + zoneId(z, i)] || 0) > 0"
        :draggable="editZones"
        :title="zoneLabel(z)"
        :hole-style="zoneHoleStyle(z)"
        :expand-level="expandLevels['zone-' + zoneId(z, i)] || 0"
        :class="{ armed: armedDot === 'zone-' + zoneId(z, i), guided: guidedDot === 'zone-' + zoneId(z, i), dimmed: !!armedDot && armedDot !== 'zone-' + zoneId(z, i) }"
        @click="onDotClick('zone', z)"
        @overlay-click="onExpandedClick('zone', z)"
        @drag-start="(e) => onZoneDragStart(e, z, i)"
      />
      </template>

      <!-- Occupant dots (non-self only, always expanded). **Placed occupants only**
           (the human, 2026-09-26): someone with no stored position is not drawn at
           all, exactly as an unplaced trait chip is not — they live in the arrange-mode
           drawer until the GM places them. Presence is not lost by hiding them: the
           peer rail still lists who is at the location. -->
      <template v-for="o in placedOccupants" :key="'o-' + o.id">
      <MapDot
        v-if="!travelAnim.active && showElements"
        type="occupant"
        :variant="o.type"
        :class="{ 'dot-draft': o.unpublished, viewed: o.id === viewingEntityId, controlled: isControlled(o.id), growing: growingIds.includes(o.id), settling: settlingIds.includes(o.id) }"
        :x="o.map_x" :y="o.map_y"
        :image="o.image"
        :image-transparent="!!o.image_transparent"
        :initials="occupantInitials(o.name)"
        :expanded="true"
        :draggable="canDragOccupant(o)"
        :dragging="dragDotKey === o.id"
        :lerping="lerpActive && dragDotKey !== o.id"
        :title="canDragOccupant(o) ? 'Drag to reposition' : (o.unpublished ? o.name + ' (draft)' : o.name)"
        @click="onDotClick('occupant', o)"
        @overlay-click="onExpandedClick('occupant', o)"
        @drag-start="(e) => onOccupantDragStart(e, o)"
      />
      <!-- Pool dice ring around occupant dot -->
      <PoolDiceRing
        v-if="!travelAnim.active && showElements && (poolDiceFor(o.id).length > 0 || (poolPhaseFor(o.id) !== 'adding' && remoteResults[o.id]))"
        :dice="poolDiceFor(o.id)"
        :phase="poolPhaseFor(o.id)"
        :cx="o.map_x"
        :cy="o.map_y"
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
        :show-label="editZones"
        :expanded="editZones || (activeElement?.type === 'nav' && activeElement?.key === nd.key) || (expandLevels['nav-' + nd.key] || 0) > 0"
        :draggable="editZones"
        :title="nd.name"
        :hole-style="navHoleStyle(nd)"
        :expand-level="expandLevels['nav-' + nd.key] || 0"
        :class="{ armed: armedDot === 'nav-' + nd.key, guided: guidedDot === 'nav-' + nd.key, dimmed: !!armedDot && armedDot !== 'nav-' + nd.key }"
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

    <!-- Location traits (B92) — the location's own, plus the challenge pools it
         inherits from its ancestors, TRAITS tab only (the server reports each
         trait's tab; profile traits like the imagen/appearance settings stay off
         the map). Visible to EVERYONE, unlike the two labels above: the server has
         already resolved what this viewer may see, so a hidden owner simply is not
         in the list. A chip is a scene element once it has a stored position
         ([[Location Trait Chips]]); until then it belongs to this stack.

         The stack is **arrange-mode only** (the human, 2026-09-25): unplaced traits are
         hidden from the map by default, because a room's whole trait list down the side
         of the screen was crowding the map — on a phone the stack alone ran 526px of an
         844px screen. It appears while the GM is placing things, which is the only time
         it is needed: a chip dragged out of it becomes a scene element and never
         returns. -->
    <div
      v-if="showElements && editZones && railOpen && unplacedCount"
      ref="railEl"
      class="loc-traits fade-in"
      :class="{ 'has-switcher': gmMode }"
    >
      <TraitChip
        v-for="t in unplacedTraits"
        :key="t.id"
        :trait="t"
        :draggable="editZones"
        :expanded="true"
        @mousedown="editZones && onTraitChipDragStart($event, t)"
        @touchstart="editZones && onTraitChipDragStart($event, t)"
        @click="!editZones && onTraitChipClick(t)"
      />
      <!-- Unplaced OCCUPANTS, in the same drawer (the human, 2026-09-26). A person
           with no stored position is sitting on a computed default, so the GM has no
           way to tell who still needs placing; this is that list. Unlike a chip they
           are not removed from the map — hiding a person would misreport the room —
           so dragging one out *places* them and the entry leaves the drawer. -->
      <div
        v-for="o in unplacedOccupants"
        :key="'uo-' + o.id"
        class="occ-drawer-chip"
        :title="`${o.name} — not placed on this map yet. Drag onto the map to place.`"
        @mousedown="editZones && onOccupantDrawerDragStart($event, o)"
        @touchstart="editZones && onOccupantDrawerDragStart($event, o)"
      >
        <video
          v-if="o.image && isVideoUrl(o.image)"
          :src="o.image" class="occ-drawer-img" autoplay loop muted playsinline
        />
        <img
          v-else-if="o.image" :src="o.image" class="occ-drawer-img" alt="" draggable="false"
        />
        <span v-else class="occ-drawer-initials">{{ occupantInitials(o.name) }}</span>
        <span class="occ-drawer-name">{{ o.name }}</span>
      </div>
    </div>

    <!-- ONE control in two states (the human, 2026-09-26). Idle in arrange mode it is the
         rail's handle: the count of what is unplaced, tap to open or close the rail.
         While an occupant or a trait chip is dragged it becomes the unplace target — the
         same gesture in reverse: drag out of the rail to place, drag onto this to unplace.
         GM-only, and `pointer-events: none` while a drag runs, because the drag owns the
         pointer through document listeners and the hit test is done against this rect. -->
    <div
      v-if="showElements && gmMode && (unplaceArmed || (editZones && unplacedCount))"
      ref="unplaceEl"
      class="top-control"
      :class="{ 'unplace-armed': unplaceArmed, armed: unplaceHover, open: railOpen && !unplaceArmed }"
      :title="unplaceArmed ? 'Drop here to unplace' : `${unplacedCount} unplaced`"
      @click="!unplaceArmed && (railOpen = !railOpen)"
    >{{ unplaceArmed ? '( x )' : `unplaced · ${unplacedCount}` }}</div>

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
      :dragging="dragDotKey === 'self'"
      title="Drag to explore"
      @click="onSelfClick()"
      @overlay-click="onSelfClick()"
      @drag-start="(e) => onSelfDragStart(e)"
    />
    <PoolDiceRing
      v-if="!travelAnim.active && showElements && (poolDiceFor(entityId).length > 0 || (poolPhaseFor(entityId) !== 'adding' && remoteResults[entityId]))"
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
      :scene="travelScene"
    />

  </div>
</template>

<script setup>
import { ref, computed, watch, watchEffect, onMounted, onUnmounted, nextTick } from 'vue'
import SceneEffectsLayer from './location/SceneEffectsLayer.vue'
import ArrivalRings from './location/ArrivalRings.vue'
import TravelOverlay from './location/TravelOverlay.vue'
import MapDot from './MapDot.vue'
import TraitChip from './location/TraitChip.vue'
import { usePercentDrag } from '../composables/usePercentDrag.js'
import { useTraitPlay } from '../composables/useTraitPlay.js'
import { normalizeLocationTrait } from '../utils/locationTrait.js'
import { useApi } from '../composables/useApi.js'
import PoolDiceRing from './PoolDiceRing.vue'
import { useTransversalLinks } from '@/composables/useTransversalLinks.js'
import { isVideoUrl, coverOverscan, probeAspect, preloadMedia } from '@/composables/media.js'
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
// How much larger than "fit" the location itself renders. Chips, dots and the
// background all live in the scene layer, so this is the one knob that spaces them
// out: everything positioned in image-% separates in proportion, and the cost is that
// less of the map is in view at once.
//
// It compensates for the viewer's WIDTH, because that is what actually crowds a map.
// A chip is a fixed number of pixels, so the narrower the viewer, the smaller the share
// of the scene those pixels cover: on a 390px phone a location's chips landed 44px
// apart where the same location gave 86px in the docked desktop view. Scaling by the
// width puts a comparable distance between them on both, and leaves the wide layout —
// which is not the crowded one — exactly as it was.
//
// ⚠ This is bounded by the BACKGROUND ART, not by taste. The `background` role serves
// the loop if the picture has one, else the `XLarge` tier (`ROLE_RENDER`,
// `services/media_utils.py`) — cap 2048 on the long side, and a tier never upscales, so
// for the common master (832×1216) XLarge IS the master. The `_Large` 478×700 variant is
// no longer what the map draws ([[B207]]). Measured live 2026-09-26: 395 location
// background images, long sides 984→2048 — 350 at 1216, 23 at 2048, 17 at 1024. A phone
// draws the scene at ~2.4k×3.5k device pixels, so at scale 1 the majority is already
// ~1.9× its native size while the largest masters are ~1.15× (near 1:1); at the cap below
// those become ~4.3× and ~2.5×. Raising these makes the map bigger and the art softer in
// proportion — see [[Location Viewer]] for the table. The cap came from the old `_Large`
// bound, so it is worth revisiting now that the served file is ~2.4× larger.
const LOCATION_SCALE_REF = 880   // viewer width that needs no extra scale (the docked view)
const LOCATION_SCALE_MAX = 2.2   // cap, so a very narrow phone still shows a map
const locationScale = (viewerW) =>
  Math.min(LOCATION_SCALE_MAX, Math.max(1, LOCATION_SCALE_REF / Math.max(viewerW, 1)))
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
  // The roller's phase, so a chip plays by the same gate the sheet does (only
  // `adding` plays; nothing is added mid-roll).
  phase: { type: String, default: 'adding' },
})

const emit = defineEmits(['moved', 'update:editZones', 'inspectEntity', 'dragging', 'addToPool', 'returnToSelf'])
const { toggleTransversalType } = useTransversalLinks()

const currentImage = ref('')
const videoBgEl = ref(null)
const bgImgEl = ref(null)   // scene-layer still, for the arrival paint gate
const isVideoBg = computed(() => isVideoUrl(currentImage.value))
const nav = ref({})
const zones = ref([])
const occupants = ref([])
// Occupants shown as navdots: players never see unpublished (GM-only draft)
// entities; the architect sees them (marked as drafts).
const occupantDots = computed(() =>
  occupants.value.filter(o => o.id !== props.entityId && (props.gmMode || !o.unpublished))
)

// An occupant with **no stored position on this map** has nowhere to be drawn, so
// they are **not drawn at all** (the human, 2026-09-26) — exactly like an unplaced
// trait chip. They are listed in the arrange-mode drawer instead, and dragging a row
// out places them. Hiding them costs no information: the peer rail still names who is
// at the location, and the drawer is where the GM finds the ones still to place.
const unplacedOccupants = computed(() =>
  occupantDots.value.filter(o => o.map_x == null || o.map_y == null)
)

// What the scene actually draws — and the reason the dot template needs no position
// fallback: everything in this list has a stored `map_x`/`map_y`.
const placedOccupants = computed(() =>
  occupantDots.value.filter(o => o.map_x != null && o.map_y != null)
)

// Unplaced occupants join the rail; see `unplacedOccupants` below for why they are
// listed rather than drawn.
const railEl = ref(null)

// The rail is **behind the top control**, not always on screen (the human, 2026-09-26):
// closed by default, opened by a tap, never remembered. That matters because an open
// rail must take pointer events to scroll, and anything taking pointer events over the
// map blocks what is behind it — acceptable for a panel you asked for, not for one that
// is always there. Closed, nothing of the rail is over the map at all.
const railOpen = ref(false)
// NOTE `.length` on BOTH: a number plus an array is string concatenation in JS, so the
// missing one on the right rendered `unplaced · 25[object Object]` (found 2026-09-26).
const unplacedCount = computed(
  () => unplacedTraits.value.length + unplacedOccupants.value.length
)

// Leaving arrange mode forgets it: "closed until asked for" has to survive the mode
// being toggled, or the next arrange session would start with the rail already open.
watch(() => props.editZones, (on) => { if (!on) railOpen.value = false })

// ── Size animation for driven dots ─────────────────────────────────────────
// One-cycle, class-triggered keyframes — deliberately NOT a transition. A
// transition only runs if (a) the element persists and (b) the property
// interpolates; on a client that receives a control change over SSE neither could
// be relied on, and the size snapped on Chrome and Firefox alike. A keyframe
// animation runs whenever the class appears — including on a freshly mounted
// element — so the growth is guaranteed.
//
// Driving it from `controlledEntityIds` (rather than the perspective) covers both
// directions on every screen: a remote take grows, a remote hand-off shrinks, and
// a local take/release does the same (the entity that loses the perspective leaves
// this set, since our own body is the set's `entityId`).
const growingIds = ref([])
const settlingIds = ref([])
let lastControlledIds = null

function animateSizeChanges(next) {
  const now = new Set(next)
  if (lastControlledIds === null) { lastControlledIds = now; return }  // first pass: no animation
  const grew = [...now].filter(id => !lastControlledIds.has(id))
  const shrank = [...lastControlledIds].filter(id => !now.has(id))
  lastControlledIds = now

  const animate = (ids, bucket) => {
    if (!ids.length) return
    bucket.value = [...bucket.value, ...ids]
    setTimeout(() => {
      bucket.value = bucket.value.filter(x => !ids.includes(x))
    }, 300)
  }
  animate(grew, growingIds)
  animate(shrank, settlingIds)
}

watch(() => props.controlledEntityIds, animateSizeChanges, { immediate: true })
const viewerEl = ref(null)
const activeElement = ref(null)  // { type: 'zone'|'occupant', name?, id? } — which dot is popped out
const travelAnim = ref({ active: false, x: 50, y: 50, image: '' })
// Holds the warm destination element for the duration of a travel: a detached
// <video> that is collected mid-wipe stops buffering, leaving the scene layer to
// start over at the handover.
let warmMedia = null
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
// map position; without one (GM free-roam, `entityId == null`) it's the roaming
// GM dot.
//
// The roaming dot is deliberately **not persisted** (B96): it marks where the GM
// is looking right now, not a remembered spot. It is placed on whatever sits
// under the centre of the view at the moment free-roam begins, so taking over
// roams from where you were already looking instead of yanking the view to a
// stored position — and opening straight into free-roam falls back to the
// location centre, which is where the camera anchors anyway.
const gmDotPositions = ref({})  // { [locationId]: { x, y } } — this session only
const gmSelfPos = computed(() => gmDotPositions.value[props.locationId] || null)
function setGmDotPos(x, y) {
  gmDotPositions.value = { ...gmDotPositions.value, [props.locationId]: { x, y } }
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
  // The roaming GM's dot has no entity to inspect — but it is still the way *back to
  // roaming*, which is what drops a foreign view (the human, 2026-09-26). Without
  // this a roaming GM who had peeked at someone had no click that let go of them.
  if (!props.entityId) { emit('returnToSelf'); return }
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
  // Folded into `zoom` rather than applied at the size below, because the destination
  // preview is sized from `c.zoom` too — a separate multiplier here would make the map
  // jump the instant a travel animation became the scene layer.
  const zoom = (1 + (TEASER_ZOOM - 1) * p) * locationScale(cw)
  const { x: mx, y: my } = selfPos.value
  // The character glides from its natural map position to the center.
  const anchor = { x: mx + (50 - mx) * p, y: my + (50 - my) * p }
  const { w, h } = imageAspect.value
    ? coverOverscan(cw * zoom, ch * zoom, imageAspect.value)
    : { w: cw * zoom * 1.8, h: ch * zoom * 1.8 }  // unknown aspect: 180% fallback
  // Pan shift in px (positive = scene shifted left/up) so the self character
  // sits at the anchor point.
  //
  // Clamped so the scene always covers the viewport. Pulling the character to
  // the anchor can ask for more pan than the image has to give — near the edge
  // of a map that slid the image off-screen and left a black band beside the
  // character, which is what the mobile teaser exposed (at p=0 the pan is
  // proportional and already in range, so this only ever bites as it zooms).
  // Better to stop following the character than to show the void behind it.
  const panX = (mx / 100) * w - (anchor.x / 100) * cw
  const panY = (my / 100) * h - (anchor.y / 100) * ch
  const clampPan = (v, max) => Math.min(Math.max(v, 0), Math.max(0, max))
  return {
    cw, ch, zoom, p, w, h,
    panX: clampPan(panX, w - cw),
    panY: clampPan(panY, h - ch),
  }
})

// ── Destination scene geometry ────────────────────────────────────────────
// The same math for the location on the other side of a travel. A travel never
// changes the container, so only the aspect and the anchored point differ — but
// a destination preview MUST be sized from here (cover + PAN_OVERSCAN + the
// teaser zoom) rather than a CSS `cover`, or it comes out a PAN_OVERSCAN short
// and visibly grows the instant it becomes the new scene layer.
// `panX`/`panY` are the offsets that put `arriveX`/`arriveY` exactly where the
// arrival camera will anchor it (its `self`), so the preview and the scene layer
// it hands over to are the same box.
function destSceneSize(destAspect) {
  const c = sceneCamera.value
  return coverOverscan(c.cw * c.zoom, c.ch * c.zoom, destAspect)
}

function destSceneLayer(destAspect, arriveX, arriveY, panX = 0, panY = 0) {
  const c = sceneCamera.value
  const { w, h } = destSceneSize(destAspect)
  // Clamp the alignment point to [0, 100]: beyond the image there is nothing to
  // show, so the shift is limited by the remaining image space in each direction
  // (asymmetric when the arrival point sits near an edge).
  const ax = Math.min(100, Math.max(0, arriveX + panX))
  const ay = Math.min(100, Math.max(0, arriveY + panY))
  const anchorX = ax + (50 - ax) * c.p
  const anchorY = ay + (50 - ay) * c.p
  return {
    w, h,
    panX: (ax / 100) * w - (anchorX / 100) * c.cw,
    panY: (ay / 100) * h - (anchorY / 100) * c.ch,
  }
}

// The wipe that plays while travelling, rendered as the scene layer it is about
// to become: same box, same anchoring, so the handover cannot jump. Null while
// the destination's aspect is unknown — the overlay then falls back to a CSS
// `cover` background.
const travelScene = computed(() => {
  const t = travelAnim.value
  if (!t.destAspect) return null
  return destSceneLayer(t.destAspect, t.bgX, t.bgY)
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
    const dest = destSceneSize(destAspect)
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
  const d = destSceneLayer(destAspect, arriveX, arriveY, panX, panY)
  // The destination layer is screen-fixed (its own pan is cancelled against the
  // dot's position inside the travelling scene), so moving the hole over it
  // reveals more world instead of dragging the world along.
  const x = -d.panX + c.panX - ((imgX / 100) * c.w)
  const y = -d.panY + c.panY - ((imgY / 100) * c.h)
  return {
    width: `${d.w}px`,
    height: `${d.h}px`,
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

// (`occupantX`/`occupantY` used to scatter an unplaced occupant near a zone so they
// were at least visible. They are gone: an unplaced occupant is not drawn at all now,
// so there is no default position left to compute.)

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
        location_id: z.location_id, x: z.x, y: z.y,
        background_image: z.background_image ?? null,
      }))),
    })
  } catch { /* silent */ }
  invalidateDestCache()  // the arrival point here just changed
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

// ── Nav dot positions ──────────────────────────────────────────────────────
// One rule for where a location's own nav dots sit: the parent dot (leads up)
// and its portal dots (lead sideways). The dots are *drawn* from these numbers
// and a travel *lands* on them, so a missing value has to resolve identically in
// both places — when it did not, the destination image visibly drifted at the
// handover. The backend seeds the same numbers when a link is created
// (`_ensure_child_zone` / `_ensure_parent_nav_position`), so these are the
// fallback for links authored before that existed.
const NAV_DOT_DEFAULTS = { parent: { x: 90, y: 15 }, portal: { x: 90, y: 50 } }
const portalKey = (i) => (i === 0 ? 'portal' : `portal:${i}`)
const parentDotDefault = () => ({ ...NAV_DOT_DEFAULTS.parent })
const portalDotDefault = (i = 0) => ({ x: NAV_DOT_DEFAULTS.portal.x, y: NAV_DOT_DEFAULTS.portal.y + i * 10 })

const navDotPositions = ref({ parent: parentDotDefault(), portal: portalDotDefault(0) })

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
    const pos = navDotPositions.value[key] || portalDotDefault(i)
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

// The one dot the guided route lights: the navdot whose target *is* the next hop
// the server returned. Identity is the stored link — a portal's target id, a
// zone's `location_id`, the parent's key — never a display name, so a rename
// cannot retarget the pulse. Empty when the character has no directions, or when
// they are already at the destination / nothing connects the two. Only ever ONE
// dot: the route is walked a hop at a time, so following directions still means
// travelling rather than reading the map.
const guidedDot = computed(() => {
  const hop = nav.value.next_hop
  if (!hop) return ''
  for (const nd of navDots.value) if (nd.target?.id === hop) return `nav-${nd.key}`
  for (const z of zones.value) if (z.location_id === hop) return `zone-${zoneId(z)}`
  return ''
})

// ── The arrival-point rule ─────────────────────────────────────────────────
// Where an entity lands when it arrives at a location coming from `fromId`.
// This is the ONE rule: the dot preview (`preloadDestNavCache`) and the travel
// itself (`travelWithAnimation`) both call it, so the framing you see through a
// hole is by construction the framing you land on. They used to be two separate
// implementations with different defaults, which is what made the destination
// image jump at the handover.
// Identity is always the stored link — a zone's `location_id`, or the parent /
// transversal edge — never a display name.
function arrivalPoint(destNav, fromId) {
  const loc = destNav?.location
  if (!loc || !fromId) return null
  // Arriving from a child: the destination carries a zone whose stored link
  // points back at where we came from.
  for (const z of (loc.zones || [])) {
    if (z.location_id === fromId) return { x: z.x, y: z.y }
  }
  // Arriving from the parent: this location's parent dot.
  if (destNav.parent?._key === fromId) {
    return loc.nav_positions?.parent || parentDotDefault()
  }
  // Arriving through a portal: this location's matching portal dot, by index —
  // a location can be linked to several, and each gets its own dot.
  const idx = (destNav.transversal || []).findIndex(t => t._key === fromId)
  if (idx >= 0) {
    return loc.nav_positions?.[portalKey(idx)] || portalDotDefault(idx)
  }
  return null
}

const imageAspect = ref(null)  // width/height ratio of current image, or null if unknown

// ── B96: where the roaming GM dot spawns ───────────────────────────────────
// The image point under the centre of the view, sampled *while* a perspective
// entity is held. The watcher below cannot work it out for itself: the camera
// re-anchors the instant `entityId` clears, so by the time it runs the framing
// we wanted to preserve is already gone.
//
// ⚠ Placement is load-bearing. `watchEffect` runs its callback **synchronously
// during setup**, which evaluates `sceneCamera` on the spot — and `sceneCamera`
// reads `imageAspect`. Put this block above that `const` and setup throws
// "can't access lexical declaration 'imageAspect' before initialization", taking
// the whole viewer down. The build cannot catch this class; only a browser can.
let viewCentreBeforeRoam = null
watchEffect(() => {
  if (props.entityId) viewCentreBeforeRoam = toImagePos(50, 50)
})

// Acting entity → free-roam: park the roaming dot on the view centre, so the
// handover leaves the camera where it was rather than jumping to the location
// centre. Nothing is stored — see the note on `gmDotPositions`.
watch(() => props.entityId, (id, prev) => {
  if (id || !prev) return  // only the acting-entity → free-roam edge
  const clamp = (v) => Math.max(2, Math.min(98, Math.round(v ?? 50)))
  setGmDotPos(clamp(viewCentreBeforeRoam?.x), clamp(viewCentreBeforeRoam?.y))
})

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

// May the GM *send* this occupant somewhere by dropping it on a navdot (B170)?
// Only the world occupants the GM may already drag — player characters stay
// immovable by the GM — and never in arrange mode, which is for positioning.
// Self is excluded: its own drag path animates the portal and moves the viewer.
function canTravelOccupant(occupant) {
  if (!occupant || occupant.id === props.entityId) return false
  if (props.editZones) return false
  return props.gmMode && (occupant.type === 'gmc' || occupant.type === 'asset')
}

function occupantInitials(name) {
  return name.split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase()
}

const poolDiceFor = (eid) => {
  const pool = props.remotePools[eid]
  const results = props.remoteResults[eid]
  const phase = pool?.phase || 'adding'
  // Rolled results are live only while the roll is: back in `adding` the ring
  // shows the pool itself — and nothing at all once the pool is cleared, rather
  // than holding the last roll's dice until the end of the beat.
  if (phase !== 'adding' && results?.rolls?.length) return results.rolls
  // Otherwise the pool's own dice, in **every** phase. Phase names come from two
  // vocabularies — the roller publishes `rolling`/`picking`, while the server's
  // roll endpoints broadcast `rolled`/`selected`/`resolved` (with the dice already
  // carrying their results). Gating this on a phase list is what made the ring
  // vanish the instant a roll started, with its dice still sitting right there.
  // A *cleared* pool still empties the ring: the server broadcasts it as
  // `dice: []` with phase `adding`, so this returns nothing.
  return (pool?.dice || []).map(d => (typeof d === 'string' ? d : d.die || d))
}
const poolPhaseFor = (eid) => props.remotePools[eid]?.phase || 'adding'

// ── Occupant drag ──────────────────────────────────

const occDragging = ref(null)  // { index }
// Which dot the pointer is actually dragging, set once it passes the tap/drag
// threshold: an occupant id, or 'self' for the GM free-roam dot. The dragged dot
// fades to a ghost so the destination preview under it stays readable, and rises
// above the expanded bubbles — an occupant otherwise paints *under* them.
const dragDotKey = ref('')
let occDragMoved = false       // pointer moved past the tap threshold
let draggingEmitted = false    // emitted 'dragging' so the HUD hides during a real drag
let occSuppressClick = false   // suppress the synthesized click after a real drag

// ── The unplace target (the human, 2026-09-26) ─────────────────────────────
// While an **occupant** or a **trait chip** is being dragged, a `( x )` sits at the
// top of the map. Dropping the dragged thing on it **unplaces** it — the occupant's
// `map_x`/`map_y` are cleared, the chip's entry is dropped from `trait_positions` —
// which is exactly the inverse of dragging one OUT of the drawer: it goes back there.
//
// **GM-only**, deliberately. A player can drag only their own dot, and unplacing it
// would hide them with no drawer to get back from — the drawer is arrange-mode
// furniture and they cannot open it. The GM can always re-place anything.
//
// The target is `pointer-events: none`; the drag's own hit test decides, so it can
// never swallow a pointer event mid-drag (the listeners live on `document`).
const unplaceArmed = ref(false)   // an unplaceable drag is running
const unplaceHover = ref(false)   // …and the pointer is over the target
const unplaceEl = ref(null)
let unplacePointer = null         // client px of the last drag move

function overUnplaceTarget() {
  const el = unplaceEl.value
  if (!el || !unplacePointer) return false
  const r = el.getBoundingClientRect()
  return unplacePointer.x >= r.left && unplacePointer.x <= r.right
    && unplacePointer.y >= r.top && unplacePointer.y <= r.bottom
}

function noteUnplacePointer(clientX, clientY) {
  unplacePointer = { x: clientX, y: clientY }
  unplaceHover.value = unplaceArmed.value && overUnplaceTarget()
}

// Called on EVERY end path, including the early returns below, so a stale target can
// never survive a drag it does not belong to.
function endUnplaceDrag() {
  unplaceArmed.value = false
  unplaceHover.value = false
  unplacePointer = null
}

async function unplaceOccupant(occ) {
  occ.map_x = null
  occ.map_y = null
  noteOwnMove(occ.id, null, null)
  try {
    await fetch(`/api/v1/entities/${occ.id}/map-position`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ map_x: null, map_y: null }),
    })
  } catch { /* silent: the dot is gone locally either way */ }
}

async function unplaceTrait(traitId) {
  const next = { ...traitPositions.value }
  delete next[traitId]
  traitPositions.value = next
  try {
    // Whole-map replace, so the absent id IS the unplacement.
    await fetch(`/api/v1/locations/${props.locationId}/trait-positions`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ trait_positions: next }),
    })
  } catch { /* silent: the chip is back in the drawer locally */ }
}

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

function onOccupantDragStart(e, occupant) {
  if (!canDragOccupant(occupant)) return
  occDragMoved = false
  // The template loops over the filtered (non-self) occupants, so a loop index would
  // not match occupants.value — resolve the real index by id.
  const realIndex = occupants.value.findIndex(o => o.id === occupant.id)
  if (realIndex === -1) return
  const el = viewerEl.value
  if (!el) return
  const clientX = e.touches ? e.touches[0].clientX : e.clientX
  const clientY = e.touches ? e.touches[0].clientY : e.clientY

  // Drag origin must be the dot's rendered viewport position at grab time:
  // self renders 1:1 at its map %, other occupants render through the
  // parallax conversion — otherwise the dot jumps on the first move. No position
  // fallback is needed: only PLACED occupants are rendered, so `map_x`/`map_y` are
  // always set here (an unplaced one lives in the drawer instead).
  const imgX = occupant.map_x
  const imgY = occupant.map_y
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
    dragDotKey.value = isSelf ? 'self' : (occupants.value[start.index]?.id || '')
    startFrameProfile(isSelf ? 'self' : 'occupant')
    if (!draggingEmitted) { draggingEmitted = true; emit('dragging', true) }
    // Past the tap threshold this is a real drag, so offer the unplace target.
    if (props.gmMode) unplaceArmed.value = true
  }
  e.preventDefault()
  notePointerEvent()
  noteUnplacePointer(clientX, clientY)
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

  // Arm travel for self, and for a world occupant the GM is carrying (B170): the
  // feedback — bubbles expanding, the nearest dot arming — is the same either way.
  if (occ && (occ.id === props.entityId || canTravelOccupant(occ))) {
    updateTravelTargets(occ.map_x, occ.map_y)
  }

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
    console.info('[travel] nav target', { id: nd.target.id, type: nd.type, effects: (nd.target.effects || []).length })
    const fakeZone = { x: nd.x, y: nd.y }
    // **The portal's effects travel with it.** `travelWithAnimation` hands
    // `child.effects` to `relocate`, which fires `/portal/{to}/fire` only when that
    // list is non-empty — so omitting it here meant a portal navdot *moved* the
    // traveller and never fired the portal. That is why dropping **your own**
    // character on a portal did nothing while a GM dropping *someone else* on the
    // same dot worked: the self path comes through here, the other path through
    // `travelDescriptor`, which does carry `effects` (2026-10-17).
    const fakeChild = {
      _key: nd.target.id, name: destName, current_universe: nd.target.universe,
      transversal_type: nd.type === 'portal' ? nd.transversal_type : null,
      effects: nd.target.effects,
    }
    travelWithAnimation(fakeZone, fakeChild, nd.image)
    return true
  }
  return false
}

// Resolve a drop target into the travel it implies. Deliberately parallel to
// `travelToTarget` (which drives the viewer's animation), but returning a
// description so `sendOccupant` can address it to someone who is not us — the
// occupant must reach the same world state its own drop would have produced.
function travelDescriptor(t) {
  if (!t) return null
  if (t.type === 'zone') {
    const zone = zones.value.find(z => zoneId(z) === t.id)
    if (!zone) return null
    const child = childForZone(zone)
    if (child) {
      return {
        locationId: child._key,
        universe: child.current_universe ?? '',
        consciousness: child.transversal_type === 'consciousness',
        effects: child.effects,
      }
    }
    // No resolvable child: a plain move to the stored link, as `travelToTarget`.
    if (zone.location_id) {
      return { locationId: zone.location_id, universe: '', consciousness: false, effects: null }
    }
    return null
  }
  if (t.type === 'nav') {
    const nd = navDots.value.find(d => d.key === t.id)
    if (!nd) return null
    return {
      locationId: nd.target.id,
      universe: nd.target.universe ?? '',
      // The destination's own consequences, read exactly as `travelWithAnimation`
      // reads them: only a portal can be a consciousness jump. Nav dots carry no
      // effects — portal effects hang off a zone's child location.
      consciousness: nd.type === 'portal' && nd.transversal_type === 'consciousness',
      effects: nd.target.effects,
    }
  }
  return null
}

// Send another entity travelling, mirroring `relocate`'s three travel kinds but
// addressed to it rather than to us. No `moved` emit: the viewer is not
// travelling, so App.vue's perspective must not change — only the occupant's
// location does.
async function sendOccupant(occId, desc) {
  const post = (url, body) => fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  try {
    if (desc.effects?.length) {
      await post(`/api/v1/locations/${props.locationId}/portal/${desc.locationId}/fire`,
        { entity_id: occId })
    } else if (desc.consciousness) {
      await post(`/api/v1/entities/${occId}/consciousness-travel`,
        { location: desc.locationId })
    } else {
      await post(`/api/v1/entities/${occId}/move`,
        { location: desc.locationId, universe: desc.universe })
    }
  } catch { /* silent */ }
  await fetchNav()  // it has left this location — drop its dot
}

async function onOccDragEnd() {
  document.removeEventListener('mousemove', onOccDragMove)
  document.removeEventListener('mouseup', onOccDragEnd)
  document.removeEventListener('touchmove', onOccDragMove)
  document.removeEventListener('touchend', onOccDragEnd)
  // Read the drop against the unplace target BEFORE clearing the drag state, then
  // clear it here so no early return below can leave a stale `( x )` on screen.
  const droppedOnUnplace = unplaceArmed.value && overUnplaceTarget()
  endUnplaceDrag()
  expandLevels.value = {}
  armedDot.value = ''
  dragDotKey.value = ''   // with the rest of the transient drag state: the early
                          // return below would otherwise leave the ghost on
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

  // Dropped on the `( x )`: UNPLACE rather than place, and never travel — the target
  // wins over anything the pointer happened to be passing near.
  if (droppedOnUnplace) {
    dragTarget = null
    await unplaceOccupant(occ)
    activeElement.value = { type: 'occupant', id: props.entityId }  // keep self popped
    return
  }

  // If the player dropped near a target, travel there
  console.info('[travel] occupant dropped', {
    occ: occ.id, entityId: props.entityId, editZones: props.editZones,
    dragTarget: dragTarget?.type || null, wasMoved, canTravel: canTravelOccupant(occ),
  })
  if (occ.id === props.entityId && dragTarget && !props.editZones) {
    const t = dragTarget
    dragTarget = null
    if (travelToTarget(t)) return
  }
  // The GM dropped a world occupant on a navdot: send it travelling (B170). Its
  // location changes server-side, so the drop must NOT also be persisted as a map
  // position here — the occupant no longer stands on this location.
  if (canTravelOccupant(occ) && dragTarget) {
    const desc = travelDescriptor(dragTarget)
    dragTarget = null
    if (desc) {
      await sendOccupant(occ.id, desc)
      activeElement.value = { type: 'occupant', id: props.entityId }  // keep self popped
      return
    }
  }
  dragTarget = null
  // Keep self popped
  activeElement.value = { type: 'occupant', id: props.entityId }

  noteOwnMove(occ.id, occ.map_x, occ.map_y)
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
    dragDotKey.value = 'self'
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
  dragDotKey.value = ''
  expandLevels.value = {}
  armedDot.value = ''
  if (draggingEmitted) { draggingEmitted = false; emit('dragging', false) }
  const t = dragTarget
  dragTarget = null
  if (!wasMoved) return
  armClickSuppression()  // a drag must not fire the click handler
  // Dropped on a location → travel the view there
  // Diagnostic (remove once the portal path is confirmed): a dot click that does not
  // travel has exactly two causes here — no target, or arrange mode.
  console.info('[travel] dot click', { target: t?.type, editZones: props.editZones, entityId: props.entityId })
  if (t && !props.editZones) travelToTarget(t)
}

// ── Fetch nav data ─────────────────────────────────

async function fetchNav() {
  try {
    // The destination is per-character, so the guided route only exists when we
    // ask for it as someone (`destination` / `next_hop` in the response).
    const q = props.entityId ? `?entity_id=${encodeURIComponent(props.entityId)}` : ''
    const r = await fetch(`/api/v1/locations/${props.locationId}/navigate${q}`)
    const data = await r.json()
    nav.value = data
    zones.value = data.location?.zones || []
    occupants.value = data.occupants || []
    loadNavPositions()
    loadTraitPositions()
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

    // …and this location's traits, already filtered for this viewer (B92).
    fetchLocationTraits()
  } catch { /* silent */ }
}

// The location's traits as THIS viewer may see them ([[B92]]): the location's own
// of every kind, plus the challenge pools it inherits from its ancestors. The
// server resolves the fog-of-war because only it knows who is asking — pass the
// acting character and a hidden owner narrows to its `known_to`; omit it (GM
// free-roam) for the whole set with the flags still on it. Failure is silent and
// leaves the block empty, like every other background read here.
const locationTraits = ref([])

// Chip positions, keyed by trait-setting id — the sibling of `navDotPositions`, and
// loaded the same way. A **ref**, not a computed, because a drag mutates it live and
// it is the whole map that gets saved.
const traitPositions = ref({})

function loadTraitPositions() {
  const raw = nav.value.location?.trait_positions
  if (!raw) return
  try {
    const parsed = typeof raw === 'string' ? JSON.parse(raw) : raw
    const out = {}
    for (const [k, v] of Object.entries(parsed || {})) {
      if (v && typeof v.x === 'number' && typeof v.y === 'number') out[k] = v
    }
    traitPositions.value = out
  } catch {}
}

// A placed chip is a scene element; the rest stay in the auto-stack beside the
// labels, so nothing has to be hand-placed to be readable.
const placedTraits = computed(() => locationTraits.value.filter(t => traitPositions.value[t.id]))
const unplacedTraits = computed(() => locationTraits.value.filter(t => !traitPositions.value[t.id]))

// ── A chip opens by proximity, pointer or tap ────────────────────────────────
//
// The nav bubbles already expand near the dragged character, but only *while* a
// drag is running: `updateTravelTargets` is called from the drag frames and
// `expandLevels` is wiped on release (see `onGmDotDragEnd`). A trait chip has to
// stay open once the character is beside it — the human's rule, 2026-09-25 — so
// this is a **computed** over the self position instead of drag-time state, and it
// therefore holds at rest, after a drag, and when someone else moves the body.
//
// Same radius and curve as the bubbles (`EXPAND_PROXIMITY`, quadratic) so a chip and
// a nav dot near the character open together rather than at two different distances.
const hoveredTraitId = ref('')
const peekTraitId = ref('')       // tapped open — the touch path, where there is no hover
// The level at which an open chip counts as readable, for the click rule below.
const TRAIT_EXPANDED_AT = 0.5

// Where to measure proximity from: the character's body if it is on this map, else
// the GM's free-roam dot, else nowhere. Falling back to the location centre (what
// `selfPos` does for the camera) would open chips in the middle of the room for a
// viewer who is not standing anywhere.
const proximityAnchor = computed(() => {
  if (props.entityId && occupants.value.some(o => o.id === props.entityId)) return selfPos.value
  return gmSelfPos.value || null
})

const traitProximity = computed(() => {
  const anchor = proximityAnchor.value
  const out = {}
  if (!anchor) return out
  for (const t of placedTraits.value) {
    const p = traitPositions.value[t.id]
    if (!p) continue
    const dist = Math.hypot(p.x - anchor.x, p.y - anchor.y)
    if (dist < EXPAND_PROXIMITY) {
      const k = dist / EXPAND_PROXIMITY
      out[t.id] = 1 - k * k           // quadratic: opens fast, like the bubbles
    }
  }
  return out
})

function traitChipExpanded(t) {
  // The stack is never collapsed: nothing can be approached there, and it is the
  // legend you read the map against.
  if (!traitPositions.value[t.id]) return true
  // Arrange mode opens every chip, the way it already opens every zone and nav dot:
  // the GM is placing these, and you cannot place what you cannot read. Without it,
  // dragging a chip means chasing an unlabelled marker around the map.
  if (props.editZones) return true
  if (hoveredTraitId.value === t.id || peekTraitId.value === t.id) return true
  return (traitProximity.value[t.id] || 0) >= TRAIT_EXPANDED_AT
}

// Dragging a chip: the same plumbing the nav dots use, and the same composable — a
// chip and a dot are both one {x, y} entry in a position map on this location. The
// map is written whole, like `nav_positions`, so an absent id keeps meaning "not
// placed yet".
function onTraitChipDragStart(e, trait) {
  let from = traitPositions.value[trait.id]
  if (!from) {
    // Promoting a chip out of the auto-stack: it has no scene position yet, so it
    // lands under the pointer and the drag continues from there — grabbing it does
    // not fling it to a default spot first.
    //
    // `getPosFromEvent` is the px → viewport% → image% conversion the zone drag uses.
    // Do NOT hand-roll it: `toImagePos` takes viewport PERCENTAGES, so passing pixels
    // turns a 30px pointer into "30%" and a 200px one into "200%", which lands the
    // chip outside the scene — where it simply disappears.
    const img = getPosFromEvent(e)
    from = {
      x: Math.max(2, Math.min(98, Math.round(img.x))),
      y: Math.max(2, Math.min(98, Math.round(img.y))),
    }
    traitPositions.value = { ...traitPositions.value, [trait.id]: from }
  }
  percentDrag.start(e, {
    x: from.x,
    y: from.y,
    onMove: (x, y, cx, cy) => {
      traitPositions.value = { ...traitPositions.value, [trait.id]: { x, y } }
      // Moving is dragging, not clicking: offer the unplace target.
      if (props.gmMode) unplaceArmed.value = true
      noteUnplacePointer(cx, cy)
    },
    onEnd: async (pointer) => {
      // Dropped on the `( x )`: the chip goes back to the drawer instead of being
      // saved. Checked before the PUT so the absence IS the unplacement.
      if (pointer) noteUnplacePointer(pointer.clientX, pointer.clientY)
      if (unplaceArmed.value && overUnplaceTarget()) {
        endUnplaceDrag()
        await unplaceTrait(trait.id)
        return
      }
      endUnplaceDrag()
      try {
        await fetch(`/api/v1/locations/${props.locationId}/trait-positions`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ trait_positions: traitPositions.value }),
        })
      } catch { /* silent: the chip stays where it was dragged locally */ }
    },
  })
}

// Dragging an unplaced occupant out of the drawer **places** them, exactly as
// dragging their dot does: the same `usePercentDrag`, the same PATCH. The occupant
// has no stored position yet, so — like a chip promoted out of the stack — they land
// under the pointer rather than jumping to a default first, and the moment
// `map_x`/`map_y` are set the drawer entry disappears (that is what `unplaced`
// measures), leaving only their dot on the map.
function onOccupantDrawerDragStart(e, occ) {
  const img = getPosFromEvent(e)
  const from = {
    x: Math.max(2, Math.min(98, Math.round(img.x))),
    y: Math.max(2, Math.min(98, Math.round(img.y))),
  }
  occ.map_x = from.x
  occ.map_y = from.y
  percentDrag.start(e, {
    x: from.x,
    y: from.y,
    onMove: (x, y) => { occ.map_x = x; occ.map_y = y },
    onEnd: async () => {
      noteOwnMove(occ.id, occ.map_x, occ.map_y)
      try {
        await fetch(`/api/v1/entities/${occ.id}/map-position`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ map_x: occ.map_x, map_y: occ.map_y }),
        })
      } catch { /* silent: they stay where they were dragged locally */ }
    },
  })
}

// (The rating's dice — and the grouping that fans them — live in `TraitChip`, so
// both the auto-stack and the scene render them identically.)

async function fetchLocationTraits() {
  try {
    const q = props.entityId ? `?viewer=${encodeURIComponent(props.entityId)}` : ''
    const r = await fetch(`/api/v1/locations/${props.locationId}/traits${q}`)
    const data = await r.json()
    // TRAITS tab only: a trait's tab is its trait SET's `sheet_tab`, reported by the
    // server. Profile-tab traits are the place's imagen/appearance configuration,
    // which has no business on the map (B92, the human's rule). `normalizeLocationTrait`
    // then puts each entry into the shape `useTraitPlay` reads — the wire's snake_case
    // and lowercase enums are not it, and getting that wrong made a CHALLENGE trait
    // behave like a static one.
    locationTraits.value = (data.traits || [])
      .filter(t => (t.sheet_tab || 'traits') === 'traits')
      .map(normalizeLocationTrait)
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
  console.info('[travel] relocate', { to: locationId, entityId: props.entityId, effects: (effects || []).length,
    branch: !props.entityId ? 'view-only' : ((effects && effects.length) ? 'FIRE PORTAL' : (consciousness ? 'consciousness' : 'plain move')) })
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

// A zone's label is the linked child's name — derived, never stored, so renaming
// a child can never leave the pin stale. An unresolvable child renders unlabelled
// rather than borrowing a copy that can drift.
function zoneLabel(zone) {
  return childForZone(zone)?.name || ''
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

// Playing a location's trait from its chip: the SAME act a trait row's rating click
// performs in the sheet, through the same composable — so the gates, the pool payload
// and the challenge/resource spend rules cannot drift between the two surfaces.
const { spendResourceDie, spendChallengeDie } = useApi()
const traitPlay = useTraitPlay({
  phase: () => props.phase,
  // No pool tree exists on the map, so the sheet's cascade (descendants, carried
  // negatives, completing ancestors) is honestly a no-op here: the dice layer decides
  // what a repeated play does.
  cascade: () => {},
  addToPool: (payload) => emit('addToPool', payload),
  // Armed SFX live in the roller, which the map has no view of. No location trait
  // carries SFX today, so this is where a future fold-out would hook in.
  armedSfxIdsFor: () => [],
  spendResourceDie,
  spendChallengeDie,
  // A spend changes the pool's remaining dice, so the chips' ratings must be re-read.
  refresh: async () => { await fetchLocationTraits() },
})

// One gesture, two steps: a click on a chip that is not open yet OPENS it, and the
// click after that plays the trait. Without this a resting chip — which is now a bare
// marker with no words — would spend a die on a tap that was only meant to read it.
// The stack's chips are always open, so they still play on the first click.
function onTraitChipClick(trait) {
  if (!traitChipExpanded(trait)) {
    peekTraitId.value = trait.id
    return
  }
  traitPlay.playTrait(trait)
}

// Everything the GM places by hand drags the same way — a nav dot and a trait chip
// are both one {x, y} entry in a position map on this location, expressed as a
// percentage **of the scene layer**. `usePercentDrag` therefore needs the scene's own
// px size to convert the pointer's movement, not the viewer's box: the scene is
// bigger than the viewer (overscan + teaser zoom), so the viewer's size made a
// dragged element outrun the cursor by `scene ÷ viewer` — 1.19× on a square
// background, 2.11× on a wide one. Each caller supplies only its own map, key, write.
const percentDrag = usePercentDrag({
  enabled: () => props.editZones,
  viewerEl,
  span: () => ({ w: sceneCamera.value.w, h: sceneCamera.value.h }),
})

function onNavDragStart(e, nd) {
  percentDrag.start(e, {
    x: nd.x,
    y: nd.y,
    onMove: (x, y) => { navDotPositions.value[nd.key] = { x, y } },
    onEnd: async () => {
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
      invalidateDestCache()  // the arrival point here just changed
    },
  })
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
  activeElement.value = { type: 'zone', name: child.name }

  // Warm the destination before the portal opens. `new Image()` is not enough:
  // it cannot decode a .webm at all, and even a cached still has to be decoded
  // before it can paint. Bounded, because a cold asset must not stall the drop —
  // the real guarantee is the paint gate at the handover below.
  const preload = await preloadMedia(img, { timeout: 500 })
  warmMedia = preload

  // Hide elements during portal
  showElements.value = false
  showSelf.value = false

  // Where the character lands: the SAME rule the dot preview used to frame the
  // hole (`arrivalPoint`), so the preview and the landing cannot disagree.
  let arriveX = zone.x, arriveY = zone.y  // fallback: the source zone's position
  try {
    const r = await fetch(`/api/v1/locations/${child._key}/navigate`)
    const destNav = await r.json()
    const arrive = arrivalPoint(destNav, sourceId)
    if (arrive) { arriveX = arrive.x; arriveY = arrive.y }
  } catch { /* use fallback */ }

  // Compute portal origin using current character position
  const vp = toViewportPos(zone.x, zone.y)

  // Aspect for the wipe's sizing: the same one the arrival camera will use. The
  // cache is filled by the destination preload via `probeAspect` (video-aware);
  // the warm element's own intrinsic size is preferred when it arrived in time.
  const preW = preload ? (preload.videoWidth || preload.naturalWidth) : 0
  const preH = preload ? (preload.videoHeight || preload.naturalHeight) : 0
  const destAspect = (preW && preH ? preW / preH : null)
    || destNavCache.value[child._key]?.destAspect

  travelAnim.value = { active: true, x: parseFloat(vp.left), y: parseFloat(vp.top), image: img, bgX: arriveX, bgY: arriveY, destAspect }

  // Now set the new aspect ratio so background switch uses correct sizing
  if (preW && preH) imageAspect.value = preW / preH
  else if (destAspect) imageAspect.value = destAspect

  relocate(child._key, child.current_universe, child.transversal_type === 'consciousness', child.effects, child.name)

  setTimeout(async () => {
    await fetchNav()

    // Reset overlay to new location's value (may be null)
    optimisticOverlay.value = props.overlay

    // Lock position and swap the background UNDER the portal. The portal is not
    // lifted here — it waits for that media to actually paint (see
    // `waitForBackgroundPaint`). Removing it on the timer alone is what flashed
    // black: the element had the new `src` but no decoded frame yet, and a
    // .webm had not even started playing.
    const so = occupants.value.find(o => o.id === props.entityId)
    if (so) { so.map_x = arriveX; so.map_y = arriveY }
    else { setGmDotPos(arriveX, arriveY) }  // free-roam dot lands here
    currentImage.value = img

    // Sync background if it changed during travel (watch skips while travelAnim is active)
    if (props.backgroundImage && props.backgroundImage !== currentImage.value) {
      currentImage.value = props.backgroundImage
    }

    await waitForBackgroundPaint()
    warmMedia = null

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

// Resolve once the scene layer's OWN media has a frame to paint, so the portal is
// never lifted off a blank background. Waiting on the preloaded element is not
// enough — Vue patches the scene layer's element separately, and a video has to
// reach a decoded frame, not merely fetched bytes. Capped so a broken or slow
// asset cannot strand the overlay on screen.
function nextPaint() {
  return new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)))
}

function waitForBackgroundPaint(timeout = 2000) {
  const painted = (async () => {
    await nextTick()  // let Vue mount/patch the scene-layer media first
    if (isVideoBg.value) {
      const el = videoBgEl.value
      if (!el) return
      if (el.readyState < 2) {  // HAVE_CURRENT_DATA — no decoded frame yet
        await new Promise((resolve) => {
          el.addEventListener('loadeddata', resolve, { once: true })
          el.addEventListener('error', resolve, { once: true })
        })
      }
      // A decoded first frame exists now (a paused video still paints it), so the
      // compositor only needs a paint cycle. `requestVideoFrameCallback` is the
      // exact signal, but a fully-occluded video can be throttled into never
      // presenting, so it may only *confirm* the paint — never hold it up.
      if (el.requestVideoFrameCallback) {
        await Promise.race([
          new Promise((resolve) => el.requestVideoFrameCallback(() => resolve())),
          nextPaint(),
        ])
      } else {
        await nextPaint()
      }
    } else {
      const el = bgImgEl.value
      if (!el) return
      // decode() settles when the still is decoded and ready to paint.
      if (el.decode) await el.decode().catch(() => {})
      else if (!el.complete) {
        await new Promise((resolve) => {
          el.addEventListener('load', resolve, { once: true })
          el.addEventListener('error', resolve, { once: true })
        })
      }
      await nextPaint()
    }
  })()
  return Promise.race([painted, new Promise((resolve) => setTimeout(resolve, timeout))])
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
  noteOwnMove(props.entityId, nx, ny)
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
    // Tapping the map also closes the rail: it is a panel you opened, so the map is the
    // natural "never mind". This is the other half of it being over the map on purpose.
    railOpen.value = false
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
  // A peek belongs to the room it was opened in — the chips are different ones now.
  peekTraitId.value = ''
  hoveredTraitId.value = ''
  if (!travelAnim.value.active) fetchNav()
})

const lerpActive = ref(false)
// Position writes WE sent, so their SSE echo does not animate. The server
// broadcasts `entity_moved` to every subscriber including the one that asked for
// it, so without this a GM drag smooths *into* the position they just dropped it
// at. Matched on entity + the exact position written, and only trusted briefly,
// so a genuine foreign move to that same spot still animates later.
const ownMoves = new Map()  // entityId -> { x, y, at }
function noteOwnMove(id, x, y) {
  if (id) ownMoves.set(id, { x, y, at: Date.now() })
}
function isOwnMove(id, x, y) {
  const m = ownMoves.get(id)
  return !!m && m.x === x && m.y === y && Date.now() - m.at < 2000
}
const destNavCache = ref({})  // { [locationId]: { arriveX, arriveY, destAspect } } lazy-populated

// Drop this location's cached landing point. That entry describes how to arrive
// *here* — it is computed from this location's own nav positions and zones — so
// editing either makes it stale. The staleness is invisible and sticky: the hole
// keeps framing the destination at the old spot, and the travel now reads the
// same rule, so both would agree on the wrong number until the page reloaded.
function invalidateDestCache() {
  delete destNavCache.value[props.locationId]
}

// ── Lazy pre-fetch destination nav data for dot overlay positioning ──

async function preloadDestNavCache() {
  const currentId = props.locationId

  // Built from the DOTS, not from the raw payload: each entry needs its dot's own
  // x/y, because that position is the fallback landing point for a **one-way**
  // edge (see below). The zone dots are the child links; `navDots` covers the
  // parent and every portal.
  const destinations = []
  for (const z of zones.value) {
    const child = childForZone(z)
    if (child) destinations.push({ id: child._key, name: child.name, image: childImage(z), x: z.x, y: z.y })
  }
  for (const nd of navDots.value) {
    destinations.push({ id: nd.target.id, name: nd.name, image: nd.image, x: nd.x, y: nd.y })
  }

  for (const dest of destinations) {
    // Only a real aspect counts as cached — a destination that probed before its
    // image existed must be able to pick one up, and a null aspect is exactly
    // what makes the hole preview silently fall back to a dot-sized thumbnail.
    if (destNavCache.value[dest.id]?.destAspect) continue
    try {
      const r = await fetch(`/api/v1/locations/${dest.id}/navigate`)
      const data = await r.json()
      const loc = data.location

      // The very same rule the travel uses — see `arrivalPoint` — with the very
      // same fallback. A **one-way** transversal edge leaves the destination with
      // no landing dot for us (100 of 354 transversal edges store only one
      // direction), so `arrivalPoint` legitimately returns null; travel then lands
      // at the source dot's own position. Skipping the cache entirely there is
      // what left those dots showing a plain thumbnail instead of the hole —
      // e.g. Azure Dawn → Whispering Forest. Using the same fallback keeps the
      // preview and the landing in step, which is the whole point of sharing the
      // rule.
      const arrive = arrivalPoint(data, currentId) || { x: dest.x, y: dest.y }

      // Get destination image aspect. Videos must be probed through metadata:
      // an <img> cannot decode .webm, which silently left animated destinations
      // (e.g. Cloud-Soaked Bazaar) without a hole preview.
      //
      // The background is only the arrival image when it exists: most locations
      // carry a navdot image and NO background (283 of 410), and the arrival
      // falls back to the navdot image there (the dot's own `childImage`). Probing
      // `background_image` alone left every one of those with a null aspect, which
      // drops the hole preview back to a plain dot-sized thumbnail.
      //
      // Take the first candidate that actually **decodes**, not the first that is
      // merely truthy. A dead URL used to win over a working one: a stale
      // `background_image` naming an `_anim_` file the media pipeline had renamed
      // probed to null, and the navdot — fine all along — was never tried, so the
      // hole silently fell back to a plain thumbnail while the arrival painted the
      // real background (Beast Pools, 2026-09-26). The payload now resolves the
      // background server-side, so this is the belt to that braces: no single 404
      // may take the hole preview down again.
      const destAspect =
        (await probeAspect(loc?.background_image)) ?? (await probeAspect(dest.image))

      destNavCache.value = { ...destNavCache.value, [dest.id]: { arriveX: arrive.x, arriveY: arrive.y, destAspect } }
    } catch { /* skip failed pre-fetches */ }
  }
}

// Re-sync after a position update. `origin` (when the caller knows it) tells us
// whose update it was: the lerp is for a *foreign* move — something that changed
// where we were not looking — and direct input must land instantly, or the dot
// slides out from under the pointer that is still holding it.
async function fetchNavWithLerp(origin = null) {
  if (origin && isOwnMove(origin.id, origin.x, origin.y)) {
    await fetchNav()
    return
  }
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

/* Location traits (B92) — chips in the sheet's visual language ([[TraitRow]]), so a
   trait reads the same wherever it appears: an ordinary rounded chip, the name on
   row 1 and the statement on row 2, and the FULL rating (every die) on the right —
   not the chip's edge. Sits under the two labels above; when the GM's overlay
   switcher is present (also GM-only, at +44px) it steps below it rather than
   overlapping. `pointer-events: none` like the labels, so the map keeps every
   click. This block is the AUTO-STACK for chips with no stored position yet; a
   placed chip is drawn in the scene instead ([[Location Trait Chips]]). */
.loc-traits {
  /* Internal breathing room for what the chips paint outside their own box (a cutout
     stands ~10px proud above and below, the rating dice straddle the right edge), kept
     in variables because **the box is offset by them**: padding that moved the chips
     would let the rail cover scene chips it used to sit clear of, and a placed chip
     under the rail cannot be grabbed — its own click target wins the hit test. */
  --rail-pad-y: 10px;
  --rail-pad-x: 8px;
  /* The rail's top as ONE value: `max-height` below subtracts exactly the offset the
     box starts at, or the cap drifts from where the rail begins. The switcher variant
     moves it, so it moves the variable instead of `top`. */
  --rail-top: calc(env(safe-area-inset-top, 16px) + 44px);
  position: absolute;
  top: calc(var(--rail-top) - var(--rail-pad-y));   /* net: the chips sit at --rail-top */
  left: calc(16px - var(--rail-pad-x));             /* …and at 16px, as they always have */
  display: flex; flex-direction: column; gap: 10px;
  /* Each chip sizes to ITS own content, the width it would have if it were placed in
     the scene. A column flex container stretches its items across the cross axis by
     default, so without this every chip took the width of the WIDEST one in the stack
     (and, capped by the max-width below, the same 40vw on a phone) — a two-word trait
     drawn as wide as the longest sentence in the room. */
  align-items: flex-start;
  max-width: 40vw;
  z-index: 2;
  /* Never taller than the map it floats over: past that the rail SCROLLS instead of
     running off the bottom of the viewer (the human, 2026-09-26). Written from the same
     `--rail-top` the box starts at, so the cap cannot drift from the box. */
  max-height: calc(100% - (var(--rail-top) - var(--rail-pad-y)) - 16px);
  /* Vertical ONLY — the rail is a column and a horizontal scrollbar would be noise.
     Note `overflow-y: auto` clips BOTH axes (the spec promotes the other axis to
     `auto`), which is what the padding above is for. */
  overflow-y: auto;
  overflow-x: hidden;
  overscroll-behavior: contain;   /* don't chain the wheel to the page behind */
  padding: var(--rail-pad-y) var(--rail-pad-x);
  /* Interactive, because the rail is now OPENED (the human, 2026-09-26) rather than
     always on screen: a scroll container that ignores pointer events cannot be scrolled
     at all — not by wheel, not by touch. Taking events is acceptable here precisely
     because the rail is transient; closed, it is not over the map at all. */
  pointer-events: auto;
}

.loc-traits.has-switcher {
  --rail-top: calc(env(safe-area-inset-top, 16px) + 80px);
}

/* The one top control: the rail's handle when idle, the unplace target while a drag is
   running. Centred at the top of the map, in the same pill language as the other map
   controls. */
.top-control {
  position: absolute;
  top: calc(env(safe-area-inset-top, 16px) + 6px);
  left: 50%;
  transform: translateX(-50%);
  padding: 5px 15px;
  border-radius: 999px;
  border: 1px solid rgba(255,255,255,0.18);
  background: rgba(10,10,20,0.55);
  backdrop-filter: blur(4px);
  color: var(--map-text);
  font-size: 12px;
  letter-spacing: 0.5px;
  text-shadow: 0 1px 6px rgba(0,0,0,0.85);
  cursor: pointer;
  z-index: 40;
  /* IDLE it is a button — the rail's handle — so it must be tappable. It is a small,
     visible control, so taking events here costs the map nothing it did not already
     give up to the other controls. */
  pointer-events: auto;
  -webkit-tap-highlight-color: transparent;
}

/* …but while a drag is running it is a DROP TARGET, not a button: the drag owns the
   pointer through document listeners and hit-testing is done against this rect, so it
   must not intercept anything itself. */
.top-control.unplace-armed {
  pointer-events: none;
  cursor: default;
  font-size: 14px;
  letter-spacing: 1px;
  border-style: dashed;
  border-color: rgba(255,255,255,0.45);
}

/* Over it: the drop will unplace. Same accent language as the armed travel dot, so
   "this drop will do something" reads the same way everywhere on the map. */
.top-control.armed {
  border-color: var(--accent);
  border-style: solid;
  background: var(--accent-16);
}

/* The rail is open (and no drag is running): the handle reads as pressed. */
.top-control.open {
  border-color: var(--accent);
  background: var(--accent-16);
}

/* An unplaced OCCUPANT in the same drawer: a small row — picture or initials, then
   the name — in the chips' own visual language, so the drawer reads as one list of
   "not placed yet" whatever the kind. `pointer-events: auto` so the row can be dragged
   out of the rail (the rail takes events while it is open; see `.loc-traits`). */
.occ-drawer-chip {
  display: flex; align-items: center; gap: 7px;
  padding: 3px 9px 3px 5px;
  border: 1px solid rgba(255,255,255,0.18);
  border-radius: 11px;
  background: rgba(10,10,20,0.55);
  backdrop-filter: blur(4px);
  font-size: 12px;
  color: var(--map-text);
  text-shadow: 0 1px 6px rgba(0,0,0,0.85);
  cursor: grab;
  pointer-events: auto;
}
.occ-drawer-img {
  width: 22px; height: 22px; border-radius: 50%; object-fit: cover; flex: 0 0 auto;
}
.occ-drawer-initials {
  width: 22px; height: 22px; border-radius: 50%; flex: 0 0 auto;
  display: flex; align-items: center; justify-content: center;
  font-size: 10px; background: rgba(255,255,255,0.12);
}
.occ-drawer-name { white-space: nowrap; }

/* The chip's own appearance — the edge, the two text rows, and the fanned dice —
   lives in `location/TraitChip.vue`, because the same chip renders in two places
   here (the auto-stack below, and a scene element once placed). */

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

/* Map-dot styling lives in MapDot.vue's global block ONLY. It used to be
   duplicated here as a scoped copy, which — being scoped — compiled to
   `.map-dot[data-v-…]` and outranked the component's own rules, silently
   shadowing them: the dot's `transition` lost `opacity` and `transform`, and
   `.armed`/`.dragging`'s z-index lifts were beaten by `.expanded`. Two copies
   of one component's styles will always drift; keep them in MapDot. */

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
