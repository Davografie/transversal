/**
 * Per-entity-type sheet profiles.
 *
 * One sheet shell, three faces. Everything expensive in `CharacterSheet.vue` —
 * the trait list, the container recursion, the trait editor, the detail panel,
 * the tag/markdown rendering — is already type-agnostic, so a second and third
 * sheet would only duplicate it. What actually differs between an occupant, a
 * location and a faction is small and declarative: **which tabs exist** and
 * **which header extras apply**. That is all this file decides.
 *
 * The distinction it draws is about what the entity *is*, not who is looking:
 *
 *   - an **occupant** carries a body — a character, a GMC, or an asset. It has
 *     razmerit, it can be assumed, it travels, and it progresses through life
 *     paths. This is the sheet as it has always been.
 *   - a **location** is a place. It has traits (the live data is rich — 226
 *     locations hold 1,897 trait settings) and a blue book, but no razmerit
 *     (`GmEntityForm.vue` excludes LOCATION from `RAZMERIT_TYPES`) and no life
 *     paths, which are faction-bound.
 *   - a **faction** is an organisation. It has traits, razmerit (62 of 74 live
 *     factions carry some) and a **roster** — its members, which live on
 *     `membership` edges and read through `factionMembers`.
 *
 * Anything else — `universe`, and the two pseudo-types `subtrait` and
 * `relation` — falls back to the occupant profile on purpose: it is what those
 * entities render today, so nothing that is not being designed here moves.
 *
 * A profile may only *remove* affordances that are meaningless for the type.
 * It must never gate the trait machinery: every profile carries `traits`, which
 * is asserted in `scripts/check-sheet-profile.mjs`.
 */

/** The tabs a sheet can show. `relation` is not here — it is conditional on the
 *  viewer holding ties, not on the type (see `showRelationTab` in the sheet). */
export const SHEET_TABS = Object.freeze({
  PROFILE: 'profile',
  TRAITS: 'traits',
  BLUEBOOK: 'bluebook',
  LIFEPATH: 'lifepath',
  ROSTER: 'roster',
  TIES: 'ties',
})

/** The fallback view when the current one is not available for this type. */
export const DEFAULT_SHEET_TAB = SHEET_TABS.TRAITS

/** The entity types that carry a body. */
export const OCCUPANT_TYPES = Object.freeze(['CHARACTER', 'GMC', 'ASSET'])

const OCCUPANT_PROFILE = Object.freeze({
  kind: 'occupant',
  razmerit: true,
  tabs: Object.freeze([SHEET_TABS.PROFILE, SHEET_TABS.TRAITS, SHEET_TABS.BLUEBOOK, SHEET_TABS.LIFEPATH]),
})

const LOCATION_PROFILE = Object.freeze({
  kind: 'location',
  razmerit: false,
  // `ties` is the incoming half of the relation surface: what others hold about
  // this place. It is declared here but the sheet only *shows* it when there is
  // something in it (see `showTiesTab`), the same convention the relation tab
  // follows — for 353 of 410 locations the tab would otherwise open onto
  // nothing.
  tabs: Object.freeze([SHEET_TABS.PROFILE, SHEET_TABS.TRAITS, SHEET_TABS.TIES, SHEET_TABS.BLUEBOOK]),
})

const FACTION_PROFILE = Object.freeze({
  kind: 'faction',
  razmerit: true,
  tabs: Object.freeze([SHEET_TABS.PROFILE, SHEET_TABS.TRAITS, SHEET_TABS.ROSTER, SHEET_TABS.BLUEBOOK]),
})

const PROFILES = Object.freeze({
  CHARACTER: OCCUPANT_PROFILE,
  GMC: OCCUPANT_PROFILE,
  ASSET: OCCUPANT_PROFILE,
  LOCATION: LOCATION_PROFILE,
  FACTION: FACTION_PROFILE,
})

/**
 * The profile for an entity type.
 *
 * `type` is normalised, because the same enum arrives as the stored lowercase
 * (`entity_types: ['character']` in the DB) and as the GraphQL name uppercase
 * (`App.vue` compares `type === 'LOCATION'`). Keying on one spelling would
 * silently hand a location the occupant profile.
 */
export function sheetProfileFor(entityType) {
  return PROFILES[normaliseType(entityType)] || OCCUPANT_PROFILE
}

/** Whether this type carries a body. */
export function isOccupantType(entityType) {
  return OCCUPANT_TYPES.includes(normaliseType(entityType))
}

/**
 * An entity type, as this file keys on it.
 *
 * Trimmed as well as upper-cased: an unrecognised spelling falls back to the
 * *occupant* profile, so a padded `' location '` would hand a place the full
 * character sheet — razmerit, life paths and all. Correcting it is the safer
 * failure, and an enum read has no legitimate whitespace to preserve.
 */
function normaliseType(entityType) {
  return String(entityType ?? '').trim().toUpperCase()
}

/** Whether a profile offers a tab. */
export function hasSheetTab(profile, tab) {
  return !!profile && profile.tabs.includes(tab)
}
