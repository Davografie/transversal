import { test, expect } from '@playwright/test'
import { findPlayableCharacter, openSheet } from '../helpers/sheet.js'
import { asPlayer } from '../helpers/role.js'

// A trait set's own rules — attached to the set as a **unit**, or granted to it by
// a rule's reach ([[Dynamic SFX Reach]]) — are a fact about the *set*, so they sit
// under its title and **above its rows** (the human, 2026-09-29). Below the rows a
// set-level rule read as one more trait's card, and on a long set it fell off the
// end of the list entirely.
//
// Both sheet shapes are pinned, because the placement was only right in one of
// them before this: the **accordion** (landscape, height to spare) drew the cards
// after the rows, and the **drill-in** — the default everywhere else, so phones
// and portrait tablets — drew them not at all once a set was entered.
//
// This spec reads the live world rather than stubbing a granted id: it needs a set
// that *has* a rule, and skips when none does. The author's own `sfx-gift` on the
// assets set is the fixture of the moment, which is the honest dependency — a
// placement rule with nothing to place is not a failure.

let character
test.beforeAll(async ({ request }) => {
  character = await findPlayableCharacter(request)
})

/** Expand every collapsed set, so the accordion's set bodies exist. */
async function openAllSets(page) {
  for (let i = 0; i < 12; i++) {
    const t = page.locator('.set-toggle[aria-expanded="false"]').first()
    if (!(await t.count())) break
    await t.click({ timeout: 3000 }).catch(() => {})
    await page.waitForTimeout(150)
  }
  await page.waitForTimeout(400)
}

/** The name of the first set in the list whose own rules are drawn, or null. */
async function firstSetWithRules(page) {
  return page.evaluate(() => {
    for (const sec of document.querySelectorAll('.sheet-embedded .trait-set')) {
      if (sec.querySelector(':scope > .sfx-cards .sfx-card')) {
        return sec.querySelector('.set-name')?.textContent?.trim() || ''
      }
    }
    return null
  })
}

test('the accordion draws a set\'s rules above its rows', async ({ page }) => {
  await asPlayer(page)
  await page.setViewportSize({ width: 1400, height: 1000 })
  await openSheet(page, character)
  await openAllSets(page)

  const name = await firstSetWithRules(page)
  test.skip(!name, 'no trait set currently carries a rule — nothing to place')

  const order = await page.evaluate((setName) => {
    for (const sec of document.querySelectorAll('.sheet-embedded .trait-set')) {
      if (sec.querySelector('.set-name')?.textContent?.trim() !== setName) continue
      const kids = [...sec.children]
      return {
        cards: kids.findIndex((c) => c.classList.contains('sfx-cards')),
        rows: kids.findIndex((c) => c.classList.contains('set-traits')),
        cardsInsideRows: !!sec.querySelector('.set-traits .sfx-cards'),
      }
    }
    return null
  }, name)

  expect(order, `the '${name}' set is still in the accordion`).not.toBeNull()
  expect(order.cards, 'the set draws its rules').toBeGreaterThanOrEqual(0)
  expect(order.rows, 'the set draws its rows').toBeGreaterThanOrEqual(0)
  expect(order.cards, 'the rules come before the rows, not after them').toBeLessThan(order.rows)
  expect(order.cardsInsideRows, 'and are not nested inside the row list').toBe(false)
})

test('the drill-in draws a set\'s rules under its title', async ({ page }) => {
  await asPlayer(page)
  await page.setViewportSize({ width: 820, height: 640 })
  await openSheet(page, character)

  const name = await firstSetWithRules(page)
  test.skip(!name, 'no trait set currently carries a rule — nothing to place')

  await page.evaluate((setName) => {
    const headers = [...document.querySelectorAll('.sheet-embedded .set-header-link')]
    const h = headers.find((x) => x.querySelector('.set-name')?.textContent?.trim() === setName)
    if (h) h.click()
  }, name)
  await page.waitForTimeout(700)

  const order = await page.evaluate(() => {
    const list = document.querySelector('.sheet-embedded .trait-list')
    if (!list) return null
    const kids = [...list.children]
    return {
      title: list.querySelector('.trait-list-title')?.textContent?.trim() || '',
      cards: kids.findIndex((c) => c.classList.contains('sfx-cards')),
      firstRow: kids.findIndex((c) => (c.className || '').includes('trait-node')),
    }
  })

  expect(order, 'the sheet drilled into a set').not.toBeNull()
  expect(order.title, 'the set is the one we entered').toContain(name)
  expect(order.cards, 'the entered set draws its rules').toBeGreaterThanOrEqual(0)
  expect(order.firstRow, 'the entered set draws its rows').toBeGreaterThanOrEqual(0)
  expect(order.cards, 'the rules come before the rows').toBeLessThan(order.firstRow)
})
