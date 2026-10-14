// Canonical GM entity types, in the order they appear in entity pickers.
// Values are the GraphQL enum member names (see EntityType in the API domain).
export const ENTITY_TYPES = ['CHARACTER', 'GMC', 'ASSET', 'FACTION', 'UNIVERSE', 'LOCATION']

// The types that carry a razmerit rating. A location is a place and a universe
// is a container — neither is rated — so a form must not offer the field for
// them. Shared because the create and edit panels both ask the question, and
// they had drifted: the edit form hid the field, the create form always showed
// it, so the same entity was authored differently depending on the door used.
export const RAZMERIT_TYPES = new Set(['CHARACTER', 'GMC', 'FACTION'])

/** Whether an entity type is rated, and so whether a form should offer razmerit. */
export function hasRazmerit(type) {
  return RAZMERIT_TYPES.has(String(type || '').toUpperCase())
}

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
 * The total order an entity list reads in: **rank → name → id**.
 *
 * All three keys are load-bearing. The entity list arrives unsorted (the
 * `entities` query has no `SORT`), so a stable sort alone would preserve that
 * arbitrary order *inside* a type; the name is what makes the order visible, and
 * the id is the last resort so two names that compare equal (they differ only in
 * case, which `sensitivity: 'base'` ignores) still land somewhere fixed.
 *
 * `agency` is the map {@link buildAgencyIndex} returns — without it there is no
 * main/support signal and every character is a plain `PC`.
 *
 * The location tree, the sheet's contacts and the peer strip each open-code these
 * same three keys; this is that comparison, named, for callers that want it.
 */
export function compareEntityOrder(a, b, agency) {
  return (entityTypeRank(a.type, agency?.get(a.id)) - entityTypeRank(b.type, agency?.get(b.id)))
    || String(a?.name || '').localeCompare(String(b?.name || ''), undefined, { sensitivity: 'base' })
    || String(a?.id).localeCompare(String(b?.id))
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

/**
 * Which players hold each entity, from the same `players { name agency }`
 * payload — the index a **player filter** needs (B188).
 *
 * Deliberately not {@link buildAgencyIndex}: that answers "which ONE player is
 * this" for the PC(MC)/PC(SC) buckets, and collapsing to a single holder would
 * make a character invisible to the filter under any *other* record that holds
 * it. One human's per-device identities each hold their characters, so
 * `character-20809` is held by eight player records live; a filter for one of
 * them must find it rather than lose to whichever record the bucket rule picked.
 *
 * `holders` is entity → the set of player ids holding it; `byPlayer` lists the
 * players worth offering, i.e. those holding something.
 */
export function buildPlayerHoldings(players) {
  const byPlayer = new Map()
  const holders = new Map()
  for (const p of players || []) {
    const edges = (p.agency || []).filter((e) => e?.entityId)
    if (!edges.length) continue
    byPlayer.set(p.id, { id: p.id, name: p.name || p.id })
    for (const e of edges) {
      if (!holders.has(e.entityId)) holders.set(e.entityId, new Set())
      holders.get(e.entityId).add(p.id)
    }
  }
  return { byPlayer, holders }
}

/** The empty {@link buildPlayerHoldings} shape, for callers with no players yet. */
export const NO_PLAYER_HOLDINGS = { byPlayer: new Map(), holders: new Map() }

