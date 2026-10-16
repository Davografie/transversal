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
//     collection can only ever be `many`;
//   * the picker's results are an **inline list the host panel scrolls**, not an
//     overlay an `overflow` ancestor crops (B47). This is the only spec that
//     reaches the picker nested three panels deep, so the geometry rides here
//     rather than in a second spec that would duplicate the whole journey.
//
// It builds a path against a **scratch table**, because the panels auto-save: a spec
// that typed into `rt-earth-regions` would write to authored content.
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

/** GM panel → Prep → Earth → 🎲 Roll Tables → Shared → the scratch table → row 1 →
 *  ✎, then a fresh bound variable and its path builder. */
async function openPathBuilder(page) {
  await page.locator('.gm-toggle').click()
  await page.locator('.mode-tabs').waitFor({ state: 'visible', timeout: 20000 })
  await page.locator('.mode-tabs button', { hasText: 'Prep' }).click()
  const earth = page.locator('.entity-row.tree-row', { hasText: 'Earth' }).first()
  await earth.waitFor({ state: 'visible', timeout: 20000 })
  await earth.click()
  // Wait for each step's own control before clicking it: these panels re-read
  // themselves after a write, so a blind click can race a re-render — and on a
  // cold Vite (a component just changed) the 30s test timeout is easy to hit.
  const rollTables = page.locator('.section-btn', { hasText: 'Roll Tables' })
  await rollTables.waitFor({ state: 'visible', timeout: 20000 })
  await rollTables.click()
  const shared = page.locator('.rtp-group', { hasText: 'Shared' }).first()
  await shared.waitFor({ state: 'visible', timeout: 20000 })
  await shared.click()
  const table = page.locator('.entity-name', { hasText: new RegExp(`^${NAME}$`) }).first()
  await table.waitFor({ state: 'visible', timeout: 20000 })
  await table.click()
  await expect(page.locator('.rte-root')).toBeVisible({ timeout: 20000 })
  await expect(page.locator('.rte-entry-body')).toHaveCount(2, { timeout: 20000 })

  const edit = page.locator('.rte-edit').first()
  await edit.waitFor({ state: 'visible', timeout: 20000 })
  await edit.click()
  await expect(page.locator('.eep-root')).toBeVisible({ timeout: 20000 })
  // A **new** variable, so its path starts empty and the seed menu is what is on
  // screen. `.last()` on both: `.first()` would be a declaration the table already
  // has, and with auto-save editing it writes.
  const addVar = page.locator('.eep-root .bv-add')
  await addVar.waitFor({ state: 'visible', timeout: 20000 })
  await addVar.click()
  await page.locator('.eep-root .bv-name').last().fill('picked_location')
  const openPath = page.locator('.eep-root .pf-open').last()
  await openPath.waitFor({ state: 'visible', timeout: 20000 })
  await openPath.click()
  await expect(page.locator('.tsb-root')).toBeVisible({ timeout: 20000 })
}

test('a literal step is a seed, and its value is picked by name', async ({ page, request }) => {
  await seedScratch(request)
  await bootApp(page)
  await openPathBuilder(page)

  // The empty builder's ＋ opens the seed menu.
  const plus = page.locator('.tsb-plus').first()
  await plus.waitFor({ state: 'visible', timeout: 20000 })
  await plus.click()
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
  // It is a *search* dropdown, so type rather than scroll: `location` has 400-odd
  // candidates and India is nowhere near the top of an alphabetical list.
  await picker.locator('input.sd-input').click()
  await picker.locator('input.sd-input').fill('India')

  const option = page.locator('.sd-item', { hasText: /^India/ }).first()
  await option.waitFor({ state: 'visible', timeout: 20000 })
  await option.scrollIntoViewIfNeeded()

  // ── the result list is an inline list, not an overlay a panel can crop (B47) ──
  // The human: *"The dropdown list gets cropped wherever the component is
  // embedded. Instead of a dropdown list, an actual list might be more
  // convenient."* The cause was structural: the list was `position: absolute`
  // inside a relative root, so any ancestor with `overflow` clipped it — and this
  // picker is nested three panels deep, the case that clipped worst. These pin the
  // *rendered* fact, so they hold whatever the markup becomes.
  await expect(option).toHaveClass(/\bentity-row\b/)
  const shape = await option.evaluate((el) => {
    const list = el.parentElement
    const cs = getComputedStyle(list)
    // The nearest ancestor that scrolls — the panel the list must live inside.
    let s = list.parentElement, scroller = null
    while (s) {
      if (/(auto|scroll)/.test(getComputedStyle(s).overflowY)) { scroller = s; break }
      s = s.parentElement
    }
    return {
      position: cs.position,
      overflowY: cs.overflowY,
      hasScroller: !!scroller,
      rowHeight: Math.round(el.getBoundingClientRect().height),
    }
  })
  expect(shape.position, 'the list must be in flow, so no ancestor can crop it').toBe('static')
  expect(shape.overflowY, 'the list must not own a second scroller').not.toMatch(/auto|scroll/)
  expect(shape.hasScroller, 'the row must sit inside the panel that scrolls it').toBe(true)
  expect(shape.rowHeight, 'a row is the shared shell, not a one-line crumb').toBeGreaterThanOrEqual(28)

  // That a clipped overlay cannot do this is the click below's own assertion:
  // Playwright refuses to click an element that does not receive pointer events
  // where it claims to be, so the pick is the hit-testability proof.
  await option.click()

  // Picking a *name* stores the id — the option offers the name, the step keeps the
  // identity, so the rule means exactly one thing.
  await expect(step.locator('.tsb-literal-id')).toHaveValue('location-india-55a094fc')

  // And the trace agrees it is `one`, which is what a filter could never reach.
  await expect(page.locator('.tsb-summary-type')).toContainText('location', { timeout: 20000 })
})

test('the id box stays as the way out for an element with no candidates', async ({ page, request }) => {
  await seedScratch(request)
  await bootApp(page)
  await openPathBuilder(page)

  const plus = page.locator('.tsb-plus').first()
  await plus.waitFor({ state: 'visible', timeout: 20000 })
  await plus.click()
  const seed = page.locator('.tsb-add-btn', { hasText: 'Pick one thing' }).first()
  await seed.waitFor({ state: 'visible', timeout: 20000 })
  await seed.click()
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
