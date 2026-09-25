import { test, expect } from '@playwright/test'
import { gql } from '../helpers/sheet.js'

// The Active SFX rail is chrome for the map it floats over, so it must not be
// mounted on top of a surface that has taken the screen.
//
// The rail is `position: fixed; left: 10px; top: 50%` and mounted in `App.vue`,
// which had it gated on the login overlay and the full canvas. That left the
// phone **band stack's sheet focus**: the sheet fills the middle of the viewport
// there, and the rail rendered straight across it. Measured at 390×844,
// `document.elementsFromPoint` at the rail's centre returned `.trait-sets` /
// `.sheet-scroll` instead of `.location-viewer`.
//
// The rule is "not the sheet focus" rather than "the location focus" *because it
// was measured*: `focus-dice` keeps the roller in the bottom band with the map
// still behind the rail, and `focus-location` is the map. Asserting the narrow
// version would pin a bug fix into deleting two working reads.

// The testing character, resolved through the ownership relationship rather than
// by name — the player has been renamed once already (`Tester` → `DSH MCP`).
const TEST_ENTITY = 'character-kael-drift-e555ccde'
const PHONE = { width: 390, height: 844 }
const DESKTOP = { width: 1280, height: 950 }

let character
test.beforeAll(async ({ request }) => {
  const { players } = await gql(request, `query { players { id name agency { entityId main } } }`)
  const owner = players.find((p) => (p.agency || []).some((a) => a.entityId === TEST_ENTITY && a.main))
  if (!owner) throw new Error(`no player mains ${TEST_ENTITY} — cannot reach the testing character`)
  character = { playerId: owner.id, playerName: owner.name, entityId: TEST_ENTITY }
})

/**
 * Give the rail something to render, deterministically.
 *
 * The rail draws `activeSfx(entityId)` and nothing else in the app asks for it,
 * so the list is stubbed over the wire rather than waited for. Live active SFX is
 * *transient* — the two the testing character happened to carry while this was
 * written were `on_session_start` rules that expired within the hour, and the
 * first version of this spec therefore skipped itself instead of testing
 * anything. A layout rule must not depend on session state to be checkable.
 */
async function stubActiveSfx(page) {
  await page.route('**/api/v1/graphql', async (route) => {
    if (!(route.request().postData() || '').includes('activeSfx')) return route.continue()
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        data: {
          activeSfx: [
            { sfxId: 'sfx-one-trick', name: 'One Trick', sourceKind: 'table', sourceId: null, sourceName: null, bindings: [] },
          ],
        },
      }),
    })
  })
}

async function load(page, size) {
  await stubActiveSfx(page)
  await page.setViewportSize(size)
  await page.goto('/')
  await page.evaluate((ids) => {
    localStorage.setItem('playerId', ids.playerId)
    localStorage.setItem('playerName', ids.playerName)
    localStorage.setItem('entityId', ids.entityId)
  }, character)
  await page.goto('/')
  await page.waitForFunction(() => !!document.querySelector('.stage'), null, { timeout: 20_000 })
  await page.waitForTimeout(2000)
}

/** Focus a band in the stack by tapping it, as a reader does. */
async function focusBand(page, bandClass) {
  // A raw mouse click, not `locator.click()`: the band is a *container* whose
  // top-left corner is covered by one of its own children (the map at the
  // location focus, the `.band-tap` capture layer at every other), so Playwright's
  // actionability check sees an intercepted click and retries forever. A finger
  // does not care which descendant is on top — the tap bubbles to the band — so
  // the test should not either.
  const y = await page.evaluate((sel) => {
    const r = document.querySelector(sel).getBoundingClientRect()
    return Math.round(r.y + 6)
  }, `.${bandClass}`)
  await page.mouse.click(6, y)
  await page.waitForTimeout(700)
}

test('the rail is absent when the band stack focuses the sheet, and present on the map', async ({ page }) => {
  await load(page, PHONE)

  const rail = page.locator('.armed-sfx-rail')
  await expect(rail, 'the stack opens on the location band, where the rail belongs').toBeVisible({ timeout: 10_000 })

  await focusBand(page, 'sheet-band')
  await expect(page.locator('.stage')).toHaveClass(/focus-sheet/)
  await expect(rail, 'the rail must not sit on top of the sheet').toHaveCount(0)

  await focusBand(page, 'loc-band')
  await expect(page.locator('.stage')).toHaveClass(/focus-location/)
  await expect(rail, 'back on the map, the rail comes back').toBeVisible({ timeout: 10_000 })
})

test('docked, the rail sits over the location viewer rather than the sheet', async ({ page }) => {
  await load(page, DESKTOP)

  const rail = page.locator('.armed-sfx-rail')
  await expect(rail).toBeVisible({ timeout: 10_000 })

  // What is actually behind it — the dock puts the sheet in the left column, so a
  // rail that failed to step clear would land on the sheet instead of the map.
  const behind = await page.evaluate(() => {
    const r = document.querySelector('.armed-sfx-rail').getBoundingClientRect()
    return document.elementsFromPoint(Math.round(r.left + r.width / 2), Math.round(r.top + r.height / 2))
      .map((e) => (typeof e.className === 'string' ? e.className : ''))
  })
  expect(behind.some((c) => c.includes('location-viewer')), `the map must be behind the rail (got ${behind.join(' | ')})`).toBe(true)
  expect(behind.some((c) => c.includes('sheet-scroll')), 'the rail must have stepped clear of the docked sheet').toBe(false)
})
