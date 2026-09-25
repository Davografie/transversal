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
          <span class="ct-cell-key">{{ keyHeader }}</span>
          <span class="ct-cell-main">Result</span>
          <span class="ct-cell-cost">{{ costHeader }}</span>
        </div>

        <div class="ct-rows" role="list">
          <button
            v-for="(r, i) in rows"
            :key="r.id ?? i"
            type="button"
            role="listitem"
            class="ct-row"
            :class="[toneOf(r), stateOf(r), {
              'is-selected': isSelected(r, i),
              'is-rolled': flashIndex === i,
              'is-locked': isLocked(r),
            }]"
            :style="{ '--i': i }"
            :disabled="isLocked(r) || busy"
            :aria-current="isSelected(r, i) ? 'true' : undefined"
            @click="onRow(r, i)"
          >
            <slot name="row" :row="r" :index="i" :selected="isSelected(r, i)">
              <span v-if="showKey" class="ct-cell-key">
                <span class="ct-pip">{{ keyOf(r, i) }}</span>
              </span>
              <span class="ct-cell-main">
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
        <Button
          v-if="allowRandom"
          variant="neutral"
          size="sm"
          title="Pick one at random"
          :disabled="busy"
          @click="pickRandom"
        >🎲 {{ randomLabel }}</Button>
        <Button
          v-if="selectable"
          variant="primary"
          size="sm"
          :disabled="busy || selected === null || selected === undefined"
          :loading="busy"
          @click="$emit('confirm', rows[selected], selected)"
        >{{ confirmLabel }}</Button>
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
//   a roll and a pick   — the scheme decides whether a row can be picked, so the
//                         🎲 is a separate control and is opt-in per host; a
//                         rolled row is *selected*, never applied
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
  /** Clicking a row selects it (then `confirm`) instead of picking immediately. */
  selectable: { type: Boolean, default: false },
  selected: { type: Number, default: null },
  /** The row a roll landed on — flashed once, so "found" reads differently from "chosen". */
  rolledIndex: { type: Number, default: null },
  /** Bump to flash `rolledIndex` again (a second roll can land on the same row,
   *  and that must still read as a roll rather than as nothing happening). */
  rollToken: { type: Number, default: 0 },
  /** Show the 🎲. Off by default: rolling is meaningful on a roll table, but a
   *  consequence or a hitch is usually a deliberate choice, so the host decides. */
  allowRandom: { type: Boolean, default: false },
  randomLabel: { type: String, default: 'Roll' },
  confirmLabel: { type: String, default: 'Continue' },
  cancelLabel: { type: String, default: 'Cancel' },
  showCancel: { type: Boolean, default: true },
  /** Force the column legend off (it is on automatically when a key cell exists). */
  showHeader: { type: Boolean, default: null },
  /** Stagger the rows in on mount. Wanted for a modal surface, off in a dense panel. */
  stagger: { type: Boolean, default: false },
  /** Test seam / advanced: override the app-wide resolver. */
  resolver: { type: Object, default: null },
})

const emit = defineEmits(['pick', 'select', 'confirm', 'close'])

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

