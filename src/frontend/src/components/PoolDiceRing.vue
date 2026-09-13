<template>
  <div
    v-if="positionedDice.length > 0 || (phase === 'resolved' && resolved)"
    class="pool-dice-container"
    :style="{ left: cx.toFixed(1) + '%', top: cy.toFixed(1) + '%' }"
  >
    <!-- Adding / rolling / picking / resolved: the dice themselves. Faces are the
         rolled results when we have them, a tumbling random face while a roll is
         in flight, and blank otherwise. -->
    <span
      v-for="(d, i) in positionedDice"
      :key="i"
      class="pool-die-item"
      :class="{ tumbling: tumbleActive, locked: d.locked }"
      :style="{ transform: 'translate(' + d.tx.toFixed(0) + 'px, ' + d.ty.toFixed(0) + 'px)' }"
    >
      <DieIcon :die="d.die" :result="d.face" />
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
import { computed, onUnmounted, ref, watch } from 'vue'
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

// ── What the ring shows ────────────────────────────────────────────────────
// Same timings as the roller: it tumbles a face every 70ms and locks its dice
// left-to-right so the numbers fall into place.
const TUMBLE_MS = 70
const FIRST_LOCK_MS = 900
const LOCK_STAGGER_MS = 1000

// Rolled results win over the specs they came from: once we have them, the ring
// shows the numbers that landed, in every phase after the roll.
const rolledDice = computed(() => {
  const rolls = props.resolved?.rolls || []
  return rolls.length ? rolls.map(r => ({ die: r.die, result: r.result ?? null })) : []
})

// Otherwise the pool's own dice: strings in `adding`, result objects in `picking`.
const specDice = computed(() => props.dice.map((d) => {
  if (typeof d === 'string') return { die: d, result: null }
  const die = d.die?.die ?? d.die
  return { die, result: d.result ?? null }
}))

const baseDice = computed(() => (rolledDice.value.length ? rolledDice.value : specDice.value))

// How many rolled dice have visibly settled. Staggered, so the ring reads like
// the panel rather than flipping every number in one frame.
const revealedCount = ref(0)
let lockTimers = []

function clearLockTimers() {
  for (const t of lockTimers) clearTimeout(t)
  lockTimers = []
}

// Restart the sequence whenever a fresh set of results lands (and drop it when
// there are none — e.g. the pool was cleared and the phase went back to adding).
watch(() => rolledDice.value.length, (n) => {
  clearLockTimers()
  revealedCount.value = 0
  for (let i = 0; i < n; i++) {
    lockTimers.push(setTimeout(() => {
      revealedCount.value = Math.max(revealedCount.value, i + 1)
    }, FIRST_LOCK_MS + i * LOCK_STAGGER_MS))
  }
}, { immediate: true })

// Tumbling covers both halves: the roll in flight (no results yet), and the
// staggered reveal while the numbers fall into place one by one.
const tumbleActive = computed(() => {
  if (rolledDice.value.length) return revealedCount.value < rolledDice.value.length
  return props.phase === 'rolling' && baseDice.value.length > 0
})
const tumbleFaces = ref([])
let tumbleTimer = null

function rollFace(die) {
  const sides = Number(String(die).replace(/^d/, '')) || 6
  return Math.floor(Math.random() * sides) + 1
}

watch(tumbleActive, (on) => {
  if (tumbleTimer) { clearInterval(tumbleTimer); tumbleTimer = null }
  if (!on) { tumbleFaces.value = []; return }
  tumbleFaces.value = baseDice.value.map(d => rollFace(d.die))
  tumbleTimer = setInterval(() => {
    tumbleFaces.value = baseDice.value.map(d => rollFace(d.die))
  }, TUMBLE_MS)
}, { immediate: true })

onUnmounted(() => {
  if (tumbleTimer) clearInterval(tumbleTimer)
  clearLockTimers()
})

const shownDice = computed(() => baseDice.value.map((d, i) => {
  const settled = d.result != null && i < revealedCount.value
  return {
    ...d,
    face: settled ? d.result : (tumbleActive.value ? (tumbleFaces.value[i] ?? null) : null),
    locked: settled,
  }
}))

const positionedDice = computed(() =>
  distribute(shownDice.value, -Math.PI / 2)
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

// The resolved total sits outside the ring: above it normally, below it when the
// portrait overflows the top.
const totalOffsetY = computed(() =>
  props.transparent ? radiusPx.value + 16 : -radiusPx.value - 16
)
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
/* Roll animation, mirroring DiceRoller's (roll-pop when the dice appear, die-lock
   as each face settles, one per LOCK_STAGGER_MS). Animated with the *scale*
   property, never `transform`: each item's inline transform is what places it on
   the ring, and an animation on `transform` would override it and stack every die
   at the centre. */
.pool-die-item.tumbling { animation: ringRollPop 0.09s ease-in-out; }
.pool-die-item.locked { animation: ringDieLock 0.2s ease-out; }
@keyframes ringRollPop {
  0% { scale: 0.92; }
  50% { scale: 1.04; }
  100% { scale: 1; }
}
@keyframes ringDieLock {
  0% { scale: 1.18; }
  100% { scale: 1; }
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
