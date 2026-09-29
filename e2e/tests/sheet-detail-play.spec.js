import { test, expect } from '@playwright/test'
import { gql } from '../helpers/sheet.js'
import { establishSession } from '../helpers/session.js'

// B185 — adding a rating from the trait *detail* view must return the reader to
// the trait list, not strand them on the detail.
//
// The detail is opened by clicking a trait row (right-click opens the editor),
// and it takes over the whole sheet body. Playing the rating from there used to
// leave the panel up, so the reader had to find "← back" to carry on — even
// though the reason they opened the trait was to put its die in the pool.
//
// Measured against the unfixed tree, the detail stayed open and the set list did
// not come back; that is the assertion below.

// The project's testing character, named by `AGENTS.md`: Kael Drift, owned as a
// main by the dedicated `DSH MCP` test player. Resolved through the *relationship*
// rather than by name — the player has been renamed once already (`Tester` →
// `DSH MCP`) and a name lookup broke the dock suite the moment it happened.
const TEST_ENTITY = 'character-kael-drift-e555ccde'

let character
test.beforeAll(async ({ request }) => {
  const { players } = await gql(request, `query { players { id name agency { entityId main } } }`)
  const owner = players.find((p) => (p.agency || []).some((a) => a.entityId === TEST_ENTITY && a.main))
  if (!owner) throw new Error(`no player mains ${TEST_ENTITY} — cannot reach the testing character`)
  character = { playerId: owner.id, playerName: owner.name, entityId: TEST_ENTITY }
})
// Playing a trait writes to the entity's dice pool, which lives per
// location+entity. The probe snapshots and restores it so the testing character
// is left exactly as it was found.
const POOL = '/api/v1/locations/loc-409859/pools/character-kael-drift-e555ccde'

async function seedAndOpen(page) {
  await page.goto('/')
  await page.evaluate((ids) => {
    localStorage.setItem('playerId', ids.playerId)
    localStorage.setItem('playerName', ids.playerName)
    localStorage.setItem('entityId', ids.entityId)
  }, character)
  await establishSession(page)
  await page.goto('/')

  const self = page.locator('button.map-dot.self').first()
  try {
    await self.waitFor({ state: 'visible', timeout: 20_000 })
  } catch {
    test.skip(true, `the testing character ${TEST_ENTITY} is not a main occupant here`)
  }
  await self.click()
  await page.locator('.sheet-embedded').first().waitFor({ state: 'visible', timeout: 20_000 })
  await page.waitForFunction(() => !!document.querySelector('.sheet-embedded .header'), null, { timeout: 20_000 })
  await page.waitForTimeout(1000)
}

test('adding a rating from the detail view returns to the set list', async ({ page, request }) => {
  // Nothing to restore if the pool cannot be read, so this doubles as the guard
  // for the restore below.
  const poolRes = await request.get(POOL)
  const before = poolRes.ok() ? (await poolRes.json()).dice || [] : null

  await seedAndOpen(page)

  const setNames = await page.locator('.set-name').evaluateAll((els) => els.map((e) => e.innerText.trim()))
  expect(setNames.length, 'this sheet must render the set layer').toBeGreaterThan(0)

  // Find a trait the sheet will actually let us play, rather than assuming the
  // first row is rated — the data decides that, not the test.
  let found = null
  for (let s = 0; s < setNames.length && !found; s++) {
    await page.locator('.set-header').nth(s).click()
    await page.waitForTimeout(400)
    const rows = await page.locator('.trait-row').count()
    for (let r = 0; r < rows && !found; r++) {
      await page.locator('.trait-row').nth(r).click()
      await page.waitForTimeout(350)
      if (await page.locator('.detail-rating-band.playable').count()) {
        found = { set: setNames[s], trait: await page.locator('.detail-name').innerText() }
        break
      }
      await page.locator('.detail-back').click()
      await page.waitForTimeout(250)
    }
    if (!found) {
      await page.locator('.set-header').nth(s).click()
      await page.waitForTimeout(200)
    }
  }
  expect(found, 'no playable trait on the testing character').not.toBeNull()

  // The act B185 is about: play the rating from the detail.
  await page.locator('.detail-rating-band').click()
  await page.waitForTimeout(1200)

  try {
    const after = await page.evaluate(() => ({
      detailOpen: !!document.querySelector('.trait-detail-panel'),
      setsRendered: document.querySelectorAll('.set-header').length,
      openSets: [...document.querySelectorAll('.trait-set.open .set-name')].map((e) => e.innerText.trim()),
    }))

    expect(after.detailOpen, `playing "${found.trait}" left the reader on the detail`).toBe(false)
    expect(after.setsRendered, 'the set list must be back').toBeGreaterThan(0)
    // …and they are standing in exactly one set's list, not on the set layer as a
    // whole. *Which* set is deliberately not asserted here: on this character every
    // set is limit 1, so the pick fills it and the auto-advance hands them the
    // next one. That rule has its own spec (`sheet-set-advance.spec.js`); this one
    // is about not being stranded on the detail.
    expect(after.openSets, 'the reader is in a set, not on the bare set layer').toHaveLength(1)
  } finally {
    // Restore even when the assertion fails — the pool is the testing
    // character's, and a red test must not leave a die in it.
    if (before) {
      const r = await request.put(POOL, { data: { dice: before } })
      expect(r.ok(), 'the testing character\'s pool must be restored').toBeTruthy()
    }
  }
})
