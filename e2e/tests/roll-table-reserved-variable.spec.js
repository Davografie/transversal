// A roll table **reserving** a typed name, and a row assigning it (B285).
//
// The author's problem, in their words: *"authoring all Where on Earth entries can
// yield inconsistent `{picked_location}`s. A `{picked_location}` should be
// `location/one`, but if I make a mistake it could become `location/many` or
// something, breaking down-the-line processes."* Before this, a name's type was only
// as consistent as every hand-written path that happened to use it — so the table now
// states the type once and each row assigns it.
//
// Two things are only true in a browser, which is why this is a spec and not a unit
// test: the **slot editor** is a component (an element picker where a path builder
// used to be), and the **assignment picker** reaches the row editor through the
// panel's `context` — a child panel cannot inject its parent's provide, so a missing
// key there leaves the picker empty with no error anywhere.
//
// It runs against a **scratch table**: the panels auto-save, so a spec that typed
// into `rt-earth-regions` would write to authored content.
//
// SEC-3: identity is a server session, so the spec enters as the architect and takes
// the testing player's session (`helpers/session.js`); `ARCHITECT_TOKEN` must be in
// the environment.
import { test, expect } from '@playwright/test'
import { gql } from '../helpers/sheet.js'
import { asArchitect } from '../helpers/arrange.js'
import { establishSession } from '../helpers/session.js'
import { NAME, SPEC, dropScratch, readScratch, seedScratch } from '../helpers/rollTableScratch.js'

const KAEL = 'character-kael-drift-e555ccde'
const SLOT = 'picked_location'

let owner
test.beforeAll(async ({ request }) => {
  const { players } = await gql(request, `query { players { id name agency { entityId main } } }`)
  owner = players.find((p) => (p.agency || []).some((a) => a.entityId === KAEL && a.main))
  if (!owner) throw new Error(`no player mains ${KAEL} — cannot reach the testing character`)
})

test.afterEach(async ({ request }) => {
  await dropScratch(request)
})

/** Seed the identity, load the app as an architect, and let the boot settle.
 *
 *  Deliberately *stops* before the GM panel, so a spec can attach its console
 *  watchers afterwards — Firefox reports `NS_BINDING_ABORTED` as an uncaught
 *  `NetworkError` for requests the second `goto` cancels mid-flight, which is
 *  browser noise on navigation and would fail every spec on that engine. */
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

/** GM panel → Prep → the Earth universe's editor → 🎲 Roll Tables → Shared → the
 *  scratch table. Leaves the table panel open. */
async function openTablePanel(page) {
  await page.locator('.gm-toggle').click()
  await page.locator('.mode-tabs').waitFor({ state: 'visible', timeout: 20000 })
  await page.locator('.mode-tabs button', { hasText: 'Prep' }).click()

  // The universe's own editor is where the 🎲 Roll Tables section lives, and it is
  // also what fixes the panel's universe to `earth` — which is what puts a table with
  // no owning path under "Shared" rather than "Fundamental".
  const earth = page.locator('.entity-row.tree-row', { hasText: 'Earth' }).first()
  await earth.waitFor({ state: 'visible', timeout: 20000 })
  await earth.click()
  const section = page.locator('.section-btn', { hasText: 'Roll Tables' })
  await section.waitFor({ state: 'visible', timeout: 20000 })
  await section.click()

  const shared = page.locator('.rtp-group', { hasText: 'Shared' }).first()
  await shared.waitFor({ state: 'visible', timeout: 20000 })
  await shared.click()

  const table = page.locator('.entity-name', { hasText: new RegExp(`^${NAME}$`) }).first()
  await table.waitFor({ state: 'visible', timeout: 20000 })
  await table.click()
  await expect(page.locator('.rte-root')).toBeVisible({ timeout: 20000 })
  // The panel renders before its fetch resolves; wait for the rows so the editor is
  // always driven against a loaded document.
  await expect(page.locator('.rte-entry-body')).toHaveCount(2, { timeout: 20000 })
}

/** Anything the page threw, or any Vue complaint, collected as a failure list. */
function watchProblems(page) {
  const problems = []
  page.on('pageerror', (e) => problems.push('uncaught: ' + String(e)))
  page.on('console', (m) => {
    if (m.type() === 'error' && /\[Vue warn\]/.test(m.text())) problems.push(m.text())
  })
  return problems
}

