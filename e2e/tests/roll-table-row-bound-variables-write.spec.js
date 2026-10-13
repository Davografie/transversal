// A row's bound variables, read and written **through the UI** (B281).
//
// The mount spec next door proves the panel opens; this one proves the panel's
// save reaches the database and does not drop what it read. That distinction is
// the whole point: the row editor has *two* contracts — opened from the table
// panel it edits that panel's live row draft and persists nothing, and the table
// panel's own Save is the only commit point — and every writer here replaces the
// whole document, which is how a field gets erased ([[B273]], [[B274]], [[B279]],
// and [[B281]] one level down).
//
// The declaration is seeded through the API and then only *renamed* in the UI,
// deliberately: driving the target-path builder from a spec is brittle, and what
// needs proving is the round trip, not the builder.
//
// It runs against a **scratch table** created and deleted by the spec, so it never
// touches authored content.
import { test, expect } from '@playwright/test'
import { gql } from '../helpers/sheet.js'
import { asArchitect } from '../helpers/arrange.js'
import { establishSession } from '../helpers/session.js'

const KAEL = 'character-kael-drift-e555ccde'
const SCRATCH = 'rt-e2e-bv-write'
const NAME = 'E2E Bound Variables Scratch'
const LOCATION = 'location-india-55a094fc'
const ORIGINAL = 'picked_location'

const SPEC = { steps: [{ kind: 'literal', element: 'location', value: LOCATION }] }

let owner
test.beforeAll(async ({ request }) => {
  const { players } = await gql(request, `query { players { id name agency { entityId main } } }`)
  owner = players.find((p) => (p.agency || []).some((a) => a.entityId === KAEL && a.main))
  if (!owner) throw new Error(`no player mains ${KAEL} — cannot reach the testing character`)
})

const READ = `query { rollTable(id: "${SCRATCH}") {
  id name boundVariables { name } entries { key label boundVariables { name spec } } } }`

async function stored(request) {
  // `gql` returns `body.data` already, and throws on `errors`.
  return (await gql(request, READ)).rollTable
}

