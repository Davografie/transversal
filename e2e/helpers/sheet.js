// Shared navigation for sheet-level tests.
//
// Identity is a **server-issued session** (SEC-3), so it cannot be asserted from
// localStorage any more: `establishSession` obtains one for the player a spec
// names. What still lives in localStorage is the *perspective* — `entityId` and
// the current location — which is UI state, not identity.
//
// Those are the project's **test character and its owning test player** — never a
// real player's. `AGENTS.md` § "Player characters & the testing character"
// designates Kael Drift as the only `CHARACTER` an agent may act as. A suite that
// picks a real PC instead both reads and writes that player's data and makes their
// character appear online while the run is happening.
//
// Reaching a trait row also takes two steps that are not obvious from the markup:
// the sheet opens on the **set layer**, which renders no rows at all, so a test
// must drill into a set first; and the occupant dot that opens your own sheet has
// no accessible name (its title becomes "Drag to reposition" once it is
// draggable), so it is reached by its `self` class.

import { establishSession } from './session.js'

const GQL = '/api/v1/graphql'

/** Run a GraphQL query against the app's own endpoint. */
export async function gql(request, query, variables = {}) {
  const res = await request.post(GQL, { data: { query, variables } })
  if (!res.ok()) throw new Error(`graphql HTTP ${res.status()}`)
  const body = await res.json()
  if (body.errors) throw new Error(`graphql errors: ${JSON.stringify(body.errors)}`)
  return body.data
}

/** The project's testing character — see `AGENTS.md`. */
export const TEST_CHARACTER = 'character-kael-drift-e555ccde'

/**
 * The test character, asserted to be a usable sheet fixture.
 *
 * Deliberately pinned rather than searched for: tests act as the project's test
 * character (Kael Drift), never a real player's PC — driving a player's character
 * reads and writes their data and makes it appear online while the suite runs. If
 * the fixture is missing this throws with the fix in the message, rather than
 * quietly falling back to somebody's character.
 *
 * The *owning player* is resolved by the relationship, not by name: that test
 * identity has already been renamed once (`Tester` → `DSH MCP`) and a name lookup
 * broke the dock suite the moment it happened. Only the character id is pinned.
 *
 * The character still has to be *playable*: a trait setting whose set is gated to
 * another universe is filtered out of the sheet, so an entity can hold hundreds
 * of settings and still render an empty trait list. Since the sheet opens on the
 * set layer, which renders no rows at all, the fixture is only usable if one of
 * its settings belongs to a set available in its own universe — checked against
 * `traitsetsByUniverse`, the same availability signal the sheet uses, rather than
 * by loading sheets until one works.
 *
 * Returns `{ playerId, entityId, name, universe, traitSettings }`.
 */
export async function findPlayableCharacter(request) {
  const { players } = await gql(request, `
    query { players { id name agency { entityId main } } }
  `)
  // By the relationship, never by name — see the note in this function's docblock.
  const holders = (players || []).filter((p) =>
    (p.agency || []).some((a) => a.entityId === TEST_CHARACTER),
  )
  const tester = holders.find((p) =>
    (p.agency || []).some((a) => a.entityId === TEST_CHARACTER && a.main),
  ) || holders[0]
  if (!tester) {
    throw new Error(
      `no player holds ${TEST_CHARACTER} (Kael Drift) — the e2e suite acts as the project's ` +
      `testing character, not a real player (see AGENTS.md). Create the dedicated test player ` +
      `and claim Kael Drift as a main.`
    )
  }

  const { entity } = await gql(request, `
    query($id: ID!) {
      entity(id: $id) {
        id name currentUniverse
        traitSettings {
          id traitId name traitsetId traitsetName
          fromType relationshipType relationshipContactId
        }
      }
    }
  `, { id: TEST_CHARACTER })
  const settings = entity?.traitSettings || []
  if (!settings.length) {
    throw new Error(`the test character ${TEST_CHARACTER} has no trait settings — its sheet would render empty`)
  }

  const { traitsetsByUniverse } = await gql(request, `
    query($u: String!) { traitsetsByUniverse(universe: $u) { id } }
  `, { u: entity.currentUniverse })
  const available = new Set((traitsetsByUniverse || []).map((t) => t.id))
  if (!settings.some((s) => available.has(s.traitsetId))) {
    throw new Error(
      `the test character ${TEST_CHARACTER} holds no trait setting in a set available in ` +
      `${entity.currentUniverse} — its sheet would render an empty trait list`
    )
  }

  return {
    playerId: tester.id,
    playerName: tester.name,
    entityId: TEST_CHARACTER,
    name: entity.name,
    universe: entity.currentUniverse,
    traitSettings: settings,
  }
}

