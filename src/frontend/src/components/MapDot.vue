<template>
  <button
    class="map-dot"
    :class="dotClasses"
    :style="dotStyle"
    :title="draggable ? 'Drag to reposition' : title"
    @mousedown="onDragStart"
    @touchstart="onDragStart"
    @click.stop="onClick"
  >
    <video
      v-if="image && overlayVisible && isVideoImage"
      :src="image"
      class="dot-overlay"
      :class="{ 'occ-img-overlay': type === 'occupant' || type === 'self', 'dot-hole': holeStyle, 'img-transparent': imageTransparent }"
      :style="holeStyle || overlayImgStyle"
      autoplay loop muted playsinline
      @click.stop="onOverlayClick"
    />
    <img
      v-else-if="image && overlayVisible"
      :src="image"
      class="dot-overlay"
      :class="{ 'occ-img-overlay': type === 'occupant' || type === 'self', 'dot-hole': holeStyle, 'img-transparent': imageTransparent }"
      :style="holeStyle || overlayImgStyle"
      alt=""
      draggable="false"
      @click.stop="onOverlayClick"
    />
    <span
      v-else-if="overlayVisible && label"
      class="dot-label"
      @click.stop="onOverlayClick"
    >{{ label }}</span>
    <span
      v-else-if="overlayVisible"
      class="dot-initials"
    >{{ initials }}</span>
  </button>
</template>

<script setup>
import { computed } from 'vue'
import { isVideoUrl } from '@/composables/media.js'

const props = defineProps({
  type: { type: String, required: true },
  variant: { type: String, default: '' },
  image: { type: String, default: null },
  imageTransparent: { type: Boolean, default: false },  // cutout image — no bubble/crop
  label: { type: String, default: '' },
  initials: { type: String, default: '' },
  x: { type: Number, required: true },
  y: { type: Number, required: true },
  expanded: { type: Boolean, default: false },
  draggable: { type: Boolean, default: false },
  lerping: { type: Boolean, default: false },
  title: { type: String, default: '' },
  holeStyle: { type: Object, default: null },  // px transform for the "hole" dest preview (zone/nav)
  expandLevel: { type: Number, default: 0 },  // 0..1 — proximity-driven size
})

const emit = defineEmits(['click', 'overlay-click', 'drag-start'])

const isVideoImage = computed(() => isVideoUrl(props.image))

// 0 (collapsed) .. 1 (fully expanded). Tap/edit/self/occupant are always 1;
// zone/nav dots scale continuously with expandLevel during a drag.
const effectiveLevel = computed(() => {
  if (props.expanded) return 1
  const l = props.expandLevel || 0
  return l > 1 ? 1 : l < 0 ? 0 : l
})

const dotClasses = computed(() => [
  props.type === 'zone' ? 'zone-dot' : '',
  props.type === 'occupant' ? 'occ-dot' : '',
  props.type === 'nav' ? 'nav-dot' : '',
  props.type === 'self' ? 'occ-dot self' : '',
  props.variant ? `occ-${props.variant}` : '',
  props.variant && props.type === 'nav' ? `nav-${props.variant}` : '',
  { expanded: effectiveLevel.value > 0, draggable: props.draggable, lerping: props.lerping, 'dot-transparent': props.imageTransparent },
].filter(Boolean))

const dotStyle = computed(() => {
  const style = { left: props.x.toFixed(1) + '%', top: props.y.toFixed(1) + '%' }
  if (props.type === 'zone' || props.type === 'nav') {
    const full = Math.min(260, Math.max(120, window.innerWidth * 0.14))
    const size = 16 + (full - 16) * effectiveLevel.value
    style.width = size + 'px'
    style.height = size + 'px'
    style.marginLeft = -(size / 2) + 'px'
    style.marginTop = -(size / 2) + 'px'
  }
  return style
})

const overlayVisible = computed(() => effectiveLevel.value > 0 || props.type === 'self' || props.type === 'occupant')

