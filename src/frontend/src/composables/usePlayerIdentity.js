import { computed, ref, watch } from 'vue'

/**
 * Who you are: the login flow (name → player, with live search over existing
 * players and a "new transverser" path), the stale-identity recovery on boot,
 * and the identity switch inside the settings overlay.
 *
 * `playerId` / `playerName` / `showLoginOverlay` are created by the caller and
 * handed in: they are localStorage-backed handles other composables also read
 * (usePlayerCharacters needs playerId, the shell gates on showLoginOverlay), so
 * owning them here would only force an instantiation cycle.
 *
 * The app owns everything downstream, so those are injected:
 *   entityId             current perspective entity (claimed on boot if owned)
 *   needsCharacterPick   true while a player must pick an owned character
 *   loadPlayerRole       fetch + apply the player's role (architect/player)
 *   initLocation         re-init the map/location after an identity switch
 *   fetchPlayerEntities / fetchSupportCharacters / fetchActiveMains
 *   fetchEntitiesFor     entities for an arbitrary player id (switch preview)
 *   pendingPlayerEntities  ref filled with the switch preview list
 *   focusSwitchInput     focuses the settings name input (the DOM ref lives in App)
 *   diag                 DIAG.mark
 */
export function usePlayerIdentity({
  playerId,
  playerName,
  showLoginOverlay,
  entityId,
  needsCharacterPick,
  loadPlayerRole,
  initLocation,
  fetchPlayerEntities,
  fetchSupportCharacters,
  fetchActiveMains,
  fetchEntitiesFor,
  pendingPlayerEntities,
  focusSwitchInput = () => {},
  diag = () => {},
}) {
  const checking = ref(false)
  const nameStatus = ref('')
  const nameFound = ref(false)
  const pendingPlayer = ref(null)

  // Settings panel — identity switching
  const switchName = ref('')
  const switchEditing = ref(false)
  const switching = ref(false)
  const switchError = ref('')
  const switchPending = ref(null)
  const switchStatus = ref('')
  const switchFound = ref(false)

  // Name search
  const nameSuggestions = ref([])
  const switchSuggestions = ref([])
  const loginHasExactMatch = ref(false)
  const switchHasExactMatch = ref(false)
  let nameDebounce = null
  let switchDebounce = null

  const showLoginCreate = computed(() => playerName.value.trim() && !loginHasExactMatch.value)
  const showSwitchCreate = computed(() => switchName.value.trim() && !switchHasExactMatch.value)

  async function searchPlayers(q) {
    if (!q || q.length < 1) { nameSuggestions.value = []; return }
    try {
      const r = await fetch(`/api/v1/players?q=${encodeURIComponent(q)}`)
      const data = await r.json()
      nameSuggestions.value = data
    } catch (e) {
      nameSuggestions.value = []
    }
  }

  // Watch playerName for live search suggestions in login flow
  watch(playerName, (val) => {
    if (playerId.value) return  // only in login flow
    if (nameDebounce) clearTimeout(nameDebounce)
    const q = val.trim()
    nameDebounce = setTimeout(async () => {
      if (!q) {
        nameSuggestions.value = []
        loginHasExactMatch.value = false
        pendingPlayer.value = null
        nameStatus.value = ''
        nameFound.value = false
        return
      }
      await searchPlayers(q)
      const exact = nameSuggestions.value.find(s => s.name.toLowerCase() === q.toLowerCase())
      loginHasExactMatch.value = !!exact
      if (exact && nameSuggestions.value.length === 1) {
        // Unique exact match — auto-assume it and show no suggestions (the
        // "New transverser" option hides via loginHasExactMatch).
        nameSuggestions.value = []
        pendingPlayer.value = { id: exact.id, name: exact.name, found: true }
        nameStatus.value = `You've transversed before, ${exact.name}.`
        nameFound.value = true
      } else {
        // Multiple candidates (e.g. "Daan" + "Daan2") or none — keep the
        // suggestions visible so the player can pick. If the already-selected
        // player's name still matches the query, hold the selection and hide
        // the list; otherwise clear a stale auto-assumed match.
        const assumed = pendingPlayer.value
        if (assumed?.found && assumed.name.toLowerCase() === q.toLowerCase()) {
          nameSuggestions.value = []
        } else if (assumed?.found) {
          pendingPlayer.value = null
          nameStatus.value = ''
          nameFound.value = false
        }
      }
    }, 150)
  })

  async function onNameEnter() {
    if (nameDebounce) clearTimeout(nameDebounce)
    const name = playerName.value.trim()
    if (!name) return
    checking.value = true
    nameSuggestions.value = []
    try {
      await searchPlayers(name)
      const p = await findOrCreatePlayer(name)
      if (p) {
        pendingPlayer.value = p
        localStorage.setItem('playerName', name)
        if (p.found) {
          nameStatus.value = `You've transversed before, ${name}.`
          nameFound.value = true
        } else {
          nameStatus.value = `New transverser detected. Welcome, ${name}.`
          nameFound.value = false
        }
      }
    } finally {
      checking.value = false
    }
  }

  function selectSuggestion(s) {
    playerName.value = s.name
    nameSuggestions.value = []
    loginHasExactMatch.value = true  // an existing player was picked — no "New transverser" flash
    localStorage.setItem('playerName', s.name)
    pendingPlayer.value = { id: s.id, name: s.name, found: true }
    nameStatus.value = `You've transversed before, ${s.name}.`
    nameFound.value = true
  }

  async function searchSwitchPlayers(q) {
    if (!q || q.length < 1) { switchSuggestions.value = []; return }
    try {
      const r = await fetch(`/api/v1/players?q=${encodeURIComponent(q)}`)
      switchSuggestions.value = await r.json()
    } catch { switchSuggestions.value = [] }
  }

  // Watch switchName for live suggestions in settings panel
  watch(switchName, (val) => {
    if (switchDebounce) clearTimeout(switchDebounce)
    const q = val.trim()
    switchError.value = ''
    switchDebounce = setTimeout(async () => {
      await searchSwitchPlayers(q)
      const exact = switchSuggestions.value.some(s => s.name.toLowerCase() === q.toLowerCase())
      switchHasExactMatch.value = exact
      if (exact) switchSuggestions.value = []
    }, 150)
  })

  function selectSwitchSuggestion(s) {
    switchName.value = s.name
    switchSuggestions.value = []
    switchPending.value = { id: s.id, name: s.name, found: true }
    switchStatus.value = `You've transversed before, ${s.name}.`
    switchFound.value = true
    switchError.value = ''
    pendingPlayerEntities.value = []
    fetchEntitiesFor(s.id).then(e => { pendingPlayerEntities.value = e })
    switchEditing.value = false
  }

  async function findOrCreatePlayer(name) {
    try {
      const r = await fetch('/api/v1/players', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name }) })
      return await r.json()
    } catch { return null }
  }

  async function fetchPlayer(pid) {
    if (!pid) return null
    try {
      const r = await fetch(`/api/v1/players/${pid}`)
      if (!r.ok) return null
      return (await r.json()) || null
    } catch {
      return null
    }
  }

  async function ensurePlayer() {
    diag('ensurePlayer-start', { playerId: playerId.value, playerName: playerName.value })
    if (playerId.value) {
      const p = await fetchPlayer(playerId.value)
      if (p) {
        diag('ensurePlayer-have-id', { playerId: playerId.value, entityIds: p.entity_ids })
        if (Array.isArray(p.entity_ids) && p.entity_ids.includes(entityId.value)) {
          fetch(`/api/v1/players/${playerId.value}/claim/${entityId.value}`, { method: 'POST' }).catch(() => {})
        }
        loadPlayerRole()
        return
      }
      diag('ensurePlayer-stale-id', { playerId: playerId.value })
      playerId.value = ''
      playerName.value = ''
      localStorage.removeItem('playerId')
      localStorage.removeItem('playerName')
    }

    if (playerName.value) {
      // Have name but no ID — try to recover
      const p = await findOrCreatePlayer(playerName.value)
      diag('ensurePlayer-recover-result', { found: !!p, id: p?.id })
      if (p) {
        playerId.value = p.id
        localStorage.setItem('playerId', p.id)
        return
      }
    }

    // No name or ID — show entry
    diag('ensurePlayer-no-identity', 'showing login overlay')
    showLoginOverlay.value = true
  }

  function confirmPlayer() {
    if (!pendingPlayer.value) return
    playerId.value = pendingPlayer.value.id
    localStorage.setItem('playerId', pendingPlayer.value.id)
    localStorage.setItem('playerName', playerName.value.trim())
    nameStatus.value = ''
    pendingPlayer.value = null
    // Stay on the overlay until this player has a usable character: a fresh
    // player has no entities yet and must create or claim one before playing.
    Promise.all([loadPlayerRole(), fetchPlayerEntities(), fetchSupportCharacters(), fetchActiveMains()]).then(() => {
      if (!needsCharacterPick.value) showLoginOverlay.value = false
    })
  }

  async function startSwitchEdit() {
    switchEditing.value = true
    await focusSwitchInput()
  }

  function onSwitchBlur() {
    if (!switchStatus.value && !switching.value) {
      switchEditing.value = false
      switchName.value = playerName.value
      switchSuggestions.value = []
    }
  }

  async function onSwitchEnter() {
    if (switchDebounce) clearTimeout(switchDebounce)
    const name = switchName.value.trim()
    if (!name) return
    switching.value = true
    switchSuggestions.value = []
    switchError.value = ''
    try {
      await searchSwitchPlayers(name)
      const p = await findOrCreatePlayer(name)
      if (!p) { switchError.value = 'Could not reach server'; return }
      switchPending.value = p
      if (p.found) {
        switchStatus.value = `You've transversed before, ${name}.`
        switchFound.value = true
      } else {
        switchStatus.value = `New transverser detected. Welcome, ${name}.`
        switchFound.value = false
      }
      pendingPlayerEntities.value = []
      if (p.found) fetchEntitiesFor(p.id).then(e => { pendingPlayerEntities.value = e })
      switchEditing.value = false
    } catch (e) {
      switchError.value = e.message
    } finally {
      switching.value = false
    }
  }

  function confirmSwitch() {
    if (!switchPending.value) return
    const p = switchPending.value
    playerId.value = p.id
    playerName.value = p.name
    localStorage.setItem('playerId', p.id)
    localStorage.setItem('playerName', p.name)
    switchStatus.value = ''
    switchPending.value = null
    pendingPlayerEntities.value = []
    switchName.value = ''
    showLoginOverlay.value = false
    fetchPlayerEntities()
    initLocation()
    loadPlayerRole()
  }

  /** Clear the switch-in-progress state (the overlay's own dismissal). */
  function resetSwitch() {
    switchEditing.value = false
    switchStatus.value = ''
    switchPending.value = null
    pendingPlayerEntities.value = []
  }

  return {
    checking, nameStatus, nameFound, pendingPlayer,
    nameSuggestions, showLoginCreate, loginHasExactMatch,
    switchName, switchEditing, switching, switchError, switchPending, switchStatus, switchFound,
    switchSuggestions, showSwitchCreate,
    searchPlayers, onNameEnter, selectSuggestion,
    searchSwitchPlayers, selectSwitchSuggestion,
    findOrCreatePlayer, fetchPlayer, ensurePlayer, confirmPlayer,
    startSwitchEdit, onSwitchBlur, onSwitchEnter, confirmSwitch, resetSwitch,
  }
}
