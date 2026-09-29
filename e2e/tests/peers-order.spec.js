import { test, expect } from '@playwright/test'
import { gql } from '../helpers/sheet.js'
// The shared order the relationship list and the location tree already use. The
// point of this spec is that the peers bar agrees with *this*, not with a copy.
import { buildAgencyIndex, entityTypeRank } from '../../src/frontend/src/constants/entityTypes.js'
import { establishSession } from '../helpers/session.js'

// The peer tabs are ordered like every other entity list on the sheet: mains,
// supports, then by type, alphabetical inside each group — with the entity you
// act as pinned first, since the strip scrolls and your own tab has to be
// reachable without hunting.
//
// Why it is a *determinism* fix and not just tidiness: the old order was a local
// map (`{ CHARACTER: 0, GMC: 1, ASSET: 2, LOCATION: 3 }`) with no tiebreak, and
// the entity list arrives unsorted (the query has no SORT). So peers of one type
// came out in whatever order the database returned, and two loads could differ.
// Faction and universe were absent from the map entirely, which put a faction
// *after* every location.

/**
 * A location with several peer types, plus an entity there to act as.
 *
 * Acted as: the entity the peers bar marks `assumed`, seeded so the bar has a
 * location to list. Deliberately never a `CHARACTER` — those are players'
 * characters, and an agent may not act as one. A GMC, or failing that any
 * non-character, is enough to put the bar on screen.
 */
async function findPeersData(request) {
  const data = await gql(request, `query {
    entities { id name type currentLocation unpublished }
    players { id name agency { entityId main } }
  }`)
  const agency = buildAgencyIndex(data.players)
  const every = data.entities || []
  // Membership mirrors the bar's own: everyone standing here — `unpublished`
  // hidden for a player — plus **the location itself**, which is prepended
  // because a location's `currentLocation` is its *parent*, so it is never in
  // the "standing here" set. The order is what this spec is about, so the
  // membership is taken as given; only the sequence is re-derived.
  const members = (locationId) => {
    const standing = every.filter((e) => e.currentLocation === locationId && !e.unpublished)
    const here = every.find((e) => e.id === locationId)
    return here && !standing.some((e) => e.id === here.id) ? [here, ...standing] : standing
  }
  const locations = [...new Set(every.map((e) => e.currentLocation).filter(Boolean))]
  const at = new Map(locations.map((id) => [id, members(id)]))
  let best = null
  for (const [locationId, peers] of at) {
    const buckets = new Set(peers.map((p) => entityTypeRank(p.type, agency.get(p.id))))
    // Prefer a roster that also has a faction *and* a location: that pair is
    // where the old map ordered them backwards, so it is the roster that can
    // catch a regression rather than one that happens to sort the same way.
    const decisive = peers.some((p) => p.type === 'FACTION') && peers.some((p) => p.type === 'LOCATION')
    const score = buckets.size + (decisive ? 10 : 0) + peers.length / 100
    if (peers.length >= 4 && buckets.size >= 3 && (!best || score > best.score)) {
      best = { locationId, peers, agency, score }
    }
  }
  if (!best) return null
  const actor = best.peers.find((p) => p.type === 'GMC')
    || best.peers.find((p) => p.type !== 'CHARACTER')
  return { ...best, actor }
}

/** The order the rule asks for, from the shared helper. */
function expectedOrder({ peers, agency, actor }) {
  const byName = { sensitivity: 'base' }
  return peers
    .slice()
    .sort((a, b) => {
      if (a.id === actor.id) return -1
      if (b.id === actor.id) return 1
      return (entityTypeRank(a.type, agency.get(a.id)) - entityTypeRank(b.type, agency.get(b.id)))
        || String(a.name || '').localeCompare(String(b.name || ''), undefined, byName)
        || String(a.id).localeCompare(String(b.id))
    })
    .map((p) => p.name)
}

async function load(page, entityId) {
  await page.setViewportSize({ width: 1280, height: 950 })
  await page.goto('/')
  await page.evaluate((id) => {
    localStorage.setItem('playerId', 'player-75a410')
    localStorage.setItem('playerName', 'DSH MCP')
    localStorage.setItem('entityId', id)
    // Pinned, because the bar hides `unpublished` entities per `gmMode` and the
    // expectation below has to filter by the same rule. GM mode is where
    // `get_scene_store`-style drafts are meant to be visible; this spec is about
    // the order, so it asks for the plain player view and says so.
    localStorage.setItem('architectMode', 'false')
  }, entityId)
  await establishSession(page)
  await page.goto('/')
  await page.waitForFunction(() => !!document.querySelector('.stage'), null, { timeout: 20_000 })
  await page.waitForTimeout(2500)
  const dot = page.locator('button.map-dot.self').first()
  if (await dot.count()) { await dot.click().catch(() => {}); await page.waitForTimeout(1200) }
}

const chipNames = (page) => page.evaluate(() =>
  [...document.querySelectorAll('.peers-bar .peer-chip .peer-label')].map((e) => e.innerText.trim()))

test('the peer tabs follow the shared entity order', async ({ page, request }) => {
  const data = await findPeersData(request)
  test.skip(!data || !data.actor, 'no location with a mixed peer roster to check')

  await load(page, data.actor.id)
  const shown = await chipNames(page)
  const want = expectedOrder(data)
  console.log('[peers]', JSON.stringify({ location: data.locationId, actor: data.actor.name, shown, want }))

  expect(shown.length, 'the bar lists the location\'s peers').toBeGreaterThan(1)
  expect(shown, 'the bar agrees with the shared order').toEqual(want)
  // Your own tab is first, and is drawn as yours.
  expect(shown[0]).toBe(data.actor.name)
  await expect(page.locator('.peers-bar .peer-chip').first()).toHaveClass(/assumed/)
})

test('the order does not change between loads', async ({ page, request }) => {
  const data = await findPeersData(request)
  test.skip(!data || !data.actor, 'no location with a mixed peer roster to check')

  await load(page, data.actor.id)
  const first = await chipNames(page)
  // A fresh load is a fresh fetch — the entity list has no SORT, so the old
  // build's order came straight from the database and was not guaranteed stable.
  await load(page, data.actor.id)
  const second = await chipNames(page)
  console.log('[peers] load 1:', JSON.stringify(first))
  console.log('[peers] load 2:', JSON.stringify(second))
  expect(second).toEqual(first)
  expect(first.length).toBeGreaterThan(1)
})
