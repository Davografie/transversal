<template>
  <ChoiceTable
    :rows="options"
    density="compact"
    :loading="loading"
    :busy="busy"
    :allow-random="allowRandom"
    :random-label="randomLabel"
    :cancel-label="cancelLabel"
    :empty-text="emptyText"
    @pick="(o, i, roll) => $emit('pick', o, i, roll)"
    @close="$emit('close')"
  />
</template>

<script setup>
import ChoiceTable from './ChoiceTable.vue'

// The entry picker: the **compact** face of [[UI-UX Design#Choice table]].
//
// It exists as its own name because three menus (roll table, consequence, hitch)
// were written against it and its contract is worth keeping stable: one row per
// option, an optional weighted 🎲, and a cancel. `options` is now literally the
// choice table's row vocabulary, and the rows themselves are rendered by
// `ui/ChoiceTable` — so there is one row engine and one set of row CSS in the
// app rather than two (this file used to carry its own).
//
// An option is:
//   { id?, key?, label, description?, cost?, costFree?, hint?, tone?, disabled?, weight? }
//
// `key` is the leading cell (a roll table's range/key), `tone` is a CSS hook for
// semantic colour (the consequence menu's gm/player sides), and `weight` makes
// the random pick weighted — a table with no weights rolls uniformly.
//
// It reports *what was chosen* and nothing else: resolving the pick (opening the
// target wizard, applying an entry's effects, driving the dice) belongs to the
// host, which is why the same picker serves three surfaces with three different
// resolutions.
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

defineEmits(['pick', 'close'])
</script>
