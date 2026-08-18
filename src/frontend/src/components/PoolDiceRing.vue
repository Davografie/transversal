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

    <!-- Resolved: total badge above, effect dice below -->
    <template v-if="phase === 'resolved' && resolved">
      <span
        class="resolved-total"
        :style="{ transform: 'translate(-50%, ' + (-radiusPx - 16) + 'px)' }"
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
})

// Radius in pixels from dot center — keeps dice equidistant regardless of viewport shape
const radiusPx = 44

function radialOffset(index, total, radius, startAngle) {
  const angle = (2 * Math.PI / total) * index + startAngle
  return {
    tx: radius * Math.cos(angle),
    ty: radius * Math.sin(angle),
  }
}

const positionedDice = computed(() => {
  const n = props.dice.length
  if (n === 0) return []
  return props.dice.map((d, i) => {
    const off = radialOffset(i, n, radiusPx, -Math.PI / 2)
    return { ...off, die: d }
  })
})

const positionedEffectDice = computed(() => {
  const effectDice = props.resolved?.effect_dice || []
  if (props.resolved?.effect_die && effectDice.length === 0) {
    effectDice.push({ die: props.resolved.effect_die, result: props.resolved.effect_die_value })
  }
  const n = effectDice.length
  if (n === 0) return []
  return effectDice.map((ed, i) => {
    const off = radialOffset(i, n, radiusPx, Math.PI / 2)
    return { ...off, die: ed.die, result: ed.result }
  })
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
