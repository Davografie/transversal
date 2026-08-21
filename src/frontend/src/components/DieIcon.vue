<template>
  <svg class="die-icon" :class="[`die-${die}`, { hitch: isHitch }]" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 52">
    <!-- d4: triangle -->
    <polygon v-if="die === 'd4'" class="die-shape" points="3,46 24,3 45,46" />

    <!-- d6: square -->
    <rect v-if="die === 'd6'" class="die-shape" x="3" y="3" width="42" height="42" rx="4" />

    <!-- d8: diamond -->
    <polygon v-if="die === 'd8'" class="die-shape" points="45,36 45,13 24,2 3,13 3,36 24,47" />

    <!-- d10: teardrop/kite -->
    <path v-if="die === 'd10'" class="die-shape" d="M45,18 L24,2 L3,17 L2,27 C2,27 23,47 23,47 L45,28 Z" />

    <!-- d12: pentagon-ish -->
    <polygon v-if="die === 'd12'" class="die-shape" points="37,44 23,48 9,43 1,31 2,17 10,5 24,2 38,6 46,18 45,32" />

    <text class="die-text" text-anchor="middle" dominant-baseline="central" x="24" y="26">
      {{ display }}
    </text>
  </svg>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  die: { type: String, required: true },   // d4, d6, d8, d10, d12
  label: { type: String, default: '' },     // rating text, e.g., "d8", "4d4"
  result: { type: Number, default: null },  // rolled value
  isHitch: { type: Boolean, default: false },
})

const display = computed(() => {
  if (props.isHitch) return '!'
  if (props.result !== null) return String(props.result)
  return props.label || props.die
})
</script>

<style scoped>
.die-icon {
  width: 36px;
  height: 40px;
  display: block;
  filter: drop-shadow(0 1px 2px rgba(0,0,0,0.3));
  pointer-events: none;  /* let parent handle drag/click */
}
.die-shape {
  fill: #14142a;
  stroke: #2a2a4a;
  stroke-width: 1.5;
}
.die-icon.die-d4 .die-shape  { fill: var(--die-d4); stroke: var(--die-d4); }
.die-icon.die-d6 .die-shape  { fill: var(--die-d6); stroke: var(--die-d6); }
.die-icon.die-d8 .die-shape  { fill: var(--die-d8); stroke: var(--die-d8); }
.die-icon.die-d10 .die-shape { fill: var(--die-d10); stroke: var(--die-d10); }
.die-icon.die-d12 .die-shape { fill: var(--die-d12); stroke: var(--die-d12); }

.die-icon.hitch .die-shape {
  fill: rgba(212,64,64,0.4);
  stroke: rgba(212,64,64,0.5);
}

.die-text {
  fill: #ffffff;
  font-size: 16px;
  font-weight: 800;
  font-family: 'Segoe UI', system-ui, sans-serif;
  pointer-events: none;
  user-select: none;
  paint-order: stroke;
  stroke: rgba(0,0,0,0.85);
  stroke-width: 3px;
  stroke-linecap: round;
  stroke-linejoin: round;
}
.die-icon.hitch .die-text {
  fill: #ffffff;
}
</style>
