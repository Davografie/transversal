<template>
  <div class="ct-root" :class="[`ct-${density}`, { 'ct-stagger': stagger }]">
    <slot name="caption" />

    <div v-if="loading && !rows.length" class="ct-state">Loading…</div>
    <div v-else-if="!rows.length" class="ct-state">{{ emptyText }}</div>

    <template v-else>
      <div class="ct-scroll" :style="maxHeight ? { maxHeight, overflowY: 'auto' } : null">
        <!-- The column head is a legend, not a control: it is hidden once the
             surface has collapsed to stacked rows, so it never labels a layout
             the reader cannot see. -->
        <div v-if="headerOn" class="ct-head" aria-hidden="true">
          <span class="ct-head-cell ct-head-result">Result</span>
          <span v-if="showKey" class="ct-head-cell ct-head-key">{{ keyHeader }}</span>
          <span class="ct-head-cell ct-head-cost">{{ costHeader }}</span>
        </div>

        <div class="ct-rows" role="list">
          <button
            v-for="(r, i) in rows"
            :key="r.id ?? i"
            type="button"
            role="listitem"
            class="ct-row"
            :class="[toneOf(r), stateOf(r), {
              'is-rolled': rolled === i,
              'is-landing': landing === i,
              'is-locked': isLocked(r),
            }]"
            :style="{ '--i': i }"
            :disabled="isLocked(r) || busy"
            :aria-current="rolled === i ? 'true' : undefined"
            @click="onRow(r, i)"
          >
            <slot name="row" :row="r" :index="i" :rolled="rolled === i">
              <span class="ct-cell-main">
                <!-- The key is a **corner chip inside the content**, not a column
                     of its own: at the dock's ~290px the old left key column
                     collapsed to a full line above every row (18px + a 10px grid
                     gap on each), and the row is the thing being read. Floated
                     right, it shares the label's first line and the text flows
                     under it — so the key costs a line only when the row is one
                     line tall. See [[UI-UX Design#Choice table]]. -->
                <span v-if="showKey" class="ct-cell-key">
                  <span class="ct-pip">{{ keyOf(r, i) }}</span>
                </span>
                <span class="ct-label">{{ r.label }}</span>
                <span v-if="r.description" class="ct-desc">{{ r.description }}</span>
                <span v-if="conditionLines(r).length" class="ct-conds">
                  <span v-for="(c, ci) in conditionLines(r)" :key="ci" class="ct-cond">if {{ c }}</span>
                </span>
                <span v-if="effectLines(r).length" class="ct-effects">
                  <span v-for="(e, ei) in effectLines(r)" :key="ei" class="ct-effect">{{ e }}</span>
                </span>
                <span v-if="isLocked(r) && whyOf(r)" class="ct-why">🔒 {{ whyOf(r) }}</span>
              </span>
              <span class="ct-cell-cost">
                <span v-if="costOf(r).label" class="ct-cost" :class="{ 'is-free': costOf(r).free }">{{ costOf(r).label }}</span>
                <span v-else-if="r.hint" class="ct-hint">{{ r.hint }}</span>
              </span>
            </slot>
          </button>
        </div>
      </div>

      <div class="ct-actions">
        <!-- The 🎲 *finds* a row and marks it; it never takes it. Taking is the
             click, on that row or on any other — which is why there is no
             confirm button anywhere in this surface. -->
        <Button
          v-if="allowRandom"
          variant="neutral"
          size="sm"
          title="Find one at random"
          :disabled="busy"
          @click="pickRandom"
        >🎲 {{ randomLabel }}</Button>
        <Button v-if="showCancel" variant="neutral" size="sm" :disabled="busy" @click="$emit('close')">{{ cancelLabel }}</Button>
        <!-- Flow chrome belongs to the driver: a step that can be left by name
             (the life path's `↩ Paths`) puts its own exit here rather than
             making the surface know what `Back` means. -->
        <slot name="actions" />
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import Button from './Button.vue'
import { useLabelResolver } from '@/composables/useLabelResolver.js'
import { conditionSummary, costSummary, effectSummary, entryKey } from '@/utils/rowSummary.js'

// The choice table: one presentational surface for every "here are things you
// may take" list — a played roll table, a life-path step, a character-creation
// archetype list, a consequence menu, a hitch menu, an availability list.
//
// It renders *what a row is* and reports *what was chosen*; it resolves nothing.
// The three acts it refuses to conflate (see [[UI-UX Design#Choice table]]):
//
//   a roll and a pick   — **a roll finds a row, a click takes it.** The roll
//                         (the 🎲 here, or the dice roller's own roll reported
//                         through `rolledIndex`) only *marks* a row; picking is
//                         always the click, on that row or on another. There is
//                         deliberately no confirm button: a marked row that needs
//                         a second press to take is a step with nothing in it.
//   a row and a flow    — position, `Back` and named exits belong to the driver
//   cost and benefit    — the cost cell is always shown, never merged into the label
//
// A row is:
//   { id?, key?, label, description?, cost?, costEffects?, costFree?, hint?,
//     tone?, state?, why?, disabled?, locked?, conditions?, effects?,
//     minValue?, maxValue?, weight?, tier? }
//
// `conditions` / `effects` are the domain objects; the surface phrases them
// through the shared resolver (`useLabelResolver`), so no host carries a name
// map and no id can leak raw into a row. A host with pre-phrased text passes
// `conditionLines` / `effectLines` / `cost` instead, which is what the compact
// menus do.
const props = defineProps({
  rows: { type: Array, default: () => [] },
  /** The table's scheme — it, not the row, decides what the key cell means. */
  scheme: { type: String, default: '' },
  /** 'comfortable' (a surface) | 'compact' (a small panel: the roller's menus). */
  density: { type: String, default: 'comfortable' },
  loading: { type: Boolean, default: false },
  /** While a host is applying a pick, the whole list is inert. */
  busy: { type: Boolean, default: false },
  emptyText: { type: String, default: 'Nothing to choose from.' },
  maxHeight: { type: String, default: '' },
  /** The row a roll landed on, when the roll came from outside (the dice roller).
   *  Marks the row until it is taken or the rows change — it never commits it. */
  rolledIndex: { type: Number, default: null },
  /** Bump to re-mark `rolledIndex` (a second roll can land on the same row, and
   *  that must still read as a roll rather than as nothing happening). */
  rollToken: { type: Number, default: 0 },
  /** Show the 🎲. Off by default: rolling is meaningful on a roll table, but a
   *  consequence or a hitch is usually a deliberate choice, so the host decides. */
  allowRandom: { type: Boolean, default: false },
  randomLabel: { type: String, default: 'Roll' },
  cancelLabel: { type: String, default: 'Cancel' },
  showCancel: { type: Boolean, default: true },
  /** Force the column legend off (it is on automatically when a key cell exists). */
  showHeader: { type: Boolean, default: null },
  /** Stagger the rows in on mount. Wanted for a modal surface, off in a dense panel. */
  stagger: { type: Boolean, default: false },
  /** Test seam / advanced: override the app-wide resolver. */
  resolver: { type: Object, default: null },
})

/** `pick` is the click (the only way a row is taken); `roll` is the 🎲 finding one. */
const emit = defineEmits(['pick', 'roll', 'close'])

const shared = useLabelResolver()
const labels = computed(() => props.resolver || shared)

// Every surface that phrases a row needs the registry-wide name map, and the
// resolver loads it once per page. Doing it here — rather than in each host —
// is the same "supplied once" rule as the map itself: a host cannot forget it.
onMounted(() => { if (!props.resolver) shared.load() })

const keyHeader = 'Key'
const costHeader = 'Cost'

// A key cell appears when the surface knows what a key means (a scheme) or when
// a row brings its own — an archetype list has neither and so looks exactly like
// the list the human already liked, with no empty column.
const showKey = computed(() =>
  !!props.scheme || props.rows.some((r) => r.key !== undefined && r.key !== null && r.key !== ''),
)
const headerOn = computed(() => (props.showHeader === null ? showKey.value : props.showHeader))

// The row a roll found. A host that knows the roll (the dice roller's own) passes
// `rolledIndex` and owns it; otherwise the 🎲 owns it here, so a host that only
// wants "roll, see it marked, click it" needs no state at all. A new set of rows
// clears the mark — the next step's table must not inherit the last one's find.
const ownRoll = ref(null)
const rolled = computed(() => (props.rolledIndex === null || props.rolledIndex === undefined
  ? ownRoll.value
  : props.rolledIndex))
watch(() => props.rows, () => { ownRoll.value = null })

// The landing beat: the mark is persistent, the animation is not.
const landing = ref(null)
let landingTimer = null
watch(() => [rolled.value, props.rollToken], () => {
  const v = rolled.value
  if (v === null || v === undefined) { landing.value = null; return }
  landing.value = v
  if (landingTimer) clearTimeout(landingTimer)
  landingTimer = setTimeout(() => { landing.value = null }, 900)
}, { immediate: true })
onUnmounted(() => { if (landingTimer) clearTimeout(landingTimer) })

function keyOf(r, i) {
  if (r.key !== undefined && r.key !== null && r.key !== '') return r.key
  return entryKey(r, i, props.scheme)
}
function toneOf(r) {
  return r.tone ? `ct-tone-${r.tone}` : ''
}
function stateOf(r) {
  return r.state ? `is-${r.state}` : ''
}
function isLocked(r) {
  return !!(r.locked || r.disabled)
}
function whyOf(r) {
  return r.why || r.reason || ''
}

function conditionLines(r) {
  if (r.conditionLines) return r.conditionLines
  return (r.conditions || []).map((c) => labels.value.condition(c)).filter(Boolean)
}
function effectLines(r) {
  if (r.effectLines) return r.effectLines
  return (r.effects || []).map((e) => labels.value.effect(e)).filter(Boolean)
}
function costOf(r) {
  if (typeof r.cost === 'string') return { label: r.cost, free: !!r.costFree }
  if (Array.isArray(r.costEffects)) return labels.value.cost(r.costEffects)
  return { label: '', free: true }
}

/** The click is the pick — the one and only way a row is taken. */
function onRow(r, i) {
  if (props.busy || isLocked(r)) return
  emit('pick', r, i)
}

/** The pool a random pick may draw from: locked rows are never rolled. */
const pool = computed(() => props.rows.map((r, i) => ({ r, i })).filter((x) => !isLocked(x.r)))
/** Whether the list carries weights at all — decides weighted vs uniform roll. */
const weighted = computed(() => pool.value.some((x) => (Number(x.r.weight) || 0) > 0))

/**
 * Roll one row and **mark** it. A weighted list rolls a die over the cumulative
 * weights (the life-path rule) and reports the number rolled; an unweighted list
 * picks uniformly and reports none. Locked and zero-weight rows are never rolled.
 *
 * It deliberately does not pick: the mark says *which row the dice found*, and
 * taking it stays the player's click — on that row or on any other, which is how
 * "the dice said the third one" and "actually, I want the first" stay one click
 * apart instead of two presses and a confirm.
 */
function pickRandom() {
  if (props.busy) return
  const entries = pool.value
  if (!entries.length) return

  const land = (x, roll) => {
    ownRoll.value = x.i
    emit('roll', x.r, x.i, roll)
  }

  if (weighted.value) {
    const total = entries.reduce((s, x) => s + (Number(x.r.weight) || 0), 0)
    const roll = Math.floor(Math.random() * total) + 1
    let cum = 0
    for (const x of entries) {
      cum += Number(x.r.weight) || 0
      if (roll <= cum) { land(x, roll); return }
    }
    land(entries[entries.length - 1], roll)     // float drift → the last entry
    return
  }

  land(entries[Math.floor(Math.random() * entries.length)], null)
}
</script>

<style scoped>
/* Container, not viewport: the same surface is a 400px sheet panel when the
   character sheet is docked and a full-screen modal on a phone, so what the row
   needs to know is how much room *it* has — not how wide the window is. */
.ct-root {
  container-type: inline-size;
  container-name: ct;
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
  font-size: 12px;
  color: var(--text);
}

.ct-scroll { display: flex; flex-direction: column; gap: 3px; min-width: 0; }
.ct-rows { display: flex; flex-direction: column; gap: 3px; min-width: 0; }

/* ── the column legend ─────────────────────────────────────────────────────
   A hairline under a micro-caps line: it labels the columns without competing
   with the rows, which are the content. It mirrors the row's own order — the
   result, then the key (which sits at the content's right edge), then the
   price. */
.ct-head {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto auto;
  gap: 10px;
  align-items: end;
  padding: 0 9px 4px;
  font-size: 9px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--text-dim);
  border-bottom: 1px solid var(--overlay-12);
  background-image: linear-gradient(to right, var(--accent-16), transparent 60%);
  background-repeat: no-repeat;
  background-size: 100% 1px;
  background-position: bottom;
}
.ct-head-key { min-width: 26px; text-align: center; }
.ct-head-cost { text-align: right; }

/* ── a row ─────────────────────────────────────────────────────────────────
   Two cells, one grid: the block (what it is and what it does, with the key
   floated into its top-right corner) and the price. The block is unbounded
   height on purpose — conditions and effects stack inside it rather than
   widening the row. */
.ct-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 8px;
  align-items: start;
  width: 100%;
  padding: 6px 9px;
  border-radius: var(--radius-xs);
  border: 1px solid var(--overlay-10);
  background: var(--overlay-4);
  color: var(--text);
  font: inherit;
  font-size: 12px;
  text-align: left;
  cursor: pointer;
  transition: background 0.12s ease, border-color 0.12s ease, box-shadow 0.12s ease;
}

.ct-row:hover:not(:disabled) { background: var(--accent-12); border-color: var(--accent); }
.ct-row:focus-visible { outline: 2px solid var(--accent); outline-offset: 1px; }

/* Tone is a semantic edge, not a fill: a mixed list (some gm, some player)
   still reads as one control. */
.ct-tone-gm { border-left: 2px solid var(--danger); }
.ct-tone-player { border-left: 2px solid var(--success); }

/* ── the row a roll found ──────────────────────────────────────────────────
   A *mark*, not a selection: it says which row the dice found and it stays there
   while the player decides, because the taking is their click and it can land on
   any row. Distinct from `:hover` on purpose — a mark that looks like a pointer
   passing over would not be read as the dice having spoken. */
.ct-row.is-rolled {
  background: var(--accent-12);
  border-color: var(--accent);
  box-shadow: inset 3px 0 0 var(--accent);
}
.ct-row.is-rolled .ct-pip {
  background: var(--accent);
  border-color: var(--accent);
  color: var(--text-on-accent);
  font-weight: 700;
}

.ct-row.is-locked { opacity: 0.55; cursor: not-allowed; border-style: dashed; }
.ct-row.is-locked:hover { background: var(--overlay-4); border-color: var(--overlay-10); }

/* Semantic states, the same vocabulary as the GM lists, so a row means the same
   thing here as it does in a panel. */
.ct-row.is-active { background: var(--accent-12); box-shadow: inset 0 0 0 1px var(--accent); }
.ct-row.is-warning { background: var(--warn-12); box-shadow: inset 0 0 0 1px var(--warn); }
.ct-row.is-danger { background: var(--danger-12); box-shadow: inset 0 0 0 1px var(--danger); }
.ct-row.is-success { background: var(--success-12); box-shadow: inset 0 0 0 1px var(--success); }
.ct-row.is-muted { opacity: 0.6; }

/* ── the key pip ───────────────────────────────────────────────────────────
   The roll's own number, as a die-face chip: tabular so a column of them lines
   up, and it fills when a roll lands on it. Floated, so it is a corner marker
   rather than a column — the label's first line wraps beside it and the text
   continues beneath. */
.ct-cell-main { display: block; min-width: 0; }
.ct-cell-key { float: right; margin: 0 0 2px 8px; }
.ct-pip {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 26px;
  padding: 1px 6px;
  border-radius: var(--radius-xs);
  border: 1px solid var(--overlay-20);
  background: var(--overlay-6);
  color: var(--text-dim);
  font-size: 10px;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

/* The stack starts below the pip rather than beside it: a chip is wide, and
   overlapping the float's last pixel would read as a rendering fault. */
.ct-label { display: block; font-weight: 600; }
.ct-desc { display: block; font-size: 11px; color: var(--text-dim); }

.ct-conds { display: flex; flex-direction: column; align-items: flex-start; gap: 1px; margin-top: 1px; clear: right; }
.ct-cond { font-size: 10px; color: var(--accent); }

.ct-effects { display: flex; flex-direction: column; align-items: flex-start; gap: 2px; margin-top: 2px; clear: right; }
.ct-effect {
  font-family: monospace;
  font-size: 10px;
  line-height: 1.35;
  padding: 1px 6px;
  border-radius: var(--radius-xs);
  background: var(--overlay-6);
  border: 1px solid var(--overlay-10);
  /* A long effect phrase is wrapped, never clipped: the panel does not scroll
     sideways, so an over-wide chip used to paint out of its own row. */
  max-width: 100%;
  overflow-wrap: anywhere;
}

/* "Why not" is a line in the row, not a tooltip: a locked row has to say what
   it is waiting for without being hovered or tapped ([[B190]]). */
.ct-why { display: block; font-size: 10px; color: var(--danger-bright); margin-top: 1px; clear: right; }

.ct-cell-cost { display: flex; justify-content: flex-end; align-items: flex-start; }
.ct-cost {
  font-size: 10px;
  font-weight: 600;
  color: var(--warn);
  background: var(--warn-12);
  border: 1px solid var(--warn-20);
  border-radius: var(--radius-pill);
  padding: 1px 7px;
  white-space: nowrap;
}
.ct-cost.is-free { color: var(--text-dim); background: var(--overlay-4); border-color: var(--overlay-8); font-weight: 400; }
.ct-hint { font-size: 9px; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.04em; }

.ct-state { font-size: 11px; color: var(--text-dim); padding: 6px 2px; }
.ct-actions { display: flex; gap: 6px; align-self: flex-start; margin-top: 2px; }

/* ── the landing beat ──────────────────────────────────────────────────────
   The mark above is persistent; this is the *arrival* — one lift and one ring as
   the dice land, so the row reads as found rather than as already chosen. */
.ct-row.is-landing { animation: ct-land 0.85s ease-out; }
@keyframes ct-land {
  0% { box-shadow: 0 0 0 0 var(--accent-45), inset 3px 0 0 var(--accent); transform: translateY(0); }
  12% { transform: translateY(-2px); }
  100% { box-shadow: 0 0 0 14px transparent, inset 3px 0 0 var(--accent); transform: translateY(0); }
}

/* ── entrance ──────────────────────────────────────────────────────────────
   A short stagger so a menu arrives rather than appears. Opt-in, because a
   dense panel wants none. */
.ct-stagger .ct-row { animation: ct-in 0.22s ease-out both; animation-delay: calc(var(--i) * 16ms); }
@keyframes ct-in { from { opacity: 0; transform: translateY(3px); } }

/* ── narrowing: the row becomes a card ─────────────────────────────────────
   Below ~520px of *surface* width the cost wraps under the result and the
   legend goes: a table read at 380px is two cramped columns, and the same
   content stacked is one comfortable one. This is what makes the surface work
   on a phone in portrait and in a 400px dock. The key is **not** part of this:
   it is a corner chip in the content at every width, so it never costs a line
   of its own — which is where the dock's ~290px used to spend 28px per row. */
@container ct (max-width: 520px) {
  .ct-head { display: none; }
  .ct-row { grid-template-columns: minmax(0, 1fr); }
  .ct-cell-cost { grid-column: 1; justify-content: flex-start; margin-top: 1px; }
}

/* ── compact: the roller's own menus ───────────────────────────────────────
   Same row, smaller bones: the dice roller's panels are ~360px and the menu
   sits under a pool, so it must not out-shout the roll it followed. */
.ct-compact { gap: 4px; font-size: 11px; }
.ct-compact .ct-row { padding: 5px 8px; gap: 6px; font-size: 11px; }
.ct-compact .ct-label { font-weight: 600; }
.ct-compact .ct-desc { font-size: 10px; }
.ct-compact .ct-effect { font-size: 9px; padding: 1px 5px; }
.ct-compact .ct-head { padding-bottom: 3px; font-size: 8px; }

@media (prefers-reduced-motion: reduce) {
  .ct-row, .ct-row.is-landing { animation: none !important; }
  .ct-row { transition: none; }
}
</style>
