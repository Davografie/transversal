// Inner locations: a place an **entity** carries (an inner world).
//
// The human's design, 2026-10-16: *"don't render inner locations as nested under
// characters, but put them in the entity edit panel. Then open them as child
// panels."* Plus: create one there, and no unlink yet.
//
// `check-inner-locations.mjs` drives the tree filter for real and reads the panel
// wiring; what only a browser can show is that a carrier stops being drawn as a
// place, that the section lists and makes one, and that a row really opens a
// child panel.
//
// The first test is **read-only against live data** (the one live carrier is a
// player character, so it is read and never written). The second creates its own
// carrier — a GMC, which is fair game — and tears everything down again.
import { test, expect } from '@playwright/test'
import { gql } from '../helpers/sheet.js'
import { bootGmPanel, enterPrep } from '../helpers/gm.js'

const TEST_CHARACTER = 'character-kael-drift-e555ccde'
// The only live carrier: Phaos Tyish (a CHARACTER) holds "Phaos Tyish Qihai"
// (an earth location). Read-only, per backend-platform's note on B308.
const LIVE_CARRIER = 'character-20809'
const LIVE_CARRIED = { id: 'loc-345978606', name: 'Phaos Tyish Qihai' }

const CARRIER_NAME = 'E2E Inner Carrier'
const INNER_NAME = 'E2E Inner World'
const SECTION = '.inner-locations'

let character
test.beforeAll(async ({ request }) => {
  const { players } = await gql(request, `query { players { id name agency { entityId main } } }`)
  const owner = players.find((p) => (p.agency || []).some((a) => a.entityId === TEST_CHARACTER && a.main))
  if (!owner) throw new Error(`no player mains ${TEST_CHARACTER} — cannot reach the testing character`)
  character = { playerId: owner.id, playerName: owner.name, entityId: TEST_CHARACTER }
})

/** Delete anything this spec made, whatever happened. */
test.afterEach(async ({ request }) => {
  const { entities } = await gql(request, `query { entities(type: LOCATION) { id name } }`)
  for (const e of entities.filter((x) => x.name === INNER_NAME)) {
    await gql(request, `mutation($id: ID!){ deleteEntity(id: $id, rmtree: false) }`, { id: e.id })
  }
  const { entities: all } = await gql(request, `query { entities { id name type } }`)
  for (const e of all.filter((x) => x.name === CARRIER_NAME)) {
    await gql(request, `mutation($id: ID!){ deleteEntity(id: $id, rmtree: false) }`, { id: e.id })
  }
})

/** Open an entity's panel from the GM panel's focus filter. */
async function openEntity(page, name) {
  await page.locator('.filter-input:visible').first().fill(name)
  await page.waitForTimeout(900)
  await page.locator('.suggestion-row:visible').first().click()
  await page.waitForTimeout(1600)
}

test('a carried location is not drawn as a place in the tree', async ({ page, request }) => {
  // Guard against a vacuous pass: live data must still contain a carrier, or this
  // asserts nothing. If the fixture ever goes away the test says so.
  const { entity } = await gql(request,
    `query($id: ID!){ entity(id: $id){ carriedLocations { id name } } }`, { id: LIVE_CARRIER })
  expect(entity.carriedLocations.map((l) => l.name), 'the live carrier still carries a place')
    .toContain(LIVE_CARRIED.name)

  await bootGmPanel(page, character)
  await enterPrep(page)

  // A carrier used to render as `node_type: 'location'` — a place sitting at the
  // top level beside the universes, named after the character.
  await expect(page.locator('.tree-row.location', { hasText: 'Phaos Tyish' }),
    'no carrier is drawn as a place').toHaveCount(0)

  // And it is not reachable through the filter either, which is the stronger
  // check: filtering expands the path to a match, so a carried location still in
  // the tree would be revealed here rather than staying collapsed.
  await page.locator('.filter-input:visible').first().fill(LIVE_CARRIED.name)
  await page.waitForTimeout(1200)
  await expect(page.locator('.tree-row', { hasText: LIVE_CARRIED.name }),
    'and the place it carries is not in the tree at all').toHaveCount(0)
})

test('the entity panel lists an inner location, creates one, and opens it', async ({ page, request }) => {
  // A carrier of our own: a GMC, so nothing of a player's is touched.
  const made = await gql(request,
    `mutation($input: CreateEntityInput!){ createEntity(input: $input){ id name } }`,
    { input: { name: CARRIER_NAME, type: 'GMC', universe: 'earth' } })
  const carrierId = made.createEntity.id
  expect(carrierId, 'the throwaway carrier exists').toBeTruthy()

  await bootGmPanel(page, character)
  await enterPrep(page)
  await openEntity(page, CARRIER_NAME)

  const section = page.locator(SECTION)
  await expect(section, 'the panel has an Inner locations section').toHaveCount(1)
  await expect(section, 'and it says there are none yet').toContainText('None yet')

  // Create one — the parent is an edge to this GMC, which is not a place.
  await section.locator('input').first().fill(INNER_NAME)
  await section.locator('button', { hasText: 'Add' }).first().click()
  await page.waitForTimeout(2200)
  await expect(section.locator('.member-row'), 'the new inner location is listed').toHaveCount(1)
  await expect(section.locator('.member-row')).toContainText(INNER_NAME)

  // It is real, and it is parented to the carrier.
  const { entity } = await gql(request,
    `query($id: ID!){ entity(id: $id){ carriedLocations { id name } } }`, { id: carrierId })
  expect(entity.carriedLocations.map((l) => l.name), 'and the edge was written').toEqual([INNER_NAME])

  // A row opens it as a **child panel** — depth 2, under the carrier's panel.
  await section.locator('.member-row').first().click()
  await page.waitForTimeout(1600)
  const child = page.locator('.panel-node[data-panel-depth="2"]:visible')
  await expect(child, 'clicking the row opened a child panel').toHaveCount(1)
  await expect(child, 'and it is the place that was opened').toContainText(INNER_NAME)
  // Which is the "held by" half: the place itself says who carries it, since
  // nothing in the tree will explain why it is not there.
  await expect(child, 'and it says who holds it').toContainText('Held by')
})
