// A cutout trait marker pops OUT of its chip (`B200`).
//
// The chip's picture is the trait's `navdot`-role image ([[Media Pipeline]] §Traits
// as image owners). A cutout has to break the chip's outline rather than be
// contained by it — that is the whole reason it is absolutely placed and sized off
// the text height instead of sitting in the chip's box like a thumbnail.
//
// The trait payload is mocked on purpose: this asserts the chip's own geometry, not
// the backend's resolution (that is `tests/test_location_trait_markers.py`), and it
// keeps the test free of live content. The images are data URIs with real intrinsic
// sizes, so "does it overhang" is exact rather than dependent on the art.

import { test, expect } from '@playwright/test'
import { gql } from '../helpers/sheet.js'

// NEVER a real player character — Kael Drift is the project's testing character, a
// main of a dedicated test player. Resolved by the relationship, not by name: the
// player has already been renamed once.
const KAEL = 'character-kael-drift-e555ccde'

/** A portrait cutout (2:3) and a square opaque picture, as data URIs. */
const CUTOUT = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='40' height='60'%3E%3Crect width='40' height='60' fill='%23cc44ff'/%3E%3C/svg%3E"
const OPAQUE = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='60' height='60'%3E%3Crect width='60' height='60' fill='%2344ccff'/%3E%3C/svg%3E"

const TRAITS = [
  {
    id: 'ts-cutout', trait_id: 'trait-cutout', name: 'spirit herb',
    statement: 'Corpse Lily', traitset_id: 'ts-1', sheet_tab: 'traits',
    rating_type: 'static', polarity: 'positive', sfx_ids: [], dice: ['d4'],
    capacity: [], owner_location_id: 'loc-x', owner_name: 'Somewhere',
    inherited: false, hidden: false, known_to: [],
    navdot_image: CUTOUT, navdot_transparent: true,
  },
  {
    id: 'ts-opaque', trait_id: 'trait-opaque', name: 'population',
    statement: '', traitset_id: 'ts-1', sheet_tab: 'traits',
    rating_type: 'static', polarity: 'positive', sfx_ids: [], dice: ['d6'],
    capacity: [], owner_location_id: 'loc-x', owner_name: 'Somewhere',
    inherited: false, hidden: false, known_to: [],
    navdot_image: OPAQUE, navdot_transparent: false,
  },
]

let character
test.beforeAll(async ({ request }) => {
  const { players } = await gql(request, `query { players { id name agency { entityId main } } }`)
  const owner = players.find((p) => (p.agency || []).some((a) => a.entityId === KAEL && a.main))
  if (!owner) throw new Error(`no player mains ${KAEL} — cannot reach the testing character`)
  character = { playerId: owner.id, playerName: owner.name, entityId: KAEL }
})

/** Plant the session and load the app with the trait payload mocked. */
async function openWithMockedTraits(page) {
  await page.setViewportSize({ width: 1280, height: 950 })
  // Both traits are PLACED with the character standing on them, so both chips are open:
  // the marker's composition is a property of the open chip, and unplaced chips only
  // exist in arrange mode now, so the stack is not a fixture this can lean on.
  await page.route('**/api/v1/locations/*/navigate*', (route) => route.fulfill({
    json: {
      location: { name: 'Marker Hall', zones: [], trait_positions: { 'ts-cutout': { x: 50, y: 50 }, 'ts-opaque': { x: 52, y: 50 } } },
      parent: null, children: [], transversal: [],
      occupants: [{ id: KAEL, type: 'character', name: 'Kael Drift', image: null, map_x: 50, map_y: 50 }],
    },
  }))
  await page.route('**/api/v1/locations/*/traits*', (route) =>
    route.fulfill({ json: { location_id: 'loc-x', viewer: null, traits: TRAITS } }))
  await page.route('**/api/v1/locations/*/pools**', (route) => route.fulfill({ json: { pools: {} } }))
  await page.goto('/')
  await page.evaluate(([pid, pname, eid]) => {
    localStorage.setItem('playerId', pid)
    localStorage.setItem('playerName', pname)
    localStorage.setItem('entityId', eid)
  }, [character.playerId, character.playerName, character.entityId])
  await page.goto('/')
  await expect(page.locator('.name-entry')).toHaveCount(0)
  // Open, or there is no marker composition on screen to measure.
  await expect(page.locator('.scene-chip.expanded')).toHaveCount(2)
}

/** The chip carrying `name`, with its picture decoded. */
async function chipFor(page, name) {
  const chip = page.locator('.trait-chip').filter({ hasText: name }).first()
  await expect(chip).toBeAttached()
  await expect.poll(
    () => chip.locator('img').evaluate((el) => el.complete && el.naturalWidth),
    { message: `the ${name} picture never loaded` }
  ).toBeGreaterThan(0)
  return chip
}

test('a cutout marker is taller than its chip, so it breaks the outline', async ({ page }) => {
  await openWithMockedTraits(page)

  const chip = await chipFor(page, 'spirit herb')
  const marker = chip.locator('.trait-chip-marker.transparent')
  await expect(marker).toBeAttached()

  const geom = await marker.evaluate((el) => {
    const img = el.querySelector('img')
    return {
      chip: el.closest('.trait-chip').getBoundingClientRect().toJSON(),
      img: img.getBoundingClientRect().toJSON(),
      markerBorder: getComputedStyle(el).borderTopWidth,
    }
  })

  expect(geom.img.height).toBeGreaterThan(geom.chip.height)
  expect(geom.img.top).toBeLessThan(geom.chip.top)
  expect(geom.img.bottom).toBeGreaterThan(geom.chip.bottom)
  // "Doesn't need to have a ring" — the marker adds no frame of its own.
  expect(geom.markerBorder).toBe('0px')
})

test('an opaque marker stays a contained thumbnail', async ({ page }) => {
  await openWithMockedTraits(page)

  const chip = await chipFor(page, 'population')
  const marker = chip.locator('.trait-chip-marker')
  await expect(marker).toBeAttached()
  await expect(marker).not.toHaveClass(/transparent/)

  const geom = await marker.evaluate((el) => {
    const img = el.querySelector('img')
    return {
      chip: el.closest('.trait-chip').getBoundingClientRect().toJSON(),
      img: img.getBoundingClientRect().toJSON(),
      radius: getComputedStyle(img).borderTopLeftRadius,
    }
  })

  // Contained: the picture is no taller than the chip it sits in.
  expect(geom.img.height).toBeLessThanOrEqual(geom.chip.height)
  expect(geom.img.top).toBeGreaterThanOrEqual(geom.chip.top - 1)
  expect(geom.radius).toBe('50%')
})
