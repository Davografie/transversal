import { test, expect } from '@playwright/test'
import { gql } from '../helpers/sheet.js'
import { establishSession } from '../helpers/session.js'

// This drives a live backend that other sessions are also using, and a batch run
// can take far longer than the 30s default purely because of that contention —
// each test alone is ~5s. Same allowance the definition suite takes.
test.setTimeout(120_000)

// Filling a set's limit hands the reader the next set — in **both** shapes:
// the drill-in enters the next set's list, the accordion closes the finished
// section and opens the next.
//
// The check hangs on the *pool update*, not on the click. `isInPool` reads the
// pool the host owns, so at click time the new die is not in it yet and any count
// taken there is a guess; `setPoolSources` runs when the host pushes the changed
// sources back, which is the first moment the answer is true. That distinction is
// the whole reason this was twice deferred as racy, so it is worth a test rather
// than a comment.
//
// Two shapes, and the interplay with B185's return-from-detail, because that also
// navigates: the two share one `setIsFull` predicate so neither undoes the other.

// The testing character, resolved through the ownership relationship rather than
// by name — the player has been renamed once already (`Tester` → `DSH MCP`).
const TEST_ENTITY = 'character-kael-drift-e555ccde'
const TEST_PLAYER = 'player-75a410'
const TEST_PLAYER_NAME = 'DSH MCP'
const DESKTOP = { width: 1280, height: 950 }
const PHONE = { width: 390, height: 844 }

let character
test.beforeAll(async ({ request }) => {
  const { players } = await gql(request, `query { players { id name agency { entityId main } } }`)
  const owner = players.find((p) => (p.agency || []).some((a) => a.entityId === TEST_ENTITY && a.main))
  if (!owner) throw new Error(`no player mains ${TEST_ENTITY} — cannot reach the testing character`)
  character = { playerId: owner.id, playerName: owner.name, entityId: TEST_ENTITY }
})

/** The pool a sheet plays into: per location and entity. */
async function poolUrl(request, entityId) {
  const { entity } = await gql(request, `query($id: ID!) { entity(id: $id) { currentLocation } }`, { id: entityId })
  return entity?.currentLocation
    ? `/api/v1/locations/${entity.currentLocation}/pools/${entityId}`
    : null
}

/** Snapshot the pool so a test can put it back exactly, pass or fail. */
async function snapshotPool(request, entityId) {
  const url = await poolUrl(request, entityId)
  if (!url) return null
  const res = await request.get(url)
  return { url, dice: res.ok() ? (await res.json()).dice || [] : [] }
}

async function restorePool(request, snap) {
  if (!snap) return
  const res = await request.put(snap.url, { data: { dice: snap.dice } })
  expect(res.ok(), 'the sheet\'s pool must be put back as it was found').toBeTruthy()
}

async function load(page, size, { entityId, playerId, playerName }) {
  await page.setViewportSize(size)
  await page.goto('/')
  await page.evaluate((ids) => {
    localStorage.setItem('playerId', ids.playerId)
    localStorage.setItem('playerName', ids.playerName)
    localStorage.setItem('entityId', ids.entityId)
    // Both shapes persist where the reader is, so a case must not inherit one.
    localStorage.removeItem('sheet.openTraitSets')
    localStorage.removeItem('sheet.traitSetDrill')
  }, { entityId, playerId, playerName })
  await establishSession(page)
  await page.goto('/')
  await page.waitForFunction(() => !!document.querySelector('.stage'), null, { timeout: 20_000 })
  await page.waitForTimeout(1200)

  const dot = page.locator('button.map-dot.self').first()
  if (await dot.count()) { await dot.click().catch(() => {}); await page.waitForTimeout(900) }
  // The band stack starts on the map; its sheet band is a teaser until tapped.
  if (await page.locator('.stage.mobile-stack').count()) {
    const y = await page.evaluate(() => {
      const r = document.querySelector('.sheet-band').getBoundingClientRect()
      return Math.round(r.y + 6)
    })
    await page.mouse.click(6, y)
  }
  await page.waitForSelector('.sheet-embedded .set-header, .sheet-embedded .trait-row', { timeout: 20_000 })
  await page.waitForTimeout(400)
}

const kael = () => ({ entityId: character.entityId, playerId: character.playerId, playerName: character.playerName })
// The row that a plain click actually plays — *chosen*, not assumed.
//
// A row click toggles its die, so a row already in the pool would remove rather
// than add, silently inverting every assertion here (`:not(.in-pool)` rules that
// out). And not every unpooled row plays: a trait with no die contributes nothing
// (`emitTraitDice` returns early), a resource or a challenge spends through its own
// die groups rather than the row, and a container has no `.trait-right` at all. A
// click on one of those is silently a no-op, which is exactly how this spec first
// went flaky. The modifiers are the discriminator: the plain branch is
// `.trait-die-groups` carrying neither `resource` nor `challenge`.
const UNPOOLED_ROWS = '.sheet-embedded .trait-row:not(.in-pool)'
async function playableRow(page) {
  const rows = page.locator(UNPOOLED_ROWS)
  const idx = await rows.evaluateAll((els) => els.findIndex((r) => {
    const groups = r.querySelector('.trait-right .trait-die-groups')
    return !!groups && !groups.classList.contains('resource') && !groups.classList.contains('challenge')
  }))
  return idx === -1 ? null : rows.nth(idx)
}

// …and never pin the set *names*. The testing character is shared, and other
// sessions move him between universes, which changes which sets render and in
// what order — a spec that asserts "CULTIVATION then ASSETS" starts failing for a
// reason that has nothing to do with the code. So the set is found, and the
// expectation is "the one after it in the sheet's own order".
async function setNameList(page) {
  return page.locator('.sheet-embedded .set-name').evaluateAll((els) => els.map((e) => e.innerText.trim()))
}

