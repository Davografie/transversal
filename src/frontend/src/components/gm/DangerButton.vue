<template>
  <button
    type="button"
    class="danger-button"
    :class="{ confirming }"
    :disabled="disabled"
    @click="onClick"
  >
    {{ displayLabel }}
  </button>
</template>

<script setup>
import { ref, computed, onUnmounted } from 'vue'

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
.danger-button {
  width: 100%;
  font-size: 12px; padding: 6px;
  background: rgba(212, 64, 64, 0.12); color: var(--danger);
  border: 1px solid rgba(212, 64, 64, 0.25); border-radius: 6px;
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s, color 0.15s, opacity 0.15s;
}
.danger-button:hover { background: rgba(212, 64, 64, 0.25); }

.danger-button:disabled { opacity: 0.4; cursor: default; }

.danger-button.confirming {
  background: rgba(212, 64, 64, 0.35); border-color: rgba(212, 64, 64, 0.5);
  font-weight: 600;
  animation: pulse-confirm 0.6s ease-in-out infinite alternate;
}

@keyframes pulse-confirm {
  from { opacity: 0.85; }
  to { opacity: 1; }
}
</style>
