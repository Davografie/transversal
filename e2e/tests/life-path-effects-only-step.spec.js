// A step that wraps **no table** — effects triggered by the step itself ([[B314]]).
//
// The owner's ask, verbatim: *"I want to be able to trigger Effects as whole steps…
// instead of authoring table entries, I'll author a `{choose}` selection."* Before
// this, every `LifePathStep` had to name a `table_id`: the executor loaded the table,
// the wizard drew its rows, and there was no way to make a step *do* something except
// by authoring rows and hanging effects on them.
//
// Two halves, and both are browser-visible:
//
//   1. **Authoring** — the path panel can create a step with no table, and it says so
//      rather than looking like a step whose table went missing. Auto-save persists
//      it, so it survives a cold load.
//   2. **Playing** — the wizard renders such a step as itself with one button, rather
//      than as a table with no entries. (The end-to-end answer to a step's `{choose}`
//      is pinned at the GraphQL layer in `test_graphql_lifepath.py`; here we pin the
//      surface the player actually touches.)
import { test, expect } from '@playwright/test'
import { gql } from '../helpers/sheet.js'
import { asArchitect } from '../helpers/arrange.js'
import { establishSession } from '../helpers/session.js'

const KAEL = 'character-kael-drift-e555ccde'
const PATH = 'lp-e2e-effects-only'
const PATH_NAME = 'E2E Effects Only'
const INTROS_KEY = 'sfx.lifePathIntros'

let owner
test.beforeAll(async ({ request }) => {
  const { players } = await gql(request, `query { players { id name agency { entityId main } } }`)
  owner = players.find((p) => (p.agency || []).some((a) => a.entityId === KAEL && a.main))
  if (!owner) throw new Error(`no player mains ${KAEL} — cannot reach the testing character`)
})

/** A path whose **entry step wraps no table**: one effects-only step, ending there. */
async function seedPath(request) {
  await gql(
    request,
    `mutation($id:String!,$name:String!,$universe:String!,$description:String!,$entryStep:String,$steps:[LifePathStepInput!]) {
       saveLifePath(id:$id, name:$name, universe:$universe, description:$description,
                    entryStep:$entryStep, steps:$steps) }`,
    { id: PATH, name: PATH_NAME, universe: 'earth', description: '',
      entryStep: 's1',
      steps: [{ id: 's1', tableId: '', label: 'Study', next: '', effects: [] }] },
  )
}

test.afterEach(async ({ page }) => {
  await gql(page.request, `mutation { deleteLifePath(id: "${PATH}") }`).catch(() => {})
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

/** GM panel → Prep → Earth → 🎲 Roll Tables → the scratch path. */
async function openPathPanel(page) {
  await page.locator('.gm-toggle').click()
  await page.locator('.mode-tabs').waitFor({ state: 'visible', timeout: 20000 })
  await page.locator('.mode-tabs button', { hasText: 'Prep' }).click()
  const earth = page.locator('.entity-row.tree-row', { hasText: 'Earth' }).first()
  await earth.waitFor({ state: 'visible', timeout: 20000 })
  await earth.click()
  await page.locator('.section-btn', { hasText: 'Roll Tables' }).click()
  const row = page.locator('.entity-name', { hasText: new RegExp(`^${PATH_NAME}$`) }).first()
  await row.waitFor({ state: 'visible', timeout: 20000 })
  await row.click()
  await expect(page.locator('.lpd-root')).toBeVisible({ timeout: 20000 })
}

test('a step with no table can be authored, and the panel says so', async ({ page }) => {
  await bootApp(page)
  await seedPath(page.request)
  await openPathPanel(page)

  await expect(page.locator('.lpd-step')).toHaveCount(1, { timeout: 20000 })
  // The seeded step is already effects-only: the panel must show that as a state, not
  // as an empty table picker waiting for a choice.
  const step = page.locator('.lpd-step').first()
  await expect(step).toContainText('Effects only')

  // …and adding another is a deliberate act, not a table selection.
  const saved = page.waitForResponse(
    (r) => (r.request().postData() || '').includes('saveLifePath'), { timeout: 20000 })
  await page.locator('button', { hasText: 'Add effects-only step' }).first().click()
  await expect(page.locator('.lpd-step')).toHaveCount(2, { timeout: 20000 })
  const body = (await saved).request().postData() || ''
  expect(body).toContain('"tableId":""')

  // A cold load: the auto-save is what makes it real, so a reload is the assertion.
  await page.reload()
  await page.waitForTimeout(2500)
  if (!(await page.locator('.lpd-root').count())) await openPathPanel(page)
  await expect(page.locator('.lpd-step')).toHaveCount(2, { timeout: 20000 })
})

test('the wizard plays an effects-only step as a step, not as an empty table', async ({ page }) => {
  await bootApp(page)
  await seedPath(page.request)

  // Route the wizard at the scratch path the way a rule would ([[B303]]): the intro
  // block in the settings panel is the surface a shown path reaches.
  await page.addInitScript(([key, cid, lp]) => {
    localStorage.setItem(key, JSON.stringify({ [cid]: { lifePathId: lp, surface: 'overlay' } }))
  }, [INTROS_KEY, KAEL, PATH])
  await page.reload()
  await page.waitForTimeout(2500)

  await page.locator('.settings-btn').click()
  const block = page.locator('.lifepath-intro')
  await expect(block).toBeVisible({ timeout: 20000 })
  await block.locator('.entity-name', { hasText: new RegExp(`^${PATH_NAME}$`) }).first().click()

  // The surface: the step itself, the reason it has no dice, and one button. The
  // failure this catches is the wizard falling to `done` on a term with no table id —
  // which is what it did before, silently ending the term.
  await expect(page.locator('.wiz-phase-label')).toContainText('Study', { timeout: 20000 })
  await expect(page.locator('.wiz-hint')).toContainText('nothing to roll')
  await expect(page.locator('.wiz-done-actions button', { hasText: 'Continue' })).toBeVisible()

  await page.locator('.wiz-done-actions button', { hasText: 'Continue' }).click()
  // The step ends the term (its `next` is empty), so the term's end state is the proof
  // that the step *ran* rather than being skipped.
  await expect(page.locator('.wiz-phase-label')).toContainText('Term Complete', { timeout: 20000 })
})

test.afterEach(async ({ page }) => {
  await page.unrouteAll({ behavior: 'ignoreErrors' })
})
