// B169 — the landscape dock: the sheet sits beside the roller instead of above it.
//
// The gate is one matchMedia (width AND orientation) plus one CSS block, and its
// failure mode is silent: a wrong layout still looks like a layout. So the cases
// are asserted as measured geometry rather than as classes alone.
//
//   width ≤ 820px              → the three-band stack
//   width > 820px, portrait    → the bottom-centre pop-out column (unchanged)
//   width > 820px, landscape   → the sheet docks left; the roller keeps the peek
//
// Every claim about "unchanged" is a claim about the pop-out's own geometry, so
// portrait is asserted as strictly as landscape.

import { test, expect } from '@playwright/test'
import { findPlayableCharacter, openSheet } from '../helpers/sheet.js'

const DESKTOP = { width: 1280, height: 950 }
const TABLET_PORTRAIT = { width: 834, height: 1194 }
const PHONE_PORTRAIT = { width: 390, height: 844 }
const PHONE_LANDSCAPE = { width: 844, height: 390 }

const DOCK_W = 400            // --dock-w: the width the sheet already has
const SHEET_CHROME = 240      // .embedded-sheet's `calc(100dvh - 240px)` cap

let character
test.beforeAll(async ({ request }) => {
  character = await findPlayableCharacter(request)
})

/** Set the viewport, then seed identity and open the sheet on the self dot. */
async function openAt(page, size) {
  await page.setViewportSize(size)
  await openSheet(page, character)
}

const transformOf = (loc) => loc.evaluate((el) => getComputedStyle(el).transform)
const maxHeightOf = (loc) => loc.evaluate((el) => getComputedStyle(el).maxHeight)

test('wide landscape docks the sheet beside the map', async ({ page }) => {
  const problems = []
  page.on('pageerror', (e) => problems.push('uncaught: ' + String(e)))
  // Vue's own warnings are the signal that the wiring broke. Deliberately not
  // every console error: this suite drives a live backend, which throws its own
  // network errors (`fetchSfxCatalog`, the GraphQL client) on release-build too.
  page.on('console', (m) => {
    if (m.type() === 'error' && /\[Vue warn\]/.test(m.text())) problems.push(m.text())
  })

  await openAt(page, DESKTOP)

  const stage = page.locator('.stage').first()
  await expect(stage).toHaveClass(/dock-sheet/)
  await expect(stage).toHaveClass(/sheet-open/)

  // The dock is the full left column, edge to edge.
  const dock = await page.locator('.dice-panel-wrapper').first().boundingBox()
  expect(dock.x).toBeLessThan(1)
  expect(Math.round(dock.width)).toBe(DOCK_W)
  expect(Math.round(dock.height)).toBe(DESKTOP.height)

  // The map is INSET, not overlaid — the viewer starts where the dock ends, so
  // its own top-left overlay controls ride along instead of going under the
  // sheet. It slides there, so measure it settled rather than mid-flight.
  await expect.poll(async () => {
    const box = await page.locator('.location-viewer').first().boundingBox()
    return Math.round(box.x)
  }).toBe(DOCK_W)
  const map = await page.locator('.location-viewer').first().boundingBox()
  expect(Math.round(map.width)).toBe(DESKTOP.width - DOCK_W)

  // The roller centres on the map area it left behind, not on the viewport.
  const roller = await page.locator('.roller-band').first().boundingBox()
  expect(Math.round(roller.x + roller.width / 2)).toBe((DESKTOP.width + DOCK_W) / 2)

  // The sheet gets the dock's height: the 100dvh-240px cap is gone.
  expect(await maxHeightOf(page.locator('.embedded-sheet').first())).toBe('none')

  expect(problems).toEqual([])
})

test('portrait tablet keeps the pop-out column, capped sheet and all', async ({ page }) => {
  await openAt(page, TABLET_PORTRAIT)

  const stage = page.locator('.stage').first()
  await expect(stage).not.toHaveClass(/dock-sheet/)

  // Still the bottom-centre column, and still capped by the same arithmetic.
  const column = await page.locator('.dice-panel-wrapper').first().boundingBox()
  expect(Math.round(column.x + column.width / 2)).toBe(TABLET_PORTRAIT.width / 2)
  expect(Math.round(parseFloat(await maxHeightOf(page.locator('.embedded-sheet').first()))))
    .toBe(TABLET_PORTRAIT.height - SHEET_CHROME)
})

test('phone portrait keeps the three-band stack', async ({ page }) => {
  await openAt(page, PHONE_PORTRAIT)

  const stage = page.locator('.stage').first()
  await expect(stage).toHaveClass(/mobile-stack/)
  await expect(stage).not.toHaveClass(/dock-sheet/)
})

test('phone landscape docks too — the case the ticket left open', async ({ page }) => {
  await openAt(page, PHONE_LANDSCAPE)

  const stage = page.locator('.stage').first()
  await expect(stage).toHaveClass(/dock-sheet/)
  await expect(stage).not.toHaveClass(/mobile-stack/)

  const roller = await page.locator('.roller-band').first().boundingBox()
  expect(Math.round(roller.x + roller.width / 2)).toBe((PHONE_LANDSCAPE.width + DOCK_W) / 2)
})

// The peek used to live on the bottom-centre column. Docking moves it onto the
// roller band, and a transform on the column would both slide the dock and
// capture the band's `position: fixed` — so which element carries it is the
// load-bearing detail, and rotating has to hand it back.
test('the peek moves with the layout, and back again on rotation', async ({ page }) => {
  await openAt(page, DESKTOP)

  const column = page.locator('.dice-panel-wrapper').first()
  const roller = page.locator('.roller-band').first()

  await expect(page.locator('.stage').first()).toHaveClass(/dock-sheet/)
  expect(await transformOf(column)).toBe('none')     // the dock does not slide
  expect(await transformOf(roller)).not.toBe('none') // the band carries the peek

  await page.setViewportSize(TABLET_PORTRAIT)

  await expect(page.locator('.stage').first()).not.toHaveClass(/dock-sheet/)
  expect(await transformOf(roller)).toBe('none')     // handed back
  expect(await transformOf(column)).not.toBe('none') // the column carries it again
})
