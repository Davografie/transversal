import { test, expect } from '@playwright/test'
import { gql } from '../helpers/sheet.js'

// B125 — a sheet refresh must patch the sheet in place, not rebuild it.
//
// The bug was invisible to every static check and to the naked eye on a fast
// machine, but it was expensive: `useApi()`'s `loading` ref is set by *every*
// GraphQL call the sheet makes, and the body was gated on `v-if="loading"`. A
// `v-if` branch is keyed by its *index*, so flipping `loading` on for even one
// frame swapped the body out for the "Loading…" placeholder and swapped it back
// — unmounting and remounting the whole entity subtree. Every sheet refresh
// therefore re-ran every child's `onMounted` (which is what fed the B120 loop),
// and a failed background call replaced a perfectly good sheet with raw error
// text.
//
// The two assertions below are the same measurement from both ends: the
// placeholder must never be inserted into a sheet that already has an entity,
// and the header node captured before the refresh must still be the header node
// afterwards. Element *identity* is the point — a rebuild leaves an equivalent
// header that is a different node, which a `toBeVisible()` check would pass.

// The project's testing character, named by `AGENTS.md`: Kael Drift, owned as a
// main by the dedicated `DSH MCP` test player. Resolved through the *relationship*
// rather than by name — the player has already been renamed once (`Tester` →
// `DSH MCP`), and a name lookup broke the dock suite the moment it happened.
const TEST_ENTITY = 'character-kael-drift-e555ccde'

let character
test.beforeAll(async ({ request }) => {
  const { players } = await gql(request, `query { players { id name agency { entityId main } } }`)
  const owner = players.find((p) => (p.agency || []).some((a) => a.entityId === TEST_ENTITY && a.main))
  if (!owner) throw new Error(`no player mains ${TEST_ENTITY} — cannot reach the testing character`)
  character = { playerId: owner.id, playerName: owner.name, entityId: TEST_ENTITY }
})

/** Seed the testing identity and open Kael's own sheet, or skip with a reason. */
async function openTestingSheet(page) {
  await page.goto('/')
  await page.evaluate((ids) => {
    localStorage.setItem('playerId', ids.playerId)
    localStorage.setItem('playerName', ids.playerName)
    localStorage.setItem('entityId', ids.entityId)
  }, character)
  await page.goto('/')

  const self = page.locator('button.map-dot.self').first()
  try {
    await self.waitFor({ state: 'visible', timeout: 20_000 })
  } catch {
    test.skip(true, `the testing character ${TEST_ENTITY} is not a main occupant here`)
  }
  await self.click()

  const panel = page.locator('.sheet-embedded').first()
  await panel.waitFor({ state: 'visible', timeout: 20_000 })
  // The panel is visible before the entity lands, so wait for something that
  // only the loaded body renders.
  await page.waitForFunction(
    () => !!document.querySelector('.sheet-embedded .header'),
    null,
    { timeout: 20_000 },
  )
  return panel
}

test('a sheet refresh does not remount the sheet body', async ({ page }) => {
  await openTestingSheet(page)

  // Watch the body for the placeholder being inserted. That insertion *is* the
  // teardown, so counting it needs no reference to the old markup.
  await page.evaluate(() => {
    const root = document.querySelector('.sheet-embedded')
    window.__b125 = { loadingSeen: 0 }
    new MutationObserver((records) => {
      for (const r of records) {
        for (const n of r.addedNodes) {
          if (n.nodeType === 1 && n.classList?.contains('loading')) window.__b125.loadingSeen++
        }
      }
    }).observe(root, { childList: true, subtree: true })
  })

  await page.evaluate(() => {
    document.querySelector('.sheet-embedded .header').dataset.b125Mark = 'kept'
  })

  // `+ Add Trait` asks the sheet's own API for the candidate list — a read-only
  // refresh, and the one that used to blank the body.
  await page.locator('button.add-trait-btn').first().click()
  await page.waitForTimeout(1500)

  const state = await page.evaluate(() => {
    const h = document.querySelector('.sheet-embedded .header')
    return {
      loadingSeen: window.__b125.loadingSeen,
      headerMarked: h?.dataset.b125Mark === 'kept',
    }
  })
  expect(state.loadingSeen, 'a refresh replaced the sheet body with the loading placeholder').toBe(0)
  expect(state.headerMarked, 'a refresh unmounted and remounted the sheet body').toBe(true)
})
