<template>
  <div
    class="travel-overlay"
    :style="{
      '--travel-x': x + '%',
      '--travel-y': y + '%',
      ...(scene ? {} : {
        backgroundImage: 'url(' + image + ')',
        backgroundPosition: (bgX || 50) + '% ' + (bgY || 50) + '%',
      }),
    }"
  >
    <!-- Sized as the destination's own scene layer (cover + overscan + zoom), so
         the wipe and the background it hands over to are the same box. -->
    <img
      v-if="scene"
      class="travel-scene"
      :src="image"
      :style="{
        width: scene.w + 'px',
        height: scene.h + 'px',
        transform: 'translate3d(' + (-scene.panX) + 'px, ' + (-scene.panY) + 'px, 0)',
      }"
      alt=""
      draggable="false"
    />
  </div>
</template>

<script setup>
// The portal-expand wipe played while travelling: the destination image opens
// from a circle at the origin point (the two custom properties), fixed over the
// whole viewport. Mounted only while `travelAnim.active`.
defineProps({
  x: { type: Number, default: 50 },
  y: { type: Number, default: 50 },
  image: { type: String, default: '' },
  bgX: { type: Number, default: 50 },
  bgY: { type: Number, default: 50 },
  // Destination scene-layer box ({ w, h, panX, panY }) from the viewer, or null
  // when the destination's aspect is unknown — then the CSS `cover` background
  // below is the fallback.
  scene: { type: Object, default: null },
})
</script>

<style scoped>
/* ── Travel expansion animation ──────────────────── */

.travel-overlay {
  position: fixed; inset: 0; z-index: 50;
  background-size: cover;
  background-position: center;
  overflow: hidden;
  clip-path: circle(clamp(40px, 5vw, 120px) at var(--travel-x, 50%) var(--travel-y, 50%));
  animation: portal-expand 1.2s ease-out forwards;
  pointer-events: none;
  opacity: 1;
}

.travel-scene {
  position: absolute; top: 0; left: 0;
  object-fit: cover;
}

@keyframes portal-expand {
  0% {
    clip-path: circle(clamp(40px, 5vw, 120px) at var(--travel-x, 50%) var(--travel-y, 50%));
  }
  100% {
    clip-path: circle(150vmax at var(--travel-x, 50%) var(--travel-y, 50%));
  }
}

</style>
