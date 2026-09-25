import { test, expect } from '@playwright/test'
import { gql } from '../helpers/sheet.js'

// Which **shape** the traits tab takes, by the sheet's height — the human's rule,
// 2026-09-25: *"the accordion is only for landscape views with a large height (so
// desktops and tablets)."*
//
//   landscape AND taller than 500px  → the accordion (B178): every set a section,
//                                      several open at once
//   everything else                  → the drill-in: the set list is navigation
//                                      and one set's traits replace it
//
// The gate is `sheetDock && !shortViewport`, and both conjuncts carry weight: dock
// alone would put the accordion on the phone-landscape column (390px tall), and
// height alone would put it on a portrait tablet, which the wording excludes.
// `shortViewport` is deliberately the same 500px threshold as the CSS rule that
// swaps in `--dock-w-short`, so "short" means one thing across the stage.
//
// This is asserted as *markup*, because that is what differs: the accordion's row
// is a `.set-toggle` button that expands in place, the drill-in's is a
// `.set-header-link` that replaces the list. A layout gate that silently stopped
// applying would leave both shapes looking like layouts.

// The testing character, resolved through the ownership relationship rather than
// by name — the player has been renamed once already (`Tester` → `DSH MCP`).
const TEST_ENTITY = 'character-kael-drift-e555ccde'

const DESKTOP = { width: 1280, height: 950 }
const TABLET_LANDSCAPE = { width: 1194, height: 834 }
const TABLET_PORTRAIT = { width: 834, height: 1194 }
const PHONE_PORTRAIT = { width: 390, height: 844 }
const PHONE_LANDSCAPE = { width: 844, height: 390 }
// One pixel either side of the "large height" line, on a viewport that docks.
const JUST_SHORT = { width: 844, height: 500 }
const JUST_TALL = { width: 844, height: 501 }

let character
test.beforeAll(async ({ request }) => {
  const { players } = await gql(request, `query { players { id name agency { entityId main } } }`)
  const owner = players.find((p) => (p.agency || []).some((a) => a.entityId === TEST_ENTITY && a.main))
  if (!owner) throw new Error(`no player mains ${TEST_ENTITY} — cannot reach the testing character`)
  character = { playerId: owner.id, playerName: owner.name, entityId: TEST_ENTITY }
})

async function load(page, size) {
  await page.setViewportSize(size)
  await page.goto('/')
  await page.evaluate((ids) => {
    localStorage.setItem('playerId', ids.playerId)
    localStorage.setItem('playerName', ids.playerName)
    localStorage.setItem('entityId', ids.entityId)
    // The drill is persisted, so a previous case would otherwise decide this one.
    localStorage.removeItem('sheet.traitSetDrill')
  }, character)
  await page.goto('/')
  await page.waitForFunction(() => !!document.querySelector('.stage'), null, { timeout: 20_000 })
  await page.waitForTimeout(1200)

  // Pick the character first — that is what loads the sheet — and only then focus
  // its band. The other order leaves the stack on the map with nothing rendered,
  // which is how this spec first timed out on phone portrait.
  const dot = page.locator('button.map-dot.self').first()
  if (await dot.count()) { await dot.click().catch(() => {}); await page.waitForTimeout(800) }

  // On the band stack the sheet band starts as a teaser, and its set rows are not
  // actionable until it is focused. A raw tap, because the band's own children
  // cover its corner (see sfx-rail.spec.js for the same reason).
  if (await page.locator('.stage.mobile-stack').count()) {
    const y = await page.evaluate(() => {
      const r = document.querySelector('.sheet-band').getBoundingClientRect()
      return Math.round(r.y + 6)
    })
    await page.mouse.click(6, y)
  }
  await page.waitForSelector('.sheet-embedded .set-header, .sheet-embedded .trait-row', { timeout: 20_000 })
  await page.waitForTimeout(400)
}

const shape = (page) => page.evaluate(() => ({
  toggles: document.querySelectorAll('.sheet-embedded .set-toggle').length,
  links: document.querySelectorAll('.sheet-embedded .set-header-link').length,
  rows: document.querySelectorAll('.sheet-embedded .trait-row').length,
  title: document.querySelector('.sheet-embedded .trait-list-title')?.innerText?.trim() || null,
}))

test('a tall landscape sheet keeps the accordion', async ({ page }) => {
  for (const size of [DESKTOP, TABLET_LANDSCAPE]) {
    await load(page, size)
    const s = await shape(page)
    expect(s.toggles, `${size.width}×${size.height} must expand sets in place`).toBeGreaterThan(0)
    expect(s.links, `${size.width}×${size.height} must not drill in`).toBe(0)
  }
})

// One test per viewport rather than one looping test: each load is a few seconds,
// so three in a row blew the 30s budget and reported "timeout" instead of which
// layout was wrong.
const DRILL_IN_LAYOUTS = {
  'phone portrait': PHONE_PORTRAIT,
  'phone landscape': PHONE_LANDSCAPE,
  'tablet portrait': TABLET_PORTRAIT,
}
for (const [name, size] of Object.entries(DRILL_IN_LAYOUTS)) {
  test(`drills in and comes back out: ${name}`, async ({ page }) => {
    await load(page, size)
    const list = await shape(page)
    expect(list.links, `${name} must list the sets as navigation`).toBeGreaterThan(0)
    expect(list.toggles, `${name} must not expand in place`).toBe(0)
    expect(list.rows, `${name} starts on the set list, so no rows yet`).toBe(0)

    // Entering a set replaces the list with that set's traits…
    await page.locator('.sheet-embedded .set-header-link').nth(1).click()
    await page.waitForTimeout(500)
    const drilled = await shape(page)
    expect(drilled.rows, `${name} must show the set it entered`).toBeGreaterThan(0)
    expect(drilled.links, 'the set list is replaced, not stacked').toBe(0)
    expect(drilled.title, 'and says which set you are in, as the way back').toBeTruthy()

    // …and the title is the way back out.
    await page.locator('.sheet-embedded .trait-list-title').click()
    await page.waitForTimeout(500)
    const back = await shape(page)
    expect(back.links, 'back returns to the set list').toBeGreaterThan(0)
    expect(back.rows).toBe(0)
  })
}

test('the height boundary is where the stylesheet says it is', async ({ page }) => {
  // Both dock (same width, same orientation); only height differs, and it is the
  // `max-height: 500px` line the `--dock-w-short` rule already uses.
  await load(page, JUST_SHORT)
  expect((await shape(page)).links, 'at 500px tall the sheet is short — drill in').toBeGreaterThan(0)

  await load(page, JUST_TALL)
  expect((await shape(page)).toggles, 'at 501px tall the sheet has room — accordion').toBeGreaterThan(0)
})
