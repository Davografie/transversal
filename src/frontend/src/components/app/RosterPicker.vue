<template>
  <!-- SEC-3: the device is through the passage; this is "who are you?".
       A roster rather than a name box, because taking an existing player must be
       a deliberate act — typing someone's name is what used to make you them. -->
  <div class="roster-picker">
    <p class="name-hint">
      You are through the passage. Say who you are — take your name from the table,
      or become someone new.
    </p>

    <div v-if="roster.length" class="char-list">
      <button
        v-for="p in orderedRoster"
        :key="p.id"
        class="char-item"
        :disabled="busy"
        @click="$emit('take', p.id)"
      >{{ p.name }}</button>
    </div>
    <p v-else class="name-hint">Nobody else is at this table yet.</p>

    <div class="roster-new">
      <input
        :value="newName"
        class="settings-name-input"
        placeholder="…or a new name"
        :disabled="busy"
        @input="$emit('update:newName', $event.target.value)"
        @keyup.enter="$emit('claim')"
      />
      <button
        class="continue-btn"
        :disabled="busy || !newName.trim()"
        @click="$emit('claim')"
      >Begin</button>
    </div>

    <p v-if="error" class="name-status name-new">{{ error }}</p>
  </div>
</template>

<script setup>
import { computed } from 'vue'

// The roster half of identity (SEC-3). Pure presentation: the composable owns the
// calls, this owns only what is on screen. Global styles (.char-list, .char-item,
// .continue-btn, .settings-name-input) are reused deliberately so the picker
// looks like the rest of the overlay.
const props = defineProps({
  roster: { type: Array, default: () => [] },
  busy: { type: Boolean, default: false },
  error: { type: String, default: '' },
  newName: { type: String, default: '' },
})

defineEmits(['take', 'claim', 'update:newName'])

// The API answers in creation order, which is no order at all once a table has
// twenty names on it — and this is the list you scan for *your own* name. Sorted
// here rather than in the endpoint because it is this surface's problem: a chip
// grid read at a glance, not a list you scroll.
const orderedRoster = computed(() =>
  [...props.roster].sort((a, b) => (a.name || '').localeCompare(b.name || '')),
)
</script>

<style scoped>
/* The picker owns a **column**, not the viewport. Without this the roster is as
   wide as the window — a table with 24 players spilled a chip grid 1216px across a
   1280px screen — and the explanation, capped at `.name-hint`'s 280px (a measure
   for the centred login card), wrapped to four lines in the middle of it. Capping
   the picker gives the chips a width to wrap inside and centres the block, and the
   hint then uses the column it is actually in. */
.roster-picker {
  width: min(520px, calc(100vw - 32px));
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.roster-picker .name-hint { max-width: none; }
.roster-picker .char-list { max-width: 100%; }
.roster-new {
  display: flex;
  gap: 8px;
  align-items: center;
  width: 100%;
}
/* `min-width: 0` lets the field shrink with the column instead of setting its
   width — the same trap the admission link had. */
.roster-new input { flex: 1; min-width: 0; }
</style>
