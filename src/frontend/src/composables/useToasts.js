import { ref } from 'vue'

let nextId = 0

/**
 * Minimal non-intrusive toast flash messages.
 *
 * Every toast declares **who it is for** — `all`, `gm` or `player` — and the
 * filtering happens here, once. Call sites used to decide for themselves with
 * `if (gmMode.value)`, which made "who sees what" impossible to read in one
 * place and easy to get wrong (a player-relevant message behind a GM guard, or
 * the reverse). ``isGm`` is a getter so the composable can be created before
 * the role ref it reads is settled.
 */
export function useToasts({ maxToasts = 5, ttlMs = 4000, isGm = () => false } = {}) {
  const toasts = ref([])

  function addToast(message, type = 'info', audience = 'all') {
    if (audience === 'gm' && !isGm()) return null
    if (audience === 'player' && isGm()) return null
    const id = ++nextId
    toasts.value = [...toasts.value.slice(-(maxToasts - 1)), { id, message, type, audience }]
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
