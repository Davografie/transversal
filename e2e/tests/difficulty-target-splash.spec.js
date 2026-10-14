// The difficulty a player is dealt arrives as a splash they can act on: the
// number, the dice it was rolled from, and a tap that brings up their sheet
// ([[B229]]'s splash, third face — a *target*, not a report).
//
// Two things shape how it is driven:
//
//   * The splash is the **receiving player's** — the GM who set the target
//     already watched it happen, and an architect has no sheet of their own to
//     focus. So the role read is *pinned* to `player` with `architectMode` seeded
//     false; the two agreeing is what keeps the app's `watch(gmMode)` from
//     PATCHing a role back to the server. Pinned rather than taken as given: the
//     `DSH MCP` test player has been an architect and has been a player, and which
//     one it is that week is not this spec's subject.
//   * The event is delivered by **fulfilling the app's own SSE stream**, not by
//     setting a difficulty for real. `difficulty_set` only reaches *started*
//     sessions, so the live route would mean starting and ending a session on the
//     human's table — and setting a difficulty that nothing but a beat can clear.
//     The server's half (the payload the splash reads) is pinned in
//     `tests/test_scene_state.py`; these specs pin what the client does with it.
//
// The stream is answered only once the app knows its own location, because that
// is what the splash is filtered on — the same ordering the real event has, where
// the player is already somewhere when the GM sets a target.
//
// Only Kael Drift is driven (AGENTS.md).

import { test, expect } from '@playwright/test'
import { establishSession } from '../helpers/session.js'

const KAEL = 'character-kael-drift-e555ccde'

// A phone: the bands are where "focus" is a real, observable thing (the stage
// carries `focus-<band>`), and it is how the human drives this app. On a wide
// screen the sheet is simply on screen — there is nothing to reveal — so the
// focus would be invisible to a test either way.
test.use({ viewport: { width: 390, height: 844 } })

const dice = [
  { die: 'd8', label: 'Sword', source_id: 'ts-sword', source_kind: 'trait', result: 6 },
  { die: 'd6', label: '2d6', source_id: 'difficulty', source_kind: 'difficulty', result: 3 },
]
const streamFor = (difficulty, at) => `event: difficulty_set\ndata: ${JSON.stringify({
  difficulty, location_id: at, dice,
})}\n\n`

let character
test.beforeAll(async ({ request }) => {
  const res = await request.post('/api/v1/graphql', {
    data: { query: '{ players { id name agency { entityId main } } }' },
  })
  const { players } = (await res.json()).data
  const owner = players.find((p) => (p.agency || []).some((a) => a.entityId === KAEL && a.main))
  if (!owner) throw new Error(`no player mains ${KAEL} — cannot reach the testing character`)
  character = { playerId: owner.id, playerName: owner.name, entityId: KAEL }
})

/**
 * Load the app as the player, and answer its SSE stream with `bodyFor(location)`
 * once the app has settled on a location. Returns that location.
 */
async function openAsPlayer(page, bodyFor) {
  // Player mode, without writing to the server's view of the player.
  await page.route('**/api/v1/players/*', async (route) => {
    const body = await (await route.fetch()).json()
    return route.fulfill({ json: { ...body, role: 'player' } })
  })

  // One answered connection; a later reconnect is held open rather than answered,
  // so a repeat of the event cannot re-raise a splash already dismissed.
  let body = null
  let release
  const ready = new Promise((r) => { release = r })
  let served = 0
  await page.route('**/api/v1/stream*', async (route) => {
    if (served++) { await new Promise(() => {}) ; return }
    await ready
    await route.fulfill({
      status: 200,
      contentType: 'text/event-stream',
      headers: { 'cache-control': 'no-cache' },
      body,
    })
  })

  // Which location the app is at: it names it in the pool it reads for itself.
  const locations = []
  page.on('request', (r) => {
    const m = r.url().match(/\/api\/v1\/locations\/([^/]+)\/pools\//)
    if (r.method() === 'GET' && m) locations.push(m[1])
  })

  await page.goto('/')
  await page.evaluate((ids) => {
    localStorage.setItem('playerId', ids.playerId)
    localStorage.setItem('playerName', ids.playerName)
    localStorage.setItem('entityId', ids.entityId)
    localStorage.setItem('architectMode', 'false')   // agrees with the mock above
  }, character)
  await establishSession(page)
  await page.goto('/')

  // The app settles on its current location a moment after loading, so the last
  // pool it reads is the one to address (it reads an earlier one on the way).
  await expect.poll(() => locations.length, { timeout: 30_000 }).toBeGreaterThan(0)
  await page.waitForTimeout(1500)
  const location = locations[locations.length - 1]

  body = bodyFor(location)
  release()
  return location
}

test('a difficulty dealt to the player splashes its dice, and the tap opens the sheet', async ({ page }) => {
  test.setTimeout(150_000)
  await openAsPlayer(page, (location) => streamFor(9, location))

  const splash = page.locator('.sp-note-action')
  await splash.waitFor({ state: 'visible', timeout: 30_000 })

  // The number as the loudest thing on the surface, and behind it the traits and the
  // dice it was rolled from, as the map's own trait chips.
  await expect(splash.locator('.sp-target-label')).toHaveText('Difficulty')
  await expect(splash.locator('.sp-target-value')).toHaveText('9')

  // One chip per trait instance, each carrying the face its die actually rolled.
  const chips = splash.locator('.sp-chip')
  await expect(chips).toHaveCount(dice.length)
  for (const [i, d] of dice.entries()) {
    const chip = chips.nth(i)
    await expect(chip.locator('.trait-chip-name'), `the ${d.die}'s trait`).toHaveText(d.label)
    // The rolled face, not the die's type: DieIcon prints the result when it has one.
    await expect(chip.locator('.die-icon'), `the ${d.die} ${d.result} face`)
      .toHaveAttribute('class', new RegExp(`die-${d.die}`))
    await expect(chip.locator('.die-text')).toHaveText(String(d.result))
  }
  await expect(splash.locator('.sp-note-cue')).toHaveText('Open character sheet')

  // A target waits for its tap: it is still there long past a note's dwell.
  await page.waitForTimeout(2600)
  await expect(splash).toBeVisible()

  // ── the tap ──
  // The bands, where focusing is a state the stage wears: the player is on the
  // map, and the tap is what brings the sheet's band forward.
  const stage = page.locator('.stage')
  await expect(stage).toHaveClass(/focus-location/)
  await splash.click()
  await expect(page.locator('.sp-note-action'), 'the target has been read').toHaveCount(0)
  await expect(stage, 'the tap focuses the sheet').toHaveClass(/focus-sheet/, { timeout: 10_000 })
})

test('a difficulty set somewhere else does not take this player\'s surface', async ({ page }) => {
  test.setTimeout(150_000)
  const seen = []
  page.on('console', (m) => { if (m.text().includes('difficulty_set')) seen.push(m.text()) })

  await openAsPlayer(page, () => streamFor(9, 'loc-somewhere-else'))

  // The event really arrived — otherwise "no splash" would pass for the wrong
  // reason, which is the usual way a negative assertion lies.
  await expect.poll(() => seen.length, { timeout: 15_000 }).toBeGreaterThan(0)
  await expect(page.locator('.sp-note-action')).toHaveCount(0)
})
