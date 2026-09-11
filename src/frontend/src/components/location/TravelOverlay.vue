<template>
  <div
    class="travel-overlay"
    :style="{
      '--travel-x': x + '%',
      '--travel-y': y + '%',
      backgroundImage: 'url(' + image + ')',
      backgroundPosition: (bgX || 50) + '% ' + (bgY || 50) + '%',
    }"
  />
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
})
</script>

<style scoped>
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

</style>
