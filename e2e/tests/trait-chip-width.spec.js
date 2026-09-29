// A chip in the auto-stack is as wide as its OWN content — the width it has when it is
// placed in the scene.
//
// The stack is a column flex container, and a column flex container stretches its items
// across the cross axis by default. So every chip took the width of the WIDEST one in
// the stack, and on a phone that meant the container's `max-width: 40vw` — a two-word
// trait drawn as wide as the longest sentence in the room, filling the strip.
//
// Both REST reads are mocked, so the two chips compared here can be given IDENTICAL
// text: same name, same statement, same dice, one placed and one stacked. Nothing else
// pins that equality as directly.
//
// Checked at a phone viewport as well as a desktop one, because that is where the
// reported symptom was.

import { test, expect } from '@playwright/test'
import { gql } from '../helpers/sheet.js'
import { asArchitect, enterArrangeMode } from '../helpers/arrange.js'
import { establishSession } from '../helpers/session.js'

const KAEL = 'character-kael-drift-e555ccde'
const LOC = 'loc-chip-width-test'

/** The same trait twice — once placed, once left in the stack. */
function twin(id, extra) {
  return {
    id, trait_id: `trait-${id}`, name: 'spirit herb', statement: 'Corpse Lily',
    traitset_id: 'ts-1', sheet_tab: 'traits', rating_type: 'static', polarity: 'positive',
    sfx_ids: [], dice: ['d4'], capacity: [], owner_location_id: LOC, owner_name: 'Somewhere',
    inherited: false, hidden: false, known_to: [],
    navdot_image: null, navdot_transparent: false,
    ...extra,
  }
}

const PLACED = 'ts-twin-placed'
const STACKED = 'ts-twin-stacked'
const LONG = 'ts-long'

const TRAITS = [
  twin(PLACED, {}),
  twin(STACKED, {}),
  twin(LONG, { name: 'operations', statement: 'a town that exists to support a thing above it' }),
]

let character
test.beforeAll(async ({ request }) => {
  const { players } = await gql(request, `query { players { id name agency { entityId main } } }`)
  const owner = players.find((p) => (p.agency || []).some((a) => a.entityId === KAEL && a.main))
  if (!owner) throw new Error(`no player mains ${KAEL} — cannot reach the testing character`)
  character = { playerId: owner.id, playerName: owner.name, entityId: KAEL }
})

/** Load at `size` in arrange mode, where the unplaced stack and its chips are shown. */
async function open(page, size) {
  // The stack is arrange-mode only (the human, 2026-09-25), and arrange mode also opens
  // every placed chip — so this is where a stacked chip and a placed one are in the same
  // state and their widths can honestly be compared.
  await asArchitect(page)
  const at = { x: 70, y: 70 }
  await page.route('**/api/v1/locations/*/navigate*', (route) => route.fulfill({
    json: {
      location: { name: 'Width Hall', zones: [], trait_positions: { [PLACED]: at } },
      parent: null, children: [], transversal: [],
      occupants: [{ id: KAEL, type: 'character', name: 'Kael Drift', image: null, map_x: at.x, map_y: at.y }],
    },
  }))
  await page.route('**/api/v1/locations/*/traits*', (route) =>
    route.fulfill({ json: { location_id: LOC, viewer: null, traits: TRAITS } }))
  await page.route('**/api/v1/locations/*/pools**', (route) => route.fulfill({ json: { pools: {} } }))

  await page.setViewportSize(size)
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

  await expect(page.locator('.loc-traits .trait-chip')).toHaveCount(2)
  await expect(page.locator(`.scene-chip[data-trait-id="${PLACED}"]`)).toHaveClass(/expanded/)

  return page.evaluate(() => {
    const width = (sel) => document.querySelector(sel).getBoundingClientRect().width
    return {
      container: width('.loc-traits'),
      placed: width(`.scene-chip[data-trait-id="${'ts-twin-placed'}"]`),
      stacked: width(`.loc-traits .trait-chip[data-trait-id="${'ts-twin-stacked'}"]`),
      long: width(`.loc-traits .trait-chip[data-trait-id="${'ts-long'}"]`),
    }
  })
}

for (const [label, size] of Object.entries({
  'desktop': { width: 1280, height: 950 },
  'phone': { width: 390, height: 844 },
})) {
  test(`a stacked chip is as wide as the same chip placed — ${label}`, async ({ page }) => {
    const w = await open(page, size)

    // The point: identical content, identical width, wherever it is drawn.
    expect(Math.abs(w.stacked - w.placed)).toBeLessThan(1)

    // …and each chip sizes to itself, rather than every one taking the widest in the
    // stack (which is also what the container's max-width used to force on a phone).
    expect(w.long).toBeGreaterThan(w.stacked + 20)
    expect(w.stacked).toBeLessThan(w.container)
    expect(w.stacked).toBeLessThan(size.width * 0.5)
  })
}
