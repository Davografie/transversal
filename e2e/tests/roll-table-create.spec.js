// Creating a roll table from the GM panel's group — the author's report.
//
// *"Just tried creating a shared roll table, but the auto-save doesn't seem to
// create new tables."* Exactly right, and for a structural reason: the auto-save
// returns early when the document has no id (there is nothing to write onto), and
// nothing minted one — the panel had **no Create affordance at all**, so a new table
// could not be saved by any route, while the readout said "Edits save as you make
// them." [[B225]]'s rule, applied here: create is the one deliberate act, and the
// auto-save arms afterwards.
//
// Two things only a browser proves, and the second is the one that would bite
// silently: the Create button appears in create mode, and the id the server mints is
// **adopted** — otherwise the panel keeps looking new and the next edit creates a
// second table instead of updating the first.
//
// SEC-3: identity is a server session, so the spec enters as the architect and takes
// the testing player's session (`helpers/session.js`).
import { test, expect } from '@playwright/test'
import { gql } from '../helpers/sheet.js'
import { asArchitect } from '../helpers/arrange.js'
import { establishSession } from '../helpers/session.js'

const KAEL = 'character-kael-drift-e555ccde'
const NAME = 'E2E Created Table'
const RENAMED = 'E2E Created Table v2'
const READ = `query { rollTables { id name lifePath universe } }`

let owner
test.beforeAll(async ({ request }) => {
  const { players } = await gql(request, `query { players { id name agency { entityId main } } }`)
  owner = players.find((p) => (p.agency || []).some((a) => a.entityId === KAEL && a.main))
  if (!owner) throw new Error(`no player mains ${KAEL} — cannot reach the testing character`)
})

test.afterEach(async ({ page }) => {
  // Whatever the run got to: the scratch table is named after this spec, so both
  // spellings are cleaned up and nothing authored is touched.
  const { rollTables } = await gql(page.request, READ)
  for (const t of rollTables.filter((x) => x.name.startsWith(NAME))) {
    await gql(page.request, `mutation($id:ID!){ deleteRollTable(id:$id) }`, { id: t.id })
  }
  await page.unrouteAll({ behavior: 'ignoreErrors' })
})

async function bootApp(page) {
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
}

/** GM panel → Prep → the Earth universe → 🎲 Roll Tables → the **Shared** group. */
async function openSharedGroup(page) {
  await page.locator('.gm-toggle').click()
  await page.locator('.mode-tabs').waitFor({ state: 'visible', timeout: 20000 })
  await page.locator('.mode-tabs button', { hasText: 'Prep' }).click()
  const earth = page.locator('.entity-row.tree-row', { hasText: 'Earth' }).first()
  await earth.waitFor({ state: 'visible', timeout: 20000 })
  await earth.click()
  await page.locator('.section-btn', { hasText: 'Roll Tables' }).click()

  const shared = page.locator('.rtp-group', { hasText: 'Shared' }).first()
  await shared.waitFor({ state: 'visible', timeout: 20000 })
  await shared.click()
  await expect(page.locator('.rtg-add-btn')).toBeVisible({ timeout: 20000 })
}

test('a new shared table is created, and the next edit updates it', async ({ page }) => {
  await bootApp(page)
  const problems = []
  page.on('pageerror', (e) => problems.push('uncaught: ' + String(e)))
  page.on('console', (m) => {
    if (m.type() === 'error' && /\[Vue warn\]/.test(m.text())) problems.push(m.text())
  })

  await openSharedGroup(page)
  await page.locator('.rtg-add-btn').click()
  await expect(page.locator('.rte-root')).toBeVisible({ timeout: 20000 })

  // Create mode: the auto-save has nothing to write onto, so there is one deliberate
  // act — and it stays disabled until it has a name.
  const create = page.locator('.rte-create')
  await expect(create).toBeVisible({ timeout: 20000 })
  await expect(create).toBeDisabled()
  const name = page.locator('.rte-root input[placeholder="Table name…"]')
  await name.fill(NAME)
  await expect(create).toBeEnabled()

  const created = page.waitForResponse(
    (r) => (r.request().postData() || '').includes('saveRollTable'), { timeout: 20000 })
  await create.click()
  await created

  // The id was adopted, so the panel is an editor now and not a create form: the
  // create prompt is gone. (Its readout reads "Saved" straight after the write, so
  // asserting the *steady-state* sentence here would be a race.)
  await expect(page.locator('.rte-create')).toHaveCount(0, { timeout: 20000 })
  await expect(page.locator('.rte-save-state')).not.toContainText('Not created yet')

  // A **cold read** of the store: a passing mutation response is not a stored row.
  await expect.poll(async () => {
    const { rollTables } = await gql(page.request, READ)
    return rollTables.filter((t) => t.name === NAME).length
  }, { timeout: 20000 }).toBe(1)

  // The half that would bite silently — an edit updates that table. Without the
  // adoption this creates a **second** table, and the panel never says so.
  const saved = page.waitForResponse(
    (r) => (r.request().postData() || '').includes('saveRollTable'), { timeout: 20000 })
  await name.fill(RENAMED)
  await saved
  await expect.poll(async () => {
    const { rollTables } = await gql(page.request, READ)
    return [
      rollTables.filter((t) => t.name === NAME).length,
      rollTables.filter((t) => t.name === RENAMED).length,
    ]
  }, { timeout: 20000 }).toEqual([0, 1])

  expect(problems, problems.join('\n')).toEqual([])
})
