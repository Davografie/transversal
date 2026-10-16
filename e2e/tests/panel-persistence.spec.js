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
import { gql } from '../helpers/sheet.js'
import { bootGmPanel, enterPrep, detachByDrag } from '../helpers/gm.js'

const TEST_CHARACTER = 'character-kael-drift-e555ccde'
// Both the chain and the floating windows render inside a `.panel-viewport`, and
// both are `.panel-node[data-panel-window]` — the root panel is the one whose
// window id is `root`, the floats are `gm-win-N`.
const WINDOWS = '[data-panel-window]:not([data-panel-window="root"])'
const STORE = 'gmPanelWindows'

let character
test.beforeAll(async ({ request }) => {
  const { players } = await gql(request, `query { players { id name agency { entityId main } } }`)
  const owner = players.find((p) => (p.agency || []).some((a) => a.entityId === TEST_CHARACTER && a.main))
  if (!owner) throw new Error(`no player mains ${TEST_CHARACTER} — cannot reach the testing character`)
  character = { playerId: owner.id, playerName: owner.name, entityId: TEST_CHARACTER }
})


const stored = (page) => page.evaluate((k) => JSON.parse(localStorage.getItem(k) || 'null'), STORE)

test('an entity panel: detach, reload, still floating', async ({ page }) => {
  await bootGmPanel(page, character)
  await enterPrep(page)

  await page.locator('.tree-row').first().click()
  await page.waitForTimeout(1400)
  await detachByDrag(page)
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
  await bootGmPanel(page, character)
  await enterPrep(page)

  await page.locator('.panel-node button', { hasText: 'SFX' }).first().click()
  await page.waitForTimeout(1500)
  // Scope to the SFX panel's own node: `.entity-row` is a shared row shell.
  await page.locator('.panel-node').last().locator('.entity-row').first().click()
  await page.waitForTimeout(1500)
  await detachByDrag(page)
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

// A Panel's collapse is `props.collapsed ?? localCollapsed`: pass the prop and the
// state belongs to the caller (and so can be stored), leave it off and the Panel
// keeps it privately — which is why a reload used to come back expanded however
// the window had been left.
test('a collapsed window comes back collapsed', async ({ page }) => {
  await bootGmPanel(page, character)
  await enterPrep(page)

  await page.locator('.tree-row').first().click()
  await page.waitForTimeout(1400)
  await detachByDrag(page)
  await page.waitForTimeout(900)
  await expect(page.locator(WINDOWS)).toHaveCount(1)

  // Collapse the window through its own rail, then confirm it is the *stored*
  // state that changed rather than a local one.
  await page.locator(`${WINDOWS} [title="Collapse"]`).first().click()
  await page.waitForTimeout(900)
  expect((await stored(page))[0].collapsed, 'the collapse was written').toBe(true)

  await page.reload()
  await page.waitForTimeout(3000)
  await expect(page.locator(WINDOWS), 'the window came back').toHaveCount(1)
  await expect(page.locator(`${WINDOWS} .panel.is-collapsed`), 'and still collapsed').toHaveCount(1)
  // Collapsed means the chip header, which is where its expand/close controls
  // live while the rail is hidden.
  await expect(page.locator(`${WINDOWS} .panel-header`), 'still a chip, not a hole').toHaveCount(1)
})

// The stack root is deliberately **not** collapsible (2026-10-16, at the human's
// direction): collapsing the chain's own root only ever produced a chip of the
// panel you were working in. The control is gone from that panel, and the chip
// state an older build wrote to `gmPanelStackCollapsed` is no longer read — so a
// value left behind cannot strand the root as a chip.
test('the stack root offers no collapse, and a stale stored state cannot strand it', async ({ page }) => {
  // What an older build would have left behind, written before the app boots.
  await page.addInitScript(() => localStorage.setItem('gmPanelStackCollapsed', 'true'))

  // `bootGmPanel` opens the chain itself, and this spec never closes it.
  await bootGmPanel(page, character)

  const root = '[data-panel-window="root"][data-panel-depth="0"]'
  await expect(page.locator(`${root} .panel-actions [title="Collapse"]`),
    'no collapse control on the root').toHaveCount(0)
  await expect(page.locator(`${root} .panel`),
    'and the stale value did not leave it a chip').not.toHaveClass(/is-collapsed/)
  await expect(page.locator(`${root} .panel-body`), 'its body is there').toBeVisible()

  // The floating-window half of this is the test above: a window's own rail
  // still offers `Collapse`, which is what keeps its chip across a reload.
})
