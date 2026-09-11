<template>
  <!-- Name: business-card style, click to edit -->
  <div class="search-wrapper settings-name-wrapper">
    <div
      v-if="!editing"
      class="settings-name-static"
      @click="$emit('start-edit')"
    >{{ switchName || playerName }}</div>
    <input
      v-else
      ref="inputEl"
      :value="switchName"
      class="settings-name-input"
      placeholder="Your name"
      :disabled="switching"
      @input="$emit('update:switchName', $event.target.value)"
      @keyup.enter="$emit('enter')"
      @blur="$emit('blur')"
    />
    <div v-if="editing && (suggestions.length || showCreate)" class="name-suggestions">
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
      >New transverser: <strong>{{ switchName.trim() }}</strong></button>
    </div>
  </div>

  <!-- Switch confirmation: who you'd become, and the characters that name owns -->
  <p v-if="status" class="name-status" :class="{ 'name-found': found, 'name-new': !found }">{{ status }}</p>
  <div v-if="status && pendingEntities.length" class="settings-section">
    <label class="settings-label">Characters</label>
    <div class="char-list">
      <button v-for="e in pendingEntities" :key="e.id" class="char-item">{{ e.name || e.id }}</button>
    </div>
  </div>
  <button v-if="status" class="continue-btn" @click="$emit('confirm')">{{ found ? 'Continue' : 'Begin' }}</button>
</template>

<script setup>
import { ref } from 'vue'

// The identity-switch half of the settings overlay: the player's name as a
// click-to-edit field with live suggestions, and the confirmation (status line,
// the characters that name owns, Continue/Begin). Styling is global.
defineProps({
  /** The name shown when not editing (the signed-in player's). */
  playerName: { type: String, default: '' },
  /** The draft name while editing (v-model:switch-name). */
  switchName: { type: String, default: '' },
  editing: { type: Boolean, default: false },
  switching: { type: Boolean, default: false },
  suggestions: { type: Array, default: () => [] },
  showCreate: { type: Boolean, default: false },
  status: { type: String, default: '' },
  found: { type: Boolean, default: false },
  /** Characters owned by the name being switched to. */
  pendingEntities: { type: Array, default: () => [] },
})

defineEmits(['update:switchName', 'start-edit', 'enter', 'blur', 'select', 'confirm'])

// The sheet focuses this field when the name is clicked; the focus callback is
// owned by the app, so it comes through here.
const inputEl = ref(null)
defineExpose({ focusName: () => inputEl.value?.focus() })
</script>
