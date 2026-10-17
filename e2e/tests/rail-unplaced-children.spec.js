// A child location with no hotspot on its parent's map is listed in the arrange-mode
// drawer, and dragging a row out CREATES the zone (human, 2026-10-17).
//
// Why this exists: `_ensure_child_zone` runs from the repository's `create_relationship`,
// but the REST `create_edge` the GM tree uses inserts the edge document directly — so a
// reparent leaves the child linked and **invisible on the parent's map**, with no way to
// give it a hotspot from the UI. Measured 2026-10-17: 43 such children in the global
// content. This is the escape hatch until that writer is fixed.
//
// What makes it a rail item rather than a code fix: most of those 43 are geographic
// containers (Asia, Africa, Europe) where a pin on the parent map may be pointless, so a
// blanket backfill would scatter arbitrary dots. Placing is a per-parent decision.
//
// The put body is asserted in full, not just its length: `/zones` REPLACES the list, so a
// new row that forgets to echo the existing entries strips their `location_id` — and the
// child silently stops resolving.

import { test, expect } from '@playwright/test'
import { gql } from '../helpers/sheet.js'
import { asArchitect, enterArrangeMode } from '../helpers/arrange.js'
import { establishSession } from '../helpers/session.js'

const KAEL = 'character-kael-drift-e555ccde'
const LOC = 'loc-rail-zones-test'

const PLACED_CHILD = 'loc-rail-zone-placed'
const UNPLACED_CHILD = 'loc-rail-zone-unplaced'
const PLACED_NAME = 'Gilded Basin'
const UNPLACED_NAME = 'Astral Peaks'

let character
test.beforeAll(async ({ request }) => {
  const { players } = await gql(request, `query { players { id name agency { entityId main } } }`)
  const owner = players.find((p) => (p.agency || []).some((a) => a.entityId === KAEL && a.main))
  if (!owner) throw new Error(`no player mains ${KAEL} — cannot reach the testing character`)
  character = { playerId: owner.id, playerName: owner.name, entityId: KAEL }
})

const svg = (fill) =>
  `data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='40' height='40'%3E%3Crect width='40' height='40' fill='%23${fill}'/%3E%3C/svg%3E`

// One trait left unplaced as well, so the rail SURVIVES the placement and the zone row can
// be asserted gone specifically — rather than "the whole rail vanished because it is now
// empty", which would pass even if the row were never shown.
const TRAIT = {
  id: 'ts-rail', trait_id: 'trait-rail', name: 'spirit herb', statement: '',
  traitset_id: 'ts-1', sheet_tab: 'traits', rating_type: 'static', polarity: 'positive',
  sfx_ids: [], dice: ['d4'], capacity: [], owner_location_id: LOC, owner_name: 'Somewhere',
  inherited: false, hidden: false, known_to: [],
  navdot_image: null, navdot_transparent: false,
}

function navigatePayload() {
  return {
    location: {
      name: 'Rail Hall',
      zones: [{ location_id: PLACED_CHILD, x: 30, y: 30, background_image: null }],
      trait_positions: {},
      nav_positions: {},
    },
    parent: null,
    children: [
      { _key: PLACED_CHILD, name: PLACED_NAME, navdot_image: svg('33aa66'), background_image: null },
      { _key: UNPLACED_CHILD, name: UNPLACED_NAME, navdot_image: svg('aa6633'), background_image: null },
    ],
    transversal: [],
    occupants: [{ id: KAEL, type: 'character', name: 'Kael Drift', image: null, map_x: 60, map_y: 60 }],
  }
}

