// The tree chevron's three modes — the browser half of `check-tree-expand.mjs`.
//
// The human (2026-10-13): *"I'd like the expand arrow in location tree items to
// cycle through three modes instead of only cycling through filtered and expanded.
// I also want it to be able to collapse when filter is active."*
//
// The node check owns the arithmetic (which content each mode shows, and what a
// press lands in); what only a browser can show is that the glyph on screen is the
// mode, that a press moves it, and that collapsing under a filter really takes the
// matches off screen — the thing that was impossible before, when an explicit
// collapse was answered by returning the level to the filter's path.
import { test, expect } from '@playwright/test'
import { gql } from '../helpers/sheet.js'
import { bootGmPanel, enterPrep } from '../helpers/gm.js'

const TEST_CHARACTER = 'character-kael-drift-e555ccde'

let character
test.beforeAll(async ({ request }) => {
  const { players } = await gql(request, `query { players { id name agency { entityId main } } }`)
  const owner = players.find((p) => (p.agency || []).some((a) => a.entityId === TEST_CHARACTER && a.main))
  if (!owner) throw new Error(`no player mains ${TEST_CHARACTER} — cannot reach the testing character`)
  character = { playerId: owner.id, playerName: owner.name, entityId: TEST_CHARACTER }
})

test('the chevron cycles filtered → everything → collapsed, with a filter on', async ({ page }) => {
  await bootGmPanel(page, character)
  await enterPrep(page)

  // A **chip** is what filters the tree (typing only offers suggestions), and a type
  // chip is the cheapest one to place: no navigation, no panel. Its populated path
  // is broad, so some level on it is bound to be only partly revealed.
  await page.locator('.filter-input').fill('GMC')
  await page.waitForTimeout(900)
  await page.locator('.suggestion-row').filter({ hasText: 'Gmc' }).first().click()
  await page.waitForTimeout(1200)
  // (The panel already carries a chip for the acting character, so this asserts the
  // chip *it* added rather than a count.)
  await expect(page.locator('.filter-chip').filter({ hasText: 'Gmc' }), 'the type chip is on')
    .toHaveCount(1)

  // The level is found by its *state*, then tracked by id — a locator pinned to
  // `reveal-partial` would stop matching the moment the press lands.
  const partialRow = page.locator('.browse-zone [data-node-id]')
    .filter({ has: page.locator('.tree-toggle.reveal-partial') }).first()
  await expect(partialRow, 'the filter leaves a level partly revealed').toHaveCount(1)
  const id = await partialRow.getAttribute('data-node-id')
  const chevron = page.locator(`.browse-zone [data-node-id="${id}"] .tree-toggle`)
  const rows = () => page.locator('.browse-zone [data-node-id]').count()
  // The tree keeps growing for a moment after a chip lands (the occupant lists
  // arrive from their own reads), so a single count is a moving target — measured
  // here, the same state read 626 and then 631 on two runs. Sample until it holds
  // still; the comparison is about the chevron, not about the fetch.
  const settled = async () => {
    let last = -1
    for (let i = 0; i < 20; i++) {
      const now = await rows()
      if (now === last) return now
      last = now
      await page.waitForTimeout(250)
    }
    return last
  }

  await expect(chevron, 'a filtered level reads ▿').toHaveClass(/reveal-partial/)
  const filtered = await settled()

  await chevron.click()
  await expect(chevron, 'press 1: everything at this level reads ▾').toHaveClass(/reveal-expanded/)
  const everything = await settled()
  expect(everything, 'revealing the rest adds rows below it').toBeGreaterThan(filtered)

  await chevron.click()
  await expect(chevron, 'press 2: collapsed reads ▸ — the press that used to bounce back to ▿')
    .toHaveClass(/reveal-collapsed/)
  const collapsed = await settled()
  expect(collapsed, 'and the content under it is off screen, filter or no filter')
    .toBeLessThan(everything)

  await chevron.click()
  await expect(chevron, 'press 3: back to the filter\'s path').toHaveClass(/reveal-partial/)
  expect(await settled(), 'and the matches are back, exactly as before').toBe(filtered)
})
