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
         the wipe and the background it hands over to are the same box. An
         animated destination needs a real <video>: an <img>/background-image
         cannot decode a .webm, which left the wipe blank (and black on the
         swap) for every animated location. -->
    <video
      v-if="scene && isVideo"
      class="travel-scene"
      :src="image"
      :style="sceneStyle"
      autoplay loop muted playsinline
    />
    <img
      v-else-if="scene"
      class="travel-scene"
      :src="image"
      :style="sceneStyle"
      alt=""
      draggable="false"
    />
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { isVideoUrl } from '@/composables/media.js'

// The portal-expand wipe played while travelling: the destination image opens
// from a circle at the origin point (the two custom properties), fixed over the
// whole viewport. Mounted only while `travelAnim.active`.
const props = defineProps({
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

const isVideo = computed(() => isVideoUrl(props.image))

const sceneStyle = computed(() => ({
  width: props.scene.w + 'px',
  height: props.scene.h + 'px',
  transform: 'translate3d(' + (-props.scene.panX) + 'px, ' + (-props.scene.panY) + 'px, 0)',
}))
</script>

<style scoped>
/* The portal-expand wipe sits in the MAP's box, never the viewport's.
 *
 * This must be `absolute`, not `fixed`. `fixed` resolves against the viewport,
 * but every percentage fed to `--travel-x`/`--travel-y` — and the destination
 * scene box, sized from the viewer's `cw`/`ch` — is measured against the *viewer*.
 * The two agree only while the viewer happens to be the whole viewport, and the
 * B169 dock broke that: `.stage.dock-sheet .location-viewer { left: var(--dock-w) }`
 * offsets the map by 400px, so a viewport-wide wipe opened the portal exactly one
 * dock width away from the dot that was clicked (measured in the browser: 400px
 * off, with the destination scene parked at the viewport's left edge). The mobile
 * stack breaks the same thing on the other axis: there the viewer is an `absolute`
 * band, so a fixed wipe also took its percentages from the wrong box height.
 *
 * `.location-viewer` is positioned in every layout — `fixed` by default,
 * `absolute` in the mobile stack, `fixed` + `left` when docked — and this overlay
 * is its child, so `absolute; inset: 0` fills exactly the box the viewer measured
 * in all of them, and the viewer's own `overflow: hidden` clips the wipe to the map.
 */
.travel-overlay {
  position: absolute; inset: 0; z-index: 50;
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
