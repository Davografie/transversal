<template>
  <!-- A challenge's track: the dice the ledger has filled, then the unfilled
       tail of `capacity` as ghosts. Extracted so the three places a challenge
       can render — a top-level row, a container's own cell, and a nested
       sub-trait — cannot drift again. They had: the container cell and the
       nested row simply had no challenge branch, so a challenge *container*
       (the portents agenda, capacity [d6,d6,d6,d8]) drew nothing at all, and a
       challenge sub-trait (a portent, capacity [d6]) drew an empty die span. -->
  <div
    class="trait-die-groups challenge"
    :title="api.challengeProgressLabel(trait) ? api.challengeProgressLabel(trait) + ' filled' : null"
  >
    <div
      v-for="(group, gi) in api.resourceDiceGroups(trait)"
      :key="'c' + gi"
      class="trait-die-group clickable"
      :title="`Spend ${group[0]} from challenge pool`"
      @click.stop="api.spendChallengeGroup(trait, group[0])"
    >
      <DieIcon
        v-for="(die, i) in group"
        :key="i"
        :die="die"
        class="trait-die-icon"
        :class="{ 'sub-trait-die': compact }"
        :style="i ? { marginLeft: compact ? '-12px' : '-20px', marginTop: compact ? null : `${i * 4}px` } : null"
      />
    </div>
    <!-- The unfilled tail of the track — the capacity's own dice, dimmed and not
         clickable: there is nothing to spend until a slot fills. The filled dice
         stay themselves, so a d6 filling a d8 slot reads as a d6 rather than
         being disguised as the capacity. -->
    <div
      v-for="(group, gi) in api.challengeRemainingGroups(trait)"
      :key="'r' + gi"
      class="trait-die-group"
    >
      <DieIcon
        v-for="(die, i) in group"
        :key="i"
        :die="die"
        class="trait-die-icon ghost"
        :class="{ 'sub-trait-die': compact }"
        :style="i ? { marginLeft: compact ? '-12px' : '-20px', marginTop: compact ? null : `${i * 4}px` } : null"
      />
    </div>
    <span v-if="!(trait.dice || []).length && !api.challengeRemainingGroups(trait).length" class="trait-die depleted">empty</span>
  </div>
</template>

<script setup>
// Presentational, like `TraitRow` and `TraitDetailPanel`: every helper arrives
// through `api`, so the sheet stays the only place that knows how a challenge is
// read or spent. `compact` is the nested row's scale (depth > 0) — the same
// difference `TraitRow` already draws for every other kind of die.
import DieIcon from '@/components/DieIcon.vue'

defineProps({
  trait: { type: Object, required: true },
  api: { type: Object, required: true },
  compact: { type: Boolean, default: false },
})
</script>

<style scoped>
.trait-die-groups {
  display: flex;
  align-items: flex-start;
  gap: 12px;
}

.trait-die-group {
  display: flex;
  align-items: flex-start;
}

.trait-die-group.clickable { cursor: pointer; }

.trait-die-group.clickable:hover .trait-die-icon { filter: brightness(1.25); }

.trait-die-icon {
  width: 32px;
  height: 34px;
}

.trait-die-icon.ghost {
  opacity: 0.32;
}

/* The nested row's chips are smaller — TraitRow's `.sub-trait-die` scale. */
.trait-die-icon.sub-trait-die {
  font-size: 12px;
}
</style>
