<template>
  <div class="settings-section">
    <label class="settings-label">Appearance</label>
    <SegmentedControl
      class="settings-segmented"
      aria-label="Appearance"
      :model-value="mode"
      :options="options"
      @update:model-value="$emit('update:mode', $event)"
    />
  </div>
</template>

<script setup>
import SegmentedControl from '@/components/ui/SegmentedControl.vue'

// Light/dark/auto for the whole app. `auto` follows the device; the choice is
// persisted by useThemeMode (see composables/useThemeMode.js), which also keeps
// the browser-chrome `theme-color` meta in step.
defineProps({
  mode: { type: String, default: 'auto' },   // 'auto' | 'light' | 'dark'
})

defineEmits(['update:mode'])

const options = [
  { value: 'auto', label: 'Auto', title: 'Follow your device' },
  { value: 'light', label: 'Light' },
  { value: 'dark', label: 'Dark' },
]
</script>
