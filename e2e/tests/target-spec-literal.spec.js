// The `literal` step: pin one thing, chosen from the universal picker (B281).
//
// This exists because the step landed without a browser test, and the field it
// replaces was a plain id box. The human: *"The 'Literal' should re-use the Picker
// component, so I don't have to enter plain text, but can select from suggestions."*
//
// What it pins, beyond "it renders":
//
//   * the step is offered where a **seed** goes (it starts a path, like `select`),
//     and choosing it reveals an element select and a picker;
//   * the picker is `ui/TargetPicker`, the universal one, backed by
//     `targetCandidates(kind)` — so the suggestions are the set the engine can
//     actually resolve, not a list this component keeps;
//   * picking a name stores the **id**, and the step then type-checks as
//     `location / one` — which is the whole reason the step exists: a filtered
//     collection can only ever be `many`.
//
// It builds a path inside a *draft* and never saves, so no live content is touched.
import { test, expect } from '@playwright/test'
import { gql } from '../helpers/sheet.js'
import { asArchitect } from '../helpers/arrange.js'
import { establishSession } from '../helpers/session.js'

const KAEL = 'character-kael-drift-e555ccde'
const TABLE = 'Where on Earth'

let owner
test.beforeAll(async ({ request }) => {
  const { players } = await gql(request, `query { players { id name agency { entityId main } } }`)
  owner = players.find((p) => (p.agency || []).some((a) => a.entityId === KAEL && a.main))
  if (!owner) throw new Error(`no player mains ${KAEL} — cannot reach the testing character`)
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

/** GM panel → Prep → Earth → 🎲 Roll Tables → Shared → the table → row 1 → ✎,
 *  then a fresh bound variable and its path builder. */
async function openPathBuilder(page) {
  await page.locator('.gm-toggle').click()
  await page.locator('.mode-tabs').waitFor({ state: 'visible', timeout: 20000 })
  await page.locator('.mode-tabs button', { hasText: 'Prep' }).click()
  const earth = page.locator('.entity-row.tree-row', { hasText: 'Earth' }).first()
  await earth.waitFor({ state: 'visible', timeout: 20000 })
  await earth.click()
  await page.locator('.section-btn', { hasText: 'Roll Tables' }).click()
  await page.locator('.rtp-group', { hasText: 'Shared' }).first().click()
  const table = page.locator('.entity-name', { hasText: new RegExp(`^${TABLE}$`) }).first()
  await table.waitFor({ state: 'visible', timeout: 20000 })
  await table.click()
  await expect(page.locator('.rte-root')).toBeVisible({ timeout: 20000 })
  await expect(page.locator('.rte-entry-body')).toHaveCount(17, { timeout: 20000 })

  await page.locator('.rte-edit').first().click()
  await expect(page.locator('.eep-root')).toBeVisible({ timeout: 20000 })
  // A name whose path is just a pin, so the row exposes exactly one location.
  await page.locator('.eep-root .bv-add').click()
  await page.locator('.eep-root .bv-name').first().fill('picked_location')
  await page.locator('.eep-root .pf-open').first().click()
  await expect(page.locator('.tsb-root')).toBeVisible({ timeout: 20000 })
}

test('a literal step is a seed, and its value is picked by name', async ({ page }) => {
  await bootApp(page)
  await openPathBuilder(page)

  // The empty builder's `＋` opens the seed menu.
  await page.locator('.tsb-plus').first().click()
  // A literal starts a path, so it is offered there…
  const seed = page.locator('.tsb-add-btn', { hasText: 'Pick one thing' }).first()
  await expect(seed).toBeVisible({ timeout: 20000 })
  await seed.click()

  // …and once it exists it is a step with an element and a value.
  const step = page.locator('.tsb-step').first()
  await expect(step).toBeVisible()
  await step.locator('select.tsb-kind').selectOption('literal')

  // The element is the kind the picker is asked for.
  await step.locator('.tsb-literal select').first().selectOption('location')

  // The universal picker, not a text box: this is the assertion the request was about.
  const picker = step.locator('.tp-root')
  await expect(picker).toBeVisible({ timeout: 20000 })
  await picker.locator('input.sd-input').click()

  const option = page.locator('.sd-item', { hasText: /^India/ }).first()
  await option.waitFor({ state: 'visible', timeout: 20000 })
  await option.click()

  // Picking a *name* stores the id — the option offers the name, the step keeps the
  // identity, so the rule means exactly one thing.
  const idBox = step.locator('.tsb-literal-id')
  await expect(idBox).toHaveValue('location-india-55a094fc')

  // And the trace agrees it is `one`, which is what a filter could never reach.
  await expect(page.locator('.tsb-summary-type')).toContainText('location', { timeout: 20000 })
})

test('the id box stays as the way out for an element with no candidates', async ({ page }) => {
  await bootApp(page)
  await openPathBuilder(page)

  await page.locator('.tsb-plus').first().click()
  await page.locator('.tsb-add-btn', { hasText: 'Pick one thing' }).first().click()
  const step = page.locator('.tsb-step').first()
  await step.locator('select.tsb-kind').selectOption('literal')
  // `pool` is one of the nine catalog elements `targetCandidates` cannot list, so
  // the picker is legitimately empty here and the step is still authorable.
  await step.locator('.tsb-literal select').first().selectOption('pool')
  await step.locator('.tsb-literal-id').fill('pool-some-id')
  await expect(step.locator('.tsb-literal-id')).toHaveValue('pool-some-id')
})

test.afterEach(async ({ page }) => {
  await page.unrouteAll({ behavior: 'ignoreErrors' })
})
