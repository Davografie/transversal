// The "Starter Location" checkbox on a location's panel did not seem to persist
// (reported 2026-10-16).
//
// The panel form is `GmEntityForm`, whose checkbox emits through the panel's
// `v-model` into `useEntityCrud`'s debounced auto-save; the read query and the
// update mutation both carry `starterLocation`, and the API round-trips it
// (verified by hand). So the failure, if it is one, is in the *panel* path —
// which only a browser can show.
//
// The spec asserts BOTH halves, because they fail differently and the difference
// is the diagnosis: the stored value (the write happened) and the checkbox after
// a reload (the read reached the form).
import { test, expect } from '@playwright/test'
import { gql } from '../helpers/sheet.js'
import { bootGmPanel, enterPrep, openStack } from '../helpers/gm.js'

const TEST_CHARACTER = 'character-kael-drift-e555ccde'
const LOCATION = 'Antarctica'   // a root-level place, and not a starter in live data
const CHECKBOX = 'label:has-text("Starter Location") input[type="checkbox"]'
const PANEL = '.panel-node[data-panel-depth="1"]:visible'

let character
test.beforeAll(async ({ request }) => {
  const { players } = await gql(request, `query { players { id name agency { entityId main } } }`)
  const owner = players.find((p) => (p.agency || []).some((a) => a.entityId === TEST_CHARACTER && a.main))
  if (!owner) throw new Error(`no player mains ${TEST_CHARACTER} — cannot reach the testing character`)
  character = { playerId: owner.id, playerName: owner.name, entityId: TEST_CHARACTER }
})

/** What the database says, read over the same API the app uses. */
async function stored(request, name) {
  const { entities } = await gql(request, `query { entities(type: LOCATION) { id name starterLocation } }`)
  const found = entities.find((e) => e.name === name)
  if (!found) throw new Error(`no location named ${name}`)
  return found
}

/** Open that location's panel from the GM panel's focus filter. */
async function openLocation(page, name) {
  await page.locator('.filter-input:visible').first().fill(name)
  await page.waitForTimeout(900)
  await page.locator('.suggestion-row:visible').first().click()
  await page.waitForTimeout(1600)
}

test.beforeEach(async ({ request }) => {
  // Leave it clean whatever the previous run did.
  const e = await stored(request, LOCATION)
  if (e.starterLocation) {
    await gql(request, `mutation($i: UpdateEntityInput!){ updateEntity(input: $i){ id } }`,
      { i: { id: e.id, starterLocation: false } })
  }
})

test('ticking Starter Location survives a reload, and reaches the database', async ({ page, request }) => {
  await bootGmPanel(page, character)
  await enterPrep(page)
  await openLocation(page, LOCATION)

  const box = page.locator(PANEL).locator(CHECKBOX).first()
  await expect(box, 'the checkbox is on a location panel').toHaveCount(1)
  await expect(box, 'and starts unticked, as the database says').not.toBeChecked()

  await box.check()
  // The auto-save is debounced 600ms, then there is a round trip.
  await page.waitForTimeout(2000)

  // Half one: the write reached the database.
  expect((await stored(request, LOCATION)).starterLocation, 'the tick was saved').toBe(true)

  // Half two: it comes back ticked after a reload.
  await page.reload()
  await page.waitForTimeout(3000)
  // The 🛠 open/closed state is deliberately *not* persisted, so the chain comes
  // back closed and has to be switched on again before anything is rendered.
  await openStack(page)
  await enterPrep(page)
  await openLocation(page, LOCATION)
  await expect(page.locator(PANEL).locator(CHECKBOX).first(),
    'and the panel shows the stored value after a reload').toBeChecked()
})

// The panel re-reads its entity whenever it becomes the active tab again
// (`watch(panelActive …) → selectEntity`), which rebuilds the whole form from the
// database — while the auto-save that carries the tick is still sitting in a
// 600ms debounce. So a tick taken just before a tab switch is read back as it was
// *stored*, and then written that way: the change is silently reverted. This is
// the "doesn't seem to persist" report, and it is a race, not a lost write.
test('a tick is not lost when the panel is re-activated before the save lands', async ({ page, request }) => {
  await bootGmPanel(page, character)
  await enterPrep(page)
  await openLocation(page, LOCATION)

  const box = page.locator(PANEL).locator(CHECKBOX).first()
  await expect(box, 'the checkbox starts unticked').not.toBeChecked()
  await box.check()

  // Inside the debounce: open a second child (this panel goes inactive), then come
  // back to it through the chip strip — which is what makes it re-read.
  await page.locator('.tree-row').nth(1).click()
  await page.waitForTimeout(150)
  await page.locator('.panel-chip').first().click()
  await page.waitForTimeout(2500)

  expect((await stored(request, LOCATION)).starterLocation,
    'the tick survived the panel being re-activated').toBe(true)
})
