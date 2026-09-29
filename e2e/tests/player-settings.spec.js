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

  // The picker is a **column**, not the viewport, and the explanation uses it.
  // Measured, because the failure this fixes is invisible in a screenshot: with 24
  // players the chip grid ran 1216px across a 1280px screen, and the hint — capped
  // at the login card's 280px — was four lines in the middle of it.
  const drill = await page.evaluate(() => {
    const box = (sel) => {
      const el = document.querySelector(sel)
      return el ? { w: el.getBoundingClientRect().width, scrollW: el.scrollWidth, clientW: el.clientWidth } : null
    }
    const names = [...document.querySelectorAll('.roster-picker .char-item')].map((e) => e.textContent.trim())
    return {
      picker: box('.roster-picker'),
      list: box('.roster-picker .char-list'),
      hint: box('.roster-picker .name-hint'),
      chips: names.length,
      // The engine that sorted it is the engine that checks it, so there is no
      // cross-browser comparator question here.
      sorted: names.every((n, i) => i === 0 || names[i - 1].localeCompare(n) <= 0),
      overflow: document.documentElement.scrollWidth > window.innerWidth,
    }
  })
  expect(drill.picker.w, 'a column, not the window').toBeLessThanOrEqual(521)
  expect(drill.hint.w, 'the explanation uses that column').toBeGreaterThan(280)
  expect(drill.list.scrollW, 'the chips wrap inside it').toBeLessThanOrEqual(drill.list.clientW + 1)
  expect(drill.chips, 'the roster is not empty').toBeGreaterThan(1)
  expect(drill.sorted, 'and is sorted, so you can find your own name').toBe(true)
  expect(drill.overflow, 'nothing scrolls sideways').toBe(false)

  // …and Back comes out of it, leaving the plate where it was.
  await page.locator('.name-entry-scroll button', { hasText: /^Back$/ }).first().click()
  await expect(plate).toBeVisible()
})
