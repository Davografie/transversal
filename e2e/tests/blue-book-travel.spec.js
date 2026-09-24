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
// character) and is owned as a main by the `Tester` player, so this drives Kael and
// never a player's PC. Travelling it is deliberate — it is the project's character,
// and a run leaves it with one more Blue Book entry to click.

import { test, expect } from '@playwright/test'

const KAEL = 'character-kael-drift-e555ccde'
const TESTER = 'player-75a410'

/** Open Kael's Blue Book and return the locator for its clickable locations. */
async function openKaelBlueBook(page) {
  await page.goto('/')
  await page.evaluate(([pid, eid]) => {
    localStorage.setItem('playerId', pid)
    localStorage.setItem('playerName', 'Tester')
    localStorage.setItem('entityId', eid)
  }, [TESTER, KAEL])
  await page.goto('/')

  const self = page.locator('button.map-dot.self').first()
  await self.waitFor({ state: 'visible', timeout: 30_000 })
  await self.click()
  await page.locator('.sheet-embedded').first().waitFor({ state: 'visible', timeout: 30_000 })
  const tab = page.locator('button.pill', { hasText: '📘' }).first()
  await tab.waitFor({ state: 'visible', timeout: 20_000 })
  await tab.click()
  await page.locator('.bb-entry').first().waitFor({ state: 'visible', timeout: 20_000 })
  await page.waitForTimeout(1_500)
  return page.locator('.bb-location-img, .bb-location-missing')
}

test('clicking a location really requests a travel, and reports why if refused', async ({ page }) => {
  test.setTimeout(120_000)

  const responses = []
  page.on('response', (r) => {
    if (r.url().includes('consciousness-travel')) responses.push(r.status())
  })

  const locations = await openKaelBlueBook(page)
  test.skip(!(await locations.count()), 'Kael Drift has no transversal chain to click yet')

  await locations.first().click()
  await page.waitForTimeout(4_000)

  expect(responses, 'the click sends the travel request (this is the shadowed-fetch regression)').not.toHaveLength(0)
  expect(responses[0], 'and the travel is accepted').toBe(200)
  expect(await page.locator('.bb-travel-error').count(), 'no failure is reported').toBe(0)
})

test('a refusal is shown with its reason', async ({ page }) => {
  test.setTimeout(120_000)

  // Stubbed so nothing travels: this pins the message, not the mechanism.
  await page.route('**/consciousness-travel', (route) => route.fulfill({
    status: 404,
    contentType: 'application/json',
    body: JSON.stringify({ detail: "Location 'loc-gone' not found" }),
  }))

  const locations = await openKaelBlueBook(page)
  test.skip(!(await locations.count()), 'Kael Drift has no transversal chain to click yet')

  await locations.first().click()
  const shown = page.locator('.bb-travel-error').first()
  await expect(shown).toBeVisible({ timeout: 10_000 })
  await expect(shown).toContainText("Location 'loc-gone' not found")
  await expect(shown).toContainText('404')
})
