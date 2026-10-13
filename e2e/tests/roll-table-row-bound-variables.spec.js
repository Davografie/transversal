// A roll table **row**'s own bound variables (B281), reached the way a GM reaches
// them: the entity editor's 🎲 Roll Tables → the table → a row's ✎.
//
// This exists as a browser test because of how the first version failed. The row
// editor called `useBoundVariableScope` *above* the `form` declaration, and the
// composable's watcher is `immediate`, so it evaluated `computed(() =>
// form.boundVariables)` during `<script setup>` — inside the temporal dead zone:
//
//   ReferenceError: Cannot access 'form' before initialization
//     at ComputedRefImpl.fn (GmRollTableEntryEditPanel.vue:128)
//
// The build minified cleanly, all 32 check scripts passed, the entire API suite
// passed and the schema validated. None of them *can* see it: a TDZ error does not
// exist until the line runs. One click found it. So the mount is the assertion
// here, with the console watched.
//
// It runs against a **scratch table**: the panels auto-save now, so a spec that
// typed into `rt-earth-regions` would write to authored content.
//
// SEC-3: identity is a server session, so the spec enters as the architect and
// takes the testing player's session (`helpers/session.js`); `ARCHITECT_TOKEN`
// must be in the environment.
import { test, expect } from '@playwright/test'
import { gql } from '../helpers/sheet.js'
import { asArchitect } from '../helpers/arrange.js'
import { establishSession } from '../helpers/session.js'
import { NAME, dropScratch, seedScratch } from '../helpers/rollTableScratch.js'

const KAEL = 'character-kael-drift-e555ccde'

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
 *  watchers afterwards. Firefox reports `NS_BINDING_ABORTED` as an uncaught
 *  `NetworkError` for requests the second `goto` cancels mid-flight — browser
 *  noise on navigation, not the app failing — so listening across the boot would
 *  make every spec here fail on that engine for a reason that has nothing to do
 *  with what it is testing. Everything the panels do happens after this. */
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
 *  scratch table → row 1's ✎. */
async function openRowEditor(page) {
  await page.locator('.gm-toggle').click()
  await page.locator('.mode-tabs').waitFor({ state: 'visible', timeout: 20000 })
  await page.locator('.mode-tabs button', { hasText: 'Prep' }).click()

  // The universe's own editor is where the 🎲 Roll Tables section lives, and it is
  // also what fixes the panel's universe to `earth` — which is what puts a table
  // with no owning path under "Shared" rather than "Fundamental".
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
  // The panel renders before its fetch resolves; wait for the rows so the editor
  // is opened against a loaded document.
  await expect(page.locator('.rte-entry-body')).toHaveCount(2, { timeout: 20000 })

  const edit = page.locator('.rte-edit').first()
  await edit.waitFor({ state: 'visible', timeout: 20000 })
  await edit.click()
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

test('the row editor mounts and offers the row its own bound variables', async ({ page, request }) => {
  await seedScratch(request)
  await bootApp(page)
  // Watchers go on once the boot has settled — see `bootApp`. Everything the
  // panels do, including the mount under test, happens after this point.
  const problems = watchProblems(page)
  await openRowEditor(page)

  // The panel the ✎ was meant to open is on screen...
  await expect(page.locator('.eep-root')).toBeVisible({ timeout: 20000 })
  // ...with its own layer, and the add affordance the table's declarations use.
  // Scoped to `.eep-root`: the *table* panel below is still open and carries a
  // Bound-variables section of its own, so an unscoped selector matches both.
  await expect(page.locator('.eep-root .eep-subtitle', { hasText: 'Bound variables' })).toBeVisible()
  await expect(page.locator('.eep-root .bv-add')).toBeVisible()
  // Deliberately **no** assertion on how many declarations the row has: that is
  // authored content, and pinning it means the author working breaks the test.

  // The assertion this spec exists for: nothing threw on the way in. A TDZ error
  // in setup is invisible to the build, the check scripts and the API suite.
  expect(problems, problems.join('\n')).toEqual([])
})

test('a name the table already binds is shown refused, not silently saved', async ({ page, request }) => {
  await seedScratch(request)
  await bootApp(page)
  const problems = watchProblems(page)
  await openRowEditor(page)

  await page.locator('.eep-root .bv-add').click()
  // `.last()` — the row just added. `.first()` would rename whatever the row
  // already declares, and with auto-save that writes it.
  await page.locator('.eep-root .bv-name').last().fill('roll')

  // `roll` is one of the ambient facts the engine binds *before* a row's own
  // declarations, so `table_bindings` refuses the shadow and the existing value
  // wins. The author has to be told that here — otherwise the name saves and then
  // quietly does nothing.
  await expect(page.locator('.eep-root .bv-shadows').first()).toBeVisible({ timeout: 5000 })
  await expect(page.locator('.eep-root .bv-collide').first()).toBeVisible()
  await expect(page.locator('.eep-root .bv-shadows').first()).toContainText('already in scope')

  expect(problems, problems.join('\n')).toEqual([])
})

test.afterEach(async ({ page }) => {
  await page.unrouteAll({ behavior: 'ignoreErrors' })
})
