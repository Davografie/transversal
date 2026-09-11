<template>
  <div
    v-for="r in RINGS"
    :key="r.key"
    class="arrival-ring"
    :class="r.class"
    :style="{ left: x + '%', top: y + '%' }"
  />
</template>

<script setup>
// The three-phase arrival animation that plays where the self dot lands:
// an inward ripple, a portal flash, then a triple burst. Purely decorative —
// the parent decides when it is visible (not travelling, elements shown, self
// shown) and where it sits.
defineProps({
  x: { type: Number, default: 50 },
  y: { type: Number, default: 50 },
})

const RINGS = [
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
</script>

<style scoped>
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

</style>