async function seed(request, { rowVariables = [ORIGINAL], tableVariables = [] } = {}) {
  const res = await gql(
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
  if (res.errors) throw new Error('seed: ' + JSON.stringify(res.errors))
}

test.afterEach(async ({ request }) => {
  await gql(request, `mutation { deleteRollTable(id: "${SCRATCH}") }`)
})

/** GM panel → Prep → Earth's editor → 🎲 Roll Tables → Shared → the scratch table. */
async function openScratchTable(page) {
  await asArchitect(page)
  await page.addInitScript(([pid, pname]) => {
    localStorage.setItem('playerId', pid)
    localStorage.setItem('playerName', pname)
    localStorage.setItem('entityId', '')
    localStorage.setItem('architectMode', 'true')
  }, [owner.id, owner.name])
  await page.goto('/')
  await establishSession(page)
  await page.goto('/')
  await page.locator('.name-entry.panel').first().waitFor({ state: 'hidden', timeout: 20000 })

  await page.locator('.gm-toggle').click()
  await page.locator('.mode-tabs').waitFor({ state: 'visible', timeout: 20000 })
  await page.locator('.mode-tabs button', { hasText: 'Prep' }).click()
  const earth = page.locator('.entity-row.tree-row', { hasText: 'Earth' }).first()
  await earth.waitFor({ state: 'visible', timeout: 20000 })
  await earth.click()
  await page.locator('.section-btn', { hasText: 'Roll Tables' }).click()
  await page.locator('.rtp-group', { hasText: 'Shared' }).first().click()

  const row = page.locator('.entity-name', { hasText: new RegExp(`^${NAME}$`) }).first()
  await row.waitFor({ state: 'visible', timeout: 20000 })
  await row.click()
  await expect(page.locator('.rte-root')).toBeVisible({ timeout: 20000 })
  // The panel renders *before* its fetch resolves, and its Save writes whatever
  // `form.entries` holds — so clicking Save any earlier saves an empty table.
  // Waiting for the rows is what makes the save meaningful.
  await expect(page.locator('.rte-entry-body')).toHaveCount(2, { timeout: 20000 })
}

/** Click the table's Save and wait for the mutation to come back.
 *
 *  Waiting matters for the erasure tests: the seeded state already holds the
 *  declaration, so a poll for it passes before the save has even happened and
 *  proves nothing. */
async function saveTable(page) {
  const done = page.waitForResponse(
    (r) => r.url().includes('/graphql') && (r.request().postData() || '').includes('saveRollTable'),
    { timeout: 20000 },
  )
  await page.locator('.rte-save').click()
  await done
}

test('the row editor reads back a row\'s declaration', async ({ page, request }) => {
  await seed(request)
  await openScratchTable(page)
  await expect(page.locator('.rte-root')).toBeVisible({ timeout: 20000 })

  await page.locator('.rte-edit').first().click()
  await expect(page.locator('.eep-root')).toBeVisible({ timeout: 20000 })
  // The declaration the server holds is on screen, by name — a writer that fetched
  // the entries without the field would show an empty section here.
  await expect(page.locator('.eep-root .bv-name').first()).toHaveValue(ORIGINAL)
})

test('saving a table from the panel keeps every row\'s declaration', async ({ page, request }) => {
  await seed(request)
  await openScratchTable(page)

  // Touch nothing; just save the document the panel is holding. This is the pure
  // erasure check: the whole `entries` list is replaced on save, so a field the
  // panel read but did not send back is gone.
  await saveTable(page)

  await expect.poll(async () => {
    const t = await stored(request)
    return (t?.entries || []).find((e) => e.key === 'india')?.boundVariables?.map((b) => b.name)
  }, { timeout: 15000, intervals: [500, 1000] }).toEqual([ORIGINAL])

  // …and the *path* survives, not just the name: a declaration that persists
  // nameless, or with its spec emptied, would resolve to nothing at run time.
  const t = await stored(request)
  const india = t.entries.find((e) => e.key === 'india')
  expect(india.boundVariables[0].spec).toEqual(SPEC)
})

test('renaming a row\'s declaration in the editor persists, spec and all', async ({ page, request }) => {
  await seed(request)
  await openScratchTable(page)

  await page.locator('.rte-edit').first().click()
  await expect(page.locator('.eep-root')).toBeVisible({ timeout: 20000 })
  await page.locator('.eep-root .bv-name').first().fill('picked_place')

  // "Save entry" only writes into the table panel's live draft…
  await page.locator('.eep-save').click()
  await expect(page.locator('.eep-root')).toBeHidden({ timeout: 20000 })
  // …so the table panel's own Save is the commit point. Both are clicked here on
  // purpose: a person who presses only the first has saved nothing.
  await saveTable(page)

  await expect.poll(async () => {
    const t = await stored(request)
    return (t?.entries || []).find((e) => e.key === 'india')?.boundVariables?.map((b) => b.name)
  }, { timeout: 15000, intervals: [500, 1000] }).toEqual(['picked_place'])

  const t = await stored(request)
  const india = t.entries.find((e) => e.key === 'india')
  expect(india.boundVariables[0].spec).toEqual(SPEC)
  // The sibling row is untouched, and the table's own layer is not invented.
  expect(t.entries.find((e) => e.key === 'other').boundVariables).toEqual([])
  expect(t.boundVariables).toEqual([])
})

test('the table\'s own declarations survive a save that only touched a row', async ({ page, request }) => {
  // Both layers seeded: the point is that editing one does not disturb the other.
  await seed(request, { rowVariables: [ORIGINAL], tableVariables: ['flagged'] })
  await openScratchTable(page)

  await page.locator('.rte-edit').first().click()
  await expect(page.locator('.eep-root')).toBeVisible({ timeout: 20000 })
  await page.locator('.eep-root .bv-name').first().fill('picked_place')
  await page.locator('.eep-save').click()
  await expect(page.locator('.eep-root')).toBeHidden({ timeout: 20000 })
  await saveTable(page)

  await expect.poll(async () => {
    const t = await stored(request)
    return (t?.boundVariables || []).map((b) => b.name)
  }, { timeout: 15000, intervals: [500, 1000] }).toEqual(['flagged'])

  // …and the row's edit landed too, so "the table layer survived" is not a
  // consequence of the save having done nothing at all.
  const t = await stored(request)
  expect(t.entries.find((e) => e.key === 'india').boundVariables.map((b) => b.name))
    .toEqual(['picked_place'])
})
