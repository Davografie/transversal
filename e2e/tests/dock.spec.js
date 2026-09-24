// B169 — the landscape dock: the sheet sits beside the roller, permanently.
//
// The gate is one matchMedia (width AND orientation) plus one CSS block, and its
// failure mode is silent: a wrong layout still looks like a layout. So the cases
// are asserted as measured geometry rather than as classes alone.
//
//   width ≤ 820px              → the three-band stack
//   width > 820px, portrait    → the bottom-centre pop-out column (unchanged)
//   width > 820px, landscape   → the sheet docks left, always visible
//                                (and narrower still when the viewport is short,
//                                 i.e. a phone held sideways)
//
// Every claim about "unchanged" is a claim about the pop-out's own geometry, so
// portrait is asserted as strictly as landscape.

import { test, expect } from '@playwright/test'
import { findPlayableCharacter, openSheet } from '../helpers/sheet.js'

const DESKTOP = { width: 1280, height: 950 }
const TABLET_LANDSCAPE = { width: 1194, height: 834 }
const TABLET_PORTRAIT = { width: 834, height: 1194 }
const PHONE_PORTRAIT = { width: 390, height: 844 }
const PHONE_LANDSCAPE = { width: 844, height: 390 }

const DOCK_W = 400            // --dock-w: the width the sheet already has
const PHONE_DOCK_W = 160      // --dock-w when the viewport is short (phone landscape)
const PHONE_DOCK_PAD = 12     // top room the narrow dock gives the sheet's portrait
const SHEET_CHROME = 240      // .embedded-sheet's `calc(100dvh - 240px)` cap
const PEEK = 56               // PANEL_CLOSED_PEEK

let character
test.beforeAll(async ({ request }) => {
  character = await findPlayableCharacter(request)
})

/** Seed identity and load — deliberately with no further interaction. */
async function seedAndLoad(page, size) {
  await page.setViewportSize(size)
  await page.goto('/')
  await page.evaluate(([pid, pname, eid]) => {
    localStorage.setItem('playerId', pid)
    localStorage.setItem('playerName', pname)
    localStorage.setItem('entityId', eid)
  }, [character.playerId, character.playerName, character.entityId])
  await page.goto('/')
}

/** Set the viewport, then seed identity and open the sheet on the self dot. */
async function openAt(page, size) {
  await page.setViewportSize(size)
  await openSheet(page, character)
}

const box = (loc) => loc.boundingBox()
const transformOf = (loc) => loc.evaluate((el) => getComputedStyle(el).transform)
const maxHeightOf = (loc) => loc.evaluate((el) => getComputedStyle(el).maxHeight)

test('wide landscape docks the sheet beside the map, before anything is clicked', async ({ page }) => {
  const problems = []
  page.on('pageerror', (e) => problems.push('uncaught: ' + String(e)))
  // Vue's own warnings are the signal that the wiring broke. Deliberately not
  // every console error: this suite drives a live backend, which throws its own
  // network errors (`fetchSfxCatalog`, the GraphQL client) on release-build too.
  page.on('console', (m) => {
    if (m.type() === 'error' && /\[Vue warn\]/.test(m.text())) problems.push(m.text())
  })

  await seedAndLoad(page, DESKTOP)

  const stage = page.locator('.stage').first()
  await expect(stage).toHaveClass(/dock-sheet/)

  // THE point of the dock: it is not a drawer. No hover, no dot click, no phase
  // change — the sheet is simply there, and stays there.
  await expect(page.locator('.embedded-sheet').first()).toBeVisible()

  // The dock is the full left column, edge to edge.
  const dock = await box(page.locator('.sheet-band').first())
  expect(Math.round(dock.x)).toBe(0)
  expect(Math.round(dock.width)).toBe(DOCK_W)

  // The map is INSET, not overlaid — the viewer starts where the dock ends, so
  // its own top-left overlay controls ride along instead of going under the sheet.
  const map = await box(page.locator('.location-viewer').first())
  expect(Math.round(map.x)).toBe(DOCK_W)
  expect(Math.round(map.width)).toBe(DESKTOP.width - DOCK_W)

  // The roller centres on the map area it left behind, not on the viewport.
  const roller = await box(page.locator('.roller-band').first())
  expect(Math.round(roller.x + roller.width / 2)).toBe((DESKTOP.width + DOCK_W) / 2)

  // The sheet gets the dock's height: the 100dvh-240px cap is gone.
  expect(await maxHeightOf(page.locator('.embedded-sheet').first())).toBe('none')

  expect(problems).toEqual([])
})

