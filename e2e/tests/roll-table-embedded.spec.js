// A roll table rendered **inside the character sheet's panel** (B268), and the fit
// that an embedded table needs — the author, rolling "Where on Earth" (17 rows) as
// a roaming GM: *"it doesn't quite fit into the panel on my desktop (the table is
// wider and shorter than the character sheet, so it's cut off on the side and has
// vertical scrolling). On mobile … nested in 2 vertical scroll elements."*
//
// Measured, not eyeballed, because every one of those is a geometry failure that
// still *looks* like a layout:
//
//   * the card must not be wider than the slot it lives in (it shipped 560px inside
//     a 323px slot — 237px clipped by the slot's `overflow-x: hidden`);
//   * there must be exactly **one** vertical scroller in the chain (the rows) —
//     the slot scrolling *and* the card scrolling is the mobile complaint;
//   * the header (the table's name) and the roll/cancel actions stay visible while
//     the rows scroll: that is what "always visible" means;
//   * a roll brings the row it marked to the **middle** of the scroller.
//
// SEC-3: identity is a server session now, so the spec enters as the architect and
// takes the testing player (`helpers/gm.js`); `ARCHITECT_TOKEN` must be in the
// environment.
import { test, expect } from '@playwright/test'
import { gql } from '../helpers/sheet.js'
import { bootGmPanel } from '../helpers/gm.js'

const KAEL = 'character-kael-drift-e555ccde'
const TABLE = 'Where on Earth'

let owner
test.beforeAll(async ({ request }) => {
  const { players } = await gql(request, `query { players { id name agency { entityId main } } }`)
  owner = players.find((p) => (p.agency || []).some((a) => a.entityId === KAEL && a.main))
  if (!owner) throw new Error(`no player mains ${KAEL} — cannot reach the testing character`)
})

/** Roaming GM → the bucket rule → the table path → the embedded menu. */
async function openEmbeddedMenu(page, size) {
  await page.setViewportSize(size)
  await page.emulateMedia({ colorScheme: 'dark' })
  // Free-roam: a `gm`-sourced rule lives on the roaming GM's play surface.
  await bootGmPanel(page, { playerId: owner.id, playerName: owner.name, entityId: '' })
  const card = page.locator('.sfx-card', { hasText: 'Roll Table' }).first()
  await card.waitFor({ state: 'visible', timeout: 20000 })
  await card.click()
  // `refs.table` is a *path*: the engine asks which table, then the client opens it.
  const candidate = page.locator('.etw-candidate', { hasText: new RegExp(TABLE, 'i') }).first()
  await candidate.waitFor({ state: 'visible', timeout: 20000 })
  await candidate.click()
  await expect(page.locator('.rtm-root.rtm-embedded')).toBeVisible({ timeout: 20000 })
  // Let the rows land (the table is fetched in this step).
  await expect(page.locator('.ct-row')).toHaveCount(17, { timeout: 20000 })
}

const geometry = (page) => page.evaluate(() => {
  const menu = document.querySelector('.rtm-root.rtm-embedded')
  const slot = menu.closest('.sheet-sfx-choice')
  const scroller = document.querySelector('.ct-scroll')
  const marked = document.querySelector('.ct-row.is-rolled')
  const box = (el) => { const b = el.getBoundingClientRect(); return { w: Math.round(b.width), h: Math.round(b.height), top: Math.round(b.top), bottom: Math.round(b.bottom) } }
  const inside = (child, parent) => {
    const c = child.getBoundingClientRect(), p = parent.getBoundingClientRect()
    return c.top >= p.top - 1 && c.bottom <= p.bottom + 1
  }
  const scrollers = []
  const visit = (n) => {
    for (const c of n.children) {
      const oy = getComputedStyle(c).overflowY
      if ((oy === 'auto' || oy === 'scroll') && c.scrollHeight > c.clientHeight + 1) scrollers.push(String(c.className).split(' ')[0])
      visit(c)
    }
  }
  visit(slot)
  return {
    slotW: box(slot).w, menuW: box(menu).w, sheetW: box(document.querySelector('.sheet-embedded')).w,
    slotScrollW: slot.scrollWidth - slot.clientWidth,
    pageScrollW: document.documentElement.scrollWidth - document.documentElement.clientWidth,
    slotScrollH: slot.scrollHeight - slot.clientHeight,
    scrollers,
    title: document.querySelector('.rtm-table')?.innerText || '',
    titleVisible: inside(document.querySelector('.rtm-title'), slot),
    actionsVisible: inside(document.querySelector('.ct-actions'), slot),
    marked: marked ? Math.round(Math.abs((marked.getBoundingClientRect().top + marked.getBoundingClientRect().height / 2) - (scroller.getBoundingClientRect().top + scroller.getBoundingClientRect().height / 2))) : null,
    atScrollStart: scroller.scrollTop <= 1,
    atScrollEnd: scroller.scrollTop >= scroller.scrollHeight - scroller.clientHeight - 1,
  }
})

test('the embedded table fits its panel, in one scroller, with the header and actions in view', async ({ page }) => {
  await openEmbeddedMenu(page, { width: 1280, height: 950 })
  const g = await geometry(page)

  // The table's name, not the rule that opened it ("Roll Table").
  expect(g.title.toLowerCase()).toBe(TABLE.toLowerCase())
  // No clipping: the card is the slot's width, and nothing overflows sideways.
  expect(g.menuW).toBeLessThanOrEqual(g.slotW)
  expect(g.slotScrollW).toBeLessThanOrEqual(0)
  expect(g.pageScrollW).toBeLessThanOrEqual(0)
  // One scrollbar for the reader, and it is the rows.
  expect(g.scrollers).toEqual(['ct-scroll'])
  // Header and actions stay put while the rows scroll.
  expect(g.titleVisible, 'the header is visible').toBe(true)
  expect(g.actionsVisible, 'roll and cancel are visible').toBe(true)
})

test('a roll brings the marked row to the middle, without moving the header', async ({ page }) => {
  await openEmbeddedMenu(page, { width: 1280, height: 950 })
  await page.locator('.ct-actions button', { hasText: /Roll/i }).first().click()

  // Smooth, so poll rather than sample mid-animation — and "centred" has to mean
  // *as centred as the scroll allows*: a roll that lands on one of the first rows
  // cannot be centred, because the scroller clamps at its own start. (The roll is
  // random, so asserting the strict version passed only when it picked a middle
  // row — a flake waiting to happen.)
  await expect.poll(async () => {
    const g = await geometry(page)
    return g.marked <= 2 || g.atScrollStart || g.atScrollEnd
  }, { timeout: 5000, intervals: [100, 200, 300] }).toBe(true)
  const g = await geometry(page)
  expect(g.titleVisible, 'the header is still visible after the scroll').toBe(true)
  expect(g.actionsVisible, 'the actions are still visible after the scroll').toBe(true)
})

test('a short panel shrinks the rows rather than growing the card', async ({ page }) => {
  // The failure mode this catches: the card grows to its content, so a shorter
  // window pushes the header off the top of the panel and the reader scrolls a
  // card *and* the panel.
  await openEmbeddedMenu(page, { width: 1280, height: 700 })
  const g = await geometry(page)
  expect(g.slotScrollH, 'the panel does not scroll as well as the rows').toBeLessThanOrEqual(1)
  expect(g.scrollers).toEqual(['ct-scroll'])
  expect(g.titleVisible).toBe(true)
  expect(g.actionsVisible).toBe(true)
})

test.afterEach(async ({ page }) => {
  await page.unrouteAll({ behavior: 'ignoreErrors' })
})
