import { test, expect } from '@playwright/test'

// The trait-definition picker inside a trait set that allows duplicates.
//
// `allow_duplicates` exists so a set can hold several instances of one
// definition (`resources`: two weapons, two contacts, two of anything). The
// picker contradicted it — "a definition the entity already holds is not a legal
// destination (its one instance is not this one)" — so the definition the flag
// exists for was the one definition it never offered. Reported on `resources`:
// the human could *add* a second copy but could not repoint an instance onto one.
//
// The backend had the same fault from the other side: it asked
// `find_traitsetting_collision`, the *instance* question (a statement tells two
// instances apart), where the sheet needs the *set* question (`may_hold_another`
// — does this set permit more than one instance of a definition?). Both now
// mirror the same rule, which is what this checks from the outside.
//
// Kael Drift is the project's testing character, pinned here on purpose: the
// sheet's shared helper picks *a real player's* character, which an automated
// run must not drive (it would read and write the player's data). Kael is the
// project's own, owned by the dedicated test player `DSH MCP`.
const KAEL = 'character-kael-drift-e555ccde'
const PLAYER = 'player-75a410'
const PLAYER_NAME = 'DSH MCP'

const GQL = '/api/v1/graphql'
const escapeRe = (s) => String(s).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')

async function gql(request, query, variables = {}) {
  const res = await request.post(GQL, { data: { query, variables } })
  if (!res.ok()) throw new Error(`graphql HTTP ${res.status()}`)
  const body = await res.json()
  if (body.errors) throw new Error(`graphql errors: ${JSON.stringify(body.errors)}`)
  return body.data
}

/** Sign in as the test player and open Kael's sheet. */
async function openKaelsSheet(page) {
  await page.setViewportSize({ width: 1280, height: 950 })
  await page.goto('/')
  await page.evaluate(({ playerId, playerName, entityId }) => {
    localStorage.setItem('playerId', playerId)
    localStorage.setItem('playerName', playerName)
    localStorage.setItem('entityId', entityId)
  }, { playerId: PLAYER, playerName: PLAYER_NAME, entityId: KAEL })
  await page.goto('/')
  await page.locator('.sheet-embedded .header').first().waitFor({ state: 'visible', timeout: 20_000 })
}

/**
 * Two instances of *different* definitions inside one duplicate-allowing set —
 * the pair the picker is supposed to offer each other.
 *
 * Read from the API rather than pinned: which traits Kael holds is live data, and
 * a spec that named `qi` and `ammunition` would start failing for a reason that
 * has nothing to do with the picker. Returns the instance to open, the definition
 * it must offer, and the name of the set they share.
 */
async function duplicatePair(request) {
  const who = await gql(request, `
    query($id: ID!) { entities(ids: [$id]) { currentUniverse } }
  `, { id: KAEL })
  const universe = who.entities[0].currentUniverse

  const data = await gql(request, `
    query($id: ID!, $u: String!) {
      entities(ids: [$id]) { traitSettings { id traitId name traitsetId } }
      traitsets { id name allowDuplicates }
      traitsByUniverse(universe: $u) { id }
    }
  `, { id: KAEL, u: universe })

  // Only definitions the picker could offer at all. It is scoped to the body's
  // current universe, so a trait from another one is out of the list for a reason
  // that has nothing to do with duplicates — and Kael holds three_realms traits
  // while standing in earth, which would otherwise pick an impossible pair.
  const available = new Set(data.traitsByUniverse.map((t) => t.id))
  const sets = new Map(data.traitsets.map((s) => [s.id, s]))
  const bySet = new Map()
  for (const s of data.entities[0].traitSettings) {
    if (!sets.get(s.traitsetId)?.allowDuplicates) continue
    if (!available.has(s.traitId)) continue
    if (!bySet.has(s.traitsetId)) bySet.set(s.traitsetId, [])
    bySet.get(s.traitsetId).push(s)
  }
  for (const settings of bySet.values()) {
    settings.sort((a, b) => String(a.name).localeCompare(String(b.name)))
    for (const setting of settings) {
      const sibling = settings.find((o) => o.traitId !== setting.traitId)
      if (sibling) return { setting, sibling, setName: sets.get(setting.traitsetId).name }
    }
  }
  throw new Error('Kael holds no duplicate-allowing set with two different definitions')
}

test('a definition the body already holds is offered inside a duplicate-allowing set', async ({ page, request }) => {
  test.setTimeout(120_000)
  const { setting, sibling, setName } = await duplicatePair(request)

  await openKaelsSheet(page)

  // The sheet lists its *sets* first, so a set's rows are only in the DOM once it
  // is drilled into — and the editor is opened from the row.
  const row = page.locator(`[data-ts-id="${setting.id}"]`)
  if (!(await row.count())) {
    const header = page.locator('.trait-set')
      .filter({ has: page.locator('.set-name', { hasText: new RegExp(`^${escapeRe(setName)}$`, 'i') }) })
      .locator('.set-header').first()
    await header.waitFor({ state: 'visible', timeout: 10_000 })
    await header.click()
  }
  await row.waitFor({ state: 'visible', timeout: 10_000 })
  await row.click({ button: 'right' })
  await page.locator('.trait-edit-panel').first().waitFor({ state: 'visible', timeout: 10_000 })

  await page.locator('.definition-chip').click()
  await expect(page.locator('.definition-dropdown'), 'the picker must open on the first click')
    .toBeVisible()
  await expect(page.locator('.definition-option').first(), 'the picker must load its options')
    .toBeVisible({ timeout: 10_000 })

  // The picker opens filtered to the instance's own set, which is where the
  // sibling lives. Pin that, so a failure below is the collision filter and not
  // the set filter hiding it.
  await expect(page.locator('.definition-set-filter')).toHaveValue(setting.traitsetId)

  const labels = await page.locator('.definition-option').evaluateAll(
    (els) => els.map((e) => e.innerText.trim()),
  )
  expect(
    labels.some((l) => l.toLowerCase() === String(sibling.name).toLowerCase()),
    `"${sibling.name}" is already held by Kael and "${setName}" allows duplicates, so it must be `
    + `offerable — the picker offered: ${labels.join(', ')}`,
  ).toBe(true)
})