/**
 * Seed identity and open the sheet for `character`, returning the sheet locator.
 *
 * Fails loudly rather than silently, because "the sheet never opened" and "the
 * thing I meant to test is broken" look identical from the outside otherwise.
 */
export async function openSheet(page, { playerId, entityId, playerName = 'e2e' }) {
  await page.goto('/')
  await page.evaluate(([pid, pname, eid]) => {
    localStorage.setItem('playerId', pid)
    localStorage.setItem('playerName', pname)
    localStorage.setItem('entityId', eid)
  }, [playerId, playerName, entityId])
  // SEC-3: the seeding above records *intent*; the session is what the app reads.
  await establishSession(page)
  await page.goto('/')

  const self = page.locator('button.map-dot.self').first()
  await self.waitFor({ state: 'visible', timeout: 20_000 })
  await self.click()

  const panel = page.locator('.sheet-embedded').first()
  await panel.waitFor({ state: 'visible', timeout: 20_000 })
  return panel
}

/** Drill into a trait set by name, so its trait rows exist in the DOM. */
export async function openSet(page, setName) {
  const header = page.locator('.set-header').filter({ hasText: new RegExp(`^\\s*${setName}\\s*$`, 'i') }).first()
  await header.waitFor({ state: 'visible', timeout: 10_000 })
  await header.click()
  await page.locator('.trait-row').first().waitFor({ state: 'visible', timeout: 10_000 })
}

const escapeRe = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')

/**
 * Make trait rows visible, returning the name of the set opened (or null when the
 * sheet is flat and shows its rows directly).
 *
 * Which sets render rows depends on the universe gate, which is data — so this
 * tries each set in turn. Two things about the sheet make that fiddly and are the
 * reason this helper exists: it opens on the set layer, which renders no rows at
 * all, and a set with nothing visible renders *no control to go back*, so the way
 * out is the traits pill (`goToTraitSets`), not the list title.
 */
export async function ensureTraitRowsVisible(page) {
  const rows = page.locator('.trait-row')
  if (await rows.count()) return null // flat sheet — rows are already the list

  // The sheet element is visible before its traits have loaded, so wait for the
  // set layer (or a flat list) to exist. Without this the enumeration below sees
  // an empty sheet and reports "no set rendered rows" — a race, not a fault.
  await page.waitForFunction(
    () => document.querySelector('.set-name') || document.querySelector('.trait-row'),
    null,
    { timeout: 20_000 },
  )
  if (await rows.count()) return null

  const names = await page.locator('.set-name').evaluateAll(
    (els) => els.map((e) => e.innerText.trim()),
  )
  for (const name of names) {
    // Match the `.set-name` child, not the header: the header also carries the
    // set's limit dots, so its text is "DISTINCTIONS ○" and an anchored match on
    // the header itself never fires.
    const header = page
      .locator('.trait-set')
      .filter({ has: page.locator('.set-name', { hasText: new RegExp(`^${escapeRe(name)}$`, 'i') }) })
      .locator('.set-header')
      .first()
    await header.click()
    try {
      await rows.first().waitFor({ state: 'visible', timeout: 1_500 })
      return name
    } catch {
      // Nothing visible in this set — back to the set layer for the next one.
      await page.locator('button.pill', { hasText: '🎲' }).first().click()
      await page.locator('.set-header').first().waitFor({ state: 'visible', timeout: 5_000 })
    }
  }
  throw new Error(`no trait set on this sheet rendered a trait row (tried: ${names.join(', ')})`)
}

/** Right-click a trait row to open its editor; returns the setting id it opened. */
export async function openTraitEditor(page, { settingId } = {}) {
  const row = settingId
    ? page.locator(`[data-ts-id="${settingId}"]`).first()
    : page.locator('.trait-row').first()
  await row.waitFor({ state: 'visible', timeout: 10_000 })
  const opened = await row.getAttribute('data-ts-id')
  await row.click({ button: 'right' })
  await page.locator('.trait-edit-panel').first().waitFor({ state: 'visible', timeout: 10_000 })
  return opened
}
