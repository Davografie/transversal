// The travel wipe must fill the MAP, not the viewport.
//
// The docked layout (B169) offsets the map: `.stage.dock-sheet .location-viewer
// { left: var(--dock-w) }`, with `--dock-w` = 400px. The viewer is therefore
// narrower than the viewport and does not start at its left edge, and the
// ResizeObserver measures exactly that box — so every percentage the viewer
// produces (`toViewportPos`, and the destination scene box sized from `cw`/`ch`)
// is a percentage **of the docked map**.
//
// TravelOverlay used to be `position: fixed; inset: 0`, which spans the whole
// viewport and resolves those percentages against the wrong box. Measured before
// the fix: the wipe's frame was the full 1280px viewport starting at x=0 while the
// map was 880px wide starting at x=400 — one dock width out, so the portal opened
// beside the dot that was clicked and the destination scene was parked at the
// viewport's left edge.
//
// The fix makes the overlay fill its positioned parent (the viewer) instead:
// `absolute`, not `fixed`. `.location-viewer` is positioned in every layout
// (`fixed` by default, `absolute` in the mobile stack, `fixed` + `left` when
// docked) and the overlay is its direct child, so the wipe is the map's box in all
// of them — which also makes the portal origin, a percentage of that same box,
// land on the dot by construction.
//
// WHY THIS ASSERTS LAYOUT AND NOT `getBoundingClientRect()`: the map is a moving
// frame during travel (the camera's zoom/pan eases, and the row is animating), so
// two rects read in two round-trips are two different moments — measuring the
// overlay and the viewer that way produced a phantom 234px error while
// `offsetTop`/`offsetParent` showed the layout was already correct. `offsetTop`
// and `offsetParent` are pure layout: no transforms, no animation, no timing.

import { test, expect } from '@playwright/test'
import { gql } from '../helpers/sheet.js'

const DESKTOP = { width: 1280, height: 950 }
const DOCK_W = 400          // --dock-w: the width the docked sheet occupies

// NEVER a real player character. Kael Drift is the project's testing character —
// the only CHARACTER an agent may act as — and it is a *main* of a dedicated test
// player. The owner is resolved by the RELATIONSHIP, not by name: the player has
// already been renamed once and a name lookup broke the dock suite when it was.
const KAEL = 'character-kael-drift-e555ccde'

let character
test.beforeAll(async ({ request }) => {
  const { players } = await gql(request, `query { players { id name agency { entityId main } } }`)
  const owner = players.find((p) => (p.agency || []).some((a) => a.entityId === KAEL && a.main))
  if (!owner) throw new Error(`no player mains ${KAEL} — cannot reach the testing character`)
  character = { playerId: owner.id, playerName: owner.name, entityId: KAEL }
})

async function seedAndLoad(page, size) {
  await page.setViewportSize(size)
  await page.goto('/')
  await page.evaluate(([pid, pname, eid]) => {
    localStorage.setItem('playerId', pid)
    localStorage.setItem('playerName', pname)
    localStorage.setItem('entityId', eid)
  }, [character.playerId, character.playerName, character.entityId])
  await page.goto('/')
}

test('the travel wipe fills the docked map, not the viewport', async ({ page }) => {
  const problems = []
  page.on('pageerror', (e) => problems.push('uncaught: ' + String(e)))

  await seedAndLoad(page, DESKTOP)

  await expect(page.locator('.stage').first()).toHaveClass(/dock-sheet/)

  // The dock really is shifting the map — otherwise this test proves nothing.
  const mapLeft = await page.locator('.location-viewer').first()
    .evaluate((el) => el.getBoundingClientRect().left)
  expect(mapLeft).toBeGreaterThan(DOCK_W * 0.5)

  // Expand a nav dot, then click its overlay to travel. `force: true`: the dots
  // are continuously animated (proximity expansion, the armed breathe), so
  // Playwright's actionability "stable" check never settles and the click would
  // retry until the test times out. Dot click reliability is not what is under
  // test — the travel origin is implied by the wipe filling the map's own box.
  const nav = page.locator('.nav-dot').first()
  await expect(nav).toBeVisible()
  await nav.click({ force: true })                                              // pop the bubble
  await nav.locator('.dot-overlay, .dot-label').first().click({ force: true })  // travel

  const overlay = page.locator('.travel-overlay').first()
  await expect(overlay).toBeVisible()

  const geom = await overlay.evaluate((el) => {
    const parent = el.offsetParent
    return {
      // `offsetParent` is null for a `position: fixed` element — so this alone
      // catches the regression: fixed ⇒ null, absolute-in-the-map ⇒ the viewer.
      parentIsMap: !!parent && parent.classList.contains('location-viewer'),
      offsetTop: el.offsetTop,
      offsetLeft: el.offsetLeft,
      width: el.offsetWidth,
      height: el.offsetHeight,
      mapW: parent ? parent.clientWidth : null,
      mapH: parent ? parent.clientHeight : null,
    }
  })

  expect(geom.parentIsMap).toBe(true)
  expect(geom.offsetTop).toBe(0)
  expect(geom.offsetLeft).toBe(0)
  expect(geom.width).toBe(geom.mapW)     // the wipe is exactly the map's width
  expect(geom.height).toBe(geom.mapH)    // …and height, not the viewport's

  expect(problems).toEqual([])
})
