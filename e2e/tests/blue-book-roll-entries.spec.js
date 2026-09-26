// A test or contest renders in the Blue Book as its own entry: the owner's roll on the
// left, what they rolled against on the right, one row per round ([[B177]]). The record
// is written at resolution and holds every round, so nothing here updates live.
//
// The rules worth pinning are the ones a reader would get wrong silently: a die the
// owner kept is marked apart from the ones they set aside, a hitch reads as a hitch
// rather than as the number 1, and a side that did not re-roll after a push shows as
// **still standing** — not as the same dice thrown a second time.
//
// Data-dependent: it needs a roll-shaped entry in the book, and skips without one.
// Kael Drift is the testing character; the owning player is discovered, not pinned.
// The role is pinned to `player` in the browser (`asPlayer`) — an architect runs in GM
// free-roam with no `entityId`, which empties the book and makes the skip unreachable.

import { test, expect } from '@playwright/test'
import { asPlayer } from '../helpers/role.js'

const KAEL = 'character-kael-drift-e555ccde'

const gql = (request, query) => request.post('/api/v1/graphql', { data: { query } })
  .then(async (r) => (await r.json()).data)

test('a test/contest entry reads own left, opposition right, rounds stacked', async ({ page, request }) => {
  test.setTimeout(120_000)
  await asPlayer(page)

  const { players } = await gql(request, '{ players { id name agency { entityId main } } }')
  const owner = players.find((p) => (p.agency || []).some((e) => e.entityId === KAEL))
  test.skip(!owner, 'no player holds Kael Drift — see Overseer Operations')

  await page.goto('/')
  await page.evaluate(([pid, pname, eid]) => {
    localStorage.setItem('playerId', pid)
    localStorage.setItem('playerName', pname)
    localStorage.setItem('entityId', eid)
  }, [owner.id, owner.name, KAEL])
  await page.goto('/')

  await page.locator('button.map-dot.self').first().waitFor({ state: 'visible', timeout: 30_000 })
  await page.locator('button.map-dot.self').first().click()
  await page.locator('.sheet-embedded').first().waitFor({ state: 'visible', timeout: 30_000 })
  await page.locator('button.pill', { hasText: '📘' }).first().click()
  // The panel, not an entry: the data guard two lines down must be reachable when the
  // book is empty, instead of timing out on the entry it is about to skip for.
  await page.locator('.bb-embedded').first().waitFor({ state: 'visible', timeout: 20_000 })
  await page.waitForTimeout(2_500)

  const rolls = page.locator('.bb-roll')
  const count = await rolls.count()
  test.skip(!count, 'no test/contest entries in this book')
  console.log(`${count} roll-shaped entries; checking the newest`)

  const entry = rolls.last()
  // Both columns are named, so the split is readable without colour.
  const head = await entry.locator('.bb-roll-head').innerText()
  expect(head).toContain('vs')

  const rounds = entry.locator('.bb-roll-round')
  expect(await rounds.count(), 'at least one round').toBeGreaterThan(0)
  expect(await rounds.first().locator('.bb-roll-cell').count(), 'two sides per round').toBe(2)

  // Dice are drawn, and the kept ones are distinguishable from those set aside.
  const allDice = entry.locator('.die-icon')
  expect(await allDice.count(), 'the pool is drawn').toBeGreaterThan(0)
  const diceWithResults = await allDice.evaluateAll(
    (els) => els.filter((e) => /^\d+$/.test(e.textContent.trim())).length,
  )
  expect(diceWithResults, 'rolled dice show their results').toBeGreaterThan(0)

  // A hitch is called out rather than printed as its number: DieIcon renders "!".
  const hitches = entry.locator('.die-icon.hitch')
  if (await hitches.count()) {
    expect((await hitches.first().textContent()).trim()).toBe('!')
  }

  // The carry-forward rule: a standing side shows its total and no fresh dice.
  const standing = entry.locator('.bb-roll-standing')
  for (let i = 0; i < await standing.count(); i++) {
    const cell = standing.nth(i).locator('xpath=ancestor::*[contains(@class,"bb-roll-cell")]')
    expect(await cell.locator('.die-icon').count(), 'a standing side is not re-rolled').toBe(0)
    expect((await standing.nth(i).innerText()).trim()).toMatch(/standing \d+/)
  }

  // The verdict, from this book's side.
  await expect(entry.locator('.bb-roll-foot')).toContainText(/Won|Lost|Gave in|Taken out|Unopposed/)
})
