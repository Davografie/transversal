// The player-settings overlay's identity block.
//
// SEC-3 rebuilt it: identity comes from the server and switching is a roster
// (`beginSwitch` → take), which is a deliberate act rather than the old
// type-a-name-and-maybe-become-them search. The *styling* went with the rebuild —
// a green "— switch player" button and an explanatory paragraph, where the overlay
// had always shown the player as a name plate you click. The plate is back, still
// opening the (new) picker, and this pins both halves so a future identity change
// cannot quietly drop the surface again.
//
// The plate's *look* is asserted as computed style rather than by class name: the
// point is 28px with wide tracking (the business card), and a class that renders as
// a normal text row would pass a class assertion.
import { test, expect } from '@playwright/test'

import { enterAsArchitect } from '../helpers/session.js'

test('your name is a plate in the settings overlay, and it opens the roster', async ({ page }) => {
  await enterAsArchitect(page)
  await page.addInitScript(() => localStorage.setItem('architectMode', 'true'))
  await page.goto('/')
  await page.waitForTimeout(2500)

  await page.locator('.settings-btn').click()
  const plate = page.locator('.settings-name-static')
  await expect(plate).toBeVisible()

  // It shows who the *server* says you are — the plate is not a text field.
  const who = await page.evaluate(async () => (await fetch('/api/v1/auth/session')).json())
  await expect(plate).toHaveText(who.player.name)
  // The identity block itself has no field: the name is shown, not editable in
  // place. (The overlay has other inputs — the character search — so this is
  // scoped to the plate's own wrapper.)
  await expect(page.locator('.settings-name-wrapper input')).toHaveCount(0)

  // The plate, not a row of text and not a button.
  expect(await plate.evaluate((el) => {
    const s = getComputedStyle(el)
    return [s.fontSize, s.letterSpacing, s.cursor]
  })).toEqual(['28px', '3px', 'pointer'])

  // The overlay does not scroll sideways at any width.
  const widths = await page.evaluate(() => {
    const el = document.querySelector('.name-entry-scroll')
    return [el.scrollWidth, el.clientWidth]
  })
  expect(widths[0]).toBeLessThanOrEqual(widths[1] + 1)

  // Clicking it opens the picker on the roster — the secure flow, not a name box.
  await plate.click()
  await expect(page.locator('.roster-new input'), 'the roster picker, not a name box').toBeVisible()

  // …and Back comes out of it, leaving the plate where it was.
  await page.locator('.name-entry-scroll button', { hasText: /^Back$/ }).first().click()
  await expect(plate).toBeVisible()
})
