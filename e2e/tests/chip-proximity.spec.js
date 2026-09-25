// A placed trait chip rests as its marker and opens by proximity, pointer or tap
// (`B92`). Three rules, all from the human (2026-09-25):
//
//   * resting, a chip is ONLY its marker — the trait's picture, or its rating when
//     it has no picture;
//   * it opens when the character is near, when the pointer is over it, or on a tap
//     — and proximity holds it open at rest, which the nav bubbles do not do (they
//     expand only while a drag is running);
//   * a tap on a chip that is not open yet opens it, and the tap after that plays
//     the trait. Without that two-step a resting marker — no words, no pill — would
//     spend a die on a tap that only meant to read it.
//
// Both REST reads are mocked, with the real shapes: the rule is about GEOMETRY (the
// chip's position against the character's), and driving that from live content would
// mean walking the testing character around a real room until it hit a radius. The
// mocks match ANY location on purpose — the app moves to the character's own location
// once the entity fetch lands, so naming one here would not hold.
//
// The spend is stubbed: this spec owns the gesture, not the play rules (those are
// `scripts/check-trait-play.mjs`), and a real spend would eat a die of real content.

import { test, expect } from '@playwright/test'
import { gql } from '../helpers/sheet.js'

// NEVER a real player character — Kael Drift is the project's testing character, a
// main of a dedicated test player. The owner is resolved by the RELATIONSHIP rather
// than by name: the player has already been renamed once, and a name lookup broke a
// suite the moment it happened. The *player* has to be a real one — seeding a made-up
// id leaves the login overlay up, which is what a pointer test cannot see through.
const KAEL = 'character-kael-drift-e555ccde'
const LOC = 'loc-chip-proximity-test'

let character
test.beforeAll(async ({ request }) => {
  const { players } = await gql(request, `query { players { id name agency { entityId main } } }`)
  const owner = players.find((p) => (p.agency || []).some((a) => a.entityId === KAEL && a.main))
  if (!owner) throw new Error(`no player mains ${KAEL} — cannot reach the testing character`)
  character = { playerId: owner.id, playerName: owner.name, entityId: KAEL }
})

const HERB_AT = { x: 30, y: 30 }     // the chip with a picture
const RATING_AT = { x: 20, y: 40 }   // the chip without one — placed clear of the other,
                                     // because two expanded chips at one point overlap
                                     // and the lower one cannot be hovered at all
// Where the character stands for the "nothing is open" cases: outside the 24% radius
// of both chips, but near enough that they are still ON SCREEN — the camera anchors on
// the character, so a distant chip cannot be hovered at all.
const FAR = { x: 58, y: 54 }
const NEAR = { x: 32, y: 33 }        // inside the radius of both

const WITH_IMAGE = 'ts-herb'
const RATING_ONLY = 'ts-rating'
const STACKED = 'ts-stacked'

const CUTOUT = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='40' height='60'%3E%3Crect width='40' height='60' fill='%23cc44ff'/%3E%3C/svg%3E"

function trait(id, extra) {
  return {
    id, trait_id: `trait-${id}`, name: id === WITH_IMAGE ? 'spirit herb' : 'population',
    statement: '', traitset_id: 'ts-1', sheet_tab: 'traits',
    rating_type: 'static', polarity: 'positive', sfx_ids: [], dice: ['d4'],
    capacity: [], owner_location_id: LOC, owner_name: 'Somewhere',
    inherited: false, hidden: false, known_to: [],
    ...extra,
  }
}

const TRAITS = [
  trait(WITH_IMAGE, { navdot_image: CUTOUT, navdot_transparent: true }),
  trait(RATING_ONLY, { dice: ['d6', 'd8'] }),
  trait(STACKED, {}),   // no picture AND no position — the stack, always open
]

/** The navigate payload: the character's position and the chips' positions. */
function navigatePayload(self) {
  return {
    location: {
      name: 'Proximity Hall',
      zones: [],
      trait_positions: { [WITH_IMAGE]: HERB_AT, [RATING_ONLY]: RATING_AT },
    },
    parent: null, children: [], transversal: [],
    occupants: [{
      id: KAEL, type: 'character', name: 'Kael Drift',
      image: null, map_x: self.x, map_y: self.y,
    }],
  }
}

