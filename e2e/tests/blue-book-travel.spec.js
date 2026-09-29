// The Blue Book's click-a-place gesture must actually reach the network.
//
// It did not, for a while: the component defined its own `fetch()` loader, which
// shadows `window.fetch` inside the file, so the click called the loader instead of
// the request and reported a bare "Could not travel there." with nothing leaving the
// browser. No API-level test can see that, and neither could a browser test that
// drove the endpoint directly rather than clicking the thing — which is why this one
// clicks. It also pins the *reason* on failure: the reader is told why.
//
// Kael Drift is the testing character (AGENTS.md § Player characters & the testing
// character); this drives Kael and never a player's PC. Its owning player is
// *discovered* rather than pinned — that identity has already been renamed once.
// Clicking it is deliberate: a seek moves Kael, and a run leaves it with a leg to
// have clicked.
//
// The role is pinned to `player` in the browser (`asPlayer`): the shared test identity
// has been flipped to `architect`, and an architect's own sheet runs in GM free-roam
// with no `entityId`, so the book renders empty and every assertion below is moot.

import { test, expect } from '@playwright/test'
import { asPlayer } from '../helpers/role.js'
import { establishSession } from '../helpers/session.js'

const KAEL = 'character-kael-drift-e555ccde'

const gql = (request, query) => request.post('/api/v1/graphql', { data: { query } })
  .then(async (r) => (await r.json()).data)

/** The player who holds Kael Drift as a main — discovered, not pinned: the test
 *  identity has already been renamed once, and its id could move with it. */
async function kaelOwner(request) {
  const { players } = await gql(request, '{ players { id name agency { entityId main } } }')
  const owner = players.find((p) => (p.agency || []).some((e) => e.entityId === KAEL))
  if (!owner) throw new Error('no player holds Kael Drift — see Overseer Operations')
  return owner
}

/** Open Kael's Blue Book and return the locator for its clickable locations. */
async function openKaelBlueBook(page, owner) {
  await page.goto('/')
  await page.evaluate(([pid, pname, eid]) => {
    localStorage.setItem('playerId', pid)
    localStorage.setItem('playerName', pname)
    localStorage.setItem('entityId', eid)
  }, [owner.id, owner.name, KAEL])
  await establishSession(page)
  await page.goto('/')

  const self = page.locator('button.map-dot.self').first()
  await self.waitFor({ state: 'visible', timeout: 30_000 })
  await self.click()
  await page.locator('.sheet-embedded').first().waitFor({ state: 'visible', timeout: 30_000 })
  const tab = page.locator('button.pill', { hasText: '📘' }).first()
  await tab.waitFor({ state: 'visible', timeout: 20_000 })
  await tab.click()
  // Wait for the *panel*, not for an entry: a data-dependent spec has to be able to see
  // an empty book and skip on it, which a hard wait for `.bb-entry` makes impossible.
  await page.locator('.bb-embedded').first().waitFor({ state: 'visible', timeout: 20_000 })
  await page.waitForTimeout(1_500)
  return page.locator('.bb-location-img, .bb-location-missing')
}

test('clicking a location really requests a travel, and reports why if refused', async ({ page, request }) => {
  test.setTimeout(120_000)
  await asPlayer(page)

  const responses = []
  page.on('response', (r) => {
    if (r.url().includes('consciousness-travel')) responses.push(r.status())
  })

  const locations = await openKaelBlueBook(page, await kaelOwner(request))
  test.skip(!(await locations.count()), 'Kael Drift has no transversal chain to click yet')

  await locations.first().click()
  await page.waitForTimeout(4_000)

  expect(responses, 'the click sends the travel request (this is the shadowed-fetch regression)').not.toHaveLength(0)
  expect(responses[0], 'and the travel is accepted').toBe(200)
  expect(await page.locator('.bb-travel-error').count(), 'no failure is reported').toBe(0)
})

test('a refusal is shown with its reason', async ({ page, request }) => {
  test.setTimeout(120_000)
  await asPlayer(page)

  // Stubbed so nothing travels: this pins the message, not the mechanism.
  await page.route('**/consciousness-travel', (route) => route.fulfill({
    status: 404,
    contentType: 'application/json',
    body: JSON.stringify({ detail: "Location 'loc-gone' not found" }),
  }))

  const locations = await openKaelBlueBook(page, await kaelOwner(request))
  test.skip(!(await locations.count()), 'Kael Drift has no transversal chain to click yet')

  await locations.first().click()
  const shown = page.locator('.bb-travel-error').first()
  await expect(shown).toBeVisible({ timeout: 10_000 })
  await expect(shown).toContainText("Location 'loc-gone' not found")
  await expect(shown).toContainText('404')
})
