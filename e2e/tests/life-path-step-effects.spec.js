// A life-path step's own effects, edited the conventional way (B281).
//
// The human: *"Instead of rendering step effect actions embedded, they should be in
// child panels."* They were inline (`EffectEditor`), which made the path panel grow
// by a stacked builder per step. Every other effects list in the app is a list in the
// panel plus a **child panel** for the form — "an effect is a stacked builder of
// unbounded height, and the list has to stay in view while it is edited" — so this
// spec pins the interaction: the list stays with the step, the form opens beside it.
//
// It also pins the thing that makes the child usable rather than merely present: a
// step effect may only start a path from a name that resolves for **every** row of
// the step, which is the wrapped table's own declarations. Without those offered,
// `select variable …` cannot be authored at all.
//
// Runs against a **scratch table** and a **scratch path**: the panels auto-save, so a
// spec that edited authored content would write to it.
import { test, expect } from '@playwright/test'
import { gql } from '../helpers/sheet.js'
import { asArchitect } from '../helpers/arrange.js'
import { establishSession } from '../helpers/session.js'
import { NAME, SPEC, dropScratch, seedScratch } from '../helpers/rollTableScratch.js'

const KAEL = 'character-kael-drift-e555ccde'
const PATH = 'lp-e2e-step-effects'
const PATH_NAME = 'E2E Step Effects'
const DECLARED = 'table_pick'

let owner
test.beforeAll(async ({ request }) => {
  const { players } = await gql(request, `query { players { id name agency { entityId main } } }`)
  owner = players.find((p) => (p.agency || []).some((a) => a.entityId === KAEL && a.main))
  if (!owner) throw new Error(`no player mains ${KAEL} — cannot reach the testing character`)
})

/** The scratch path wraps the scratch table, so the step has a real scope to offer. */
async function seedPath(request) {
  await gql(
    request,
    `mutation($id:String!,$name:String!,$universe:String!,$description:String!,$entryStep:String,$steps:[LifePathStepInput!]) {
       saveLifePath(id:$id, name:$name, universe:$universe, description:$description,
                    entryStep:$entryStep, steps:$steps) }`,
    { id: PATH, name: PATH_NAME, universe: 'earth', description: '',
      entryStep: 's1', steps: [{ id: 's1', tableId: 'rt-e2e-scratch', label: 'Start', next: '' }] },
  )
}

test.afterEach(async ({ page }) => {
  // Cleanup through the same authenticated context the seed used.
  await gql(page.request, `mutation { deleteLifePath(id: "${PATH}") }`)
  await dropScratch(page.request)
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

/** GM panel → Prep → Earth → 🎲 Roll Tables → the scratch path → its step. */
async function openPathPanel(page) {
  await page.locator('.gm-toggle').click()
  await page.locator('.mode-tabs').waitFor({ state: 'visible', timeout: 20000 })
  await page.locator('.mode-tabs button', { hasText: 'Prep' }).click()
  const earth = page.locator('.entity-row.tree-row', { hasText: 'Earth' }).first()
  await earth.waitFor({ state: 'visible', timeout: 20000 })
  await earth.click()
  await page.locator('.section-btn', { hasText: 'Roll Tables' }).click()

  // Under "Life paths" — the group panel lists them by name.
  const row = page.locator('.entity-name', { hasText: new RegExp(`^${PATH_NAME}$`) }).first()
  await row.waitFor({ state: 'visible', timeout: 20000 })
  await row.click()
  await expect(page.locator('.lpd-root')).toBeVisible({ timeout: 20000 })
  await expect(page.locator('.lpd-step')).toHaveCount(1, { timeout: 20000 })
}

test('a step effect opens in a child panel, not inline', async ({ page }) => {
  await bootApp(page)
  // Seeded *after* the boot: `saveLifePath` is a mutation and needs the session.
  await seedScratch(page.request, { tableVariables: [DECLARED] })
  await seedPath(page.request)
  await openPathPanel(page)

  const step = page.locator('.lpd-step').first()
  // The list lives with the step…
  const add = step.locator('.ee-add')
  await expect(add).toBeVisible({ timeout: 20000 })
  // …and **nothing** is embedded: no form in the path panel until one is opened.
  await expect(step.locator('.ee-form')).toHaveCount(0)

  await add.click()

  // The form arrives as its own panel, beside the path rather than inside it.
  await expect(page.locator('.reep-root')).toBeVisible({ timeout: 20000 })
  await expect(page.locator('.reep-root .ee-form')).toBeVisible()
  // …and the step still shows no inline form: the list stayed put.
  await expect(step.locator('.ee-form')).toHaveCount(0)
})

test('the step effect is offered the table\'s declarations, not just ambient names', async ({ page }) => {
  await bootApp(page)
  await seedScratch(page.request, { tableVariables: [DECLARED] })
  await seedPath(page.request)
  await openPathPanel(page)

  await page.locator('.lpd-step').first().locator('.ee-add').click()
  const form = page.locator('.reep-root .ee-form')
  await expect(form).toBeVisible({ timeout: 20000 })

  // Build a `select variable` from the step's scope: this is the assertion about
  // *usability* — the child panel alone would leave the feature unauthorable, since
  // the variable picker is a dropdown with no free text.
  // By value, not label: `actionId` is the stable spelling.
  await form.locator('select').first().selectOption('create_relationship')
  // This action's target is **path-only**, so no mode row is rendered at all — the
  // path builder is the only input, which is exactly the surface in question.
  await form.locator('.pf-open').first().click()

  await page.locator('.tsb-plus').first().click()
  await page.locator('.tsb-add-btn', { hasText: 'Select' }).first().click()
  const step = page.locator('.tsb-step').first()
  // `variable` is a **collection** of the `select` step, not a step kind — the step's
  // own kind select is `select.tsb-kind`, and the config's first dropdown picks what
  // it selects from.
  const config = step.locator('.tsb-config').first()
  await config.locator('select').first().selectOption('variable')

  // The table's own declaration is on offer — resolved by the same tracer the engine
  // binds with, so what is offered is what will resolve at run time. Without it the
  // variable dropdown is empty and a step effect cannot consume a row's name at all.
  await expect(config.locator('select').nth(1).locator('option', { hasText: DECLARED }))
    .toHaveCount(1, { timeout: 20000 })
})

test.afterEach(async ({ page }) => {
  await page.unrouteAll({ behavior: 'ignoreErrors' })
})
