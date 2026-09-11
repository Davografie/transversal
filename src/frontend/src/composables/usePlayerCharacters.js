import { ref } from 'vue'
import { useEntityCache } from './entityCache.js'

/**
 * The characters a player owns — the list behind the settings overlay, the
 * pending list shown when switching identity, and the per-character actions
 * (set/unset main, relinquish agency, reveal the ✕ on long-press).
 *
 * Everything here is player-scoped: callers pass the current `playerId` (and
 * `entityId` for the "the body I'm in got released" fix-up).
 */
export function usePlayerCharacters({ playerId, entityId, graphql }) {
  const playerEntities = ref([])
  const pendingPlayerEntities = ref([])
  const loadingPlayerEntities = ref(false)

  const locationNames = ref({})
  let locationNamesLoaded = false

  // Reveal the release (✕) button on long-press (touch) or right-click.
  const revealedReleaseId = ref(null)
  let releaseTouchTimer = null
  let suppressCardClickUntil = 0

  async function fetchPlayerEntities() {
    if (!playerId.value) return
    loadingPlayerEntities.value = true
    try {
      playerEntities.value = await fetchEntitiesFor(playerId.value)
    } finally {
      loadingPlayerEntities.value = false
    }
  }

  async function fetchLocationNames() {
    if (locationNamesLoaded) return
    try {
      const r = await fetch('/api/v1/locations/tree')
      const tree = await r.json()
      const map = {}
      const walk = (nodes) => {
        for (const n of nodes || []) {
          if (n.id && n.name) map[n.id] = n.name
          if (n.children) walk(n.children)
        }
      }
      walk(tree)
      locationNames.value = map
      locationNamesLoaded = true
    } catch {
      locationNames.value = {}
    }
  }

  function locationLabel(e) {
    const lid = e?.currentLocation
    if (lid) return locationNames.value[lid] || lid
    return e?.currentUniverse || ''
  }

  async function fetchEntitiesFor(pid) {
    fetchLocationNames()
    try {
      const r = await fetch(`/api/v1/players/${pid}`)
      const p = await r.json()
      if (p && p.entity_ids?.length) {
        const r2 = await fetch('/api/v1/graphql', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            query: `query($ids: [ID!]!) { entities(ids: $ids) { id name type sheetPortrait currentLocation currentUniverse } }`,
            variables: { ids: p.entity_ids }
          })
        })
        const json = await r2.json()
        const results = json.data?.entities || []
        const mains = await fetchPlayerMains(pid)
        const entityCache = useEntityCache()
        for (const e of results) {
          e.main = mains.has(e.id)
          entityCache.setEntity(e.id, e)
        }
        return results
      }
    } catch {}
    return []
  }

  async function fetchPlayerMains(pid) {
    // The agency `main` flag lives on the player→entity edge, not the entity doc.
    try {
      const data = await graphql(`query($id: ID!) { player(id: $id) { agency { entityId main } } }`, { id: pid })
      return new Set((data?.player?.agency || []).filter((a) => a.main).map((a) => a.entityId))
    } catch { return new Set() }
  }

  async function toggleMain(e) {
    if (!playerId.value || !e?.id) return
    const next = !e.main
    await fetch(`/api/v1/players/${playerId.value}/main/${e.id}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ main: next }),
    }).catch(() => {})
    // Marking the currently-controlled body as main should stamp spotlight now
    // (the control endpoint writes last_spotlight_at/last_main_entity_id).
    if (next && entityId.value === e.id) {
      await fetch(`/api/v1/players/${playerId.value}/control/${e.id}`, { method: 'POST' }).catch(() => {})
    }
    await fetchPlayerEntities()
  }

  async function releaseCharacter(e) {
    if (!playerId.value || !e?.id) return
    try {
      await fetch(`/api/v1/players/${playerId.value}/release/${e.id}`, { method: 'POST' })
    } catch {}
    const wasActive = entityId.value === e.id
    await fetchPlayerEntities()
    if (wasActive && playerEntities.value.length) {
      entityId.value = playerEntities.value[0].id
    }
  }

  function revealRelease(id) {
    revealedReleaseId.value = id
  }

  function onReleaseTouchStart(event, id) {
    clearTimeout(releaseTouchTimer)
    releaseTouchTimer = setTimeout(() => {
      revealedReleaseId.value = id
      // Long-press engaged — swallow the synthetic tap-click that follows.
      suppressCardClickUntil = Date.now() + 700
    }, 500)
  }

  function onReleaseTouchCancel() {
    clearTimeout(releaseTouchTimer)
    releaseTouchTimer = null
  }

  function onReleaseTouchEnd() {
    clearTimeout(releaseTouchTimer)
    releaseTouchTimer = null
  }

  /** True while the just-finished long-press should swallow the tap. */
  function isReleaseSuppressed() {
    return Date.now() < suppressCardClickUntil
  }

  function clearReleaseReveal() {
    revealedReleaseId.value = null
  }

  return {
    playerEntities, pendingPlayerEntities, loadingPlayerEntities,
    locationNames, revealedReleaseId,
    fetchPlayerEntities, fetchEntitiesFor, fetchPlayerMains,
    fetchLocationNames, locationLabel,
    toggleMain, releaseCharacter, revealRelease,
    onReleaseTouchStart, onReleaseTouchCancel, onReleaseTouchEnd,
    isReleaseSuppressed, clearReleaseReveal,
  }
}
