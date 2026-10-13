// A row's bound variables, read and written **through the UI**, with auto-save (B281).
//
// The mount spec next door proves the panel opens; this one proves an edit reaches
// the database and does not drop what the panel read. Both halves matter: every
// writer here replaces the whole document, which is how a field gets erased
// ([[B273]], [[B274]], [[B279]], and [[B281]] one level down — where the *read* map
// was the half that was missing and an author's work vanished).
//
// There are **no Save buttons** any more: the panels auto-save (B211's convention,
// the human 2026-10-13). So each test makes an edit and waits for the write it
// triggers, rather than pressing anything.
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
  // The panel renders before its fetch resolves; wait for the rows so an edit
  // cannot be made against a half-loaded document.
  await expect(page.locator('.rte-entry-body')).toHaveCount(2, { timeout: 20000 })
}

/** Arm a waiter for the next auto-save, do `act`, and let the write land.
 *
 *  Waiting for the *response* is what makes these tests mean something: the seeded
 *  state already holds what some of them assert, so a poll for the value alone would
 *  pass before the save had happened. */
async function editAndWaitForSave(page, act) {
  const done = page.waitForResponse(
    (r) => r.url().includes('/graphql') && (r.request().postData() || '').includes('saveRollTable'),
    { timeout: 20000 },
  )
  await act()
  await done
}

test('the row editor reads back a row\'s declaration', async ({ page, request }) => {
  await seed(request)
  await openScratchTable(page)

  await page.locator('.rte-edit').first().click()
  await expect(page.locator('.eep-root')).toBeVisible({ timeout: 20000 })
  // The declaration the server holds is on screen, by name — a writer that fetched
  // the entries without the field would show an empty section here.
  await expect(page.locator('.eep-root .bv-name').first()).toHaveValue(ORIGINAL)
})

test('adding a row does not erase another row\'s declaration', async ({ page, request }) => {
  await seed(request)
  await openScratchTable(page)

  // The pure erasure check, in its auto-save form. `entries` is replaced whole on
  // every write, so a read map that dropped `boundVariables` loses it the moment
  // anything else in the table is edited — which is how the author's work vanished.
  await editAndWaitForSave(page, () => page.locator('.rte-add').click())

  await expect.poll(async () => {
    const t = await stored(request)
    return (t?.entries || []).find((e) => e.key === 'india')?.boundVariables?.map((b) => b.name)
  }, { timeout: 15000, intervals: [500, 1000] }).toEqual([ORIGINAL])

  // …and the *path* survives, not just the name: a declaration that persists
  // nameless, or with its spec emptied, would resolve to nothing at run time.
  const t = await stored(request)
  expect(t.entries.find((e) => e.key === 'india').boundVariables[0].spec).toEqual(SPEC)
})

test('renaming a row\'s declaration in the editor persists, spec and all', async ({ page, request }) => {
  await seed(request)
  await openScratchTable(page)

  await page.locator('.rte-edit').first().click()
  await expect(page.locator('.eep-root')).toBeVisible({ timeout: 20000 })

  // No Save entry any more: the row writes into the table panel's live draft as it
  // is edited, and *that* panel's auto-save is the write. So the edit is made and
  // the write awaited — nothing is pressed in between.
  await editAndWaitForSave(page, () =>
    page.locator('.eep-root .bv-name').first().fill('picked_place'))

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

test('the table\'s own declarations survive an edit that only touched a row', async ({ page, request }) => {
  // Both layers seeded: the point is that editing one does not disturb the other.
  await seed(request, { rowVariables: [ORIGINAL], tableVariables: ['flagged'] })
  await openScratchTable(page)

  await page.locator('.rte-edit').first().click()
  await expect(page.locator('.eep-root')).toBeVisible({ timeout: 20000 })
  await editAndWaitForSave(page, () =>
    page.locator('.eep-root .bv-name').first().fill('picked_place'))

  await expect.poll(async () => {
    const t = await stored(request)
    return (t?.boundVariables || []).map((b) => b.name)
  }, { timeout: 15000, intervals: [500, 1000] }).toEqual(['flagged'])

  // …and the row's edit landed too, so "the table layer survived" is not a
  // consequence of the write having done nothing at all.
  const t = await stored(request)
  expect(t.entries.find((e) => e.key === 'india').boundVariables.map((b) => b.name))
    .toEqual(['picked_place'])
})
