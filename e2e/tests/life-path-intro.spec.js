// A life path a rule has shown to a player ([[B303]]).
//
// Two things this pins that nothing else can see, both from the author's first
// look at it in the running app:
//
//   1. the wizard must be **narrowed to the path the rule named**, not open on the
//      whole catalogue — the author was shown a "choose a life path" list instead;
//   2. it must **take the settings panel over**, rather than appear as one more
//      section among the character list and the device preferences.
//
// Seeded through storage rather than by driving a character creation: the suite
// must not author a player character, and the pending intro *is* the state the
// client holds after the effect fires.
import { test, expect } from '@playwright/test'

import { enterAsArchitect } from '../helpers/session.js'
import { findPlayableCharacter, openSheet } from '../helpers/sheet.js'

const CHARACTER = 'character-kael-drift-e555ccde'
const LIFE_PATH = 'lp-24f963a8'
const INTROS_KEY = 'sfx.lifePathIntros'

test('a shown life path takes the panel over, narrowed to that path', async ({ page }) => {
  await enterAsArchitect(page)
  await page.addInitScript(([key, cid, lp]) => {
    localStorage.setItem('architectMode', 'true')
    localStorage.setItem(key, JSON.stringify({ [cid]: { lifePathId: lp, surface: 'overlay' } }))
  }, [INTROS_KEY, CHARACTER, LIFE_PATH])
  await page.goto('/')
  await page.waitForTimeout(2500)
  await page.locator('.settings-btn').click()

  const block = page.locator('.lifepath-intro')
  await expect(block).toBeVisible()

  // The path the rule named, plus the way back to the rest of the catalogue —
  // that pair *is* the narrowed state.
  await expect(block).toContainText('Life on Earth')
  await expect(page.locator('.wiz-show-all')).toBeVisible()
  await expect(block).not.toContainText('Choose a life path to take a term in.')

  // Taken over: the settings sections are not rendered while it is up. Asserted by
  // absence, because `v-else-if` is what does it — a merely hidden section would
  // still be reachable by a screen reader and by tab order.
  await expect(page.locator('.new-char-toggle')).toHaveCount(0)
  await expect(page.locator('.find-char-wrapper')).toHaveCount(0)

  // Dismissing gives the panel back, so the reveal is not a trap.
  await page.locator('.lifepath-dismiss').click()
  await expect(page.locator('.lifepath-intro')).toHaveCount(0)
  await expect(page.locator('.new-char-toggle')).toBeVisible()
})

// The other half of the routing: a path shown **in that character's sheet**. The
// case worth pinning is the second visit — the intro is stored, the player comes
// back later, and the sheet must still open on the path. The first cut only
// reacted to the live event, so a reload silently downgraded it to the plain
// chooser, and the author saw exactly that.
test('a stored sheet-routed intro still opens that character\'s sheet on the path', async ({ page }) => {
  const character = await findPlayableCharacter(page.request)
  await page.addInitScript(([key, cid, lp]) => {
    localStorage.setItem(key, JSON.stringify({ [cid]: { lifePathId: lp, surface: 'sheet' } }))
  }, [INTROS_KEY, CHARACTER, LIFE_PATH])

  const panel = await openSheet(page, character)
  await expect(panel.locator('.wiz-show-all')).toBeVisible()
  await expect(panel).toContainText('Life on Earth')
  await expect(panel).not.toContainText('Choose a life path to take a term in.')
})
