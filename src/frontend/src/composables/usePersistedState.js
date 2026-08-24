import { ref, watch } from 'vue'

// Write-through localStorage persistence for small refs (draft edits, view
// state). Each ref rehydrates on setup and writes back on every change, so a
// standby-to-wake reload restores what the user was working on. The registry
// lets a single visibilitychange/pagehide handler flush everything on suspend
// (belt-and-suspenders — write-through already covers the common path).
const registry = []

function flushAll() {
  for (const { key, value } of registry) {
    try { localStorage.setItem(key, JSON.stringify(value.value)) } catch {}
  }
}

if (typeof window !== 'undefined' && typeof document !== 'undefined') {
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'hidden') flushAll()
  })
  window.addEventListener('pagehide', flushAll)
}

export function usePersistedRef(key, fallback = null) {
  let initial = fallback
  try {
    const raw = localStorage.getItem(key)
    if (raw != null) initial = JSON.parse(raw)
  } catch {}

  const r = ref(initial)
  watch(r, (v) => {
    try { localStorage.setItem(key, JSON.stringify(v)) } catch {}
  }, { deep: true })

  registry.push({ key, value: r })
  return r
}
