<template>
  <div
    v-if="dice.length > 0 || (phase === 'resolved' && resolved)"
    class="pool-dice-container"
    :style="{ left: cx.toFixed(1) + '%', top: cy.toFixed(1) + '%' }"
  >
    <!-- Adding / Picking: radial die icons -->
    <span
      v-for="(d, i) in positionedDice"
      :key="i"
      class="pool-die-item"
      :style="{ transform: 'translate(' + d.tx.toFixed(0) + 'px, ' + d.ty.toFixed(0) + 'px)' }"
    >
      <!-- Adding: d is a die-type string like "d8" -->
      <DieIcon
        v-if="phase === 'adding'"
        :die="d.die"
        :result="null"
      />
      <!-- Picking: d is { die, result, source } — no kept/unused dimming for remote view -->
      <DieIcon
        v-else-if="phase === 'picking'"
        :die="d.die.die || d.die"
        :result="d.die.result != null ? d.die.result : d.result"
      />
    </span>

    <!-- Resolved: total badge above, effect dice below (below the ring when the
         portrait overflows the top) -->
    <template v-if="phase === 'resolved' && resolved">
      <span
        class="resolved-total"
        :style="{ transform: 'translate(-50%, ' + totalOffsetY + 'px)' }"
      >{{ resolved.total }}</span>
      <span
        v-for="(ed, i) in positionedEffectDice"
        :key="'eff-' + i"
        class="pool-die-item"
        :style="{ transform: 'translate(' + ed.tx.toFixed(0) + 'px, ' + ed.ty.toFixed(0) + 'px)' }"
      >
        <DieIcon :die="ed.die" :result="ed.result" class="effect-die" />
      </span>
    </template>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import DieIcon from './DieIcon.vue'

const props = defineProps({
  dice: { type: Array, default: () => [] },
  phase: { type: String, default: 'adding' },
  cx: { type: Number, required: true },
  cy: { type: Number, required: true },
  resolved: { type: Object, default: null },
  scale: { type: Number, default: 1 },        // the dot's own scale (controlled dots are bigger)
  transparent: { type: Boolean, default: false },  // portrait overflows the top of the rim
})

// Radius in pixels from the dot center — keeps dice equidistant regardless of
// viewport shape. Scaled with the dot so a sized-up dot keeps its ring outside
// the rim instead of inside the portrait.
const BASE_RADIUS_PX = 44
// Fraction of the circle a transparent portrait may overflow into (its head).
// Dice never enter this slice: they are spread over the rest of the arc.
const TOP_GAP_FRACTION = 0.2

const radiusPx = computed(() => BASE_RADIUS_PX * (props.scale || 1))

function radialOffset(index, total, radius, startAngle) {
  const angle = (2 * Math.PI / total) * index + startAngle
  return {
    tx: radius * Math.cos(angle),
    ty: radius * Math.sin(angle),
  }
}

// Transparent portraits stick out above the rim, so their dice are anchored on
// the bottom (6 o'clock — +π/2 in screen coords) and spread upward to both
// sides, filling the arc outside the reserved top slice.
function radialOffsetBottomAnchored(index, total, radius) {
  const span = 2 * Math.PI * (1 - TOP_GAP_FRACTION)
  const angle = (Math.PI / 2) - span / 2 + (span / total) * (index + 0.5)
  return {
    tx: radius * Math.cos(angle),
    ty: radius * Math.sin(angle),
  }
}

// `items` are per-die payloads; each gets the offset for its place in the ring.
function distribute(items, startAngle) {
  const n = items.length
  if (n === 0) return []
  return items.map((item, i) => {
    const off = props.transparent
      ? radialOffsetBottomAnchored(i, n, radiusPx.value)
      : radialOffset(i, n, radiusPx.value, startAngle)
    return { ...item, ...off }
  })
}

// The resolved total sits outside the ring: above it normally, below it when the
// portrait overflows the top.
const totalOffsetY = computed(() =>
  props.transparent ? radiusPx.value + 16 : -radiusPx.value - 16
)

const positionedDice = computed(() =>
  distribute(props.dice.map(d => ({ die: d })), -Math.PI / 2)
)

const positionedEffectDice = computed(() => {
  const resolved = props.resolved
  // Copy — never push into a prop's array.
  const effectDice = resolved?.effect_dice ? [...resolved.effect_dice] : []
  if (resolved?.effect_die && effectDice.length === 0) {
    effectDice.push({ die: resolved.effect_die, result: resolved.effect_die_value })
  }
  return distribute(
    effectDice.map(ed => ({ die: ed.die, result: ed.result })),
    Math.PI / 2,
  )
})
</script>

<style scoped>
.pool-dice-container {
  position: absolute;
  z-index: 22;
  pointer-events: none;
  transform: translate(-50%, -50%);
}
.pool-die-item {
  position: absolute;
  pointer-events: none;
  /* DieIcon is 36×40 — neg margin centers it on the transform origin */
  margin-left: -18px;
  margin-top: -20px;
  transform-origin: 0 0;
}
.resolved-total {
  position: absolute;
  z-index: 23;
  color: #fff;
  font-size: 1.5rem;
  font-weight: 800;
  text-shadow:
    0 0 4px rgba(0,0,0,0.9),
    0 0 8px rgba(0,0,0,0.7),
    0 1px 2px rgba(0,0,0,0.8);
  pointer-events: none;
  white-space: nowrap;
}
.kept-die {
  filter: brightness(1.25);
}
.unused-die {
  opacity: 0.45;
}
.effect-die {
  filter: drop-shadow(0 0 3px rgba(255,255,255,0.4));
}
</style>
