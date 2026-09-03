import { ref } from 'vue'
import { useApi } from './useApi.js'

// ── Module-level singleton state ─────────────────────
// Spotlight recency for the GM troupe overview (B56). One entry per player,
// ordered oldest-first by the server (never-spotlit players sort first). Each
// entry's `mainEntity` is the main the player last took control of.
const players = ref([])
const loading = ref(false)
const error = ref(null)

const RECENCY_QUERY = `query {
  spotlightRecency {
    id name role lastSpotlightAt lastMainEntityId
    mainEntity {
      id type name razmerit currentUniverse currentLocation sheetPortrait
    }
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

  return { players, loading, error, fetchRecency }
}
