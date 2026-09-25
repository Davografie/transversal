// A chip's rating sits BESIDE its text, not on top of it (`B92`).
//
// The dice hang off the chip's right edge and grow leftwards as dice are added, while
// the chip reserved a fixed 22px lane for them — one die's width. So a two-die rating
// printed 5px inside its own name, three dice 14px, and a four-die mixed rating 92px:
// the rating appeared to start at the right edge and march inwards over the text.
//
// The lane is the rating's own width now, so this checks the clearance holds for one
// die, for a deep fan of one type, and for several types at once — and that the last
// die still straddles the border, which is the look the chip is supposed to have.
//
// The traits are mocked, so the dice counts are exact.

import { test, expect } from '@playwright/test'
import { gql } from '../helpers/sheet.js'

const KAEL = 'character-kael-drift-e555ccde'
const LOC = 'loc-rating-lane'

function trait(id, name, dice) {
  return {
    id, trait_id: `trait-${id}`, name, statement: 'a statement on the row below',
    traitset_id: 'ts-1', sheet_tab: 'traits', rating_type: 'static', polarity: 'positive',
    sfx_ids: [], dice, capacity: [], owner_location_id: LOC, owner_name: 'Somewhere',
    inherited: false, hidden: false, known_to: [],
    navdot_image: null, navdot_transparent: false,
  }
}

const TRAITS = [
  trait('one', 'one die', ['d6']),
  trait('two', 'two dice', ['d6', 'd6']),
  trait('three', 'three dice', ['d6', 'd6', 'd6']),
  trait('mixed', 'mixed dice', ['d6', 'd8', 'd6']),
  trait('wide', 'four mixed', ['d4', 'd6', 'd8', 'd10']),
]

let character
test.beforeAll(async ({ request }) => {
  const { players } = await gql(request, `query { players { id name agency { entityId main } } }`)
  const owner = players.find((p) => (p.agency || []).some((a) => a.entityId === KAEL && a.main))
  if (!owner) throw new Error(`no player mains ${KAEL} — cannot reach the testing character`)
  character = { playerId: owner.id, playerName: owner.name, entityId: KAEL }
})

test('every rating keeps clear of the text, however many dice it has', async ({ page }) => {
  await page.route('**/api/v1/locations/*/navigate*', (route) => route.fulfill({
    json: {
      location: { name: 'Lane Hall', zones: [], trait_positions: {} },
      parent: null, children: [], transversal: [],
      occupants: [{ id: KAEL, type: 'character', name: 'Kael Drift', image: null, map_x: 95, map_y: 95 }],
    },
  }))
  await page.route('**/api/v1/locations/*/traits*', (route) =>
    route.fulfill({ json: { location_id: LOC, viewer: null, traits: TRAITS } }))
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

  const chips = page.locator('.loc-traits .trait-chip')
  await expect(chips).toHaveCount(TRAITS.length)
  await expect(page.locator('.name-entry')).toHaveCount(0)

  const measured = await page.evaluate(() => [...document.querySelectorAll('.loc-traits .trait-chip')].map((chip) => {
    const box = chip.getBoundingClientRect()
    const text = chip.querySelector('.trait-chip-text').getBoundingClientRect()
    const rating = chip.querySelector('.trait-chip-rating').getBoundingClientRect()
    return {
      name: chip.querySelector('.trait-chip-text').innerText.split('\n')[0],
      clearance: +(rating.left - text.right).toFixed(1),
      overhang: +(rating.right - box.right).toFixed(1),
    }
  }))

  for (const m of measured) {
    // Beside the text, with air between — never over it. Before the fix the deeper
    // ratings were negative here by up to 92px.
    expect(m.clearance, `${m.name} clears its text`).toBeGreaterThanOrEqual(4)
    // …and still hanging over the border, which is what hides that piece of it.
    expect(m.overhang, `${m.name} overhangs the border`).toBeGreaterThan(0)
  }
  console.log(JSON.stringify(measured, null, 1))
})
