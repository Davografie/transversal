// Rules on **someone else's sheet**: a GM sees them live, a player sees them and
// cannot press them.
//
// The author, 2026-09-29: *"As GM, I still want to see SFX's on foreign sheets, but
// for players they should be disabled. Also: I want the SFX's to trigger for the
// character I'm viewing when I trigger them as GM."*
//
// The two halves are one rule, and they have to land together: making a GM's press
// run the **viewed** character's rule is only safe if a player's press cannot reach
// it. Before this, a foreign sheet's cards were live for everyone and a press ran
// the rule against the *acting* entity — so the cards on screen were one character's
// and the trigger went to another's.
//
// The card is put there by the spec, not by content: no live GMC carries a rule, and
// a stub that grafts one onto the **viewed** entity only is what keeps the two cases
// comparable. The trigger request is intercepted rather than performed, so neither
// test writes anything — and the GM test's whole assertion is *what that request
// carries*.

import { test, expect } from '@playwright/test'
import { asPlayer } from '../helpers/role.js'
import { enterAsArchitect, establishSession } from '../helpers/session.js'
import { findPlayableCharacter, gql, openSheet } from '../helpers/sheet.js'

/** A real, manual rule, so the card resolves through the catalog. */
const RULE = 'sfx-reveal-entity'
/** The foreign entity: a GMC at the testing character's location, so a peer chip reaches it. */
const FOREIGN = 'gmc-3147032' // Karl Starmozov
const FOREIGN_NAME = 'Karl Starmozov'
const AT = 'loc-409859' // where the testing character stands

let character
test.beforeAll(async ({ request }) => {
  character = await findPlayableCharacter(request)
  const { entity } = await gql(request, `query($id: ID!) { entity(id: $id) { id name currentLocation } }`, { id: FOREIGN })
  if (!entity || entity.currentLocation !== AT) {
    throw new Error(`${FOREIGN} is not at ${AT} any more (got ${JSON.stringify(entity)}) — the peer chip this spec clicks would not be there`)
  }
})

/**
 * Give the **viewed** entity a rule, and let the world answer for everyone else.
 *
 * `availableSfxIds` is patched too: it is what greys a card whose conditions do not
 * hold, so a grafted id missing from it would draw a blocked card and the GM test
 * would pass for the wrong reason.
 */
async function stubForeignRule(page) {
  await page.route('**/api/v1/graphql', async (route) => {
    let body
    try {
      const res = await route.fetch()
      try { body = await res.json() } catch { return route.fulfill({ response: res }) }
    } catch (err) {
      // The app keeps asking while a test is *ending*, so this callback can still
      // be awaiting its real fetch when Playwright tears the context down. That
      // surfaces as `route.fetch: Test ended` and **fails the test** — a teardown
      // race, not a fault in what it asserts. Same guard, same reason, as
      // `helpers/role.js`.
      if (/Test ended/i.test(String(err && err.message))) return
      throw err
    }
    if (body?.data?.entity?.id === FOREIGN) body.data.entity.sfxIds = [RULE]
    if (Array.isArray(body?.data?.availableSfxIds) && !body.data.availableSfxIds.includes(RULE)) {
      body.data.availableSfxIds.push(RULE)
    }
    return route.fulfill({ json: body }).catch(() => {})
  })
}

/** Capture every trigger the app asks for, and never perform one. */
async function captureTriggers(page) {
  const seen = []
  await page.route('**/api/v1/effects/trigger', async (route) => {
    seen.push(route.request().postDataJSON())
    return route.fulfill({ json: { applied: true, effects_applied: 1, pending: 0 } })
  })
  return seen
}

async function boot(page, { asGm }) {
  await page.setViewportSize({ width: 1280, height: 950 })
  await page.addInitScript((loc) => localStorage.setItem('currentLocationId', loc), AT)
  if (asGm) {
    // The owner's own seat (SEC-3): no player is taken, which is the roaming GM
    // this spec wants — no acting entity, one viewed character.
    await enterAsArchitect(page)
    await page.goto('/')
  } else {
    // A player: the project's testing character, never a real PC. The role has to
    // be pinned as well as the session, or the architect's seat would leak back in
    // and the cards would be live for the wrong reason.
    await asPlayer(page)
    await page.goto('/')
    await page.evaluate((c) => {
      localStorage.setItem('playerId', c.playerId)
      localStorage.setItem('playerName', c.playerName)
      localStorage.setItem('entityId', c.entityId)
    }, character)
    await establishSession(page)
    await page.goto('/')
  }
  // The peer chip is how both audiences reach a foreign sheet.
  await expect(page.locator('.peer-chip', { hasText: FOREIGN_NAME }).first())
    .toBeVisible({ timeout: 20_000 })
  // The dock turns the peers strip into a vertical rail, and the chip is still
  // moving while it settles — measured: the bar's box is 45×938 in the dock, and
  // Playwright refuses to click a moving target. Wait for the layout before
  // pressing anything.
  await page.waitForTimeout(1500)
  await page.locator('.peer-chip', { hasText: FOREIGN_NAME }).first().click()
  const sheet = page.locator('.sheet-embedded')
  await expect(sheet.locator('.name-primary')).toHaveText(FOREIGN_NAME, { timeout: 20_000 })
  return sheet
}

test("a GM's press runs the viewed character's rule, not the acting one's", async ({ page }) => {
  await stubForeignRule(page)
  const triggers = await captureTriggers(page)
  const sheet = await boot(page, { asGm: true })

  const card = sheet.locator('.entity-sfx-cards .sfx-card').first()
  await expect(card, 'the viewed character\'s rules are drawn for the GM').toBeVisible()
  await expect(card, 'and the GM may press them').not.toHaveClass(/sfx-blocked/)

  await card.click()
  await expect.poll(() => triggers.length, { timeout: 10_000 }).toBe(1)
  expect(triggers[0].entity_id, 'the trigger names the character on screen').toBe(FOREIGN)
  expect(triggers[0].sfx_name).toBe(RULE)
})

test('a player sees them on a foreign sheet and cannot press them', async ({ page }) => {
  await stubForeignRule(page)
  const triggers = await captureTriggers(page)
  const sheet = await boot(page, { asGm: false })

  const card = sheet.locator('.entity-sfx-cards .sfx-card').first()
  await expect(card, 'a player still sees what the character has').toBeVisible()
  await expect(card, 'but not as something they can press').toHaveClass(/sfx-blocked/)
  await expect(card).toHaveAttribute('title', /not yours to press/)

  await card.click()
  // The card refuses at the source, so nothing is even asked of the server. Give a
  // real trigger time to arrive before believing the silence.
  await page.waitForTimeout(700)
  expect(triggers, 'a player pressing another character\'s rule must ask for nothing').toEqual([])
})
