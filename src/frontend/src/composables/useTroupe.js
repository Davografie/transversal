import { ref } from 'vue'
import { useApi } from './useApi.js'

// ── Module-level singleton state ─────────────────────
// Spotlight recency for the GM troupe overview (B56). One entry per player,
// ordered oldest-first by the server (never-spotlit players sort first). Each
// entry's `mainEntity` is the main the player last took control of.
const players = ref([])
const loading = ref(false)
const error = ref(null)

// Support characters for the player settings overlay (B57). One entry per
// `support` edge (SC → main), with the main's owner and whether that main is
// currently active (the availability signal).
const supportCharacters = ref([])

// The mains currently being controlled by their players (B66). One entry per
// active main (player → main entity), for the "create a support character for
// someone else's main" entry point.
const activeMains = ref([])

// The entity each player is currently controlling — main OR support character
// (B66+). Cross-referenced with `supportCharacters` to show what SC a player is
// currently playing.
const playerBodies = ref([])

// Player ids with an active SSE connection (presence). Used to filter the troupe
// overview to online players and to mark SCs "available".
const onlinePlayers = ref([])

// The support-cast roll-table id for a given main, resolved universe-aware by
// the server (B65): ``rt-<universe>-support-cast`` with a generic fallback.
const supportCastTableId = ref(null)

const RECENCY_QUERY = `query {
  spotlightRecency {
    id name role lastSpotlightAt lastMainEntityId
    mainEntity {
      id type name razmerit currentUniverse currentLocation sheetPortrait
    }
  }
}`

const SUPPORT_QUERY = `query {
  supportCharacters {
    entity { id type name razmerit currentUniverse currentLocation sheetPortrait }
    main { id type name sheetPortrait }
    mainOwnerId ownerId mainActive
  }
}`

const ACTIVE_MAINS_QUERY = `query {
  activeMains {
    playerId playerName
    main { id type name razmerit currentUniverse currentLocation sheetPortrait }
  }
}`

const PLAYER_BODIES_QUERY = `query {
  playerBodies {
    playerId playerName
    entity { id type name razmerit currentUniverse currentLocation sheetPortrait }
  }
}`

const ONLINE_PLAYERS_QUERY = `query { onlinePlayers }`

export function useTroupe() {
  const { graphql } = useApi()

  async function fetchRecency(force = false) {
    if (players.value.length && !force) return players.value
    loading.value = true
    error.value = null
    try {
      const data = await graphql(RECENCY_QUERY, {})
      if (data?.spotlightRecency) players.value = data.spotlightRecency
    } catch (e) {
      error.value = e?.message || String(e)
    } finally {
      loading.value = false
    }
    return players.value
  }

  async function fetchSupportCharacters(force = false) {
    if (supportCharacters.value.length && !force) return supportCharacters.value
    try {
      const data = await graphql(SUPPORT_QUERY, {})
      if (data?.supportCharacters) supportCharacters.value = data.supportCharacters
    } catch (e) {
      error.value = e?.message || String(e)
    }
    return supportCharacters.value
  }

  async function fetchActiveMains(force = false) {
    if (activeMains.value.length && !force) return activeMains.value
    try {
      const data = await graphql(ACTIVE_MAINS_QUERY, {})
      if (data?.activeMains) activeMains.value = data.activeMains
    } catch (e) {
      error.value = e?.message || String(e)
    }
    return activeMains.value
  }

  async function fetchPlayerBodies(force = false) {
    if (playerBodies.value.length && !force) return playerBodies.value
    try {
      const data = await graphql(PLAYER_BODIES_QUERY, {})
      if (data?.playerBodies) playerBodies.value = data.playerBodies
    } catch (e) {
      error.value = e?.message || String(e)
    }
    return playerBodies.value
  }

  async function fetchOnlinePlayers(force = false) {
    if (onlinePlayers.value.length && !force) return onlinePlayers.value
    try {
      const data = await graphql(ONLINE_PLAYERS_QUERY, {})
      if (data?.onlinePlayers) onlinePlayers.value = data.onlinePlayers
    } catch (e) {
      error.value = e?.message || String(e)
    }
    return onlinePlayers.value
  }

  async function fetchSupportCastTableId(mainId) {
    if (!mainId) return null
    try {
      const data = await graphql(
        `query($id: ID!) { supportCastTableId(entityId: $id) }`,
        { id: mainId },
      )
      supportCastTableId.value = data?.supportCastTableId || null
    } catch (e) {
      error.value = e?.message || String(e)
    }
    return supportCastTableId.value
  }

  return {
    players, supportCharacters, activeMains, playerBodies, onlinePlayers, supportCastTableId,
    loading, error,
    fetchRecency, fetchSupportCharacters, fetchActiveMains, fetchPlayerBodies, fetchOnlinePlayers, fetchSupportCastTableId,
  }
}
