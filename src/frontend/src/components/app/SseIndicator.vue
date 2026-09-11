<template>
  <div
    class="sse-indicator"
    :class="[connected ? 'shape-circle' : 'shape-triangle', { pulse }]"
    :title="title"
  ></div>
</template>

<script setup>
import { computed } from 'vue'

// Live-connection dot: circle while the event stream is up, triangle with the
// error (or "disconnected") in the tooltip when it isn't, plus a one-shot pulse
// the caller drives on each event. Styling is global (`.sse-indicator` in
// assets/styles.css).
const props = defineProps({
  connected: { type: Boolean, default: false },
  pulse: { type: Boolean, default: false },
  error: { type: String, default: '' },
})

const title = computed(() => props.connected ? 'SSE connected' : (props.error || 'SSE disconnected'))
</script>