/**
 * Open sets in order until one offers a plain playable pick, and report it with
 * its successor. Returns null when no set does.
 */
async function firstPlayableSet(page, { open }) {
  const names = await setNameList(page)
  for (let i = 0; i < names.length; i++) {
    await open(i)
    await page.waitForTimeout(350)
    const row = await playableRow(page)
    if (row) return { name: names[i], next: names[i + 1] || null, row }
    await open(i) // close it again and try the next
    await page.waitForTimeout(200)
  }
  return null
}

/**
 * Wait for a read to reach what it should.
 *
 * Everything asserted here crosses the same hop: the sheet writes to the pool the
 * *host* owns, the host pushes the changed sources back, and only then do the open
 * sets and the limit dots reflect the pick. That is one round trip of unknown
 * length under load, so a fixed sleep is a guess — this polls instead.
 */
async function until(page, read, ok, timeout = 8000) {
  const deadline = Date.now() + timeout
  let value = await read()
  while (!ok(value) && Date.now() < deadline) {
    await page.waitForTimeout(150)
    value = await read()
  }
  return value
}

const openSets = (page) => page.evaluate(() =>
  [...document.querySelectorAll('.sheet-embedded .trait-set.open .set-name')].map((e) => e.innerText.trim()))
const drillTitle = (page) => page.evaluate(() =>
  document.querySelector('.sheet-embedded .trait-list-title')?.innerText?.trim() || null)

test('accordion: filling a set closes it and opens the next', async ({ page, request }) => {
  const snap = await snapshotPool(request, character.entityId)
  try {
    await load(page, DESKTOP, kael())
    const target = await firstPlayableSet(page, { open: (i) => page.locator('.sheet-embedded .set-toggle').nth(i).click() })
    expect(target, 'some set offers a plain playable pick').not.toBeNull()
    expect(target.next, 'and has a successor to advance to').not.toBeNull()
    expect(await openSets(page), 'the set being filled is the open one').toEqual([target.name])

    await target.row.locator('.trait-right').click()

    // The finished set is closed so the next one is where the reader is looking.
    const after = await until(page, () => openSets(page), (v) => v.length === 1 && v[0] === target.next)
    expect(after, `expected to be handed ${target.next}`).toEqual([target.next])
  } finally {
    await restorePool(request, snap)
  }
})

test('drill-in: filling a set enters the next', async ({ page, request }) => {
  const snap = await snapshotPool(request, character.entityId)
  try {
    await load(page, PHONE, kael())
    const target = await firstPlayableSet(page, { open: (i) => page.locator('.sheet-embedded .set-header-link').nth(i).click() })
    expect(target, 'some set offers a plain playable pick').not.toBeNull()
    expect(target.next, 'and has a successor to advance to').not.toBeNull()
    expect(await drillTitle(page), 'the set being filled is the one entered').toBe(`← ${target.name}`)

    await target.row.locator('.trait-right').click()

    const title = await until(page, () => drillTitle(page), (v) => v === `← ${target.next}`)
    expect(title, 'the reader is handed the next set').toBe(`← ${target.next}`)
  } finally {
    await restorePool(request, snap)
  }
})

test('playing from the detail advances instead of re-opening the finished set', async ({ page, request }) => {
  // B185 also navigates on this path (it returns from the detail to the set), so
  // the two have to agree on who owns where the reader lands.
  const snap = await snapshotPool(request, character.entityId)
  try {
    await load(page, DESKTOP, kael())
    const target = await firstPlayableSet(page, { open: (i) => page.locator('.sheet-embedded .set-toggle').nth(i).click() })
    expect(target, 'some set offers a plain playable pick').not.toBeNull()
    expect(target.next, 'and has a successor to advance to').not.toBeNull()

    await target.row.locator('.trait-name').click()
    await page.waitForTimeout(600)
    expect(await page.locator('.detail-rating-band.playable').count()).toBeGreaterThan(0)
    await page.locator('.detail-rating-band').click()
    await until(page, () => openSets(page), (v) => v.length === 1 && v[0] === target.next)

    expect(await page.locator('.trait-detail-panel').count(), 'the detail closes').toBe(0)
    expect(await openSets(page), 'and the filled set is not reopened behind it').toEqual([target.next])
  } finally {
    await restorePool(request, snap)
  }
})

// **Not in this suite: "a pick that does not fill the set advances nothing."** It is
// the other half of the rule, and it is *not* covered here on purpose.
//
// Every one of the testing character's sets has a limit of 1, so any pick fills one
// and the negative case cannot be reached on him. The obvious substitute — seed a
// foreign GMC's id and drive *its* sheet — turns out to be unsafe rather than merely
// awkward: the app then writes to the pool keyed by the **location** it believes it
// is standing in, while the sheet's own `poolSources` reflect a different key, so a
// row that is already pooled looks unpooled and the click *removes* a die instead of
// adding one. Measured: a click on Li Huan's `complications` took a d4 out of
// `loc-40646134`'s shared pool. That is a property of seeding a foreign entity, not
// of the advance, and it was restored by hand.
//
// The case *was* observed once, on a genuinely clean pool: one pick into a limit-4
// set filled one of its four dots and moved nobody. The predicate itself is one
// expression shared with the dots (`setIsFull`), and tests above prove it fires when
// the set really is full — so the gap is the *setup*, not the logic. Closing it
// needs a fixture that owns its own entity and pool.