/** Load in arrange mode with the rail open, capturing every zone write. */
async function open(page) {
  await asArchitect(page)
  await page.route('**/api/v1/locations/*/navigate*', (route) => route.fulfill({ json: navigatePayload() }))
  await page.route('**/api/v1/locations/*/traits*', (route) =>
    route.fulfill({ json: { location_id: LOC, viewer: null, traits: [TRAIT] } }))
  await page.route('**/api/v1/locations/*/pools**', (route) => route.fulfill({ json: { pools: {} } }))

  const writes = []
  await page.route('**/api/v1/locations/*/zones', (route) => {
    if (route.request().method() === 'PUT') writes.push(route.request().postDataJSON())
    return route.fulfill({ json: { status: 'ok', count: 2 } })
  })

  await page.setViewportSize({ width: 1280, height: 950 })
  await page.goto('/')
  await page.evaluate(([pid, pname, eid, loc]) => {
    localStorage.setItem('playerId', pid)
    localStorage.setItem('playerName', pname)
    localStorage.setItem('entityId', eid)
    localStorage.setItem('currentLocationId', loc)
  }, [character.playerId, character.playerName, character.entityId, LOC])
  await establishSession(page)
  await page.goto('/')

  await expect(page.locator('.name-entry')).toHaveCount(0)
  await enterArrangeMode(page)
  // The rail is open-on-demand: arrange mode alone does not reveal it.
  await page.locator('.top-control').click()

  return {
    writes,
    row: page.locator('.zone-drawer-chip', { hasText: UNPLACED_NAME }),
  }
}

test('a zoneless child is listed in the drawer; a zoned one is not', async ({ page }) => {
  const { row } = await open(page)

  // The count is traits + occupants + zoneless children: one trait, no unplaced
  // occupants, one child. `toHaveText` is exact on purpose — a substring match would
  // accept the `unplaced · 25[object Object]` bug the count was fixed for.
  await expect(page.locator('.top-control')).toHaveText('unplaced · 2')
  await expect(row).toHaveCount(1)
  await expect(row).toContainText(UNPLACED_NAME)
  // The already-placed child must NOT be offered as placeable.
  await expect(page.locator('.zone-drawer-chip', { hasText: PLACED_NAME })).toHaveCount(0)
  // …and it is drawn, because it has a hotspot.
  await expect(page.locator('.zone-dot')).toHaveCount(1)
})

test('dragging a drawer row out creates the zone, and keeps the existing ones', async ({ page }) => {
  const { writes, row } = await open(page)
  await expect(row).toHaveCount(1)

  const box = await row.boundingBox()
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2)
  await page.mouse.down()
  // Onto the map, well clear of the rail.
  await page.mouse.move(760, 520, { steps: 14 })
  await page.mouse.up()

  await expect.poll(() => writes.length).toBe(1)
  const body = writes[0]

  // The new hotspot, linked to the child it stands for.
  const added = body.find((z) => z.location_id === UNPLACED_CHILD)
  expect(added).toBeTruthy()
  expect(added.x).toBeGreaterThanOrEqual(2)
  expect(added.x).toBeLessThanOrEqual(98)
  expect(added.y).toBeGreaterThanOrEqual(2)
  expect(added.y).toBeLessThanOrEqual(98)

  // `/zones` REPLACES the list: the pre-existing entry has to survive the write intact,
  // or its child silently stops resolving on the map.
  expect(body).toHaveLength(2)
  expect(body.find((z) => z.location_id === PLACED_CHILD))
    .toEqual({ location_id: PLACED_CHILD, x: 30, y: 30, background_image: null })

  // It is a hotspot now: the row leaves the drawer and a second dot is on the map.
  await expect(page.locator('.zone-drawer-chip', { hasText: UNPLACED_NAME })).toHaveCount(0)
  await expect(page.locator('.zone-dot')).toHaveCount(2)
  // …and only the trait is still unplaced, which is the count's own statement.
  await expect(page.locator('.top-control')).toHaveText('unplaced · 1')
})

test('the drag does not arm the unplace target', async ({ page }) => {
  const { row } = await open(page)
  const box = await row.boundingBox()

  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2)
  await page.mouse.down()
  await page.mouse.move(700, 500, { steps: 10 })

  // A child being placed has nothing to unplace — it is already off the map — so the
  // control must stay the rail's handle and never become `( x )`.
  await expect(page.locator('.top-control')).not.toHaveClass(/unplace-armed/)
  await page.mouse.up()
})
