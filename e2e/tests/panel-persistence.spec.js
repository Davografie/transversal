// Floating GM panels persist client-side (the `gm-panel-persistence` check's
// browser half).
//
// The node check proves the serialization rules but cannot prove the feature:
// whether a detach writes anything, and whether a reload brings the window back,
// are browser facts. The first cut of this shipped with **two** bugs that only a
// browser could show, and both are pinned here:
//
//   1. `restorableNameOf` matched components by identity. The Vite dev server
//      serves a module it has invalidated (HMR) under `<path>?t=<stamp>`, so the
//      same SFC can exist as two objects — the opener's and the registry's — and
//      identity silently missed. Nothing persisted at all, and the store was then
//      rewritten empty. (Fixed with a `__name` fallback; see the unit check.)
//   2. A reactive `props` value was refused. The SFX editor is opened with a
//      record straight out of the shared store, so its props are proxies by
//      construction — refusing them made that panel unrestorable.
//
// `gmMode` is a ref **seeded from localStorage**, not a live read of the player's
// role, so arrange mode has to be seeded before load rather than mocked after it.
import { test, expect } from '@playwright/test'
import { asArchitect } from '../helpers/arrange.js'
import { gql } from '../helpers/sheet.js'

const TEST_CHARACTER = 'character-kael-drift-e555ccde'
const DETACH = '[title="Detach into a floating window"]'
const WINDOWS = '[data-panel-window]'
const STORE = 'gmPanelWindows'

let character
test.beforeAll(async ({ request }) => {
  const { players } = await gql(request, `query { players { id name agency { entityId main } } }`)
  const owner = players.find((p) => (p.agency || []).some((a) => a.entityId === TEST_CHARACTER && a.main))
  if (!owner) throw new Error(`no player mains ${TEST_CHARACTER} — cannot reach the testing character`)
  character = { playerId: owner.id, playerName: owner.name, entityId: TEST_CHARACTER }
})

async function bootGmPanel(page) {
  await asArchitect(page)
  await page.addInitScript(([pid, eid, pname]) => {
    localStorage.setItem('playerId', pid)
    localStorage.setItem('playerName', pname)
    localStorage.setItem('entityId', eid)
    localStorage.setItem('architectMode', 'true')
  }, [character.playerId, character.entityId, character.playerName])
  await page.goto('/')
  await page.waitForTimeout(2500)
  await page.locator('button', { hasText: '🛠' }).first().click()
  await page.waitForTimeout(1000)
}

const stored = (page) => page.evaluate((k) => JSON.parse(localStorage.getItem(k) || 'null'), STORE)

test('an entity panel: detach, reload, still floating', async ({ page }) => {
  await bootGmPanel(page)
  const prep = page.locator('.mode-tabs button, .tab-btn', { hasText: 'Prep' })
  if (await prep.count()) { await prep.first().click(); await page.waitForTimeout(1000) }

  await page.locator('.tree-row').first().click()
  await page.waitForTimeout(1400)
  await page.locator(DETACH).last().click()
  await page.waitForTimeout(900)

  const afterDetach = await stored(page)
  expect(afterDetach, 'the detach wrote a record').toHaveLength(1)
  expect(afterDetach[0].name).toBe('GmEntityEditPanel')
  // The spec cannot be stored — only its name, props and geometry.
  expect(afterDetach[0]).not.toHaveProperty('listeners')
  expect(afterDetach[0]).not.toHaveProperty('context')
  expect(typeof afterDetach[0].props.entityId).toBe('string')
  expect(afterDetach[0].x).toBeGreaterThan(0)

  await page.reload()
  await page.waitForTimeout(3000)
  await expect(page.locator(WINDOWS), 'the window came back').toHaveCount(1)
  // And the record survived the load — a failed restore rewrites the store empty,
  // which is what made the first cut's failure permanent.
  expect((await stored(page))[0].name).toBe('GmEntityEditPanel')
})

test('an SFX panel: detach, reload, still floating', async ({ page }) => {
  await bootGmPanel(page)
  const prep = page.locator('.mode-tabs button, .tab-btn', { hasText: 'Prep' })
  if (await prep.count()) { await prep.first().click(); await page.waitForTimeout(1000) }

  await page.locator('.panel-node button', { hasText: 'SFX' }).first().click()
  await page.waitForTimeout(1500)
  // Scope to the SFX panel's own node: `.entity-row` is a shared row shell.
  await page.locator('.panel-node').last().locator('.entity-row').first().click()
  await page.waitForTimeout(1500)
  await page.locator(DETACH).last().click()
  await page.waitForTimeout(900)

  const afterDetach = await stored(page)
  expect(afterDetach, 'the detach wrote a record').toHaveLength(1)
  // Its props come out of the shared store as a **reactive proxy**; the record
  // must hold the plain snapshot, not the proxy's internals.
  expect(afterDetach[0].name).toBe('GmSfxEditPanel')
  expect(typeof afterDetach[0].props.sfx.id).toBe('string')
  expect(JSON.stringify(afterDetach[0])).not.toContain('__v_isReactive')

  await page.reload()
  await page.waitForTimeout(3000)
  await expect(page.locator(WINDOWS), 'the window came back').toHaveCount(1)
  expect((await stored(page))[0].name).toBe('GmSfxEditPanel')
})
