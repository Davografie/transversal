// The GM panel filter's entity suggestions are also "take me to it".
//
// The human: "When I click the suggested entity from the GM panel filter, I want
// the location tree to center on that entity and for that entity to open in a
// child panel." A chip alone only *scoped* the list and scrolled nowhere.
//
// The centring is the interesting half and is asserted as geometry, because a
// single measured scroll is not enough: the tree's rows keep shifting for about
// half a second after the click, and a scroll computed in that window lands on a
// position that no longer exists (measured in chromium at `scrollTop: 48` with the
// row 600px below the fold).
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

// Picking a suggestion that names one entity is "take me to it": the chip scopes
// the list, the tree centres on the entity, and the entity opens in a child panel.
test('a filter suggestion centres the tree and opens the entity', async ({ page }) => {
  await bootGmPanel(page, character)
  await enterPrep(page)

  await page.locator('.filter-input').fill('Krasnoyarsk')
  await page.waitForTimeout(800)
  const first = page.locator('.suggestion-row').first()
  await expect(first).toBeVisible()
  // A row reads `BADGE / name / hint`, and the badge is absent on some kinds.
  const parts = (await first.innerText()).split('\n').map((s) => s.trim()).filter(Boolean)
  const name = parts[parts.length - 2]

  await first.click()
  await page.waitForTimeout(1800)

  // The entity opened in a child panel beside the root.
  const titles = await page.locator('.panel-title').allTextContents()
  expect(titles.some((t) => t.includes(name)),
    `the entity panel opened (titles: ${JSON.stringify(titles)}, picked: ${name})`).toBe(true)

  // And the tree came to it — which a chip alone never did: it scoped the list and
  // scrolled nowhere, so the matched entity could sit off-view.
  const row = page.locator('.browse-zone [data-node-id]').filter({ hasText: name }).first()
  await expect(row, 'the entity has a row in the tree').toHaveCount(1)
  // Asserted as geometry — is the row inside the tree's scrollport? — because
  // `toBeInViewport` sampled it while the reveal was still settling and was flaky
  // in chromium, where the same run measured the final state as correctly centred.
  await page.waitForTimeout(2000)
  const rect = await page.evaluate((n) => {
    const rows = [...document.querySelectorAll('.browse-zone [data-node-id]')]
    const r = rows.find((x) => x.textContent.includes(n))
    const zone = document.querySelector('.browse-zone')
    if (!r || !zone) return { missing: true, rows: rows.length, name: n }
    const rr = r.getBoundingClientRect()
    const zr = zone.getBoundingClientRect()
    return {
      rows: rows.length, scrollTop: zone.scrollTop,
      top: Math.round(rr.top - zr.top), bottom: Math.round(rr.bottom - zr.top), h: Math.round(zr.height),
    }
  }, name)
  expect(rect.missing, `the row exists (${JSON.stringify(rect)})`).toBeFalsy()
  expect(rect.top, `below the scrollport top (${JSON.stringify(rect)})`).toBeGreaterThanOrEqual(0)
  expect(rect.bottom, `above its bottom (${JSON.stringify(rect)})`).toBeLessThanOrEqual(rect.h)
})
