<template>
  <template v-if="dice.length > 0 || (phase === 'resolved' && resolved)">
    <span
      v-for="(d, i) in positionedDice"
      :key="i"
      class="pool-die-ring-item"
      :style="{ left: d.x.toFixed(1) + '%', top: d.y.toFixed(1) + '%' }"
    >
      <span class="die-icon-wrap">
        <DieIcon
          v-if="phase === 'adding'"
          :die="typeof d.die === 'string' ? d.die : d.die.die || d.die"
          :result="null"
        />
        <DieIcon
          v-else-if="phase === 'picking'"
          :die="d.die.die || d.die"
          :result="d.die.result"
          :class="{ 'kept-die': d.die.kept, 'unused-die': !d.die.kept }"
        />
      </span>
    </span>
    <!-- Resolved: total + effect die(s) -->
    <template v-if="phase === 'resolved' && resolved">
      <span class="pool-die-ring-item resolved-total" :style="{ left: resolvedTotalX.toFixed(1) + '%', top: resolvedTotalY.toFixed(1) + '%' }">
        <span class="total-label">{{ resolved.total }}</span>
      </span>
      <span
        v-for="(ed, i) in positionedEffectDice"
        :key="'eff-' + i"
        class="pool-die-ring-item"
        :style="{ left: ed.x.toFixed(1) + '%', top: ed.y.toFixed(1) + '%' }"
      >
        <span class="die-icon-wrap"><DieIcon :die="ed.die" :result="ed.result" class="effect-die" /></span>
      </span>
    </template>
  </template>
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

const RADIUS = 8  // percentage units from dot center

function radialPosition(index, total, radius, cx, cy, startAngle) {
  const angle = (2 * Math.PI / total) * index + startAngle
  return {
    x: cx + radius * Math.cos(angle),
    y: cy + radius * Math.sin(angle),
  }
}

const positionedDice = computed(() => {
  const n = props.dice.length
  if (n === 0) return []
  return props.dice.map((d, i) => {
    const pos = radialPosition(i, n, RADIUS, props.cx, props.cy, -Math.PI / 2)
    return { ...pos, die: d }
  })
})

// Resolved phase: total at top, effect dice at bottom
const resolvedTotalX = computed(() => props.cx)
const resolvedTotalY = computed(() => props.cy - RADIUS)

const positionedEffectDice = computed(() => {
  const effectDice = props.resolved?.effect_dice || []
  if (props.resolved?.effect_die && effectDice.length === 0) {
    effectDice.push({ die: props.resolved.effect_die, result: props.resolved.effect_die_value })
  }
  const n = effectDice.length
  if (n === 0) return []
  return effectDice.map((ed, i) => {
    const pos = radialPosition(i, n, RADIUS, props.cx, props.cy + RADIUS, Math.PI / 2)
    return { ...pos, die: ed.die, result: ed.result }
  })
})
</script>

<style>
.pool-die-ring-item {
  position: absolute;
  z-index: 22;
  pointer-events: none;
  transform: translate(-50%, -50%);
}
.die-icon-wrap {
  display: block;
  transform: scale(0.6);
  transform-origin: center;
}
.resolved-total {
  z-index: 23;
  background: rgba(30,30,30,0.85);
  color: #fff;
  font-size: 0.75rem;
  font-weight: 800;
  min-width: 20px;
  height: 20px;
  line-height: 20px;
  text-align: center;
  border-radius: 10px;
  padding: 0 5px;
  box-shadow: 0 0 6px rgba(0,0,0,0.5);
}
.kept-die {
  filter: brightness(1.2);
}
.unused-die {
  opacity: 0.5;
}
.effect-die {
  filter: drop-shadow(0 0 3px rgba(255,255,255,0.4));
}
</style>
