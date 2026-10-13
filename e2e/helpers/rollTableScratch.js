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
  id name boundVariables { name spec } entries { key label boundVariables { name spec } } } }`

/** Create (or reset) the scratch table. Two rows; declare on either layer. */
export async function seedScratch(request, { rowVariables = [], tableVariables = [] } = {}) {
  await gql(
    request,
    `mutation($input: RollTableInput!){ saveRollTable(input:$input){ id } }`,
    { input: {
      id: SCRATCH, name: NAME, universe: 'earth', lifePath: null, subjectKind: '',
      scheme: 'RANGE', rollSource: 'FIXED_DIE', traitDiceCount: 1, die: 'd100', check: null,
      boundVariables: tableVariables.map((n) => ({ name: n, spec: SPEC })),
      entries: [
        { key: 'india', label: 'India', description: '', minValue: 1, maxValue: 12,
          conditions: [], costEffects: [], effects: [],
          boundVariables: rowVariables.map((n) => ({ name: n, spec: SPEC })) },
        { key: 'other', label: 'Other', description: '', minValue: 13, maxValue: 24,
          conditions: [], costEffects: [], effects: [], boundVariables: [] },
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