/** Load the app at a known self position, with every read mocked. */
async function open(page, self) {
  await page.route('**/api/v1/locations/*/navigate*', (route) =>
    route.fulfill({ json: navigatePayload(self) }))
  await page.route('**/api/v1/locations/*/traits*', (route) =>
    route.fulfill({ json: { location_id: LOC, viewer: null, traits: TRAITS } }))
  // No pool anywhere: the roller must be in its `adding` phase for a play to land.
  // `pools**` and not `pools*` — a single star does not cross a `/`, so `pools*` misses
  // the `PUT .../pools/{entity}` save and the run quietly writes to the real pool.
  await page.route('**/api/v1/locations/*/pools**', (route) => route.fulfill({ json: { pools: {} } }))

  await page.setViewportSize({ width: 1280, height: 950 })
  await page.goto('/')
  await page.evaluate(([pid, pname, eid, loc]) => {
    localStorage.setItem('playerId', pid)
    localStorage.setItem('playerName', pname)
    localStorage.setItem('entityId', eid)
    localStorage.setItem('currentLocationId', loc)
  }, [character.playerId, character.playerName, character.entityId, LOC])
  await page.goto('/')

  const chip = (id) => page.locator(`.scene-chip[data-trait-id="${id}"]`)
  await expect(chip(WITH_IMAGE)).toBeAttached()
  // The login overlay (`.name-entry`) sits above the map until the seeded session is
  // accepted, and a pointer test cannot hover through it. Firefox is slow enough to
  // still be showing it when the chips are already up.
  await expect(page.locator('.name-entry')).toHaveCount(0)
  return { chip }
}

test('resting, a chip is only its marker — and the stack stays open', async ({ page }) => {
  const { chip } = await open(page, FAR)

  // Nothing placed is open at this distance.
  await expect(page.locator('.scene-chip.expanded')).toHaveCount(0)

  // With a picture: no words at all, and the marker is the box.
  const withImage = chip(WITH_IMAGE)
  await expect(withImage.locator('.trait-chip-text')).toHaveCount(0)
  const img = await withImage.locator('img').boundingBox()
  const chipBox = await withImage.boundingBox()
  expect(img.height).toBeGreaterThan(20)            // a marker, not a sliver
  expect(chipBox.width).toBeLessThan(60)            // and no pill around it

  // Without one: the rating IS the marker, so the dice are there and the words are not.
  const ratingOnly = chip(RATING_ONLY)
  await expect(ratingOnly.locator('.trait-chip-text')).toHaveCount(0)
  await expect(ratingOnly.locator('.trait-chip-rating')).toBeVisible()
  await expect(page.locator(`.scene-chip[data-trait-id="${STACKED}"]`)).toHaveCount(0)

  // The stack has no position to approach, so it is the legend: always open.
  const stacked = page.locator('.loc-traits .trait-chip')
  await expect(stacked).toHaveCount(1)
  await expect(stacked.first()).toHaveClass(/expanded/)
})

test('proximity opens a chip and holds it open at rest', async ({ page }) => {
  const { chip } = await open(page, NEAR)

  await expect(chip(WITH_IMAGE)).toHaveClass(/expanded/)
  await expect(chip(RATING_ONLY)).toHaveClass(/expanded/)
  // …and it stays open with no drag running: the nav bubbles only expand mid-drag.
  await page.waitForTimeout(400)
  await expect(chip(WITH_IMAGE)).toHaveClass(/expanded/)
})

test('the pointer opens a chip, and leaving closes it', async ({ page }) => {
  const { chip } = await open(page, FAR)
  const target = chip(WITH_IMAGE)
  await expect(target).not.toHaveClass(/expanded/)

  await target.hover()
  await expect(target).toHaveClass(/expanded/)

  await page.mouse.move(5, 5)
  await expect(target).not.toHaveClass(/expanded/)
})

test('a tap opens a closed chip, and the next tap plays it', async ({ page }) => {
  const { chip } = await open(page, FAR)
  await page.mouse.move(5, 5)                       // no hover standing in for a tap
  const target = chip(WITH_IMAGE)
  const pool = page.locator('.dice-pool .die-chip')
  // The pool is the character's real one — the app moves to its own location once the
  // entity fetch lands, whatever `currentLocationId` was seeded with — so this counts
  // the DELTA rather than assuming an empty pool.
  const before = await pool.count()

  // `dispatchEvent` is a click with no pointer movement, i.e. the touch path.
  await target.dispatchEvent('click')
  await expect(target).toHaveClass(/expanded/)
  expect(await pool.count()).toBe(before)           // opening must not play

  // The second tap plays: a STATIC rating puts its die in the pool.
  await target.dispatchEvent('click')
  await expect.poll(() => pool.count()).toBe(before + 1)
})