// The dock used to be the roller's column, so anything that revealed the sheet
// opened the roller with it. They are independent now, and this is the check
// that they cannot silently re-couple.
test('the docked sheet and the roller are independent', async ({ page }) => {
  await openAt(page, DESKTOP)

  const stage = page.locator('.stage').first()
  const roller = page.locator('.roller-band').first()
  const sheet = page.locator('.embedded-sheet').first()

  // Selecting a character opens the sheet — and must NOT drag the roller open.
  await expect(stage).toHaveClass(/dock-sheet/)
  await expect(sheet).toBeVisible()
  await expect(roller).not.toHaveClass(/open/)

  // Hovering the roller opens the roller — and must leave the sheet alone.
  await page.mouse.move((DESKTOP.width + DOCK_W) / 2, DESKTOP.height - 30)
  await expect(roller).toHaveClass(/open/)
  await expect(sheet).toBeVisible()
  await expect(stage).toHaveClass(/dock-sheet/)
})

test('portrait tablet keeps the pop-out column, capped sheet and all', async ({ page }) => {
  await openAt(page, TABLET_PORTRAIT)

  const stage = page.locator('.stage').first()
  await expect(stage).not.toHaveClass(/dock-sheet/)

  // Still the bottom-centre column, and still capped by the same arithmetic.
  const column = await box(page.locator('.dice-panel-wrapper').first())
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

test('phone landscape docks, with a narrower dock so the map keeps its room', async ({ page }) => {
  await openAt(page, PHONE_LANDSCAPE)

  const stage = page.locator('.stage').first()
  await expect(stage).toHaveClass(/dock-sheet/)
  await expect(stage).not.toHaveClass(/mobile-stack/)

  // A phone held sideways is short, so the dock takes 40% of its other width
  // rather than about half the screen, and the map gets the difference back.
  const dock = await box(page.locator('.sheet-band').first())
  expect(Math.round(dock.width)).toBe(PHONE_DOCK_W)

  const map = await box(page.locator('.location-viewer').first())
  expect(Math.round(map.x)).toBe(PHONE_DOCK_W)
  expect(Math.round(map.width)).toBe(PHONE_LANDSCAPE.width - PHONE_DOCK_W)

  const roller = await box(page.locator('.roller-band').first())
  expect(Math.round(roller.x + roller.width / 2)).toBe((PHONE_LANDSCAPE.width + PHONE_DOCK_W) / 2)

  // The sheet's portrait pops above its own header. At this width the header is
  // tall enough that it used to pop past the top of the screen, so the dock
  // carries top room for it — the sheet band must start clear of the edge.
  expect(dock.y).toBeGreaterThanOrEqual(PHONE_DOCK_PAD)
  expect(await page.evaluate(() => document.documentElement.scrollWidth
    - document.documentElement.clientWidth)).toBe(0)
})

// The narrower dock is keyed on a SHORT viewport, not on being in landscape, so
// a tablet in landscape must keep the full-width one. This is the boundary.
test('tablet landscape keeps the full-width dock', async ({ page }) => {
  await openAt(page, TABLET_LANDSCAPE)

  const stage = page.locator('.stage').first()
  await expect(stage).toHaveClass(/dock-sheet/)

  const dock = await box(page.locator('.sheet-band').first())
  expect(Math.round(dock.width)).toBe(DOCK_W)

  const map = await box(page.locator('.location-viewer').first())
  expect(Math.round(map.x)).toBe(DOCK_W)
  expect(Math.round(map.width)).toBe(TABLET_LANDSCAPE.width - DOCK_W)
})

// The peek used to live on the bottom-centre column. Docking moves it onto the
// roller band, and a transform on the column would both drag the dock around
// and capture the band's `position: fixed` — so which element carries it is the
// load-bearing detail, and rotating has to hand it back.
test('the peek moves with the layout, and back again on rotation', async ({ page }) => {
  await openAt(page, DESKTOP)

  const column = page.locator('.dice-panel-wrapper').first()
  const roller = page.locator('.roller-band').first()

  await expect(page.locator('.stage').first()).toHaveClass(/dock-sheet/)
  expect(await transformOf(column)).toBe('none')     // the dock does not slide
  expect(await transformOf(roller)).not.toBe('none') // the band carries the peek

  // Closed, the band is pushed down so the peek is what stays on screen and the
  // rest hangs below the viewport bottom. The panel settles to its peek with a
  // 0.3s transition on load (in the pop-out too, pre-existing), so poll rather
  // than measure the slide; the offset derives from `offsetHeight`, which rounds
  // where layout does not, hence the pixel of slack. The regression this guards
  // — a band left open, or gone — is ~90px away.
  await expect.poll(async () => {
    const b = await box(roller)
    return Math.round(Math.abs(DESKTOP.height - b.y - PEEK))
  }).toBeLessThanOrEqual(2)
  const peeked = await box(roller)
  expect(peeked.y + peeked.height).toBeGreaterThan(DESKTOP.height)

  await page.setViewportSize(TABLET_PORTRAIT)

  await expect(page.locator('.stage').first()).not.toHaveClass(/dock-sheet/)
  expect(await transformOf(roller)).toBe('none')     // handed back
  expect(await transformOf(column)).not.toBe('none') // the column carries it again
})
