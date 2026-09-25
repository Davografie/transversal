// The location renders larger on a narrow viewer, and exactly as before on a wide one.
//
// Chips, dots and the background all live in the scene layer, so the scene's size is
// what sets how far apart they sit in pixels. A chip is a FIXED number of pixels, so
// the narrower the viewer, the smaller the share of the scene it covers — which is why
// a busy location crowds on a phone and not in the docked desktop view. The viewer
// compensates by width (`locationScale`), and this pins both halves of that: the phone
// gets more scale, the wide layout gets none.
//
// Both reads are mocked, so the location is identical in every case and only the
// viewport differs.

import { test, expect } from '@playwright/test'
import { gql } from '../helpers/sheet.js'

const KAEL = 'character-kael-drift-e555ccde'
const LOC = 'loc-scale-test'

const TRAIT = {
  id: 'ts-one', trait_id: 'trait-one', name: 'spirit herb', statement: 'Corpse Lily',
  traitset_id: 'ts-1', sheet_tab: 'traits', rating_type: 'static', polarity: 'positive',
  sfx_ids: [], dice: ['d4'], capacity: [], owner_location_id: LOC, owner_name: 'Somewhere',
  inherited: false, hidden: false, known_to: [], navdot_image: null, navdot_transparent: false,
}

let character
test.beforeAll(async ({ request }) => {
  const { players } = await gql(request, `query { players { id name agency { entityId main } } }`)
  const owner = players.find((p) => (p.agency || []).some((a) => a.entityId === KAEL && a.main))
  if (!owner) throw new Error(`no player mains ${KAEL} — cannot reach the testing character`)
  character = { playerId: owner.id, playerName: owner.name, entityId: KAEL }
})

/** Scene width ÷ viewer width at a given viewport — how much the map overflows. */
async function ratioAt(page, size) {
  await page.route('**/api/v1/locations/*/navigate*', (route) => route.fulfill({
    json: {
      location: { name: 'Scale Hall', zones: [], trait_positions: { 'ts-one': { x: 50, y: 50 } } },
      parent: null, children: [], transversal: [],
      occupants: [{ id: KAEL, type: 'character', name: 'Kael Drift', image: null, map_x: 50, map_y: 50 }],
    },
  }))
  await page.route('**/api/v1/locations/*/traits*', (route) =>
    route.fulfill({ json: { location_id: LOC, viewer: null, traits: [TRAIT] } }))
  await page.route('**/api/v1/locations/*/pools**', (route) => route.fulfill({ json: { pools: {} } }))

  await page.setViewportSize(size)
  await page.goto('/')
  await page.evaluate(([pid, pname, eid, loc]) => {
    localStorage.setItem('playerId', pid)
    localStorage.setItem('playerName', pname)
    localStorage.setItem('entityId', eid)
    localStorage.setItem('currentLocationId', loc)
  }, [character.playerId, character.playerName, character.entityId, LOC])
  await page.goto('/')

  await expect(page.locator('.scene-layer')).toBeAttached()
  await expect(page.locator('.name-entry')).toHaveCount(0)
  return page.evaluate(() => {
    const layer = document.querySelector('.scene-layer').getBoundingClientRect()
    const viewer = document.querySelector('.location-viewer').getBoundingClientRect()
    return layer.width / viewer.width
  })
}

test('a narrow viewer gets a larger location, a wide one is left alone', async ({ page }) => {
  const wide = await ratioAt(page, { width: 1440, height: 950 })
  const phone = await ratioAt(page, { width: 390, height: 844 })
  console.log('scene÷viewer — wide:', wide.toFixed(2), 'phone:', phone.toFixed(2))

  // The phone is compensating; the wide layout is the plain cover + overscan.
  expect(phone).toBeGreaterThan(wide * 1.25)

  // …and the compensation is capped, so a very narrow viewer still sees a map rather
  // than a single corner of one.
  const tiny = await ratioAt(page, { width: 320, height: 844 })
  expect(tiny).toBeLessThanOrEqual(phone + 0.01)
})
