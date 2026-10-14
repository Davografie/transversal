// A scratch roll table for the B281 specs.
//
// These specs used to drive `rt-earth-regions` itself, which was a latent bug in
// two directions: they asserted on authored content (so the author working broke
// them) and they edited it (harmless while a Save button had to be pressed, and
// **not harmless once the panels auto-save**). A spec that types into a live
// document now writes to it.
//
// It lives in the *earth* universe with no owning path, so it lists under "Shared"
// in the Roll Tables panel — the route the specs already used.
import { gql } from './sheet.js'

export const SCRATCH = 'rt-e2e-scratch'
export const NAME = 'E2E Scratch Table'
export const LOCATION = 'location-india-55a094fc'

/** A pinned location — the shape that makes a resolved value `one`. */
export const SPEC = { steps: [{ kind: 'literal', element: 'location', value: LOCATION }] }

const READ = `query { rollTable(id: "${SCRATCH}") {
  id name boundVariables { name element cardinality spec }
  entries { key label boundVariables { name spec } } } }`

/** Create (or reset) the scratch table. Two rows; declare on either layer.
 *
 *  `reservedSlots` are the table's **reservations** ([[B285]]): `{name, element,
 *  cardinality}` with no value, which each row's `rowVariables` then assigns — and
 *  which an assignment resolving anything else is refused against.
 *
 *  `rowValues` maps a row key to the names that row assigns, for a spec that needs
 *  the two rows to differ — an assignment resolving `many`, say, which the API only
 *  accepts while the table still reserves nothing. */
export async function seedScratch(
  request,
  { rowVariables = [], tableVariables = [], reservedSlots = [], rowValues = null } = {},
) {
  const assigned = (key) => {
    if (rowValues) return (rowValues[key] || []).map((v) => ({ name: v.name, spec: v.spec }))
    return rowVariables.map((n) => ({ name: n, spec: SPEC }))
  }
  await gql(
    request,
    `mutation($input: RollTableInput!){ saveRollTable(input:$input){ id } }`,
    { input: {
      id: SCRATCH, name: NAME, universe: 'earth', lifePath: null, subjectKind: '',
      scheme: 'RANGE', rollSource: 'FIXED_DIE', traitDiceCount: 1, die: 'd100', check: null,
      boundVariables: [
        ...tableVariables.map((n) => ({ name: n, spec: SPEC })),
        // A reservation states a type and no path — the shape the API keeps only at
        // the table level, and the one every row's assignment is checked against.
        ...reservedSlots.map((s) => ({ name: s.name, element: s.element,
                                       cardinality: s.cardinality || 'one', spec: null })),
      ],
      entries: [
        { key: 'india', label: 'India', description: '', minValue: 1, maxValue: 12,
          conditions: [], costEffects: [], effects: [], boundVariables: assigned('india') },
        { key: 'other', label: 'Other', description: '', minValue: 13, maxValue: 24,
          conditions: [], costEffects: [], effects: [], boundVariables: assigned('other') },
      ],
    } },
  )
}

export async function dropScratch(request) {
  await gql(request, `mutation { deleteRollTable(id: "${SCRATCH}") }`)
}

/** The stored table — `gql` already returns `data` and throws on `errors`. */
export async function readScratch(request) {
  return (await gql(request, READ)).rollTable
}
