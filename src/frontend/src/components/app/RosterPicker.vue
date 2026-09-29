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
        v-for="p in roster"
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
// The roster half of identity (SEC-3). Pure presentation: the composable owns the
// calls, this owns only what is on screen. Global styles (.char-list, .char-item,
// .continue-btn, .settings-name-input) are reused deliberately so the picker
// looks like the rest of the overlay.
defineProps({
  roster: { type: Array, default: () => [] },
  busy: { type: Boolean, default: false },
  error: { type: String, default: '' },
  newName: { type: String, default: '' },
})

defineEmits(['take', 'claim', 'update:newName'])
</script>

<style scoped>
.roster-new {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-top: 12px;
}
.roster-new input { flex: 1; }
</style>
