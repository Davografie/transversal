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

  <div class="settings-section">
    <label class="settings-label">Media quality</label>
    <SegmentedControl
      class="settings-segmented"
      aria-label="Media quality"
      :model-value="mediaQuality"
      :options="qualityOptions"
      @update:model-value="$emit('set-media-quality', $event)"
    />
    <p class="settings-note">Low uses smaller images (less data). Auto follows your connection.</p>
  </div>
</template>

<script setup>
import SegmentedControl from '@/components/ui/SegmentedControl.vue'

const modeOptions = [
  { value: false, label: '🎭 Player' },
  { value: true, label: '🏛 Architect' },
]
const qualityOptions = [
  { value: 'auto', label: 'Auto' },
  { value: 'low', label: 'Low' },
  { value: 'high', label: 'High' },
]

// The two preference toggles at the top of the settings overlay: Player/Architect
// (the app persists it and re-fetches role-scoped data) and media quality.
defineProps({
  gmMode: { type: Boolean, default: false },
  mediaQuality: { type: String, default: 'auto' },
})

defineEmits(['update:gmMode', 'set-media-quality'])
</script>
