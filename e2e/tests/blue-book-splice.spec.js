// The Blue Book's *position*: clicking a location re-enters it without writing a leg
// (a **seek**), and the next travel is spliced in there rather than appended —
// A→B→C→D, click B, travel E reads A→B→E→C→D ([[B173]]).
//
// Both halves are pinned because either can break silently: a seek that records a leg
// turns the path into a branch, and a splice that does not happen appends the leg to
// the end, which looks like success until you read the chain. The chain is never reset
// between runs, so every assertion identifies *this* run's records by id and clicks
// this run's own seam.
//
// Kael Drift is the testing character (AGENTS.md § Player characters & the testing
// character); this drives Kael and never a player's PC, and its owning player is
// *discovered* rather than pinned — that identity has already been renamed once. It
// travels Kael, which is the point: the chain it reads is the one it just made.
import { test, expect } from '@playwright/test'

const KAEL = 'character-kael-drift-e555ccde'
const A = { id: 'loc-148649253', name: 'Ardennes' }
const B = { id: 'loc-148699243', name: 'Kremlin' }
const C = { id: 'loc-155592996', name: 'Beijing' }
const D = { id: 'loc-155593437', name: 'Tokyo' }
const E = { id: 'loc-155571988', name: 'JFK Airport' }

const gql = (request, query) => request.post('/api/v1/graphql', { data: { query } })
  .then(async (r) => (await r.json()).data)

/** The player who holds Kael Drift as a main — discovered, not pinned: the test
 *  identity has already been renamed once, and its id could move with it. */
async function kaelOwner(request) {
  const { players } = await gql(request, '{ players { id name agency { entityId main } } }')
  const owner = players.find((p) => (p.agency || []).some((e) => e.entityId === KAEL))
  if (!owner) throw new Error('no player holds Kael Drift — see Overseer Operations')
  return owner
}
const records = async (request) =>
  (await gql(request, '{ historicalRecords(entityId: "' + KAEL + '") { id data afterIds } }')).historicalRecords
const travel = (request, loc) => request.post('/api/v1/entities/' + KAEL + '/consciousness-travel',
  { data: { location: loc, projection_policy: '{closest_projection}' } })

test('a seek records nothing, and the next travel splices in at that point', async ({ page, request }) => {
  test.setTimeout(180_000)

  // These are real locations in the dev database; a fresh one may not have them.
  const names = (await gql(request, '{ entities(type: LOCATION) { id name } }')).entities
  const have = new Set(names.map((l) => l.id))
  test.skip(![A, B, C, D, E].every((l) => have.has(l.id)),
    'the fixture locations are not in this database')

  // A→B→C→D, then back to B so the click's seek is a no-op even against an API that
  // does not know `seek` yet (an unchanged location writes no record either way).
  const idsAtStart = new Set((await records(request)).map((x) => x.id))
  for (const loc of [A, B, C, D, B]) {
    const r = await travel(request, loc.id)
    if (r.status() !== 200) throw new Error(`travel to ${loc.name} failed: ${r.status()} ${await r.text()}`)
  }
  await page.waitForTimeout(500)
  const before = await records(request)
  console.log('records before the click:', before.length)

  const owner = await kaelOwner(request)
  await page.goto('/')
  await page.evaluate(([pid, pname, eid]) => {
    localStorage.setItem('playerId', pid); localStorage.setItem('playerName', pname); localStorage.setItem('entityId', eid)
  }, [owner.id, owner.name, KAEL])
  await page.goto('/')
  await page.locator('button.map-dot.self').first().waitFor({ state: 'visible', timeout: 30_000 })
  await page.locator('button.map-dot.self').first().click()
  await page.locator('.sheet-embedded').first().waitFor({ state: 'visible', timeout: 30_000 })
  await page.locator('button.pill', { hasText: '📘' }).first().click()
  await page.locator('.bb-entry').first().waitFor({ state: 'visible', timeout: 20_000 })
  await page.waitForTimeout(2_000)

  const titles = () => page.locator('.bb-record-locations [title]')
    .evaluateAll((els) => els.map((e) => (e.getAttribute('title') || '').replace('Travel to ', '')))
  const path = async () => (await titles()).join(' → ')
  console.log('path before:', await path())

  // Click *this run's* arrival at B — the Kremlin that this run's Ardennes leg leads
  // into. The chain accumulates across runs, so the first Kremlin on screen belongs to
  // an earlier one; this run's chain is the tail, ending Ardennes → B → C → D → B, so
  // its A→B arrival is the second-to-last Kremlin.
  const kremlins = page.locator(`.bb-record-locations [title="Travel to ${B.name}"]`)
  const n = await kremlins.count()
  expect(await path(), 'this run\'s chain is the tail').toContain(
    `${A.name} → ${B.name} → ${C.name} → ${D.name} → ${B.name}`)
  await kremlins.nth(n - 2).click()
  await page.waitForTimeout(3_000)

  const afterSeek = await records(request)
  console.log('records after the seek:', afterSeek.length)
  expect(afterSeek.length, 'a seek writes no record').toBe(before.length)

  // The next travel, from anywhere, belongs at that position.
  const idsBeforeTravel = new Set((await records(request)).map((x) => x.id))
  const r = await travel(request, E.id)
  console.log('out-of-band travel to', E.name, ':', r.status())

  // This run's records only: the chain is never reset, so every earlier run left
  // records naming the same locations.
  const mine = () => records(request).then((rs) => rs.filter(
    (x) => !idsAtStart.has(x.id) && !idsBeforeTravel.has(x.id),
  ))
  let placed = null
  for (let i = 0; i < 24; i++) {
    await page.waitForTimeout(500)
    placed = (await mine()).find((x) => x.data.to_location === E.id)
    if (placed && (placed.afterIds || []).length) break
  }
  const all = await records(request)
  const newAB = all.find((x) => x.data.from_name === A.name && x.data.to_name === B.name && !idsAtStart.has(x.id))
  const newBC = all.find((x) => x.data.from_name === B.name && x.data.to_name === C.name && !idsAtStart.has(x.id))
  console.log('E record', placed?.id, 'after:', JSON.stringify(placed?.afterIds))
  console.log('A→B record', newAB?.id)
  console.log('B→C record', newBC?.id, 'after:', JSON.stringify(newBC?.afterIds))
  console.log('path after:', await path())

  expect(placed?.afterIds, 'the new leg follows the record that ended at the clicked place').toEqual([newAB.id])
  expect(newBC?.afterIds, 'and the old successor now follows the new leg').toEqual([placed.id])
  expect(await path(), 'the book reads A→B→E→C→D').toContain(
    `${A.name} → ${B.name} → ${E.name} → ${C.name} → ${D.name}`)
})