// Non-hole image layout. Transparent cutouts are owned entirely by the
// .img-transparent CSS (emerging-from-the-ring composition); everything else
// is a plain cover fill.
const overlayImgStyle = computed(() => {
  if (props.imageTransparent) return null
  return { width: '100%', height: '100%', objectFit: 'cover' }
})

function onClick() { emit('click', { type: props.type, x: props.x, y: props.y }) }
function onOverlayClick() { emit('overlay-click', { type: props.type, x: props.x, y: props.y }) }
function onDragStart(e) { if (props.draggable) emit('drag-start', e) }
</script>

<style>
.map-dot {
  position: absolute;
  pointer-events: auto; /* parent scene-layer is pointer-events:none — dots opt back in */
  margin-left: -8px; margin-top: -8px;
  border-radius: 50%;
  border: none;
  cursor: pointer;
  transition: width 0.25s ease, height 0.25s ease, margin 0.25s ease, background 0.25s ease, border 0.25s ease, box-shadow 0.25s ease;
  -webkit-tap-highlight-color: transparent;
  padding: 0;
  z-index: 3;
}
.zone-dot { width: 16px; height: 16px; background: rgba(64,184,96,0.7); box-shadow: 0 0 6px rgba(64,184,96,0.4); }
.occ-dot { width: 16px; height: 16px; }
.occ-dot.occ-character { background: rgba(64,136,212,0.8); box-shadow: 0 0 6px rgba(64,136,212,0.4); }
.occ-dot.occ-gmc { background: rgba(232,136,48,0.8); box-shadow: 0 0 6px rgba(232,136,48,0.4); }
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
.occ-dot:not(.self).lerping {
  transition: left 1.5s ease-out, top 1.5s ease-out, width 0.25s ease, height 0.25s ease, margin 0.25s ease, background 0.25s ease, border 0.25s ease, box-shadow 0.25s ease;
}
.nav-dot { width: 16px; height: 16px; }
.nav-dot.nav-parent { background: rgba(200,170,60,0.8); box-shadow: 0 0 6px rgba(200,170,60,0.4); }
.nav-dot.nav-portal { background: rgba(160,80,200,0.8); box-shadow: 0 0 6px rgba(160,80,200,0.4); }
.nav-dot.expanded {
  background: rgba(10,10,20,0.85); border: none;
  box-shadow: inset 0 0 20px rgba(0,0,0,0.6), inset 0 0 4px rgba(255,255,255,0.1);
  z-index: 10; overflow: hidden;
}
.map-dot.expanded {
  background: rgba(10,10,20,0.85); border: none;
  box-shadow: inset 0 0 20px rgba(0,0,0,0.6), inset 0 0 4px rgba(255,255,255,0.1);
  z-index: 10; overflow: hidden;
}
.occ-dot.expanded {
  width: clamp(60px, 5.5vw, 88px) !important; height: clamp(60px, 5.5vw, 88px) !important;
  margin-left: calc(clamp(60px, 5.5vw, 88px) / -2); margin-top: calc(clamp(60px, 5.5vw, 88px) / -2);
  --dot-r: calc(clamp(60px, 5.5vw, 88px) / 2);  /* ring radius, for the cutout's bottom crop */
}
/* Viewed — the rail's `.peer-chip.viewing` convention mirrored on the map: a
   highlight ring with no fill change ("you are peeking at this one"). Drawn as
   a shadow so the dot's box is untouched and the expanded ring/portrait
   geometry (`--dot-r`) stays exact. */