test('the table editor authors a reserved slot, and it is still there after a reload', async ({ page, request }) => {
  await seedScratch(request)
  await bootApp(page)
  const problems = watchProblems(page)
  await openTablePanel(page)

  // The slot affordance is the table's alone: a row assigns a name, it does not
  // state one, so the row editor must not offer this.
  const slot = page.locator('.rte-root .bv-add-slot')
  await expect(slot).toBeVisible({ timeout: 20000 })
  await slot.click()

  const row = page.locator('.rte-root .bv-row').last()
  await row.locator('.bv-name').fill(SLOT)
  await row.locator('.bv-slot select').first().selectOption('location')
  await row.locator('.bv-slot select').nth(1).selectOption('one')

  // Auto-save: the write is the panel's, so wait for it rather than for the UI.
  await page.waitForResponse(
    (r) => (r.request().postData() || '').includes('saveRollTable'), { timeout: 20000 })

  // A cold read of the *stored* table: the mutation's own response would pass even if
  // the read half never carried the type, which is the bug this file exists for.
  await expect.poll(async () => {
    const t = await readScratch(page.request)
    return (t?.boundVariables || []).map((b) => `${b.name}:${b.element}/${b.cardinality}`)
  }, { timeout: 20000 }).toContain(`${SLOT}:location/one`)

  // …and the reload, which is where the read half actually fails.
  await page.reload()
  await page.waitForTimeout(2000)
  if (!(await page.locator('.rte-root').count())) await openTablePanel(page)

  const shown = page.locator('.rte-root .bv-row').last()
  await expect(shown.locator('.bv-name')).toHaveValue(SLOT, { timeout: 20000 })
  await expect(shown.locator('.bv-slot select').first()).toHaveValue('location')
  // The catalog's own label, which is capitalised — the *value* is `location`.
  await expect(shown.locator('.bv-type')).toContainText(/location/i)

  expect(problems, problems.join('\n')).toEqual([])
})

test('a row editor offers the reserved name, and shows a bad assignment in red', async ({ page, request }) => {
  // Seeded **free-form**: the row assigns the name from a collection, which resolves
  // `location/many` — the drift itself. The API accepts it only while the table
  // reserves nothing, which is exactly the state the author is in before they protect
  // the name; reserving it is what turns the drift into an error they can see.
  await seedScratch(request, {
    rowValues: { india: [{ name: SLOT, spec: { steps: [{ kind: 'select', collection: 'locations' }] } }] },
  })
  await bootApp(page)
  const problems = watchProblems(page)
  await openTablePanel(page)

  // Reserve the name the row already assigns. The table now contradicts itself, so
  // the panel's own auto-save is refused — and with no Save button, the readout is
  // the only place that can say so.
  const slot = page.locator('.rte-root .bv-add-slot')
  await expect(slot).toBeVisible({ timeout: 20000 })
  await slot.click()
  const decl = page.locator('.rte-root .bv-row').last()
  await decl.locator('.bv-name').fill(SLOT)
  await decl.locator('.bv-slot select').first().selectOption('location')

  const refusal = page.locator('.rte-root .rte-save-state.rte-save-error')
  await expect(refusal).toBeVisible({ timeout: 20000 })
  await expect(refusal).toContainText('location/many')
  await expect(refusal).toContainText(SLOT)

  // The row's own editor is where the author has to be told, before they walk away:
  // the name becomes a **picker** of the table's reserved slots…
  const edit = page.locator('.rte-edit').first()
  await edit.waitFor({ state: 'visible', timeout: 20000 })
  await edit.click()
  await expect(page.locator('.eep-root')).toBeVisible({ timeout: 20000 })

  const name = page.locator('.eep-root .bv-name')
  await expect(name).toHaveJSProperty('tagName', 'SELECT')
  await expect(name.locator('option', { hasText: SLOT })).toHaveCount(1)

  // …and the assignment that resolves `many` against a `one` slot is shown refused.
  const shadow = page.locator('.eep-root .bv-shadows').first()
  await expect(shadow).toBeVisible({ timeout: 20000 })
  await expect(shadow).toContainText(SLOT)
  await expect(shadow).toContainText('several')
  await expect(page.locator('.eep-root .bv-collide').first()).toBeVisible()

  expect(problems, problems.join('\n')).toEqual([])
})

test.afterEach(async ({ page }) => {
  await page.unrouteAll({ behavior: 'ignoreErrors' })
})
