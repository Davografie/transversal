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
      :class="{ 'occ-img-overlay': type === 'occupant' || type === 'self' }"
      style="object-fit: cover; width: 100%; height: 100%; border-radius: 50%;"
      autoplay loop muted playsinline
      @click.stop="onOverlayClick"
    />
    <div
      v-else-if="image && overlayVisible"
      class="dot-overlay"
      :class="{ 'occ-img-overlay': type === 'occupant' || type === 'self' }"
      :style="{ backgroundImage: 'url(' + image + ')', ...(overlayBgStyle || {}) }"
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
import { isVideoUrl, panAxis } from '@/composables/media.js'

const props = defineProps({
  type: { type: String, required: true },
  variant: { type: String, default: '' },
  image: { type: String, default: null },
  label: { type: String, default: '' },
  initials: { type: String, default: '' },
  x: { type: Number, required: true },
  y: { type: Number, required: true },
  expanded: { type: Boolean, default: false },
  draggable: { type: Boolean, default: false },
  lerping: { type: Boolean, default: false },
  title: { type: String, default: '' },
  arrivalX: { type: Number, default: null },
  arrivalY: { type: Number, default: null },
  destAspect: { type: Number, default: null },
  panX: { type: Number, default: 0 },
  panY: { type: Number, default: 0 },
})

const emit = defineEmits(['click', 'overlay-click', 'drag-start'])

const isVideoImage = computed(() => isVideoUrl(props.image))

const dotClasses = computed(() => [
  props.type === 'zone' ? 'zone-dot' : '',
  props.type === 'occupant' ? 'occ-dot' : '',
  props.type === 'nav' ? 'nav-dot' : '',
  props.type === 'self' ? 'occ-dot self' : '',
  props.variant ? `occ-${props.variant}` : '',
  props.variant && props.type === 'nav' ? `nav-${props.variant}` : '',
  { expanded: props.expanded, draggable: props.draggable, lerping: props.lerping },
].filter(Boolean))

const dotStyle = computed(() => ({
  left: props.x.toFixed(1) + '%',
  top: props.y.toFixed(1) + '%',
}))

const overlayVisible = computed(() => props.expanded || props.type === 'self' || props.type === 'occupant')

const overlayBgStyle = computed(() => {
  if (props.arrivalX == null || props.arrivalY == null || props.destAspect == null) return null
  const viewAspect = window.innerWidth / window.innerHeight
  const axis = panAxis(props.destAspect, viewAspect)
  if (axis === 'x') return { backgroundPosition: `${props.arrivalX + props.panX}% 50%` }
  if (axis === 'y') return { backgroundPosition: `50% ${props.arrivalY + props.panY}%` }
  return null
})

function onClick() { emit('click', { type: props.type, x: props.x, y: props.y }) }
function onOverlayClick() { emit('overlay-click', { type: props.type, x: props.x, y: props.y }) }
function onDragStart(e) { if (props.draggable) emit('drag-start', e) }
</script>

<style>
.map-dot {
  position: absolute;
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
  width: clamp(120px, 14vw, 260px) !important; height: clamp(120px, 14vw, 260px) !important;
  margin-left: calc(clamp(120px, 14vw, 260px) / -2); margin-top: calc(clamp(120px, 14vw, 260px) / -2);
  background: rgba(10,10,20,0.85); backdrop-filter: blur(8px); border: none;
  box-shadow: inset 0 0 20px rgba(0,0,0,0.6), inset 0 0 4px rgba(255,255,255,0.1);
  z-index: 10; overflow: hidden;
}
.map-dot.expanded {
  width: clamp(120px, 14vw, 260px) !important; height: clamp(120px, 14vw, 260px) !important;
  margin-left: calc(clamp(120px, 14vw, 260px) / -2); margin-top: calc(clamp(120px, 14vw, 260px) / -2);
  background: rgba(10,10,20,0.85); backdrop-filter: blur(8px); border: none;
  box-shadow: inset 0 0 20px rgba(0,0,0,0.6), inset 0 0 4px rgba(255,255,255,0.1);
  z-index: 10; overflow: hidden;
}
.occ-dot.expanded {
  width: clamp(60px, 5.5vw, 88px) !important; height: clamp(60px, 5.5vw, 88px) !important;
  margin-left: calc(clamp(60px, 5.5vw, 88px) / -2); margin-top: calc(clamp(60px, 5.5vw, 88px) / -2);
}
.dot-overlay {
  position: absolute; inset: 0; border-radius: 50%;
  background-size: cover; background-position: center;
  opacity: 0; transition: opacity 0.2s ease;
  cursor: pointer; pointer-events: none;
}
.map-dot.expanded .dot-overlay { opacity: 1; pointer-events: auto; }
.zone-dot .dot-overlay, .nav-dot .dot-overlay { background-attachment: fixed; }
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
.zone-dot.draggable { width: 240px !important; height: 240px !important; margin-left: -120px; margin-top: -120px; background: rgba(10,10,20,0.85); backdrop-filter: blur(8px); z-index: 10; overflow: hidden; }
.occ-dot.draggable:not(.self) { width: 96px !important; height: 96px !important; margin-left: -48px; margin-top: -48px; background: rgba(10,10,20,0.85); backdrop-filter: blur(8px); z-index: 10; overflow: hidden; }
.nav-dot.draggable { width: 240px !important; height: 240px !important; margin-left: -120px; margin-top: -120px; background: rgba(10,10,20,0.85); backdrop-filter: blur(8px); z-index: 10; overflow: hidden; }
.map-dot.draggable .dot-overlay, .map-dot.draggable .dot-label, .map-dot.draggable .dot-initials { opacity: 1; }
@keyframes dot-pulse {
  0%, 100% { border-color: var(--map-accent); }
  50% { border-color: rgba(64,136,212,0.3); }
}

/* GM-only draft (unpublished) entity marker */
.map-dot.dot-draft {
  opacity: 0.55;
  outline: 2px dashed rgba(255,255,255,0.6);
  outline-offset: 3px;
}
</style>
