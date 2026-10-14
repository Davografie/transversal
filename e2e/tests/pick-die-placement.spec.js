// During picking, a die is in exactly one of three states: **unassigned, a result,
// or an effect**. Dragging the same die out of the pool a second time used to leave
// it in two slots at once — and because the total is summed from the result slots,
// that die was counted twice, so the number on screen was not the number the table
// would resolve.
//
// The fault is in the drop, not the gesture: a drag that starts on a *pool* tile
// carries no source slot, so the placement never lifted the die out of the slot it
// already occupied. Dragging from a slot was always correct, which is why this only
// shows when the same pool die is dragged twice.
//
// Measured against the unfixed tree, the first slot stayed filled and the shown
// total doubled the die; that is what the assertions below catch.
//
// Kael Drift is the testing character (AGENTS.md § Player characters & the testing
// character), mained by the `DSH MCP` test player. The pick being tested is the
// player's **own** — which is how the bug was reported — so the role read is pinned
// to `player` with `architectMode` seeded false, rather than left to whatever role
// the test identity happens to carry that week. (It *was* an architect, and the
// roller then picks in the location's pool; the identity was demoted, and this spec
// broke on the integration branch for a reason that had nothing to do with dice.)
// The pool is discovered from the roller's own request and left as it was found.

import { test, expect } from '@playwright/test'
import { establishSession } from '../helpers/session.js'

const KAEL = 'character-kael-drift-e555ccde'

// The roller needs vertical room: in a short viewport the sheet and the dice band
// keep re-settling against each other, and the band is not reliably clickable.
test.use({ viewport: { width: 1400, height: 1000 } })

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

test('a die dragged from the pool twice fills one slot, not two', async ({ page, request }) => {
  test.setTimeout(150_000)

  // Player mode, pinned — and without writing to the server's view of the player.
  await page.route('**/api/v1/players/*', async (route) => {
    const body = await (await route.fetch()).json()
    return route.fulfill({ json: { ...body, role: 'player' } })
  })

  // The pools the roller reads: its own entity's, at the location it settles on.
  const poolReads = []
  page.on('request', (r) => {
    const m = r.url().match(/\/api\/v1\/locations\/([^/]+)\/pools\/([^/?]+)$/)
    if (r.method() === 'GET' && m) poolReads.push({ loc: m[1], entity: m[2] })
  })

  await page.goto('/')
  await page.evaluate((ids) => {
    localStorage.setItem('playerId', ids.playerId)
    localStorage.setItem('playerName', ids.playerName)
    localStorage.setItem('entityId', ids.entityId)
    localStorage.setItem('architectMode', 'false')   // agrees with the mock above
  }, character)
  await establishSession(page)

  const openRoller = async () => {
    await page.locator('button.map-dot.self').first().waitFor({ state: 'visible', timeout: 30_000 })
    await page.locator('button.map-dot.self').first().click()
    await page.locator('.sheet-embedded').first().waitFor({ state: 'visible', timeout: 30_000 })
    // The roller reveals on hover; its controls sit below the fold until it does.
    await page.locator('.dice-panel-wrapper').first().hover()
  }

  await page.goto('/')
  await openRoller()
  await expect(page.locator('.dice-roller')).toBeVisible({ timeout: 30_000 })
  await expect.poll(() => poolReads.length, { timeout: 30_000 }).toBeGreaterThan(0)
  const poolUrl = `/api/v1/locations/${poolReads[poolReads.length - 1].loc}/pools/${KAEL}`

  // The scene's pool is not this test's to keep.
  const before = await (await request.get(poolUrl)).json()

  try {
    // Unload first: a running roller re-saves its own pool, which would clobber the
    // seed. With the app gone the pool can be set up peacefully.
    await page.goto('about:blank')

    // A Cortex test needs three dice (keep two, plus an effect die). Seeding them is
    // deliberate: how the dice reached the pool is not what this pins, and the manual
    // die picker would also mark the pool as a difficulty roll. Rolling through the
    // API rather than the Roll button keeps the assertion off the panel's animation.
    const seeded = await request.put(poolUrl, {
      data: { dice: [{ die: 'd6' }, { die: 'd8' }, { die: 'd10' }] },
    })
    expect(seeded.ok(), 'the pool must accept three dice').toBeTruthy()
    const rolled = await request.post(`${poolUrl}/cortex-roll`)
    expect(rolled.ok(), 'the pool must roll').toBeTruthy()
    await expect
      .poll(async () => {
        const p = await (await request.get(poolUrl)).json()
        return p.dice?.length === 3 && p.dice.every((d) => d.result != null)
      }, { timeout: 15_000 })
      .toBe(true)

    // A fresh load restores the rolled pool straight into picking — the three dice
    // this test seeded. (Asserted on the dice rather than on a pool *read*: the
    // roller can also be seeded from the roll's own SSE broadcast, so which of the
    // two brings it back is not this spec's business.)
    poolReads.length = 0
    await page.goto('/')
    await openRoller()
    await page.locator('.roll-pick').waitFor({ state: 'visible', timeout: 30_000 })
    await expect(page.locator('.roll-pick .roll-die-wrap'), 'the seeded pool is the one restored').toHaveCount(3)

    // Hitches cannot be picked, so drag one that can be.
    const dice = page.locator('.roll-pick .roll-die-wrap[draggable="true"]')
    expect(await dice.count(), 'a non-hitch die to drag (a botch leaves none)').toBeGreaterThan(0)
    const die = dice.first()

    const slots = page.locator('.sel-slot')
    expect(await slots.count(), 'a Cortex test offers more than one slot').toBeGreaterThan(1)
    const first = slots.nth(0)
    const second = slots.nth(1)
    await expect(first, 'the slots start empty').toHaveClass(/empty/)

    // One die, dragged from the pool into a slot …
    await die.dragTo(first)
    await expect(first, 'the die lands where it was dragged').not.toHaveClass(/empty/)
    const kept = (await first.innerText()).trim()

    // … then dragged from the pool again, which must *move* it rather than copy it.
    await die.dragTo(second)

    await expect(second, 'the second slot takes the die').not.toHaveClass(/empty/)
    await expect(first, 'a die is a result or an effect, never both').toHaveClass(/empty/)

    // The symptom that reaches the table: the same die in two result slots is
    // counted twice, so the total shown is not the total that resolves.
    if (await second.evaluate((el) => el.classList.contains('total-slot'))) {
      await expect(page.locator('.sel-value .result-num')).toHaveText(kept)
    }
  } finally {
    // Put the scene's pool back as it was found.
    if (before.dice?.length) await request.put(poolUrl, { data: { dice: before.dice } })
    else await request.delete(poolUrl)
  }
})
