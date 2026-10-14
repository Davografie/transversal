<template>
  <div class="settings-section">
    <label class="settings-label">Fullscreen</label>
    <SegmentedControl
      class="settings-segmented"
      aria-label="Fullscreen"
      :model-value="mode"
      :options="options"
      reselect
      @update:model-value="$emit('update:mode', $event)"
    />
    <p class="settings-note">{{ hint }}</p>
  </div>
</template>

<script setup>
import SegmentedControl from '@/components/ui/SegmentedControl.vue'

// Off / On / Auto, remembered per device. On a phone this is what reclaims the
// address bar, which the app can never scroll away (the shell does not scroll)
// — see [[UI-UX Design#Fullscreen]]. The preference, the device-kind memory and
// the entry policy all live in `useFullscreenMode`; the shell owns that call, so
// `auto` still works when this screen has never been opened.
defineProps({
  mode: { type: String, default: 'off' },        // 'off' | 'on' | 'auto'
  options: { type: Array, required: true },
  hint: { type: String, default: '' },
})

defineEmits(['update:mode'])
</script>
