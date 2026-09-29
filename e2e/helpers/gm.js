// Reaching the GM panel from a spec.
//
// `gmMode` is a ref **seeded from localStorage**, not a live read of the player's
// role, so arrange mode has to be seeded before the page loads rather than mocked
// after it (`asArchitect` alone is not enough — it only fixes the role read).
//
// SEC-3: `gmMode` is still client-side, but *identity* is not — it comes from a
// server-issued session, so seeding `localStorage.playerId` is only a statement of
// intent. `establishSession` turns that intent into the session the app actually
// reads; without it the perimeter refuses every request and the sealed notice
// covers the app, which is exactly how these specs failed.
import { asArchitect } from './arrange.js'
import { establishSession } from './session.js'

/** Open the GM panel's chain — it starts closed, so nothing is rendered until this. */
export async function openStack(page) {
  await page.locator('button', { hasText: '🛠' }).first().click()
  await page.waitForTimeout(1000)
}

/** Seed the testing identity, load the app as an architect, and open the chain. */
export async function bootGmPanel(page, character) {
  await asArchitect(page)
  await page.addInitScript(([pid, eid, pname]) => {
    localStorage.setItem('playerId', pid)
    localStorage.setItem('playerName', pname)
    localStorage.setItem('entityId', eid)
    localStorage.setItem('architectMode', 'true')
  }, [character.playerId, character.entityId, character.playerName])
  await page.goto('/')
  // The initScript above runs before every navigation, so the player is readable
  // now; obtain the session, then reload so the app boots with it.
  await establishSession(page)
  await page.goto('/')
  await page.waitForTimeout(2500)
  await openStack(page)
}

/** Switch the panel to the Prep tab, where the location tree lives. */
export async function enterPrep(page) {
  const prep = page.locator('.mode-tabs button, .tab-btn', { hasText: 'Prep' })
  if (await prep.count()) {
    await prep.first().click()
    await page.waitForTimeout(1000)
  }
}
