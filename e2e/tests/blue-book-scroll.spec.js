// Blue Book scroll behaviour: it opens on the newest entry, and a refresh never moves
// a reader who has scrolled up.
//
// This is the browser side of a bug the API suite cannot see: `fetch()` runs on every
// SSE `location_changed`, so *any* travel used to drag the book's scroll position out
// from under whoever was reading it. Three separate mechanisms did it — the scripted
// jump itself, the loading state unmounting the list (an unmounted list cannot hold a
// scroll position), and the empty-then-refill that forced the entry cascade. Each of
// those looks defensible on its own, which is why the checks here are behavioural.
//
// Data-dependent by nature: it needs a Blue Book long enough to scroll. It picks the
// player-controlled character with the most entries and skips when nothing is
// scrollable, rather than pinning a character id that a fresh database will not have.

import { test, expect } from '@playwright/test'
import { gql, openSheet } from '../helpers/sheet.js'

/** The player-controlled character with the most Blue Book entries. */
async function busiestBlueBook(request) {
  const { players } = await gql(request, `query { players { id name agency { entityId main } } }`)
  const candidates = []
  for (const p of players) {
    for (const e of p.agency || []) {
      if (!String(e.entityId).startsWith('character-')) continue
      candidates.push({ playerId: p.id, playerName: p.name, entityId: e.entityId })
    }
  }
  let best = null
  for (const c of candidates) {
    const { historicalRecords } = await gql(request,
      `query($id: ID!){ historicalRecords(entityId: $id){ id } }`, { id: c.entityId })
    const { timeline } = await gql(request,
      `query($id: ID!){ timeline(entityId: $id){ id } }`, { id: c.entityId })
    const n = (historicalRecords?.length || 0) + (timeline?.length || 0)
    if (!best || n > best.n) best = { ...c, n }
  }
  return best
}

test('the book opens on the newest entry and never scrolls itself under the reader', async ({ page, request }) => {
  test.setTimeout(120_000)

  const who = await busiestBlueBook(request)
  test.skip(!who?.n, 'no Blue Book entries in this database')

  await openSheet(page, who)
  await page.locator('button.pill', { hasText: '📘' }).first().click()
  const entries = page.locator('.bb-entries').first()
  await entries.waitFor({ state: 'visible', timeout: 20_000 })
  await page.locator('.bb-entry').first().waitFor({ state: 'visible', timeout: 20_000 })

  const readGeom = () => entries.evaluate((n) => ({
    top: Math.round(n.scrollTop),
    gap: Math.round(n.scrollHeight - n.scrollTop - n.clientHeight),
    scrollable: n.scrollHeight - n.clientHeight > 100,
  }))

  // The entries' images arrive after the first paint and grow the content under it,
  // so the opening position is only settled once they have landed.
  await page.waitForTimeout(2_000)
  const opened = await readGeom()
  test.skip(!opened.scrollable, 'this Blue Book is too short to scroll; nothing to verify')
  expect(opened.gap, 'opens with the newest entry in view').toBeLessThanOrEqual(24)

  // The reader's own gesture, not a programmatic scroll: intent is read from input,
  // because the browser moves scrollTop by itself while content loads (scroll
  // anchoring) and geometry cannot tell that from a gesture.
  const wheel = async (deltaY) => {
    const box = await entries.boundingBox()
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2)
    await page.mouse.wheel(0, deltaY)
    await page.waitForTimeout(400)
  }
  // Engines disagree about the distance one wheel event travels (Firefox moves a
  // fraction of what Chromium does), so lean on the geometry instead of the delta:
  // keep wheeling until the edge is actually reached.
  const scrollUntil = async (edge) => {
    for (let i = 0; i < 14; i++) {
      const m = await readGeom()
      const arrived = edge === 'top' ? m.top <= 24 : m.gap <= 24
      if (arrived) return m
      await wheel(edge === 'top' ? -3000 : 3000)
    }
    return readGeom()
  }

  // `refresh()` is the method App.vue calls as `refreshBlueBook()` on an SSE
  // `location_changed` — the exact path that used to jump the book, reachable without
  // mutating anyone's data. It is also a real contract: the exposed name is what the
  // sheet and App call.
  const refresh = () => page.evaluate(() => {
    const inst = document.querySelector('.bb-entries').__vueParentComponent
    if (!inst?.exposed?.refresh) throw new Error('BlueBook no longer exposes refresh()')
    return inst.exposed.refresh()
  })

  // A reader part-way through the history must survive a refresh untouched — parked
  // mid-list on purpose: at the very top, "preserved" and "reset" look identical.
  await scrollUntil('top')
  await wheel(600)
  const parked = await readGeom()
  expect(parked.top, 'reader parked mid-history').toBeGreaterThan(50)
  await refresh()
  await page.waitForTimeout(1_500)
  const afterRefresh = await readGeom()
  expect(Math.abs(afterRefresh.top - parked.top), 'a refresh leaves the reader where they were').toBeLessThanOrEqual(80)

  // A reader who is at the end stays there, and still gets new entries revealed.
  await scrollUntil('end')
  await refresh()
  await page.waitForTimeout(1_500)
  expect((await readGeom()).gap, 'a refresh keeps a reader at the end at the end').toBeLessThanOrEqual(24)
})
