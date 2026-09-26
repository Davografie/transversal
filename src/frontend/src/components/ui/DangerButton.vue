<template>
  <Button
    class="danger-button"
    variant="danger"
    :active="confirming"
    :disabled="disabled"
    block
    @click="onClick"
  >{{ displayLabel }}</Button>
</template>

<script setup>
import { ref, computed, onUnmounted } from 'vue'
import Button from './Button.vue'

// Destructive action with a two-step confirm. Built on the shared Button
// primitive — the danger look comes from `variant="danger"`, the armed state
// from `active`.
const props = defineProps({
  label: { type: String, default: 'Delete' },
  confirmLabel: { type: String, default: 'Confirm?' },
  loadingLabel: { type: String, default: '' },
  disabled: { type: Boolean, default: false },
  confirmTimeout: { type: Number, default: 3000 },
  // When false, a single click performs the action immediately (for
  // non-destructive row removals). When true, requires a second confirm click.
  requiresConfirm: { type: Boolean, default: true },
})

const emit = defineEmits(['confirm'])

const confirming = ref(false)
let timer = null

const displayLabel = computed(() => {
  if (props.disabled && props.loadingLabel) return props.loadingLabel
  if (confirming.value) return props.confirmLabel
  return props.label
})

function onClick() {
  if (props.disabled) return
  if (!props.requiresConfirm) {
    emit('confirm')
    return
  }
  if (confirming.value) {
    clearTimer()
    confirming.value = false
    emit('confirm')
  } else {
    confirming.value = true
    timer = setTimeout(() => { confirming.value = false }, props.confirmTimeout)
  }
}

function clearTimer() {
  if (timer) { clearTimeout(timer); timer = null }
}

onUnmounted(clearTimer)
</script>

<style scoped>
/* Squarer than the default radius (matches the old danger-button look) and a
   pulse while armed, so the confirm step reads as a distinct state. */
.danger-button.btn-md { border-radius: var(--radius-sm); font-size: 12px; padding: 6px; }
.danger-button.is-active { font-weight: 600; animation: pulse-confirm 0.6s ease-in-out infinite alternate; }

@keyframes pulse-confirm {
  from { opacity: 0.85; }
  to { opacity: 1; }
}

@media (prefers-reduced-motion: reduce) {
  .danger-button.is-active { animation: none; }
}
</style>
