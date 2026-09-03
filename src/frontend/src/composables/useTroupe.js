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

// The support-cast roll-table id, resolved from the seeded `sfx-roll-support-cast`
// SFX (its `roll_table/menu` effect target). Used by the B59 create-from-scratch
// entry point so the table id lives in content, not duplicated in the frontend.
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
    mainOwnerId mainActive
  }
}`

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

  async function fetchSupportCastTableId(force = false) {
    if (supportCastTableId.value && !force) return supportCastTableId.value
    try {
      const data = await graphql(
        `query { sfxs { id effects { type action target } } }`,
        {},
      )
      const sfx = (data?.sfxs || []).find((s) => s.id === 'sfx-roll-support-cast')
      const menu = (sfx?.effects || []).find(
        (e) => e.type === 'roll_table' && e.action === 'menu',
      )
      supportCastTableId.value = menu?.target || null
    } catch (e) {
      error.value = e?.message || String(e)
    }
    return supportCastTableId.value
  }

  return {
    players, supportCharacters, supportCastTableId,
    loading, error,
    fetchRecency, fetchSupportCharacters, fetchSupportCastTableId,
  }
}
