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
      resolvePeerFaces()
      return
    }
    diag('fetchPeers-start', { currentLocationId: currentLocationId.value })
    const data = await graphql(`query {
    entities { id type name currentLocation unpublished }
  }`)
    if (data?.entities) {
      peersCache = { entities: data.entities, at: Date.now() }
      entityNames.value = Object.fromEntries(data.entities.map(e => [e.id, e.name]).filter(([id]) => id))
      applyPeers(data.entities)
      resolvePeerFaces()
      diag('fetchPeers-done', { total: data.entities.length, atLocation: peers.value.length })
    } else {
      diag('fetchPeers-no-data')
    }
  }

  /**
   * Resolve each peer's face: the sheet image URL, and whether that image is a
   * background-removed cutout (which renders standing out of its frame instead of
   * circle-cropped).
   *
   * The flag has to come from the SAME resolution as the URL. `/entities/images`
   * resolves through each entity's **active body** (`_role_urls`: projection
   * first, then entity-level), so a peer whose file is a cutout still reports
   * `sheetPortraitTransparent: false` — that field is the deliberate *entity-level*
   * chain that `sheetPortrait` uses, and it disagrees whenever a body carries the
   * image. Measured on a live peer: served file `…_cut_….webp`, entity-level flag
   * `false`, active projection's flag `true` → it rendered as an opaque circle.
   *
   * Asked for just these ids, never the whole entity list: every transparency
   * field costs a DB read, and the list is ~1000 rows (adding it there measured
   * 0.08s → 0.94s per fetch).
   */
  async function resolvePeerFaces() {
    const ids = peers.value.map((p) => p.id).filter(Boolean)
    if (!ids.length) return
    const qs = new URLSearchParams({ role: 'sheet', ids: ids.join(',') })
    const [images, cutouts] = await Promise.all([
      fetch(`/api/v1/entities/images?${qs}`)
        .then((r) => (r.ok ? r.json() : null))
        .catch(() => null),
      graphql(`query($ids: [ID!]!) {
        entities(ids: $ids) {
          id
          currentProjection
          sheetPortraitTransparent
          projections { id sheetImageTransparent }
        }
      }`, { ids }).catch(() => null),
    ])
    const urls = images?.images || {}
    const byId = new Map((cutouts?.entities || []).map((e) => [e.id, e]))
    peers.value = peers.value.map((p) => {
      const e = byId.get(p.id)
      // The active body's own sheet image decides; an entity with no body falls
      // back to the entity-level image, exactly as the resolver chain does.
      const active = (e?.projections || []).find((pr) => pr.id === e.currentProjection)
      return {
        ...p,
        sheetImage: urls[p.id] || '',
        cutout: active ? !!active.sheetImageTransparent : !!e?.sheetPortraitTransparent,
      }
    })
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
