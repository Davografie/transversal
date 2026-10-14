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
// One name on each layer. The **row** one is the case that was broken: a table like
// `rt-earth-regions` keeps "this row is India" on the row, so a scope built from the
// table's declarations alone offers nothing the author actually wrote against.
const TABLE_DECLARED = 'table_pick'
const ROW_DECLARED = 'row_pick'

let owner
test.beforeAll(async ({ request }) => {
  const { players } = await gql(request, `query { players { id name agency { entityId main } } }`)
  owner = players.find((p) => (p.agency || []).some((a) => a.entityId === KAEL && a.main))
  if (!owner) throw new Error(`no player mains ${KAEL} — cannot reach the testing character`)
})

/** The scratch path wraps the scratch table, so the step has a real scope to offer.
 *
 *  `stepEffects` seeds the step's own list — the field a *restored* window's prop
 *  snapshot will not have. */
async function seedPath(request, stepEffects = []) {
  await gql(
    request,
    `mutation($id:String!,$name:String!,$universe:String!,$description:String!,$entryStep:String,$steps:[LifePathStepInput!]) {
       saveLifePath(id:$id, name:$name, universe:$universe, description:$description,
                    entryStep:$entryStep, steps:$steps) }`,
    { id: PATH, name: PATH_NAME, universe: 'earth', description: '',
      entryStep: 's1', steps: [{ id: 's1', tableId: 'rt-e2e-scratch', label: 'Start', next: '',
                                 effects: stepEffects }] },
  )
}

test('an effect authored on a step is there again after a reload', async ({ page, request }) => {
  await bootApp(page)
  await seedScratch(page.request, { rowVariables: [ROW_DECLARED] })
  await seedPath(page.request)
  await openPathPanel(page)

  const summaries = page.locator('.lpd-step').first().locator('.ee-summary')
  await expect(summaries).toHaveCount(0)

  await page.locator('.lpd-step').first().locator('.ee-add').click()
  const form = page.locator('.reep-root .ee-form')
  await expect(form).toBeVisible({ timeout: 20000 })
  // Whichever action the registry lists first — this test is about the *persist*,
  // not about which verb was chosen, and pinning an action id here couples it to a
  // vocabulary that is [[Effects System]]'s to change.
  const action = form.locator('select').first()
  const firstAction = (await action.locator('option').evaluateAll(
    (os) => os.map((o) => o.value).filter(Boolean)))[0]
  await action.selectOption(firstAction)
  // The form's own commit — "Add" — is what puts the effect in the step's list. The
  // *persist* is the panel's auto-save, and it is the half this test is about.
  const saved = page.waitForResponse(
    (r) => (r.request().postData() || '').includes('saveLifePath'), { timeout: 20000 })
  await form.locator('.ee-save').click()
  await expect(summaries).toHaveCount(1, { timeout: 20000 })
  await saved

  // A cold load. The failure this catches: the editor seeds its form from the shared
  // read, so a read that does not carry `steps { effects }` shows an empty list —
  // and the next save writes that emptiness back.
  await page.reload()
  await page.waitForTimeout(2500)
  if (!(await page.locator('.lpd-root').count())) await openPathPanel(page)
  await expect(page.locator('.lpd-step').first().locator('.ee-summary'))
    .toHaveCount(1, { timeout: 20000 })
})

test('a *restored* panel shows the step effects it was not handed', async ({ page, request }) => {
  // The human's reproduction, and the one my other specs could not see: the path
  // panel is a **floating window**, so it is rebuilt from the window record in
  // localStorage — whose `props.lp` is a snapshot from when it was parked. Clicking
  // through always hands a current copy; restoring hands the old one. The panel
  // seeded its form from that and never re-seeded, so effects authored since it was
  // parked were invisible — and, being auto-saving, it would then write the stale
  // document back.
  await bootApp(page)
  await seedScratch(page.request, { rowVariables: [ROW_DECLARED] })
  await seedPath(page.request, [{ timing: 'IMMEDIATE', type: 'modify_trait', action: 'gain',
                                  target: '', result: 'd8' }])

  // Park a floating window holding a snapshot of the path **without** its effects.
  await page.addInitScript(
    ([key, rec]) => localStorage.setItem(key, JSON.stringify(rec)),
    ['gmPanelWindows', [{
      name: 'GmLifePathDetailPanel',
      props: { lp: { id: PATH, name: PATH_NAME, universe: 'earth', description: '',
                     entryTableId: '', entryStep: 's1',
                     steps: [{ id: 's1', tableId: 'rt-e2e-scratch', label: 'Start',
                               next: '', bindings: [] }],
                     conditions: [] } },
      x: 300, y: 200, direction: 'down', collapsed: false, dock: 'right',
      sourceParentKey: null, z: 1,
    }]],
  )
  await page.reload()
  await page.waitForTimeout(2500)

  await expect(page.locator('.lpd-root'), 'the restored panel mounted').toHaveCount(1)
  await expect(page.locator('.lpd-step').first().locator('.ee-summary'))
    .toHaveCount(1, { timeout: 20000 })
})

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
  await seedScratch(page.request, { tableVariables: [TABLE_DECLARED], rowVariables: [ROW_DECLARED] })
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
  await seedScratch(page.request, { tableVariables: [TABLE_DECLARED], rowVariables: [ROW_DECLARED] })
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

  // **Both** layers are on offer, resolved by the same tracer the engine binds with,
  // so what is offered is what will resolve at run time. The row one is the point: a
  // step effect is written against whatever the *picked row* exposes, and building
  // this scope from the table's declarations alone silently offered nothing for
  // `rt-earth-regions` — whose only declaration is on its India row.
  const variables = config.locator('select').nth(1)
  await expect(variables.locator('option', { hasText: TABLE_DECLARED }))
    .toHaveCount(1, { timeout: 20000 })
  await expect(variables.locator('option', { hasText: ROW_DECLARED }))
    .toHaveCount(1, { timeout: 20000 })
})

test.afterEach(async ({ page }) => {
  await page.unrouteAll({ behavior: 'ignoreErrors' })
})
