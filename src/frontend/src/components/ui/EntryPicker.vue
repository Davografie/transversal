<template>
  <div class="ep-root">
    <div v-if="loading && !options.length" class="ep-empty">Loading…</div>
    <template v-else-if="options.length">
      <button
        v-for="(o, i) in options"
        :key="o.id ?? i"
        class="ep-row"
        :class="[o.tone ? 'ep-' + o.tone : '', { 'ep-disabled': o.disabled || busy }]"
        :disabled="o.disabled || busy"
        @click="pick(o, i)"
      >
        <span v-if="o.key !== undefined && o.key !== null && o.key !== ''" class="ep-key">{{ o.key }}</span>
        <span class="ep-body">
          <span class="ep-label">{{ o.label }}</span>
          <span v-if="o.description" class="ep-desc">{{ o.description }}</span>
        </span>
        <span v-if="o.cost" class="ep-cost" :class="{ 'ep-cost-free': o.costFree }">{{ o.cost }}</span>
        <span v-else-if="o.hint" class="ep-hint">{{ o.hint }}</span>
      </button>
    </template>
    <div v-else class="ep-empty">{{ emptyText }}</div>

    <div class="ep-actions">
      <Button
        v-if="allowRandom && options.length"
        variant="neutral"
        size="sm"
        title="Pick one at random"
        :disabled="busy"
        @click="pickRandom"
      >🎲 {{ randomLabel }}</Button>
      <Button variant="neutral" size="sm" :disabled="busy" @click="$emit('close')">{{ cancelLabel }}</Button>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import Button from './Button.vue'

// The entry picker: one row per option, an optional weighted 🎲, and a cancel.
// It reports *what was chosen* and nothing else — resolving the pick (opening
// the target wizard, applying an entry's effects, driving the dice) belongs to
// the host, which is why the same picker serves a roll-table menu, the
// consequence menu and the hitch menu with three different resolutions.
//
// An entry is:
//   { id?, key?, label, description?, cost?, costFree?, hint?, tone?, disabled?, weight? }
// `key` is the leading cell (a roll table's range/key), `tone` is a CSS hook for
// semantic colour (the consequence menu's gm/player sides), and `weight` makes
// the random pick weighted — a table with no weights rolls uniformly.
//
// See [[UI-UX Design#Entry picker]].
const props = defineProps({
  options: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  /** While a host is applying a pick, the whole list is inert. */
  busy: { type: Boolean, default: false },
  /** Show the 🎲. Off by default: rolling is meaningful on a roll table, but a
   *  consequence or a hitch is usually a deliberate choice, so the host decides. */
  allowRandom: { type: Boolean, default: false },
  randomLabel: { type: String, default: 'Roll' },
  cancelLabel: { type: String, default: 'Cancel' },
  emptyText: { type: String, default: 'No options.' },
})

const emit = defineEmits(['pick', 'close'])

const pool = computed(() => props.options.map((o, i) => ({ o, i })).filter((x) => !x.o.disabled))

/** Whether the list carries weights at all — decides weighted vs uniform roll. */
const weighted = computed(() => pool.value.some((x) => (Number(x.o.weight) || 0) > 0))

function pick(o, i) {
  if (props.busy || o.disabled) return
  emit('pick', o, i, null)
}

/**
 * Pick at random. A weighted list rolls a die over the cumulative weights (the
 * life-path wizard's rule) and reports the number rolled; an unweighted list
 * picks uniformly and reports no number.
 */
function pickRandom() {
  if (props.busy) return
  const entries = pool.value
  if (!entries.length) return

  if (weighted.value) {
    const total = entries.reduce((s, x) => s + (Number(x.o.weight) || 0), 0)
    const roll = Math.floor(Math.random() * total) + 1
    let cum = 0
    for (const x of entries) {
      cum += Number(x.o.weight) || 0
      if (roll <= cum) { emit('pick', x.o, x.i, roll); return }
    }
    const last = entries[entries.length - 1]      // float drift → the last entry
    emit('pick', last.o, last.i, roll)
    return
  }

  const x = entries[Math.floor(Math.random() * entries.length)]
  emit('pick', x.o, x.i, null)
}
</script>

<style scoped>
.ep-root { display: flex; flex-direction: column; gap: 4px; }

.ep-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 7px 9px;
  border-radius: 4px;
  cursor: pointer;
  background: var(--overlay-4);
  border: 1px solid var(--overlay-10);
  color: var(--text);
  font-size: 11px;
  text-align: left;
}
.ep-row:hover:not(:disabled) { background: var(--accent-12); border-color: var(--accent); }
.ep-row:focus-visible { outline: 2px solid var(--accent); outline-offset: 1px; }

/* Tone is a semantic edge, not a fill: the row keeps its neutral surface so a
   mixed list (some gm, some player) still reads as one control. */
.ep-gm { border-left: 2px solid var(--danger); }
.ep-player { border-left: 2px solid var(--success); }

.ep-disabled { opacity: 0.45; cursor: not-allowed; }

.ep-key {
  flex: 0 0 auto;
  min-width: 34px;
  font-variant-numeric: tabular-nums;
  color: var(--text-dim);
  font-size: 10px;
}

.ep-body { flex: 1; display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.ep-label { font-weight: 600; }
.ep-desc { font-size: 10px; color: var(--text-dim); }

.ep-cost { flex: 0 0 auto; font-size: 10px; color: var(--warn-bright); font-weight: 600; }
.ep-cost-free { color: var(--text-dim); font-weight: 400; }
.ep-hint { flex: 0 0 auto; font-size: 9px; color: var(--text-dim); text-transform: uppercase; }

.ep-empty { font-size: 10px; color: var(--text-dim); }
.ep-actions { display: flex; gap: 6px; align-self: flex-start; margin-top: 2px; }
</style>
