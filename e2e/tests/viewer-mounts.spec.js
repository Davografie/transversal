// The viewer mounts, in every layout, without throwing.
//
// This role has lost three bugs to the same blind spot: `vite build` compiles the
// SFC but never *executes* it, so every one of them reached the human first —
//
//   * 2026-09-13  a `d.tx.toFixed` render crash
//   * 2026-09-15  a `watchEffect` sampling the view centre during setup, reading a
//                 `const` declared ~100 lines later: ReferenceError on every mount
//   * 2026-09-23  the travel wipe sized to the viewport instead of the docked map
//
// — and the first two were `setup`-time failures, i.e. the component never
// rendered at all. This is the cheap net for that class: load the viewer in each
// real layout and fail on an uncaught error or a Vue warning. It asserts nothing
// about how the map looks; that is what the other specs are for.
//
// Deliberately NOT asserting on every console error: this suite drives a live
// backend, which logs its own network noise on release-build too (the dock spec
// makes the same distinction).

import { test, expect } from '@playwright/test'
import { gql } from '../helpers/sheet.js'
import { establishSession } from '../helpers/session.js'

// The two layouts that render the viewer: wide landscape docks the sheet beside a
// narrower map; a phone portrait stacks the bands and the viewer becomes a band
// rather than the whole screen (the case a fixed-position overlay broke on the
// vertical axis).
const DESKTOP = { width: 1280, height: 950 }
const PHONE_PORTRAIT = { width: 390, height: 844 }

// NEVER a real player character. Kael Drift is the project's testing character —
// the only CHARACTER an agent may act as — and it is a *main* of a dedicated test
// player. The owner is resolved by the RELATIONSHIP, not by name: the player has
// already been renamed once (`Tester` → `DSH MCP`) and a name lookup broke the dock
// suite the moment it happened.
const KAEL = 'character-kael-drift-e555ccde'

let character
test.beforeAll(async ({ request }) => {
  const { players } = await gql(request, `query { players { id name agency { entityId main } } }`)
  const owner = players.find((p) => (p.agency || []).some((a) => a.entityId === KAEL && a.main))
  if (!owner) throw new Error(`no player mains ${KAEL} — cannot reach the testing character`)
  character = { playerId: owner.id, playerName: owner.name, entityId: KAEL }
})

/** Collect everything that means "the component did not render cleanly". */
function watchForBreakage(page) {
  const problems = []
  page.on('pageerror', (e) => problems.push('uncaught: ' + String(e)))
  page.on('console', (m) => {
    if (m.type() === 'error' && /\[Vue warn\]/.test(m.text())) problems.push(m.text())
  })
  return problems
}

async function seedAndLoad(page, size) {
  await page.setViewportSize(size)
  await page.goto('/')
  await page.evaluate(([pid, pname, eid]) => {
    localStorage.setItem('playerId', pid)
    localStorage.setItem('playerName', pname)
    localStorage.setItem('entityId', eid)
  }, [character.playerId, character.playerName, character.entityId])
  await establishSession(page)
  await page.goto('/')
}

test('the viewer mounts cleanly in the docked landscape layout', async ({ page }) => {
  const problems = watchForBreakage(page)
  await seedAndLoad(page, DESKTOP)
  await expect(page.locator('.stage').first()).toHaveClass(/dock-sheet/)

  // It rendered — the scene layer and at least the self dot are on screen.
  await expect(page.locator('.location-viewer').first()).toBeVisible()
  await expect(page.locator('.scene-layer').first()).toBeAttached()
  await expect.poll(() => page.locator('.map-dot').count()).toBeGreaterThan(0)

  expect(problems).toEqual([])
})

test('the viewer mounts cleanly in the phone portrait stack', async ({ page }) => {
  const problems = watchForBreakage(page)
  await seedAndLoad(page, PHONE_PORTRAIT)
  await expect(page.locator('.stage').first()).toHaveClass(/mobile-stack/)

  await expect(page.locator('.location-viewer').first()).toBeVisible()
  await expect(page.locator('.scene-layer').first()).toBeAttached()
  await expect.poll(() => page.locator('.map-dot').count()).toBeGreaterThan(0)

  expect(problems).toEqual([])
})
