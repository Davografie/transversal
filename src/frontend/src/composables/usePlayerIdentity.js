import { ref } from 'vue'

/**
 * Who is calling — asked of the server, never remembered by the browser (SEC-3).
 *
 * This replaces the old flow, which trusted a `localStorage` `playerId` and then
 * let anyone *adopt* a player by typing their name. That was the hole: identity
 * was client-asserted. Now the session cookie is the identity, issued by
 * `/enter?s=…` (an admission token) and bound to a player by `/auth/take` or
 * `/auth/claim`.
 *
 * On boot there are three answers, and they are different screens:
 *
 *   - **not admitted** — a 401. The perimeter notice owns that case; no in-app
 *     login can fix a missing cookie, only opening a passage link can.
 *   - **admitted, no player** — the roster picker. The device is in the campaign
 *     but has not said who it is.
 *   - **admitted, player taken** — carry on.
 *
 * Taking an *existing* player is deliberate, and is how someone resumes on a new
 * device; that is why a roster is offered rather than a name box. Architect
 * accounts are refused by the server and never appear in it.
 *
 * `playerId` / `playerName` / `showLoginOverlay` are the app's existing handles
 * and are still injected — the rest of the app reads them — but they are now
 * *derived* from the session rather than from storage.
 */
export function usePlayerIdentity({
  playerId,
  playerName,
  showLoginOverlay,
  onIdentityChanged = async () => {},
  diag = () => {},
}) {
  const admitted = ref(false)
  const me = ref(null)
  const roster = ref([])
  const busy = ref(false)
  const identityError = ref('')
  const newName = ref('')
  const rosterPicking = ref(false)

  function applyPlayer(player) {
    playerId.value = player?.id || ''
    playerName.value = player?.name || ''
    me.value = player || null
    showLoginOverlay.value = !player
    if (player) roster.value = roster.value.filter((r) => r.id !== player.id)
  }

  /** Ask the server who we are. The only place identity is established. */
  async function loadSession() {
    busy.value = true
    try {
      const r = await fetch('/api/v1/auth/session')
      if (r.status === 401) {
        // Not admitted at all. The perimeter notice is the right screen and is
        // already up (useAuthGate flips on the 401); there is nothing to do here.
        diag('session-not-admitted', { status: r.status })
        admitted.value = false
        applyPlayer(null)
        return
      }
      const data = await r.json()
      admitted.value = true
      applyPlayer(data.player || null)
      diag('session-loaded', { player: data.player })
      if (!data.player) await loadRoster()
    } catch (e) {
      identityError.value = 'could not reach the archive'
      diag('session-error', { error: e.message })
    } finally {
      busy.value = false
    }
  }

  /** Everyone who may be taken at this table. */
  async function loadRoster() {
    try {
      const r = await fetch('/api/v1/auth/roster')
      if (r.ok) roster.value = await r.json()
    } catch {
      roster.value = []
    }
  }

  /** Take an existing player — a deliberate act, not an accident of typing. */
  async function takePlayer(id) {
    if (id === playerId.value) return true
    busy.value = true
    identityError.value = ''
    try {
      const r = await fetch(`/api/v1/auth/take/${id}`, { method: 'POST' })
      if (!r.ok) {
        const body = await r.json().catch(() => ({}))
        identityError.value = body.detail || 'could not take that player'
        return false
      }
      const data = await r.json()
      applyPlayer(data.player)
      await onIdentityChanged()
      return true
    } finally {
      busy.value = false
    }
  }

  /** Become someone new. An existing name must be taken, not re-made. */
  async function claimPlayer() {
    const name = newName.value.trim()
    if (!name) return false
    busy.value = true
    identityError.value = ''
    try {
      const r = await fetch('/api/v1/auth/claim', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name }),
      })
      if (!r.ok) {
        const body = await r.json().catch(() => ({}))
        identityError.value = body.detail || 'could not create that player'
        return false
      }
      const data = await r.json()
      newName.value = ''
      applyPlayer(data.player)
      await onIdentityChanged()
      return true
    } finally {
      busy.value = false
    }
  }

  /** Open the picker from the settings overlay (a shared device, say). */
  async function beginSwitch() {
    await loadRoster()
    rosterPicking.value = true
  }

  function endSwitch() {
    rosterPicking.value = false
    identityError.value = ''
  }

  return {
    admitted, me, roster, busy, identityError, newName, rosterPicking,
    loadSession, loadRoster, takePlayer, claimPlayer, beginSwitch, endSwitch,
  }
}