const flashIndex = ref(null)
let flashTimer = null
watch(() => [props.rolledIndex, props.rollToken], () => {
  const v = props.rolledIndex
  if (v === null || v === undefined) { flashIndex.value = null; return }
  flashIndex.value = v
  if (flashTimer) clearTimeout(flashTimer)
  flashTimer = setTimeout(() => { flashIndex.value = null }, 900)
}, { immediate: true })
onUnmounted(() => { if (flashTimer) clearTimeout(flashTimer) })

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
function isSelected(r, i) {
  if (!props.selectable) return false
  if (r.id !== undefined && typeof props.selected === 'string') return r.id === props.selected
  return props.selected === i
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

function onRow(r, i) {
  if (props.busy || isLocked(r)) return
  if (props.selectable) emit('select', r, i)
  else emit('pick', r, i, null)
}

/** The pool a random pick may draw from: locked rows are never rolled. */
const pool = computed(() => props.rows.map((r, i) => ({ r, i })).filter((x) => !isLocked(x.r)))
/** Whether the list carries weights at all — decides weighted vs uniform roll. */
const weighted = computed(() => pool.value.some((x) => (Number(x.r.weight) || 0) > 0))

/**
 * Roll one row. A weighted list rolls a die over the cumulative weights (the
 * life-path rule) and reports the number rolled; an unweighted list picks
 * uniformly and reports none. The host still resolves the pick — the surface
 * only says which row the dice found. When the surface is `selectable` the roll
 * *selects* (and is reported as a selection), because there a roll is the way a
 * row is found and `confirm` is still the way it is taken.
 */
function pickRandom() {
  if (props.busy) return
  const entries = pool.value
  if (!entries.length) return

  const land = (x, roll) => {
    flashIndex.value = x.i
    if (props.selectable) emit('select', x.r, x.i, roll)
    else emit('pick', x.r, x.i, roll)
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
   A hairline under a micro-caps line: it labels the key column without
   competing with the rows, which are the content. */
.ct-head {
  display: grid;
  grid-template-columns: var(--ct-key-w, 58px) minmax(0, 1fr) auto;
  gap: 10px;
  align-items: end;
  padding: 0 10px 4px;
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
.ct-head .ct-cell-cost { text-align: right; }

/* ── a row ─────────────────────────────────────────────────────────────────
   Three cells, one grid: the key (what a roll finds), the block (what it is and
   what it does), the price. The middle cell is unbounded height on purpose —
   conditions and effects stack inside it rather than widening the row. */
.ct-row {
  display: grid;
  grid-template-columns: var(--ct-key-w, 58px) minmax(0, 1fr) auto;
  gap: 10px;
  align-items: start;
  width: 100%;
  padding: 7px 10px;
  border-radius: 5px;
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

.ct-row.is-selected {
  background: var(--accent-16);
  border-color: var(--accent);
  box-shadow: inset 3px 0 0 var(--accent);
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
   up, and it fills when a roll lands on it. */
.ct-cell-key { display: flex; align-items: flex-start; }
.ct-pip {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 34px;
  padding: 2px 6px;
  border-radius: 4px;
  border: 1px solid var(--overlay-20);
  background: var(--overlay-6);
  color: var(--text-dim);
  font-size: 10px;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.ct-cell-main { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.ct-label { font-weight: 600; }
.ct-desc { font-size: 11px; color: var(--text-dim); }

.ct-conds { display: flex; flex-direction: column; align-items: flex-start; gap: 1px; margin-top: 1px; }
.ct-cond { font-size: 10px; color: var(--accent); }

.ct-effects { display: flex; flex-direction: column; align-items: flex-start; gap: 2px; margin-top: 2px; }
.ct-effect {
  font-family: monospace;
  font-size: 10px;
  line-height: 1.35;
  padding: 2px 6px;
  border-radius: 4px;
  background: var(--overlay-6);
  border: 1px solid var(--overlay-10);
  word-break: break-word;
}

/* "Why not" is a line in the row, not a tooltip: a locked row has to say what
   it is waiting for without being hovered or tapped ([[B190]]). */
.ct-why { font-size: 10px; color: var(--danger-bright); margin-top: 1px; }

.ct-cell-cost { display: flex; justify-content: flex-end; align-items: flex-start; }
.ct-cost {
  font-size: 10px;
  font-weight: 600;
  color: var(--warn);
  background: var(--warn-12);
  border: 1px solid var(--warn-20);
  border-radius: 999px;
  padding: 1px 7px;
  white-space: nowrap;
}
.ct-cost.is-free { color: var(--text-dim); background: var(--overlay-4); border-color: var(--overlay-8); font-weight: 400; }
.ct-hint { font-size: 9px; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.04em; }

.ct-state { font-size: 11px; color: var(--text-dim); padding: 6px 2px; }
.ct-actions { display: flex; gap: 6px; align-self: flex-start; margin-top: 2px; }

/* ── the rolled row ────────────────────────────────────────────────────────
   "The dice found this" is a different event from "you chose this", so it gets
   its own beat: the pip fills and the row lifts, once. */
.ct-row.is-rolled { animation: ct-land 0.85s ease-out; }
.ct-row.is-rolled .ct-pip {
  background: var(--accent);
  border-color: var(--accent);
  color: var(--text-on-accent);
  font-weight: 700;
}
@keyframes ct-land {
  0% { box-shadow: 0 0 0 0 var(--accent-45); transform: translateY(0); }
  12% { transform: translateY(-2px); }
  100% { box-shadow: 0 0 0 14px transparent; transform: translateY(0); }
}

/* ── entrance ──────────────────────────────────────────────────────────────
   A short stagger so a menu arrives rather than appears. Opt-in, because a
   dense panel wants none. */
.ct-stagger .ct-row { animation: ct-in 0.22s ease-out both; animation-delay: calc(var(--i) * 16ms); }
@keyframes ct-in { from { opacity: 0; transform: translateY(3px); } }

/* ── narrowing: the row becomes a card ─────────────────────────────────────
   Below ~520px of *surface* width the cost wraps under the result and the
   legend goes: a three-column table read at 380px is three cramped columns, and
   the same content stacked is one comfortable one. This is what makes the
   surface work on a phone in portrait and in a 400px dock. */
@container ct (max-width: 520px) {
  .ct-head { display: none; }
  .ct-row { grid-template-columns: auto minmax(0, 1fr); }
  .ct-cell-cost { grid-column: 2; justify-content: flex-start; margin-top: 1px; }
  .ct-pip { min-width: 28px; }
}

/* A phone is one column — but the key stays, on its own line: it is what the
   dice found, and the moment a row is worth seeing is exactly the moment the
   surface is this narrow. */
@container ct (max-width: 340px) {
  .ct-row { grid-template-columns: minmax(0, 1fr); }
  .ct-cell-cost { grid-column: 1; }
}

/* ── compact: the roller's own menus ───────────────────────────────────────
   Same row, smaller bones: the dice roller's panels are ~360px and the menu
   sits under a pool, so it must not out-shout the roll it followed. */
.ct-compact { gap: 4px; font-size: 11px; }
.ct-compact .ct-row { --ct-key-w: 46px; padding: 6px 9px; gap: 8px; font-size: 11px; }
.ct-compact .ct-label { font-weight: 600; }
.ct-compact .ct-desc { font-size: 10px; }
.ct-compact .ct-effect { font-size: 9px; padding: 1px 5px; }
.ct-compact .ct-head { padding-bottom: 3px; font-size: 8px; }

@media (prefers-reduced-motion: reduce) {
  .ct-row, .ct-row.is-rolled { animation: none !important; }
  .ct-row { transition: none; }
}
</style>
