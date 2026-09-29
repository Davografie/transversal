import { ref } from 'vue'

/**
 * Player administration (SEC-3): the two acts that change who is at the table.
 *
 *   - **revoke** ends every session a player holds (an epoch bump server-side),
 *     which is the only way to eject a device — a signed cookie cannot be recalled.
 *   - **setRole** moves the architect line, which is what gates the GM surfaces.
 *
 * Both are architect-only *server-side*, and the server also refuses to revoke the
 * last architect. The caller therefore gates the UI on the session's role rather
 * than on the client's `gmMode`: offering an action the server will refuse is how a
 * UI teaches people to distrust its buttons.
 *
 * Revoking deliberately does not delete the player — their characters hang off
 * `agency` edges and would be orphaned. It takes their access, not their character.
 */
export function usePlayerAdmin() {
  const players = ref([])
  const busy = ref(false)
  const error = ref('')
  const notice = ref('')

  async function refresh() {
    try {
      const r = await fetch('/api/v1/players')
      if (r.ok) players.value = await r.json()
    } catch {
      players.value = []
    }
  }

  async function revoke(id) {
    busy.value = true
    error.value = ''
    notice.value = ''
    try {
      const r = await fetch(`/api/v1/players/${id}/revoke`, { method: 'POST' })
      const body = await r.json().catch(() => ({}))
      if (!r.ok) {
        error.value = body.detail || 'could not revoke'
        return false
      }
      notice.value = 'Sessions ended. They can be re-admitted, but not as this device.'
      await refresh()
      return true
    } finally {
      busy.value = false
    }
  }

  async function setRole(id, role) {
    busy.value = true
    error.value = ''
    notice.value = ''
    try {
      const r = await fetch(`/api/v1/players/${id}/role`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ role }),
      })
      const body = await r.json().catch(() => ({}))
      if (!r.ok) {
        error.value = body.detail || 'could not change the role'
        return false
      }
      notice.value = role === 'architect' ? 'Now an architect.' : 'No longer an architect.'
      await refresh()
      return true
    } finally {
      busy.value = false
    }
  }

  return { players, busy, error, notice, refresh, revoke, setRole }
}
