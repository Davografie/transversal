// Dynamic GM panel stacking (the `gm-panel-stacking` check's browser half).
//
// The node check proves the rules and the wiring; it cannot prove the browser
// *obeyed* them. Two things only a browser can show, and both are pinned here:
//
//   1. The rank reaches the DOM. The chain's rank is a `ref` bound inside an
//      inline style object — exactly the shape that silently renders as
//      `[object Object]` and leaves the unit at `z-index: auto`, which would look
//      right in the source and be unraisable in practice.
//   2. A click raises. The listener is capture-phase on `window` precisely
//      because panels are full of controls that stop propagation; that claim is
//      about event dispatch, not about the text of the code.
//
// The unit of stacking is a **unit** — the chain, or one floating window — so the
// root unit's id is `root` and a float's is its `gm-win-N`. Measured while writing
// this: the GM panel root renders **no header at all** (no title, no badge, not
// collapsed), and every child detached from the same parent parks on exactly the
// same box — so a float can be completely covered by the chain's next child, and
// the order of the gestures below matters.
import { test, expect } from '@playwright/test'
import { gql } from '../helpers/sheet.js'
import { bootGmPanel, enterPrep, openStack } from '../helpers/gm.js'

const TEST_CHARACTER = 'character-kael-drift-e555ccde'
const DETACH = '[title="Detach into a floating window"]'
const ROOT = '[data-panel-unit="root"]'
const FLOATS = '[data-panel-unit]:not([data-panel-unit="root"])'
// A panel opened as a child of the chain: a `.panel-node` inside a `.panel-node`
// (and so *not* the root panel's own rail, whose Close would close the whole
// stack).
const NESTED_CLOSE = `${ROOT} .panel-node .panel-node [title="Close"]`
const STORE = 'gmPanelWindows'

let character
test.beforeAll(async ({ request }) => {
  const { players } = await gql(request, `query { players { id name agency { entityId main } } }`)
  const owner = players.find((p) => (p.agency || []).some((a) => a.entityId === TEST_CHARACTER && a.main))
  if (!owner) throw new Error(`no player mains ${TEST_CHARACTER} — cannot reach the testing character`)
  character = { playerId: owner.id, playerName: owner.name, entityId: TEST_CHARACTER }
})

/** What the browser resolved: each unit's rank, and the layer they share. */
const stack = (page) => page.evaluate(() => {
  const units = [...document.querySelectorAll('[data-panel-unit]')]
  const ranks = {}
  for (const u of units) ranks[u.dataset.panelUnit] = Number(getComputedStyle(u).zIndex)
  return {
    ranks,
    // One parent is what makes the ranks comparable: a unit inside a second
    // stacking context could never be raised past the first layer's contents.
    sameParent: new Set(units.map((u) => u.parentElement)).size === 1,
    layerZ: units[0] ? Number(getComputedStyle(units[0].parentElement).zIndex) : null,
    // The wrapper must not have swallowed the panels: a unit's panel is still a
    // real, measured box.
    boxes: units.map((u) => Math.round(u.querySelector('.panel-node')?.getBoundingClientRect().width ?? 0)),
  }
})

/** The floats, bottom-first, identified by their panel title (ids are per-session). */
const floats = (page) => page.evaluate(() =>
  [...document.querySelectorAll('[data-panel-unit]:not([data-panel-unit="root"])')]
    .map((u) => ({
      z: Number(getComputedStyle(u).zIndex),
      title: u.querySelector('.panel-title')?.textContent?.trim() ?? '',
    }))
    .sort((a, b) => a.z - b.z))

const stored = (page) => page.evaluate((k) => JSON.parse(localStorage.getItem(k) || 'null'), STORE)

/** Open a tree row and detach the panel it opens into a floating window. */
async function detachChild(page, row) {
  await page.locator('.tree-row').nth(row).click()
  await page.waitForTimeout(1400)
  await page.locator(DETACH).last().click()
  await page.waitForTimeout(900)
}

test('clicking a panel raises its unit above the others', async ({ page }) => {
  await bootGmPanel(page, character)
  await enterPrep(page)
  await detachChild(page, 0)

  await expect(page.locator(FLOATS), 'the detached panel is its own unit').toHaveCount(1)
  const start = await stack(page)
  const float = Object.keys(start.ranks).find((id) => id !== 'root')
  expect(Object.keys(start.ranks).sort(), 'the chain and the float').toEqual(['root', float].sort())
  expect(start.sameParent, 'one layer, so one stacking context').toBe(true)
  expect(start.layerZ, 'the layer keeps its fixed rank — 25, under the 🛠 toggle').toBe(25)
  expect(start.boxes.every((w) => w > 0), 'both units still carry a measured panel').toBe(true)
  // A window was just opened, so it is on top.
  expect(start.ranks[float], 'the new window starts on top').toBeGreaterThan(start.ranks.root)

  // Work in the chain — clicking a tree row opens a child, which lands on the box
  // the window occupies. The chain comes forward over it.
  await page.locator('.tree-row').nth(1).click()
  await page.waitForTimeout(1400)
  const raised = await stack(page)
  expect(raised.ranks.root, 'the chain came forward').toBeGreaterThan(raised.ranks[float])

  // Close that child so the window is reachable again, then click the window.
  await page.locator(NESTED_CLOSE).first().click()
  await page.waitForTimeout(900)
  await page.locator(`${FLOATS} .panel-title`).first().click()
  await page.waitForTimeout(300)
  const back = await stack(page)
  expect(back.ranks[float], 'the window came back forward').toBeGreaterThan(back.ranks.root)
})

