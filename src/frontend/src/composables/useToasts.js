import { ref } from 'vue'

let nextId = 0

/**
 * Minimal non-intrusive toast flash messages.
 * Designed for architect-mode SSE event notifications.
 */
export function useToasts({ maxToasts = 5, ttlMs = 4000 } = {}) {
  const toasts = ref([])

  function addToast(message, type = 'info') {
    const id = ++nextId
    toasts.value = [...toasts.value.slice(-(maxToasts - 1)), { id, message, type }]
    setTimeout(() => dismissToast(id), ttlMs)
    return id
  }

  function dismissToast(id) {
    toasts.value = toasts.value.filter(t => t.id !== id)
  }

  function clearAll() {
    toasts.value = []
  }

  return { toasts, addToast, dismissToast, clearAll }
}
