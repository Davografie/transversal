<template>
  <div class="settings-section">
    <label class="settings-label">Mode</label>
    <div class="mode-toggle">
      <button :class="{ active: !gmMode }" @click="$emit('update:gmMode', false)">🎭 Player</button>
      <button :class="{ active: gmMode }" @click="$emit('update:gmMode', true)">🏛 Architect</button>
    </div>
  </div>

  <div class="settings-section">
    <label class="settings-label">Media quality</label>
    <div class="mode-toggle">
      <button :class="{ active: mediaQuality === 'auto' }" @click="$emit('set-media-quality', 'auto')">Auto</button>
      <button :class="{ active: mediaQuality === 'low' }" @click="$emit('set-media-quality', 'low')">Low</button>
      <button :class="{ active: mediaQuality === 'high' }" @click="$emit('set-media-quality', 'high')">High</button>
    </div>
    <p class="quality-hint">Low uses smaller images (less data). Auto follows your connection.</p>
  </div>
</template>

<script setup>
// The two preference toggles at the top of the settings overlay: Player/Architect
// (the app persists it and re-fetches role-scoped data) and media quality.
defineProps({
  gmMode: { type: Boolean, default: false },
  mediaQuality: { type: String, default: 'auto' },
})

defineEmits(['update:gmMode', 'set-media-quality'])
</script>