test('the stacking order of the floats survives a reload', async ({ page }) => {
  await bootGmPanel(page, character)
  await enterPrep(page)
  await detachChild(page, 0)
  await detachChild(page, 1)

  await expect(page.locator(FLOATS), 'two floating windows').toHaveCount(2)
  const before = await floats(page)
  expect(before.map((f) => f.title.length > 0), 'both floats are identified by a title').toEqual([true, true])
  expect(before[0].z, 'the second window is on top').toBeLessThan(before[1].z)

  // The rank is written with the window. (The chain has a rank too and is not
  // stored, so the sequence has gaps — the *order* is the promise, not the
  // numbers.)
  const records = await stored(page)
  expect(records[0].z, 'ranks are stored ascending').toBeLessThan(records[1].z)

  await page.reload()
  await page.waitForTimeout(3000)
  await expect(page.locator(FLOATS), 'both windows came back').toHaveCount(2)
  const after = await floats(page)
  expect(after.map((f) => f.title), 'in the same stacking order, bottom-first')
    .toEqual(before.map((f) => f.title))
  expect(after[0].z, 'renormalised to a dense run, and still ordered').toBeLessThan(after[1].z)
})

// The one open that is not a panel's `openChild`: the 🛠 itself. It sits *outside*
// the panel layer — it is what opens the chain — so neither the capture-phase
// raise (no `[data-panel-unit]` ancestor) nor the child-open rule can see it. A
// float left over from earlier stays where it is, and the chain that was just
// reopened comes back at the rank it had, which is behind the float: the panel
// you just opened, hidden by one you opened before it.
//
// The reopen here follows a reload on purpose. Closing the chain with a *click* on
// its rail would not show the bug: the capture-phase pointerdown raises the chain
// on the way out, so it happens to reopen in front — which is how this passed
// before the fix was written. A reload is also the ordinary way to arrive here:
// the floats are restored, the chain starts closed, and the first 🛠 draws it
// under them.
test('opening the chain with the 🛠 raises it above a window already open', async ({ page }) => {
  await bootGmPanel(page, character)
  await enterPrep(page)
  await detachChild(page, 0)

  const start = await stack(page)
  const float = Object.keys(start.ranks).find((id) => id !== 'root')
  expect(start.ranks[float], 'the new window starts on top').toBeGreaterThan(start.ranks.root)

  // Reload: the window is restored, the chain starts closed — the state the 🛠 is for.
  await page.reload()
  await page.waitForTimeout(2600)
  await expect(page.locator(ROOT), 'the chain starts closed').toHaveCount(0)
  await expect(page.locator(FLOATS), 'and the window came back').toHaveCount(1)

  await openStack(page)
  const reopened = await stack(page)
  const back = Object.keys(reopened.ranks).find((id) => id !== 'root')
  expect(reopened.ranks.root, 'the chain you just opened is in front of the window')
    .toBeGreaterThan(reopened.ranks[back])
})

// A click raises whatever unit the pointer was in — which covers the common case
// and nothing else. **Opening a panel raises too**: keyboard activation, or a
// panel opened by another panel's reaction, is not a pointerdown, and the panel
// that just appeared would otherwise land behind a window sitting over its chain.
//
// Both opens here are by keyboard on purpose. `.focus()` + Enter dispatches a
// `click` with no pointer event, so the click-raise cannot be what moves the unit
// — which is what makes this test about the rule and not about the listener.
test('opening a panel brings its unit to the front', async ({ page }) => {
  await bootGmPanel(page, character)
  await enterPrep(page)

  // A character's panel in the chain, detached: the window starts on top.
  await page.locator('.filter-input:visible').first().fill('Kael Drift')
  await page.waitForTimeout(900)
  await page.locator('.suggestion-row:visible').first().click()
  await page.waitForTimeout(1600)
  await page.locator(DETACH).last().click()
  await page.waitForTimeout(900)

  const start = await stack(page)
  const float = Object.keys(start.ranks).find((id) => id !== 'root')
  expect(start.ranks[float], 'the new window is on top').toBeGreaterThan(start.ranks.root)

  // Open a panel in the chain, by keyboard only.
  await page.getByRole('button', { name: /manage traits/i }).focus()
  await page.keyboard.press('Enter')
  await page.waitForTimeout(1400)
  const inChain = await stack(page)
  expect(inChain.ranks.root, 'opening a panel in the chain brought the chain forward')
    .toBeGreaterThan(inChain.ranks[float])

  // …and the other direction: a panel opened *inside* the window raises the window.
  const sheetBtn = page.locator(`${FLOATS} .section-btn:visible`).first()
  await expect(sheetBtn, 'the floating entity panel offers its sheet').toBeVisible()
  await sheetBtn.focus()
  await page.keyboard.press('Enter')
  await page.waitForTimeout(2000)
  const inFloat = await stack(page)
  expect(inFloat.ranks[float], 'opening a panel inside the window brought the window forward')
    .toBeGreaterThan(inFloat.ranks.root)
})
