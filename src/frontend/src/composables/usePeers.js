import { ref } from 'vue'
import { buildAgencyIndex, entityTypeRank } from '@/constants/entityTypes.js'

// Peers shown in the strip above the sheet/roller bands: every entity at the
// current location (plus the location itself). The entity you act as comes first
// — the strip scrolls, so your own tab has to be reachable without hunting — and
// **everything after it is in the sheet's own order**: mains, supports, then by
// type, alphabetical inside each group. The same order the relationship list and
// the location tree use, through the same helper, so the three cannot drift.
//
// The full entity list is cached for PEERS_TTL_MS; SSE and location events call
// `fetchPeers(true)` to bypass it, panel opens reuse it.
const PEERS_TTL_MS = 30_000

export function usePeers({ graphql, currentLocationId, entityId, gmMode, entityNames, diag = () => {} }) {
  const peers = ref([])
  let peersCache = null  // { entities, agency, at }

  function applyPeers(entities, agency) {
    const atLocation = entities
      .filter(e => e.currentLocation === currentLocationId.value)
      .filter(e => gmMode.value || !e.unpublished)
    const here = entities.find(e => e.id === currentLocationId.value)
    const combined = here && !atLocation.some(e => e.id === here.id)
      ? [here, ...atLocation]
      : atLocation
    // The type order needs `agency` to tell a main from a support character — it
    // is where that distinction lives, not in the type. `entityTypeRank` falls
    // back to a plain `PC` for an entity nobody holds, and sorts an unknown type
    // last, so this is total: no peer can end up without a rank.
    const byName = { sensitivity: 'base' }
    peers.value = combined.sort((a, b) => {
      if (a.id === entityId.value) return -1
      if (b.id === entityId.value) return 1
      // Rank, then name, then id. The name is what makes the order
      // *deterministic* rather than merely grouped — the entity list arrives
      // unsorted (the query has no SORT) and a stable sort would preserve that
      // arbitrary order inside a type. The id is the last resort so two names
      // that compare equal (they differ only in case, which `base` ignores)
      // still land in a fixed order. Same three keys as `_sortOccupants`.
      return (entityTypeRank(a.type, agency?.get(a.id)) - entityTypeRank(b.type, agency?.get(b.id)))
        || String(a.name || '').localeCompare(String(b.name || ''), undefined, byName)
        || String(a.id).localeCompare(String(b.id))
    })
  }

  async function fetchPeers(force = false) {
    if (!force && peersCache && Date.now() - peersCache.at < PEERS_TTL_MS) {
      applyPeers(peersCache.entities, peersCache.agency)
      resolvePeerFaces()
      return
    }
    diag('fetchPeers-start', { currentLocationId: currentLocationId.value })
    // `players` rides along in the same request because the type order needs it
    // (main vs support lives on the agency edge, not on the entity). Measured at
    // ~35ms against the entity list's ~90–145ms, so it is far cheaper than the
    // second round trip it replaces; it shares this cache's TTL, which is what
    // keeps a character switch re-bucketing promptly.
    const data = await graphql(`query {
    entities { id type name currentLocation unpublished }
    players { id name agency { entityId main } }
  }`)
    if (data?.entities) {
      const agency = buildAgencyIndex(data.players)
      peersCache = { entities: data.entities, agency, at: Date.now() }
      entityNames.value = Object.fromEntries(data.entities.map(e => [e.id, e.name]).filter(([id]) => id))
      applyPeers(data.entities, agency)
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