.occ-dot.viewed {
  box-shadow: 0 0 0 2px var(--accent), 0 0 12px rgba(64,136,212,0.5);
}
.occ-dot.viewed.expanded {
  box-shadow: 0 0 0 2px var(--accent), inset 0 0 20px rgba(0,0,0,0.6), inset 0 0 4px rgba(255,255,255,0.1);
}
.dot-overlay {
  position: absolute; inset: 0; border-radius: 50%;
  opacity: 0; transition: opacity 0.2s ease;
  cursor: pointer; pointer-events: none;
}
/* "Hole" destination preview: an overscan-sized <img> positioned by the parent
   (cancel scene pan + align arrival point + inverse parallax), clipped by the
   dot's border-radius + overflow. Replaces background-attachment: fixed.
   No border-radius of its own — 50% on an oversized box would clip the image
   to an inscribed ellipse whose edge cuts through the hole near screen corners. */
.dot-hole {
  position: absolute;
  left: 50%; top: 50%;
  border-radius: 0;
  will-change: transform;
}
.map-dot.expanded .dot-overlay { opacity: 1; pointer-events: auto; }
.occ-img-overlay { border-radius: 50%; }
.dot-label, .dot-initials {
  position: absolute; inset: 0;
  display: flex; align-items: center; justify-content: center;
  opacity: 0; transition: opacity 0.2s ease; cursor: pointer;
}
.map-dot.expanded .dot-label, .map-dot.expanded .dot-initials { opacity: 1; }
.dot-label { font-size: 11px; font-weight: 600; color: var(--map-text); text-align: center; padding: 4px; line-height: 1.2; }
.dot-initials { font-size: 18px; font-weight: 800; color: #fff; }
.map-dot.draggable { cursor: grab; border: 2px dashed var(--map-accent); animation: dot-pulse 2s ease-in-out infinite; }
.zone-dot.draggable { width: 240px !important; height: 240px !important; margin-left: -120px; margin-top: -120px; background: rgba(10,10,20,0.85); z-index: 10; overflow: hidden; }
.nav-dot.draggable { width: 240px !important; height: 240px !important; margin-left: -120px; margin-top: -120px; background: rgba(10,10,20,0.85); z-index: 10; overflow: hidden; }
.map-dot.draggable .dot-overlay, .map-dot.draggable .dot-label, .map-dot.draggable .dot-initials { opacity: 1; }
@keyframes dot-pulse {
  0%, 100% { border-color: var(--map-accent); }
  50% { border-color: rgba(64,136,212,0.3); }
}

/* Travel-armed: the bubble breathes so a drop here will travel */
.map-dot.armed {
  animation: armed-breathe 1.1s ease-in-out infinite;
}
@keyframes armed-breathe {
  0%, 100% { box-shadow: 0 0 0 3px rgba(120,220,255,0.9), 0 0 18px rgba(120,220,255,0.55), 0 0 40px rgba(120,220,255,0.3); }
  50%      { box-shadow: 0 0 0 9px rgba(120,220,255,0.55), 0 0 34px rgba(120,220,255,0.9), 0 0 70px rgba(120,220,255,0.5); }
}

/* GM-only draft (unpublished) entity marker */
.map-dot.dot-draft {
  opacity: 0.55;
  outline: 2px dashed rgba(255,255,255,0.6);
  outline-offset: 3px;
}

/* Transparent (background-removed) occupant portraits: floating cutout
   emerging from a "portal ring". The circle's bottom crops the image (same
   radius + bottom border as the ring), the top stays open so a tall
   portrait's head sticks out above the rim. */
.map-dot.dot-transparent {
  background: transparent !important;  /* no fill — beats draggable/expanded bubble bg */
  box-shadow: none;
  border: 2px solid rgba(255,255,255,0.4) !important;
  overflow: visible !important;  /* the cutout's top may stick out above the ring */
}
.dot-overlay.img-transparent {
  border-radius: 0 0 var(--dot-r, 44px) var(--dot-r, 44px);
  border-bottom: 2px solid rgba(255,255,255,0.4);
  object-fit: contain;
  top: auto;
  right: auto;
  left: 50%;
  bottom: 0;
  width: 100%;
  height: auto;
  transform: translateX(-50%);
}
</style>
