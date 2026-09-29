import { ref } from 'vue'

/**
 * The link a person opens. Same origin, so the cookie lands where it is read.
 *
 * Module-level and exported because it is the *rule*, not state: the invitation
 * panel renders the link and this composable mints the record, and the rule must
 * not be written down twice.
 */
export function joinUrl(record) {
  const token = record?.token || ''
  return `${window.location.origin}/enter?s=${token}`
}

/**
 * Admission windows (SEC-3).
 *
 * A window is one token, shown to the whole table, reusable for its lifetime and
 * closable early. **Any member may open one** — the owner's decision, and with
 * players otherwise unable to add anyone it is the only way a table grows. What
 * the owner keeps is sight and the off switch: the open list, closing one, closing
 * all. That is what makes "any member may invite" safe rather than merely
 * convenient, because the token is bearer and its lifetime is the only bound on a
 * leaked link.
 *
 * The state is at **module scope** because two surfaces read it: the Players tab
 * (the switch, the open list) and the invitation panel (the QR). They must see the
 * same window — including when one of them closes it, which is the case that made
 * this shared: closing from the tab used to leave the panel showing a QR for a
 * token that no longer admitted anyone.
 */
const windows = ref([])
const joining = ref(null)
const busy = ref(false)
const error = ref('')

export function useAdmission() {
  /** The open windows — who could still join. */
  async function refresh() {
    try {
      const r = await fetch('/api/v1/access/tokens')
      if (r.ok) windows.value = await r.json()
    } catch {
      windows.value = []
    }
  }

  /** Open a window. The token is returned once, to whoever opened it. */
  async function open(ttlSeconds = 1800) {
    busy.value = true
    error.value = ''
    try {
      const r = await fetch('/api/v1/access/tokens', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ttl_seconds: ttlSeconds }),
      })
      if (!r.ok) {
        const body = await r.json().catch(() => ({}))
        error.value = body.detail || 'could not open a window'
        return null
      }
      joining.value = await r.json()
      await refresh()
      return joining.value
    } finally {
      busy.value = false
    }
  }

  async function close(id) {
    busy.value = true
    try {
      await fetch(`/api/v1/access/tokens/${id}/close`, { method: 'POST' })
      if (joining.value?.id === id) joining.value = null
      await refresh()
    } finally {
      busy.value = false
    }
  }

  async function closeAll() {
    busy.value = true
    try {
      await fetch('/api/v1/access/tokens/close-all', { method: 'POST' })
      joining.value = null
      await refresh()
    } finally {
      busy.value = false
    }
  }

  return { windows, joining, busy, error, refresh, open, close, closeAll }
}
