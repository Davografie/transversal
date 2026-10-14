<template>
  <div class="settings-section">
    <label class="settings-label">Mode</label>
    <SegmentedControl
      class="settings-segmented"
      aria-label="Mode"
      :model-value="gmMode"
      :options="modeOptions"
      @update:model-value="$emit('update:gmMode', $event)"
    />
  </div>
</template>

<script setup>
import SegmentedControl from '@/components/ui/SegmentedControl.vue'

// Player / Architect. It stays at the *top* of the settings screen while the
// device preferences (appearance, media quality, fullscreen) sit at the bottom:
// this one changes what the app *is* and re-fetches role-scoped data, where the
// three below are how this device shows the game and are set once.
// (Split out of `ModeAndMediaBlock` when those three moved under Find character.)
const modeOptions = [
  { value: false, label: '🎭 Player' },
  { value: true, label: '🏛 Architect' },
]

defineProps({
  gmMode: { type: Boolean, default: false },
})

defineEmits(['update:gmMode'])
</script>
