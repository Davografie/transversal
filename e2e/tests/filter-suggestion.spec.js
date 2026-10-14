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
import { bootGmPanel, enterPrep, openStack } from '../helpers/gm.js'

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

// The suggestion list is the whole match set, revealed a page at a time and sorted
// into the canonical entity order — the human: *"Replace the hard cap with a
// lazy-load infinite scroll. It'd also be a good idea to sort the results
// deterministically, follow the sorting standard (entity type, then alphabetical)."*
//
// Two browser facts a node check cannot prove: that the scroll handler fires and
// the next page is rendered, and that the sort reached the DOM. The comparator's
// two tiebreaks (name, then id, with the main/support split) are pinned in
// `check-place-filter.mjs`, where the fixture controls the agency; the row badge
// here only says the *type*, so that is what this asserts.
//
// The query is one letter on purpose: it matches hundreds of entities whatever the
// live data does, so the page is guaranteed to be full and to have more behind it.
test('the suggestion list is sorted by type and loads more as it is scrolled', async ({ page }) => {
  await bootGmPanel(page, character)
  await enterPrep(page)

  await page.locator('.filter-input').fill('a')
  await page.waitForTimeout(900)

  const rows = page.locator('.filter-suggestions .suggestion-row')
  const first = await rows.count()
  expect(first, 'more than a screenful is offered').toBeGreaterThan(5)

  await page.locator('.filter-suggestions').evaluate((el) => { el.scrollTop = el.scrollHeight })
  await page.waitForTimeout(500)
  const grown = await rows.count()
  expect(grown, `scrolling to the end revealed the next page (was ${first})`).toBeGreaterThan(first)

  const CANONICAL = { CHARACTER: 0, GMC: 1, ASSET: 2, FACTION: 3, LOCATION: 4, UNIVERSE: 5 }
  const entityRows = await page.evaluate(() =>
    [...document.querySelectorAll('.filter-suggestions .suggestion-row')]
      .filter((r) => r.querySelector('.suggestion-hint')?.textContent?.trim() === 'name')
      .map((r) => r.querySelector('.entity-type-badge')?.textContent?.trim() || ''))

  const ranks = entityRows.map((t) => CANONICAL[t]).filter((r) => r !== undefined)
  expect(ranks.length, 'the rendered rows include entities').toBeGreaterThan(3)
  expect(ranks, `entity rows are grouped by type in the canonical order (${entityRows.join(', ')})`)
    .toEqual([...ranks].sort((a, b) => a - b))
})

// The ordering toggle: the standard order is the default and *Nearest* is the
// alternative, measured from where the GM is (the human, 2026-10-13: *"Use the
// current mode as default and the distance mode as alternative."*).
//
// The comparator itself is pinned in `check-place-filter.mjs`. What only a browser
// can show is that the mode reaches the rendered list: the map is fetched when the
// mode is first used, the rows come back reordered, each says how far it is, and
// the choice survives a reload because it is a device preference.
const stepOf = (label) => (label === 'here' ? 0 : Number(label.replace('+', '')))

test('the sort toggle orders the suggestions by distance from the GM', async ({ page }) => {
  await bootGmPanel(page, character)
  await enterPrep(page)

  const toggle = page.locator('.sort-toggle')
  await expect(toggle, 'the ordering toggle lives in the filter bar').toHaveCount(1)
  await expect(toggle, 'the default is the standard order').not.toHaveText(/Nearest/)

  await page.locator('.filter-input').fill('wang')
  await page.waitForTimeout(900)
  expect(await page.locator('.suggestion-distance').count(),
    'the default mode shows no distances').toBe(0)

  await toggle.click()
  await expect(toggle, 'the toggle says which order is on').toHaveText(/Nearest/)
  // The toggle click moves focus out of the filter box, which closes the list —
  // so put the caret back and let it open again before reading the rows.
  await page.locator('.filter-input').click()
  await page.waitForTimeout(1500)          // the map is one read, when it is wanted

  const labels = await page.evaluate(() =>
    [...document.querySelectorAll('.filter-suggestions .suggestion-row .suggestion-distance')]
      .map((s) => s.textContent.trim()))
  expect(labels.length, `rows say how far they are (${labels.join(', ')})`).toBeGreaterThan(3)

  const steps = labels.map(stepOf)
  expect(steps, `nearest first (${labels.join(', ')})`).toEqual([...steps].sort((a, b) => a - b))

  // A device preference, like the anchor and the window layout: it comes back.
  // The chain itself does not (the 🛠 open/closed state is deliberately not
  // persisted), so it has to be reopened before its filter bar exists.
  await page.reload()
  await page.waitForTimeout(2600)
  await openStack(page)
  await enterPrep(page)
  await expect(page.locator('.sort-toggle'), 'the mode survives a reload').toHaveText(/Nearest/)
  await page.locator('.filter-input').fill('wang')
  await page.waitForTimeout(1500)
  expect(await page.locator('.suggestion-distance').count(),
    'and it is still measuring, not just labelled').toBeGreaterThan(3)

  // …and back: the standard order returns, and the numbers go with the mode.
  await page.locator('.sort-toggle').click()
  await expect(page.locator('.sort-toggle'), 'the toggle flips back').not.toHaveText(/Nearest/)
  await page.locator('.filter-input').click()
  await page.waitForTimeout(600)
  expect(await page.locator('.suggestion-distance').count(),
    'no distances outside distance mode').toBe(0)
})
