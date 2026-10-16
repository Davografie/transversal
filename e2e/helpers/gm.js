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

/**
 * Detach a chain panel by dragging its ⠿ handle *away from its parent*.
 *
 * This replaced clicking ⤢ (2026-10-16), so every spec that used to click that
 * button drags instead. The pull is fed in steps because the gesture only arms
 * on a move, and it is **diagonal** on purpose: the threshold is measured on the
 * axis *perpendicular* to the slide, which is X for the default leftward chain
 * and Y for an up/down one — 70px on both covers either.
 *
 * The handle defaults to the **last one inside the chain unit**, which is the
 * deepest chain panel. Scoping to `[data-panel-unit="root"]` is the load-bearing
 * part: once a window exists, its rail is also a `.panel-drag-handle` and it
 * comes later in the DOM — but a window's handle *moves* the window, so picking
 * it would silently do something else entirely. (The old
 * `[title="Detach…"]).last()` could not hit that: windows render no ⤢ button.)
 */
export async function detachByDrag(page, handleSelector = '[data-panel-unit="root"] .panel-drag-handle:visible') {
  const handle = page.locator(handleSelector).last()
  const box = await handle.boundingBox()
  if (!box) throw new Error(`detachByDrag: no drag handle found by ${handleSelector}`)
  const x = box.x + box.width / 2
  const y = box.y + box.height / 2
  await page.mouse.move(x, y)
  await page.mouse.down()
  await page.mouse.move(x + 25, y + 25)
  await page.mouse.move(x + 50, y + 50)
  await page.mouse.move(x + 70, y + 70)
  await page.mouse.up()
  await page.waitForTimeout(900)
}
