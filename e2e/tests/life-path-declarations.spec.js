// A life path and a life path **step** declaring the names their shared tables read
// (B290).
//
// The human: *"the life paths need to be able to establish variables too then. So that
// an Iron Roots sect life path or an Azure Dawn sect life path can re-use the same roll
// tables but with different contexts"* — then, on the shape, *"both life paths and life
// path steps should be able to declare variables."* The engine half is a layer order
// (`path → step → table → row`); what only a browser proves is the two **surfaces** and
// the round trip around them:
//
//   * the path panel is seeded from the shared read, so a read that dropped the
//     declarations shows an empty editor — and, being auto-saving, writes that
//     emptiness back over what the author declared;
//   * a step's declarations are authored in a **child** panel (the step list is already
//     table + label + next + effects), which writes into the path panel's live draft;
//   * the **override** is a real control, and it persists — it is the one field that
//     says "replace the wrapped table's name of this name".
//
// Runs against a **scratch table** and a **scratch path**: the panels auto-save, so a
// spec that edited authored content would write to it.
import { test, expect } from '@playwright/test'
import { gql } from '../helpers/sheet.js'
import { asArchitect } from '../helpers/arrange.js'
import { establishSession } from '../helpers/session.js'
import { dropScratch, seedScratch } from '../helpers/rollTableScratch.js'

const KAEL = 'character-kael-drift-e555ccde'
const PATH = 'lp-e2e-declarations'
const PATH_NAME = 'E2E Declarations'
// The **table** declares this; the path declares it too, which is the case the
// override exists for. The step declares a name nothing else does.
const TABLE_DECLARED = 'table_pick'
const STEP_DECLARED = 'step_pick'
// `select self` — an ordinary path, and one the tracer can type without a repo.
const SPEC = { steps: [{ kind: 'select', collection: 'self' }] }

let owner
test.beforeAll(async ({ request }) => {
  const { players } = await gql(request, `query { players { id name agency { entityId main } } }`)
  owner = players.find((p) => (p.agency || []).some((a) => a.entityId === KAEL && a.main))
  if (!owner) throw new Error(`no player mains ${KAEL} — cannot reach the testing character`)
})

/** The scratch path, wrapping the scratch table, declaring on **both** new layers —
 *  the fields a read that forgot them would erase on the next auto-save. */
async function seedPath(request) {
  await gql(
    request,
    `mutation($id:String!,$name:String!,$universe:String!,$description:String!,$entryStep:String,
              $steps:[LifePathStepInput!],$b:[BoundVariableInput!]) {
       saveLifePath(id:$id, name:$name, universe:$universe, description:$description,
                    entryStep:$entryStep, steps:$steps, boundVariables:$b) }`,
    {
      id: PATH, name: PATH_NAME, universe: 'earth', description: '', entryStep: 's1',
      b: [{ name: TABLE_DECLARED, spec: SPEC, override: false }],
      steps: [{
        id: 's1', tableId: 'rt-e2e-scratch', label: 'Start', next: '',
        boundVariables: [{ name: STEP_DECLARED, spec: SPEC }],
      }],
    },
  )
}

/** The **stored** path, cold — `gql` returns `data` and throws on `errors`. */
async function readPath(request) {
  const { lifePaths } = await gql(
    request,
    `query { lifePaths { id boundVariables { name override }
             steps { id boundVariables { name override } } } }`)
  return lifePaths.find((p) => p.id === PATH)
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
  await expect(page.locator('.lpd-step')).toHaveCount(1, { timeout: 20000 })
}

/** The path's own declaration editor — the section labelled "Path variables" (the
 *  Steps section is a sibling of the same class, so the label is the discriminator). */
function pathVariableRows(page) {
  return page.locator('.lpd-section').filter({ hasText: 'Path variables' }).locator('.bv-row')
}

test('a path declares a name its wrapped table also declares, and the override persists', async ({ page, request }) => {
  await bootApp(page)
  await seedScratch(page.request, { tableVariables: [TABLE_DECLARED] })
  await seedPath(page.request)
  await openPathPanel(page)

  // The read half: the declaration is there because `LIFE_PATH_FIELDS` fetched it. An
  // empty editor here is the bug this spec exists for — and the panel would save that
  // emptiness back.
  const row = pathVariableRows(page).first()
  await expect(row.locator('.bv-name')).toHaveValue(TABLE_DECLARED, { timeout: 20000 })

  // The wrapped table declares the same name, so the note is informational and offers
  // the override — **not** the red "will not bind": the path resolves first and already
  // wins while it resolves.
  const note = row.locator('.bv-override-note')
  await expect(note).toContainText(TABLE_DECLARED)
  const box = row.locator('.bv-override input')
  await expect(box).not.toBeChecked()

  // Marking it suppresses the table's declaration outright, so the table's value can
  // never surface on an activation where the path's resolves nothing.
  const saved = page.waitForResponse(
    (r) => (r.request().postData() || '').includes('saveLifePath'), { timeout: 20000 })
  await box.check()
  await saved

  await expect.poll(async () => {
    const stored = await readPath(page.request)
    return (stored?.boundVariables || []).map((b) => `${b.name}:${b.override}`)
  }, { timeout: 20000 }).toContain(`${TABLE_DECLARED}:true`)

  // The write half of the read: a reload shows the tick, not a default.
  await page.reload()
  await page.waitForTimeout(2500)
  if (!(await page.locator('.lpd-root').count())) await openPathPanel(page)
  await expect(pathVariableRows(page).first().locator('.bv-override input'))
    .toBeChecked({ timeout: 20000 })
})

test('a step declares in a child panel, and the edit lands on the stored path', async ({ page, request }) => {
  await bootApp(page)
  await seedScratch(page.request, { tableVariables: [TABLE_DECLARED] })
  await seedPath(page.request)
  await openPathPanel(page)

  // The step list carries a read of what is declared, and the builder itself is a
  // child panel — the step is already table + label + next + effects.
  const step = page.locator('.lpd-step').first()
  await expect(step.locator('.lpd-step-vars .lpd-detail')).toContainText(`{${STEP_DECLARED}}`)
  await step.locator('button', { hasText: 'Edit' }).click()
  await expect(page.locator('.svp-root')).toBeVisible({ timeout: 20000 })

  // Seeded from the shared read, through the step the path panel holds.
  const name = page.locator('.svp-root .bv-name').first()
  await expect(name).toHaveValue(STEP_DECLARED, { timeout: 20000 })

  // Rename it: the child writes into the **live** draft, and the path panel's
  // auto-save is what persists it — the split that would silently lose the edit if the
  // child held a copy.
  const RENAMED = 'sect'
  const saved = page.waitForResponse(
    (r) => (r.request().postData() || '').includes('saveLifePath'), { timeout: 20000 })
  await name.fill(RENAMED)
  await saved

  await expect.poll(async () => {
    const stored = await readPath(page.request)
    return (stored?.steps?.[0]?.boundVariables || []).map((b) => b.name)
  }, { timeout: 20000 }).toEqual([RENAMED])

  // A cold load, which is where a read that forgot the step layer fails.
  await page.reload()
  await page.waitForTimeout(2500)
  if (!(await page.locator('.lpd-root').count())) await openPathPanel(page)
  await page.locator('.lpd-step').first().locator('button', { hasText: 'Edit' }).click()
  await expect(page.locator('.svp-root .bv-name').first())
    .toHaveValue(RENAMED, { timeout: 20000 })
})

test.afterEach(async ({ page }) => {
  await page.unrouteAll({ behavior: 'ignoreErrors' })
})
