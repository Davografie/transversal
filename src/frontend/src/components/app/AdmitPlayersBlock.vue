<template>
  <!-- SEC-3 admission: one window shown to the whole table.
       A link rather than a name box, because the token admits a *device* to the
       campaign; who they are is chosen afterwards, from the roster. -->
  <div class="admit-block">
    <p v-if="!joining" class="name-hint">
      Open a window and show it to the table — everyone who scans it can join. It is
      good for about 30 minutes and can be closed early.
    </p>

    <div v-if="!joining" class="settings-section">
      <button class="continue-btn" :disabled="busy" @click="$emit('open')">
        Admit players
      </button>
    </div>

    <template v-else>
      <label class="settings-label">Show this to the table</label>
      <div class="admit-link">
        <input class="settings-name-input" readonly :value="joinUrl(joining)" @focus="$event.target.select()" />
        <button class="continue-btn" @click="$emit('copy', joinUrl(joining))">Copy</button>
      </div>
      <p class="name-hint">
        Closes itself at {{ closingAt }} — or close it now with the button below.
      </p>
    </template>

    <div v-if="windows.length" class="settings-section">
      <label class="settings-label">Open now ({{ windows.length }})</label>
      <div class="char-list">
        <button
          v-for="w in windows"
          :key="w.id"
          class="char-item"
          :disabled="busy"
          @click="$emit('close', w.id)"
        >{{ w.id }} — close</button>
      </div>
      <button class="continue-btn" :disabled="busy" @click="$emit('close-all')">
        Close all windows
      </button>
    </div>

    <p v-if="error" class="switch-error">{{ error }}</p>
  </div>
</template>

<script setup>
import { computed } from 'vue'

// Presentation only: the composable owns the calls. Global styles are reused
// (.settings-section, .char-list/.char-item, .continue-btn, .settings-name-input)
// so this sits in the settings overlay like everything else.
const props = defineProps({
  windows: { type: Array, default: () => [] },
  joining: { type: Object, default: null },
  busy: { type: Boolean, default: false },
  error: { type: String, default: '' },
  joinUrl: { type: Function, required: true },
})

defineEmits(['open', 'close', 'close-all', 'copy'])

const closingAt = computed(() => {
  const iso = props.joining?.expires_at
  if (!iso) return 'soon'
  const d = new Date(iso)
  return isNaN(d) ? 'soon' : d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
})
</script>

<style scoped>
.admit-link {
  display: flex;
  gap: 8px;
  align-items: center;
}
.admit-link input { flex: 1; font-size: 12px; }
</style>
