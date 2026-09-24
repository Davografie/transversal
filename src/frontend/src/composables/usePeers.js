import { ref } from 'vue'

// Peers shown in the strip above the sheet/roller bands: every entity at the
// current location (plus the location itself), the entity you act as first,
// then by type. Sheet thumbnails resolve lazily in one batched request.
//
// The full entity list is cached for PEERS_TTL_MS; SSE and location events call
// `fetchPeers(true)` to bypass it, panel opens reuse it.
const PEERS_TTL_MS = 30_000

export function usePeers({ graphql, currentLocationId, entityId, gmMode, entityNames, diag = () => {} }) {
  const peers = ref([])
  let peersCache = null  // { entities, at }

  function applyPeers(entities) {
    const TYPE_ORDER = { CHARACTER: 0, GMC: 1, ASSET: 2, LOCATION: 3 }
    const atLocation = entities
      .filter(e => e.currentLocation === currentLocationId.value)
      .filter(e => gmMode.value || !e.unpublished)
    const here = entities.find(e => e.id === currentLocationId.value)
    const combined = here && !atLocation.some(e => e.id === here.id)
      ? [here, ...atLocation]
      : atLocation
    peers.value = combined.sort((a, b) => {
      if (a.id === entityId.value) return -1
      if (b.id === entityId.value) return 1
      return (TYPE_ORDER[a.type] ?? 9) - (TYPE_ORDER[b.type] ?? 9)
    })
  }

  async function fetchPeers(force = false) {
    if (!force && peersCache && Date.now() - peersCache.at < PEERS_TTL_MS) {
      applyPeers(peersCache.entities)
      resolvePeerSheetImages()
      return
    }
    diag('fetchPeers-start', { currentLocationId: currentLocationId.value })
    const data = await graphql(`query {
    entities { id type name currentLocation unpublished sheetPortraitTransparent }
  }`)
    if (data?.entities) {
      peersCache = { entities: data.entities, at: Date.now() }
      entityNames.value = Object.fromEntries(data.entities.map(e => [e.id, e.name]).filter(([id]) => id))
      applyPeers(data.entities)
      resolvePeerSheetImages()
      diag('fetchPeers-done', { total: data.entities.length, atLocation: peers.value.length })
    } else {
      diag('fetchPeers-no-data')
    }
  }

  async function resolvePeerSheetImages() {
    const ids = peers.value.map((p) => p.id).filter(Boolean)
    if (!ids.length) return
    const qs = new URLSearchParams({ role: 'sheet', ids: ids.join(',') })
    const r = await fetch(`/api/v1/entities/images?${qs}`)
    if (!r.ok) return
    const data = await r.json()
    const images = data?.images || {}
    peers.value = peers.value.map((p) => ({ ...p, sheetImage: images[p.id] || '' }))
  }

  /** Is `id` an entity of `type`? Falls back to the cached full list when the
   *  entity is not at the current location (e.g. a GMC elsewhere on the map). */
  function isEntityType(id, type) {
    if (!id) return false
    const atLocation = peers.value.find(e => e.id === id)
    if (atLocation) return atLocation.type === type
    return (peersCache?.entities || []).some(e => e.id === id && e.type === type)
  }

  return { peers, applyPeers, fetchPeers, isEntityType }
}
