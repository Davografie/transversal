<template>
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

// A device preference: with Appearance and Fullscreen it is grouped at the
// bottom of the settings screen, under Find character. (Split out of
// `ModeAndMediaBlock` when those three moved.)
const qualityOptions = [
  { value: 'auto', label: 'Auto' },
  { value: 'low', label: 'Low' },
  { value: 'high', label: 'High' },
]

defineProps({
  mediaQuality: { type: String, default: 'auto' },
})

defineEmits(['set-media-quality'])
</script>
