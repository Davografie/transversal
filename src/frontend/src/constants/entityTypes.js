// Canonical GM entity types, in the order they appear in entity pickers.
// Values are the GraphQL enum member names (see EntityType in the API domain).
export const ENTITY_TYPES = ['CHARACTER', 'GMC', 'ASSET', 'FACTION', 'UNIVERSE', 'LOCATION']

// The buckets an entity list groups by, in the order it shows them.
//
// Characters are the only type that splits, and `memberTypeBadge` (which calls
// every character a `PC`) cannot express it: `agency` is where main vs support
// actually lives — a player edge that is *not* the main is a support character,
// and a character nobody plays has no agency edge at all and stays a plain `PC`.
// Everything else is its own type.
export const ENTITY_TYPE_ORDER = ['PC(MC)', 'PC(SC)', 'PC', 'GMC', 'ASSET', 'FACTION', 'LOCATION', 'UNIVERSE']

/** Which bucket an entity belongs to, given its type and its `agency` edge. */
export function entityTypeBucket(type, agency) {
  const t = String(type || '').toUpperCase()
  if (t === 'CHARACTER') {
    if (!agency) return 'PC'
    return agency.main ? 'PC(MC)' : 'PC(SC)'
  }
  return t
}

/** Its position in {@link ENTITY_TYPE_ORDER}; an unknown type sorts last. */
export function entityTypeRank(type, agency) {
  const i = ENTITY_TYPE_ORDER.indexOf(entityTypeBucket(type, agency))
  return i === -1 ? ENTITY_TYPE_ORDER.length : i
}

/**
 * The single holder per entity, from a `players { agency }` payload — the map
 * {@link entityTypeRank} wants, in one read.
 *
 * `Entity.agency` on its own resolves with queries of its own, which is fine for
 * a sheet's handful of contacts and ruinous over a whole entity tree, so callers
 * that need it for many entities read the players instead. An entity can be held
 * by several player records (one human's per-device identities), so the holder
 * is picked the way the backend's `get_agency_for_entity` picks it — a `main`
 * claim first, then the lowest player id — or the client's bucket could disagree
 * with a per-entity read.
 */
export function buildAgencyIndex(players) {
  const map = new Map()
  for (const p of players || []) {
    for (const edge of p.agency || []) {
      const held = map.get(edge.entityId)
      if (!held || (edge.main && !held.main) ||
          (edge.main === held.main && String(p.id) < String(held.playerId))) {
        map.set(edge.entityId, { playerId: p.id, main: !!edge.main })
      }
    }
  }
  return map
}

