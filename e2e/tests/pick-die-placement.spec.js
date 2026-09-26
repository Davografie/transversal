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
// character), mained by the `DSH MCP` test player. That player is an **architect**,
// so the app runs in GM free-roam and the roller picks in the *location's* pool
// rather than an entity's. The pool is discovered from the roller's own request —
// a free-roam pool is keyed by the location id, so its two path segments are equal —
// and it is left as it was found.

import { test, expect } from '@playwright/test'

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

  // Every free-roam (location-keyed) pool the roller reads. The app settles on its
  // current location during load, so the last one is the pool it ends up editing.
  const freeRoamPools = []
  page.on('request', (r) => {
    const m = r.url().match(/\/api\/v1\/locations\/([^/]+)\/pools\/([^/?]+)$/)
    if (r.method() === 'GET' && m && m[1] === m[2]) freeRoamPools.push(new URL(r.url()).pathname)
  })

  await page.goto('/')
  await page.evaluate((ids) => {
    localStorage.setItem('playerId', ids.playerId)
    localStorage.setItem('playerName', ids.playerName)
    localStorage.setItem('entityId', ids.entityId)
  }, character)

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
  const poolUrl = freeRoamPools[freeRoamPools.length - 1]
  expect(poolUrl, 'the roller must read a location-keyed pool').toBeTruthy()

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

    // A fresh load restores the rolled pool straight into picking.
    freeRoamPools.length = 0
    await page.goto('/')
    await openRoller()
    await page.locator('.roll-pick').waitFor({ state: 'visible', timeout: 30_000 })
    expect(
      freeRoamPools[freeRoamPools.length - 1],
      'the roller must still be reading the pool this test seeded',
    ).toBe(poolUrl)

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
