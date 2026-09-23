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

