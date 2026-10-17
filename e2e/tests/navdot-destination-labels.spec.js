// Arrange mode captions each travel dot with its DESTINATION name (human, 2026-10-17).
//
// The dots have carried `:label` and `:title` all along, but `MapDot`'s label branch is a
// `v-else-if` *behind* the picture — and in arrange mode every zone/nav dot is a bubble
// **filled** by its destination preview. So the name could render only when there was no
// picture, i.e. never exactly when the GM was dragging unnamed destinations around.
//
// Every dot here HAS a preview image on purpose. A fixture of imageless dots would pass
// against the unfixed build, because that path already drew the label.
//
// The plate also has to fit INSIDE the circle: the dot keeps `overflow: hidden` +
// `border-radius: 50%` because that clip *is* the hole illusion, so a caption that
// overhangs the rim is sliced by it. That is geometry, so it is asserted rather than
// eyeballed.

import { test, expect } from '@playwright/test'
import { gql } from '../helpers/sheet.js'
import { asArchitect, enterArrangeMode } from '../helpers/arrange.js'
import { establishSession } from '../helpers/session.js'

// NEVER a real player character — Kael Drift is the project's testing character, a main
// of a dedicated test player. The owner is resolved by the RELATIONSHIP, not by name: the
// player has already been renamed once and a name lookup broke a suite when it happened.
const KAEL = 'character-kael-drift-e555ccde'
const LOC = 'loc-navdot-label-test'
const PARENT = 'loc-navdot-label-parent'
const PORTAL = 'loc-navdot-label-portal'
const CHILD = 'loc-navdot-label-child'

let character
test.beforeAll(async ({ request }) => {
  const { players } = await gql(request, `query { players { id name agency { entityId main } } }`)
  const owner = players.find((p) => (p.agency || []).some((a) => a.entityId === KAEL && a.main))
  if (!owner) throw new Error(`no player mains ${KAEL} — cannot reach the testing character`)
  character = { playerId: owner.id, playerName: owner.name, entityId: KAEL }
})

const svg = (fill) =>
  `data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='80' height='80'%3E%3Crect width='80' height='80' fill='%23${fill}'/%3E%3C/svg%3E`

const PARENT_NAME = 'Willow Reach'
const PORTAL_NAME = 'Eindhoven Airport'
const CHILD_NAME = 'Willow Bath'

const SELF = { x: 50, y: 50 }

// Dots are kept well apart: in arrange mode each is a 240px bubble, and a pile of them
// overlap so heavily that the lower one cannot be measured at all.
function navigatePayload() {
  return {
    location: {
      name: 'Label Hall',
      zones: [{ x: 70, y: 24, location_id: CHILD }],
      trait_positions: {},
      nav_positions: { parent: { x: 26, y: 26 }, portal: { x: 74, y: 76 } },
    },
    parent: {
      _key: PARENT, name: PARENT_NAME,
      navdot_image: svg('aa6633'), background_image: null,
      current_universe: 'three_realms',
    },
    // A zone's label is DERIVED from its linked child, never stored — so the child has
    // to be in the payload for `childForZone` to resolve it.
    children: [{ _key: CHILD, name: CHILD_NAME, navdot_image: svg('33aa66'), background_image: null }],
    transversal: [{
      _key: PORTAL, name: PORTAL_NAME,
      navdot_image: svg('3366aa'), background_image: null,
      transversal_type: 'consciousness', current_universe: 'earth',
    }],
    occupants: [{ id: KAEL, type: 'character', name: 'Kael Drift', image: null, map_x: SELF.x, map_y: SELF.y }],
  }
}

async function open(page, { arrange = false } = {}) {
  // Before `goto`: the role is fetched on mount. `asArchitect` also swallows the
  // role write-back, which would otherwise leave the testing player stored as architect.
  if (arrange) await asArchitect(page)
  await page.route('**/api/v1/locations/*/navigate*', (route) => route.fulfill({ json: navigatePayload() }))
  await page.route('**/api/v1/locations/*/traits*', (route) =>
    route.fulfill({ json: { location_id: LOC, viewer: null, traits: [] } }))
  await page.route('**/api/v1/locations/*/pools**', (route) => route.fulfill({ json: { pools: {} } }))

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

  await expect(page.locator('.nav-dot').first()).toBeAttached()
  // The login overlay sits above the map until the seeded session is accepted, and
  // firefox is slow enough to still be showing it when the dots are already up.
  await expect(page.locator('.name-entry')).toHaveCount(0)
  if (arrange) await enterArrangeMode(page)

  return {
    parent: page.locator('.nav-dot.nav-parent'),
    portal: page.locator('.nav-dot.nav-portal'),
    zone: page.locator('.zone-dot'),
  }
}

test('arrange mode captions every travel dot with its destination', async ({ page }) => {
  const { parent, portal, zone } = await open(page, { arrange: true })

  // The caption is ADDED to the preview, never swapped for it: each dot still shows the
  // picture that made the name unreadable in the first place.
  await expect(parent.locator('img.dot-overlay')).toBeVisible()
  await expect(portal.locator('img.dot-overlay')).toBeVisible()
  await expect(zone.locator('img.dot-overlay')).toBeVisible()

  await expect(parent.locator('.dot-caption')).toHaveText(PARENT_NAME)
  await expect(portal.locator('.dot-caption')).toHaveText(`${PORTAL_NAME} · consciousness`)
  await expect(zone.locator('.dot-caption')).toHaveText(CHILD_NAME)
})

test('outside arrange mode there is no caption — the dot is its preview', async ({ page }) => {
  const { parent, portal, zone } = await open(page)

  await expect(parent).toBeAttached()
  await expect(portal).toBeAttached()
  await expect(zone).toBeAttached()
  await expect(page.locator('.dot-caption')).toHaveCount(0)
})

test('the plate fits inside the circle, and never swallows the dot', async ({ page }) => {
  const { parent } = await open(page, { arrange: true })
  const caption = parent.locator('.dot-caption')
  await expect(caption).toBeVisible()
  // The bubble reaches 240px through a 250ms width transition, and the caption has no
  // such transition — so measuring straight after the click catches a 16px dot and
  // reads a plate that overhangs it. Wait for the size the geometry is about.
  await expect(parent).toHaveCSS('width', '240px')

  // The plate's bottom corners must land inside the bubble's inscribed circle — the clip
  // that makes the hole illusion is also what would slice an overhanging caption. Check
  // the corners rather than trusting the two percentages.
  const dotBox = await parent.boundingBox()
  const capBox = await caption.boundingBox()
  const r = dotBox.width / 2
  const cx = dotBox.x + r
  const cy = dotBox.y + r
  for (const [px, py] of [
    [capBox.x, capBox.y + capBox.height],
    [capBox.x + capBox.width, capBox.y + capBox.height],
  ]) {
    expect(Math.hypot(px - cx, py - cy)).toBeLessThanOrEqual(r)
  }

  // …and the plate must not intercept a click. Every click on this dot reaches either the
  // overlay image (which stops it) or the dot itself; a plate with pointer events would
  // silently take that over for the strip it covers.
  await expect(caption).toHaveCSS('pointer-events', 'none')
})
