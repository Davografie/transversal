<template>
  <h3>Who are you?</h3>
  <p class="name-hint">Your name is your recovery key — use the same name on any device.</p>
  <div class="search-wrapper">
    <input
      :value="playerName"
      placeholder="Your name"
      autofocus
      :disabled="checking"
      @input="$emit('update:playerName', $event.target.value)"
      @keyup.enter="$emit('enter')"
    />
    <!-- Search results dropdown -->
    <div v-if="suggestions.length || showCreate" class="name-suggestions">
      <button
        v-for="s in suggestions"
        :key="s.id"
        class="suggestion-item"
        @mousedown.prevent
        @click="$emit('select', s)"
      >{{ s.name }}</button>
      <button
        v-if="showCreate"
        class="suggestion-item suggestion-create"
        @mousedown.prevent
        @click="$emit('enter')"
      >New transverser: <strong>{{ playerName.trim() }}</strong></button>
    </div>
  </div>
  <p v-if="status" class="name-status" :class="{ 'name-found': found, 'name-new': !found }">{{ status }}</p>
  <button v-if="status" class="continue-btn" @click="$emit('confirm')">{{ found ? 'Continue' : 'Begin' }}</button>
</template>

<script setup>
// The fresh-login prompt (no identity yet): name entry with live suggestions
// over existing players, the "new transverser" escape hatch, and the status
// line that turns into Continue/Begin. All styling is global (.name-entry and
// friends in assets/styles.css), so nothing moves with it.
defineProps({
  playerName: { type: String, default: '' },
  checking: { type: Boolean, default: false },
  suggestions: { type: Array, default: () => [] },
  showCreate: { type: Boolean, default: false },
  status: { type: String, default: '' },
  found: { type: Boolean, default: false },
})

defineEmits(['update:playerName', 'enter', 'select', 'confirm'])
</script>
